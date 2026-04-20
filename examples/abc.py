#!/usr/bin/env python3
"""Run `a + b - c` using a local WASM client and remote ILC server."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

import tinychain as tc
from tinychain.uri import URI

from ilc import (
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    ENV_ILC_CLIENT_WASM_SHA256,
    ENV_TC_ACTOR_ID,
    ENV_TC_BEARER_TOKEN,
    ENV_TC_INSTALL_BEARER_TOKEN,
    ENV_TC_PUBLIC_KEY_B64,
    ENV_TC_TOKEN_HOST,
    ILCClient,
    ILCServer,
    evaluate_abc,
    build_local_kernel,
    wasm_install,
)


@dataclass(frozen=True)
class RuntimeInputs:
    bearer_token: str
    install_bearer_token: str
    token_host: str
    actor_id: str | None
    public_key_b64: str
    wasm_sha256: str | None


def _missing_env_error() -> str:
    return (
        "Missing required environment variables.\n"
        "Set:\n"
        f"  export {ENV_TC_BEARER_TOKEN}=...\n"
        f"  export {ENV_TC_INSTALL_BEARER_TOKEN}=...   # may match {ENV_TC_BEARER_TOKEN}\n"
        f"  export {ENV_TC_PUBLIC_KEY_B64}=...\n"
        "Optional:\n"
        f"  export {ENV_ILC_CLIENT_WASM_SHA256}=<expected wasm sha256>\n"
        f"  export {ENV_TC_TOKEN_HOST}={DEFAULT_SERVER_LIBRARY_ROOT}\n"
        f"  export {ENV_TC_ACTOR_ID}=<group>/<user>\n"
        "Then run:\n"
        f"  python examples/abc.py --server {DEFAULT_LOCAL_AUTHORITY} "
        "--wasm-path /path/to/cipher_wasm.wasm"
    )


def _load_runtime_inputs(server: ILCServer) -> RuntimeInputs:
    bearer_token = os.environ.get(ENV_TC_BEARER_TOKEN)
    install_bearer_token = os.environ.get(ENV_TC_INSTALL_BEARER_TOKEN, bearer_token)
    token_host = os.environ.get(ENV_TC_TOKEN_HOST, server.route_root)
    actor_id = os.environ.get(ENV_TC_ACTOR_ID)
    public_key_b64 = os.environ.get(ENV_TC_PUBLIC_KEY_B64)
    wasm_sha256 = os.environ.get(ENV_ILC_CLIENT_WASM_SHA256)

    if not bearer_token or not install_bearer_token or not public_key_b64:
        raise RuntimeError(_missing_env_error())

    return RuntimeInputs(
        bearer_token=bearer_token,
        install_bearer_token=install_bearer_token,
        token_host=token_host,
        actor_id=actor_id,
        public_key_b64=public_key_b64,
        wasm_sha256=wasm_sha256,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        default=None,
        help="Override ILC server authority (e.g. https://api.tctest.net)",
    )
    parser.add_argument(
        "--wasm-path",
        default=str(DEFAULT_CLIENT_WASM_PATH),
        help="Path to prebuilt cipher_wasm.wasm",
    )
    parser.add_argument("--a", type=int, default=7)
    parser.add_argument("--b", type=int, default=5)
    parser.add_argument("--c", type=int, default=3)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved configuration only (no network/kernel actions)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output",
    )
    args = parser.parse_args()

    server = ILCServer(authority=URI.parse(args.server)) if args.server else ILCServer()
    client = ILCClient()
    wasm_path = Path(args.wasm_path)

    if args.dry_run:
        payload = {
            "server_link": str(server.link()),
            "server_route_root": server.route_root,
            "client_id": client.id().path,
            "client_route_root": client.route_root,
            "wasm_path": str(wasm_path),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("ILC Example (configuration only)")
            print(f"  Server: {payload['server_link']}")
            print(f"  Server route root: {payload['server_route_root']}")
            print(f"  Client library id: {payload['client_id']}")
            print(f"  Client route root: {payload['client_route_root']}")
            print(f"  WASM path: {payload['wasm_path']}")
            print("  Set TC_* auth environment variables and run without --dry-run.")
        return 0

    runtime = _load_runtime_inputs(server)
    data_dir = Path(".ilc-local")
    data_dir.mkdir(parents=True, exist_ok=True)
    kernel = build_local_kernel(
        client,
        data_dir=data_dir,
        token_host=runtime.token_host,
        actor_id=runtime.actor_id,
        public_key_b64=runtime.public_key_b64,
    )
    install = wasm_install(
        client,
        bearer_token=runtime.install_bearer_token,
        wasm_path=wasm_path,
        expected_sha256=runtime.wasm_sha256,
        kernel=kernel,
    )
    if getattr(install, "status", None) != 204:
        raise RuntimeError(
            "WASM install failed. "
            f"status={getattr(install, 'status', None)} "
            f"Check token claims for {client.route_root} and token-host alignment."
        )

    with tc.backend(kernel, bearer_token=runtime.bearer_token):
        abc = evaluate_abc(
            client=client,
            a=args.a,
            b=args.b,
            c=args.c,
        )

    payload = {
        "server_link": str(server.link()),
        "result": {
            "recovered": abc.recovered,
            "expected": abc.expected,
            "ok": abc.ok,
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("ILC Example (a + b - c)")
        print(f"  Inputs: a={abc.a}, b={abc.b}, c={abc.c}")
        print(f"  Result: recovered={abc.recovered}, expected={abc.expected}")
        print(f"  Status: {'OK' if abc.ok else 'MISMATCH'}")
        print("  Local WASM evaluation completed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
