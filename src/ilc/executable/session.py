"""Provider session contracts and public config fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProviderSession(Protocol):
    """Public session metadata shared by executable providers."""

    @property
    def provider_id(self) -> str:
        ...

    @property
    def session_id(self) -> str:
        ...

    @property
    def config_fingerprint(self) -> str:
        ...


def compute_fingerprint(provider_id: str, payload: Any) -> str:
    """Return a stable key-free fingerprint for public provider config."""

    normalized = _normalize(payload)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{provider_id}:v1:{digest}"


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


@dataclass(frozen=True)
class BasicSession:
    """Simple public session value for lightweight providers."""

    provider_id: str
    session_id: str
    config_fingerprint: str

