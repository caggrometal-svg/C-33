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

## 2026-09-25 status — AUDIT REAL

Fuente de verdad: `main`.

**HEAD actual:** `b2caf0f85fa82986ed5c2e2994f382e1dfd92826`.

**Implementación:** el repositorio contiene contratos hasta **ETAPA 40 — AUTO MODE** y las secciones de cierre 41-60.

**Certificación:** el último gate completo antes de este ciclo falló en Web/IA remota con HTTP 504 porque el runtime agotaba aproximadamente 12 s tras Vireonix + Animica. El código ya fue corregido para trabajar con presupuesto de 18 s y límite por proveedor de 4.5 s.

**Acciones:** NEXO Progress Gate sobre el nuevo HEAD está PASS. C-33 Certification está ejecutándose sobre el nuevo HEAD.

### Correcciones aplicadas
- PostgreSQL usa realmente el esquema configurado en el pool y en `PostgresState`.
- Inicialización PostgreSQL fija `search_path` al esquema configurado.
- Failover conserva presupuesto para un tercer proveedor.
- La regresión de resiliencia exige alcanzar un tercer proveedor en un presupuesto de 18 s.
- Railway production fue ajustado a BACKEND_TOTAL_TIMEOUT_MS=18000, CLIENT_TIMEOUT_MS=22000 y NETWORK_TIMEOUT_SECONDS=8.

### Estado operacional por bloque

| Bloque | Estado |
|---|---|
| C-33 / salud / readiness | ✅ implementado y probado |
| Circuit breaker | ✅ implementado y probado |
| Failover | 🟡 implementado; falta certificación inducida reproducible |
| Observabilidad | ✅ implementado |
| Web + fuentes | 🟡 implementado; certificación live bloqueada por provider path |
| Memoria | 🟡 durable + ranking determinista; E2E pendiente |
| Model Hub | 🟡 integrado; runtime depende de provider path |
| Tool Hub | 🟡 implementado; runtime pendiente |
| Orchestrator | 🟡 bounded + integrado; E2E pendiente |
| ETAPAS 23-30 | 🟡 contratos presentes; certificación live pendiente donde aplica |
| ETAPAS 31-40 | 🟡 contratos presentes; Auto Mode integrado; certificación live pendiente |
| Secciones 41-60 | 🟡 contratos y tests presentes; cierre maestro pendiente |
| Local AI real | 🔴 pendiente |
| Export/import usuario | 🟡 parcial |
| Autonomía externa | 🔴 pendiente |
| Portabilidad completa | 🟡 parcial |
| Descentralización completa | 🔴 pendiente |
| Android release certificada | 🟡 pipeline presente; artifact final aún no certificado |

### Regla de avance
Un bloque solo pasa a producción cuando contrato + tests + commit + SHA desplegado + runtime observado + recuperación están alineados.

El detalle completo del mapa 0-72 está en `docs/NEXO-AUDIT-2026-09-25.md`.

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

## Phase 31-40 contracts (2026-09-25)

The roadmap's phases 31-40 are now represented by deterministic contracts in `src/nexo/phases_31_40.py` with regression coverage in `tests/test_phases_31_40.py`.

- **31 — Multidispositivo:** `DeviceEndpoint` and `ReplicationManifest` define a shared-core/device boundary using the NEXO protocol envelope.
- **32 — NEXO portable:** `PortableIdentity` and `PortableBundleContract` validate phase-30 export bundles and reject unsupported versions/checksum tampering.
- **33 — Descentralización progresiva:** replication manifests keep identity and device membership separate from any single transport/provider.
- **34 — IA local más fuerte:** `LocalRemoteCooperationPolicy` defines local context/memory work and optional remote reasoning/research without pretending a local LLM exists.
- **35 — Private by default:** `PrivacyByDefaultPolicy` makes sensitive work local-first and permits network access only when the task requires current external information.
- **36 — Research Mode:** bounded plan is question -> plan -> search -> read -> compare -> verify -> synthesize -> sources.
- **37 — Memory Mode:** explicit priority order is history -> memory -> research -> preferences.
- **38 — Action Mode:** tools/APIs/automations require explicit authorization and optional action scope.
- **39 — Normal Chat:** chat mode is the simple path with memory/context and no unnecessary tools.
- **40 — Auto Mode:** deterministic router selects among LOCAL, RESEARCH, MEMORY, ACTION and CHAT; the live Brain now records the selected mode and contract in turn metadata.

Runtime certification remains subject to the same rule above: tests must pass, the deployed SHA must match the source SHA, the live route must be observed, and recovery behavior must be documented.

## Closure sections 41-60 (2026-09-25)

The source PDF's sections 41-60 close the architecture rather than introducing ETAPA 41-60. They are now represented by `src/nexo/phases_41_60.py` and `tests/test_phases_41_60.py`.

- **41 — Degraded mode:** deterministic capability-preservation policy for Web failure, provider failure/failover, memory failure, and local fallback.
- **42 — Research as object:** structured research object with question, sources, findings, confidence, timestamp and summary.
- **43 — Long-term context:** selective persistence thresholds and deterministic deduplication key.
- **44 — Controlled autonomy:** bounded tool sequence with an explicit maximum of 8 steps and authorization state.
- **45 — Permissions:** least-privilege matrix for WEB, MEMORY, FILES and AUTOMATION.
- **46 — Architecture of Trust:** reconstructable turn record carrying request, reason, knowledge state and optional tool/source/model fields.
- **47 — NEXO protocol:** reuses the existing versioned NEXO envelope contract.
- **48-50 — Multidevice, portability, decentralization:** shared-core device manifest, portable bundle compatibility and explicit decentralization path.
- **51-52 — Local/remote cooperation and privacy:** local-first private work and network access only when task-required.
- **53-57 — Modes:** Research, Memory, Action, Chat and Auto contracts.
- **58 — Mode matrix:** explicit mode capability matrix.
- **59 — Master test:** 12-case integration battery defined as the closure test plan.
- **60 — Success criterion:** explicit capability set for functional maturity; this remains an acceptance criterion, not a claim of completed maturity.

The live Brain now emits closure metadata for degraded mode, selected mode/matrix, autonomy contract, and master-test contract.
