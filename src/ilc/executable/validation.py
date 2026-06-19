"""Validation helpers for executable-encryption programs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .errors import ToleranceExceededError
from .program import PlainProgram, ProgramOp
from .tensors import PlainTensor


def estimate_depth(program: PlainProgram) -> dict[str, int]:
    """Return multiplicative depth at each node."""

    depth: dict[str, int] = {}
    for node in program.nodes:
        if node.op == ProgramOp.INPUT:
            depth[node.id] = 0
        elif node.op == ProgramOp.ADD:
            depth[node.id] = max(depth[input_id] for input_id in node.inputs)
        elif node.op in (ProgramOp.MUL, ProgramOp.GEMM):
            depth[node.id] = max(depth[input_id] for input_id in node.inputs) + 1
    return depth


def required_program_depth(program: PlainProgram) -> int:
    depth = estimate_depth(program)
    return max(depth[output_id] for output_id in program.output_ids)


@dataclass(frozen=True)
class ToleranceResult:
    passed: bool
    max_absolute_error: float


def check_tolerance(
    actual: tuple[float, ...],
    expected: tuple[float, ...],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> ToleranceResult:
    if len(actual) != len(expected):
        raise ToleranceExceededError("actual and expected output lengths differ")
    max_error = 0.0
    for got, want in zip(actual, expected):
        err = abs(float(got) - float(want))
        max_error = max(max_error, err)
        if not isfinite(err) or err > absolute_tolerance + relative_tolerance * abs(float(want)):
            return ToleranceResult(False, max_error)
    return ToleranceResult(True, max_error)


def compare_outputs(
    actual: Mapping[str, PlainTensor],
    expected: Mapping[str, PlainTensor],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> ToleranceResult:
    if set(actual) != set(expected):
        raise ToleranceExceededError("actual and expected output ids differ")
    passed = True
    max_error = 0.0
    for output_id in actual:
        if actual[output_id].shape != expected[output_id].shape:
            raise ToleranceExceededError(f"output {output_id!r} shape mismatch")
        result = check_tolerance(
            actual[output_id].values,
            expected[output_id].values,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        passed = passed and result.passed
        max_error = max(max_error, result.max_absolute_error)
    return ToleranceResult(passed, max_error)

