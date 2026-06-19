"""Deterministic graph/tensor encoding for executable encryption."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, Mapping, TypeVar

from .errors import ProgramValidationError
from .program import PlainProgram, ProgramOp
from .tensors import EncryptedTensor, PlainTensor

TensorT = TypeVar("TensorT", bound=EncryptedTensor)

PROGRAM_ENCODING_VERSION = "program_graph_tensor_encoding_v1"
ENCRYPTED_GRAPH_REPRESENTATION_SUFFIX = "encrypted_graph_tensor_encoding_v1"
ENCRYPTED_GRAPH_TENSOR_NAMES: tuple[str, ...] = (
    "opcode",
    "adjacency",
    "lhs_selector",
    "rhs_selector",
    "input_selector",
    "output_selector",
)

OPCODE_ORDER: tuple[ProgramOp, ...] = (
    ProgramOp.INPUT,
    ProgramOp.ADD,
    ProgramOp.MUL,
    ProgramOp.GEMM,
)


@dataclass(frozen=True)
class ProgramEncoding:
    """Versioned tensor encoding of a program graph."""

    version: str
    program_id: str
    node_ids: tuple[str, ...]
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    node_shapes: tuple[tuple[int, ...], ...]
    tensors: Mapping[str, PlainTensor] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", tuple(self.node_ids))
        object.__setattr__(self, "input_ids", tuple(self.input_ids))
        object.__setattr__(self, "output_ids", tuple(self.output_ids))
        object.__setattr__(self, "node_shapes", tuple(tuple(shape) for shape in self.node_shapes))
        object.__setattr__(self, "tensors", MappingProxyType(dict(self.tensors)))


@dataclass(frozen=True)
class EncryptedGraphProgram(Generic[TensorT]):
    """Provider-neutral encrypted executable graph artifact."""

    provider_id: str
    session_id: str
    program_id: str
    node_ids: tuple[str, ...]
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    node_shapes: tuple[tuple[int, ...], ...]
    encrypted_tensors: Mapping[str, TensorT] = field(repr=False)
    representation_type: str = ""

    def __post_init__(self) -> None:
        provider_id = str(self.provider_id)
        representation_type = self.representation_type or encrypted_graph_representation_type(provider_id)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "program_id", str(self.program_id))
        object.__setattr__(self, "node_ids", tuple(str(value) for value in self.node_ids))
        object.__setattr__(self, "input_ids", tuple(str(value) for value in self.input_ids))
        object.__setattr__(self, "output_ids", tuple(str(value) for value in self.output_ids))
        object.__setattr__(self, "node_shapes", tuple(tuple(int(dim) for dim in shape) for shape in self.node_shapes))
        object.__setattr__(self, "encrypted_tensors", MappingProxyType(dict(self.encrypted_tensors)))
        object.__setattr__(self, "representation_type", representation_type)


def encrypted_graph_representation_type(provider_id: str) -> str:
    """Return the canonical encrypted graph representation type for a provider."""

    return f"{provider_id}_{ENCRYPTED_GRAPH_REPRESENTATION_SUFFIX}"


def encrypted_graph_tensor_shapes(
    *,
    node_count: int,
    input_count: int,
    output_count: int,
) -> dict[str, tuple[int, ...]]:
    """Return the canonical encrypted graph tensor shapes."""

    return {
        "opcode": (node_count, len(OPCODE_ORDER)),
        "adjacency": (node_count, node_count),
        "lhs_selector": (node_count, node_count),
        "rhs_selector": (node_count, node_count),
        "input_selector": (node_count, max(input_count, 1)),
        "output_selector": (max(output_count, 1), node_count),
    }


def validate_encrypted_graph_program(
    encrypted_program: EncryptedGraphProgram[TensorT],
    *,
    provider_id: str,
    session_id: str | None = None,
) -> dict[str, tuple[int, ...]]:
    """Validate provider-neutral encrypted graph metadata and tensor shapes."""

    if encrypted_program.provider_id != provider_id:
        raise ProgramValidationError("encrypted program provider mismatch")
    if session_id is not None and encrypted_program.session_id != session_id:
        raise ProgramValidationError("encrypted program session mismatch")
    if encrypted_program.representation_type != encrypted_graph_representation_type(provider_id):
        raise ProgramValidationError("encrypted program representation_type mismatch")

    node_count = len(encrypted_program.node_ids)
    if node_count == 0:
        raise ProgramValidationError("encrypted program has no nodes")
    if len(set(encrypted_program.node_ids)) != node_count:
        raise ProgramValidationError("encrypted program node ids are not unique")
    if len(encrypted_program.node_shapes) != node_count:
        raise ProgramValidationError("encrypted program node shape count mismatch")
    if not encrypted_program.input_ids:
        raise ProgramValidationError("encrypted program has no inputs")
    if not encrypted_program.output_ids:
        raise ProgramValidationError("encrypted program has no outputs")
    node_ids = set(encrypted_program.node_ids)
    if not set(encrypted_program.input_ids).issubset(node_ids):
        raise ProgramValidationError("encrypted program input ids must be node ids")
    if not set(encrypted_program.output_ids).issubset(node_ids):
        raise ProgramValidationError("encrypted program output ids must be node ids")

    expected_shapes = encrypted_graph_tensor_shapes(
        node_count=node_count,
        input_count=len(encrypted_program.input_ids),
        output_count=len(encrypted_program.output_ids),
    )
    if set(encrypted_program.encrypted_tensors) != set(expected_shapes):
        raise ProgramValidationError("encrypted program tensor set mismatch")
    for name, shape in expected_shapes.items():
        tensor = encrypted_program.encrypted_tensors[name]
        if tensor.provider_id != provider_id:
            raise ProgramValidationError(f"encrypted program tensor {name!r} provider mismatch")
        if session_id is not None and tensor.session_id != session_id:
            raise ProgramValidationError(f"encrypted program tensor {name!r} session mismatch")
        if tensor.shape != shape:
            raise ProgramValidationError(f"encrypted program tensor {name!r} shape mismatch")
    return expected_shapes


def encode_program(program: PlainProgram) -> ProgramEncoding:
    """Encode a program as opcode, adjacency, and selector tensors."""

    program.revalidate()
    node_ids = tuple(node.id for node in program.nodes)
    node_index = {node_id: idx for idx, node_id in enumerate(node_ids)}
    input_index = {input_id: idx for idx, input_id in enumerate(program.input_ids)}
    n_nodes = len(node_ids)
    n_inputs = len(program.input_ids)
    n_outputs = len(program.output_ids)

    opcode_values = [0.0] * (n_nodes * len(OPCODE_ORDER))
    adjacency_values = [0.0] * (n_nodes * n_nodes)
    lhs_values = [0.0] * (n_nodes * n_nodes)
    rhs_values = [0.0] * (n_nodes * n_nodes)
    input_values = [0.0] * (n_nodes * max(n_inputs, 1))
    output_values = [0.0] * (max(n_outputs, 1) * n_nodes)

    for row, node in enumerate(program.nodes):
        opcode_values[row * len(OPCODE_ORDER) + OPCODE_ORDER.index(node.op)] = 1.0
        if node.op == ProgramOp.INPUT:
            input_values[row * max(n_inputs, 1) + input_index[node.id]] = 1.0
            continue
        if len(node.inputs) != 2:
            raise ProgramValidationError(f"node {node.id!r} must have two inputs")
        lhs_col = node_index[node.inputs[0]]
        rhs_col = node_index[node.inputs[1]]
        adjacency_values[lhs_col * n_nodes + row] = 1.0
        adjacency_values[rhs_col * n_nodes + row] = 1.0
        lhs_values[row * n_nodes + lhs_col] = 1.0
        rhs_values[row * n_nodes + rhs_col] = 1.0

    for row, output_id in enumerate(program.output_ids):
        output_values[row * n_nodes + node_index[output_id]] = 1.0

    shapes = encrypted_graph_tensor_shapes(node_count=n_nodes, input_count=n_inputs, output_count=n_outputs)
    tensors = {
        "opcode": PlainTensor(tuple(opcode_values), shapes["opcode"]),
        "adjacency": PlainTensor(tuple(adjacency_values), shapes["adjacency"]),
        "lhs_selector": PlainTensor(tuple(lhs_values), shapes["lhs_selector"]),
        "rhs_selector": PlainTensor(tuple(rhs_values), shapes["rhs_selector"]),
        "input_selector": PlainTensor(tuple(input_values), shapes["input_selector"]),
        "output_selector": PlainTensor(tuple(output_values), shapes["output_selector"]),
    }
    return ProgramEncoding(
        version=PROGRAM_ENCODING_VERSION,
        program_id=program.id,
        node_ids=node_ids,
        input_ids=tuple(program.input_ids),
        output_ids=tuple(program.output_ids),
        node_shapes=tuple(node.output_shape for node in program.nodes),
        tensors=tensors,
    )
