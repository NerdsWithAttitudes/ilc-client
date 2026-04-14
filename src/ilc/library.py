from __future__ import annotations

from typing import Any, TypeAlias

import tinychain as tc
from tinychain.executor import try_current
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
    server_library_root,
)

Metric: TypeAlias = list[int]
Ciphertext: TypeAlias = list[float]
CiphertextResponse: TypeAlias = dict[str, list[float]]


class ILCServer(Library):
    """Remote ILC server wrapper for authenticated encrypt/decrypt routes."""

    publisher = PUBLISHER
    name = SERVER_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_SERVER_AUTHORITY)

    @classmethod
    def with_authority(cls, authority: str, *, version: str = DEFAULT_VERSION) -> "ILCServer":
        return cls(version=version, authority=URI.parse(authority))

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

    def encrypt(self, *, payload: list[int], budget_log2: int | None = None) -> tc.OpRef:
        body: dict[str, object] = {"payload": payload}
        if budget_log2 is not None:
            body["budget_log2"] = budget_log2
        return self._post("/encrypt", body)

    def decrypt(self, *, ciphertext: dict[str, Any]) -> tc.OpRef:
        return self._post("/decrypt", {"ciphertext": ciphertext})


class ILCClient(Library):
    """Local ILC evaluator wrapper for ciphertext-domain add/mul/gemm routes."""

    publisher = PUBLISHER
    name = CLIENT_NAME
    version = DEFAULT_VERSION
    authority = URI.parse(DEFAULT_LOCAL_AUTHORITY)
    dependencies = (URI.parse(DEFAULT_SERVER_LIBRARY_ROOT),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not kwargs.get("dependencies"):
            dep_version = self.version
            object.__setattr__(
                self,
                "dependencies",
                (URI.parse(server_library_root(dep_version)),),
            )

    @classmethod
    def with_authority(cls, authority: str, *, version: str = DEFAULT_VERSION) -> "ILCClient":
        return cls(version=version, authority=URI.parse(authority))

    @property
    def route_root(self) -> str:
        return self.id().path

    def _get(self, path: str, body: dict[str, Any]) -> tc.OpRef:
        return tc.OpRef("GET", f"{self.route_root}{path}", body=body)

    @staticmethod
    def _dispatch(op: tc.OpRef) -> CiphertextResponse | tc.OpRef:
        if isinstance(op.path, str) and op.path.startswith("http"):
            uri = URI.parse(op.path)
            op = tc.OpRef(op.method, uri.path, op.headers, op.body)

        executor = try_current()
        if executor is not None:
            should_auto = getattr(executor, "should_auto_execute", None)
            if callable(should_auto):
                auto = bool(should_auto())
            else:
                auto = bool(getattr(executor, "auto_execute", True))

            if not auto:
                return op

        return tc.execute(op)

    def add(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
    ) -> CiphertextResponse | tc.OpRef:
        op = self._get("/add", {"metric": metric, "lhs": lhs, "rhs": rhs})
        return self._dispatch(op)

    def mul(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
    ) -> CiphertextResponse | tc.OpRef:
        op = self._get("/mul", {"metric": metric, "lhs": lhs, "rhs": rhs})
        return self._dispatch(op)

    def gemm(
        self,
        *,
        metric: Metric,
        lhs: Ciphertext,
        rhs: Ciphertext,
        lhs_rows: int,
        lhs_cols: int,
        rhs_cols: int,
    ) -> CiphertextResponse | tc.OpRef:
        op = self._get(
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
        return self._dispatch(op)
