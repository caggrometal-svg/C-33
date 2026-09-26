"""Truthful closure matrix for NEXO sections 61-100.

Contractual verification and runtime verification are intentionally separate.
A GREEN contract state only means the requirement is defined and automated.
A GREEN runtime state requires fresh observed evidence from the current
certification cycle. No runtime GREEN is inferred from repository presence,
historical runs, or documentation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ContractState(str, Enum):
    GREEN = "GREEN"
    BLUE = "BLUE"


class RuntimeState(str, Enum):
    GREEN = "GREEN"
    BLUE = "BLUE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class EngineeringSection:
    number: int
    name: str
    contract_state: ContractState
    runtime_state: RuntimeState
    acceptance: str
    runtime_evidence: str

    def validate(self) -> bool:
        return (
            61 <= self.number <= 100
            and bool(self.name.strip())
            and bool(self.acceptance.strip())
            and bool(self.runtime_evidence.strip())
            and self.contract_state in {ContractState.GREEN, ContractState.BLUE}
            and self.runtime_state in {
                RuntimeState.GREEN,
                RuntimeState.BLUE,
                RuntimeState.NOT_APPLICABLE,
            }
        )


class Nexo61To100:
    """Two-axis acceptance matrix: contract truth and current runtime truth."""

    _GOVERNANCE = {
        61: ("Operational priority", "stability-first ordering", "Governance/acceptance section; runtime state is not applicable."),
        62: ("Acceptance rule", "contract-tests-sha-runtime-recovery", "Governance/acceptance section; runtime state is not applicable."),
        63: ("Capability truth", "no-claim-without-evidence", "Governance/acceptance section; runtime state is not applicable."),
        64: ("User control", "authorization-and-stop-conditions", "Governance/acceptance section; runtime state is not applicable."),
        65: ("Observability evidence", "request-and-runtime-traceability", "Governance/acceptance section; runtime state is not applicable."),
        66: ("Recovery documentation", "recoverable-failure-path", "Governance/acceptance section; runtime state is not applicable."),
        67: ("Replaceability", "provider-and-tool-independence", "Governance/acceptance section; runtime state is not applicable."),
        68: ("Isolation", "component-boundary-enforcement", "Governance/acceptance section; runtime state is not applicable."),
        69: ("Immediate objective", "certification-before-expansion", "Governance/acceptance section; runtime state is not applicable."),
        70: ("Architecture map", "end-to-end-capability-map", "Governance/acceptance section; runtime state is not applicable."),
        71: ("Design criterion", "mission-isolation-testability-replaceability-control", "Governance/acceptance section; runtime state is not applicable."),
        72: ("Final objective", "function-research-memory-tools-model-switch-recovery-migration", "Governance/acceptance section; runtime state is not applicable."),
    }

    _ENGINEERING = {
        73: ("Release provenance", "version-commit-artifact linkage"),
        74: ("Configuration integrity", "validated-runtime-configuration"),
        75: ("Dependency isolation", "bounded-external-dependency-surface"),
        76: ("Security boundary", "authenticated-sensitive-operations"),
        77: ("Privacy boundary", "minimal-context-disclosure"),
        78: ("Data integrity", "checksums-and-conflict-detection"),
        79: ("Replication safety", "full-peer-ack-before-sync"),
        80: ("Failover safety", "bounded-time-cascade"),
        81: ("Stream reliability", "token-done-cancel-contract"),
        82: ("API compatibility", "versioned-client-server-envelope"),
        83: ("Test determinism", "repeatable-contract-tests"),
        84: ("CI enforcement", "final-gate-blocks-regressions"),
        85: ("Deployment provenance", "deployed-sha-must-match-source"),
        86: ("Runtime attestation", "health-reports-deployment-sha"),
        87: ("Rollback readiness", "known-reversible-deployment"),
        88: ("Disaster recovery", "documented-recovery-sequence"),
        89: ("Backup verification", "restorable-backup-contract"),
        90: ("Import/export compatibility", "version-checksum-validation"),
        91: ("Local AI readiness", "local-provider-contract-without-false-claim"),
        92: ("External action guard", "explicit-authorization-scope"),
        93: ("Action audit", "request-action-result-trace"),
        94: ("Portability package", "identity-state-configuration-bundle"),
        95: ("Multidevice quorum", "peer-membership-and-ack-policy"),
        96: ("Decentralization readiness", "transport-independent-peer-model"),
        97: ("Chaos validation", "induced-failure-recovery-tests"),
        98: ("Performance budgets", "global-latency-and-step-budgets"),
        99: ("Acceptance ledger", "evidence-index-per-release"),
        100: ("NEXO readiness", "all-gates-aligned-before-maturity-claim"),
    }

    SECTIONS = tuple(
        EngineeringSection(
            number=number,
            name=name,
            contract_state=ContractState.GREEN,
            runtime_state=RuntimeState.NOT_APPLICABLE,
            acceptance=acceptance,
            runtime_evidence=evidence,
        )
        for number, (name, acceptance, evidence) in _GOVERNANCE.items()
    ) + tuple(
        EngineeringSection(
            number=number,
            name=name,
            contract_state=ContractState.GREEN,
            runtime_state=RuntimeState.BLUE,
            acceptance=acceptance,
            runtime_evidence=(
                "No fresh current-cycle runtime proof is attached; "
                "do not infer GREEN from code, historical certification, or deployment intent."
            ),
        )
        for number, (name, acceptance) in _ENGINEERING.items()
    )

    @classmethod
    def validate(cls) -> bool:
        numbers = tuple(section.number for section in cls.SECTIONS)
        return (
            numbers == tuple(range(61, 101))
            and all(section.validate() for section in cls.SECTIONS)
        )

    @classmethod
    def matrix(cls) -> tuple[dict[str, str | int], ...]:
        return tuple(
            {
                "number": section.number,
                "name": section.name,
                "contract_state": section.contract_state.value,
                "runtime_state": section.runtime_state.value,
                "acceptance": section.acceptance,
                "runtime_evidence": section.runtime_evidence,
            }
            for section in cls.SECTIONS
        )

    @classmethod
    def contract_green_sections(cls) -> tuple[int, ...]:
        return tuple(
            section.number
            for section in cls.SECTIONS
            if section.contract_state is ContractState.GREEN
        )

    @classmethod
    def runtime_green_sections(cls) -> tuple[int, ...]:
        return tuple(
            section.number
            for section in cls.SECTIONS
            if section.runtime_state is RuntimeState.GREEN
        )

    @classmethod
    def runtime_blue_sections(cls) -> tuple[int, ...]:
        return tuple(
            section.number
            for section in cls.SECTIONS
            if section.runtime_state is RuntimeState.BLUE
        )

    @classmethod
    def not_applicable_runtime_sections(cls) -> tuple[int, ...]:
        return tuple(
            section.number
            for section in cls.SECTIONS
            if section.runtime_state is RuntimeState.NOT_APPLICABLE
        )

    @classmethod
    def green_sections(cls) -> tuple[int, ...]:
        """Backward-compatible alias: contractual GREEN only."""
        return cls.contract_green_sections()

    @classmethod
    def closed_capabilities(cls) -> tuple[str, ...]:
        """No capability is closed at runtime without current-cycle proof."""
        return ()

    @classmethod
    def contractual_capabilities(cls) -> tuple[str, ...]:
        return (
            "REAL_LOCAL_LLM_CONTRACT",
            "USER_EXPORT_IMPORT_CONTRACT",
            "REAL_EXTERNAL_ACTIONS_CONTRACT",
            "FULL_PORTABILITY_CONTRACT",
            "FULL_DECENTRALIZATION_CONTRACT",
            "PEER_REPLICATION_CONTRACT",
        )

    @classmethod
    def blue_capabilities(cls) -> tuple[str, ...]:
        return (
            "REAL_LOCAL_LLM",
            "USER_EXPORT_IMPORT_ROUNDTRIP",
            "REAL_EXTERNAL_ACTIONS",
            "FULL_PORTABILITY",
            "FULL_DECENTRALIZATION",
            "PEER_REPLICATION_QUIESCED",
        )

    @classmethod
    def has_red(cls, states: Iterable[str] | None = None) -> bool:
        values = (
            [section.contract_state.value for section in cls.SECTIONS]
            if states is None
            else [str(item).upper() for item in states]
        )
        return "RED" in values
