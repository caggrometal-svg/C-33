# NEXO — Estado auditado 2026-09-25

Fuente de verdad: rama `main`.

Commit operativo verificado: `14652ccad9687ce203b14aa0ee9b373512c6a1bf`.

Railway production deployment para ese SHA: `04304de8-3f83-421c-af99-905d72a9c9c7` — SUCCESS.

Los logs de producción registran HTTP 200 para `/health`, `/ready`, `/v1/chat`, `/v1/ai-ready`, `/v1/ai/stream`, `/status` y `/v1/ai/diagnostics` el 2026-09-25 entre 07:40:40 y 07:40:52 UTC.

El código actual incluye resiliencia de proveedores, circuit breaker persistente, failover, WebTool, memoria PostgreSQL, ModelHub, ToolHub, Orchestrator, VerificationEngine, diagnostics y cliente Android/Capacitor.

Importante: el fallback local actual es determinista; no se considera un LLM local.

Pendientes reales: certificación reproducible completa de failover, evidencia extremo a extremo de Web/Memory, Release estable de APK y cierre de la arquitectura documental.

Las ramas `c33-hardening-*` y otras ramas antiguas no representan el estado actual; varias están más de 100 commits detrás de `main`.
