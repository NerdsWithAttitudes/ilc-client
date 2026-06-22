from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import tinychain as tc

from .config import DEFAULT_CLIENT_WASM_PATH


def build_local_kernel(
    schema_owner,
    *,
    data_dir: Path,
    token_host: Optional[str] = None,
    actor_id: Optional[str] = None,
    public_key_b64: Optional[str] = None,
) -> object:
    """Build a local TinyChain kernel preloaded with the given library schema."""
    if not hasattr(tc, "KernelHandle"):
        raise RuntimeError("tinychain-local is required for local PyO3 kernel usage")

    if token_host and actor_id and public_key_b64:
        token = tc.auth.SignedBearerToken(
            host=token_host,
            actor_id=actor_id,
            public_key_b64=public_key_b64,
            bearer_token="",
        )
        return tc.kernel.with_library(schema_owner, data_dir=data_dir, token=token)

    return tc.kernel.with_library(schema_owner, data_dir=data_dir)


def wasm_install(
    schema_owner,
    *,
    bearer_token: str,
    wasm_path: Path = DEFAULT_CLIENT_WASM_PATH,
    expected_sha256: Optional[str] = None,
    kernel: Optional[object] = None,
    data_dir: Optional[Path] = None,
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

    token = tc.auth.SignedBearerToken(
        host="",
        actor_id="",
        public_key_b64="",
        bearer_token=bearer_token,
    )
    try:
        return tc.install(
            schema_owner,
            wasm=wasm_path,
            kernel=kernel,
            data_dir=data_dir,
            token=token,
        )
    except ValueError as e:
        if str(e) == "invalid bearer token":
            route = getattr(schema_owner, "route_root", str(schema_owner.id().path))
            raise RuntimeError(
                "WASM install token was rejected by the local TinyChain verifier. "
                f"TC_INSTALL_BEARER_TOKEN must be a raw RJWT bearer token which "
                f"authorizes installing {route}, not an Authorization header and "
                "not a runtime-only route token. It must be signed by TC_ACTOR_ID "
                "for TC_TOKEN_HOST using the public key in TC_PUBLIC_KEY_B64."
            ) from e
        raise
