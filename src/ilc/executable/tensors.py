"""Tensor contracts for executable-encryption providers."""

from __future__ import annotations

from dataclasses import dataclass
from math import prod
from numbers import Real
from typing import Protocol, runtime_checkable

from .errors import ShapeMismatchError


@dataclass(frozen=True)
class PlainTensor:
    """Immutable dense numeric tensor in row-major order."""

    values: tuple[float, ...]
    shape: tuple[int, ...]

    def __post_init__(self) -> None:
        shape = tuple(int(dim) for dim in self.shape)
        if not shape or any(dim <= 0 for dim in shape):
            raise ShapeMismatchError(f"shape must contain positive dimensions, got {self.shape!r}")
        values = tuple(float(value) for value in self.values)
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
            raise TypeError("PlainTensor values must be real numbers")
        if len(values) != prod(shape):
            raise ShapeMismatchError(
                f"value count {len(values)} does not match shape {shape} size {prod(shape)}"
            )
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "shape", shape)

    @classmethod
    def scalar(cls, value: float) -> "PlainTensor":
        return cls(values=(float(value),), shape=(1,))


@runtime_checkable
class EncryptedTensor(Protocol):
    """Opaque encrypted tensor metadata visible to shared runtime code."""

    @property
    def provider_id(self) -> str:
        ...

    @property
    def session_id(self) -> str:
        ...

    @property
    def shape(self) -> tuple[int, ...]:
        ...

