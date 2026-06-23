"""Shared provider-side validation and tensor arithmetic helpers."""

from __future__ import annotations

from typing import Any, TypeVar

from ..errors import ProviderCompatibilityError, SessionCompatibilityError, ShapeMismatchError
from ..tensors import PlainTensor

_T = TypeVar("_T")


def validate_tensor(
    value: Any,
    *,
    provider_id: str,
    session_id: str,
    expected_type: type[_T],
    operation: str,
) -> _T:
    """Validate provider/session/type metadata and return the typed value."""

    if getattr(value, "provider_id", None) != provider_id:
        raise ProviderCompatibilityError(f"{operation} requires {provider_id} tensor")
    if getattr(value, "session_id", None) != session_id:
        raise SessionCompatibilityError(f"{operation} requires current {provider_id} session")
    if not isinstance(value, expected_type):
        raise ProviderCompatibilityError(f"{operation} requires {expected_type.__name__}")
    return value


def validate_pair(
    lhs: Any,
    rhs: Any,
    *,
    provider_id: str,
    session_id: str,
    expected_type: type[_T],
    operation: str,
    same_shape: bool,
) -> tuple[_T, _T]:
    left = validate_tensor(
        lhs,
        provider_id=provider_id,
        session_id=session_id,
        expected_type=expected_type,
        operation=operation,
    )
    right = validate_tensor(
        rhs,
        provider_id=provider_id,
        session_id=session_id,
        expected_type=expected_type,
        operation=operation,
    )
    if same_shape and left.shape != right.shape:
        raise ShapeMismatchError(f"{operation} requires equal shapes")
    return left, right


def gemm_shape(lhs_shape: tuple[int, ...], rhs_shape: tuple[int, ...]) -> tuple[int, int, int]:
    if len(lhs_shape) != 2 or len(rhs_shape) != 2 or lhs_shape[1] != rhs_shape[0]:
        raise ShapeMismatchError(f"gemm requires (m,k) @ (k,n), got {lhs_shape} @ {rhs_shape}")
    return lhs_shape[0], lhs_shape[1], rhs_shape[1]


def elementwise_plain(
    lhs: PlainTensor,
    rhs: PlainTensor,
    op: str,
) -> PlainTensor:
    if lhs.shape != rhs.shape:
        raise ShapeMismatchError(f"{op} requires equal shapes")
    if op == "add":
        values = tuple(a + b for a, b in zip(lhs.values, rhs.values))
    elif op == "mul":
        values = tuple(a * b for a, b in zip(lhs.values, rhs.values))
    else:
        raise ValueError(f"unsupported elementwise op {op!r}")
    return PlainTensor(values=values, shape=lhs.shape)


def gemm_plain(lhs: PlainTensor, rhs: PlainTensor) -> PlainTensor:
    m, k, n = gemm_shape(lhs.shape, rhs.shape)
    return PlainTensor(
        values=tuple(
            sum(lhs.values[row * k + idx] * rhs.values[idx * n + col] for idx in range(k))
            for row in range(m)
            for col in range(n)
        ),
        shape=(m, n),
    )

