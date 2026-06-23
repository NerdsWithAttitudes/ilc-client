"""Executable-encryption provider protocol."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .program import EncryptedProgram, PlainProgram
from .session import ProviderSession
from .tensors import EncryptedTensor, PlainTensor


@runtime_checkable
class ExecutableEncryptionProvider(Protocol):
    """Required V1 provider surface."""

    @property
    def provider_id(self) -> str:
        ...

    @property
    def session(self) -> ProviderSession:
        ...

    @property
    def absolute_tolerance(self) -> float:
        ...

    @property
    def relative_tolerance(self) -> float:
        ...

    def validate_program(self, program: PlainProgram) -> None:
        ...

    def encrypt_tensor(self, tensor: PlainTensor) -> EncryptedTensor:
        ...

    def encrypt_program(
        self,
        program: PlainProgram,
        *,
        assume_validated: bool = False,
    ) -> EncryptedProgram:
        ...

    def execute_program(
        self,
        encrypted_program: EncryptedProgram,
        inputs: Mapping[str, EncryptedTensor],
    ) -> Mapping[str, EncryptedTensor]:
        ...

    def add(self, lhs: EncryptedTensor, rhs: EncryptedTensor) -> EncryptedTensor:
        ...

    def mul(self, lhs: EncryptedTensor, rhs: EncryptedTensor) -> EncryptedTensor:
        ...

    def gemm(self, lhs: EncryptedTensor, rhs: EncryptedTensor) -> EncryptedTensor:
        ...

    def decrypt_tensor(self, tensor: EncryptedTensor) -> PlainTensor:
        ...
