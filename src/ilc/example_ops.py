from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tinychain as tc

from .library import AuthContext, ILCClient


@dataclass(frozen=True)
class AbcEvaluation:
    a: int
    b: int
    c: int
    recovered: int
    expected: int
    ok: bool


def _first_result_component(value: Any) -> float:
    if isinstance(value, dict):
        data = value.get("result")
    else:
        data = value

    if not isinstance(data, list) or not data:
        raise RuntimeError(f"unexpected evaluator response shape: {value!r}")

    return float(data[0])


def evaluate_abc(
    *,
    client: ILCClient,
    auth: AuthContext,
    a: int,
    b: int,
    c: int,
) -> AbcEvaluation:
    add_ab = tc.execute(
        client.add_scalars(
            a=float(a),
            b=float(b),
            auth=auth,
        )
    )
    add_neg_c = tc.execute(
        client.sub_scalars(
            a=_first_result_component(add_ab),
            b=float(c),
            auth=auth,
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
