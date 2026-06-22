from __future__ import annotations

from typing import Any, TypeAlias, TypedDict

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

Metric: TypeAlias = list[int]
Ciphertext: TypeAlias = list[float]


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
        secret_metric: list[int],
        payload_dims: int,
        nonce_dims: int,
        nonce_bound: int,
        salt_hex: str | None = None,
    ) -> tc.OpRef:
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
    ) -> tc.OpRef:
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
    ) -> tc.OpRef:
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
    name = CLIENT_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_LOCAL_AUTHORITY)
    dependencies = (URI.parse(DEFAULT_SERVER_LIBRARY_ROOT),)

    @property
    def route_root(self) -> str:
        return self.id().path

    def _get(self, path: str, body: dict[str, Any]) -> tc.OpRef:
        return tc.OpRef("GET", f"{self.route_root}{path}", body=body)

    def add(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
    ) -> tc.OpRef:
        return self._get("/add", {"metric": metric, "lhs": lhs, "rhs": rhs})

    def mul(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
    ) -> tc.OpRef:
        return self._get("/mul", {"metric": metric, "lhs": lhs, "rhs": rhs})

    def gemm(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
        lhs_rows: int,
        lhs_cols: int,
        rhs_cols: int,
    ) -> tc.OpRef:
        return self._get(
            "/gemm",
            {
                "metric": metric,
                "lhs": lhs,
                "rhs": rhs,
                "lhs_rows": int(lhs_rows),
                "lhs_cols": int(lhs_cols),
                "rhs_cols": int(rhs_cols),
            },
        )
