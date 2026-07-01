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

import ilc.runtime as ilc_runtime
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

    def test_wasm_install_normalizes_authorization_header_token(self) -> None:
        client = ILCClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            wasm_path = Path(temp_dir) / "cipher_wasm.wasm"
            wasm_path.write_bytes(b"\0asm")

            class Install:
                status = 204

            with patch("ilc.runtime.tc.install", return_value=Install()) as install:
                result = wasm_install(
                    client,
                    bearer_token="  Bearer signed.jwt.token  ",
                    wasm_path=wasm_path,
                    token_host=DEFAULT_CLIENT_LIBRARY_ROOT,
                    actor_id="ci-test",
                    public_key_b64="falcon-public-key",
                )

        self.assertEqual(result.status, 204)
        token = install.call_args.kwargs["token"]
        self.assertEqual(token.bearer_token, "signed.jwt.token")
        self.assertEqual(token.host, DEFAULT_CLIENT_LIBRARY_ROOT)
        self.assertEqual(token.actor_id, "ci-test")
        self.assertEqual(token.public_key_b64, "falcon-public-key")
        self.assertEqual(token.alg, "falcon512")

    def test_wasm_install_explains_invalid_bearer_token(self) -> None:
        client = ILCClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            wasm_path = Path(temp_dir) / "cipher_wasm.wasm"
            wasm_path.write_bytes(b"\0asm")

            with patch(
                "ilc.runtime.tc.install",
                side_effect=ValueError("invalid bearer token"),
            ):
                with self.assertRaisesRegex(RuntimeError, "TC_INSTALL_BEARER_TOKEN"):
                    wasm_install(
                        client,
                        bearer_token="bad-token",
                        wasm_path=wasm_path,
                    )

    def test_local_kernel_dependency_recovery_preserves_token(self) -> None:
        client = ILCClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(ilc_runtime.tc, "KernelHandle", object, create=True),
                patch(
                    "ilc.runtime.tc.kernel.with_library",
                    side_effect=ValueError("invalid dependency route authority"),
                ),
                patch(
                    "tinychain._local.kernel_with_library_definition",
                    return_value="kernel",
                ) as recovery,
            ):
                kernel = ilc_runtime.build_local_kernel(
                    client,
                    data_dir=Path(temp_dir),
                    token_host=DEFAULT_SERVER_LIBRARY_ROOT,
                    actor_id="ci-test",
                    public_key_b64="cHVi",
                    server_authority=DEFAULT_SERVER_AUTHORITY,
                )

        self.assertEqual(kernel, "kernel")
        self.assertIsNotNone(recovery.call_args.kwargs["token"])

    def test_local_kernel_uses_falcon512_token_verifier(self) -> None:
        client = ILCClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(ilc_runtime.tc, "KernelHandle", object, create=True),
                patch(
                    "ilc.runtime.tc.kernel.with_library",
                    return_value="kernel",
                ) as with_library,
            ):
                kernel = ilc_runtime.build_local_kernel(
                    client,
                    data_dir=Path(temp_dir),
                    token_host=DEFAULT_SERVER_LIBRARY_ROOT,
                    actor_id="ci-test",
                    public_key_b64="falcon-public-key",
                )

        self.assertEqual(kernel, "kernel")
        self.assertEqual(with_library.call_args.kwargs["token"].alg, "falcon512")

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

    def test_bootstrap_installs_tinychain_rjwt_py(self) -> None:
        script = (self._repo_root() / "scripts" / "bootstrap_and_test.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("rjwt-py @ git+https://github.com/TinyChain-Inc/rjwt.git", script)

    def test_ci_mints_bearer_tokens_at_runtime(self) -> None:
        root = self._repo_root()
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        preflight = (root / ".github" / "workflows" / "preflight.yml").read_text(encoding="utf-8")
        mint_script = (root / "scripts" / "mint_ci_tokens.py").read_text(encoding="utf-8")
        setup_script = (root / "scripts" / "configure_github_live_smoke.sh").read_text(
            encoding="utf-8"
        )

        combined_workflows = workflow + "\n" + preflight
        self.assertIn("Mint live smoke bearer tokens", workflow)
        self.assertIn("Mint preflight bearer tokens", preflight)
        self.assertIn("TC_FALCON512_SECRET_KEY_B64", combined_workflows)
        self.assertNotIn("secrets.TC_BEARER_TOKEN", combined_workflows)
        self.assertNotIn("secrets.TC_INSTALL_BEARER_TOKEN", combined_workflows)
        self.assertIn("consume_and_sign", mint_script)
        self.assertIn("TC_FALCON512_SECRET_KEY_B64", setup_script)

    def test_generate_keypair_requires_falcon512_rjwt_binding(self) -> None:
        script = (self._repo_root() / "scripts" / "generate_keypair.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('getattr(rjwt.Actor, "new_falcon512")', script)
        self.assertIn("rjwt-py @ git+https://github.com/TinyChain-Inc/rjwt.git", script)

    def test_live_preflight_rejects_common_auth_misconfiguration(self) -> None:
        script = (self._repo_root() / "scripts" / "ci_preflight.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("raw RJWT token", script)
        self.assertIn("TC_ACTOR_ID must not contain '/'", script)
        self.assertIn("expected Falcon-512", script)
        self.assertIn("elif isinstance(custom, dict)", script)

    def test_deferred_add_uses_representative_ciphertext_contract(self) -> None:
        client = ILCClient()
        public_context = {"context_id": [4] * 16, "payload_dims": 2}
        lhs = {"limbs": [[10, 0]], "shape": [2]}
        rhs = {"limbs": [[-3, 0]], "shape": [2]}

        op = client.add(
            public_context=public_context,
            lhs_ciphertext=lhs,
            rhs_ciphertext=rhs,
        )

        self.assertEqual(op.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/add")
        self.assertEqual(op.body["public_context"], public_context)
        self.assertEqual(op.body["rhs_ciphertext"], rhs)
        self.assertNotIn("context", op.body)

    def test_representative_mul_and_gemm_routes_use_ciphertext_contract(self) -> None:
        client = ILCClient()
        public_context = {"context_id": [4] * 16, "payload_dims": 2}
        lhs = {"limbs": [[1, 2]], "shape": [2]}
        rhs = {"limbs": [[3, 4]], "shape": [2]}
        witness = {"limbs": [[0, 0]], "shape": [2]}

        mul = client.mul(
            public_context=public_context,
            lhs_ciphertext=lhs,
            rhs_ciphertext=rhs,
            witness=witness,
        )
        gemm = client.gemm(
            public_context=public_context,
            lhs_ciphertext=lhs,
            rhs_ciphertext=rhs,
            witness=witness,
        )

        self.assertEqual(mul.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/exact/mul")
        self.assertEqual(gemm.path, f"{DEFAULT_CLIENT_LIBRARY_ROOT}/chart/exact/gemm")
        self.assertEqual(mul.body["public_context"], public_context)
        self.assertEqual(mul.body["lhs_ciphertext"], lhs)
        self.assertEqual(gemm.body["witness"], witness)

    def test_server_encrypt_includes_explicit_public_context(self) -> None:
        server = ILCServer()
        public_context = {"context_id": [1] * 16, "payload_dims": 3}
        op = server.encrypt(
            public_context=public_context,
            payload=[1, 2, 3],
            shape=[3, 1],
            budget_log2=20,
        )
        self.assertEqual(op.path, f"{DEFAULT_SERVER_LIBRARY_ROOT}/chart/encrypt")
        self.assertEqual(op.body["public_context"], public_context)
        self.assertEqual(op.body["payload"], [1, 2, 3])
        self.assertEqual(op.body["shape"], [3, 1])

    def test_secret_routes_require_public_context_while_eval_routes_do_not(self) -> None:
        server = ILCServer()
        client = ILCClient()
        public_context = {"context_id": [7] * 16, "payload_dims": 2}

        encrypt_op = server.encrypt(public_context=public_context, payload=[7, 0], budget_log2=20)
        self.assertIn("public_context", encrypt_op.body)
        self.assertEqual(encrypt_op.body["public_context"], public_context)

        eval_op = client.add(
            public_context=public_context,
            lhs_ciphertext={"limbs": [[1, 0]], "shape": [2]},
            rhs_ciphertext={"limbs": [[2, 0]], "shape": [2]},
        )
        self.assertNotIn("context", eval_op.body)

    def test_setup_response_context_can_be_passed_directly_to_encrypt(self) -> None:
        server = ILCServer()
        setup_response = {
            "body": {"RepresentativeSetup": {"public_context": {"context_id": [1] * 16}}},
        }
        public_context = setup_response["body"]["RepresentativeSetup"]["public_context"]
        op = server.encrypt(public_context=public_context, payload=[9, 0], budget_log2=20)
        self.assertEqual(op.body["public_context"], public_context)

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

    def test_no_package_local_http_transport_shim(self) -> None:
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
