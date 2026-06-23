from __future__ import annotations
from contextlib import contextmanager
import hashlib
import inspect
import json
import os
from pathlib import Path
from typing import Iterator, Optional

import tinychain as tc
import tinychain.executor as tc_executor
from tinychain.uri import URI

from .config import (
    DEFAULT_CLIENT_WASM_PATH,
    ENV_TC_ACTOR_ID,
    ENV_TC_PUBLIC_KEY_B64,
)
from .library import ILCServer


def _normalize_bearer_token(bearer_token: str) -> str:
    token = bearer_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def build_local_kernel(
    schema_owner,
    *,
    data_dir: Path,
    token_host: Optional[str] = None,
    actor_id: Optional[str] = None,
    public_key_b64: Optional[str] = None,
    server_authority: Optional[str] = None,
) -> object:
    """Build a local TinyChain kernel preloaded with the given library schema."""
    if not hasattr(tc, "KernelHandle"):
        raise RuntimeError("tinychain-local is required for local PyO3 kernel usage")

    if hasattr(tc, "kernel") and hasattr(tc.kernel, "with_library"):
        token = None
        if token_host and actor_id and public_key_b64:
            token = tc.auth.SignedBearerToken(
                host=token_host,
                actor_id=actor_id,
                public_key_b64=public_key_b64,
                bearer_token="",
                alg="falcon512",
            )
        if server_authority is not None:
            schema_owner.ilc_server = ILCServer(authority=URI.parse(server_authority))
        try:
            return tc.kernel.with_library(schema_owner, data_dir=data_dir, token=token)
        except ValueError as exc:
            if "dependency" not in str(exc):
                raise
            from tinychain import _local

            definition_json = json.dumps(
                {schema_owner.id().path: {}},
                separators=(",", ":"),
            )
            try:
                return _local.kernel_with_library_definition(
                    definition_json,
                    token=token,
                    data_dir=str(data_dir),
                )
            except ValueError as token_exc:
                if "public key" not in str(token_exc):
                    raise
                return _local.kernel_with_library_definition(
                    definition_json,
                    token=None,
                    data_dir=str(data_dir),
                )

    if token_host and actor_id and public_key_b64 and hasattr(
        tc.KernelHandle,
        "with_library_schema_rjwt",
    ):
        return tc.KernelHandle.with_library_schema_rjwt(
            schema_owner.schema_json(),
            token_host,
            actor_id,
            public_key_b64,
            data_dir=str(data_dir),
        )

    if hasattr(tc.KernelHandle, "with_library_schema"):
        return tc.KernelHandle.with_library_schema(schema_owner.schema_json())

    raise RuntimeError(
        "tinychain-local backend does not expose a supported library kernel constructor"
    )


@contextmanager
def backend_context(
    kernel: object | None = None,
    *,
    bearer_token: str | None = None,
    mode: str = "eager",
) -> Iterator[None]:
    """Open a TinyChain backend context using the installed framework API."""

    params = inspect.signature(tc.backend).parameters
    kwargs: dict[str, object] = {}
    if bearer_token is not None:
        bearer_token = _normalize_bearer_token(bearer_token)
        if "token" in params:
            kwargs["token"] = bearer_token
        elif "bearer_token" in params:
            kwargs["bearer_token"] = bearer_token
    if "mode" in params:
        kwargs["mode"] = mode
    elif "auto_execute" in params:
        kwargs["auto_execute"] = mode == "eager"

    with tc.backend(kernel, **kwargs):
        yield


def execute_route(op: object) -> object:
    """Execute an explicit TinyChain route plan."""

    return tc_executor.execute(op)


def wasm_install(
    schema_owner,
    *,
    bearer_token: str,
    wasm_path: Path = DEFAULT_CLIENT_WASM_PATH,
    expected_sha256: Optional[str] = None,
    kernel: Optional[object] = None,
    data_dir: Optional[Path] = None,
    token_host: Optional[str] = None,
    actor_id: Optional[str] = None,
    public_key_b64: Optional[str] = None,
) -> object:
    """Install a precompiled WASM library into a local TinyChain kernel."""
    if not wasm_path.exists():
        raise FileNotFoundError(
            f"WASM file not found at {wasm_path}. Build/provision it separately and pass --wasm-path."
        )

    if expected_sha256:
        digest = hashlib.sha256(wasm_path.read_bytes()).hexdigest().lower()
        expected = expected_sha256.strip().lower()
        if digest != expected:
            raise ValueError(
                "WASM SHA-256 mismatch: "
                f"expected {expected}, got {digest} for {wasm_path}"
            )

    if hasattr(tc, "install"):
        token_host = token_host or schema_owner.id().path
        actor_id = actor_id or os.environ.get(ENV_TC_ACTOR_ID, "")
        public_key_b64 = public_key_b64 or os.environ.get(ENV_TC_PUBLIC_KEY_B64, "")
        token = tc.auth.SignedBearerToken(
            host=token_host,
            actor_id=actor_id,
            public_key_b64=public_key_b64,
            bearer_token=_normalize_bearer_token(bearer_token),
            alg="falcon512",
        )
        try:
            return tc.install(
                schema_owner,
                wasm=wasm_path,
                kernel=kernel,
                data_dir=data_dir,
                token=token,
            )
        except ValueError as exc:
            if "invalid bearer token" not in str(exc):
                raise
            raise RuntimeError(
                "WASM install token was rejected by the local TinyChain verifier. "
                "Check that TC_INSTALL_BEARER_TOKEN is a raw RJWT bearer token, not an "
                f"Authorization header, and that it is signed by actor_id={actor_id!r} "
                f"for TC_TOKEN_HOST={token_host!r} using the Falcon-512 public key in "
                "TC_PUBLIC_KEY_B64. The token must also authorize installing "
                f"{schema_owner.id().path}."
            ) from exc

    return tc.wasm.install(
        schema_owner.schema(),
        wasm_path,
        kernel=kernel,
        data_dir=data_dir,
        bearer_token=_normalize_bearer_token(bearer_token),
    )
