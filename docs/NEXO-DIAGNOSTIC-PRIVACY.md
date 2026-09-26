# C-33 — Privacidad de diagnóstico

## Política

El diagnóstico del cliente conserva únicamente evidencia operacional necesaria para detectar y recuperar fallos de conectividad.

### Se conserva

- timestamp
- etapa del diagnóstico
- backend y rol
- endpoint como **pathname**, nunca URL completa
- código HTTP
- tipo de contenido
- latencia
- código de razón normalizado
- proveedor
- versión de configuración
- referencia corta de correlación
- estado de replay, recuperación y fallback

### No se conserva

- prompts o mensajes del usuario
- síntesis o respuestas de NEXO
- cuerpos HTTP
- datos SSE crudos
- stack traces
- nombres de excepciones
- URLs completas, query strings o fragmentos de URL
- cabeceras de autenticación, cookies o credenciales
- identificadores completos de sesión o dispositivo

## Retención local

- máximo: **20 eventos**
- informe visible: **10 eventos**
- escritura en una única clave versionada: `C33_REMOTE_DIAGNOSTICS_V2`
- la migración elimina `C33_REMOTE_DIAGNOSTICS_V1`
- cada evento se somete a una lista blanca antes de escribirse
- los registros históricos se compactan al iniciar la aplicación

## Principio de evidencia

El diagnóstico debe permitir responder:

1. qué backend falló;
2. cuándo y en qué etapa;
3. con qué código HTTP o razón operacional;
4. cuánto tardó;
5. si hubo replay o failover;
6. cuál backend recuperó la operación.

No debe permitir reconstruir el contenido de la conversación ni las credenciales de acceso.

## Criterio de aceptación

Privacidad de diagnóstico = PASS cuando:

- no se almacenan campos fuera de la lista blanca;
- no se almacenan cuerpos ni contenido conversacional;
- se eliminan los registros V1 durante la migración;
- la retención máxima queda limitada a 20 eventos;
- el informe solo expone la evidencia operacional minimizada.
