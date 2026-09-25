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

### Model Hub — PARTIAL / SELECTION POLICY IMPLEMENTED

Provider-neutral profiles now carry capability metadata. `ModelSelectionPolicy` classifies simple, reasoning, summary, privacy and local intents and chooses a matching configured capability deterministically.

`ModelHub.select_for_task()` is connected to the real `ProviderCascade` for remote generation, including SSE. Privacy/local intent does not silently fall back to a remote provider when no local capability exists; the current deterministic local fallback is explicitly marked degraded.

Next: cost/latency-aware selection and a real local provider.

### Tool Hub — PARTIAL

Tool registry and permissions exist.

Next: memory search/store, documents, APIs and bounded actions.

### Orchestrator — PARTIAL

A turn-level planner exists.

Next: explicit CHAT/RESEARCH/MEMORY/ACTION/LOCAL/AUTO modes, multi-step bounded tool use and stop conditions.

### Verification — PARTIAL

Source and citation structure is validated.

Next: contradiction handling, multi-source verification and explicit SÉ / PUEDO INVESTIGAR / NO PUEDO DETERMINARLO states.

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