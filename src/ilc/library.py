from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TypeAlias, TypedDict
from urllib import error as urlerror
from urllib import request as urlrequest

import tinychain as tc
from tinychain.library import Library
from tinychain.uri import URI

from .config import (
    CLIENT_NAME,
    DEFAULT_COMPUTE,
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_HTTP_TIMEOUT_SECS,
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SCALAR_PAYLOAD_DIMS,
    DEFAULT_SERVER_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    DEFAULT_VERSION,
    ENV_TC_BEARER_TOKEN,
    ENV_TC_PUBLIC_KEY_B64,
    ENV_TC_TOKEN_HOST,
    NANOS_PER_SECOND,
    PUBLISHER,
    SERVER_NAME,
    server_library_root,
)

JsonDict: TypeAlias = dict[str, Any]


class SetupRequest(TypedDict):
    params: JsonDict
    secret_metric: list[int]
    payload_dims: int
    nonce_dims: int
    nonce_bound: int
    salt_hex: str | None


class EncryptScalarResponse(TypedDict):
    ciphertext: JsonDict


class DecryptResponse(TypedDict, total=False):
    payload: list[int]


class EvaluatorRequest(TypedDict, total=False):
    metric: list[int]
    lhs: list[float]
    rhs: list[float]
    auth_token: str
    auth_public_key_hex: str
    auth_host: str
    txn_timestamp_min: int
    txn_timestamp_max: int


class ILCServer(Library):
    publisher = PUBLISHER
    name = SERVER_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_SERVER_AUTHORITY)

    @classmethod
    def with_authority(cls, authority: str, *, version: str = DEFAULT_VERSION) -> "ILCServer":
        return cls(version=version, authority=URI.parse(authority))

    @property
    def route_root(self) -> str:
        return self.id().path

    def setup(
        self,
        *,
        params: JsonDict,
        secret_metric: list[int],
        payload_dims: int,
        nonce_dims: int,
        nonce_bound: int,
        salt_hex: str | None = None,
    ) -> tc.OpRef:
        return tc.OpRef(
            "POST",
            f"{self.route_root}/setup",
            body={
                "params": params,
                "secret_metric": secret_metric,
                "payload_dims": payload_dims,
                "nonce_dims": nonce_dims,
                "nonce_bound": nonce_bound,
                "salt_hex": salt_hex,
            },
        )

    def session(
        self,
        *,
        bearer_token: str,
        timeout_secs: int = DEFAULT_HTTP_TIMEOUT_SECS,
    ) -> "ILCServerSession":
        return ILCServerSession(self, bearer_token=bearer_token, timeout_secs=timeout_secs)

    def encrypt(self, *, payload: list[int], budget_log2: int | None = None) -> tc.OpRef:
        body: dict[str, object] = {"payload": payload}
        if budget_log2 is not None:
            body["budget_log2"] = budget_log2
        return tc.OpRef("POST", f"{self.route_root}/encrypt", body=body)

    def decrypt(self, *, ciphertext: JsonDict) -> tc.OpRef:
        return tc.OpRef("POST", f"{self.route_root}/decrypt", body={"ciphertext": ciphertext})


class ILCClient(Library):
    publisher = PUBLISHER
    name = CLIENT_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_LOCAL_AUTHORITY)
    dependencies = (URI.parse(DEFAULT_SERVER_LIBRARY_ROOT),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not kwargs.get("dependencies"):
            dep_version = self.version
            object.__setattr__(
                self,
                "dependencies",
                (URI.parse(server_library_root(dep_version)),),
            )

    @classmethod
    def with_authority(cls, authority: str, *, version: str = DEFAULT_VERSION) -> "ILCClient":
        return cls(version=version, authority=URI.parse(authority))

    @property
    def route_root(self) -> str:
        return self.id().path

    def add(
        self,
        *,
        metric: list[int],
        lhs: list[float],
        rhs: list[float],
        auth_token: str,
        auth_public_key_hex: str,
        auth_host: str,
        txn_timestamp_min: int | None = None,
        txn_timestamp_max: int | None = None,
    ) -> tc.OpRef:
        body: EvaluatorRequest = {
            "metric": metric,
            "lhs": lhs,
            "rhs": rhs,
            "auth_token": auth_token,
            "auth_public_key_hex": auth_public_key_hex,
            "auth_host": auth_host,
        }
        if txn_timestamp_min is not None:
            body["txn_timestamp_min"] = txn_timestamp_min
        if txn_timestamp_max is not None:
            body["txn_timestamp_max"] = txn_timestamp_max

        return tc.OpRef(
            "POST",
            f"{self.route_root}/add",
            body=body,
        )

    def mul(
        self,
        *,
        metric: list[int],
        lhs: list[float],
        rhs: list[float],
        auth_token: str,
        auth_public_key_hex: str,
        auth_host: str,
        txn_timestamp_min: int | None = None,
        txn_timestamp_max: int | None = None,
    ) -> tc.OpRef:
        body: EvaluatorRequest = {
            "metric": metric,
            "lhs": lhs,
            "rhs": rhs,
            "auth_token": auth_token,
            "auth_public_key_hex": auth_public_key_hex,
            "auth_host": auth_host,
        }
        if txn_timestamp_min is not None:
            body["txn_timestamp_min"] = txn_timestamp_min
        if txn_timestamp_max is not None:
            body["txn_timestamp_max"] = txn_timestamp_max

        return tc.OpRef(
            "POST",
            f"{self.route_root}/mul",
            body=body,
        )

    def add_scalars(
        self,
        *,
        a: float,
        b: float,
        auth: "AuthContext",
        metric: list[int] | None = None,
    ) -> tc.OpRef:
        metric = metric or list(DEFAULT_COMPUTE.metric)
        return self.add(
            metric=metric,
            lhs=[float(a), 0.0],
            rhs=[float(b), 0.0],
            **auth.op_kwargs(),
        )

    def sub_scalars(
        self,
        *,
        a: float,
        b: float,
        auth: "AuthContext",
        metric: list[int] | None = None,
    ) -> tc.OpRef:
        metric = metric or list(DEFAULT_COMPUTE.metric)
        return self.add(
            metric=metric,
            lhs=[float(a), 0.0],
            rhs=[-float(b), 0.0],
            **auth.op_kwargs(),
        )

    def wasm_install(
        self,
        *,
        bearer_token: str,
        wasm_path: Path = DEFAULT_CLIENT_WASM_PATH,
        kernel: Optional[object] = None,
        data_dir: Optional[Path] = None,
    ) -> object:
        """
        Install the precompiled ILC client WASM into a local TinyChain kernel.

        Note: this package intentionally does not ship or commit WASM binaries.
        """
        if not wasm_path.exists():
            raise FileNotFoundError(
                f"WASM file not found at {wasm_path}. Build/provision it separately and pass --wasm-path."
            )

        return tc.wasm.install(
            self.schema(),
            wasm_path,
            kernel=kernel,
            data_dir=data_dir,
            bearer_token=bearer_token,
        )


def build_local_kernel(
    client: ILCClient,
    *,
    data_dir: Path,
    token_host: Optional[str] = None,
    actor_id: Optional[str] = None,
    public_key_b64: Optional[str] = None,
) -> object:
    """Build a local PyO3 TinyChain kernel preloaded with the ILC client schema."""
    if not hasattr(tc, "KernelHandle"):
        raise RuntimeError("tinychain-local is required for local PyO3 kernel usage")

    if token_host and actor_id and public_key_b64:
        return tc.KernelHandle.with_library_schema_rjwt(
            client.schema_json(),
            token_host,
            actor_id,
            public_key_b64,
            data_dir=str(data_dir),
        )

    return tc.KernelHandle.with_library_schema(client.schema_json())


@dataclass(frozen=True)
class AuthContext:
    auth_token: str
    auth_public_key_hex: str
    auth_host: str
    txn_timestamp_min: int | None = None
    txn_timestamp_max: int | None = None

    @classmethod
    def from_public_key_b64(
        cls,
        *,
        auth_token: str,
        public_key_b64: str,
        auth_host: str,
        infer_token_window: bool = True,
    ) -> "AuthContext":
        txn_min = None
        txn_max = None
        if infer_token_window:
            window = token_validity_window(auth_token)
            if window:
                txn_min, txn_max = window

        return cls(
            auth_token=auth_token,
            auth_public_key_hex=public_key_hex_from_b64(public_key_b64),
            auth_host=auth_host,
            txn_timestamp_min=txn_min,
            txn_timestamp_max=txn_max,
        )

    @classmethod
    def from_env(
        cls,
        *,
        auth_token: str | None = None,
        auth_host: str | None = None,
        public_key_b64: str | None = None,
        infer_token_window: bool = True,
    ) -> "AuthContext":
        token = auth_token or os.environ.get(ENV_TC_BEARER_TOKEN)
        host = auth_host or os.environ.get(ENV_TC_TOKEN_HOST)
        key_b64 = public_key_b64 or os.environ.get(ENV_TC_PUBLIC_KEY_B64)

        if not token:
            raise ValueError(f"missing auth token (set {ENV_TC_BEARER_TOKEN})")
        if not host:
            raise ValueError(f"missing auth host (set {ENV_TC_TOKEN_HOST})")
        if not key_b64:
            raise ValueError(f"missing public key (set {ENV_TC_PUBLIC_KEY_B64})")

        return cls.from_public_key_b64(
            auth_token=token,
            public_key_b64=key_b64,
            auth_host=host,
            infer_token_window=infer_token_window,
        )

    def op_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "auth_token": self.auth_token,
            "auth_public_key_hex": self.auth_public_key_hex,
            "auth_host": self.auth_host,
        }
        if self.txn_timestamp_min is not None:
            kwargs["txn_timestamp_min"] = self.txn_timestamp_min
        if self.txn_timestamp_max is not None:
            kwargs["txn_timestamp_max"] = self.txn_timestamp_max
        return kwargs


def _base_url(authority: str) -> str:
    authority = authority.strip().rstrip("/")
    if "://" not in authority:
        authority = f"http://{authority}"
    return authority


def _decode_state(value):
    # Normalize TinyChain scalar wrappers to plain JSON-like values.
    if isinstance(value, list):
        return [_decode_state(v) for v in value]
    if isinstance(value, dict):
        if len(value) == 1:
            key, inner = next(iter(value.items()))
            if key.startswith("/state/scalar/value/"):
                return _decode_state(inner)
            if key == "/state/scalar/map":
                if isinstance(inner, dict):
                    return {k: _decode_state(v) for k, v in inner.items()}
                return _decode_state(inner)
        return {k: _decode_state(v) for k, v in value.items()}
    return value


def _unwrap_response(payload: dict) -> dict:
    # Responses may be wrapped in {"body": ...} and/or a single top-level state key.
    body = payload.get("body", payload)
    if isinstance(body, dict) and len(body) == 1:
        only = next(iter(body.values()))
        if isinstance(only, dict):
            return only
    if isinstance(body, dict):
        return body
    raise RuntimeError(f"unexpected response body shape: {payload!r}")


def post_json(
    *,
    authority: str,
    path: str,
    payload: JsonDict,
    bearer_token: str,
    timeout_secs: int = DEFAULT_HTTP_TIMEOUT_SECS,
) -> JsonDict:
    req = urlrequest.Request(
        f"{_base_url(authority)}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_secs) as resp:
            body = resp.read().decode("utf-8")
            decoded = _decode_state(json.loads(body) if body else {})
            if not isinstance(decoded, dict):
                raise RuntimeError(f"unexpected response shape: {decoded!r}")
            return _unwrap_response(decoded)
    except urlerror.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} failed: HTTP {err.code}: {detail}") from err


class ILCServerSession:
    """Authenticated wrapper for ILC server routes."""

    def __init__(
        self,
        server: ILCServer,
        *,
        bearer_token: str,
        timeout_secs: int = DEFAULT_HTTP_TIMEOUT_SECS,
    ):
        self.server = server
        self.bearer_token = bearer_token
        self.timeout_secs = timeout_secs

    def post(self, path: str, payload: JsonDict) -> JsonDict:
        return post_json(
            authority=str(self.server.authority),
            path=path,
            payload=payload,
            bearer_token=self.bearer_token,
            timeout_secs=self.timeout_secs,
        )

    def setup(
        self,
        *,
        params: JsonDict,
        secret_metric: list[int],
        payload_dims: int,
        nonce_dims: int,
        nonce_bound: int,
        salt_hex: str | None = None,
    ) -> JsonDict:
        request: SetupRequest = {
            "params": params,
            "secret_metric": secret_metric,
            "payload_dims": payload_dims,
            "nonce_dims": nonce_dims,
            "nonce_bound": nonce_bound,
            "salt_hex": salt_hex,
        }
        return self.post(
            f"{self.server.route_root}/setup",
            request,
        )

    def encrypt_scalar(
        self,
        value: int,
        *,
        payload_dims: int = DEFAULT_SCALAR_PAYLOAD_DIMS,
    ) -> EncryptScalarResponse:
        return self.post(
            f"{self.server.route_root}/encrypt",
            {"payload": [int(value)] + [0] * (payload_dims - 1)},
        )

    def decrypt(self, ciphertext: JsonDict) -> DecryptResponse:
        return self.post(f"{self.server.route_root}/decrypt", {"ciphertext": ciphertext})


def public_key_hex_from_b64(public_key_b64: str) -> str:
    key_bytes = base64.b64decode(public_key_b64, validate=True)
    if len(key_bytes) != 32:
        raise ValueError(f"expected 32-byte public key, got {len(key_bytes)} bytes")
    return binascii.hexlify(key_bytes).decode("ascii")


def token_validity_window(token: str) -> tuple[int, int] | None:
    segments = token.split(".")
    if len(segments) < 2:
        return None

    payload = segments[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        claims = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None

    iat = claims.get("iat")
    exp = claims.get("exp")
    if iat is None or exp is None:
        return None

    try:
        iat_ns = int(iat) * NANOS_PER_SECOND
        exp_ns = int(exp) * NANOS_PER_SECOND
    except (TypeError, ValueError):
        return None

    if exp_ns <= iat_ns:
        return None

    return iat_ns, exp_ns
