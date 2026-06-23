"""Benchmark result schema and report writers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, TextIO

SCHEMA_VERSION = "benchmark_result_v1"

CSV_COLUMNS = (
    "schema_version",
    "workload_instance_id",
    "workload_id",
    "provider_id",
    "session_id",
    "config_fingerprint",
    "representation_type",
    "encryption_time_s",
    "execution_time_s",
    "decryption_time_s",
    "total_time_s",
    "encryption_time_std_s",
    "execution_time_std_s",
    "decryption_time_std_s",
    "passed_validation",
    "max_absolute_error",
    "absolute_tolerance",
    "relative_tolerance",
    "required_multiplicative_depth",
    "repeat",
    "logical_operation_count",
    "output_shapes",
)


@dataclass(frozen=True)
class BenchmarkResult:
    workload_instance_id: str
    workload_id: str
    provider_id: str
    session_id: str
    config_fingerprint: str
    representation_type: str
    encryption_time_s: float
    execution_time_s: float
    decryption_time_s: float
    total_time_s: float
    encryption_time_std_s: float | None
    execution_time_std_s: float | None
    decryption_time_std_s: float | None
    passed_validation: bool
    max_absolute_error: float | None
    absolute_tolerance: float
    relative_tolerance: float
    required_multiplicative_depth: int
    repeat: int
    logical_operation_count: int
    output_shapes: Mapping[str, tuple[int, ...]]
    primitive_operation_count_estimate: Mapping[str, int] | None = None
    schema_version: str = SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workload_instance_id": self.workload_instance_id,
            "workload_id": self.workload_id,
            "provider_id": self.provider_id,
            "session_id": self.session_id,
            "config_fingerprint": self.config_fingerprint,
            "representation_type": self.representation_type,
            "encryption_time_s": self.encryption_time_s,
            "execution_time_s": self.execution_time_s,
            "decryption_time_s": self.decryption_time_s,
            "total_time_s": self.total_time_s,
            "encryption_time_std_s": self.encryption_time_std_s,
            "execution_time_std_s": self.execution_time_std_s,
            "decryption_time_std_s": self.decryption_time_std_s,
            "passed_validation": self.passed_validation,
            "max_absolute_error": self.max_absolute_error,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "required_multiplicative_depth": self.required_multiplicative_depth,
            "repeat": self.repeat,
            "logical_operation_count": self.logical_operation_count,
            "output_shapes": {key: list(value) for key, value in self.output_shapes.items()},
            "primitive_operation_count_estimate": (
                dict(self.primitive_operation_count_estimate)
                if self.primitive_operation_count_estimate is not None
                else None
            ),
        }


def write_json(results: Iterable[BenchmarkResult], destination: str | Path | TextIO) -> None:
    text = json.dumps(
        {"schema_version": SCHEMA_VERSION, "results": [result.to_json_dict() for result in results]},
        indent=2,
        sort_keys=True,
    ) + "\n"
    _write_text(destination, text)


def write_csv(results: Iterable[BenchmarkResult], destination: str | Path | TextIO) -> None:
    rows = [_csv_row(result) for result in results]
    if hasattr(destination, "write"):
        writer = csv.DictWriter(destination, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return
    with Path(destination).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_stdout(results: Iterable[BenchmarkResult], destination: str | Path | TextIO) -> None:
    lines = [
        f"{result.workload_instance_id} {result.provider_id} "
        f"{'pass' if result.passed_validation else 'fail'} "
        f"total={result.total_time_s:.6f}s max_error={result.max_absolute_error}"
        for result in results
    ]
    _write_text(destination, "\n".join(lines) + ("\n" if lines else ""))


def _csv_row(result: BenchmarkResult) -> dict[str, str]:
    data = result.to_json_dict()
    data["output_shapes"] = json.dumps(data["output_shapes"], sort_keys=True)
    return {column: _csv_cell(data[column]) for column in CSV_COLUMNS}


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_text(destination: str | Path | TextIO, text: str) -> None:
    if hasattr(destination, "write"):
        destination.write(text)
    else:
        Path(destination).write_text(text, encoding="utf-8")

