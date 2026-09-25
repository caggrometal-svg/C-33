# NEXO — ROADMAP

## Rule

Each layer is certified before the next layer is built on top of it.

## Current sequence

```text
C-33
-> connectivity
-> observability
-> failover
-> Web Engine
-> Memory Engine
-> Model Hub
-> Tool Hub
-> Orchestrator
-> Verification
-> local AI
-> export/import
-> autonomy
-> portability
-> decentralization
-> NEXO LIBRE
```

## 2026-09-25 status

### C-33 — FINAL CERTIFICATION

Integrated: yes, on `main`.

Verified commit: `14652ccad9687ce203b14aa0ee9b373512c6a1bf`.

Verified deployment: Railway production deployment `04304de8-3f83-421c-af99-905d72a9c9c7`, status `SUCCESS`.

Observed production route sequence: health, readiness, chat, AI readiness, chat, SSE stream, status and diagnostics all returned HTTP 200 during the certification traffic recorded at 07:40 UTC.

Still required:
- reproducible evidence of induced provider failover;
- direct end-to-end verification of Web and Memory assertions;
- stable APK Release associated with version/commit/tests/date;
- Android verification of the exact published artifact.

### Observability — IMPLEMENTED

Request IDs, metrics and diagnostics exist. The next step is to encode the important runtime claims as regression assertions.

### Failover — IMPLEMENTED, CERTIFICATION INCOMPLETE

Provider cascade and persistent circuit breaker are real. Production logs show rate limits, timeouts, circuit-open states and multiple providers.

Next: controlled failure injection and proof that the next provider answers within the same request budget.

### Web Engine — PARTIAL

Search, fetch and source tracking exist.

Next: formal source object with URL, timestamp, relevant fragment and provenance tests.

### Memory Engine — PARTIAL

Durable conversation context and deterministic ranking exist. Portable bundles exist.

Next: short-term/session/persistent/research layers, confidence/importance/expiration/deduplication and complete user-facing export/import.

### Model Hub — PHASE 21 — COMPLETE (DEPLOYED)

Provider-neutral profiles now carry capability metadata. `ModelSelectionPolicy` classifies simple, reasoning, summary, privacy and local intents and chooses a matching configured capability deterministically.

`ModelHub.select_for_task()` is connected to the real `ProviderCascade` for remote generation, including SSE. Privacy/local intent does not silently fall back to a remote provider when no local capability exists; the current deterministic local fallback is explicitly marked degraded.

Runtime verification: Railway production deployment `b953c1c0-f64d-4dfd-a1f4-d1414ec60d9d` is `SUCCESS` on source SHA `00631f51004bfe4980054f73b577759a4abcc3e7`. The container started successfully and Railway recorded `GET /health` → `200 OK` after the phase-21 changes.

Phase-21 contract is therefore closed for the implemented scope. Remaining Model Hub work is explicitly later: cost/latency-aware optimization and a real local provider.

### Tool Hub — PHASE 22 — IMPLEMENTED / PENDING RUNTIME CERTIFICATION

Tool registry and permissions are active. Web search/fetch, UTC time and calculation are registered. Durable memory_search and state-mutating memory_store are now exposed through the same ToolHub boundary, with mutation permission enforced by the tool policy.

Next: runtime certification, document search, explicit schemas for tool inputs/outputs, and bounded external/API actions.

### Orchestrator — PHASE 23 — IMPLEMENTED / PENDING RUNTIME CERTIFICATION

Turn-level planning remains in NexoOrchestrator. Phase-23 adds a bounded execution contract with a hard step budget; no unrestricted agent loop is introduced.

Next: wire the bounded executor into the live request path.

### Verification — PHASE 25-26 — IMPLEMENTED / PENDING RUNTIME CERTIFICATION

VerificationPolicy now defines research-required detection and the three explicit knowledge states: SÉ, PUEDO INVESTIGAR and NO PUEDO DETERMINARLO.

Next: integrate contradiction handling and multi-source verification into the live turn.

### Local AI — PENDING

The local fallback is deterministic, not an LLM.

Next: integrate a real local model through the same provider contract and prove offline operation.

### Export / import — PARTIAL

Portable bundle schema and checksum validation exist.

Next: user-facing round-trip flow with compatibility tests.

### Autonomy — PENDING

No unrestricted agent loop should be added before permissions, budgets and stop conditions are explicit.

### Portability — PARTIAL

Backend replication and portable bundles exist.

Next: portable identity, memory and configuration across compatible installations.

### Decentralization — PENDING

Replication is a resilience component, not yet a fully distributed architecture.

## Advancement rule

A block is advanced only when:

1. contract exists;
2. tests exist;
3. tests pass;
4. commit is identifiable;
5. deployed SHA equals the source SHA;
6. runtime path is observed;
7. recovery is documented.

## Mission

The objective is not an impressive APK. The objective is a replaceable, inspectable, portable system in which the user retains control.

## Phase 24-30 contracts (2026-09-25)

- **24 — Request cycle:** canonical 12-step request lifecycle is defined and tested.
- **25 — Verification Engine:** research-required detection and verification state contract are defined and tested.
- **26 — Knowing when NEXO does not know:** explicit SÉ / PUEDO INVESTIGAR / NO PUEDO DETERMINARLO states are defined and tested.
- **27 — Cache:** TTL cache contract is defined and tested.
- **28 — Security:** secret redaction contract is defined and tested.
- **29 — Privacy:** context minimization contract is defined and tested.
- **30 — Export / data freedom:** checksummed export bundle contract is defined and tested.

Implementation is in src/nexo/phases_23_30.py with regression coverage in tests/test_phases_23_30.py. These phases are not called production-certified until their current main SHA has a terminal Railway SUCCESS and the live path is observed.
