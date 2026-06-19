"""Backend-neutral program graph contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol, Union, runtime_checkable

from .errors import ProgramValidationError

JsonValue = Union[
    str,
    int,
    float,
    bool,
    None,
    "tuple[JsonValue, ...]",
    "Mapping[str, JsonValue]",
]


class ProgramOp(Enum):
    """Supported executable-encryption operations."""

    INPUT = "INPUT"
    ADD = "ADD"
    MUL = "MUL"
    GEMM = "GEMM"


def frozen_attrs(value: object) -> object:
    """Recursively freeze public JSON-like node attributes."""

    if value is None:
        return MappingProxyType({})
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): frozen_attrs(val) for key, val in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(frozen_attrs(item) for item in value)
    return value


@dataclass(frozen=True)
class ProgramNode:
    """Immutable node in a topologically ordered program graph."""

    id: str
    op: ProgramOp
    inputs: tuple[str, ...]
    output_shape: tuple[int, ...]
    attrs: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ProgramValidationError("node id must be a non-empty string")
        if not isinstance(self.op, ProgramOp):
            raise ProgramValidationError(f"node {self.id!r} has invalid op {self.op!r}")
        shape = tuple(int(dim) for dim in self.output_shape)
        if not shape or any(dim <= 0 for dim in shape):
            raise ProgramValidationError(f"node {self.id!r} has invalid shape {shape!r}")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "output_shape", shape)
        object.__setattr__(self, "attrs", frozen_attrs(self.attrs))


@dataclass(frozen=True)
class PlainProgram:
    """Immutable backend-neutral program in topological order."""

    id: str
    nodes: tuple[ProgramNode, ...]
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ProgramValidationError("program id must be a non-empty string")
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "input_ids", tuple(self.input_ids))
        object.__setattr__(self, "output_ids", tuple(self.output_ids))
        self.revalidate()

    def revalidate(self) -> None:
        self._validate_structure()
        self._validate_shapes()

    def _validate_structure(self) -> None:
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ProgramValidationError(f"duplicate node id {node.id!r}")
            seen.add(node.id)
            if node.op == ProgramOp.INPUT and node.inputs:
                raise ProgramValidationError(f"INPUT node {node.id!r} must not have inputs")
            if node.op != ProgramOp.INPUT and not node.inputs:
                raise ProgramValidationError(f"node {node.id!r} must have inputs")
            for input_id in node.inputs:
                if input_id not in seen:
                    raise ProgramValidationError(
                        f"node {node.id!r}: input {input_id!r} is not yet defined"
                    )
        actual_inputs = {node.id for node in self.nodes if node.op == ProgramOp.INPUT}
        if set(self.input_ids) != actual_inputs:
            raise ProgramValidationError(
                f"input_ids {set(self.input_ids)!r} do not match INPUT nodes {actual_inputs!r}"
            )
        if not self.output_ids:
            raise ProgramValidationError("output_ids must not be empty")
        for output_id in self.output_ids:
            if output_id not in seen:
                raise ProgramValidationError(f"unknown output id {output_id!r}")

    def _validate_shapes(self) -> None:
        shapes: dict[str, tuple[int, ...]] = {}
        for node in self.nodes:
            if node.op in (ProgramOp.ADD, ProgramOp.MUL):
                if len(node.inputs) != 2:
                    raise ProgramValidationError(f"{node.op.name} node {node.id!r} needs 2 inputs")
                lhs_shape = shapes[node.inputs[0]]
                rhs_shape = shapes[node.inputs[1]]
                if lhs_shape != rhs_shape or node.output_shape != lhs_shape:
                    raise ProgramValidationError(
                        f"{node.op.name} node {node.id!r} shape mismatch: "
                        f"{lhs_shape}, {rhs_shape} -> {node.output_shape}"
                    )
            elif node.op == ProgramOp.GEMM:
                if len(node.inputs) != 2:
                    raise ProgramValidationError(f"GEMM node {node.id!r} needs 2 inputs")
                lhs_shape = shapes[node.inputs[0]]
                rhs_shape = shapes[node.inputs[1]]
                if len(lhs_shape) != 2 or len(rhs_shape) != 2 or lhs_shape[1] != rhs_shape[0]:
                    raise ProgramValidationError(
                        f"GEMM node {node.id!r} requires (m,k) @ (k,n), got {lhs_shape} @ {rhs_shape}"
                    )
                expected = (lhs_shape[0], rhs_shape[1])
                if node.output_shape != expected:
                    raise ProgramValidationError(
                        f"GEMM node {node.id!r} output {node.output_shape} != {expected}"
                    )
            shapes[node.id] = node.output_shape


@runtime_checkable
class EncryptedProgram(Protocol):
    """Opaque encrypted-program metadata visible to shared runtime code."""

    @property
    def provider_id(self) -> str:
        ...

    @property
    def session_id(self) -> str:
        ...

    @property
    def program_id(self) -> str:
        ...

    @property
    def representation_type(self) -> str:
        ...

