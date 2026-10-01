# Diff P9_ASIGNAR_DEPOSITO → P9_ASIGNAR_DEPOSITO_POWERAPPS_V2

Base: `P9_ASIGNAR_DEPOSITO.zip` (SHA256 `90890c1f4bd5ee741c1b61f862cde5085ed51b8e08f0f8f5949b694d79b05a85`, el probado en el tenant). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip`.
Generado por `python -m p9.asignar.convertir_powerapps_v2`. **Único cambio: `triggers.manual.kind`.**

## Nodos JSON que cambiaron (1)

| Ruta | Antes | Después |
|---|---|---|
| `properties.definition.triggers.manual.kind` | `Button` | `PowerAppV2` |

## Archivos del ZIP

| Archivo | Estado |
|---|---|
| `manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/manifest.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/apisMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/connectionsMap.json` | idéntico (byte a byte) |
| `Microsoft.Flow/flows/1e61afbc-a5ae-5ee9-bfaf-c3bde2b2f578/definition.json` | **distinto** |

(La diferencia en `definition.json` es exactamente la sustitución de `"kind":"Button"` por `"kind":"PowerAppV2"`.)

## Diff de texto (definition.json, una propiedad por línea)

```diff
--- P9_ASIGNAR_DEPOSITO.zip
+++ P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip
@@ -13 +13 @@
-"kind":"Button",
+"kind":"PowerAppV2",
```

## Lo que NO cambió

`actions` completo (9 acciones de primer nivel, ver prueba): `PARAM_SITIO_SHAREPOINT`, `PARAM_LISTA_DEPOSITOS_ACTIVOS`, `Entrada`, validaciones, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones, manejo de `CONFLICTO`/`NO_DISPONIBLE`/`ERROR`, `Responder_a_PowerApps` (mismos 6 campos), las entradas del trigger (`number`, `text`, `text_1`…`text_6`: mismo orden, tipos y títulos), `parameters`, `contentVersion`, manifiestos, IDs de recursos, `displayName`.
