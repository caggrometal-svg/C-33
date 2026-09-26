# NEXO — Extensión de cierre 61-100

## Regla de certificación veraz

Las secciones 61-100 se certifican en dos ejes independientes:

- **Contractual:** GREEN significa que el requisito está definido, delimitado y automatizado mediante pruebas deterministas.
- **Runtime:** GREEN significa que existe evidencia observada en el ciclo de certificación actual para la capacidad desplegada.
- **Runtime BLUE:** la capacidad puede existir en código o tener contrato/tests, pero no existe evidencia runtime actual suficiente para declararla operativa.
- **Runtime N/A:** la sección es de gobierno/aceptación y no representa una capacidad runtime.

Nunca se deriva un GREEN runtime a partir de documentación, código, un test histórico, intención de despliegue o existencia del módulo.

## Matriz actual

| Secciones | Contractual | Runtime |
|---|---|---|
| 61-72 | 🟢 GREEN (12/12) | — N/A |
| 73-100 | 🟢 GREEN (28/28) | 🔵 BLUE (28/28) |
| Total | 🟢 GREEN (40/40) | 🟢 GREEN (0/40) · 🔵 BLUE (28/40) · N/A (12/40) |

### Secciones 61-72

Son la capa de gobierno, aceptación y reglas de ingeniería. Su estado runtime es **N/A** porque no representan funcionalidades desplegadas.

### Secciones 73-100

Todas tienen contrato y automatización GREEN, pero actualmente permanecen **RUNTIME BLUE** hasta que la certificación live actual produzca evidencia específica para cada capacidad.

Esto incluye, entre otras, seguridad sensible, export/import, replicación, failover, SSE, deployment provenance, local AI, acciones externas, portabilidad, multidevice, descentralización, chaos y performance.

## Capacidades que NO están cerradas en runtime

- REAL_LOCAL_LLM
- USER_EXPORT_IMPORT_ROUNDTRIP
- REAL_EXTERNAL_ACTIONS
- FULL_PORTABILITY
- FULL_DECENTRALIZATION
- PEER_REPLICATION_QUIESCED

Estas capacidades sí tienen contrato (`*_CONTRACT`), pero ninguna está declarada cerrada operacionalmente en este ciclo.

## Gate CI

`src/nexo/phases_61_100.py` contiene la única matriz de verdad.

`tests/test_phases_61_100.py` verifica:

- cobertura exacta 61-100;
- contractual GREEN completo;
- runtime GREEN = 0 mientras no exista evidencia actual;
- runtime BLUE explícito para 73-100;
- ausencia de RED;
- separación serializada entre ambos ejes.

El workflow de C-33 ejecuta este gate como **cierre contractual**, no como certificación runtime de capacidades.

## Promoción runtime

Una sección solo puede pasar de RUNTIME BLUE a RUNTIME GREEN cuando exista evidencia actual y reproducible de:

`contrato + tests + PASS + commit identificable + SHA desplegado coincidente + ejecución runtime + recovery cuando corresponda`.

El cambio de estado debe ser explícito en la matriz y en la evidencia del release.

## Regla de cierre

**Código existente ≠ capacidad completada.**

**Contrato GREEN ≠ runtime GREEN.**

La certificación final de C-33 no debe utilizar el color GREEN contractual para ocultar una capacidad runtime no observada.
