from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_real_provenance(
    *,
    provider: str,
    source_url: str | None = None,
    version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "provider": provider,
        "mode": "real",
        "retrieved_at": utc_timestamp(),
    }
    if source_url:
        provenance["source_url"] = source_url
    if version:
        provenance["version"] = version
    if extra:
        provenance.update(extra)
    return provenance


def build_fallback_provenance(
    *,
    provider: str,
    warning: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "provider": provider,
        "mode": "fallback",
        "retrieved_at": utc_timestamp(),
        "warning": warning,
    }
    if extra:
        provenance.update(extra)
    return provenance
