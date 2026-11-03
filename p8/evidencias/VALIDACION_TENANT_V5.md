# Validación real en tenant: P8 carga V5

## 1. Qué es este registro
Evidencia de la validación del flujo de carga P8 V5 en el tenant piloto real de Microsoft 365.

**Origen de los datos.** Los resultados de las tres ejecuciones y el estado final de las listas fueron
**reportados por la persona responsable del piloto** tras ejecutarlos en Power Automate y consultar
SharePoint REST. Quien redactó este documento no tuvo acceso al tenant y no los observó directamente.
Lo marcado como "por construcción" se deriva de los archivos del repo, no se leyó del tenant.

| Dato | Valor |
|---|---|
| Fecha de registro de este documento | 2026-10-01 |
| Fecha y hora de las 3 ejecuciones | **No proporcionada.** Completar desde el historial de ejecuciones del flujo. |
| IDs de ejecución de Power Automate | **No proporcionados.** |

## 2. Versión validada
| Dato | Valor |
|---|---|
| Flujo | `P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES` |
| Paquete validado | `P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES.zip` (6986 bytes) |
| SHA256 del paquete | `3761f0eba22225605e9acbe227a5cf37d4a773267ac476d5665477c5d9472e57` |
| Commit base de la versión | `37c39fb392c8c7d3f2393cd9850fb6c1bf728d92` (rama `candidate/p8-m365-pilot`) |
| Trigger | SharePoint `GetOnNewFileItems`, cada 1 minuto, concurrencia 1 |
| Sitio | `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` |
| Biblioteca (GUID) | `2a9d48e4-7ed6-4cef-9967-22d189c809bd` |
| Carpeta de entrada | `/Documents/P8_PILOTO` |
| `Depositos_Activos` (GUID) | `296c450a-25d6-415b-ad10-c909c74817cb` |
| `Depositos_Cargas` (GUID) | `677aab03-28d0-4893-83cf-1f394850c515` |
| Solución del hash | nombre visible `SHA256`, InternalName `HASH_SHA256` (sin cambios) |

## 3. Resultados de las tres ejecuciones (reportados)
| # | Ejecución | Archivo | RECIBIDA | VALIDA | NUEVA | YA_EXISTE | ERROR | ESTADO_LOTE |
|---|---|---|---|---|---|---|---|---|
| 1 | Primera carga | `DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json` | 8 | 8 | 8 | 0 | 0 | COMPLETADO |
| 2 | Reproceso del mismo lote | `DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json` | 8 | 8 | 0 | 8 | 0 | COMPLETADO |
| 3 | Lote mixto | `DEPOSITOS_ACTIVOS__P8-MIXTO-2N-2E.json` | 4 | 4 | 2 | 2 | 0 | COMPLETADO |

## 4. Estado final observado vía SharePoint REST (reportado)
| Lista | Elementos |
|---|---|
| `Depositos_Activos` | **10** (8 de la primera carga + 2 nuevos del mixto) |
| `Depositos_Cargas` | **3** (una bitácora por ejecución) |

## 5. Qué confirma, según los resultados reportados
- **Carga normal:** la ejecución 1 creó los 8 movimientos sin errores.
- **Idempotencia:** la ejecución 2 no creó nada (NUEVA 0, YA_EXISTE 8, ERROR 0). Con el mixto, `Depositos_Activos` suma 10 = 8 + 2.
- **Anti-duplicados y clasificación fila por fila:** en la ejecución 3, 2 filas se clasificaron como existentes y 2 como nuevas, sin errores. La asignación esperada por fila está en la sección 6.
  Los contadores agregados vienen del reporte de la persona responsable. No se adjuntó el detalle de cada fila leído del tenant.
- **Bitácora:** `Depositos_Cargas` pasó a 3 elementos, uno por ejecución, y sus conteos coinciden con los de la sección 3.
- **Identificadores esperados en la bitácora (por construcción, no leídos del tenant):**
  - ejecuciones 1 y 2: `LOTE_ID` = `P7-3af418fcadd6`, `HASH_SHA256` = `3af418fcadd6fd848a5957af5225222a8f9e753254269514cd719a718d35c83e`
  - ejecución 3: `LOTE_ID` = `P7-dcd6ec0cd635`, `HASH_SHA256` = `dcd6ec0cd635051d6b6465e7e113ab44493330a1c5b89b8ccd87c9151eedffef`

## 6. Lote mixto: `DEPOSITOS_ACTIVOS__P8-MIXTO-2N-2E.json`
Archivo versionado en `p8/evidencias/DEPOSITOS_ACTIVOS__P8-MIXTO-2N-2E.json` (4719 bytes, SHA256 `9963c3f1a831b8864f55526fc688722990025bd17127b4ebc9534553540b2d71`).
Esquema `P7_DEPOSITOS_ACTIVOS_V1`, 26 columnas P7, `omitidos` vacío. Los 4 movimientos son idénticos campo por campo a los de sus archivos de origen; no se editó ningún valor.

### 2 movimientos repetidos (ya existían entre los 8 de la primera carga)
Origen: `ejemplos_p7/motor/LISTS.csv` → `ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json` (lote `P7-3af418fcadd6`, extracto `bcp_me_1.xls`).

| Pos. en el mixto | Pos. en los 8 originales | CLAVE_TRANSACCION | Clasificación esperada |
|---|---|---|---|
| 1 | 1 | `BCP\|301-5005425-2-71\|20260707\|144349\|547521\|CRÉDITO\|445.00\|22768.54` | YA_EXISTE |
| 2 | 8 | `BCP\|301-5005425-2-71\|20260731\|110126\|287293\|CRÉDITO\|485.00\|27888.54` | YA_EXISTE |

### 2 movimientos nuevos
Origen: `p8/piloto_ampliado/LISTS_PILOTO_AMPLIADO.csv` → `p8/piloto_ampliado/DEPOSITOS_ACTIVOS__P7-b4d991f026be.json`.
Según `p8/piloto_ampliado/TRAZABILIDAD.json`, ese piloto sale de la golden `tests/golden/LOTE_12_LISTS.csv` (SHA256 `6d5da35355cbcb50ff2a154c05d6767d2a6af580488961cd93540f48a62fc8bf`).

| Pos. en el mixto | Fila de datos en la golden | Fixture | CLAVE_TRANSACCION | Clasificación esperada |
|---|---|---|---|---|
| 3 | 24 | `bnb_mn_3.xls` | `BNB\|3000100152\|20260801\|093143\|3P58189022\|CRÉDITO\|8662.00\|7361576.48` | NUEVO |
| 4 | 28 | `bcp_mn_3.xls` | `BCP\|301-5005684-3-97\|20260801\|095007\|15\|DÉBITO\|458.82\|2136281.62` | NUEVO |

### Cómo se construyó
1. Un `LISTS.csv` de 4 filas: encabezado de `LISTS.csv` más las 4 líneas anteriores, copiadas byte a byte (2 del original, 2 del piloto ampliado).
   Este CSV derivado se llamó `LISTS_P8_MIXTO_2N_2E.csv` (SHA256 `dcd6ec0cd635051d6b6465e7e113ab44493330a1c5b89b8ccd87c9151eedffef`, 2169 bytes). No se versionó; su huella es el `sha256_archivo_fuente` del JSON.
2. `adaptador_m365.adaptar()` generó el artefacto, sin modificar el código. Solo se renombró a `DEPOSITOS_ACTIVOS__P8-MIXTO-2N-2E.json`.
   Por eso `lote_id` es `P7-dcd6ec0cd635` y no coincide con el nombre del archivo; el flujo solo exige el patrón `DEPOSITOS_ACTIVOS__*.json`.

## 7. Ensayo local previo (simulador, no ejecución Microsoft)
`p8/ensayo_wdl.py` contra la definición V5 y los 8 movimientos existentes dio el mismo resultado que el tenant: 4/4/2/2/0, COMPLETADO, `Depositos_Activos` 8 → 10.

## 8. No disponible en este registro
- Fecha y hora de cada ejecución, IDs de ejecución y duraciones.
- Detalle de cada fila y contenido de las bitácoras leídos del tenant (solo se reportaron conteos agregados).
- Capturas o exportaciones de las listas.
