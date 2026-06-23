"""Public exception hierarchy for executable-encryption providers."""

from __future__ import annotations


class ExecutableEncryptionError(Exception):
    """Base class for executable-encryption errors."""


class MissingDependencyError(ExecutableEncryptionError):
    """Raised when an optional provider dependency is unavailable."""


class ProgramValidationError(ExecutableEncryptionError):
    """Raised when a program is malformed or unsupported."""


class UnsupportedOperationError(ProgramValidationError):
    """Raised when a provider does not support a program operation."""


class ProviderConfigurationError(ExecutableEncryptionError):
    """Raised when provider construction or backend setup fails."""


class BenchmarkConfigurationError(ExecutableEncryptionError):
    """Raised when benchmark configuration is invalid."""


class ProviderCompatibilityError(ExecutableEncryptionError):
    """Raised when a tensor belongs to the wrong provider."""


class SessionCompatibilityError(ExecutableEncryptionError):
    """Raised when provider session identifiers do not match."""


class ShapeMismatchError(ExecutableEncryptionError):
    """Raised when tensor or program shapes are incompatible."""


class DepthBudgetError(ProgramValidationError):
    """Raised when a program exceeds a provider multiplicative-depth budget."""

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        required_depth: int | None = None,
        configured_depth: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.required_depth = required_depth
        self.configured_depth = configured_depth


class ToleranceExceededError(ExecutableEncryptionError):
    """Raised when decrypted output exceeds the configured tolerance."""

