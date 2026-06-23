"""Executable-encryption benchmark runner and CLI."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .errors import BenchmarkConfigurationError, MissingDependencyError
from .metrics import BenchmarkResult, SCHEMA_VERSION, write_csv, write_json, write_stdout
from .program import ProgramOp
from .protocol import ExecutableEncryptionProvider
from .providers.plaintext import PlaintextProvider
from .runtime import ExecutableGraphRuntime
from .tensors import PlainTensor
from .validation import compare_outputs
from .workloads import WORKLOAD_REGISTRY, WorkloadInstance

_OUTPUT_FORMATS = frozenset({"json", "csv", "stdout"})


@dataclass(frozen=True)
class BenchmarkConfig:
    workload_instance_ids: tuple[str, ...]
    provider_ids: tuple[str, ...]
    repeat: int = 1
    output_format: str = "json"
    output_path: str | None = None

    def __post_init__(self) -> None:
        workload_ids = tuple(self.workload_instance_ids)
        provider_ids = tuple(self.provider_ids)
        object.__setattr__(self, "workload_instance_ids", workload_ids)
        object.__setattr__(self, "provider_ids", provider_ids)
        if not workload_ids:
            raise BenchmarkConfigurationError("workload_instance_ids must be non-empty")
        if len(set(workload_ids)) != len(workload_ids):
            raise BenchmarkConfigurationError("workload_instance_ids must not contain duplicates")
        unknown = [value for value in workload_ids if value not in WORKLOAD_REGISTRY]
        if unknown:
            raise BenchmarkConfigurationError(f"unknown workloads: {unknown!r}")
        if not provider_ids:
            raise BenchmarkConfigurationError("provider_ids must be non-empty")
        if len(set(provider_ids)) != len(provider_ids):
            raise BenchmarkConfigurationError("provider_ids must not contain duplicates")
        if not isinstance(self.repeat, int) or isinstance(self.repeat, bool) or self.repeat <= 0:
            raise BenchmarkConfigurationError("repeat must be a positive integer")
        if self.output_format not in _OUTPUT_FORMATS:
            raise BenchmarkConfigurationError(f"invalid output_format {self.output_format!r}")
        if self.output_path is not None and not Path(self.output_path).expanduser().parent.is_dir():
            raise BenchmarkConfigurationError("output_path parent directory does not exist")


def run_benchmark(
    config: BenchmarkConfig,
    providers: Mapping[str, ExecutableEncryptionProvider],
    runtime: ExecutableGraphRuntime | None = None,
) -> list[BenchmarkResult]:
    missing = [provider_id for provider_id in config.provider_ids if provider_id not in providers]
    if missing:
        raise BenchmarkConfigurationError(f"missing providers: {missing!r}")
    graph_runtime = runtime or ExecutableGraphRuntime()
    results: list[BenchmarkResult] = []
    for workload_id in config.workload_instance_ids:
        workload = WORKLOAD_REGISTRY[workload_id]
        reference = _reference_outputs(workload, graph_runtime)
        for provider_id in config.provider_ids:
            provider = providers[provider_id]
            provider.validate_program(workload.program)
            timings = [_run_once(workload, provider, graph_runtime) for _ in range(config.repeat)]
            comparisons = [
                compare_outputs(
                    timing.outputs,
                    reference,
                    absolute_tolerance=provider.absolute_tolerance,
                    relative_tolerance=provider.relative_tolerance,
                )
                for timing in timings
            ]
            encryption_times = [timing.encryption_time_s for timing in timings]
            execution_times = [timing.execution_time_s for timing in timings]
            decryption_times = [timing.decryption_time_s for timing in timings]
            encryption_mean = statistics.fmean(encryption_times)
            execution_mean = statistics.fmean(execution_times)
            decryption_mean = statistics.fmean(decryption_times)
            results.append(
                BenchmarkResult(
                    workload_instance_id=workload.workload_instance_id,
                    workload_id=workload.workload_id,
                    provider_id=provider.provider_id,
                    session_id=provider.session.session_id,
                    config_fingerprint=provider.session.config_fingerprint,
                    representation_type=timings[-1].representation_type,
                    encryption_time_s=encryption_mean,
                    execution_time_s=execution_mean,
                    decryption_time_s=decryption_mean,
                    total_time_s=encryption_mean + execution_mean + decryption_mean,
                    encryption_time_std_s=_std(encryption_times),
                    execution_time_std_s=_std(execution_times),
                    decryption_time_std_s=_std(decryption_times),
                    passed_validation=all(comparison.passed for comparison in comparisons),
                    max_absolute_error=max(comparison.max_absolute_error for comparison in comparisons),
                    absolute_tolerance=provider.absolute_tolerance,
                    relative_tolerance=provider.relative_tolerance,
                    required_multiplicative_depth=workload.required_multiplicative_depth,
                    repeat=config.repeat,
                    logical_operation_count=sum(1 for node in workload.program.nodes if node.op != ProgramOp.INPUT),
                    output_shapes={key: value.shape for key, value in timings[-1].outputs.items()},
                    primitive_operation_count_estimate=_primitive_counts(workload),
                )
            )
    return results


@dataclass(frozen=True)
class _RunTiming:
    encryption_time_s: float
    execution_time_s: float
    decryption_time_s: float
    outputs: dict[str, PlainTensor]
    representation_type: str


def _run_once(
    workload: WorkloadInstance,
    provider: ExecutableEncryptionProvider,
    runtime: ExecutableGraphRuntime,
) -> _RunTiming:
    start = time.perf_counter()
    encrypted_inputs = {
        input_id: provider.encrypt_tensor(tensor)
        for input_id, tensor in workload.plain_inputs.items()
    }
    encrypted_program = provider.encrypt_program(workload.program, assume_validated=True)
    encryption_time = time.perf_counter() - start

    start = time.perf_counter()
    artifact = runtime.execute(
        provider,
        workload.program,
        encrypted_program,
        encrypted_inputs,
        validate_program=False,
    )
    execution_time = time.perf_counter() - start

    start = time.perf_counter()
    outputs = {output_id: provider.decrypt_tensor(tensor) for output_id, tensor in artifact.outputs.items()}
    decryption_time = time.perf_counter() - start
    return _RunTiming(encryption_time, execution_time, decryption_time, outputs, encrypted_program.representation_type)


def _reference_outputs(workload: WorkloadInstance, runtime: ExecutableGraphRuntime) -> dict[str, PlainTensor]:
    provider = PlaintextProvider()
    return _run_once(workload, provider, runtime).outputs


def _primitive_counts(workload: WorkloadInstance) -> dict[str, int]:
    counts = {"ciphertext_add": 0, "ciphertext_mul": 0}
    shapes: dict[str, tuple[int, ...]] = {}
    for node in workload.program.nodes:
        if node.op == ProgramOp.ADD:
            counts["ciphertext_add"] += 1
        elif node.op == ProgramOp.MUL:
            counts["ciphertext_mul"] += 1
        elif node.op == ProgramOp.GEMM:
            lhs = shapes[node.inputs[0]]
            rhs = shapes[node.inputs[1]]
            m, k = lhs
            _, n = rhs
            counts["ciphertext_mul"] += m * k * n
            counts["ciphertext_add"] += m * n * max(k - 1, 0)
        shapes[node.id] = node.output_shape
    return counts


def _std(values: list[float]) -> float | None:
    return None if len(values) == 1 else float(statistics.stdev(values))


def _provider_factories(provider_ids: Sequence[str]) -> dict[str, ExecutableEncryptionProvider]:
    providers: dict[str, ExecutableEncryptionProvider] = {}
    for provider_id in provider_ids:
        if provider_id == "plaintext":
            providers[provider_id] = PlaintextProvider()
        elif provider_id == "ckks":
            from .providers.ckks import CKKSConfig, CKKSProvider

            providers[provider_id] = CKKSProvider(CKKSConfig())
        elif provider_id == "ilc":
            from .providers.ilc import ILCConfig, ILCProvider

            providers[provider_id] = ILCProvider.from_environment(ILCConfig())
        else:
            raise BenchmarkConfigurationError(f"unknown provider {provider_id!r}")
    return providers


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run executable-encryption benchmark workloads")
    parser.add_argument("--workload", action="append", required=True, dest="workloads")
    parser.add_argument("--provider", action="append", required=True, dest="providers")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output-format", choices=sorted(_OUTPUT_FORMATS), default="json")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config = BenchmarkConfig(
        workload_instance_ids=tuple(_split_csv(args.workloads)),
        provider_ids=tuple(_split_csv(args.providers)),
        repeat=args.repeat,
        output_format=args.output_format,
        output_path=args.output_path,
    )
    if args.dry_run:
        message = (
            f"dry-run OK: workloads={list(config.workload_instance_ids)} "
            f"providers={list(config.provider_ids)} repeat={config.repeat}"
        )
        _write_output(message + "\n", config.output_path)
        return 0
    try:
        providers = _provider_factories(config.provider_ids)
    except MissingDependencyError as exc:
        _write_skip(config, str(exc))
        return 0
    results = run_benchmark(config, providers)
    destination = Path(config.output_path) if config.output_path else sys.stdout
    if config.output_format == "json":
        write_json(results, destination)
    elif config.output_format == "csv":
        write_csv(results, destination)
    else:
        write_stdout(results, destination)
    return 0


def _split_csv(values: Sequence[str]) -> list[str]:
    return [part.strip() for value in values for part in value.split(",") if part.strip()]


def _write_output(text: str, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _write_skip(config: BenchmarkConfig, reason: str) -> None:
    destination = Path(config.output_path) if config.output_path else sys.stdout
    if config.output_format == "json":
        _write_output(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "results": [],
                    "skipped": True,
                    "reason": reason,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            config.output_path,
        )
    elif config.output_format == "csv":
        _write_output(f"# skipped: {reason}\n", config.output_path)
    else:
        if hasattr(destination, "write"):
            destination.write(f"skipped: {reason}\n")
        else:
            destination.write_text(f"skipped: {reason}\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
