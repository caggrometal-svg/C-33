"""Contracts for NEXO phases 31-40.

These boundaries turn the roadmap's portability, privacy, cooperation, and mode
selection concepts into deterministic, testable policy objects. They do not
pretend that a real local LLM, distributed transport, or external automation
system exists before one is actually connected.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from nexo.phases_23_30 import ExportBundle, NexoProtocol, PrivacyPolicy


class NexoMode(str, Enum):
    RESEARCH = "RESEARCH"
    MEMORY = "MEMORY"
    ACTION = "ACTION"
    CHAT = "CHAT"
    LOCAL = "LOCAL"
    AUTO = "AUTO"


@dataclass(frozen=True, slots=True)
class DeviceEndpoint:
    device_id: str
    platform: str
    protocol_version: str = "1"

    def envelope(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "device_id": self.device_id,
            "platform": self.platform,
            **payload,
        }
        return NexoProtocol.envelope(kind, body)


@dataclass(frozen=True, slots=True)
class PortableIdentity:
    identity_id: str
    bundle_version: str = "1"

    def validate(self) -> bool:
        return bool(self.identity_id.strip()) and self.bundle_version == "1"


@dataclass(frozen=True, slots=True)
class ReplicationManifest:
    identity: PortableIdentity
    devices: tuple[DeviceEndpoint, ...]
    memory_checksum: str | None = None

    def validate(self) -> bool:
        if not self.identity.validate() or not self.devices:
            return False
        ids = [device.device_id for device in self.devices]
        return len(ids) == len(set(ids))


@dataclass(frozen=True, slots=True)
class PortableBundleContract:
    """Phase-32 compatibility boundary around the phase-30 export bundle."""

    supported_version: str = "1"

    def validate_export(self, bundle: ExportBundle) -> bool:
        return bundle.version == self.supported_version and bundle.verify()

    def import_payload(self, payload: Mapping[str, Any]) -> ExportBundle:
        version = str(payload.get("version", ""))
        if version != self.supported_version:
            raise ValueError("unsupported_bundle_version")
        required = ("memory", "preferences", "research", "configuration", "metadata", "checksum")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError("missing_bundle_fields:" + ",".join(missing))
        bundle = ExportBundle(
            version=version,
            memory=tuple(payload["memory"]),
            preferences=dict(payload["preferences"]),
            research=tuple(payload["research"]),
            configuration=dict(payload["configuration"]),
            metadata=dict(payload["metadata"]),
            checksum=str(payload["checksum"]),
        )
        if not bundle.verify():
            raise ValueError("invalid_bundle_checksum")
        return bundle


@dataclass(frozen=True, slots=True)
class CooperationPlan:
    local_tasks: tuple[str, ...]
    remote_tasks: tuple[str, ...]
    reason: str

    def validate(self) -> bool:
        return bool(self.local_tasks or self.remote_tasks)


class LocalRemoteCooperationPolicy:
    """Phase-34 policy: keep private work local and allow remote heavy work only when needed."""

    PRIVATE_MARKERS = (
        "privado",
        "privacidad",
        "confidencial",
        "sensible",
        "private",
        "secret",
        "solo local",
        "offline",
    )
    HEAVY_REMOTE_MARKERS = (
        "razona",
        "razonamiento",
        "análisis profundo",
        "analiza en profundidad",
        "research",
        "investiga",
        "compara",
    )

    @classmethod
    def plan(cls, prompt: str) -> CooperationPlan:
        lower = (prompt or "").strip().lower()
        private = any(marker in lower for marker in cls.PRIVATE_MARKERS)
        heavy = any(marker in lower for marker in cls.HEAVY_REMOTE_MARKERS)
        if private:
            return CooperationPlan(
                local_tasks=("context", "memory"),
                remote_tasks=(),
                reason="private_by_default",
            )
        if heavy:
            return CooperationPlan(
                local_tasks=("context", "memory"),
                remote_tasks=("reasoning", "research"),
                reason="heavy_remote_work_allowed",
            )
        return CooperationPlan(
            local_tasks=("context",),
            remote_tasks=("chat",),
            reason="ordinary_request",
        )


@dataclass(frozen=True, slots=True)
class PrivacyByDefaultDecision:
    local_required: bool
    allow_network: bool
    permitted_fields: tuple[str, ...]
    reason: str


class PrivacyByDefaultPolicy:
    """Phase-35: privacy is local-first; network use is opt-in by task need."""

    def __init__(self) -> None:
        self.base = PrivacyPolicy()

    def decide(self, prompt: str) -> PrivacyByDefaultDecision:
        lower = (prompt or "").strip().lower()
        private = any(marker in lower for marker in LocalRemoteCooperationPolicy.PRIVATE_MARKERS)
        current = any(marker in lower for marker in ("actual", "actualmente", "hoy", "ahora", "latest", "current", "precio", "noticia", "internet", "web", "busca", "buscar", "investiga", "investigar", "research", "fuentes", "verifica", "verificar", "consulta", "consultar"))
        if private:
            return PrivacyByDefaultDecision(
                local_required=True,
                allow_network=False,
                permitted_fields=self.base.allowed_context_fields,
                reason="private_by_default",
            )
        return PrivacyByDefaultDecision(
            local_required=False,
            allow_network=current,
            permitted_fields=self.base.allowed_context_fields,
            reason="network_only_when_task_requires_it" if current else "no_network_required",
        )


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    steps: tuple[str, ...] = (
        "question",
        "plan",
        "search",
        "read",
        "compare",
        "verify",
        "synthesize",
        "sources",
    )
    max_sources: int = 5

    def validate(self) -> bool:
        expected = ("question", "plan", "search", "read", "compare", "verify", "synthesize", "sources")
        return self.steps == expected and 1 <= self.max_sources <= 10


@dataclass(frozen=True, slots=True)
class MemoryModePlan:
    priorities: tuple[str, ...] = (
        "history",
        "memory",
        "research",
        "preferences",
    )

    def validate(self) -> bool:
        return self.priorities == ("history", "memory", "research", "preferences")


@dataclass(frozen=True, slots=True)
class ActionAuthorization:
    authorized: bool
    scope: tuple[str, ...] = ()
    reason: str = "authorization_required"

    def allows(self, action: str) -> bool:
        return self.authorized and (not self.scope or action in self.scope)


class ActionModePolicy:
    """Phase-38 guard: tools/APIs/automations require explicit authorization."""

    def decision(self, *, action: str, authorized: bool, scope: Iterable[str] = ()) -> ActionAuthorization:
        clean_scope = tuple(sorted({str(item).strip() for item in scope if str(item).strip()}))
        decision = ActionAuthorization(
            authorized=bool(authorized),
            scope=clean_scope,
            reason="authorized" if authorized else "authorization_required",
        )
        if decision.authorized and not decision.allows(action):
            return ActionAuthorization(False, clean_scope, "action_outside_authorized_scope")
        return decision


@dataclass(frozen=True, slots=True)
class ChatModePlan:
    use_tools: bool = False
    use_memory: bool = True

    def validate(self) -> bool:
        return not self.use_tools and self.use_memory


@dataclass(frozen=True, slots=True)
class ModeDecision:
    mode: NexoMode
    reason: str
    confidence: str = "deterministic"


class AutoModeRouter:
    """Phase-40 deterministic default mode selector."""

    @staticmethod
    def choose(prompt: str, *, has_memory: bool = False, authorized_action: bool = False) -> ModeDecision:
        lower = (prompt or "").strip().lower()
        private = any(marker in lower for marker in LocalRemoteCooperationPolicy.PRIVATE_MARKERS)
        research = any(marker in lower for marker in (
            "investiga", "research", "busca en internet", "fuentes", "verifica", "actualmente", "latest", "current",
        ))
        action = any(marker in lower for marker in (
            "crea", "envía", "manda", "ejecuta", "programa", "automatiza", "action", "actúa",
        ))
        memory = any(marker in lower for marker in (
            "recuerda", "memoria", "historial", "preferencia", "qué te dije",
        ))
        if private:
            return ModeDecision(NexoMode.LOCAL, "private_request")
        if research:
            return ModeDecision(NexoMode.RESEARCH, "research_signals")
        if action:
            return ModeDecision(
                NexoMode.ACTION if authorized_action else NexoMode.ACTION,
                "authorized_action" if authorized_action else "action_requires_authorization",
            )
        if memory or has_memory:
            return ModeDecision(NexoMode.MEMORY, "memory_context")
        return ModeDecision(NexoMode.CHAT, "ordinary_conversation")

    @staticmethod
    def plan(prompt: str, *, has_memory: bool = False, authorized_action: bool = False) -> dict[str, Any]:
        decision = AutoModeRouter.choose(
            prompt,
            has_memory=has_memory,
            authorized_action=authorized_action,
        )
        payload = {
            "mode": decision.mode.value,
            "reason": decision.reason,
            "confidence": decision.confidence,
        }
        if decision.mode == NexoMode.RESEARCH:
            payload["plan"] = ResearchPlan().steps
        elif decision.mode == NexoMode.MEMORY:
            payload["priorities"] = MemoryModePlan().priorities
        elif decision.mode == NexoMode.ACTION:
            payload["authorization_required"] = not authorized_action
        elif decision.mode == NexoMode.CHAT:
            payload["chat"] = ChatModePlan().validate()
        return payload
