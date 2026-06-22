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
    """Canonical setup context shape returned by the server and passed to secret routes."""

    version: int
    alg: str
    kid: str | None
    payload_b64: str
    signature_b64: str


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
        secret_metric: list[int],
        payload_dims: int,
        nonce_dims: int,
        nonce_bound: int,
        salt_hex: str | None = None,
    ) -> object:
        return self._post(
            "/setup",
            {
                "params": params,
                "secret_metric": secret_metric,
                "payload_dims": payload_dims,
                "nonce_dims": nonce_dims,
                "nonce_bound": nonce_bound,
                "salt_hex": salt_hex,
            },
        )

    def encrypt(
        self,
        *,
        context: CipherContext,
        payload: list[int],
        budget_log2: int | None = None,
    ) -> object:
        body: dict[str, object] = {
            "context": context,
            "payload": payload,
        }
        if budget_log2 is not None:
            body["budget_log2"] = budget_log2
        return self._post("/encrypt", body)

    def decrypt(
        self,
        *,
        context: CipherContext,
        ciphertext: dict[str, Any],
    ) -> object:
        return self._post(
            "/decrypt",
            {
                "context": context,
                "ciphertext": ciphertext,
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
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
    ) -> object:
        return self._get("/chart/exact/mul", {"metric": metric, "lhs": lhs, "rhs": rhs})

    def gemm(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
        lhs_rows: int,
        lhs_cols: int,
        rhs_cols: int,
    ) -> object:
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
