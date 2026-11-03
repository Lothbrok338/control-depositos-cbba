# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V4 → P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip` (SHA256 `df1855a4892e28a650078cf99ad5d47e82bfb14b1628b3b848c8442726500184`, **descartada**). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip`.
> **SUPERADA por la V4.2** (`P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip`): con `text_5` opcional Power Apps pidió 7 posicionales + un registro final.

Generado por `python -m p9.asignar.convertir_powerapps_v4_1`. **Único cambio: `text_2` (CODIGO_ESTUDIANTE) vuelve a estar en `required` del trigger.**

Motivo: con la V4, Power Apps marcó `P9_ASIGNAR_DEPOSITO.Run(...)` con «recibe 8 argumentos; espera entre 6 y 7». El `required` del trigger forma parte de la firma de `.Run(...)`.

## V4 → V4.1: nodos JSON que cambiaron (1)

| Ruta | V4 | V4.1 |
|---|---|---|
| `properties.definition.triggers.manual.inputs.schema.required` | `['number', 'text', 'text_1', 'text_3', 'text_4', 'text_6']` | `['number', 'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_6']` |

## Archivos del ZIP (V4 → V4.1)

| Archivo | Estado |
|---|---|
| `manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/apisMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/connectionsMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/definition.json` | **distinto** |

## Diff de texto V4 → V4.1 (definition.json, una propiedad por línea)

```diff
--- V4.zip
+++ V4_1.zip
@@ -57,0 +58 @@
+"text_2",
```

## V3 (validada en el tenant) → V4.1: nodos JSON que difieren (1)

El trigger de V4.1 es idéntico al de la V3 validada (misma firma de 8 argumentos). Lo único que difiere de la V3 es la validación de contenido de `CODIGO_ESTUDIANTE`:

| Ruta | V3 | V4.1 |
|---|---|---|
| `properties.definition.actions.Validar_entrada.inputs` | `@if(or(empty(outputs('Entrada')?['clave']),empty(outputs('Entrada')?['estudiante']),empty(outputs('Entrada')?['codigo_estudiante']),empty(outputs('Entrada')?['solicitado_por']),empty(outputs('Entrada')?['sede_asignacion']),empty(outputs('Entrada')?['usuario'])),'CAMPOS_OBLIGATORIOS',if(or(greater(length(outputs('Entrada')?['clave']),255),greater(length(outputs('Entrada')?['estudiante']),255),greater(length(outputs('Entrada')?['codigo_estudiante']),255),greater(length(outputs('Entrada')?['solicitado_por']),255),greater(length(outputs('Entrada')?['sede_asignacion']),255),greater(length(outputs('Entrada')?['usuario']),255)),'CAMPO_EXCEDE_255',if(or(less(outputs('Entrada')?['id'],1),contains(string(outputs('Entrada')?['id']),'.')),'ID_INVALIDO','')))` | `@if(or(empty(outputs('Entrada')?['clave']),empty(outputs('Entrada')?['estudiante']),empty(outputs('Entrada')?['solicitado_por']),empty(outputs('Entrada')?['sede_asignacion']),empty(outputs('Entrada')?['usuario'])),'CAMPOS_OBLIGATORIOS',if(or(greater(length(outputs('Entrada')?['clave']),255),greater(length(outputs('Entrada')?['estudiante']),255),greater(length(outputs('Entrada')?['codigo_estudiante']),255),greater(length(outputs('Entrada')?['solicitado_por']),255),greater(length(outputs('Entrada')?['sede_asignacion']),255),greater(length(outputs('Entrada')?['usuario']),255)),'CAMPO_EXCEDE_255',if(or(less(outputs('Entrada')?['id'],1),contains(string(outputs('Entrada')?['id']),'.')),'ID_INVALIDO','')))` |

## Lo que NO cambió

Los 8 inputs del trigger (claves `number`, `text`, `text_1`…`text_6`, mismo orden, nombres, tipos y descripciones), el `required` de la V3, `OBSERVACION` (`text_5`) opcional, la
validación de contenido de V4 en `Validar_entrada`, `Entrada`, validación de longitud (> 255) y de ID, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`),
condiciones, `CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, las 6 salidas de la respuesta, las 8 columnas escritas (`CODIGO_ESTUDIANTE` se sigue escribiendo, vacío),
sitio, GUID de la lista, manifiestos, IDs y `displayName`. El frontend no cambia.
