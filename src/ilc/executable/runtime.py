"""Shared node-by-node executable-encryption runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .errors import ProgramValidationError, ShapeMismatchError
from .program import EncryptedProgram, PlainProgram, ProgramOp
from .protocol import ExecutableEncryptionProvider
from .tensors import EncryptedTensor


@dataclass(frozen=True)
class ExecutionArtifact:
    """Immutable encrypted output bundle."""

    program_id: str
    provider_id: str
    session_id: str
    representation_type: str
    outputs: MappingProxyType[str, EncryptedTensor]

    @classmethod
    def create(
        cls,
        *,
        program_id: str,
        provider_id: str,
        session_id: str,
        representation_type: str,
        outputs: Mapping[str, EncryptedTensor],
    ) -> "ExecutionArtifact":
        return cls(
            program_id=program_id,
            provider_id=provider_id,
            session_id=session_id,
            representation_type=representation_type,
            outputs=MappingProxyType(dict(outputs)),
        )


class ExecutableGraphRuntime:
    """Execute a public program through a provider's public operation surface."""

    def execute(
        self,
        provider: ExecutableEncryptionProvider,
        program: PlainProgram,
        encrypted_program: EncryptedProgram,
        inputs: Mapping[str, EncryptedTensor],
        *,
        validate_program: bool = True,
    ) -> ExecutionArtifact:
        native_execute = getattr(provider, "execute_program", None)
        if callable(native_execute):
            self._validate_encrypted_program(provider, program, encrypted_program)
            outputs = native_execute(encrypted_program, inputs)
            return ExecutionArtifact.create(
                program_id=encrypted_program.program_id,
                provider_id=provider.provider_id,
                session_id=provider.session.session_id,
                representation_type=encrypted_program.representation_type,
                outputs=outputs,
            )

        if validate_program:
            program.revalidate()
            provider.validate_program(program)
        self._validate_encrypted_program(provider, program, encrypted_program)
        self._validate_inputs(provider, program, inputs)

        values: dict[str, EncryptedTensor] = dict(inputs)
        for node in program.nodes:
            if node.op == ProgramOp.INPUT:
                continue
            lhs = values[node.inputs[0]]
            rhs = values[node.inputs[1]]
            if node.op == ProgramOp.ADD:
                result = provider.add(lhs, rhs)
            elif node.op == ProgramOp.MUL:
                result = provider.mul(lhs, rhs)
            elif node.op == ProgramOp.GEMM:
                result = provider.gemm(lhs, rhs)
            else:
                raise ProgramValidationError(f"unsupported operation {node.op!r}")
            if result.shape != node.output_shape:
                raise ShapeMismatchError(
                    f"node {node.id!r}: expected shape {node.output_shape}, got {result.shape}"
                )
            values[node.id] = result

        return ExecutionArtifact.create(
            program_id=program.id,
            provider_id=provider.provider_id,
            session_id=provider.session.session_id,
            representation_type=encrypted_program.representation_type,
            outputs={output_id: values[output_id] for output_id in program.output_ids},
        )

    @staticmethod
    def _validate_encrypted_program(
        provider: ExecutableEncryptionProvider,
        program: PlainProgram,
        encrypted_program: EncryptedProgram,
    ) -> None:
        if encrypted_program.provider_id != provider.provider_id:
            raise ProgramValidationError("encrypted program provider mismatch")
        if encrypted_program.session_id != provider.session.session_id:
            raise ProgramValidationError("encrypted program session mismatch")
        if encrypted_program.program_id != program.id:
            raise ProgramValidationError("encrypted program id mismatch")
        if not encrypted_program.representation_type:
            raise ProgramValidationError("encrypted program representation_type is empty")

    @staticmethod
    def _validate_inputs(
        provider: ExecutableEncryptionProvider,
        program: PlainProgram,
        inputs: Mapping[str, EncryptedTensor],
    ) -> None:
        expected = set(program.input_ids)
        if set(inputs) != expected:
            raise ProgramValidationError(f"input ids mismatch: expected {expected!r}, got {set(inputs)!r}")
        shapes = {node.id: node.output_shape for node in program.nodes}
        for input_id, tensor in inputs.items():
            if tensor.provider_id != provider.provider_id:
                raise ProgramValidationError(f"input {input_id!r} provider mismatch")
            if tensor.session_id != provider.session.session_id:
                raise ProgramValidationError(f"input {input_id!r} session mismatch")
            if tensor.shape != shapes[input_id]:
                raise ProgramValidationError(f"input {input_id!r} shape mismatch")
