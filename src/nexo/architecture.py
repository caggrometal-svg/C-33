"""Architecture contracts for NEXO phases 0.1-20.

These contracts keep tool use, model routing, local fallback, orchestration, and
verification replaceable instead of embedding them in the mobile client.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable

from nexo.tool_policy import ToolCapability, ToolPolicy

Handler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """Deterministic decision about which capabilities a turn may need."""

    use_memory: bool
    use_web: bool
    verify: bool
    reason: str


class ToolHub:
    """Small capability registry decoupled from the model provider."""

    def __init__(self) -> None:
        self._tools: dict[str, Handler] = {}
        self.policy = ToolPolicy()

    def register(self, name: str, handler: Handler, *, network: bool = False, mutates_state: bool = False, risk: str = "low") -> None:
        key = name.strip().lower()
        if not key or not callable(handler):
            raise ValueError("tool name and callable handler are required")
        if key in self._tools:
            raise ValueError(f"tool_already_registered:{key}")
        self._tools[key] = handler
        self.policy.register(ToolCapability(key, network=network, mutates_state=mutates_state, risk=risk))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def describe(self) -> tuple[dict[str, Any], ...]:
        return tuple({
            "name": name,
            "network": bool(self.policy.get(name).network),
            "mutates_state": bool(self.policy.get(name).mutates_state),
            "risk": self.policy.get(name).risk,
        } for name in self.names)

    async def invoke(
        self,
        name: str,
        *args: Any,
        network_allowed: bool = False,
        mutations_allowed: bool = False,
        **kwargs: Any,
    ) -> Any:
        key = name.strip().lower()
        if key not in self._tools:
            raise KeyError(f"unknown_tool:{key}")
        if not self.policy.allows(
            key,
            network_allowed=network_allowed,
            mutations_allowed=mutations_allowed,
        ):
            raise PermissionError(f"tool_not_allowed:{key}")
        result = self._tools[key](*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


@dataclass(frozen=True, slots=True)
class ModelProfile:
    provider_id: str
    model_id: str
    failure_domain: str
    capabilities: tuple[str, ...] = ("chat", "stream")


class ModelHub:
    """Provider-neutral model surface backed by the existing cascade."""

    def __init__(self, cascade: Any) -> None:
        if cascade is None:
            raise ValueError("cascade is required")
        self.cascade = cascade

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(getattr(self.cascade, "configured_provider_ids", []))

    @property
    def profiles(self) -> tuple[ModelProfile, ...]:
        profiles = []
        for spec in getattr(self.cascade, "providers", []):
            profiles.append(ModelProfile(spec.provider_id, spec.model, spec.failure_domain))
        return tuple(profiles)

    def select(self, preferred_provider: str | None = None) -> ModelProfile | None:
        preferred = (preferred_provider or "").strip()
        if preferred:
            for profile in self.profiles:
                if profile.provider_id == preferred:
                    return profile
        return self.profiles[0] if self.profiles else None

    async def complete(self, messages: list[dict[str, str]], budget: Any) -> Any:
        return await self.cascade.complete(messages, budget)

    def stream(self, messages: list[dict[str, str]], budget: Any) -> Any:
        return self.cascade.stream(messages, budget)


class LocalModel:
    """Explicit local responder interface.

    This is intentionally deterministic: it provides a local safety response
    without pretending that a hidden local LLM exists.
    """

    provider_id = "local"
    model_id = "deterministic-local"

    @classmethod
    def complete(cls, prompt: str, reason: str) -> str:
        clean = prompt.strip()
        return (
            "NEXO está operando en respaldo local. "
            "La generación remota no está disponible en este momento "
            f"({reason}). No presentaré este texto como una respuesta de IA remota. "
            f"Consulta recibida: {clean[:200]}"
        )


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    warnings: tuple[str, ...]
    sources: tuple[str, ...]


class VerificationEngine:
    """Structural evidence verifier for web-grounded turns."""

    _citation_re = re.compile(r"\[(\d{1,2})\]")

    def verify_sources(self, sources: list[str]) -> VerificationResult:
        clean = []
        warnings = []
        for source in sources:
            value = str(source or "").strip()
            if not value:
                continue
            if not re.match(r"^https?://", value, flags=re.IGNORECASE):
                warnings.append("non_http_source")
                continue
            if value not in clean:
                clean.append(value)
        if not clean:
            warnings.append("no_external_sources")
        return VerificationResult(not warnings, tuple(warnings), tuple(clean[:5]))

    def verify_response(self, response: str, sources: list[str]) -> VerificationResult:
        source_check = self.verify_sources(sources)
        citations = [int(match) for match in self._citation_re.findall(response or "")]
        warnings = list(source_check.warnings)
        if citations and (min(citations) < 1 or max(citations) > len(source_check.sources)):
            warnings.append("citation_out_of_range")
        if source_check.sources and not citations:
            warnings.append("web_sources_without_inline_citations")
        return VerificationResult(not warnings, tuple(dict.fromkeys(warnings)), source_check.sources)


class NexoOrchestrator:
    """Turn-level planner; it does not generate text."""

    def plan(self, prompt: str, memory_hits: list[Any]) -> RoutePlan:
        lower = prompt.lower().strip()
        explicit_web = (
            lower.startswith("/web ")
            or lower.startswith("web:")
            or "busca en internet" in lower
        )
        web_markers = {
            "latest",
            "today",
            "ahora",
            "actual",
            "actualmente",
            "current",
            "news",
            "noticia",
            "noticias",
            "precio",
            "price",
            "fuente",
            "fuentes",
            "verifica",
            "verificar",
            "comprueba",
            "evidencia",
            "internet",
            "navega",
            "navegar",
            "web",
            "busca",
            "buscar",
            "investiga",
            "investigar",
            "consulta",
            "consultar",
        }
        use_web = bool(re.search(r"https?://\S+", lower)) or explicit_web or any(
            marker in lower for marker in web_markers
        )
        use_memory = bool(memory_hits)
        reason = "web+memory" if use_web and use_memory else "web" if use_web else "memory" if use_memory else "direct"
        return RoutePlan(
            use_memory=use_memory,
            use_web=use_web,
            verify=use_web,
            reason=reason,
        )
