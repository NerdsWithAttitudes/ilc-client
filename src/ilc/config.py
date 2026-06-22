from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Package/version defaults
DEFAULT_VERSION = "0.1.0"
PUBLISHER = "applied-physics"
CLIENT_NAME = "ilc_client"
SERVER_NAME = "ilc_server"

# Common authorities
ENV_ILC_LOCAL_AUTHORITY = "ILC_LOCAL_AUTHORITY"
ENV_ILC_SERVER_AUTHORITY = "ILC_SERVER_AUTHORITY"
DEFAULT_LOCAL_AUTHORITY = os.environ.get(ENV_ILC_LOCAL_AUTHORITY, "http://127.0.0.1:8700")
DEFAULT_SERVER_AUTHORITY = os.environ.get(ENV_ILC_SERVER_AUTHORITY, "https://api.tctest.net")

# Service metadata
def server_library_root(version: str = DEFAULT_VERSION) -> str:
    return f"/lib/{PUBLISHER}/{SERVER_NAME}/{version}"


def client_library_root(version: str = DEFAULT_VERSION) -> str:
    return f"/lib/{PUBLISHER}/{CLIENT_NAME}/{version}"


DEFAULT_SERVER_LIBRARY_ROOT = server_library_root()
DEFAULT_CLIENT_LIBRARY_ROOT = client_library_root()
_SERVICE_ADMIN_DOMAIN = "appliedphysics.org"
SERVICE_ADMIN_EMAIL = "haydn" + "@" + _SERVICE_ADMIN_DOMAIN

# Local runtime artifact path (never committed to this repo)
ENV_ILC_CLIENT_WASM_PATH = "ILC_CLIENT_WASM_PATH"
ENV_ILC_CLIENT_WASM_SHA256 = "ILC_CLIENT_WASM_SHA256"
DEFAULT_CLIENT_WASM_PATH = Path(
    os.environ.get(ENV_ILC_CLIENT_WASM_PATH, "artifacts/cipher_wasm.wasm")
)

# TinyChain auth env vars used by helpers/examples.
ENV_TC_BEARER_TOKEN = "TC_BEARER_TOKEN"
ENV_TC_INSTALL_BEARER_TOKEN = "TC_INSTALL_BEARER_TOKEN"
ENV_TC_PUBLIC_KEY_B64 = "TC_PUBLIC_KEY_B64"
ENV_TC_TOKEN_HOST = "TC_TOKEN_HOST"
ENV_TC_ACTOR_ID = "TC_ACTOR_ID"

# Default local compute parameters used by scalar helper methods.
DEFAULT_COMPUTE_METRIC: tuple[int, ...] = (3, 5)
@dataclass(frozen=True)
class ComputeDefaults:
    metric: tuple[int, ...] = DEFAULT_COMPUTE_METRIC


DEFAULT_COMPUTE = ComputeDefaults()
