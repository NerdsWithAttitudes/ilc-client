"""Optional CKKS executable-encryption provider backed by OpenFHE Python."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, prod
from numbers import Real
from typing import Any
from uuid import uuid4

from ..errors import (
    DepthBudgetError,
    MissingDependencyError,
    ProviderConfigurationError,
)
from ..program import PlainProgram
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


@dataclass(frozen=True)
class CKKSEncryptedProgram:
    session_id: str
    program_id: str
    _encrypted_metadata: CKKSEncryptedTensor = field(repr=False)
    provider_id: str = field(default="ckks", init=False)
    representation_type: str = field(default="ckks_numeric_program_encoding_v1", init=False)


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
        required_depth = required_program_depth(program)
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
        metadata = _program_metadata(program)
        return CKKSEncryptedProgram(
            session_id=self._session.session_id,
            program_id=program.id,
            _encrypted_metadata=self.encrypt_tensor(PlainTensor(values=metadata, shape=(len(metadata),))),
        )

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


def _program_metadata(program: PlainProgram) -> tuple[float, ...]:
    values = [1.0, float(len(program.nodes)), float(len(program.input_ids)), float(len(program.output_ids))]
    op_code = {"INPUT": 0.0, "ADD": 1.0, "MUL": 2.0, "GEMM": 3.0}
    for node in program.nodes:
        values.append(op_code[node.op.name])
        values.append(float(len(node.inputs)))
        values.append(float(len(node.output_shape)))
        values.extend(float(dim) for dim in node.output_shape)
    return tuple(values)
