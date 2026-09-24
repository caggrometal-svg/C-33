"""Centralized application configuration for C-33."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime configuration loaded from environment variables."""

    app_name: str
    environment: str
    host: str
    port: int
    agent_max_steps: int
    network_timeout_seconds: float
    search_max_results: int
    model_base_url: str
    model_api_key: str | None
    model_name: str
    model_temperature: float
    memory_file: str
    short_term_limit: int
    long_term_limit: int


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Read and validate a positive integer environment variable."""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _env_float(name: str, default: float, *, minimum: float = 0.1) -> float:
    """Read and validate a floating-point environment variable."""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def load_settings(dotenv_path: str | None = ".env") -> Settings:
    """Load .env values and return a validated immutable settings object."""
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)

    api_key = os.getenv("MODEL_API_KEY", "").strip() or None
    model_base_url = os.getenv("MODEL_BASE_URL", "").strip().rstrip("/")

    return Settings(
        app_name=os.getenv("APP_NAME", "C-33").strip() or "C-33",
        environment=os.getenv("APP_ENV", "development").strip() or "development",
        host=os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_env_int("PORT", 8000),
        agent_max_steps=_env_int("AGENT_MAX_STEPS", 8),
        network_timeout_seconds=_env_float("NETWORK_TIMEOUT_SECONDS", 15.0),
        search_max_results=_env_int("SEARCH_MAX_RESULTS", 5),
        model_base_url=model_base_url,
        model_api_key=api_key,
        model_name=os.getenv("MODEL_NAME", "").strip(),
        model_temperature=_env_float("MODEL_TEMPERATURE", 0.2, minimum=0.0),
        memory_file=os.getenv("MEMORY_FILE", "data/memory.json").strip()
        or "data/memory.json",
        short_term_limit=_env_int("SHORT_TERM_LIMIT", 8),
        long_term_limit=_env_int("LONG_TERM_LIMIT", 12),
    )
