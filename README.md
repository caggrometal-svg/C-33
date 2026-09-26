# C-33 / NEXO

C-33 es el núcleo actual de NEXO: una IA personal modular orientada a conectividad real, memoria durable, herramientas reemplazables, múltiples proveedores y recuperación ante fallos.

## Estado actual

La rama operativa es `main`. El estado documentado y auditado se encuentra en:

- `docs/NEXO-STATE-2026-09-25.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`

El commit operativo auditado es identificable en GitHub y el deployment de Railway se verifica contra el mismo SHA.

## Capacidades actuales

- API FastAPI para chat y streaming SSE.
- Readiness e IA remota comprobable.
- Cascade de proveedores con circuit breaker persistente y failover.
- Fallback local determinista, explícitamente marcado como degradado.
- WebTool para búsqueda y fetch HTTP(S).
- Memoria durable en PostgreSQL.
- Model Hub y Tool Hub con contratos independientes.
- Orchestrator y VerificationEngine.
- Observabilidad mediante request IDs, métricas y diagnostics.
- Cliente Android/Capacitor.
- Pipelines de tests, CodeQL y construcción de APK.

## Cliente Android

La versión actual declarada del bundle móvil es NEXO 0.1.6.

La construcción reproducible se realiza mediante GitHub Actions. La APK no debe considerarse una versión estable únicamente por existir como artifact temporal: una versión distribuible debe quedar asociada a versión, commit, fecha y pruebas.

## Configuración del modelo

C-33 usa una topología **FREE-only** para inferencia remota: Kilo Auto Free → Vireonix. Ambos tienen acceso sin pago requerido; el núcleo rechaza proveedores externos no aprobados y cualquier API key de inferencia.

El núcleo puede operar con fallback local determinista cuando la generación remota no está disponible. Ese fallback no se presenta como LLM hasta que exista un runtime local real. La vía FREE no depende de créditos, saldo o facturación de proveedores.

## Infraestructura

La topología certificable de C-33 usa **Railway como primario**, **Deplexo como backend de respaldo para el cliente**, y un **peer secundario externo en Supabase Edge Functions + PostgreSQL**. Railway y Deplexo sirven la misma API C-33; el cliente prueba Railway primero y conmuta a Deplexo ante fallos de infraestructura mediante su circuito de failover. La replicación durable se mantiene con el peer de Supabase, firmada con HMAC, protegida por RLS y validada mediante conteo, unicidad e integridad criptográfica. Los servicios heredados de Render/IAC33 no forman parte de la ruta operativa de C-33.

## Regla fundamental

NEXO no debe fingir capacidades.

No afirma que realizó una búsqueda si no la realizó, no afirma que recuerda datos que no puede recuperar y no afirma que la IA remota está disponible sin una comprobación de la ruta correspondiente.

## Próximo objetivo

La prioridad es cerrar la certificación reproducible de C-33 antes de ampliar la arquitectura: conectividad, observabilidad, failover, Web Engine y Memory Engine.

NEXO no se mide por la apariencia de la APK, sino por su capacidad de funcionar, investigar, recordar, cambiar de modelo, recuperarse y mantener el control en manos del usuario.