#!/usr/bin/env python3
"""Mint short-lived Falcon-512 RJWT tokens for CI.

GitHub stores the Falcon private key as a secret. CI uses this script to mint
fresh runtime/install tokens inside each job, avoiding expiring bearer-token
secrets.
"""

from __future__ import annotations

import argparse
import base64
import os
import time


DEFAULT_CLIENT_LIBRARY_ROOT = "/lib/applied-physics/ilc_client/0.1.0"
DEFAULT_TTL_SECS = 3600.0
MODE_USER_RWX = 0o700


def _env(name: str, *, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value.strip():
        raise SystemExit(f"error: missing required environment variable {name}")
    return value.strip()


def _load_private_key() -> bytes:
    encoded = _env("TC_FALCON512_SECRET_KEY_B64")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit(f"error: TC_FALCON512_SECRET_KEY_B64 is not valid base64: {exc}") from exc


def _mint_tokens() -> tuple[str, str]:
    try:
        import rjwt
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "error: TinyChain rjwt-py with Falcon-512 support is required; install it with: "
            'pip install "rjwt-py @ git+https://github.com/TinyChain-Inc/rjwt.git#subdirectory=rjwt-py"'
        ) from exc

    actor_id = _env("TC_ACTOR_ID")
    if "/" in actor_id:
        raise SystemExit("error: TC_ACTOR_ID must not contain '/'")

    token_host = _env("TC_TOKEN_HOST").rstrip("/")
    client_lib = (os.environ.get("ILC_CLIENT_LIBRARY_ROOT") or DEFAULT_CLIENT_LIBRARY_ROOT).strip().rstrip("/")
    ttl_secs = float(os.environ.get("TC_TOKEN_TTL_SECS") or DEFAULT_TTL_SECS)
    if ttl_secs <= 0:
        raise SystemExit("error: TC_TOKEN_TTL_SECS must be positive")

    now = time.time()
    actor = rjwt.Actor.with_keypair(actor_id, _load_private_key(), "falcon512")

    runtime_token = rjwt.Token(
        token_host,
        now,
        ttl_secs,
        actor_id,
        {token_host: MODE_USER_RWX},
    )
    runtime_signed = actor.sign_token(runtime_token)

    install_signed = actor.consume_and_sign(
        runtime_signed,
        token_host,
        {client_lib: MODE_USER_RWX},
        now,
    )

    return runtime_signed.jwt(), install_signed.jwt()


def _write_github_env(runtime_token: str, install_token: str) -> None:
    github_env = os.environ.get("GITHUB_ENV")
    if not github_env:
        return

    print(f"::add-mask::{runtime_token}")
    print(f"::add-mask::{install_token}")
    with open(github_env, "a", encoding="utf-8") as handle:
        handle.write(f"TC_BEARER_TOKEN={runtime_token}\n")
        handle.write(f"TC_INSTALL_BEARER_TOKEN={install_token}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="print shell exports for local debugging; CI writes to GITHUB_ENV without printing tokens",
    )
    args = parser.parse_args()

    runtime_token, install_token = _mint_tokens()
    _write_github_env(runtime_token, install_token)

    if args.print_env:
        print(f"export TC_BEARER_TOKEN={runtime_token!r}")
        print(f"export TC_INSTALL_BEARER_TOKEN={install_token!r}")
    else:
        print("minted fresh Falcon-512 CI bearer tokens")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
