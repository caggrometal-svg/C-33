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

**Certified code SHA:** `031aa50d422a0d098b53200f63f34fbf3720194b`

**C-33 Certification:** PASS (run 296)

**NEXO Progress Gate:** PASS (run 152)

**Railway production:** SUCCESS (deployment `ae3166dc-4bad-46e9-83d0-2a57b1f2a9a3`)

### Closed in green
C-33 connectivity, health, circuit breaker, observability, real provider cascade/failover logic, Web Engine live path, memory continuity, Model Hub, Tool Hub, bounded Orchestrator, contracts 23-40, closure 41-60, and the 61-100 engineering acceptance extension.

### Current architecture boundary
**ETAPA 40 — AUTO MODE remains the last numbered architecture stage; closure sections 41-60 are now explicitly certified green at the contractual/automated level.**

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
Present and tested in `src/nexo/phases_41_60.py` / `tests/test_phases_41_60.py`. The 20 closure sections are explicitly certified green at the contractual/automated level.

## Post-72 engineering extension 73-100
Present and tested in `src/nexo/phases_61_100.py` / `tests/test_phases_61_100.py`. Sections 61-100 form a deterministic acceptance matrix covering governance, provenance, security, privacy, data integrity, replication safety, failover, stream reliability, API compatibility, CI enforcement, deployment/runtime attestation, rollback, disaster recovery, export/import compatibility, local-AI readiness, action guards, portability, multidevice, decentralization readiness, chaos/performance budgets, and final acceptance.

**Matrix status:** 61-100 = 🟢 VERDE contractual/automated (40/40). C-33 Certification #296 = PASS.

**No-red rule:** the 61-100 matrix contains only GREEN or BLUE states. Future capabilities requiring external runtime remain explicitly 🔵 BLUE; they are not disguised as failures or completed functionality.

See `docs/NEXO-CLOSURE-61-100.md`.

## Mission
NEXO remains replaceable, inspectable and portable while the user retains control.
