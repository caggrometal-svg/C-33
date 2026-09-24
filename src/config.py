"""Strict production configuration for C-33/NEXO."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

class ConfigurationError(ValueError):
    """Raised when a required deployment variable is missing or invalid."""

@dataclass(frozen=True, slots=True)
class InfrastructureConfig:
    port: int
    database_url: str | None
    secret_keys: tuple[str, ...]
    model_name: str
    model_base_url: str
    model_api_key: str | None
    environment: str
    role: str
    backend_total_timeout_ms: int
    client_timeout_ms: int
    network_timeout_seconds: float
    peer_url: str | None
    peer_replication_secret: str | None
    local_fallback_enabled: bool
    require_provider_redundancy: bool

def _required_text(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value

def _required_port() -> int:
    raw = _required_text("PORT")
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigurationError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError("PORT must be between 1 and 65535")
    return port

def _optional_database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.netloc:
        raise ConfigurationError("DATABASE_URL must be a PostgreSQL URL")
    return value

def _required_secret_keys() -> tuple[str, ...]:
    raw = _required_text("SECRET_KEYS")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    values = [str(item).strip() for item in parsed] if isinstance(parsed, list) else [x.strip() for x in raw.split(",")]
    values = [x for x in values if x]
    if not values or any(len(x) < 16 for x in values):
        raise ConfigurationError("SECRET_KEYS must contain keys with at least 16 characters")
    return tuple(dict.fromkeys(values))

def _positive_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return value

def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be > 0")
    return value

def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}: return True
    if value in {"0", "false", "no", "off"}: return False
    raise ConfigurationError(f"{name} must be boolean")

def load_infrastructure_config(dotenv_path: str | None = ".env") -> InfrastructureConfig:
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    model_api_key = os.getenv("MODEL_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip() or None
    model_base_url = os.getenv("MODEL_BASE_URL", "https://vireonix.ai/v1").strip().rstrip("/")
    model_name = os.getenv("MODEL_NAME", "auto").strip() or "auto"
    return InfrastructureConfig(
        port=_required_port(),
        database_url=_optional_database_url(),
        secret_keys=_required_secret_keys(),
        model_name=model_name,
        model_base_url=model_base_url,
        model_api_key=model_api_key,
        environment=os.getenv("APP_ENV", "production").strip() or "production",
        role=os.getenv("C33_ROLE", "primary").strip().lower() or "primary",
        backend_total_timeout_ms=_positive_int("BACKEND_TOTAL_TIMEOUT_MS", 26000, 1000),
        client_timeout_ms=_positive_int("CLIENT_TIMEOUT_MS", 28000, 1000),
        network_timeout_seconds=_positive_float("NETWORK_TIMEOUT_SECONDS", 8.0),
        peer_url=os.getenv("PEER_BACKEND_URL", "").strip().rstrip("/") or None,
        peer_replication_secret=os.getenv("PEER_REPLICATION_SECRET", "").strip() or None,
        local_fallback_enabled=_bool("LOCAL_FALLBACK_ENABLED", True),
        require_provider_redundancy=_bool("REQUIRE_PROVIDER_REDUNDANCY", True),
    )
