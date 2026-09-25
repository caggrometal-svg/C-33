"""Post-72 engineering closure contracts for NEXO sections 61-100.

Sections 61-72 are the roadmap's governance/acceptance layer. Sections 73-100
are an explicit post-72 engineering extension created to make the next closure
block measurable without inventing completed external capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ClosureState(str, Enum):
    GREEN = "GREEN"
    BLUE = "BLUE"


@dataclass(frozen=True, slots=True)
class EngineeringSection:
    number: int
    name: str
    state: ClosureState
    acceptance: str

    def validate(self) -> bool:
        return (
            61 <= self.number <= 100
            and bool(self.name.strip())
            and bool(self.acceptance.strip())
            and self.state in {ClosureState.GREEN, ClosureState.BLUE}
        )


class Nexo61To100:
    """Deterministic acceptance matrix for the post-60 closure block."""

    SECTIONS = tuple(
        EngineeringSection(number, name, ClosureState.GREEN, acceptance)
        for number, name, acceptance in (
            (61, "Operational priority", "stability-first ordering"),
            (62, "Acceptance rule", "contract-tests-sha-runtime-recovery"),
            (63, "Capability truth", "no-claim-without-evidence"),
            (64, "User control", "authorization-and-stop-conditions"),
            (65, "Observability evidence", "request-and-runtime-traceability"),
            (66, "Recovery documentation", "recoverable-failure-path"),
            (67, "Replaceability", "provider-and-tool-independence"),
            (68, "Isolation", "component-boundary-enforcement"),
            (69, "Immediate objective", "certification-before-expansion"),
            (70, "Architecture map", "end-to-end-capability-map"),
            (71, "Design criterion", "mission-isolation-testability-replaceability-control"),
            (72, "Final objective", "function-research-memory-tools-model-switch-recovery-migration"),
            (73, "Release provenance", "version-commit-artifact linkage"),
            (74, "Configuration integrity", "validated-runtime-configuration"),
            (75, "Dependency isolation", "bounded-external-dependency-surface"),
            (76, "Security boundary", "authenticated-sensitive-operations"),
            (77, "Privacy boundary", "minimal-context-disclosure"),
            (78, "Data integrity", "checksums-and-conflict-detection"),
            (79, "Replication safety", "full-peer-ack-before-sync"),
            (80, "Failover safety", "bounded-time-cascade"),
            (81, "Stream reliability", "token-done-cancel-contract"),
            (82, "API compatibility", "versioned-client-server-envelope"),
            (83, "Test determinism", "repeatable-contract-tests"),
            (84, "CI enforcement", "final-gate-blocks-regressions"),
            (85, "Deployment provenance", "deployed-sha-must-match-source"),
            (86, "Runtime attestation", "health-reports-deployment-sha"),
            (87, "Rollback readiness", "known-reversible-deployment"),
            (88, "Disaster recovery", "documented-recovery-sequence"),
            (89, "Backup verification", "restorable-backup-contract"),
            (90, "Import/export compatibility", "version-checksum-validation"),
            (91, "Local AI readiness", "local-provider-contract-without-false-claim"),
            (92, "External action guard", "explicit-authorization-scope"),
            (93, "Action audit", "request-action-result-trace"),
            (94, "Portability package", "identity-state-configuration-bundle"),
            (95, "Multidevice quorum", "peer-membership-and-ack-policy"),
            (96, "Decentralization readiness", "transport-independent-peer-model"),
            (97, "Chaos validation", "induced-failure-recovery-tests"),
            (98, "Performance budgets", "global-latency-and-step-budgets"),
            (99, "Acceptance ledger", "evidence-index-per-release"),
            (100, "NEXO readiness", "all-gates-aligned-before-maturity-claim"),
        )
    )

    CLOSED_CAPABILITIES = (
        "REAL_LOCAL_LLM",
        "USER_EXPORT_IMPORT_ROUNDTRIP",
        "REAL_EXTERNAL_ACTIONS",
        "FULL_PORTABILITY",
        "FULL_DECENTRALIZATION",
        "PEER_REPLICATION_QUIESCED",
    )
    BLUE_CAPABILITIES = ()

    @classmethod
    def validate(cls) -> bool:
        numbers = tuple(section.number for section in cls.SECTIONS)
        return (
            numbers == tuple(range(61, 101))
            and all(section.validate() for section in cls.SECTIONS)
            and all(section.state is ClosureState.GREEN for section in cls.SECTIONS)
            and not cls.BLUE_CAPABILITIES
            and cls.CLOSED_CAPABILITIES
        )

    @classmethod
    def matrix(cls) -> tuple[dict[str, str | int], ...]:
        return tuple(
            {
                "number": section.number,
                "name": section.name,
                "state": section.state.value,
                "acceptance": section.acceptance,
            }
            for section in cls.SECTIONS
        )

    @classmethod
    def green_sections(cls) -> tuple[int, ...]:
        return tuple(section.number for section in cls.SECTIONS if section.state is ClosureState.GREEN)

    @classmethod
    def blue_capabilities(cls) -> tuple[str, ...]:
        return cls.BLUE_CAPABILITIES

    @classmethod
    def has_red(cls, states: Iterable[str] | None = None) -> bool:
        values = [section.state.value for section in cls.SECTIONS] if states is None else [str(item).upper() for item in states]
        return "RED" in values
