# NEXO — Estado de las seis capacidades

Este bloque incorpora superficies funcionales reales para las seis capacidades que permanecían AZULES.

## LLM local real
src/nexo/local_llm.py implementa cliente OpenAI-compatible para Ollama o un runtime equivalente. El modo local del Brain intenta primero este runtime y solo usa el fallback determinista cuando el runtime local no está configurado o no responde.

La promoción a GREEN exige evidencia de un runtime local real respondiendo models y chat/completions en el dispositivo o entorno local de NEXO.

## Export/Import
POST /v1/export construye un bundle con mensajes, memoria, preferencias, configuración no sensible, identidad lógica y device_id.
POST /v1/import valida versión y SHA-256 e importa mensajes idempotentemente.

La aplicación móvil añade Exportar e Importar y conserva la identidad y conversación importadas.

## Acciones externas
POST /v1/actions/execute usa CONTROL_TOKEN como control de servidor y exige además autorización explícita, scope, HTTPS, allowlist exacta, límites de tiempo/tamaño e idempotency key. La auditoría conserva metadatos y hash de respuesta, nunca el secreto ni el cuerpo sensible.

## Portabilidad
La identidad lógica, estado conversacional y preferencias viajan en el bundle. Una instalación limpia puede restaurar el estado sin transportar secretos del backend.

## Multidispositivo y descentralización
La base de replicación ya opera con UUID, secuencia, idempotencia y conflictos. Se añadió un endpoint de estado para medir ONLINE/OFFLINE, pendientes y quiescencia.

El cierre runtime completo exige un segundo backend con una base realmente independiente y dos direcciones de replicación verificadas.

## Replicación quiescida
Un lote solo se marca sincronizado cuando el peer devuelve received == accepted == batch_size. HTTP 200 por sí solo no es suficiente.

## Regla de promoción
GREEN contractual o GREEN de pruebas no sustituye la evidencia runtime. Para retirar una capacidad de AZUL se exige implementación, tests, commit, despliegue, runtime observado y recovery. Para el peer: ONLINE y replication_pending == 0 sin pérdida, duplicación ni conflicto.
