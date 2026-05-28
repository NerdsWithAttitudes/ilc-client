#!/usr/bin/env python3
"""Build the public v2 chart-representative route sequence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

import tinychain as tc
from tinychain.uri import URI

from ilc import (
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_SERVER_LIBRARY_ROOT,
    ENV_ILC_CLIENT_WASM_SHA256,
    ENV_TC_ACTOR_ID,
    ENV_TC_BEARER_TOKEN,
    ENV_TC_INSTALL_BEARER_TOKEN,
    ENV_TC_PUBLIC_KEY_B64,
    ENV_TC_TOKEN_HOST,
    ILCClient,
    ILCServer,
    build_local_kernel,
    wasm_install,
)


def _sample_public_context() -> dict[str, object]:
    return {
        "version": 1,
        "context_id": [1] * 16,
        "key_id": [2] * 16,
        "params_id": [3] * 16,
        "moduli": [65521, 65537],
        "payload_dims": 2,
        "representative_dims": 4,
        "chart_id": [4] * 16,
        "metric_view": {
            "metric_commitment": [5] * 32,
            "chart_id": [4] * 16,
            "dimension": 4,
            "distortion_bound_ppm": 10_000,
            "leakage": {
                "reveals_plaintext_metric": False,
                "reveals_secret_projection": False,
                "reveals_mask_state": False,
                "reveals_shape": True,
                "reveals_distortion_bound": True,
            },
            "admitted_ops": ["add"],
        },
        "admitted_ops": ["add"],
    }


def _sample_ciphertext() -> dict[str, object]:
    return {
        "limbs": [[10, 20, 30, 40], [11, 21, 31, 41]],
        "context_id": [1] * 16,
        "key_id": [2] * 16,
        "params_id": [3] * 16,
        "chart_id": [4] * 16,
        "shape": [2],
        "budget_log2": 20,
        "max_budget_log2": None,
    }


def _sample_handle() -> dict[str, object]:
    return {"context_id": [1] * 16, "handle": [9] * 32}


def _decode_state(value):
    if isinstance(value, list):
        return [_decode_state(item) for item in value]
    if isinstance(value, dict):
        if len(value) == 1:
            key, inner = next(iter(value.items()))
            if key.startswith("/state/scalar/value/"):
                return _decode_state(inner)
            if key == "/state/scalar/map" and isinstance(inner, dict):
                return {k: _decode_state(v) for k, v in inner.items()}
        return {k: _decode_state(v) for k, v in value.items()}
    return value


def _unwrap_response(payload: dict) -> dict:
    body = payload.get("body", payload)
    if isinstance(body, dict) and len(body) == 1:
        only = next(iter(body.values()))
        if isinstance(only, dict):
            return only
    if isinstance(body, dict):
        return body
    raise RuntimeError(f"unexpected response body shape: {payload!r}")


def _post(server: ILCServer, path: str, body: dict[str, object], bearer_token: str) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        f"{str(server.authority).rstrip('/')}{server.route_root}{path}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            decoded = _decode_state(json.loads(raw) if raw else {})
            if not isinstance(decoded, dict):
                raise RuntimeError(f"unexpected response shape: {decoded!r}")
            return _unwrap_response(decoded)
    except urlerror.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} failed: HTTP {err.code}: {detail}") from err


def _run_live(args: argparse.Namespace) -> dict[str, object]:
    bearer_token = os.environ.get(ENV_TC_BEARER_TOKEN)
    install_bearer_token = os.environ.get(ENV_TC_INSTALL_BEARER_TOKEN, bearer_token)
    public_key_b64 = os.environ.get(ENV_TC_PUBLIC_KEY_B64)
    token_host = os.environ.get(ENV_TC_TOKEN_HOST, DEFAULT_SERVER_LIBRARY_ROOT)
    actor_id = os.environ.get(ENV_TC_ACTOR_ID)
    wasm_sha256 = os.environ.get(ENV_ILC_CLIENT_WASM_SHA256)
    if not bearer_token or not install_bearer_token or not public_key_b64:
        raise RuntimeError(
            f"set {ENV_TC_BEARER_TOKEN}, {ENV_TC_INSTALL_BEARER_TOKEN}, and {ENV_TC_PUBLIC_KEY_B64}"
        )

    server_authority = args.server
    if server_authority and "://" not in server_authority:
        server_authority = f"http://{server_authority}"
    server = ILCServer(authority=URI.parse(server_authority)) if server_authority else ILCServer()
    client = ILCClient()
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    kernel = build_local_kernel(
        client,
        data_dir=data_dir,
        token_host=token_host,
        actor_id=actor_id,
        public_key_b64=public_key_b64,
    )
    install = wasm_install(
        client,
        bearer_token=install_bearer_token,
        wasm_path=Path(args.wasm_path),
        expected_sha256=wasm_sha256,
        kernel=kernel,
    )
    if getattr(install, "status", None) != 204:
        raise RuntimeError(f"WASM install failed: status={getattr(install, 'status', None)}")

    setup = _post(
        server,
        "/chart/setup",
        {
            "params": {"moduli": [65521, 65537, 65543], "params_id": [8] * 16},
            "payload_dims": 4,
            "representative_dims": 6,
            "metric_policy": "public-live-v2",
            "admitted_ops": ["add"],
        },
        bearer_token,
    )
    public_context = setup["public_context"]
    leakage = public_context.get("metric_view", {}).get("leakage", {})
    if isinstance(leakage, dict):
        for key, value in list(leakage.items()):
            if isinstance(value, int):
                leakage[key] = bool(value)
    lhs = _post(server, "/chart/encrypt", {"public_context": public_context, "payload": [3, 4, 0, 0]}, bearer_token)
    rhs = _post(server, "/chart/encrypt", {"public_context": public_context, "payload": [5, 6, 0, 0]}, bearer_token)

    with tc.backend(kernel, bearer_token=bearer_token):
        add = tc.execute(
            client.add(
                public_context=public_context,
                lhs_ciphertext=lhs["ciphertext"],
                rhs_ciphertext=rhs["ciphertext"],
            )
        )
    add = _unwrap_response(_decode_state(add) if isinstance(add, dict) else add)
    if "ciphertext" not in add:
        raise RuntimeError(f"unexpected chart_add response: {add!r}")
    sum_ciphertext = add["ciphertext"]
    sum_handle = _post(
        server,
        "/chart/record_eval",
        {
            "public_context": public_context,
            "op": "add",
            "input_handles": [lhs["handle"], rhs["handle"]],
        },
        bearer_token,
    )["handle"]
    decrypted_sum = _post(
        server,
        "/chart/decrypt",
        {
            "public_context": public_context,
            "ciphertext": sum_ciphertext,
            "handle": sum_handle,
        },
        bearer_token,
    )["payload"]

    def approx_input(encrypted: dict, shape: list[int]) -> dict[str, object]:
        return {
            "ciphertext": {
                "ciphertext": encrypted["ciphertext"],
                "shape": shape,
                "packed_len": 4,
                "scale_bits": 20,
            },
            "handle": encrypted["handle"],
        }

    approx_lhs = _post(server, "/chart/encrypt", {"public_context": public_context, "payload": [1 << 20, 2 << 20, 3 << 20, 4 << 20]}, bearer_token)
    approx_rhs = _post(server, "/chart/encrypt", {"public_context": public_context, "payload": [5 << 20, 6 << 20, 7 << 20, 8 << 20]}, bearer_token)
    mul_plan = _post(
        server,
        "/chart/approx/plan_mul",
        {
            "public_context": public_context,
            "lhs": approx_input(approx_lhs, [2, 2]),
            "rhs": approx_input(approx_rhs, [2, 2]),
            "lhs_abs_bound": 4.0,
            "rhs_abs_bound": 8.0,
            "lhs_abs_error": 0.000001,
            "rhs_abs_error": 0.000001,
            "validity_budget": 10,
        },
        bearer_token,
    )
    gemm_plan = _post(
        server,
        "/chart/approx/plan_gemm",
        {
            "public_context": public_context,
            "lhs": approx_input(approx_lhs, [2, 2]),
            "rhs": approx_input(approx_rhs, [2, 2]),
            "lhs_abs_bound": 4.0,
            "rhs_abs_bound": 8.0,
            "lhs_abs_error": 0.000001,
            "rhs_abs_error": 0.000001,
            "validity_budget": 10,
        },
        bearer_token,
    )

    return {
        "ok": decrypted_sum[:2] == [8, 10],
        "decrypted_sum": decrypted_sum,
        "mul_shape": mul_plan["witness"]["shape"],
        "gemm_shape": gemm_plan["witness"]["shape"],
        "routes": {
            "add": client.route_root + "/chart/add",
            "approx_plan_mul": server.route_root + "/chart/approx/plan_mul",
            "approx_plan_gemm": server.route_root + "/chart/approx/plan_gemm",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Run against a live server and local WASM")
    parser.add_argument("--server", default=None, help="Override ILC server authority")
    parser.add_argument("--wasm-path", default=str(DEFAULT_CLIENT_WASM_PATH), help="Path to cipher_wasm.wasm")
    parser.add_argument("--data-dir", default=".ilc-chart-v2", help="TinyChain local kernel data directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    if args.execute:
        payload = _run_live(args)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("chart_v2 live:", "OK" if payload["ok"] else "FAILED")
        return 0 if payload["ok"] else 1

    server = ILCServer()
    client = ILCClient()
    public_context = _sample_public_context()
    lhs = _sample_ciphertext()
    rhs = _sample_ciphertext()
    handle = _sample_handle()
    approx_input = {
        "ciphertext": {
            "ciphertext": lhs,
            "shape": [1, 2],
            "packed_len": 2,
            "scale_bits": 20,
        },
        "handle": handle,
    }

    with tc.backend(auto_execute=False):
        ops = {
            "setup": server.setup(
                params={"moduli": [65521, 65537], "params_id": [3] * 16},
                payload_dims=2,
                representative_dims=4,
                metric_policy="public-default",
            ),
            "encrypt": server.encrypt(
                public_context=public_context,
                payload=[7, 5],
            ),
            "add": client.add(
                public_context=public_context,
                lhs_ciphertext=lhs,
                rhs_ciphertext=rhs,
            ),
            "record_eval": server.record_eval(
                public_context=public_context,
                op="add",
                input_handles=[handle, handle],
            ),
            "exact_plan_mul": server.exact_plan_mul(
                public_context=public_context,
                lhs={"ciphertext": lhs, "handle": handle},
                rhs={"ciphertext": rhs, "handle": handle},
            ),
            "exact_mul": client.exact_mul(
                public_context=public_context,
                lhs_ciphertext=lhs,
                rhs_ciphertext=rhs,
                witness=lhs,
            ),
            "approx_plan_mul": server.approx_plan_mul(
                public_context=public_context,
                lhs=approx_input,
                rhs=approx_input,
                lhs_abs_bound=4.0,
                rhs_abs_bound=8.0,
                lhs_abs_error=0.000001,
                rhs_abs_error=0.000001,
                validity_budget=10,
            ),
            "approx_mul": client.approx_mul(
                public_context=public_context,
                lhs_approx=approx_input["ciphertext"],
                rhs_approx=approx_input["ciphertext"],
                witness_approx=approx_input["ciphertext"],
            ),
            "approx_plan_gemm": server.approx_plan_gemm(
                public_context=public_context,
                lhs=approx_input,
                rhs=approx_input,
                lhs_abs_bound=4.0,
                rhs_abs_bound=8.0,
                lhs_abs_error=0.000001,
                rhs_abs_error=0.000001,
                validity_budget=10,
            ),
            "approx_gemm": client.approx_gemm(
                public_context=public_context,
                lhs_approx=approx_input["ciphertext"],
                rhs_approx=approx_input["ciphertext"],
                witness_approx=approx_input["ciphertext"],
            ),
        }

    payload = {
        name: {
            "path": op.path,
            "body_keys": sorted(op.body.keys()),
        }
        for name, op in ops.items()
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for name, item in payload.items():
            print(f"{name}: {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
