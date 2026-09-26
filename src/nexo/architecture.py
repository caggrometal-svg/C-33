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
from agent.nexo import NexoCore

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


@dataclass(frozen=True, slots=True)
class ModelSelectionDecision:
    intent: str
    preferred_capabilities: tuple[str, ...]
    selected_provider: str | None
    reason: str
    local_required: bool = False


class ModelSelectionPolicy:
    """Deterministic task-to-model policy; never invents a local model."""

    _INTENT_CAPABILITIES = {
        "simple": ("fast", "low_latency", "chat"),
        "reasoning": ("reasoning", "quality", "deep"),
        "summary": ("economical", "cheap", "summary"),
        "privacy": ("local", "private"),
        "local": ("local", "private"),
    }

    @classmethod
    def classify(cls, prompt: str) -> str:
        lower = (prompt or "").strip().lower()
        privacy_markers = ("privado", "privacidad", "confidencial", "sensible", "private")
        local_markers = ("sin internet", "sin conexión", "offline", "localmente", "solo local")
        summary_markers = ("resume", "resumen", "summarize", "summary")
        reasoning_markers = (
            "razona", "razonamiento", "analiza", "análisis",
            "debug", "depura", "compara en profundidad",
        )
        if any(marker in lower for marker in privacy_markers):
            return "privacy"
        if any(marker in lower for marker in local_markers):
            return "local"
        if any(marker in lower for marker in summary_markers):
            return "summary"
        if any(marker in lower for marker in reasoning_markers):
            return "reasoning"
        return "simple"

    @classmethod
    def choose(cls, profiles: tuple[ModelProfile, ...], prompt: str) -> ModelSelectionDecision:
        intent = cls.classify(prompt)
        preferred = tuple(cls._INTENT_CAPABILITIES[intent])
        local_required = intent in {"privacy", "local"}

        for capability in preferred:
            for profile in profiles:
                if capability in profile.capabilities:
                    return ModelSelectionDecision(
                        intent=intent,
                        preferred_capabilities=preferred,
                        selected_provider=profile.provider_id,
                        reason=f"capability_match:{capability}",
                        local_required=local_required,
                    )

        if local_required:
            return ModelSelectionDecision(
                intent=intent,
                preferred_capabilities=preferred,
                selected_provider=None,
                reason="local_capability_unavailable",
                local_required=True,
            )

        fallback = profiles[0].provider_id if profiles else None
        return ModelSelectionDecision(
            intent=intent,
            preferred_capabilities=preferred,
            selected_provider=fallback,
            reason="stable_profile_fallback" if fallback else "no_profiles",
            local_required=False,
        )


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
            profiles.append(
                ModelProfile(
                    spec.provider_id,
                    spec.model,
                    spec.failure_domain,
                    tuple(getattr(spec, "capabilities", ("chat", "stream"))),
                )
            )
        return tuple(profiles)

    def select(self, preferred_provider: str | None = None) -> ModelProfile | None:
        preferred = (preferred_provider or "").strip()
        if preferred:
            for profile in self.profiles:
                if profile.provider_id == preferred:
                    return profile
        return self.profiles[0] if self.profiles else None

    def select_for_task(self, prompt: str) -> ModelSelectionDecision:
        """Return the provider selected by the deterministic task policy."""
        return ModelSelectionPolicy.choose(self.profiles, prompt)

    async def complete(
        self,
        messages: list[dict[str, str]],
        budget: Any,
        *,
        preferred_provider: str | None = None,
    ) -> Any:
        # Keep the ModelHub contract compatible with lightweight test doubles and
        # legacy cascade adapters that do not yet expose preferred_provider.
        complete = self.cascade.complete
        if preferred_provider is not None:
            try:
                signature = inspect.signature(complete)
            except (TypeError, ValueError):
                signature = None
            if signature is not None and (
                "preferred_provider" in signature.parameters
                or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())
            ):
                return await complete(messages, budget, preferred_provider=preferred_provider)
        return await complete(messages, budget)

    def stream(
        self,
        messages: list[dict[str, str]],
        budget: Any,
        *,
        preferred_provider: str | None = None,
    ) -> Any:
        return self.cascade.stream(messages, budget, preferred_provider=preferred_provider)


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
        if NexoCore.is_self_reference(prompt):
            return RoutePlan(
                use_memory=False,
                use_web=False,
                verify=False,
                reason="self-reference",
            )
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
            re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lower) is not None
            for marker in web_markers
        )
        use_memory = bool(memory_hits)
        reason = "web+memory" if use_web and use_memory else "web" if use_web else "memory" if use_memory else "direct"
        return RoutePlan(
            use_memory=use_memory,
            use_web=use_web,
            verify=use_web,
            reason=reason,
        )
