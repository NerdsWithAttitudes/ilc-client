"""Optional CKKS executable-encryption provider backed by OpenFHE Python."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite, prod
from numbers import Real
from typing import Any
from uuid import uuid4

from ..encoding import EncryptedGraphProgram, encode_program, validate_encrypted_graph_program
from ..errors import (
    DepthBudgetError,
    MissingDependencyError,
    ProgramValidationError,
    ProviderConfigurationError,
    ShapeMismatchError,
)
from ..program import PlainProgram, ProgramOp
from ..session import compute_fingerprint
from ..tensors import PlainTensor
from ..validation import required_program_depth
from ._helpers import gemm_shape, validate_pair, validate_tensor


@dataclass(frozen=True)
class CKKSConfig:
    """Public CKKS configuration for correctness-first scalar packing."""

    multiplicative_depth: int = 4
    scaling_mod_size: int = 50
    first_mod_size: int = 60
    relative_tolerance: float = 1e-3
    absolute_tolerance: float = 1e-6
    packing: str = "scalar"
    ring_dimension: int | None = None

    def __post_init__(self) -> None:
        for name in ("multiplicative_depth", "scaling_mod_size", "first_mod_size"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("relative_tolerance", "absolute_tolerance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative real")
            object.__setattr__(self, name, float(value))
        if self.packing != "scalar":
            raise ValueError("only scalar CKKS packing is supported in V1")
        if self.ring_dimension is not None and (
            not isinstance(self.ring_dimension, int)
            or isinstance(self.ring_dimension, bool)
            or self.ring_dimension <= 0
        ):
            raise ValueError("ring_dimension must be a positive integer when set")


@dataclass(frozen=True)
class CKKSSession:
    """Public CKKS session metadata plus provider-owned OpenFHE public material."""

    provider_id: str
    session_id: str
    config_fingerprint: str
    config: CKKSConfig
    _context: Any = field(repr=False)
    _public_key: Any = field(repr=False)


@dataclass(frozen=True)
class CKKSEncryptedTensor:
    session_id: str
    shape: tuple[int, ...]
    depth_used: int
    _ciphertexts: tuple[Any, ...] = field(repr=False)
    provider_id: str = field(default="ckks", init=False)

    def __post_init__(self) -> None:
        shape = tuple(int(dim) for dim in self.shape)
        ciphertexts = tuple(self._ciphertexts)
        if not shape or any(dim <= 0 for dim in shape):
            raise ValueError("shape must contain positive dimensions")
        if len(ciphertexts) != prod(shape):
            raise ValueError("ciphertext count must match shape product")
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "_ciphertexts", ciphertexts)


CKKSEncryptedProgram = EncryptedGraphProgram[CKKSEncryptedTensor]


class CKKSProvider:
    """OpenFHE-backed CKKS provider with scalar-packed tensor operations."""

    def __init__(self, config: CKKSConfig | None = None) -> None:
        self._openfhe = _require_openfhe()
        self._config = config or CKKSConfig()
        context = self._make_context(self._config)
        key_pair = context.KeyGen()
        public_key = _public_attr(key_pair, ("publicKey", "public_key", "GetPublicKey"))
        secret_key = _public_attr(key_pair, ("secretKey", "secret_key", "GetSecretKey"))
        context.EvalMultKeyGen(secret_key)
        self._session = CKKSSession(
            provider_id="ckks",
            session_id=uuid4().hex,
            config_fingerprint=compute_fingerprint("ckks", _fingerprint_payload(self._config)),
            config=self._config,
            _context=context,
            _public_key=public_key,
        )
        self._secret_key = secret_key

    @property
    def provider_id(self) -> str:
        return "ckks"

    @property
    def session(self) -> CKKSSession:
        return self._session

    @property
    def absolute_tolerance(self) -> float:
        return self._config.absolute_tolerance

    @property
    def relative_tolerance(self) -> float:
        return self._config.relative_tolerance

    def validate_program(self, program: PlainProgram) -> None:
        program.revalidate()
        required_depth = max(required_program_depth(program), _required_encrypted_graph_depth(program))
        if required_depth > self._config.multiplicative_depth:
            raise DepthBudgetError(
                "program exceeds CKKS multiplicative-depth budget",
                operation="validate_program",
                required_depth=required_depth,
                configured_depth=self._config.multiplicative_depth,
            )

    def encrypt_tensor(self, tensor: PlainTensor) -> CKKSEncryptedTensor:
        return CKKSEncryptedTensor(
            session_id=self._session.session_id,
            shape=tensor.shape,
            depth_used=0,
            _ciphertexts=tuple(self._encrypt_scalar(value) for value in tensor.values),
        )

    def encrypt_program(
        self,
        program: PlainProgram,
        *,
        assume_validated: bool = False,
    ) -> CKKSEncryptedProgram:
        if not assume_validated:
            self.validate_program(program)
        encoding = encode_program(program)
        return EncryptedGraphProgram[CKKSEncryptedTensor](
            provider_id="ckks",
            session_id=self._session.session_id,
            program_id=program.id,
            node_ids=encoding.node_ids,
            input_ids=encoding.input_ids,
            output_ids=encoding.output_ids,
            node_shapes=encoding.node_shapes,
            encrypted_tensors={
                name: self.encrypt_tensor(tensor)
                for name, tensor in encoding.tensors.items()
            },
        )

    def execute_program(
        self,
        encrypted_program: CKKSEncryptedProgram,
        inputs: Mapping[str, CKKSEncryptedTensor],
    ) -> Mapping[str, CKKSEncryptedTensor]:
        """Execute an encrypted-program artifact through local CKKS operations.

        CKKS V1 encrypts the graph/tensor representation and keeps execution
        entirely client-side. The executor uses only public shape metadata plus
        encrypted opcode, input, output, and operand selectors; it does not
        inspect a plaintext graph.
        """

        self._validate_encrypted_program_artifact(encrypted_program)
        input_values = self._validate_execution_inputs(encrypted_program, inputs)
        values: list[CKKSEncryptedTensor] = []
        anchor = self._anchor_ciphertext(encrypted_program)

        for node_index, output_shape in enumerate(encrypted_program.node_shapes):
            terms: list[CKKSEncryptedTensor] = []
            terms.extend(self._encrypted_input_terms(encrypted_program, input_values, node_index, output_shape))
            terms.extend(self._encrypted_operation_terms(encrypted_program, values, node_index, output_shape))
            values.append(self._sum_or_zero(terms, output_shape, anchor))

        return {
            output_id: self._encrypted_output(encrypted_program, values, output_row)
            for output_row, output_id in enumerate(encrypted_program.output_ids)
        }

    def decrypt_tensor(self, tensor: CKKSEncryptedTensor) -> PlainTensor:
        tensor = self._validate_tensor(tensor, "decrypt_tensor")
        return PlainTensor(
            values=tuple(self._decrypt_scalar(ciphertext) for ciphertext in tensor._ciphertexts),
            shape=tensor.shape,
        )

    def add(self, lhs: CKKSEncryptedTensor, rhs: CKKSEncryptedTensor) -> CKKSEncryptedTensor:
        lhs, rhs = self._validate_pair(lhs, rhs, "add", same_shape=True)
        return CKKSEncryptedTensor(
            session_id=self._session.session_id,
            shape=lhs.shape,
            depth_used=max(lhs.depth_used, rhs.depth_used),
            _ciphertexts=tuple(
                self._call("add", lambda left=left, right=right: self._session._context.EvalAdd(left, right))
                for left, right in zip(lhs._ciphertexts, rhs._ciphertexts)
            ),
        )

    def mul(self, lhs: CKKSEncryptedTensor, rhs: CKKSEncryptedTensor) -> CKKSEncryptedTensor:
        lhs, rhs = self._validate_pair(lhs, rhs, "mul", same_shape=True)
        depth = self._next_depth("mul", lhs, rhs)
        return CKKSEncryptedTensor(
            session_id=self._session.session_id,
            shape=lhs.shape,
            depth_used=depth,
            _ciphertexts=tuple(
                self._call("mul", lambda left=left, right=right: self._session._context.EvalMult(left, right))
                for left, right in zip(lhs._ciphertexts, rhs._ciphertexts)
            ),
        )

    def gemm(self, lhs: CKKSEncryptedTensor, rhs: CKKSEncryptedTensor) -> CKKSEncryptedTensor:
        lhs, rhs = self._validate_pair(lhs, rhs, "gemm", same_shape=False)
        rows, shared, cols = gemm_shape(lhs.shape, rhs.shape)
        depth = self._next_depth("gemm", lhs, rhs)
        out = []
        for row in range(rows):
            for col in range(cols):
                acc = None
                for idx in range(shared):
                    product = self._call(
                        "gemm",
                        lambda left=lhs._ciphertexts[row * shared + idx], right=rhs._ciphertexts[idx * cols + col]: (
                            self._session._context.EvalMult(left, right)
                        ),
                    )
                    acc = product if acc is None else self._call(
                        "gemm",
                        lambda acc=acc, product=product: self._session._context.EvalAdd(acc, product),
                    )
                out.append(acc)
        return CKKSEncryptedTensor(
            session_id=self._session.session_id,
            shape=(rows, cols),
            depth_used=depth,
            _ciphertexts=tuple(out),
        )

    def _make_context(self, config: CKKSConfig) -> Any:
        try:
            params = self._openfhe.CCParamsCKKSRNS()
            params.SetMultiplicativeDepth(config.multiplicative_depth)
            params.SetScalingModSize(config.scaling_mod_size)
            if hasattr(params, "SetFirstModSize"):
                params.SetFirstModSize(config.first_mod_size)
            if hasattr(params, "SetBatchSize"):
                params.SetBatchSize(1)
            if config.ring_dimension is not None:
                if hasattr(params, "SetRingDim"):
                    params.SetRingDim(config.ring_dimension)
                else:
                    raise ProviderConfigurationError("OpenFHE binding does not expose SetRingDim")
            context = self._openfhe.GenCryptoContext(params)
            context.Enable(_feature(self._openfhe, "PKE"))
            context.Enable(_feature(self._openfhe, "KEYSWITCH"))
            context.Enable(_feature(self._openfhe, "LEVELEDSHE"))
            return context
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderConfigurationError(f"OpenFHE rejected CKKS configuration: {exc}") from exc

    def _encrypt_scalar(self, value: float) -> Any:
        return self._call(
            "encrypt",
            lambda: self._session._context.Encrypt(
                self._session._public_key,
                self._session._context.MakeCKKSPackedPlaintext([float(value)]),
            ),
        )

    def _decrypt_scalar(self, ciphertext: Any) -> float:
        plaintext = self._call("decrypt", lambda: self._session._context.Decrypt(self._secret_key, ciphertext))
        if hasattr(plaintext, "SetLength"):
            plaintext.SetLength(1)
        if hasattr(plaintext, "GetRealPackedValue"):
            values = plaintext.GetRealPackedValue()
        elif hasattr(plaintext, "GetCKKSPackedValue"):
            values = plaintext.GetCKKSPackedValue()
        else:
            raise ProviderConfigurationError("OpenFHE plaintext has no packed value accessor")
        value = values[0]
        return float(value.real if hasattr(value, "real") else value)

    def _next_depth(self, operation: str, lhs: CKKSEncryptedTensor, rhs: CKKSEncryptedTensor) -> int:
        depth = max(lhs.depth_used, rhs.depth_used) + 1
        if depth > self._config.multiplicative_depth:
            raise DepthBudgetError(
                f"{operation} exceeds CKKS multiplicative-depth budget",
                operation=operation,
                required_depth=depth,
                configured_depth=self._config.multiplicative_depth,
            )
        return depth

    def _validate_pair(
        self,
        lhs: object,
        rhs: object,
        operation: str,
        *,
        same_shape: bool,
    ) -> tuple[CKKSEncryptedTensor, CKKSEncryptedTensor]:
        return validate_pair(
            lhs,
            rhs,
            provider_id="ckks",
            session_id=self._session.session_id,
            expected_type=CKKSEncryptedTensor,
            operation=operation,
            same_shape=same_shape,
        )

    def _validate_tensor(self, tensor: object, operation: str) -> CKKSEncryptedTensor:
        return validate_tensor(
            tensor,
            provider_id="ckks",
            session_id=self._session.session_id,
            expected_type=CKKSEncryptedTensor,
            operation=operation,
        )

    def _validate_encrypted_program_artifact(
        self,
        encrypted_program: CKKSEncryptedProgram,
    ) -> None:
        try:
            validate_encrypted_graph_program(
                encrypted_program,
                provider_id="ckks",
                session_id=self._session.session_id,
            )
        except ProgramValidationError as exc:
            raise ProviderConfigurationError(str(exc)) from exc
        for name, encrypted_tensor in encrypted_program.encrypted_tensors.items():
            self._validate_tensor(encrypted_tensor, f"encrypted program tensor {name!r}")

    def _validate_execution_inputs(
        self,
        encrypted_program: CKKSEncryptedProgram,
        inputs: Mapping[str, CKKSEncryptedTensor],
    ) -> dict[str, CKKSEncryptedTensor]:
        if set(inputs) != set(encrypted_program.input_ids):
            raise ProviderConfigurationError("encrypted execution input ids mismatch")
        node_index = {node_id: idx for idx, node_id in enumerate(encrypted_program.node_ids)}
        values = {}
        for input_id, tensor in inputs.items():
            encrypted_tensor = self._validate_tensor(tensor, f"execute_program input {input_id!r}")
            if encrypted_tensor.shape != encrypted_program.node_shapes[node_index[input_id]]:
                raise ProviderConfigurationError(f"execute_program input {input_id!r} shape mismatch")
            values[input_id] = encrypted_tensor
        return values

    def _encrypted_input_terms(
        self,
        encrypted_program: CKKSEncryptedProgram,
        inputs: Mapping[str, CKKSEncryptedTensor],
        node_index: int,
        output_shape: tuple[int, ...],
    ) -> list[CKKSEncryptedTensor]:
        node_by_id = {node_id: idx for idx, node_id in enumerate(encrypted_program.node_ids)}
        terms = []
        for input_col, input_id in enumerate(encrypted_program.input_ids):
            input_tensor = inputs[input_id]
            if input_tensor.shape != output_shape:
                continue
            selector, selector_depth = self._program_scalar(
                encrypted_program,
                "input_selector",
                node_index,
                input_col,
            )
            terms.append(self._scale_by_ciphertext(selector, selector_depth, input_tensor, "execute_program"))
        if encrypted_program.node_ids[node_index] in inputs:
            expected_shape = encrypted_program.node_shapes[node_by_id[encrypted_program.node_ids[node_index]]]
            if expected_shape != output_shape:
                raise ProviderConfigurationError("encrypted input node shape mismatch")
        return terms

    def _encrypted_operation_terms(
        self,
        encrypted_program: CKKSEncryptedProgram,
        values: list[CKKSEncryptedTensor],
        node_index: int,
        output_shape: tuple[int, ...],
    ) -> list[CKKSEncryptedTensor]:
        terms = []
        for lhs_index, lhs in enumerate(values):
            for rhs_index, rhs in enumerate(values):
                weight, weight_depth = self._encrypted_pair_weight(
                    encrypted_program,
                    node_index,
                    lhs_index,
                    rhs_index,
                )
                terms.extend(
                    self._weighted_candidates(
                        encrypted_program,
                        node_index,
                        output_shape,
                        lhs,
                        rhs,
                        weight,
                        weight_depth,
                    )
                )
        return terms

    def _weighted_candidates(
        self,
        encrypted_program: CKKSEncryptedProgram,
        node_index: int,
        output_shape: tuple[int, ...],
        lhs: CKKSEncryptedTensor,
        rhs: CKKSEncryptedTensor,
        pair_weight: Any,
        pair_weight_depth: int,
    ) -> list[CKKSEncryptedTensor]:
        terms = []
        if lhs.shape == output_shape and rhs.shape == output_shape:
            add_opcode, add_depth = self._opcode_weight(encrypted_program, node_index, ProgramOp.ADD)
            add_weight, add_weight_depth = self._multiply_ciphertexts(
                pair_weight,
                pair_weight_depth,
                add_opcode,
                add_depth,
                "execute_program selector",
            )
            terms.append(
                self._scale_by_ciphertext(
                    add_weight,
                    add_weight_depth,
                    self.add(lhs, rhs),
                    "execute_program add selector",
                )
            )

            mul_opcode, mul_depth = self._opcode_weight(encrypted_program, node_index, ProgramOp.MUL)
            mul_weight, mul_weight_depth = self._multiply_ciphertexts(
                pair_weight,
                pair_weight_depth,
                mul_opcode,
                mul_depth,
                "execute_program selector",
            )
            terms.append(
                self._scale_by_ciphertext(
                    mul_weight,
                    mul_weight_depth,
                    self.mul(lhs, rhs),
                    "execute_program mul selector",
                )
            )

        try:
            rows, _, cols = gemm_shape(lhs.shape, rhs.shape)
        except ShapeMismatchError:
            return terms
        if (rows, cols) != output_shape:
            return terms
        gemm_opcode, gemm_depth = self._opcode_weight(encrypted_program, node_index, ProgramOp.GEMM)
        gemm_weight, gemm_weight_depth = self._multiply_ciphertexts(
            pair_weight,
            pair_weight_depth,
            gemm_opcode,
            gemm_depth,
            "execute_program selector",
        )
        terms.append(
            self._scale_by_ciphertext(
                gemm_weight,
                gemm_weight_depth,
                self.gemm(lhs, rhs),
                "execute_program gemm selector",
            )
        )
        return terms

    def _encrypted_pair_weight(
        self,
        encrypted_program: CKKSEncryptedProgram,
        node_index: int,
        lhs_index: int,
        rhs_index: int,
    ) -> tuple[Any, int]:
        lhs_selector, lhs_depth = self._program_scalar(encrypted_program, "lhs_selector", node_index, lhs_index)
        rhs_selector, rhs_depth = self._program_scalar(encrypted_program, "rhs_selector", node_index, rhs_index)
        return self._multiply_ciphertexts(
            lhs_selector,
            lhs_depth,
            rhs_selector,
            rhs_depth,
            "execute_program selector",
        )

    def _encrypted_output(
        self,
        encrypted_program: CKKSEncryptedProgram,
        values: list[CKKSEncryptedTensor],
        output_row: int,
    ) -> CKKSEncryptedTensor:
        output_id = encrypted_program.output_ids[output_row]
        output_shape = encrypted_program.node_shapes[encrypted_program.node_ids.index(output_id)]
        terms = []
        for node_index, value in enumerate(values):
            if value.shape != output_shape:
                continue
            selector, selector_depth = self._program_scalar(
                encrypted_program,
                "output_selector",
                output_row,
                node_index,
            )
            terms.append(self._scale_by_ciphertext(selector, selector_depth, value, "execute_program output"))
        return self._sum_or_zero(terms, output_shape, self._anchor_ciphertext(encrypted_program))

    def _opcode_weight(
        self,
        encrypted_program: CKKSEncryptedProgram,
        node_index: int,
        op: ProgramOp,
    ) -> tuple[Any, int]:
        return self._program_scalar(encrypted_program, "opcode", node_index, _opcode_index(op))

    def _program_scalar(
        self,
        encrypted_program: CKKSEncryptedProgram,
        name: str,
        row: int,
        col: int,
    ) -> tuple[Any, int]:
        tensor = encrypted_program.encrypted_tensors[name]
        _, cols = tensor.shape
        return tensor._ciphertexts[row * cols + col], tensor.depth_used

    def _scale_by_ciphertext(
        self,
        scalar: Any,
        scalar_depth: int,
        tensor: CKKSEncryptedTensor,
        operation: str,
    ) -> CKKSEncryptedTensor:
        depth = self._next_depth_raw(operation, scalar_depth, tensor.depth_used)
        return CKKSEncryptedTensor(
            session_id=self._session.session_id,
            shape=tensor.shape,
            depth_used=depth,
            _ciphertexts=tuple(
                self._call(operation, lambda scalar=scalar, value=value: self._session._context.EvalMult(scalar, value))
                for value in tensor._ciphertexts
            ),
        )

    def _multiply_ciphertexts(
        self,
        lhs: Any,
        lhs_depth: int,
        rhs: Any,
        rhs_depth: int,
        operation: str,
    ) -> tuple[Any, int]:
        depth = self._next_depth_raw(operation, lhs_depth, rhs_depth)
        return (
            self._call(operation, lambda: self._session._context.EvalMult(lhs, rhs)),
            depth,
        )

    def _sum_or_zero(
        self,
        terms: list[CKKSEncryptedTensor],
        shape: tuple[int, ...],
        anchor: Any,
    ) -> CKKSEncryptedTensor:
        if not terms:
            zero = self._call("execute_program zero", lambda: self._session._context.EvalSub(anchor, anchor))
            return CKKSEncryptedTensor(
                session_id=self._session.session_id,
                shape=shape,
                depth_used=0,
                _ciphertexts=tuple(zero for _ in range(prod(shape))),
            )
        result = terms[0]
        for term in terms[1:]:
            if term.shape != result.shape:
                raise ProviderConfigurationError("execute_program attempted to sum mismatched shapes")
            result = CKKSEncryptedTensor(
                session_id=self._session.session_id,
                shape=result.shape,
                depth_used=max(result.depth_used, term.depth_used),
                _ciphertexts=tuple(
                    self._call("execute_program sum", lambda left=left, right=right: (
                        self._session._context.EvalAdd(left, right)
                    ))
                    for left, right in zip(result._ciphertexts, term._ciphertexts)
                ),
            )
        return result

    def _anchor_ciphertext(self, encrypted_program: CKKSEncryptedProgram) -> Any:
        return encrypted_program.encrypted_tensors["opcode"]._ciphertexts[0]

    def _next_depth_raw(self, operation: str, lhs_depth: int, rhs_depth: int) -> int:
        depth = max(lhs_depth, rhs_depth) + 1
        if depth > self._config.multiplicative_depth:
            raise DepthBudgetError(
                f"{operation} exceeds CKKS multiplicative-depth budget",
                operation=operation,
                required_depth=depth,
                configured_depth=self._config.multiplicative_depth,
            )
        return depth

    @staticmethod
    def _call(operation: str, fn: Any) -> Any:
        try:
            return fn()
        except (DepthBudgetError, ProviderConfigurationError):
            raise
        except Exception as exc:
            raise ProviderConfigurationError(f"OpenFHE failed during {operation}: {exc}") from exc


def _require_openfhe() -> Any:
    try:
        import openfhe  # type: ignore[import-not-found]
    except Exception as exc:
        raise MissingDependencyError("CKKSProvider requires optional OpenFHE Python bindings") from exc
    return openfhe


def _public_attr(value: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if hasattr(value, name):
            attr = getattr(value, name)
            return attr() if callable(attr) else attr
    raise ProviderConfigurationError(f"OpenFHE key pair lacks expected attributes {names!r}")


def _feature(openfhe: Any, name: str) -> Any:
    enum = getattr(openfhe, "PKESchemeFeature", None)
    if enum is not None and hasattr(enum, name):
        return getattr(enum, name)
    return getattr(openfhe, name)


def _fingerprint_payload(config: CKKSConfig) -> dict[str, object]:
    return {
        "provider_id": "ckks",
        "multiplicative_depth": config.multiplicative_depth,
        "scaling_mod_size": config.scaling_mod_size,
        "first_mod_size": config.first_mod_size,
        "relative_tolerance": config.relative_tolerance,
        "absolute_tolerance": config.absolute_tolerance,
        "packing": config.packing,
        "ring_dimension": config.ring_dimension,
    }


def _opcode_index(op: ProgramOp) -> int:
    return {
        ProgramOp.INPUT: 0,
        ProgramOp.ADD: 1,
        ProgramOp.MUL: 2,
        ProgramOp.GEMM: 3,
    }[op]


def _required_encrypted_graph_depth(program: PlainProgram) -> int:
    depths: dict[str, int] = {}
    for node in program.nodes:
        if node.op == ProgramOp.INPUT:
            depths[node.id] = 1
            continue
        lhs_depth = depths[node.inputs[0]]
        rhs_depth = depths[node.inputs[1]]
        candidate_depth = max(lhs_depth, rhs_depth)
        if node.op in (ProgramOp.MUL, ProgramOp.GEMM):
            candidate_depth += 1
        depths[node.id] = max(2, candidate_depth) + 1
    return max(depths[output_id] + 1 for output_id in program.output_ids)
