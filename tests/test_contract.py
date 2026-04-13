from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import json
from unittest.mock import patch

from ilc import (
    AbcEvaluation,
    AuthContext,
    DEFAULT_CLIENT_LIBRARY_ROOT,
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    DEFAULT_SERVER_AUTHORITY,
    ENV_TC_TOKEN_HOST,
    ILCClient,
    ILCServer,
    evaluate_abc,
    public_key_hex_from_b64,
    token_validity_window,
)


class ContractTests(unittest.TestCase):
    def test_default_library_contracts(self) -> None:
        client = ILCClient()
        server = ILCServer()

        self.assertEqual(client.id().path, DEFAULT_CLIENT_LIBRARY_ROOT)
        self.assertEqual(
            [dep.path for dep in client.dependencies],
            [DEFAULT_SERVER_LIBRARY_ROOT],
        )
        self.assertEqual(
            str(client.link()),
            f"{DEFAULT_LOCAL_AUTHORITY}{DEFAULT_CLIENT_LIBRARY_ROOT}",
        )
        self.assertEqual(
            str(server.link()),
            f"{DEFAULT_SERVER_AUTHORITY}{DEFAULT_SERVER_LIBRARY_ROOT}",
        )

    def test_authority_override(self) -> None:
        client = ILCClient.with_authority("http://127.0.0.1:4100")
        server = ILCServer.with_authority("https://example.test")

        self.assertEqual(
            str(client.link()),
            "http://127.0.0.1:4100/lib/applied-physics/ilc-client/0.1.0",
        )
        self.assertEqual(
            str(server.link()),
            "https://example.test/lib/applied-physics/ilc/0.1.0",
        )

    def test_wasm_install_requires_binary_path(self) -> None:
        client = ILCClient()

        with self.assertRaises(FileNotFoundError):
            client.wasm_install(
                bearer_token="stub-token",
                wasm_path=Path("artifacts/does-not-exist.wasm"),
            )

    def test_example_dry_run(self) -> None:
        out = subprocess.check_output(
            [sys.executable, "examples/abc.py", "--dry-run", "--json"],
            text=True,
        )
        payload = json.loads(out)
        self.assertEqual(
            payload["client_id"],
            DEFAULT_CLIENT_LIBRARY_ROOT,
        )
        self.assertEqual(
            payload["server_route_root"],
            DEFAULT_SERVER_LIBRARY_ROOT,
        )
        self.assertEqual(
            payload["server_link"],
            f"{DEFAULT_SERVER_AUTHORITY}{DEFAULT_SERVER_LIBRARY_ROOT}",
        )
        self.assertEqual(payload["wasm_path"], str(DEFAULT_CLIENT_WASM_PATH))

    def test_public_key_hex_from_b64(self) -> None:
        key_b64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        key_hex = public_key_hex_from_b64(key_b64)
        self.assertEqual(len(key_hex), 64)

    def test_auth_context_from_public_key_b64(self) -> None:
        key_b64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        ctx = AuthContext.from_public_key_b64(
            auth_token="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJpYXQiOjEsImV4cCI6M30.sig",
            public_key_b64=key_b64,
            auth_host=DEFAULT_SERVER_LIBRARY_ROOT,
            infer_token_window=True,
        )
        kwargs = ctx.op_kwargs()
        self.assertEqual(kwargs["auth_host"], DEFAULT_SERVER_LIBRARY_ROOT)
        self.assertEqual(len(kwargs["auth_public_key_hex"]), 64)
        self.assertEqual(kwargs["txn_timestamp_min"], 1_000_000_000)
        self.assertEqual(kwargs["txn_timestamp_max"], 3_000_000_000)

    def test_token_validity_window(self) -> None:
        header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
        payload = "eyJpYXQiOjEsImV4cCI6M30"  # {"iat":1,"exp":3}
        token = f"{header}.{payload}.sig"
        self.assertEqual(token_validity_window(token), (1_000_000_000, 3_000_000_000))

    def test_sub_scalars_uses_add_route_with_negated_rhs(self) -> None:
        client = ILCClient()
        auth = AuthContext(
            auth_token="stub",
            auth_public_key_hex="0" * 64,
            auth_host=DEFAULT_SERVER_LIBRARY_ROOT,
        )
        op = client.sub_scalars(a=10.0, b=3.0, auth=auth)
        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/add")
        self.assertEqual(op.body["rhs"], [-3.0, 0.0])

    def test_evaluate_abc_returns_expected_result(self) -> None:
        client = ILCClient()
        auth = AuthContext(
            auth_token="stub",
            auth_public_key_hex="0" * 64,
            auth_host=DEFAULT_SERVER_LIBRARY_ROOT,
        )

        with patch("ilc.example_ops.tc.execute", side_effect=[{"result": [12.0, 0.0]}, {"result": [9.0, 0.0]}]):
            result = evaluate_abc(client=client, auth=auth, a=7, b=5, c=3)

        self.assertIsInstance(result, AbcEvaluation)
        self.assertEqual(result.recovered, 9)
        self.assertEqual(result.expected, 9)
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
