# NEXO — ROADMAP

## Rule
Each layer is certified before the next layer is built on top of it.

## Current sequence
```
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

## 2026-09-25 status — CERTIFIED

**Certified code SHA:** `55a2d62213a37563398d65d9585329eff87c11d2`

**C-33 Certification:** PASS (run 292)

**NEXO Progress Gate:** PASS (run 146)

**Railway production:** SUCCESS (deployment `f86bc410-25f2-44f9-a349-84f56b2265f9`)

### Closed in green
C-33 connectivity, health, circuit breaker, observability, real provider cascade/failover logic, Web Engine live path, memory continuity, Model Hub, Tool Hub, bounded Orchestrator, contracts 23-40, and closure contracts 41-60.

### Current architecture boundary
**ETAPA 40 — AUTO MODE is the current certified engineering boundary.**

The repository contains deterministic contracts for later capabilities, but future capability is not mislabeled as completed functionality.

### Next engineering block
- Real local LLM through the same provider contract and offline certification.
- User-facing export/import round-trip.
- Real external actions under explicit authorization and stop conditions.
- Full portability across compatible installations.
- Full multidevice replication and decentralization.

### Advancement rule
A block advances only when contract + tests + passing result + identifiable commit + matching deployed SHA + observed runtime + documented recovery all agree.

## Phase 24-30 contracts
Present and tested in `src/nexo/phases_23_30.py` / `tests/test_phases_23_30.py`.

## Phase 31-40 contracts
Present and tested in `src/nexo/phases_31_40.py` / `tests/test_phases_31_40.py`. **ETAPA 40 — AUTO MODE is integrated into Brain.**

## Closure sections 41-60
Present and tested in `src/nexo/phases_41_60.py` / `tests/test_phases_41_60.py`. They define the acceptance architecture but do not imply that every future external capability is already connected.

## Mission
NEXO remains replaceable, inspectable and portable while the user retains control.
