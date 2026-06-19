"""Deterministic executable-encryption benchmark workloads."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from importlib import resources
from types import MappingProxyType
from typing import Mapping

from .program import PlainProgram, ProgramNode, ProgramOp
from .tensors import PlainTensor
from .validation import required_program_depth


@dataclass(frozen=True)
class WorkloadInstance:
    workload_id: str
    workload_instance_id: str
    program: PlainProgram
    plain_inputs: Mapping[str, PlainTensor]
    required_multiplicative_depth: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "plain_inputs", MappingProxyType(dict(self.plain_inputs)))
        if self.workload_instance_id != self.program.id:
            raise ValueError("workload_instance_id must match program.id")
        if set(self.plain_inputs) != set(self.program.input_ids):
            raise ValueError("plain_inputs must match program input ids")
        for node in self.program.nodes:
            if node.op == ProgramOp.INPUT and self.plain_inputs[node.id].shape != node.output_shape:
                raise ValueError(f"input {node.id!r} shape mismatch")
        if self.required_multiplicative_depth != required_program_depth(self.program):
            raise ValueError("required_multiplicative_depth mismatch")


def load_mnist_fixture() -> dict[str, object]:
    fixture = resources.files("ilc.executable.fixtures") / "mnist_v1.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def _input(node_id: str, shape: tuple[int, ...]) -> ProgramNode:
    return ProgramNode(id=node_id, op=ProgramOp.INPUT, inputs=(), output_shape=shape)


def _op(node_id: str, op: ProgramOp, inputs: tuple[str, str], shape: tuple[int, ...]) -> ProgramNode:
    return ProgramNode(id=node_id, op=op, inputs=inputs, output_shape=shape)


def _vec(seed: int, length: int = 8) -> PlainTensor:
    return PlainTensor(
        values=tuple(((seed + 1) * 10 + idx + 1) / 100.0 for idx in range(length)),
        shape=(length,),
    )


def _mat(seed: int, n: int = 2) -> PlainTensor:
    return PlainTensor(
        values=tuple((seed * 10 + row * n + col + 1) / 100.0 for row in range(n) for col in range(n)),
        shape=(n, n),
    )


def _tensor(rows: list[list[float]]) -> PlainTensor:
    if not rows or not rows[0]:
        raise ValueError("tensor rows must be non-empty")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("tensor rows must be rectangular")
    return PlainTensor(
        values=tuple(float(value) for row in rows for value in row),
        shape=(len(rows), width),
    )


def _add_chain() -> WorkloadInstance:
    inputs = tuple(_input(f"x{i}", (8,)) for i in range(9))
    ops = []
    previous = "x0"
    for idx in range(8):
        node_id = f"add_{idx}"
        ops.append(_op(node_id, ProgramOp.ADD, (previous, f"x{idx + 1}"), (8,)))
        previous = node_id
    program = PlainProgram(
        id="add_chain",
        nodes=inputs + tuple(ops),
        input_ids=tuple(f"x{i}" for i in range(9)),
        output_ids=("add_7",),
    )
    return WorkloadInstance("add_chain", "add_chain", program, {f"x{i}": _vec(i) for i in range(9)}, 0)


def _mul_chain() -> WorkloadInstance:
    program = PlainProgram(
        id="mul_chain",
        nodes=(
            _input("x0", (8,)),
            _input("x1", (8,)),
            _input("x2", (8,)),
            _op("mul_0", ProgramOp.MUL, ("x0", "x1"), (8,)),
            _op("mul_1", ProgramOp.MUL, ("mul_0", "x2"), (8,)),
        ),
        input_ids=("x0", "x1", "x2"),
        output_ids=("mul_1",),
    )
    return WorkloadInstance("mul_chain", "mul_chain", program, {f"x{i}": _vec(i) for i in range(3)}, 2)


def _gemm_chain_small() -> WorkloadInstance:
    program = PlainProgram(
        id="gemm_chain_small",
        nodes=(
            _input("m0", (2, 2)),
            _input("m1", (2, 2)),
            _input("m2", (2, 2)),
            _op("gemm_0", ProgramOp.GEMM, ("m0", "m1"), (2, 2)),
            _op("gemm_1", ProgramOp.GEMM, ("gemm_0", "m2"), (2, 2)),
        ),
        input_ids=("m0", "m1", "m2"),
        output_ids=("gemm_1",),
    )
    return WorkloadInstance(
        "gemm_chain_small",
        "gemm_chain_small",
        program,
        {f"m{i}": _mat(i) for i in range(3)},
        2,
    )


def _mnist_linear(instance_id: str, batch_size: int) -> WorkloadInstance:
    fixture = load_mnist_fixture()
    images = fixture["images"][:batch_size]
    weights = fixture["weights"]
    program = PlainProgram(
        id=instance_id,
        nodes=(
            _input("images", (batch_size, 65)),
            _input("weights", (65, 10)),
            _op("logits", ProgramOp.GEMM, ("images", "weights"), (batch_size, 10)),
        ),
        input_ids=("images", "weights"),
        output_ids=("logits",),
    )
    return WorkloadInstance(
        "mnist_linear_v1",
        instance_id,
        program,
        {"images": _tensor(images), "weights": _tensor(weights)},
        1,
    )


@cache
def _registry() -> Mapping[str, WorkloadInstance]:
    return MappingProxyType(
        {
            "add_chain": _add_chain(),
            "mul_chain": _mul_chain(),
            "gemm_chain_small": _gemm_chain_small(),
            "mnist_linear_v1_b1": _mnist_linear("mnist_linear_v1_b1", 1),
            "mnist_linear_v1_b16": _mnist_linear("mnist_linear_v1_b16", 16),
        }
    )


class _WorkloadRegistry(Mapping[str, WorkloadInstance]):
    def __getitem__(self, key: str) -> WorkloadInstance:
        return _registry()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(_registry())

    def __len__(self) -> int:
        return len(_registry())


WORKLOAD_REGISTRY: Mapping[str, WorkloadInstance] = MappingProxyType(_WorkloadRegistry())

