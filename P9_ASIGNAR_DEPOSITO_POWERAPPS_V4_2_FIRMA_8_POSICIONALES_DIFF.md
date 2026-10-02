# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1 → P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip` (SHA256 `2d656b642baa2e5caa8f41710ae21cffddf6f538e4172e1de3c0eb12f35490a2`, **superada**). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip`.
Generado por `python -m p9.asignar.convertir_powerapps_v4_2`. **Único cambio: `text_5` (OBSERVACION) se agrega a `required` del trigger.**

Motivo: con la V4.1 Power Apps pidió 7 argumentos posicionales + un registro para el opcional. Con los 8 en `required` la firma es de 8 posicionales y no hay registro.
`required` solo significa presencia del parámetro técnico; no exige contenido (eso lo decide `Validar_entrada`, que no cambia).

## V4.1 → V4.2: nodos JSON que cambiaron (1)

| Ruta | V4.1 | V4.2 |
|---|---|---|
| `properties.definition.triggers.manual.inputs.schema.required` | `['number', 'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_6']` | `['number', 'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_5', 'text_6']` |

## Archivos del ZIP (V4.1 → V4.2)

| Archivo | Estado |
|---|---|
| `manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/apisMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/connectionsMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/definition.json` | **distinto** |

## Diff de texto V4.1 → V4.2 (definition.json, una propiedad por línea)

```diff
--- V4_1.zip
+++ V4_2.zip
@@ -60,0 +61 @@
+"text_5",
```

## V3 (validada en el tenant) → V4.2: nodos JSON que difieren (2)

| Ruta | V3 | V4.2 |
|---|---|---|
| `properties.definition.actions.Validar_entrada.inputs` | `@if(or(empty(outputs('Entrada')?['clave']),empty(outputs('Entrada')?['estudiante']),empty(outputs('Entrada')?['codigo_estudiante']),empty(outputs('Entrada')?['solicitado_por']),empty(outputs('Entrada'` | `@if(or(empty(outputs('Entrada')?['clave']),empty(outputs('Entrada')?['estudiante']),empty(outputs('Entrada')?['solicitado_por']),empty(outputs('Entrada')?['sede_asignacion']),empty(outputs('Entrada')?` |
| `properties.definition.triggers.manual.inputs.schema.required` | `['number', 'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_6']` | `['number', 'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_5', 'text_6']` |

## Lo que NO cambió

Los 8 inputs del trigger (claves `number`, `text`, `text_1`…`text_6`, mismo orden, títulos, tipos y descripciones), `Validar_entrada` (no exige CODIGO_ESTUDIANTE ni OBSERVACION;
sí clave, estudiante, solicitado por, sede y usuario; límite de 255 e ID inválido), `Entrada`, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones,
`CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, las 6 salidas de la respuesta, las 8 columnas escritas, sitio, GUID de la lista, manifiestos, IDs y `displayName`.
