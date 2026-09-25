"""Centralized application configuration for C-33."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_DEBATE_SYSTEM_PROMPT = """C-33 DEBATE AND REASONING RULES:
- Anti-sycophancy: never agree merely to please the user; challenge weak or unsupported premises with reasons and evidence.
- Steelman: present the strongest defensible version of relevant opposing positions before synthesis.
- Dialectic: use Thesis, Antithesis, and Synthesis for substantive contested analysis when useful.
- Analytical freedom with rigor: examine historical, sociological, economic, scientific, philosophical, and political claims using evidence and explicit inference rather than ideological slogans.
- Fallacy detection: identify actual logical fallacies such as ad hominem, false dilemma, hasty generalization, straw man, circular reasoning, or appeal to authority.
- Evidence symmetry: seek credible supporting and counter-evidence; do not manufacture balance when evidence quality is asymmetric.
- Epistemic discipline: distinguish facts, attributed claims, interpretations, hypotheses, and uncertainty; never invent evidence.
- Higher-priority safety and lawful-operation constraints remain applicable.
"""


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

    # FREE mode: model credentials are intentionally ignored.
    api_key = None
    model_base_url = os.getenv("MODEL_BASE_URL", "https://vireonix.ai/v1").strip().rstrip("/")
    return Settings(
        app_name=os.getenv("APP_NAME", "C-33").strip() or "C-33",
        environment=os.getenv("APP_ENV", "development").strip() or "development",
        host=os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_env_int("PORT", 8000),
        agent_max_steps=_env_int("AGENT_MAX_STEPS", 8),
        network_timeout_seconds=_env_float("NETWORK_TIMEOUT_SECONDS", 45.0),
        search_max_results=_env_int("SEARCH_MAX_RESULTS", 5),
        model_base_url=model_base_url,
        model_api_key=api_key,
        model_name=os.getenv("MODEL_NAME", "auto").strip(),
        model_temperature=_env_float("MODEL_TEMPERATURE", 0.2, minimum=0.0),
        memory_file=os.getenv("MEMORY_FILE", "data/memory.json").strip()
        or "data/memory.json",
        short_term_limit=_env_int("SHORT_TERM_LIMIT", 8),
        long_term_limit=_env_int("LONG_TERM_LIMIT", 12),
    )
