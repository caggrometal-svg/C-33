# NEXO / C-33 — Auditoría integral del mapa maestro
## Corte: 2026-09-25

## Fuente de verdad
- Repositorio: caggrometal-svg/C-33
- Rama: main
- HEAD de código: b2caf0f85fa82986ed5c2e2994f382e1dfd92826
- NEXO Progress Gate para HEAD: PASS
- C-33 Certification para HEAD: EN CURSO
- Último fallo certificado observado antes de las correcciones: HTTP 504 en Web/IA remota; Vireonix agotó ~5.5 s y Animica ~5.75 s. La petición completa terminó a ~12.3 s.

## Correcciones aplicadas en este ciclo
1. PostgreSQL: el pool usa el esquema configurado y PostgresState recibe el mismo esquema.
2. PostgreSQL: inicialización fuerza search_path al esquema configurado.
3. Resiliencia: límite por proveedor reducido a 4.5 s para reservar presupuesto a failover adicional.
4. Resiliencia: prueba de regresión obliga a alcanzar un tercer proveedor dentro de un presupuesto global de 18 s.
5. Railway production: BACKEND_TOTAL_TIMEOUT_MS=18000, CLIENT_TIMEOUT_MS=22000, NETWORK_TIMEOUT_SECONDS=8.

## Estado de las ETAPAS 0-40

| Etapa | Estado | Evidencia / pendiente |
|---|---|---|
| 0 Base project | PASS | Proyecto C-33/NEXO operativo en main |
| 1 Repo/versioning | PASS | main + commits identificables |
| 2 C-33 connectivity certification | BLOCKED | certificación live actual en curso |
| 3 Health system | PASS | /health y /ready cubiertos por CI/live gates |
| 4 Circuit breaker | PASS | persistente en PostgreSQL + tests |
| 5 Real failover | PARTIAL | cascada real + circuitos; falta prueba inducida reproducible en producción |
| 6 Observability | PASS | request IDs, métricas, diagnostics |
| 7 Web Engine | PARTIAL | WebTool real; live Web/AI gate había fallado por timeout de proveedores |
| 8 Sources/traceability | PARTIAL | URLs y ledger presentes; falta certificación E2E completa |
| 9 Memory | PARTIAL | PostgreSQL + ranking determinista; falta certificación E2E completa |
| 10 Model Hub | PARTIAL | perfiles/capabilities conectados a cascade; runtime depende de provider path sano |
| 11 Tool Engine | PARTIAL | ToolHub operativo en código; certificación runtime pendiente |
| 12 Orchestrator | PARTIAL | bounded execution integrada en Brain; certificación runtime pendiente |
| 13 Cache | PASS | TTL contract + tests |
| 14 Security | PASS | redaction, HTTP security, replication signature |
| 15 Privacy | PASS | minimización y local-first contracts |
| 16 Export data | PARTIAL | bundle con checksum; flujo completo de usuario pendiente |
| 17 Import | PARTIAL | checksum/compatibility; round-trip de usuario pendiente |
| 18 Android-first | PASS* | build/lint/APK gate histórico PASS; publicación exacta aún pendiente (*no equivale a release certificada) |
| 19 GitHub Actions | PASS | gates automáticos activos |
| 20 GitHub Releases | PARTIAL | pipeline de APK existe; release estable/published artifact pendiente |
| 21 Rollback | PARTIAL | Railway permite rollback; prueba/recovery documentada pendiente |
| 22 Client-server contracts | PASS | contratos y pruebas presentes |
| 23 Error System | PARTIAL | ErrorEvent existe; falta cerrar exposición uniforme del sistema de errores en todos los paths |
| 24 Degraded Mode | PASS* | política determinista y metadata integradas; E2E runtime completo pendiente |
| 25 Research as object | PARTIAL | Research/ResearchObject existen; persistencia/flujo E2E pendiente |
| 26 Long-term context | PARTIAL | policy de persistencia/dedupe existe; integración completa pendiente |
| 27 Controlled autonomy | PASS* | límite de 8 pasos y autorización existen; ejecución multi-tool E2E pendiente |
| 28 Permissions | PASS* | PermissionMatrix + ToolHub policy |
| 29 Architecture of Trust | PASS* | TrustRecord/TrustArchitecture existen; evidencia completa por turno pendiente |
| 30 NEXO protocol | PASS | envelope versionado implementado y reutilizado |
| 31 Multidevice | PARTIAL | DeviceEndpoint/ReplicationManifest implementados; runtime multipunto pendiente |
| 32 NEXO portable | PARTIAL | bundle/identity contracts; migración completa pendiente |
| 33 Progressive decentralization | PARTIAL | manifest/replication base; arquitectura distribuida completa pendiente |
| 34 Stronger local AI | PARTIAL | cooperation policy; no LLM local real aún |
| 35 Private by default | PASS* | política local-first integrada |
| 36 Research Mode | PARTIAL | router/plan determinista; investigación E2E pendiente |
| 37 Memory Mode | PARTIAL | prioridades definidas; E2E pendiente |
| 38 Action Mode | PARTIAL | autorización definida; ejecución real externa pendiente |
| 39 Normal Chat | PASS* | ruta simple integrada en Brain |
| 40 Auto Mode | PASS* | AutoModeRouter integrado y metadata de modo emitida |

`PASS*` significa contrato/código probado y/o integrado, pero no cumple por sí solo la regla de certificación de producción.

## Secciones de cierre 41-60
El repositorio las representa en `src/nexo/phases_41_60.py` y `tests/test_phases_41_60.py`. La implementación contractual existe y la batería automatizada pasa; el cierre formal exige además runtime observado, recuperación y evidencia del sistema completo.

- 41 Degraded mode: implementado
- 42 Research as object: implementado contractualmente
- 43 Long-term context: implementado contractualmente
- 44 Controlled autonomy: implementado contractualmente
- 45 Permissions: implementado contractualmente
- 46 Architecture of Trust: implementado contractualmente
- 47 NEXO protocol: implementado contractualmente
- 48-50 Multidevice / portability / decentralization: contracts presentes
- 51-52 Local/remote + privacy: contracts presentes
- 53-57 Modes: contracts presentes
- 58 Mode matrix: presente
- 59 Master Test: batería de 12 casos definida
- 60 Success Criteria: criterio definido; no debe declararse como madurez completa todavía

## 61-72 — Gobierno y criterio final
Estas secciones no son todas etapas ejecutables de código; funcionan como reglas de prioridad, operación, aceptación y objetivo final.

- 61 Prioridad operativa: estabilidad C-33 → observabilidad → failover → Web → memoria → modelos → herramientas → orquestación → verificación → IA local → export/import → autonomía → portabilidad → descentralización.
- 69 Objetivo inmediato: certificar conectividad, failover, diagnostics y release reproducible antes de ampliar capacidades.
- 70 Mapa: C-33 → conectividad → resiliencia → observabilidad → Internet → fuentes → memoria → modelos intercambiables → herramientas → orquestación → verificación → IA local → portabilidad → privacidad → autonomía → independencia → NEXO LIBRE.
- 71 Criterio de diseño: toda función debe tener misión, aislamiento, prueba, reemplazabilidad y efecto claro sobre el control del usuario.
- 72 Objetivo final: NEXO debe funcionar, investigar, recordar, usar herramientas, cambiar de modelo, trabajar localmente, sobrevivir fallos, migrar y explicar su actuación manteniendo el control del usuario.

## Regla de avance
No se declara una etapa de producción como cerrada solo porque exista el módulo. Requiere:
1. contrato;
2. pruebas;
3. tests PASS;
4. commit identificable;
5. SHA desplegado igual al código;
6. ruta runtime observada;
7. recuperación documentada.

## Bloqueo actual
El bloqueo inmediato ya no es un fallo sintáctico de código local. Es la certificación live del camino Web/IA remoto y la demostración reproducible de failover/replicación con el SHA actual.

## Siguiente cierre técnico
- Obtener SUCCESS del C-33 Certification sobre b2caf...
- Verificar que Railway expone b2caf... con el timeout de 18 s.
- Repetir chat remoto + Web + /v1/ai-ready + SSE + diagnostics.
- Cerrar evidencia de replicación pendiente=0 y sin pérdida/duplicación.
- Actualizar ROADMAP/STATE con el SHA certificado.


## Provider topology correction

Production uses Kilo `kilo-auto/free` first, followed by BlockRun Nemotron and Vireonix. Kilo documents anonymous access for free models; BlockRun publishes its free Nemotron endpoint without a key. The topology is intentionally zero-cost and provider-independent.
