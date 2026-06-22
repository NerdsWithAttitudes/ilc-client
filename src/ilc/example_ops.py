from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

import tinychain as tc
from tinychain.codec import decode_response_body

from .library import ILCClient

_CONTEXT_ID = [1] * 16
_KEY_ID = [2] * 16
_PARAMS_ID = [3] * 16
_CHART_ID = [4] * 16
_MODULI = [17, 19]


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
    if isinstance(value, Mapping) and isinstance(value.get("ciphertext"), Mapping):
        limbs = value["ciphertext"].get("limbs")
        if isinstance(limbs, Sequence) and limbs and isinstance(limbs[0], Sequence) and limbs[0]:
            return float(limbs[0][0])

    if isinstance(value, Mapping):
        data = value.get("result")
    else:
        data = value

    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)) or not data:
        raise RuntimeError(f"unexpected evaluator response shape: {value!r}")

    return float(data[0])


def _resolve(value: Any) -> Any:
    if isinstance(value, (tc.OpRef, tc.Ref)):
        return tc.execute(value)

    status = getattr(value, "status", None)
    if callable(status):
        status = status()
    if status == 200:
        return decode_response_body(value)
    if status == 204:
        return None

    if hasattr(value, "body"):
        try:
            return decode_response_body(value)
        except (AssertionError, json.JSONDecodeError, TypeError, ValueError) as err:
            body = getattr(value, "body", None)
            text = None
            try:
                raw = body.value() if body is not None else None
                text = raw.to_json() if hasattr(raw, "to_json") else raw
            except (AttributeError, TypeError, ValueError):
                text = None
            raise RuntimeError(f"TinyChain route failed with status={status}: {text!r}") from err

    return value


def _public_context() -> dict[str, Any]:
    return {
        "version": 1,
        "context_id": _CONTEXT_ID,
        "key_id": _KEY_ID,
        "params_id": _PARAMS_ID,
        "moduli": _MODULI,
        "payload_dims": 2,
        "representative_dims": 2,
        "chart_id": _CHART_ID,
        "metric_view": {
            "metric_commitment": [5] * 32,
            "chart_id": _CHART_ID,
            "dimension": 2,
            "distortion_bound_ppm": 10_000,
            "leakage": {
                "shape": True,
                "admitted_ops": True,
                "distortion_bounds": True,
                "metric_commitment": True,
            },
            "admitted_ops": ["add"],
        },
        "admitted_ops": ["add"],
    }


def _ciphertext(value: int) -> dict[str, Any]:
    return {
        "limbs": [[value % modulus, value % modulus] for modulus in _MODULI],
        "context_id": _CONTEXT_ID,
        "key_id": _KEY_ID,
        "params_id": _PARAMS_ID,
        "chart_id": _CHART_ID,
        "shape": [2],
        "budget_log2": 1,
        "max_budget_log2": None,
    }


def evaluate_abc(
    *,
    client: ILCClient,
    a: int,
    b: int,
    c: int,
) -> AbcEvaluation:
    public_context = _public_context()
    add_ab = _resolve(
        client.add(
            public_context=public_context,
            lhs_ciphertext=_ciphertext(a),
            rhs_ciphertext=_ciphertext(b),
        )
    )
    add_neg_c = _resolve(
        client.add(
            public_context=public_context,
            lhs_ciphertext=add_ab["ciphertext"]
            if isinstance(add_ab, Mapping) and "ciphertext" in add_ab
            else _raise_unexpected_add(add_ab),
            rhs_ciphertext=_ciphertext(-c),
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


def _raise_unexpected_add(value: Any) -> Any:
    raise RuntimeError(f"unexpected add response shape: {value!r}")
