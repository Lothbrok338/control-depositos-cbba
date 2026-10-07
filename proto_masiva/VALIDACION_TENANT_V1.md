# P9 CONFIRMACIÓN MASIVA V1 — Evidencia real de tenant y matriz de validación

> **Nota:** esto describe la **V1 síncrona** (checkpoint `82b279e`). La evolución a 1999 filas (`ESCALA_1999.md`) cambia el contrato del flujo y NO está validada en el tenant: nada de lo de aquí abajo se aplica a ella salvo la lógica por fila, que no cambió.

Rama `experiment/p9-masiva-prototipo`. Alcance: **checkpoint** de lo que funcionó de punta a punta en el tenant de prueba (`P9_PRUEBA_MASIVA`, 2026-10-07). No añade funcionalidad.
Fuente de la UI: export `.msapp` posterior a la integración (sha256 `3a90a83cb31bf20a218893b7bd96c7050c3de98cd1c4e5ded75c6195f8400645`), copiado verbatim en `powerapps/tenant_v1/`.

> **Cómo se obtuvo esta evidencia:** observación directa de Gabriel en pantalla (Power Apps, Power Automate y la lista `Depositos_Activos`). No se guardó el historial de ejecuciones ni capturas
> en el repositorio. La V1 valida el **camino feliz con 2 confirmaciones** y el filtrado previo de 1 fila inválida; **no** valida escala, carreras ni fallos.

## 1 · Evidencia REAL de tenant (una sola ejecución)

Excel de 3 filas. **PREVALIDAR ARCHIVO** (flujo `P9_MASIVA_PROTO_PREVALIDAR`, ya validado antes):

| Observado | Valor |
|---|---|
| Filas leídas | 3 |
| Resultado por fila | 2 `VALIDO`, 1 `NO_ENCONTRADO` (fila 8 del Excel) |
| Estado global | `OBSERVADO` · titular «PREVALIDACIÓN · 2 DE 3 FILAS VÁLIDAS» |
| Botones | `CONFIRMAR MASIVAMENTE (2)` · `VER OBSERVACIONES (1)` |
| Observación visible | «Fila 8 · DEPÓSITO NO ENCONTRADO …» |
| Tiempo mostrado | ≈ 22 s |

**CONFIRMAR MASIVAMENTE (2)**, pulsado UNA vez:

| Observado | Valor |
|---|---|
| Estado | `OK` · «CONFIRMACIÓN COMPLETADA» · «2 de 2 depósitos confirmados.» (titular y mensaje) |
| Tiempo mostrado | ≈ 11 s |
| Botón tras terminar | `CONFIRMAR MASIVAMENTE` **Disabled**; sin doble ejecución |
| Errores | ninguno visible en Power Apps ni en Power Automate |
| `Depositos_Activos` (revisión visual) | los 2 depósitos válidos pasaron a `ESTADO_ASIGNACION = ASIGNADO` con datos de asignación; la fila inválida NO se confirmó |

Cadena validada: Excel → PREVALIDAR → selección de solo `VALIDO` → CONFIRMAR MASIVAMENTE → `P9_MASIVA_PROTO_CONFIRMAR` → escritura real → `Depositos_Activos` → respuesta final a Power Apps.

**Flujo importado e inspeccionado a mano en Power Automate** (inspección visual de la definición, no del historial): `Leer_deposito` = GET con 2 reintentos fijos **PT5S**; el ETag fresco sale de `Leer_deposito`
(`coalesce(body('Leer_deposito')?['d']?['__metadata']?['etag'], outputs('Leer_deposito')?['headers']?['ETag'], '')`); `Actualizar_deposito` = POST, `X-HTTP-Method: MERGE`, `IF-MATCH` dinámico (no `*`),
directiva de reintentos **Ninguna**. La primera importación falló con `InvalidRetryPolicy` (PT2S < mínimo PT5S); corregido en `1448732`.

**Ajustes manuales en Power Apps Studio** (ya reflejados en el repo): al pegar el `OnSelect` de `btnConfirmarMasivamenteP9`, Studio rechazó `ShowColumns(…; "fila_excel"; …)` y aceptó los nombres **sin comillas**
(`ShowColumns(Filter(colPrevalidacionP9; resultado = "VALIDO"); fila_excel; deposito_id; …)`); la misma corrección se aplicó a `galObservacionesP9.Items`. Además se quitó el prefijo «PROTOTIPO · CONFIRMAR MASIVAMENTE»
del texto de `lblAvisoPrototipoP9`. `IfError` con ramas `true`/`false` fue aceptado por Studio.

### Lo que esta evidencia NO incluye
- No se registró el historial de la ejecución de Power Automate (duración por acción, entradas/salidas), ni los IDs de los depósitos, ni el hash del Excel.
- La comparación de `Depositos_Activos` fue visual («datos de asignación esperados»); **no** se verificó campo por campo contra los 8 campos de V4.2 (sí lo hace el simulador).
- Los tiempos (≈ 22 s y ≈ 11 s) son de **una** ejecución cada uno; no se sabe cuánto es fijo (arranque, conexiones) y cuánto es por fila. No se extrapolan: 2 filas ≈ 11 s **no** implica ≈ 5,5 s por fila.

## 2 · Matriz de validación

| Capacidad | REAL en tenant | Solo test / simulador | PENDIENTE |
|---|:-:|:-:|:-:|
| Importar `P9_MASIVA_PROTO_CONFIRMAR` (tras `PT5S`) | ✅ | | |
| Power Apps conectada al flujo y fórmulas A–Q aceptadas por Studio (con `ShowColumns` sin comillas) | ✅ | | |
| Prevalidar 3 filas → 2 `VALIDO`, 1 `NO_ENCONTRADO`, global `OBSERVADO` | ✅ | | |
| Enviar al flujo SOLO las filas `VALIDO` (la observada no se envía) | ✅ | ✅ | |
| Confirmación real 2/2 con UN clic; respuesta `OK` a Power Apps | ✅ | ✅ | |
| `Depositos_Activos` cambió a `ASIGNADO` (revisión visual) | ✅ | | |
| Botón `Disabled` tras confirmar; sin doble ejecución | ✅ | ✅ | |
| Expresiones del flujo en runtime real (camino feliz): `Scope`/`actions()`, `json()`, `min`/`max`, `formatNumber`, `convertTimeZone`, `item()` | ✅ (inferido: la ejecución de 2 filas terminó sin error) | ✅ | ramas de error |
| GET fresco por fila, ETag fresco, `IF-MATCH` dinámico, MERGE, retry none (definición del flujo importado) | ✅ (inspección visual) | ✅ | |
| Los 8 campos exactos de V4.2, sin otros campos, `CODIGO_ESTUDIANTE = ""`, `OBSERVACION` nunca `null` | ◐ (visual, no campo por campo) | ✅ | verificación campo por campo |
| `412` por carrera → `CONFLICTO` y el bucle continúa | | ✅ | |
| `CONFLICTO_DATOS` (cambió clave/tipo/fecha/banco/cuenta/código/importe/moneda entre prevalidar y confirmar) | | ✅ | |
| `NO_DISPONIBLE` por depósito asignado por otro usuario / reenvío idempotente | | ✅ | |
| Fallo técnico parcial (`ERROR_FILA`, `DESCONOCIDO`), lotes mixtos 47/2/1, sin rollback global | | ✅ | |
| Fila mal formada / `LOTE_EXCEDE_LIMITE` (> 50) | | ✅ | |
| Mutaciones de las reglas críticas (If-Match `*`, retry en MERGE, comillas, modal, envío de no-`VALIDO`) | | ✅ | |
| Confirmar **10** filas reales; **50** filas reales | | | ⏳ |
| Tiempo por fila, límite por tiempo de espera de Power Apps (≈ 120 s a verificar), timeout con flujo que sigue | | | ⏳ |
| Throttling / 429, cuota de solicitudes de Power Platform | | | ⏳ |
| Escalado a cientos / 1999 confirmaciones (trozos desde la app u otro diseño) | | | ⏳ |
| Tamaño de `detalle_json` como entrada (~650 KB con 1999 filas) | | | ⏳ |
| Efecto de los 2 reintentos de lectura (hasta ~10 s por fila ante fallo transitorio) | | | ⏳ |

Límite de V1: **50 filas `VALIDO` por llamada** (`PARAM_MAX_FILAS_POR_LLAMADA`), a propósito, hasta medir. La prevalidación acepta hasta 1999 filas. Sin rollback global, sin lotes ni historial.

## 3 · Estado del código

- `P9_MASIVA_PROTO_CONFIRMAR.zip` / definición: sin cambios desde `1448732` (sha256 del ZIP `28140399a428abe414990278672d29461d85a1b17bfbac8cf8c68674bef7f73f`).
- `P9_MASIVA_PROTO_PREVALIDAR`: sin cambios.
- Auditorías estáticas: `powerapps/auditar_iferror.py` (ramas de `IfError` booleanas; `ShowColumns` sin comillas) → 0 hallazgos sobre el export final.
