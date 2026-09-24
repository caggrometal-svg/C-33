"""Strict infrastructure configuration for C-33 deployments."""

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
    """Validated environment required by Render and Railway."""

    port: int
    database_url: str | None
    secret_keys: tuple[str, ...]
    model_name: str
    model_base_url: str
    model_api_key: str | None
    environment: str
    network_timeout_seconds: float


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
        raise ConfigurationError(
            "DATABASE_URL must be a PostgreSQL URL using postgres:// or postgresql://"
        )
    return value


def _required_secret_keys() -> tuple[str, ...]:
    raw = _required_text("SECRET_KEYS")
    values: list[str]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        values = [str(item).strip() for item in parsed]
    else:
        values = [item.strip() for item in raw.split(",")]

    values = [item for item in values if item]
    if not values:
        raise ConfigurationError("SECRET_KEYS must contain at least one key")

    short_keys = [item for item in values if len(item) < 16]
    if short_keys:
        raise ConfigurationError("Every SECRET_KEYS value must contain at least 16 characters")

    return tuple(dict.fromkeys(values))


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def load_infrastructure_config(dotenv_path: str | None = ".env") -> InfrastructureConfig:
    """Load and validate deployment settings; PostgreSQL is optional for stateless edge mode."""
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)

    model_api_key = (
        os.getenv("MODEL_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or None
    )
    model_base_url = os.getenv("MODEL_BASE_URL", "").strip().rstrip("/")
    if not model_base_url and model_api_key:
        model_base_url = "https://api.openai.com/v1"

    model_name = os.getenv("MODEL_NAME", "").strip()
    if model_api_key and not model_name:
        raise ConfigurationError("MODEL_NAME is required when an AI API key is configured")

    return InfrastructureConfig(
        port=_required_port(),
        database_url=_optional_database_url(),
        secret_keys=_required_secret_keys(),
        model_name=model_name,
        model_base_url=model_base_url,
        model_api_key=model_api_key,
        environment=os.getenv("APP_ENV", "production").strip() or "production",
        network_timeout_seconds=_positive_float("NETWORK_TIMEOUT_SECONDS", 30.0),
    )
