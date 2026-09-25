"""Portable NEXO data bundle contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import hashlib
import json

SCHEMA_VERSION = "nexo.bundle.v1"


def bundle_digest(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("sha256", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class PortableBundleError(ValueError):
    pass


def export_bundle(*, user_id: str, messages: list[dict[str, Any]], memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    uid = user_id.strip()
    if not uid:
        raise PortableBundleError("user_id_required")
    clean_messages = [dict(item) for item in messages if isinstance(item, dict)]
    clean_memory = [dict(item) for item in (memory or []) if isinstance(item, dict)]
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": uid,
        "messages": clean_messages,
        "memory": clean_memory,
    }
    bundle["sha256"] = bundle_digest(bundle)
    return bundle


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
    digest = bundle.get("sha256")
    if not isinstance(digest, str) or digest != bundle_digest(bundle):
        warnings.append("checksum_mismatch")
    return not warnings, tuple(warnings)
