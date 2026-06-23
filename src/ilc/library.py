from __future__ import annotations

from typing import Any

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

def _maybe_execute(op: OpRef) -> object:
    executor = tc_executor.try_current()
    if executor is not None and executor.is_eager():
        return executor.execute(op)
    return op


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
        public_context: dict[str, Any],
        payload: list[int],
        shape: list[int] | None = None,
        budget_log2: int | None = None,
    ) -> object:
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
        public_context: dict[str, Any],
        ciphertext: dict[str, Any],
        handle: dict[str, Any] | None = None,
    ) -> object:
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
        public_context: dict[str, Any],
        lhs_ciphertext: dict[str, Any],
        rhs_ciphertext: dict[str, Any],
    ) -> object:
        return self._get(
            "/chart/add",
            {
                "public_context": public_context,
                "lhs_ciphertext": lhs_ciphertext,
                "rhs_ciphertext": rhs_ciphertext,
            },
        )

    def mul(
        self,
        *,
        public_context: dict[str, Any],
        lhs_ciphertext: dict[str, Any] | None = None,
        rhs_ciphertext: dict[str, Any] | None = None,
        witness: dict[str, Any] | None = None,
        lhs_approx: dict[str, Any] | None = None,
        rhs_approx: dict[str, Any] | None = None,
        witness_approx: dict[str, Any] | None = None,
    ) -> object:
        if lhs_approx is not None:
            return self._get(
                "/chart/approx/mul",
                {
                    "public_context": public_context,
                    "lhs_approx": lhs_approx,
                    "rhs_approx": rhs_approx,
                    "witness_approx": witness_approx,
                },
            )
        return self._get(
            "/chart/exact/mul",
            {
                "public_context": public_context,
                "lhs_ciphertext": lhs_ciphertext,
                "rhs_ciphertext": rhs_ciphertext,
                "witness": witness,
            },
        )

    def gemm(
        self,
        *,
        public_context: dict[str, Any],
        lhs_ciphertext: dict[str, Any] | None = None,
        rhs_ciphertext: dict[str, Any] | None = None,
        witness: dict[str, Any] | None = None,
        lhs_approx: dict[str, Any] | None = None,
        rhs_approx: dict[str, Any] | None = None,
        witness_approx: dict[str, Any] | None = None,
    ) -> object:
        if lhs_approx is not None:
            return self._get(
                "/chart/approx/gemm",
                {
                    "public_context": public_context,
                    "lhs_approx": lhs_approx,
                    "rhs_approx": rhs_approx,
                    "witness_approx": witness_approx,
                },
            )
        return self._get(
            "/chart/exact/gemm",
            {
                "public_context": public_context,
                "lhs_ciphertext": lhs_ciphertext,
                "rhs_ciphertext": rhs_ciphertext,
                "witness": witness,
            },
        )
