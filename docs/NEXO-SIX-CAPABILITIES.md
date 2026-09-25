# NEXO — Vía FREE / LIBERTAD

NEXO no depende de créditos, saldos o proveedores de inferencia con facturación para su ruta remota.

## Inferencia remota
Topología obligatoria:
1. Kilo Auto Free — kilo-auto/free
2. Vireonix — auto

El núcleo rechaza proveedores fuera del allowlist FREE, modelos no aprobados, API keys de inferencia y cualquier activación de AI_ZERO_COST_MODE=false.

Kilo documenta kilo-auto/free como ruta sin créditos; los modelos gratuitos pueden usarse sin autenticación. Vireonix documenta su API como gratuita y sin cuenta ni API key, sujeta a límites de fair use.

## LLM local real
La aplicación dispone de adaptador OpenAI-compatible para runtime local. La promoción requiere runtime real y prueba de inferencia local.

## Export/Import
La aplicación expone exportación e importación del estado de usuario con validación SHA-256 e importación idempotente.

## Acciones externas
Las acciones reales requieren autorización explícita, scope, host allowlist, HTTPS, límites e idempotencia. No introducen proveedor de inferencia de pago.

## Portabilidad
La identidad lógica, estado conversacional y preferencias se transportan mediante bundle sin secretos de proveedores.

## Descentralización
La vía FREE evita contratar una base de datos para el peer. El peer completo debe vivir en infraestructura dentro del nivel gratuito o en un dispositivo controlado por el usuario.

## Regla
FREE significa cero dependencia operacional de pago. Una alternativa que pueda generar cargos no puede formar parte de la ruta automática.
