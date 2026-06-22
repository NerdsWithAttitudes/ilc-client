"""Shared node-by-node executable-encryption runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .errors import ProgramValidationError
from .program import EncryptedProgram, PlainProgram
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
    """Validate public metadata and dispatch encrypted execution to the provider."""

    def execute(
        self,
        provider: ExecutableEncryptionProvider,
        program: PlainProgram,
        encrypted_program: EncryptedProgram,
        inputs: Mapping[str, EncryptedTensor],
        *,
        validate_program: bool = True,
    ) -> ExecutionArtifact:
        if validate_program:
            program.revalidate()
            provider.validate_program(program)
        self._validate_encrypted_program(provider, program, encrypted_program)
        self._validate_inputs(provider, program, inputs)
        outputs = provider.execute_program(encrypted_program, inputs)
        self._validate_outputs(provider, program, outputs)

        return ExecutionArtifact.create(
            program_id=encrypted_program.program_id,
            provider_id=provider.provider_id,
            session_id=provider.session.session_id,
            representation_type=encrypted_program.representation_type,
            outputs=outputs,
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

    @staticmethod
    def _validate_outputs(
        provider: ExecutableEncryptionProvider,
        program: PlainProgram,
        outputs: Mapping[str, EncryptedTensor],
    ) -> None:
        expected = set(program.output_ids)
        if set(outputs) != expected:
            raise ProgramValidationError(f"output ids mismatch: expected {expected!r}, got {set(outputs)!r}")
        shapes = {node.id: node.output_shape for node in program.nodes}
        for output_id, tensor in outputs.items():
            if tensor.provider_id != provider.provider_id:
                raise ProgramValidationError(f"output {output_id!r} provider mismatch")
            if tensor.session_id != provider.session.session_id:
                raise ProgramValidationError(f"output {output_id!r} session mismatch")
            if tensor.shape != shapes[output_id]:
                raise ProgramValidationError(f"output {output_id!r} shape mismatch")
