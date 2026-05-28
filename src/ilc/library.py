from __future__ import annotations

from typing import Any, TypeAlias

import tinychain as tc
from tinychain.library import Library
from tinychain.uri import URI

from .config import (
    CLIENT_NAME,
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SERVER_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    DEFAULT_VERSION,
    PUBLISHER,
    SERVER_NAME,
)

RepresentativePublicContext: TypeAlias = dict[str, Any]
RepresentativeCiphertext: TypeAlias = dict[str, Any]
OpaqueCiphertextHandle: TypeAlias = dict[str, Any]
RepresentativeApproxTensor: TypeAlias = dict[str, Any]
RepresentativeApproxInput: TypeAlias = dict[str, Any]


class ILCServer(Library):
    """Remote ILC server wrapper for authenticated chart representative routes."""

    publisher = PUBLISHER
    name = SERVER_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_SERVER_AUTHORITY)

    @property
    def route_root(self) -> str:
        return self.id().path

    def _post(self, path: str, body: dict[str, Any]) -> tc.OpRef:
        return tc.OpRef("POST", f"{self.route_root}{path}", body=body)

    def setup(
        self,
        *,
        params: dict[str, Any],
        payload_dims: int,
        representative_dims: int,
        metric_policy: str,
        admitted_ops: list[str] | None = None,
    ) -> tc.OpRef:
        return self._post(
            "/chart/setup",
            {
                "params": params,
                "payload_dims": int(payload_dims),
                "representative_dims": int(representative_dims),
                "metric_policy": metric_policy,
                "admitted_ops": admitted_ops or ["add"],
            },
        )

    def encrypt(
        self,
        *,
        public_context: RepresentativePublicContext,
        payload: list[int],
        budget_log2: int | None = None,
    ) -> tc.OpRef:
        body: dict[str, object] = {
            "public_context": public_context,
            "payload": payload,
        }
        if budget_log2 is not None:
            body["budget_log2"] = budget_log2
        return self._post("/chart/encrypt", body)

    def decrypt(
        self,
        *,
        public_context: RepresentativePublicContext,
        ciphertext: RepresentativeCiphertext,
        handle: OpaqueCiphertextHandle,
    ) -> tc.OpRef:
        return self._post(
            "/chart/decrypt",
            {
                "public_context": public_context,
                "ciphertext": ciphertext,
                "handle": handle,
            },
        )

    def record_eval(
        self,
        *,
        public_context: RepresentativePublicContext,
        op: str,
        input_handles: list[OpaqueCiphertextHandle],
    ) -> tc.OpRef:
        return self._post(
            "/chart/record_eval",
            {
                "public_context": public_context,
                "op": op,
                "input_handles": input_handles,
            },
        )

    def exact_plan_mul(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs: dict[str, Any],
        rhs: dict[str, Any],
    ) -> tc.OpRef:
        return self._post(
            "/chart/exact/plan_mul",
            {
                "public_context": public_context,
                "lhs": lhs,
                "rhs": rhs,
            },
        )

    def exact_plan_gemm(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs: dict[str, Any],
        rhs: dict[str, Any],
    ) -> tc.OpRef:
        return self._post(
            "/chart/exact/plan_gemm",
            {
                "public_context": public_context,
                "lhs": lhs,
                "rhs": rhs,
            },
        )

    def approx_plan_mul(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs: RepresentativeApproxInput,
        rhs: RepresentativeApproxInput,
        lhs_abs_bound: float,
        rhs_abs_bound: float,
        lhs_abs_error: float,
        rhs_abs_error: float,
        validity_budget: int,
    ) -> tc.OpRef:
        return self._post(
            "/chart/approx/plan_mul",
            {
                "public_context": public_context,
                "lhs": lhs,
                "rhs": rhs,
                "lhs_abs_bound": lhs_abs_bound,
                "rhs_abs_bound": rhs_abs_bound,
                "lhs_abs_error": lhs_abs_error,
                "rhs_abs_error": rhs_abs_error,
                "validity_budget": validity_budget,
            },
        )

    def approx_plan_gemm(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs: RepresentativeApproxInput,
        rhs: RepresentativeApproxInput,
        lhs_abs_bound: float,
        rhs_abs_bound: float,
        lhs_abs_error: float,
        rhs_abs_error: float,
        validity_budget: int,
    ) -> tc.OpRef:
        return self._post(
            "/chart/approx/plan_gemm",
            {
                "public_context": public_context,
                "lhs": lhs,
                "rhs": rhs,
                "lhs_abs_bound": lhs_abs_bound,
                "rhs_abs_bound": rhs_abs_bound,
                "lhs_abs_error": lhs_abs_error,
                "rhs_abs_error": rhs_abs_error,
                "validity_budget": validity_budget,
            },
        )


class ILCClient(Library):
    """Local ILC evaluator wrapper for chart representative operations."""

    publisher = PUBLISHER
    name = CLIENT_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_LOCAL_AUTHORITY)
    dependencies = (URI.parse(DEFAULT_SERVER_LIBRARY_ROOT),)

    @property
    def route_root(self) -> str:
        return self.id().path

    def _post(self, path: str, body: dict[str, Any]) -> tc.OpRef:
        return tc.OpRef("POST", f"{self.route_root}{path}", body=body)

    def add(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs_ciphertext: RepresentativeCiphertext,
        rhs_ciphertext: RepresentativeCiphertext,
    ) -> tc.OpRef:
        return self._post(
            "/chart/add",
            {
                "public_context": public_context,
                "lhs_ciphertext": lhs_ciphertext,
                "rhs_ciphertext": rhs_ciphertext,
            },
        )

    def exact_mul(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs_ciphertext: RepresentativeCiphertext,
        rhs_ciphertext: RepresentativeCiphertext,
        witness: RepresentativeCiphertext,
    ) -> tc.OpRef:
        return self._post(
            "/chart/exact/mul",
            {
                "public_context": public_context,
                "lhs_ciphertext": lhs_ciphertext,
                "rhs_ciphertext": rhs_ciphertext,
                "witness": witness,
            },
        )

    def exact_gemm(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs_ciphertext: RepresentativeCiphertext,
        rhs_ciphertext: RepresentativeCiphertext,
        witness: RepresentativeCiphertext,
    ) -> tc.OpRef:
        return self._post(
            "/chart/exact/gemm",
            {
                "public_context": public_context,
                "lhs_ciphertext": lhs_ciphertext,
                "rhs_ciphertext": rhs_ciphertext,
                "witness": witness,
            },
        )

    def approx_mul(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs_approx: RepresentativeApproxTensor,
        rhs_approx: RepresentativeApproxTensor,
        witness_approx: RepresentativeApproxTensor,
    ) -> tc.OpRef:
        return self._post(
            "/chart/approx/mul",
            {
                "public_context": public_context,
                "lhs_approx": lhs_approx,
                "rhs_approx": rhs_approx,
                "witness_approx": witness_approx,
            },
        )

    def approx_gemm(
        self,
        *,
        public_context: RepresentativePublicContext,
        lhs_approx: RepresentativeApproxTensor,
        rhs_approx: RepresentativeApproxTensor,
        witness_approx: RepresentativeApproxTensor,
    ) -> tc.OpRef:
        return self._post(
            "/chart/approx/gemm",
            {
                "public_context": public_context,
                "lhs_approx": lhs_approx,
                "rhs_approx": rhs_approx,
                "witness_approx": witness_approx,
            },
        )
