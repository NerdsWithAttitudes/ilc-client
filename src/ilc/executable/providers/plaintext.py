"""Plaintext reference executable-encryption provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from ..program import PlainProgram, ProgramOp
from ..session import BasicSession, compute_fingerprint
from ..tensors import PlainTensor
from ._helpers import elementwise_plain, gemm_plain, validate_pair, validate_tensor


@dataclass(frozen=True)
class PlaintextEncryptedTensor:
    session_id: str
    shape: tuple[int, ...]
    _plain: PlainTensor = field(repr=False)
    provider_id: str = field(default="plaintext", init=False)


@dataclass(frozen=True)
class PlaintextEncryptedProgram:
    session_id: str
    program_id: str
    provider_id: str = field(default="plaintext", init=False)
    representation_type: str = field(default="plaintext_program_handle_v1", init=False)


class PlaintextProvider:
    """Provider used for reference execution and public benchmark plumbing."""

    def __init__(self) -> None:
        self._session = BasicSession(
            provider_id="plaintext",
            session_id=uuid4().hex,
            config_fingerprint=compute_fingerprint("plaintext", {"version": 1}),
        )

    @property
    def provider_id(self) -> str:
        return "plaintext"

    @property
    def session(self) -> BasicSession:
        return self._session

    @property
    def absolute_tolerance(self) -> float:
        return 0.0

    @property
    def relative_tolerance(self) -> float:
        return 0.0

    def validate_program(self, program: PlainProgram) -> None:
        program.revalidate()

    def encrypt_tensor(self, tensor: PlainTensor) -> PlaintextEncryptedTensor:
        return PlaintextEncryptedTensor(
            session_id=self._session.session_id,
            shape=tensor.shape,
            _plain=tensor,
        )

    def encrypt_program(
        self,
        program: PlainProgram,
        *,
        assume_validated: bool = False,
    ) -> PlaintextEncryptedProgram:
        if not assume_validated:
            self.validate_program(program)
        return PlaintextEncryptedProgram(
            session_id=self._session.session_id,
            program_id=program.id,
        )

    def decrypt_tensor(self, tensor: PlaintextEncryptedTensor) -> PlainTensor:
        return self._validate_tensor(tensor, "decrypt_tensor")._plain

    def add(self, lhs: PlaintextEncryptedTensor, rhs: PlaintextEncryptedTensor) -> PlaintextEncryptedTensor:
        left, right = self._validate_pair(lhs, rhs, "add", same_shape=True)
        return self.encrypt_tensor(elementwise_plain(left._plain, right._plain, "add"))

    def mul(self, lhs: PlaintextEncryptedTensor, rhs: PlaintextEncryptedTensor) -> PlaintextEncryptedTensor:
        left, right = self._validate_pair(lhs, rhs, "mul", same_shape=True)
        return self.encrypt_tensor(elementwise_plain(left._plain, right._plain, "mul"))

    def gemm(self, lhs: PlaintextEncryptedTensor, rhs: PlaintextEncryptedTensor) -> PlaintextEncryptedTensor:
        left, right = self._validate_pair(lhs, rhs, "gemm", same_shape=False)
        return self.encrypt_tensor(gemm_plain(left._plain, right._plain))

    def _validate_pair(
        self,
        lhs: object,
        rhs: object,
        operation: str,
        *,
        same_shape: bool,
    ) -> tuple[PlaintextEncryptedTensor, PlaintextEncryptedTensor]:
        return validate_pair(
            lhs,
            rhs,
            provider_id="plaintext",
            session_id=self._session.session_id,
            expected_type=PlaintextEncryptedTensor,
            operation=operation,
            same_shape=same_shape,
        )

    def _validate_tensor(self, tensor: object, operation: str) -> PlaintextEncryptedTensor:
        return validate_tensor(
            tensor,
            provider_id="plaintext",
            session_id=self._session.session_id,
            expected_type=PlaintextEncryptedTensor,
            operation=operation,
        )
