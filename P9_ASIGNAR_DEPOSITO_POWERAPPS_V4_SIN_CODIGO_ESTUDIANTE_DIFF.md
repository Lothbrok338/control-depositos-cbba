# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA → P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip` (SHA256 `023db6b4a95b30320f27a1e4d0d38b09bcaac8889ec2e0d3e383d2eb3adb3a44`). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip`.
> **DESCARTADA — NO IMPORTAR.** Con esta V4 Power Apps marcó `.Run(...)` con «recibe 8 argumentos; espera entre 6 y 7». La corrige `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip`.

Generado por `python -m p9.asignar.convertir_powerapps_v4`. **Único cambio: `CODIGO_ESTUDIANTE` (`text_2`) deja de ser obligatorio.**

## Nodos JSON que cambiaron (2)

| Ruta | Antes | Después |
|---|---|---|
| `properties.definition.actions.Validar_entrada.inputs` | `@if(or(empty(outputs('Entrada')?['clave']),empty(outputs('Entrada')?['estudiante']),empty(outputs('Entrada')?['codigo_estudiante']),empty(outputs('Entrada')?['solicitado_por']),empty(outputs('Entrada')?['sede_asignacion']),empty(outputs('Entrada')?['usuario'])),'CAMPOS_OBLIGATORIOS',if(or(greater(length(outputs('Entrada')?['clave']),255),greater(length(outputs('Entrada')?['estudiante']),255),greater(length(outputs('Entrada')?['codigo_estudiante']),255),greater(length(outputs('Entrada')?['solicitado_por']),255),greater(length(outputs('Entrada')?['sede_asignacion']),255),greater(length(outputs('Entrada')?['usuario']),255)),'CAMPO_EXCEDE_255',if(or(less(outputs('Entrada')?['id'],1),contains(string(outputs('Entrada')?['id']),'.')),'ID_INVALIDO','')))` | `@if(or(empty(outputs('Entrada')?['clave']),empty(outputs('Entrada')?['estudiante']),empty(outputs('Entrada')?['solicitado_por']),empty(outputs('Entrada')?['sede_asignacion']),empty(outputs('Entrada')?['usuario'])),'CAMPOS_OBLIGATORIOS',if(or(greater(length(outputs('Entrada')?['clave']),255),greater(length(outputs('Entrada')?['estudiante']),255),greater(length(outputs('Entrada')?['codigo_estudiante']),255),greater(length(outputs('Entrada')?['solicitado_por']),255),greater(length(outputs('Entrada')?['sede_asignacion']),255),greater(length(outputs('Entrada')?['usuario']),255)),'CAMPO_EXCEDE_255',if(or(less(outputs('Entrada')?['id'],1),contains(string(outputs('Entrada')?['id']),'.')),'ID_INVALIDO','')))` |
| `properties.definition.triggers.manual.inputs.schema.required` | `['number', 'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_6']` | `['number', 'text', 'text_1', 'text_3', 'text_4', 'text_6']` |

## Archivos del ZIP

| Archivo | Estado |
|---|---|
| `manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/apisMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/connectionsMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/definition.json` | **distinto** |

## Diff de texto (definition.json, una propiedad por línea)

```diff
--- V3_RESPUESTA.zip
+++ V4_SIN_CODIGO_ESTUDIANTE.zip
@@ -58 +57,0 @@
-"text_2",
@@ -104 +102,0 @@
-empty(outputs('Entrada')?['codigo_estudiante']),
```

## Lo que NO cambió

Firma de `.Run(...)` (8 entradas, mismo orden, mismas claves `number`, `text`, `text_1`…`text_6`), `Entrada`, validación de longitud (> 255), validación de ID,
`Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones, `CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, las 6 salidas de la respuesta,
las 8 columnas que se escriben (`CODIGO_ESTUDIANTE` se sigue escribiendo, vacío), sitio, GUID de la lista, manifiestos, IDs y `displayName`.
