# NEXO — ROADMAP

## Rule
Each layer is certified before the next layer is built on top of it.

## Certification rule
Contractual verification and runtime verification are independent axes.
Contract GREEN means requirement + tests are internally coherent and automated.
Runtime GREEN requires fresh, observed evidence from the current certification cycle.
Historical PASS, repository presence, documentation, or deployment intent cannot create a runtime GREEN.

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
-> NEXO LIBRE / FREE-ONLY
```

## Current closure status

### Contractual
- C-33 core contracts and earlier closures remain subject to their own gates.
- Sections 61-100: **GREEN contractual (40/40)**.

### Runtime
- Sections 61-72: **N/A** runtime; governance/acceptance only.
- Sections 73-100: **BLUE runtime (28/28)** until fresh current-cycle evidence is attached.
- Real local AI, user export/import round-trip, real external actions, full portability, full decentralization and peer quiescence are not declared operationally closed.

## Closure sections 41-60
Present and tested in `src/nexo/phases_41_60.py` / `tests/test_phases_41_60.py` under the documented contractual scope.

## Post-72 engineering extension 73-100
Present and tested in `src/nexo/phases_61_100.py` / `tests/test_phases_61_100.py`.

**Matrix:** 61-100 = 🟢 contractual 40/40; runtime = 🔵 28/28 for 73-100, with 61-72 N/A.

## Advancement rule
A capability advances to runtime GREEN only when contract + tests + PASS + identifiable commit + matching deployed SHA + observed runtime + documented recovery, where applicable, all agree.

## Mission
NEXO remains replaceable, inspectable and portable while the user retains control.
