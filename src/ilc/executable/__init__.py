"""Executable-encryption contracts, runtime, and benchmark helpers."""

from .errors import (
    BenchmarkConfigurationError,
    DepthBudgetError,
    ExecutableEncryptionError,
    MissingDependencyError,
    ProgramValidationError,
    ProviderCompatibilityError,
    ProviderConfigurationError,
    SessionCompatibilityError,
    ShapeMismatchError,
    ToleranceExceededError,
    UnsupportedOperationError,
)
from .metrics import BenchmarkResult, CSV_COLUMNS, SCHEMA_VERSION
from .program import EncryptedProgram, PlainProgram, ProgramNode, ProgramOp, frozen_attrs
from .protocol import ExecutableEncryptionProvider
from .runtime import ExecutableGraphRuntime, ExecutionArtifact
from .session import BasicSession, ProviderSession, compute_fingerprint
from .tensors import EncryptedTensor, PlainTensor
from .validation import ToleranceResult, check_tolerance, compare_outputs, estimate_depth, required_program_depth
from .workloads import WORKLOAD_REGISTRY, WorkloadInstance, load_mnist_fixture

__all__ = [
    "BasicSession",
    "BenchmarkConfigurationError",
    "BenchmarkResult",
    "CSV_COLUMNS",
    "DepthBudgetError",
    "EncryptedProgram",
    "EncryptedTensor",
    "ExecutableEncryptionError",
    "ExecutableEncryptionProvider",
    "ExecutableGraphRuntime",
    "ExecutionArtifact",
    "MissingDependencyError",
    "PlainProgram",
    "PlainTensor",
    "ProgramNode",
    "ProgramOp",
    "ProgramValidationError",
    "ProviderCompatibilityError",
    "ProviderConfigurationError",
    "ProviderSession",
    "SCHEMA_VERSION",
    "SessionCompatibilityError",
    "ShapeMismatchError",
    "ToleranceExceededError",
    "ToleranceResult",
    "UnsupportedOperationError",
    "WORKLOAD_REGISTRY",
    "WorkloadInstance",
    "check_tolerance",
    "compare_outputs",
    "compute_fingerprint",
    "estimate_depth",
    "frozen_attrs",
    "load_mnist_fixture",
    "required_program_depth",
]
