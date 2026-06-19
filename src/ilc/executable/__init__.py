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
from .encoding import (
    ENCRYPTED_GRAPH_REPRESENTATION_SUFFIX,
    ENCRYPTED_GRAPH_TENSOR_NAMES,
    OPCODE_ORDER,
    PROGRAM_ENCODING_VERSION,
    EncryptedGraphProgram,
    ProgramEncoding,
    encode_program,
    encrypted_graph_representation_type,
    encrypted_graph_tensor_shapes,
    validate_encrypted_graph_program,
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
    "ENCRYPTED_GRAPH_REPRESENTATION_SUFFIX",
    "ENCRYPTED_GRAPH_TENSOR_NAMES",
    "EncryptedGraphProgram",
    "MissingDependencyError",
    "OPCODE_ORDER",
    "PROGRAM_ENCODING_VERSION",
    "PlainProgram",
    "PlainTensor",
    "ProgramEncoding",
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
    "encode_program",
    "encrypted_graph_representation_type",
    "encrypted_graph_tensor_shapes",
    "estimate_depth",
    "frozen_attrs",
    "load_mnist_fixture",
    "required_program_depth",
    "validate_encrypted_graph_program",
]
