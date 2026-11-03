# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V2 → P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip` (SHA256 `4a73ee22f9246cf8170cb9e8934ed7006f7a087f1aca460f0abac77a0e913dc6`). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip`.
Generado por `python -m p9.asignar.convertir_powerapps_v3`. **Único cambio: la marca `x-ms-dynamically-added: true` en las 6 propiedades del esquema de `Responder_a_PowerApps`.**

## Nodos JSON que cambiaron (6)

| Ruta | Antes | Después |
|---|---|---|
| `properties.definition.actions.Responder_a_PowerApps.inputs.schema.properties.asignado_por.x-ms-dynamically-added` | `<ausente>` | `True` |
| `properties.definition.actions.Responder_a_PowerApps.inputs.schema.properties.codigo.x-ms-dynamically-added` | `<ausente>` | `True` |
| `properties.definition.actions.Responder_a_PowerApps.inputs.schema.properties.estado_actual.x-ms-dynamically-added` | `<ausente>` | `True` |
| `properties.definition.actions.Responder_a_PowerApps.inputs.schema.properties.fecha_hora_asignacion.x-ms-dynamically-added` | `<ausente>` | `True` |
| `properties.definition.actions.Responder_a_PowerApps.inputs.schema.properties.mensaje.x-ms-dynamically-added` | `<ausente>` | `True` |
| `properties.definition.actions.Responder_a_PowerApps.inputs.schema.properties.resultado.x-ms-dynamically-added` | `<ausente>` | `True` |

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
--- V2.zip
+++ V3_RESPUESTA.zip
@@ -344,0 +345 @@
+"x-ms-dynamically-added":true,
@@ -346,0 +348 @@
+"x-ms-dynamically-added":true,
@@ -348,0 +351 @@
+"x-ms-dynamically-added":true,
@@ -350,0 +354 @@
+"x-ms-dynamically-added":true,
@@ -352,0 +357 @@
+"x-ms-dynamically-added":true,
@@ -354,0 +360 @@
+"x-ms-dynamically-added":true,
```

## Lo que NO cambió

Trigger «Power Apps (V2)» y sus 8 entradas, `Entrada`, validaciones, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones,
`CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, `varRespuesta` (inicialización y los 10 `Resultado_*` que la escriben), el `body` de la respuesta, sitio, GUID de la lista,
manifiestos, IDs y `displayName`.
