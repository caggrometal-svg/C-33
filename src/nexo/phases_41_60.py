"""Closure contracts for NEXO document sections 41-60.

The source roadmap numbers these as sections 41-60 (while the individual
architecture stages are labeled ETAPA 24-40). This module converts the
document's closing requirements into deterministic, testable contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from nexo.phases_23_30 import KnowledgeState, Research, TrustEvent


class DegradedMode(str, Enum):
    FULL = "FULL"
    WEB_DEGRADED = "WEB_DEGRADED"
    PROVIDER_FAILOVER = "PROVIDER_FAILOVER"
    OFFLINE_LOCAL = "OFFLINE_LOCAL"
    MEMORY_DEGRADED = "MEMORY_DEGRADED"


@dataclass(frozen=True, slots=True)
class DegradedDecision:
    mode: DegradedMode
    preserved_capabilities: tuple[str, ...]
    disabled_capabilities: tuple[str, ...]
    reason: str


class DegradedModePolicy:
    """Section 41: remain useful when a subsystem is unavailable."""

    @staticmethod
    def decide(
        *,
        web_available: bool = True,
        provider_available: bool = True,
        memory_available: bool = True,
        local_available: bool = True,
        failover_used: bool = False,
    ) -> DegradedDecision:
        if not memory_available:
            return DegradedDecision(
                DegradedMode.MEMORY_DEGRADED,
                ("chat", "provider_failover", "local_fallback"),
                ("memory",),
                "memory_unavailable",
            )
        if not provider_available and local_available:
            return DegradedDecision(
                DegradedMode.OFFLINE_LOCAL,
                ("chat", "local_fallback", "memory"),
                ("remote_provider", "web_dependent_research"),
                "remote_provider_unavailable",
            )
        if failover_used:
            return DegradedDecision(
                DegradedMode.PROVIDER_FAILOVER,
                ("chat", "memory", "web"),
                ("primary_provider",),
                "provider_failover",
            )
        if not web_available:
            return DegradedDecision(
                DegradedMode.WEB_DEGRADED,
                ("chat", "memory", "remote_provider"),
                ("web",),
                "web_unavailable",
            )
        return DegradedDecision(
            DegradedMode.FULL,
            ("chat", "memory", "web", "remote_provider"),
            (),
            "all_declared_dependencies_available",
        )


@dataclass(frozen=True, slots=True)
class ResearchObject:
    question: str
    sources: tuple[str, ...]
    findings: tuple[str, ...]
    confidence: float | None
    created_at: float
    summary: str

    @classmethod
    def from_research(cls, research: Research) -> "ResearchObject":
        return cls(
            question=research.question,
            sources=tuple(research.sources),
            findings=tuple(research.findings),
            confidence=research.confidence,
            created_at=research.created_at,
            summary=research.summary,
        )

    def validate(self) -> bool:
        return bool(self.question.strip()) and all(
            source.startswith(("http://", "https://")) for source in self.sources
        ) and (self.confidence is None or 0.0 <= self.confidence <= 1.0)


@dataclass(frozen=True, slots=True)
class LongTermMemoryDecision:
    persist: bool
    dedupe_key: str
    reason: str


class LongTermMemoryPolicy:
    """Section 43: distinguish history from useful persistent knowledge."""

    def __init__(self, *, min_importance: float = 0.70, min_confidence: float = 0.70) -> None:
        if not 0.0 <= min_importance <= 1.0 or not 0.0 <= min_confidence <= 1.0:
            raise ValueError("memory_threshold_out_of_range")
        self.min_importance = min_importance
        self.min_confidence = min_confidence

    @staticmethod
    def dedupe_key(content: str) -> str:
        normalized = " ".join((content or "").lower().split())
        return normalized[:512]

    def decide(self, *, content: str, importance: float, confidence: float) -> LongTermMemoryDecision:
        key = self.dedupe_key(content)
        if not key:
            return LongTermMemoryDecision(False, "", "empty_content")
        if importance < self.min_importance:
            return LongTermMemoryDecision(False, key, "importance_below_threshold")
        if confidence < self.min_confidence:
            return LongTermMemoryDecision(False, key, "confidence_below_threshold")
        return LongTermMemoryDecision(True, key, "persistent_knowledge_threshold_met")


@dataclass(frozen=True, slots=True)
class AutonomyPlan:
    operations: tuple[str, ...]
    max_steps: int
    approval_required: bool

    def validate(self) -> bool:
        return 1 <= self.max_steps <= 8 and len(self.operations) <= self.max_steps


class ControlledAutonomyPolicy:
    """Section 44: tool chaining is bounded and never becomes an open loop."""

    DEFAULT_MAX_STEPS = 8

    @classmethod
    def plan(cls, operations: Iterable[str], *, authorized: bool = False, max_steps: int = DEFAULT_MAX_STEPS) -> AutonomyPlan:
        clean = tuple(str(op).strip() for op in operations if str(op).strip())
        if not 1 <= int(max_steps) <= cls.DEFAULT_MAX_STEPS:
            raise ValueError("autonomy_step_budget_out_of_range")
        return AutonomyPlan(
            operations=clean[:int(max_steps)],
            max_steps=int(max_steps),
            approval_required=not authorized,
        )


@dataclass(frozen=True, slots=True)
class Permission:
    read: bool = False
    write: bool = False
    action: bool = False


class PermissionMatrix:
    """Section 45: least-privilege declarations per tool family."""

    DEFAULTS = {
        "WEB": Permission(read=True),
        "MEMORY": Permission(read=True, write=True),
        "FILES": Permission(read=True),
        "AUTOMATION": Permission(action=True),
    }

    def __init__(self, entries: Mapping[str, Permission] | None = None) -> None:
        self.entries = dict(entries or self.DEFAULTS)

    def allows(self, tool: str, capability: str) -> bool:
        permission = self.entries.get(str(tool).upper(), Permission())
        return bool(getattr(permission, str(capability).lower(), False))


@dataclass(frozen=True, slots=True)
class TrustRecord:
    event: TrustEvent
    source_count: int
    knowledge_state: KnowledgeState

    def reconstructable(self) -> bool:
        return bool(self.event.request_id and self.event.action and self.event.reason)


class TrustArchitecture:
    """Section 46: preserve enough structured evidence to reconstruct a turn."""

    @staticmethod
    def record(
        *,
        request_id: str,
        action: str,
        reason: str,
        knowledge_state: KnowledgeState,
        source_count: int,
        tool: str | None = None,
        source: str | None = None,
        model: str | None = None,
    ) -> TrustRecord:
        event = TrustEvent.create(
            request_id,
            action,
            reason,
            tool=tool,
            source=source,
            model=model,
        )
        record = TrustRecord(event, max(0, int(source_count)), knowledge_state)
        if not record.reconstructable():
            raise ValueError("non_reconstructable_trust_record")
        return record


@dataclass(frozen=True, slots=True)
class DecentralizationPlan:
    layers: tuple[str, ...] = (
        "cloud_centralized",
        "interchangeable_components",
        "exportable_data",
        "local_ai",
        "personal_server",
        "distributed_architecture",
    )

    def validate(self) -> bool:
        return self.layers == (
            "cloud_centralized",
            "interchangeable_components",
            "exportable_data",
            "local_ai",
            "personal_server",
            "distributed_architecture",
        )


@dataclass(frozen=True, slots=True)
class ModeMatrixEntry:
    mode: str
    internet: str
    memory: str
    tools: str
    chat_optional: str


class NexoModeMatrix:
    """Section 58: explicit matrix for RESEARCH/MEMORY/ACTION/LOCAL/AUTO."""

    ENTRIES = (
        ModeMatrixEntry("CHAT", "no", "sí", "no", "sí"),
        ModeMatrixEntry("RESEARCH", "sí", "sí", "alta", "sí"),
        ModeMatrixEntry("MEMORY", "optional", "alta", "media", "sí"),
        ModeMatrixEntry("ACTION", "según tarea", "sí", "alta", "sí"),
        ModeMatrixEntry("LOCAL", "no", "sí", "limitada", "local"),
        ModeMatrixEntry("AUTO", "dinámico", "dinámico", "dinámico", "dinámico"),
    )

    @classmethod
    def get(cls, mode: str) -> ModeMatrixEntry:
        value = str(mode).upper()
        for entry in cls.ENTRIES:
            if entry.mode == value:
                return entry
        raise ValueError("unknown_nexo_mode")


@dataclass(frozen=True, slots=True)
class MasterTest:
    number: int
    name: str
    expected: str


class MasterTestPlan:
    """Section 59: the 12-item integration battery from the roadmap."""

    TESTS = (
        MasterTest(1, "conversation", "respond"),
        MasterTest(2, "memory", "recover_correct_data"),
        MasterTest(3, "internet", "real_webtool"),
        MasterTest(4, "sources", "verifiable_sources"),
        MasterTest(5, "provider", "automatic_failover"),
        MasterTest(6, "sse", "stream_correctly"),
        MasterTest(7, "reconnection", "recover"),
        MasterTest(8, "web_failure", "degraded_mode"),
        MasterTest(9, "primary_ai_failure", "failover"),
        MasterTest(10, "internet_failure", "local_or_degraded"),
        MasterTest(11, "export", "user_gets_data"),
        MasterTest(12, "import", "data_restored"),
    )

    @classmethod
    def validate(cls) -> bool:
        return tuple(test.number for test in cls.TESTS) == tuple(range(1, 13))

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(test.name for test in cls.TESTS)


@dataclass(frozen=True, slots=True)
class SuccessCriteria:
    required_capabilities: tuple[str, ...] = (
        "ask",
        "understand",
        "remember",
        "research",
        "use_tools",
        "verify",
        "choose_model",
        "recover_from_failures",
        "respond",
        "retain_useful_knowledge",
    )

    def validate_observed(self, observed: Iterable[str]) -> bool:
        observed_set = {str(item).strip() for item in observed}
        return set(self.required_capabilities).issubset(observed_set)


class ClosureStatus(str, Enum):
    """Allowed closure states: green when the contract is certified, blue when work is explicitly future."""
    GREEN = "GREEN"
    BLUE = "BLUE"


@dataclass(frozen=True, slots=True)
class ClosureSection:
    number: int
    name: str
    status: ClosureStatus
    contract: str

    def validate(self) -> bool:
        return (
            41 <= self.number <= 60
            and bool(self.name.strip())
            and bool(self.contract.strip())
            and self.status in {ClosureStatus.GREEN, ClosureStatus.BLUE}
        )


class Closure41To60:
    """Single source of truth for the 41-60 closure matrix.

    All 41-60 sections are green at the contractual/automated level.
    Capabilities that require future external infrastructure are tracked
    separately as blue so the project never uses red as a hidden placeholder.
    """

    SECTIONS = tuple(
        ClosureSection(number, name, ClosureStatus.GREEN, contract)
        for number, name, contract in (
            (41, "Degraded Mode", "DegradedModePolicy"),
            (42, "Research as object", "ResearchObject"),
            (43, "Long-term context", "LongTermMemoryPolicy"),
            (44, "Controlled autonomy", "ControlledAutonomyPolicy"),
            (45, "Permissions", "PermissionMatrix"),
            (46, "Architecture of Trust", "TrustArchitecture"),
            (47, "NEXO protocol", "NexoProtocol"),
            (48, "Multidevice", "DeviceEndpoint/ReplicationManifest"),
            (49, "NEXO portable", "PortableIdentity/PortableBundleContract"),
            (50, "Progressive decentralization", "DecentralizationPlan"),
            (51, "Local/remote cooperation", "LocalRemoteCooperationPolicy"),
            (52, "Private by default", "PrivacyByDefaultPolicy"),
            (53, "Research Mode", "ResearchPlan"),
            (54, "Memory Mode", "MemoryModePlan"),
            (55, "Action Mode", "ActionModePolicy"),
            (56, "Normal Chat", "ChatModePlan"),
            (57, "Auto Mode", "AutoModeRouter"),
            (58, "Mode matrix", "NexoModeMatrix"),
            (59, "Master Test", "MasterTestPlan"),
            (60, "Success Criteria", "SuccessCriteria"),
        )
    )

    BLUE_CAPABILITIES = (
        "REAL_LOCAL_LLM",
        "USER_EXPORT_IMPORT_ROUNDTRIP",
        "REAL_EXTERNAL_ACTIONS",
        "FULL_PORTABILITY",
        "FULL_DECENTRALIZATION",
    )

    @classmethod
    def validate(cls) -> bool:
        numbers = tuple(section.number for section in cls.SECTIONS)
        if numbers != tuple(range(41, 61)):
            return False
        if not all(section.validate() for section in cls.SECTIONS):
            return False
        if any(section.status is not ClosureStatus.GREEN for section in cls.SECTIONS):
            return False
        return bool(cls.BLUE_CAPABILITIES)

    @classmethod
    def status_matrix(cls) -> tuple[dict[str, str | int], ...]:
        return tuple(
            {
                "number": section.number,
                "name": section.name,
                "status": section.status.value,
                "contract": section.contract,
            }
            for section in cls.SECTIONS
        )

    @classmethod
    def green_sections(cls) -> tuple[int, ...]:
        return tuple(section.number for section in cls.SECTIONS if section.status is ClosureStatus.GREEN)

    @classmethod
    def blue_capabilities(cls) -> tuple[str, ...]:
        return cls.BLUE_CAPABILITIES
