from __future__ import annotations

from typing import Any, TypeAlias, TypedDict

import tinychain.executor as tc_executor
from tinychain.library import Library
from tinychain.opref import OpRef, get as op_get, post as op_post
from tinychain.uri import URI

from .config import (
    DEFAULT_LOCAL_AUTHORITY,
    DEFAULT_SERVER_AUTHORITY,
    DEFAULT_SERVER_LIBRARY_ROOT,
    DEFAULT_VERSION,
    PUBLISHER,
)

Metric: TypeAlias = list[int]
Ciphertext: TypeAlias = list[float]


def _maybe_execute(op: OpRef) -> object:
    executor = tc_executor.try_current()
    if executor is not None and executor.is_eager():
        return executor.execute(op)
    return op


class CipherContext(TypedDict):
    """Compatibility wrapper for callers that pass a setup public context as a map."""

    public_context: dict[str, Any]


class ILCServer(Library):
    """Remote ILC server wrapper for authenticated encrypt/decrypt routes."""

    publisher = PUBLISHER
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_SERVER_AUTHORITY)

    @property
    def route_root(self) -> str:
        return self.id().path

    def _post(self, path: str, body: dict[str, Any]) -> object:
        return _maybe_execute(op_post(f"{self.route_root}{path}", body=body))

    def setup(
        self,
        *,
        params: dict[str, Any],
        payload_dims: int,
        nonce_dims: int = 0,
        representative_dims: int | None = None,
        metric_policy: str = "public-client-default",
        admitted_ops: list[str] | None = None,
        payload_budget_log2: int | None = None,
    ) -> object:
        body: dict[str, object] = {
            "params": params,
            "payload_dims": payload_dims,
            "representative_dims": representative_dims or payload_dims + nonce_dims,
            "metric_policy": metric_policy,
            "admitted_ops": admitted_ops or ["add"],
        }
        if payload_budget_log2 is not None:
            body["payload_budget_log2"] = payload_budget_log2
        return self._post("/chart/setup", body)

    def encrypt(
        self,
        *,
        context: CipherContext | None = None,
        public_context: dict[str, Any] | None = None,
        payload: list[int],
        shape: list[int] | None = None,
        budget_log2: int | None = None,
    ) -> object:
        if public_context is None and context is not None:
            public_context = context.get("public_context")  # type: ignore[assignment]
        if public_context is None:
            raise ValueError("encrypt requires public_context")
        body: dict[str, object] = {
            "public_context": public_context,
            "payload": payload,
        }
        if shape is not None:
            body["shape"] = shape
        if budget_log2 is not None:
            body["budget_log2"] = budget_log2
        return self._post("/chart/encrypt", body)

    def decrypt(
        self,
        *,
        context: CipherContext | None = None,
        public_context: dict[str, Any] | None = None,
        ciphertext: dict[str, Any],
        handle: dict[str, Any] | None = None,
    ) -> object:
        if public_context is None and context is not None:
            public_context = context.get("public_context")  # type: ignore[assignment]
        if public_context is None:
            raise ValueError("decrypt requires public_context")
        if handle is None:
            raise ValueError("decrypt requires handle")
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
        public_context: dict[str, Any],
        op: str,
        input_handles: list[dict[str, Any]],
    ) -> object:
        return self._post(
            "/chart/record_eval",
            {
                "public_context": public_context,
                "op": op,
                "input_handles": input_handles,
            },
        )


class ILCClient(Library):
    """Local ILC evaluator wrapper for ciphertext-domain add/mul/gemm routes."""

    publisher = PUBLISHER
    version = DEFAULT_VERSION
    dependencies = (URI.parse(DEFAULT_SERVER_LIBRARY_ROOT),)
    authority = URI.parse(DEFAULT_LOCAL_AUTHORITY)

    def bind_server(
        self,
        server: ILCServer | URI | str | None = None,
    ) -> "ILCClient":
        if server is None:
            self.server = ILCServer()
        elif isinstance(server, ILCServer):
            self.server = server
        elif isinstance(server, URI):
            self.server = ILCServer(authority=server)
        else:
            self.server = ILCServer(authority=URI.parse(server))
        return self

    @property
    def route_root(self) -> str:
        return self.id().path

    def _get(self, path: str, body: dict[str, Any]) -> object:
        return _maybe_execute(op_get(f"{self.route_root}{path}", body=body))

    def add(
        self,
        *,
        metric: Metric | None = None,
        lhs: Ciphertext | None = None,
        rhs: Ciphertext | None = None,
        public_context: dict[str, Any] | None = None,
        lhs_ciphertext: dict[str, Any] | None = None,
        rhs_ciphertext: dict[str, Any] | None = None,
    ) -> object:
        if public_context is not None or lhs_ciphertext is not None or rhs_ciphertext is not None:
            return self._get(
                "/chart/add",
                {
                    "public_context": public_context,
                    "lhs_ciphertext": lhs_ciphertext,
                    "rhs_ciphertext": rhs_ciphertext,
                },
            )
        return self._get(
            "/chart/add",
            {"metric": metric or [], "lhs": lhs or [], "rhs": rhs or []},
        )

    def mul(
        self,
        *,
        metric: Metric | None = None,
        lhs: Ciphertext | None = None,
        rhs: Ciphertext | None = None,
        public_context: dict[str, Any] | None = None,
        lhs_ciphertext: dict[str, Any] | None = None,
        rhs_ciphertext: dict[str, Any] | None = None,
        witness: dict[str, Any] | None = None,
        lhs_approx: dict[str, Any] | None = None,
        rhs_approx: dict[str, Any] | None = None,
        witness_approx: dict[str, Any] | None = None,
    ) -> object:
        if public_context is not None and lhs_approx is not None:
            return self._get(
                "/chart/approx/mul",
                {
                    "public_context": public_context,
                    "lhs_approx": lhs_approx,
                    "rhs_approx": rhs_approx,
                    "witness_approx": witness_approx,
                },
            )
        if public_context is not None:
            return self._get(
                "/chart/exact/mul",
                {
                    "public_context": public_context,
                    "lhs_ciphertext": lhs_ciphertext,
                    "rhs_ciphertext": rhs_ciphertext,
                    "witness": witness,
                },
            )
        return self._get("/chart/approx/mul", {"metric": metric, "lhs": lhs, "rhs": rhs})

    def gemm(
        self,
        *,
        metric: Metric | None = None,
        lhs: Ciphertext | None = None,
        rhs: Ciphertext | None = None,
        lhs_rows: int | None = None,
        lhs_cols: int | None = None,
        rhs_cols: int | None = None,
        public_context: dict[str, Any] | None = None,
        lhs_ciphertext: dict[str, Any] | None = None,
        rhs_ciphertext: dict[str, Any] | None = None,
        witness: dict[str, Any] | None = None,
        lhs_approx: dict[str, Any] | None = None,
        rhs_approx: dict[str, Any] | None = None,
        witness_approx: dict[str, Any] | None = None,
    ) -> object:
        if public_context is not None and lhs_approx is not None:
            return self._get(
                "/chart/approx/gemm",
                {
                    "public_context": public_context,
                    "lhs_approx": lhs_approx,
                    "rhs_approx": rhs_approx,
                    "witness_approx": witness_approx,
                },
            )
        if public_context is not None:
            return self._get(
                "/chart/exact/gemm",
                {
                    "public_context": public_context,
                    "lhs_ciphertext": lhs_ciphertext,
                    "rhs_ciphertext": rhs_ciphertext,
                    "witness": witness,
                },
            )
        return self._get(
            "/chart/exact/gemm",
            {
                "metric": metric,
                "lhs": lhs,
                "rhs": rhs,
                "lhs_rows": int(lhs_rows),
                "lhs_cols": int(lhs_cols),
                "rhs_cols": int(rhs_cols),
            },
        )
