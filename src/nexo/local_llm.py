"""Real local-LLM adapter for OpenAI-compatible runtimes."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class LocalLLMConfigurationError(ValueError):
    pass


class LocalLLMUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LocalLLMConfig:
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "llama3.2:3b"
    api_key_env: str | None = None
    timeout_ms: int = 6000

    @classmethod
    def from_environment(cls) -> "LocalLLMConfig":
        base_url = os.getenv("C33_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip().rstrip("/")
        model = os.getenv("C33_LOCAL_LLM_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"
        api_key_env = os.getenv("C33_LOCAL_LLM_API_KEY_ENV", "").strip() or None
        try:
            timeout_ms = int(os.getenv("C33_LOCAL_LLM_TIMEOUT_MS", "6000"))
        except ValueError as exc:
            raise LocalLLMConfigurationError("C33_LOCAL_LLM_TIMEOUT_MS must be an integer") from exc
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LocalLLMConfigurationError("C33_LOCAL_LLM_BASE_URL must be an http(s) URL")
        if not model:
            raise LocalLLMConfigurationError("C33_LOCAL_LLM_MODEL is required")
        if not 500 <= timeout_ms <= 30000:
            raise LocalLLMConfigurationError("C33_LOCAL_LLM_TIMEOUT_MS must be between 500 and 30000")
        return cls(base_url, model, api_key_env, timeout_ms)

    @property
    def enabled(self) -> bool:
        return bool(os.getenv("C33_LOCAL_LLM_BASE_URL", "").strip())


class LocalLLMClient:
    """Concrete local inference client; no deterministic fallback is hidden here."""

    def __init__(self, config: LocalLLMConfig | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.config = config or LocalLLMConfig.from_environment()
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.api_key_env:
            value = os.getenv(self.config.api_key_env, "").strip()
            if value:
                headers["Authorization"] = "Bearer " + value
        return headers

    async def probe(self) -> dict[str, object]:
        started = time.monotonic()
        if not self.config.enabled:
            return {
                "status": "disabled",
                "provider": "local",
                "model": self.config.model,
                "available": False,
                "reason": "C33_LOCAL_LLM_BASE_URL_not_set",
            }
        timeout = max(0.5, min(3.0, self.config.timeout_ms / 1000))
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=min(1.0, timeout)),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.get(self.config.base_url + "/models", headers=self._headers())
            ok = 200 <= response.status_code < 300
            return {
                "status": "ready" if ok else "unavailable",
                "provider": "local",
                "model": self.config.model,
                "available": ok,
                "http_status": response.status_code,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        except (httpx.HTTPError, OSError) as exc:
            return {
                "status": "unavailable",
                "provider": "local",
                "model": self.config.model,
                "available": False,
                "reason": type(exc).__name__,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }

    async def complete(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, object]]:
        if not self.config.enabled:
            raise LocalLLMUnavailable("local_llm_not_configured")
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_ms / 1000, connect=min(2.0, self.config.timeout_ms / 1000)),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    self.config.base_url + "/chat/completions",
                    headers=self._headers(),
                    json={"model": self.config.model, "messages": messages, "stream": False},
                )
            if response.status_code != 200:
                raise LocalLLMUnavailable(f"local_llm_http_{response.status_code}")
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise LocalLLMUnavailable("local_llm_empty_response")
            return text.strip(), {
                "provider_used": "local",
                "model": self.config.model,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "system_status": "AI_READY",
                "local_runtime": self.config.base_url,
            }
        except LocalLLMUnavailable:
            raise
        except (httpx.HTTPError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LocalLLMUnavailable("local_llm_transport_or_response_error") from exc
