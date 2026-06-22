from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import json
import tempfile
from unittest.mock import patch

import tinychain as tc
from tinychain.uri import URI

from ilc import (
    AbcEvaluation,
    CipherContext,
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
            [],
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
            f"http://127.0.0.1:4100{DEFAULT_CLIENT_LIBRARY_ROOT}",
        )
        self.assertEqual(
            str(server.link()),
            f"https://example.test{DEFAULT_SERVER_LIBRARY_ROOT}",
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
        op = client.add(metric=[3, 5], lhs=[10.0, 0.0], rhs=[-3.0, 0.0])
        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/add")
        self.assertEqual(op.body["rhs"], [-3.0, 0.0])
        self.assertNotIn("context", op.body)

    def test_deferred_gemm_route_shape_and_params(self) -> None:
        client = ILCClient()
        op = client.gemm(
            metric=[3, 5],
            lhs=[1.0, 2.0, 3.0, 4.0],
            rhs=[5.0, 6.0, 7.0, 8.0],
            lhs_rows=2,
            lhs_cols=2,
            rhs_cols=2,
        )
        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/exact/gemm")
        self.assertEqual(op.body["lhs_rows"], 2)
        self.assertEqual(op.body["lhs_cols"], 2)
        self.assertEqual(op.body["rhs_cols"], 2)
        self.assertNotIn("context", op.body)

    def test_server_encrypt_includes_explicit_context(self) -> None:
        server = ILCServer()
        context: CipherContext = {
            "version": 1,
            "alg": "HS256",
            "kid": None,
            "payload_b64": "payload",
            "signature_b64": "signature",
        }
        op = server.encrypt(
            context=context,
            payload=[1, 2, 3],
            budget_log2=20,
        )
        self.assertEqual(op.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/encrypt")
        self.assertEqual(op.body["context"]["alg"], "HS256")
        self.assertEqual(op.body["payload"], [1, 2, 3])

    def test_secret_routes_require_context_while_eval_routes_do_not(self) -> None:
        server = ILCServer()
        client = ILCClient()
        context: CipherContext = {
            "version": 1,
            "alg": "HS256",
            "kid": "review",
            "payload_b64": "payload",
            "signature_b64": "signature",
        }

        encrypt_op = server.encrypt(context=context, payload=[7, 0], budget_log2=20)
        self.assertIn("context", encrypt_op.body)
        self.assertEqual(encrypt_op.body["context"]["kid"], "review")

        eval_op = client.add(metric=[3, 5], lhs=[1.0, 0.0], rhs=[2.0, 0.0])
        self.assertNotIn("context", eval_op.body)

    def test_setup_response_context_can_be_passed_directly_to_encrypt(self) -> None:
        server = ILCServer()
        setup_response = {
            "public": {"cipher_metric": [1, 2]},
            "context": {
                "version": 1,
                "alg": "HS256",
                "kid": None,
                "payload_b64": "payload",
                "signature_b64": "signature",
            },
        }
        context: CipherContext = setup_response["context"]
        op = server.encrypt(context=context, payload=[9, 0], budget_log2=20)
        self.assertEqual(setup_response["public"]["cipher_metric"], [1, 2])
        self.assertEqual(op.body["context"]["alg"], "HS256")

    def test_no_handle_classes_exported(self) -> None:
        import ilc

        self.assertFalse(hasattr(ilc, "SecretCryptoHandle"))
        self.assertFalse(hasattr(ilc, "PublicEvalHandle"))

    def test_evaluate_abc_returns_expected_result(self) -> None:
        client = ILCClient()
        with patch.object(
            ILCClient,
            "add",
            side_effect=[
                tc.opref.get("/test/add-ab"),
                tc.opref.get("/test/add-neg-c"),
            ],
        ), patch.object(
            tc,
            "execute",
            side_effect=[
                {"ciphertext": {"limbs": [[12.0, 0.0]], "shape": [2]}},
                {"ciphertext": {"limbs": [[9.0, 0.0]], "shape": [2]}},
            ],
        ) as execute_mock:
            result = evaluate_abc(client=client, a=7, b=5, c=3)

        self.assertEqual(execute_mock.call_count, 2)
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
