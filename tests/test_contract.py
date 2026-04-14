from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import json
from unittest.mock import patch

import tinychain as tc

from ilc import (
    AbcEvaluation,
    DEFAULT_CLIENT_LIBRARY_ROOT,
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    DEFAULT_SERVER_AUTHORITY,
    ENV_TC_TOKEN_HOST,
    ILCClient,
    ILCServer,
    evaluate_abc,
    wasm_install,
)


class ContractTests(unittest.TestCase):
    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[1]

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
            wasm_install(
                client,
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

    def test_deferred_add_accepts_negated_rhs_for_subtraction_flow(self) -> None:
        client = ILCClient()
        with tc.backend(auto_execute=False):
            op = client.add(metric=[3, 5], lhs=[10.0, 0.0], rhs=[-3.0, 0.0])
        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/add")
        self.assertEqual(op.body["rhs"], [-3.0, 0.0])

    def test_deferred_gemm_route_shape_and_params(self) -> None:
        client = ILCClient()
        with tc.backend(auto_execute=False):
            op = client.gemm(
                metric=[3, 5],
                lhs=[1.0, 2.0, 3.0, 4.0],
                rhs=[5.0, 6.0, 7.0, 8.0],
                lhs_rows=2,
                lhs_cols=2,
                rhs_cols=2,
            )
        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/gemm")
        self.assertEqual(op.body["lhs_rows"], 2)
        self.assertEqual(op.body["lhs_cols"], 2)
        self.assertEqual(op.body["rhs_cols"], 2)

    def test_evaluate_abc_returns_expected_result(self) -> None:
        client = ILCClient()
        with patch.object(
            ILCClient,
            "add",
            side_effect=[{"result": [12.0, 0.0]}, {"result": [9.0, 0.0]}],
        ):
            result = evaluate_abc(client=client, a=7, b=5, c=3)

        self.assertIsInstance(result, AbcEvaluation)
        self.assertEqual(result.recovered, 9)
        self.assertEqual(result.expected, 9)
        self.assertTrue(result.ok)

    def test_no_authcontext_export(self) -> None:
        import ilc
        self.assertFalse(hasattr(ilc, "AuthContext"))

    def test_no_bind_auth_api(self) -> None:
        self.assertFalse(hasattr(ILCClient, "bind_auth"))

    def test_no_legacy_http_transport_shim(self) -> None:
        root = self._repo_root()
        src_files = sorted((root / "src").rglob("*.py"))
        self.assertTrue(src_files, "expected Python source files under src/")

        combined = "\n".join(p.read_text(encoding="utf-8") for p in src_files)
        self.assertNotIn("post_json", combined)
        self.assertNotIn("urllib.request", combined)
        self.assertNotIn("urlopen(", combined)

    def test_no_framework_gap_todo_wording(self) -> None:
        root = self._repo_root()
        files = [*sorted((root / "src").rglob("*.py")), root / "README.md"]
        combined = "\n".join(p.read_text(encoding="utf-8") for p in files)
        self.assertNotIn("TODO(framework-gap)", combined)


if __name__ == "__main__":
    unittest.main()
