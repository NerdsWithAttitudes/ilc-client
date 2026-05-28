from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import json
import tempfile

import tinychain as tc
from tinychain.uri import URI

from ilc import (
    DEFAULT_CLIENT_LIBRARY_ROOT,
    DEFAULT_CLIENT_WASM_PATH,
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    DEFAULT_SERVER_AUTHORITY,
    ENV_TC_TOKEN_HOST,
    ILCClient,
    ILCServer,
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
        client = ILCClient(authority=URI.parse("http://127.0.0.1:4100"))
        server = ILCServer(authority=URI.parse("https://example.test"))

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

    def test_wasm_install_rejects_hash_mismatch(self) -> None:
        client = ILCClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            wasm_path = Path(temp_dir) / "cipher_wasm.wasm"
            wasm_path.write_bytes(b"test-bytes")
            with self.assertRaises(ValueError):
                wasm_install(
                    client,
                    bearer_token="stub-token",
                    wasm_path=wasm_path,
                    expected_sha256="0" * 64,
                )

    def test_chart_v2_example_dry_run(self) -> None:
        out = subprocess.check_output(
            [sys.executable, "examples/chart_v2.py", "--json"],
            text=True,
        )
        payload = json.loads(out)
        self.assertEqual(
            payload["setup"]["path"],
            f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/setup",
        )
        self.assertEqual(
            payload["add"]["path"],
            f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/add",
        )
        self.assertEqual(
            payload["approx_plan_mul"]["path"],
            f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/approx/plan_mul",
        )
        self.assertEqual(
            payload["approx_gemm"]["path"],
            f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/approx/gemm",
        )

    def test_server_routes_are_indcpa_chart_routes(self) -> None:
        server = ILCServer()
        public_context = {"context_id": [1] * 16}
        handle = {"context_id": [1] * 16, "handle": [2] * 32}
        ciphertext = {"context_id": [1] * 16, "limbs": [[0, 1]]}
        approx_input = {
            "ciphertext": {
                "ciphertext": ciphertext,
                "shape": [1, 2],
                "packed_len": 2,
                "scale_bits": 20,
            },
            "handle": handle,
        }

        setup = server.setup(
            params={"moduli": [65521, 65537], "params_id": [9] * 16},
            payload_dims=2,
            representative_dims=4,
            metric_policy="public-default",
        )
        encrypt = server.encrypt(public_context=public_context, payload=[1, 2])
        decrypt = server.decrypt(
            public_context=public_context,
            ciphertext=ciphertext,
            handle=handle,
        )
        record = server.record_eval(
            public_context=public_context,
            op="add",
            input_handles=[handle, handle],
        )
        exact_plan = server.exact_plan_mul(
            public_context=public_context,
            lhs={"ciphertext": ciphertext, "handle": handle},
            rhs={"ciphertext": ciphertext, "handle": handle},
        )
        mul = server.approx_plan_mul(
            public_context=public_context,
            lhs=approx_input,
            rhs=approx_input,
            lhs_abs_bound=4.0,
            rhs_abs_bound=8.0,
            lhs_abs_error=0.000001,
            rhs_abs_error=0.000001,
            validity_budget=10,
        )
        gemm = server.approx_plan_gemm(
            public_context=public_context,
            lhs=approx_input,
            rhs=approx_input,
            lhs_abs_bound=4.0,
            rhs_abs_bound=8.0,
            lhs_abs_error=0.000001,
            rhs_abs_error=0.000001,
            validity_budget=10,
        )

        self.assertEqual(setup.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/setup")
        self.assertEqual(setup.body["admitted_ops"], ["add"])
        self.assertEqual(encrypt.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/encrypt")
        self.assertEqual(decrypt.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/decrypt")
        self.assertEqual(record.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/record_eval")
        self.assertEqual(exact_plan.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/exact/plan_mul")
        self.assertEqual(mul.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/approx/plan_mul")
        self.assertEqual(gemm.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/approx/plan_gemm")

    def test_client_add_route_is_chart_local_only(self) -> None:
        client = ILCClient()
        public_context = {"context_id": [1] * 16, "moduli": [65521, 65537]}
        lhs = {"context_id": [1] * 16, "limbs": [[1, 2], [3, 4]]}
        rhs = {"context_id": [1] * 16, "limbs": [[5, 6], [7, 8]]}

        with tc.backend(auto_execute=False):
            op = client.add(
                public_context=public_context,
                lhs_ciphertext=lhs,
                rhs_ciphertext=rhs,
            )

        self.assertEqual(op.method, "POST")
        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/add")
        self.assertIn("public_context", op.body)
        self.assertIn("lhs_ciphertext", op.body)
        self.assertIn("rhs_ciphertext", op.body)
        self.assertNotIn("handle", op.body)

    def test_no_handle_classes_exported(self) -> None:
        import ilc

        self.assertFalse(hasattr(ilc, "SecretCryptoHandle"))
        self.assertFalse(hasattr(ilc, "PublicEvalHandle"))

    def test_retired_public_helpers_are_removed(self) -> None:
        import ilc

        self.assertFalse(hasattr(ilc, "CipherContext"))
        self.assertFalse(hasattr(ilc, "evaluate_abc"))
        client = ILCClient()
        self.assertFalse(hasattr(client, "mul"))
        self.assertFalse(hasattr(client, "gemm"))
        self.assertFalse(hasattr(client, "chart_add"))

    def test_no_authcontext_export(self) -> None:
        import ilc
        self.assertFalse(hasattr(ilc, "AuthContext"))

    def test_no_bind_auth_api(self) -> None:
        self.assertFalse(hasattr(ILCClient, "bind_auth"))

    def test_no_raw_http_transport_shim(self) -> None:
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
