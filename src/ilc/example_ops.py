from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import tinychain as tc

from .config import DEFAULT_COMPUTE
from .library import ILCClient


@dataclass(frozen=True)
class AbcEvaluation:
    a: int
    b: int
    c: int
    recovered: int
    expected: int
    ok: bool


def _first_result_component(value: Any) -> float:
    """Extract the first ciphertext component from evaluator output."""
    if isinstance(value, Mapping):
        data = value.get("result")
    else:
        data = value

    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)) or not data:
        raise RuntimeError(f"unexpected evaluator response shape: {value!r}")

    return float(data[0])


def evaluate_abc(
    *,
    client: ILCClient,
    a: int,
    b: int,
    c: int,
) -> AbcEvaluation:
    metric = list(DEFAULT_COMPUTE.metric)
    add_ab = tc.execute(
        client.add(
            metric=metric,
            lhs=[float(a), 0.0],
            rhs=[float(b), 0.0],
        )
    )
    add_neg_c = tc.execute(
        client.add(
            metric=metric,
            lhs=[_first_result_component(add_ab), 0.0],
            rhs=[-float(c), 0.0],
        )
    )

    recovered = int(round(_first_result_component(add_neg_c)))
    expected = a + b - c
    return AbcEvaluation(
        a=a,
        b=b,
        c=c,
        recovered=recovered,
        expected=expected,
        ok=(recovered == expected),
    )
