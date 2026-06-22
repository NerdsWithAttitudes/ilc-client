"""Public ILC executable-encryption provider adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from math import isfinite, prod
from numbers import Real
from pathlib import Path
from typing import Any
from uuid import uuid4

import tinychain as tc
from tinychain.uri import URI

from ...config import (
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_SERVER_LIBRARY_ROOT,
    ENV_ILC_CLIENT_WASM_PATH,
    ENV_ILC_CLIENT_WASM_SHA256,
    ENV_ILC_LOCAL_AUTHORITY,
    ENV_ILC_SERVER_AUTHORITY,
    ENV_TC_ACTOR_ID,
    ENV_TC_BEARER_TOKEN,
    ENV_TC_INSTALL_BEARER_TOKEN,
    ENV_TC_PUBLIC_KEY_B64,
    ENV_TC_TOKEN_HOST,
)
from ...library import ILCClient, ILCServer
from ...runtime import build_local_kernel, wasm_install
from ..errors import (
    ProviderConfigurationError,
    UnsupportedOperationError,
)
from ..encoding import EncryptedGraphProgram, encode_program, validate_encrypted_graph_program
from ..program import PlainProgram
from ..session import BasicSession, compute_fingerprint
from ..tensors import PlainTensor
from ._helpers import validate_pair, validate_tensor


@dataclass(frozen=True)
class ILCConfig:
    scale_bits: int = 20
    relative_tolerance: float = 1e-3
    absolute_tolerance: float = 1e-6
    metric: tuple[int, ...] = (1,)
    setup_params: dict[str, Any] = field(
        default_factory=lambda: {"moduli": [65521, 65537, 65543], "params_id": [9] * 16}
    )
    payload_dims: int = 1
    nonce_dims: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.scale_bits, int) or self.scale_bits <= 0:
            raise ValueError("scale_bits must be a positive integer")
        for name in ("relative_tolerance", "absolute_tolerance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative real")
            object.__setattr__(self, name, float(value))
        object.__setattr__(self, "metric", tuple(int(value) for value in self.metric))


@dataclass(frozen=True)
class ILCEncryptedTensor:
    session_id: str
    shape: tuple[int, ...]
    _payload: Any = field(repr=False)
    provider_id: str = field(default="ilc", init=False)


ILCEncryptedProgram = EncryptedGraphProgram[ILCEncryptedTensor]


class ILCProvider:
    """Executable provider using public ILC server/client route wrappers."""

    def __init__(
        self,
        config: ILCConfig | None = None,
        *,
        server: ILCServer | None = None,
        client: ILCClient | None = None,
        public_context: dict[str, Any] | None = None,
        bearer_token: str | None = None,
        kernel: Any | None = None,
    ) -> None:
        self._config = config or ILCConfig()
        self._server = server or ILCServer()
        self._client = client or ILCClient()
        self._public_context = public_context
        self._bearer_token = bearer_token
        self._kernel = kernel
        self._session = BasicSession(
            provider_id="ilc",
            session_id=uuid4().hex,
            config_fingerprint=compute_fingerprint("ilc", self._config),
        )

    @classmethod
    def from_environment(cls, config: ILCConfig | None = None) -> "ILCProvider":
        token = os.environ.get(ENV_TC_BEARER_TOKEN)
        if not token:
            raise ProviderConfigurationError(f"ILCProvider requires {ENV_TC_BEARER_TOKEN} for live execution")
        install_token = os.environ.get(ENV_TC_INSTALL_BEARER_TOKEN, token)
        public_key = os.environ.get(ENV_TC_PUBLIC_KEY_B64)
        if not public_key:
            raise ProviderConfigurationError(f"ILCProvider requires {ENV_TC_PUBLIC_KEY_B64} for local WASM execution")
        actor_id = os.environ.get(ENV_TC_ACTOR_ID)
        if not actor_id:
            raise ProviderConfigurationError(f"ILCProvider requires {ENV_TC_ACTOR_ID} for Falcon-512 token verification")

        server_authority = os.environ.get("ILC_INTEGRATION_SERVER") or os.environ.get(ENV_ILC_SERVER_AUTHORITY)
        local_authority = os.environ.get(ENV_ILC_LOCAL_AUTHORITY)
        wasm_path = Path(os.environ.get("ILC_WASM_PATH") or os.environ.get(ENV_ILC_CLIENT_WASM_PATH) or DEFAULT_CLIENT_WASM_PATH)
        if not wasm_path.exists():
            raise ProviderConfigurationError(f"ILCProvider requires local WASM artifact at {wasm_path}")

        server = ILCServer(authority=URI.parse(server_authority)) if server_authority else ILCServer()
        client = ILCClient(authority=URI.parse(local_authority)) if local_authority else ILCClient()
        data_dir = Path(os.environ.get("ILC_EXECUTABLE_DATA_DIR", ".ilc-executable"))
        data_dir.mkdir(parents=True, exist_ok=True)
        token_host = os.environ.get(ENV_TC_TOKEN_HOST, DEFAULT_SERVER_LIBRARY_ROOT)
        kernel = build_local_kernel(
            client,
            data_dir=data_dir,
            token_host=token_host,
            actor_id=actor_id,
            public_key_b64=public_key,
        )
        install = wasm_install(
            client,
            bearer_token=install_token,
            wasm_path=wasm_path,
            expected_sha256=os.environ.get(ENV_ILC_CLIENT_WASM_SHA256),
            kernel=kernel,
            data_dir=data_dir,
            token_host=token_host,
            actor_id=actor_id,
            public_key_b64=public_key,
        )
        if getattr(install, "status", None) not in (None, 200, 201, 204):
            raise ProviderConfigurationError(f"ILC WASM install failed with status {getattr(install, 'status', None)}")
        return cls(config, server=server, client=client, bearer_token=token, kernel=kernel)

    @property
    def provider_id(self) -> str:
        return "ilc"

    @property
    def session(self) -> BasicSession:
        return self._session

    @property
    def absolute_tolerance(self) -> float:
        return self._config.absolute_tolerance

    @property
    def relative_tolerance(self) -> float:
        return self._config.relative_tolerance

    def validate_program(self, program: PlainProgram) -> None:
        program.revalidate()

    def encrypt_tensor(self, tensor: PlainTensor) -> ILCEncryptedTensor:
        self._ensure_public_context()
        scaled = [int(round(value * (1 << self._config.scale_bits))) for value in tensor.values]
        payload = self._execute(
            self._server.encrypt(
                public_context=self._public_context_or_raise(),
                payload=scaled,
                shape=list(tensor.shape),
                budget_log2=self._config.scale_bits,
            )
        )
        return ILCEncryptedTensor(
            session_id=self._session.session_id,
            shape=tensor.shape,
            _payload=payload,
        )

    def encrypt_program(
        self,
        program: PlainProgram,
        *,
        assume_validated: bool = False,
    ) -> ILCEncryptedProgram:
        if not assume_validated:
            self.validate_program(program)
        encoding = encode_program(program)
        return EncryptedGraphProgram[ILCEncryptedTensor](
            provider_id="ilc",
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
        encrypted_program: ILCEncryptedProgram,
        inputs: dict[str, ILCEncryptedTensor],
    ) -> dict[str, ILCEncryptedTensor]:
        validate_encrypted_graph_program(
            encrypted_program,
            provider_id="ilc",
            session_id=self._session.session_id,
        )
        for input_id, tensor in inputs.items():
            self._validate_tensor(tensor, f"execute_program input {input_id!r}")
        raise UnsupportedOperationError(
            "ILC encrypted-program execution is fail-closed because the current ILCClient evaluator still lacks "
            "the witness-free encrypted selector-scaling primitive required by the shared encrypted-selector "
            "interpreter. Program and input tensors are encrypted, and the remaining entirely client-side work is "
            "to expose ILCClient-backed zero_like, encrypted selector scaling, summation, add, mul, and gemm "
            "without additional server API or Rust backend changes."
        )

    def decrypt_tensor(self, tensor: ILCEncryptedTensor) -> PlainTensor:
        tensor = self._validate_tensor(tensor, "decrypt_tensor")
        self._ensure_public_context()
        raw = self._execute(
            self._server.decrypt(
                public_context=self._public_context_or_raise(),
                ciphertext=_ciphertext_dict(tensor._payload),
                handle=_handle_dict(tensor._payload),
            )
        )
        values = _values_from_decrypt(raw)
        scale = float(1 << self._config.scale_bits)
        expected = prod(tensor.shape)
        return PlainTensor(values=tuple(float(value) / scale for value in values[:expected]), shape=tensor.shape)

    def add(self, lhs: ILCEncryptedTensor, rhs: ILCEncryptedTensor) -> ILCEncryptedTensor:
        lhs, rhs = self._validate_pair(lhs, rhs, "add", same_shape=True)
        self._ensure_public_context()
        payload = self._execute(
            self._client.add(
                public_context=self._public_context_or_raise(),
                lhs_ciphertext=_ciphertext_dict(lhs._payload),
                rhs_ciphertext=_ciphertext_dict(rhs._payload),
            )
        )
        return ILCEncryptedTensor(self._session.session_id, lhs.shape, payload)

    def mul(self, lhs: ILCEncryptedTensor, rhs: ILCEncryptedTensor) -> ILCEncryptedTensor:
        self._validate_pair(lhs, rhs, "mul", same_shape=True)
        raise UnsupportedOperationError(
            "ILCProvider.mul requires a planned representative witness or a local selector-scaling primitive; "
            "the executable provider uses representative ciphertext contracts only."
        )

    def gemm(self, lhs: ILCEncryptedTensor, rhs: ILCEncryptedTensor) -> ILCEncryptedTensor:
        self._validate_pair(lhs, rhs, "gemm", same_shape=False)
        raise UnsupportedOperationError(
            "ILCProvider.gemm requires a planned representative witness or a local selector-scaling primitive; "
            "the executable provider uses representative ciphertext contracts only."
        )

    def _ensure_public_context(self) -> None:
        if self._public_context is not None:
            return
        raw = self._execute(
            self._server.setup(
                params=self._config.setup_params,
                payload_dims=self._config.payload_dims,
                nonce_dims=self._config.nonce_dims,
            )
        )
        public_context = _setup_public_context(raw)
        if public_context is None:
            raise ProviderConfigurationError("ILC setup response did not include public_context")
        self._public_context = public_context
        if isinstance(public_context.get("cipher_metric"), list):
            self._config = ILCConfig(
                scale_bits=self._config.scale_bits,
                relative_tolerance=self._config.relative_tolerance,
                absolute_tolerance=self._config.absolute_tolerance,
                metric=tuple(int(value) for value in public_context["cipher_metric"]),
                setup_params=self._config.setup_params,
                payload_dims=self._config.payload_dims,
                nonce_dims=self._config.nonce_dims,
            )

    def _public_context_or_raise(self) -> dict[str, Any]:
        if self._public_context is None:
            raise ProviderConfigurationError("ILC provider has no public_context")
        return self._public_context

    def _execute(self, op: Any) -> Any:
        try:
            if self._kernel is not None:
                with tc.backend(self._kernel, bearer_token=self._bearer_token):
                    return tc.execute(op)
            if self._bearer_token:
                return tc.execute(op, bearer_token=self._bearer_token)
            return tc.execute(op)
        except Exception as exc:
            raise ProviderConfigurationError(f"ILC execution failed: {exc}") from exc

    def _validate_pair(
        self,
        lhs: object,
        rhs: object,
        operation: str,
        *,
        same_shape: bool,
    ) -> tuple[ILCEncryptedTensor, ILCEncryptedTensor]:
        return validate_pair(
            lhs,
            rhs,
            provider_id="ilc",
            session_id=self._session.session_id,
            expected_type=ILCEncryptedTensor,
            operation=operation,
            same_shape=same_shape,
        )

    def _validate_tensor(self, tensor: object, operation: str) -> ILCEncryptedTensor:
        return validate_tensor(
            tensor,
            provider_id="ilc",
            session_id=self._session.session_id,
            expected_type=ILCEncryptedTensor,
            operation=operation,
        )


def _ciphertext_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    if isinstance(payload, dict):
        body = payload.get("body")
        if isinstance(body, dict):
            encrypted = body.get("RepresentativeEncrypt")
            if isinstance(encrypted, dict) and isinstance(encrypted.get("ciphertext"), dict):
                return encrypted["ciphertext"]
            added = body.get("RepresentativeAdd")
            if isinstance(added, dict) and isinstance(added.get("ciphertext"), dict):
                return added["ciphertext"]
        return payload
    raise ProviderConfigurationError("ILC ciphertext payload is not serializable")


def _handle_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        body = payload.get("body")
        if isinstance(body, dict):
            encrypted = body.get("RepresentativeEncrypt")
            if isinstance(encrypted, dict) and isinstance(encrypted.get("handle"), dict):
                return encrypted["handle"]
        handle = payload.get("handle")
        if isinstance(handle, dict):
            return handle
    raise ProviderConfigurationError("ILC ciphertext payload has no decrypt handle")


def _setup_public_context(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("public_context"), dict):
        return raw["public_context"]
    body = raw.get("body")
    if isinstance(body, dict):
        setup = body.get("RepresentativeSetup")
        if isinstance(setup, dict) and isinstance(setup.get("public_context"), dict):
            return setup["public_context"]
    setup = raw.get("RepresentativeSetup")
    if isinstance(setup, dict) and isinstance(setup.get("public_context"), dict):
        return setup["public_context"]
    return None


def _values_from_decrypt(raw: Any) -> list[float | int]:
    if isinstance(raw, dict):
        body = raw.get("body")
        if isinstance(body, dict):
            decrypted = body.get("RepresentativeDecrypt")
            if isinstance(decrypted, dict) and isinstance(decrypted.get("values"), list):
                return decrypted["values"]
        payload = raw.get("payload", raw)
        if isinstance(payload, dict) and isinstance(payload.get("values"), list):
            return payload["values"]
        if isinstance(raw.get("values"), list):
            return raw["values"]
    if isinstance(raw, list):
        return raw
    raise ProviderConfigurationError("ILC decrypt returned unsupported payload")
