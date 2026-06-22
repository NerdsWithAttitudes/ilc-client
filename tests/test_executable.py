from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from ilc.executable import (
    DepthBudgetError,
    ENCRYPTED_GRAPH_TENSOR_NAMES,
    ExecutableEncryptionProvider,
    ExecutableGraphRuntime,
    MissingDependencyError,
    PlainProgram,
    PlainTensor,
    ProgramNode,
    ProgramOp,
    ShapeMismatchError,
    UnsupportedOperationError,
    compare_outputs,
    encode_program,
    validate_encrypted_graph_program,
)
from ilc.executable.benchmark import BenchmarkConfig, run_benchmark
from ilc.executable.metrics import SCHEMA_VERSION
from ilc.executable.providers.ilc import ILCConfig, ILCProvider
from ilc.executable.providers.plaintext import PlaintextProvider
from ilc.executable.workloads import WORKLOAD_REGISTRY, load_mnist_fixture


def _input(node_id: str, shape: tuple[int, ...]) -> ProgramNode:
    return ProgramNode(id=node_id, op=ProgramOp.INPUT, inputs=(), output_shape=shape)


def _op(node_id: str, op: ProgramOp, inputs: tuple[str, str], shape: tuple[int, ...]) -> ProgramNode:
    return ProgramNode(id=node_id, op=op, inputs=inputs, output_shape=shape)


def test_import_executable_does_not_import_openfhe() -> None:
    script = (
        "import sys, importlib; "
        "sys.modules.pop('openfhe', None); "
        "import ilc; import ilc.executable; "
        "assert 'openfhe' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_plain_tensor_validates_shape_size() -> None:
    assert PlainTensor(values=(1.0, 2.0), shape=(2,)).values == (1.0, 2.0)
    with pytest.raises(ShapeMismatchError):
        PlainTensor(values=(1.0,), shape=(2,))


def test_plaintext_provider_runtime_add_mul_gemm() -> None:
    program = PlainProgram(
        id="program",
        nodes=(
            _input("a", (2, 2)),
            _input("b", (2, 2)),
            _op("g", ProgramOp.GEMM, ("a", "b"), (2, 2)),
        ),
        input_ids=("a", "b"),
        output_ids=("g",),
    )
    provider = PlaintextProvider()
    inputs = {
        "a": provider.encrypt_tensor(PlainTensor((1, 2, 3, 4), (2, 2))),
        "b": provider.encrypt_tensor(PlainTensor((5, 6, 7, 8), (2, 2))),
    }
    artifact = ExecutableGraphRuntime().execute(provider, program, provider.encrypt_program(program), inputs)
    out = provider.decrypt_tensor(artifact.outputs["g"])
    assert out.values == pytest.approx((19, 22, 43, 50))


def test_plaintext_provider_satisfies_protocol() -> None:
    assert isinstance(PlaintextProvider(), ExecutableEncryptionProvider)


def test_runtime_requires_provider_execute_program() -> None:
    provider = PlaintextProvider()
    program = WORKLOAD_REGISTRY["add_chain"].program
    encrypted_program = provider.encrypt_program(program)
    inputs = {
        input_id: provider.encrypt_tensor(tensor)
        for input_id, tensor in WORKLOAD_REGISTRY["add_chain"].plain_inputs.items()
    }
    provider.execute_program = None  # type: ignore[method-assign]
    with pytest.raises(TypeError):
        ExecutableGraphRuntime().execute(provider, program, encrypted_program, inputs)


def test_program_encoding_contains_adjacency_opcode_and_selectors() -> None:
    program = PlainProgram(
        id="program",
        nodes=(
            _input("a", (2,)),
            _input("b", (2,)),
            _op("sum", ProgramOp.ADD, ("a", "b"), (2,)),
        ),
        input_ids=("a", "b"),
        output_ids=("sum",),
    )
    encoding = encode_program(program)

    assert encoding.version == "program_graph_tensor_encoding_v1"
    assert encoding.node_ids == ("a", "b", "sum")
    assert set(encoding.tensors) == set(ENCRYPTED_GRAPH_TENSOR_NAMES)
    assert encoding.tensors["opcode"].shape == (3, 4)
    assert encoding.tensors["adjacency"].shape == (3, 3)
    assert encoding.tensors["lhs_selector"].values == pytest.approx((0, 0, 0, 0, 0, 0, 1, 0, 0))
    assert encoding.tensors["rhs_selector"].values == pytest.approx((0, 0, 0, 0, 0, 0, 0, 1, 0))
    assert encoding.tensors["adjacency"].values == pytest.approx((0, 0, 1, 0, 0, 1, 0, 0, 0))
    assert encoding.tensors["output_selector"].values == pytest.approx((0, 0, 1))


def test_workload_registry_and_fixture() -> None:
    assert set(WORKLOAD_REGISTRY) == {
        "add_chain",
        "mul_chain",
        "gemm_chain_small",
        "mnist_linear_v1_b1",
        "mnist_linear_v1_b16",
    }
    fixture = load_mnist_fixture()
    assert len(fixture["images"]) == 16
    assert len(fixture["images"][0]) == 65
    assert len(fixture["weights"]) == 65
    assert len(fixture["weights"][0]) == 10


def test_run_benchmark_plaintext_schema() -> None:
    result = run_benchmark(
        BenchmarkConfig(("add_chain", "gemm_chain_small"), ("plaintext",), repeat=1),
        {"plaintext": PlaintextProvider()},
    )
    assert [item.schema_version for item in result] == [SCHEMA_VERSION, SCHEMA_VERSION]
    assert all(item.passed_validation for item in result)
    assert result[0].primitive_operation_count_estimate == {"ciphertext_add": 8, "ciphertext_mul": 0}


def test_output_validation_mismatches_return_failed_result() -> None:
    expected = {"out": PlainTensor((1.0, 2.0), (2,))}
    assert not compare_outputs(
        {"other": PlainTensor((1.0, 2.0), (2,))},
        expected,
        absolute_tolerance=0.0,
        relative_tolerance=0.0,
    ).passed
    assert not compare_outputs(
        {"out": PlainTensor((1.0, 2.0), (1, 2))},
        expected,
        absolute_tolerance=0.0,
        relative_tolerance=0.0,
    ).passed


def test_benchmark_cli_plaintext_json() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ilc.executable.benchmark",
            "--workload",
            "add_chain",
            "--provider",
            "plaintext",
            "--repeat",
            "1",
            "--output-format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["results"][0]["provider_id"] == "plaintext"


def test_executable_benchmark_smoke_defaults_to_ckks_mnist() -> None:
    script = Path("scripts/executable_benchmark_smoke.sh").read_text(encoding="utf-8")
    assert 'PROVIDER="${ILC_EXECUTABLE_PROVIDER:-ckks}"' in script
    assert 'WORKLOAD="${ILC_EXECUTABLE_WORKLOAD:-mnist_linear_v1_b1}"' in script


def test_generate_keypair_secures_secret_directory() -> None:
    script = Path("scripts/generate_keypair.sh").read_text(encoding="utf-8")
    assert 'chmod 700 "${OUT_DIR}"' in script


def test_ckks_module_import_is_lazy() -> None:
    script = (
        "import sys, importlib; "
        "sys.modules.pop('openfhe', None); "
        "importlib.import_module('ilc.executable.providers.ckks'); "
        "assert 'openfhe' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_ckks_provider_missing_dependency_or_depth_check() -> None:
    ckks = importlib.import_module("ilc.executable.providers.ckks")
    try:
        provider = ckks.CKKSProvider(ckks.CKKSConfig(multiplicative_depth=1))
    except MissingDependencyError:
        return
    program = WORKLOAD_REGISTRY["mul_chain"].program
    with pytest.raises(DepthBudgetError):
        provider.validate_program(program)


def test_ckks_encrypted_adjacency_is_load_bearing() -> None:
    ckks = importlib.import_module("ilc.executable.providers.ckks")
    try:
        provider = ckks.CKKSProvider(ckks.CKKSConfig(multiplicative_depth=7))
    except MissingDependencyError:
        return
    program = PlainProgram(
        id="adjacency_add",
        nodes=(
            _input("a", (2,)),
            _input("b", (2,)),
            _op("sum", ProgramOp.ADD, ("a", "b"), (2,)),
        ),
        input_ids=("a", "b"),
        output_ids=("sum",),
    )
    encrypted_program = provider.encrypt_program(program)
    encrypted_tensors = dict(encrypted_program.encrypted_tensors)
    encrypted_tensors["adjacency"] = provider.encrypt_tensor(
        PlainTensor((0.0,) * 9, (3, 3))
    )
    corrupted_program = ckks.EncryptedGraphProgram(
        provider_id=encrypted_program.provider_id,
        session_id=encrypted_program.session_id,
        program_id=encrypted_program.program_id,
        node_ids=encrypted_program.node_ids,
        input_ids=encrypted_program.input_ids,
        output_ids=encrypted_program.output_ids,
        node_shapes=encrypted_program.node_shapes,
        encrypted_tensors=encrypted_tensors,
    )
    inputs = {
        "a": provider.encrypt_tensor(PlainTensor((1.0, 2.0), (2,))),
        "b": provider.encrypt_tensor(PlainTensor((3.0, 4.0), (2,))),
    }
    artifact = ExecutableGraphRuntime().execute(provider, program, corrupted_program, inputs)
    actual = {"sum": provider.decrypt_tensor(artifact.outputs["sum"])}
    expected = {"sum": PlainTensor((4.0, 6.0), (2,))}
    result = compare_outputs(
        actual,
        expected,
        absolute_tolerance=provider.absolute_tolerance,
        relative_tolerance=provider.relative_tolerance,
    )
    assert not result.passed


def test_ckks_benchmark_cli_skips_without_openfhe() -> None:
    try:
        import openfhe  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ilc.executable.benchmark",
                "--workload",
                "add_chain",
                "--provider",
                "ckks",
                "--repeat",
                "1",
                "--output-format",
                "json",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(completed.stdout)
        assert payload["skipped"] is True
        assert payload["results"] == []


def test_ilc_provider_uses_public_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_execute(op: Any, **_: Any) -> Any:
        calls.append((op.method, op.path, dict(op.body)))
        if op.path.endswith("/chart/setup"):
            return {
                "context": {
                    "version": 1,
                    "alg": "HS256",
                    "kid": None,
                    "payload_b64": "payload",
                    "signature_b64": "signature",
                },
                "public": {"cipher_metric": [3, 5]},
            }
        if op.path.endswith("/chart/encrypt"):
            return {"limbs": [[1.0, 2.0]], "key_id": [0] * 16, "params_id": [9] * 16}
        if op.path.endswith("/chart/decrypt"):
            return {"values": [16, 32]}
        if op.path.endswith("/chart/add"):
            return {"result": [3.0, 4.0]}
        raise AssertionError(f"unexpected op {op.path}")

    monkeypatch.setattr("ilc.executable.providers.ilc.tc.execute", fake_execute)
    provider = ILCProvider(ILCConfig(scale_bits=4))
    lhs = provider.encrypt_tensor(PlainTensor((1.0, 2.0), (2,)))
    rhs = provider.encrypt_tensor(PlainTensor((1.0, 2.0), (2,)))
    provider.add(lhs, rhs)
    encrypted_program = provider.encrypt_program(WORKLOAD_REGISTRY["add_chain"].program)
    assert encrypted_program.representation_type == "ilc_encrypted_graph_tensor_encoding_v1"
    assert set(encrypted_program.encrypted_tensors) == set(ENCRYPTED_GRAPH_TENSOR_NAMES)
    validate_encrypted_graph_program(
        encrypted_program,
        provider_id="ilc",
        session_id=provider.session.session_id,
    )
    with pytest.raises(UnsupportedOperationError):
        provider.execute_program(
            encrypted_program,
            {
                input_id: provider.encrypt_tensor(tensor)
                for input_id, tensor in WORKLOAD_REGISTRY["add_chain"].plain_inputs.items()
            },
        )
    provider.decrypt_tensor(lhs)

    paths = [path for _, path, _ in calls]
    assert any(path.endswith("/chart/setup") for path in paths)
    assert any(path.endswith("/chart/encrypt") for path in paths)
    assert any(path.endswith("/chart/add") for path in paths)
    assert any(path.endswith("/chart/decrypt") for path in paths)


def test_ilc_provider_from_environment_installs_local_wasm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    wasm_path = tmp_path / "cipher_wasm.wasm"
    wasm_path.write_bytes(b"wasm")
    data_dir = tmp_path / "data"
    monkeypatch.setenv("TC_BEARER_TOKEN", "server-token")
    monkeypatch.setenv("TC_INSTALL_BEARER_TOKEN", "install-token")
    monkeypatch.setenv("TC_PUBLIC_KEY_B64", "public-key")
    monkeypatch.setenv("ILC_WASM_PATH", str(wasm_path))
    monkeypatch.setenv("ILC_EXECUTABLE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ILC_INTEGRATION_SERVER", "https://example.test")

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_build_local_kernel(schema_owner: Any, **kwargs: Any) -> object:
        calls.append(("build", {"schema_owner": schema_owner, **kwargs}))
        return object()

    def fake_wasm_install(schema_owner: Any, **kwargs: Any) -> object:
        calls.append(("install", {"schema_owner": schema_owner, **kwargs}))

        class Install:
            status = 204

        return Install()

    monkeypatch.setattr("ilc.executable.providers.ilc.build_local_kernel", fake_build_local_kernel)
    monkeypatch.setattr("ilc.executable.providers.ilc.wasm_install", fake_wasm_install)

    provider = ILCProvider.from_environment(ILCConfig())

    assert provider.provider_id == "ilc"
    assert [name for name, _ in calls] == ["build", "install"]
    assert calls[1][1]["bearer_token"] == "install-token"
    assert calls[1][1]["wasm_path"] == wasm_path


@pytest.mark.integration
@pytest.mark.ckks
def test_ckks_provider_optional_integration() -> None:
    pytest.importorskip("openfhe")
    ckks = importlib.import_module("ilc.executable.providers.ckks")
    provider = ckks.CKKSProvider(ckks.CKKSConfig())
    program = PlainProgram(
        id="ckks_gemm_smoke",
        nodes=(
            _input("a", (1, 2)),
            _input("b", (2, 1)),
            _op("out", ProgramOp.GEMM, ("a", "b"), (1, 1)),
        ),
        input_ids=("a", "b"),
        output_ids=("out",),
    )
    encrypted_program = provider.encrypt_program(program)
    assert encrypted_program.representation_type == "ckks_encrypted_graph_tensor_encoding_v1"
    assert set(encrypted_program.encrypted_tensors) == set(ENCRYPTED_GRAPH_TENSOR_NAMES)
    validate_encrypted_graph_program(
        encrypted_program,
        provider_id="ckks",
        session_id=provider.session.session_id,
    )
    encrypted_inputs = {
        "a": provider.encrypt_tensor(PlainTensor((2.0, 3.0), (1, 2))),
        "b": provider.encrypt_tensor(PlainTensor((5.0, 7.0), (2, 1))),
    }
    artifact = ExecutableGraphRuntime().execute(provider, program, encrypted_program, encrypted_inputs)
    output = provider.decrypt_tensor(artifact.outputs["out"])
    assert output.values == pytest.approx((31.0,), abs=provider.absolute_tolerance, rel=provider.relative_tolerance)


@pytest.mark.integration
@pytest.mark.ilc
def test_ilc_provider_live_integration_skips_without_credentials() -> None:
    if not os.environ.get("TC_BEARER_TOKEN"):
        pytest.skip("missing TC_BEARER_TOKEN for live ILC integration")
    provider = ILCProvider.from_environment(ILCConfig())
    provider.validate_program(WORKLOAD_REGISTRY["add_chain"].program)


def test_public_boundary_no_private_mirrors_or_wasm() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in (root / "src").rglob("*.py"))
    assert "from ilc_core" not in source_text
    assert "from ilc_server" not in source_text
    assert "from ilc_client" not in source_text
    assert "import ilc_core" not in source_text
    assert "import ilc_server" not in source_text
    assert "import ilc_client" not in source_text
    tracked = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
    assert not [path for path in tracked if path.endswith(".wasm")]
