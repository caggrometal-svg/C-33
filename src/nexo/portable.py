"""Portable NEXO data bundle contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "nexo.bundle.v1"


class PortableBundleError(ValueError):
    pass


def export_bundle(*, user_id: str, messages: list[dict[str, Any]], memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    uid = user_id.strip()
    if not uid:
        raise PortableBundleError("user_id_required")
    clean_messages = [dict(item) for item in messages if isinstance(item, dict)]
    clean_memory = [dict(item) for item in (memory or []) if isinstance(item, dict)]
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": uid,
        "messages": clean_messages,
        "memory": clean_memory,
    }


def validate_bundle(bundle: Any) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(bundle, dict):
        return False, ("bundle_not_object",)
    warnings: list[str] = []
    if bundle.get("schema_version") != SCHEMA_VERSION:
        warnings.append("unsupported_schema_version")
    if not str(bundle.get("user_id", "")).strip():
        warnings.append("user_id_required")
    for key in ("messages", "memory"):
        if not isinstance(bundle.get(key, []), list):
            warnings.append(f"{key}_must_be_list")
    return not warnings, tuple(warnings)
