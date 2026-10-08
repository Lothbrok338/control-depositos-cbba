# P10-A.1 · Revisión del contrato de AUDITORIA frente al esquema REAL de `Depositos_Activos`

Objetivo: que cuando P10-B elimine un registro de `Depositos_Activos`, la hoja AUDITORIA conserve **toda la información relevante que existía realmente en ese registro**, no solo el contrato original de P0 (26 columnas) si la lista evolucionó después.

**Fuentes (todas en el repo, más la captura del tenant):** `p8/esquema_listas_p8.json` (34 columnas) · `p9/reversion/esquema_reversiones.json` (`Depositos_Activos`: «solo adiciones», +1) · `p9/contrato.py` y `p9/reversion/contrato.py` (qué escriben los flujos) · `adaptador_m365.py` (nombres P0 ↔ nombres internos) · `DISENO_LISTA_DEPOSITOS_ACTIVOS.md` §4 · captura del selector de columnas del tenant aportada por Gabriel (2026-10-08). Ningún otro flujo —ni la confirmación masiva (`proto_masiva`)— escribe o lee campos fuera de estas 35 columnas.

## 1. Esquema actual real de `Depositos_Activos` (según repo y confirmado por la captura del tenant)

**35 columnas propias** (34 de P8/P9 + `ULTIMA_REVERSION_ID` de P9-reversión), más las columnas de sistema de SharePoint. Los nombres de las 35 en la captura coinciden uno a uno con el esquema del repo («Última reversión aplicada» es el nombre para mostrar de `ULTIMA_REVERSION_ID`); no hay ninguna columna propia en el tenant que el repo no conozca (lo fija la prueba `test_el_esquema_del_repo_coincide_con_las_35_columnas_propias_del_tenant`).

## 2. Correspondencia columnas P0 ↔ columnas de la lista

| P0 (`COLUMNAS_LISTS`) | Nombre interno en la lista | Observación |
|---|---|---|
| 19 columnas: `CLAVE TRANSACCIÓN`, `CÓDIGO DE ASIGNACIÓN`, `BANCO`, `CUENTA BANCARIA`, `MONEDA`, `FECHA MOVIMIENTO`, `HORA MOVIMIENTO`, `IMPORTE`, `DÉBITO`, `CRÉDITO`, `TIPO MOVIMIENTO`, `SALDO`, `DESCRIPCIÓN`, `DEPOSITANTE / ORIGINANTE`, `INFORMACIÓN ADICIONAL`, `TEXTO DE BÚSQUEDA`, `ARCHIVO ORIGEN`, `LOTE DE CARGA`, `FECHA DE CARGA` | mismo nombre sin acentos/espacios (`CLAVE_TRANSACCION`, …, `FECHA_CARGA`) | los carga P7; ningún flujo posterior los cambia |
| `ESTADO` | `MOTOR_ESTADO` | columna **reservada**: constante de P0 (`DISPONIBLE`); nadie la escribe después |
| `ESTUDIANTE` | `MOTOR_ESTUDIANTE` | reservada, vacía |
| `SOLICITADO POR` | `MOTOR_SOLICITADO_POR` | reservada, vacía |
| `SEDE SOLICITANTE` | `MOTOR_SEDE_SOLICITANTE` | reservada, constante de P0 (`COCHABAMBA`) |
| `CONFIRMADO POR` | `MOTOR_CONFIRMADO_POR` | reservada, vacía |
| `FECHA CONFIRMACIÓN` | `MOTOR_FECHA_CONFIRMACION` | reservada, vacía (texto) |
| `OBSERVACIÓN` | `MOTOR_OBSERVACION` | reservada, vacía |

Decisión D-1 de P7/P8: las 7 columnas homónimas del motor llevan prefijo `MOTOR_` y quedan **reservadas**; los datos operativos **vivos** están en otras columnas de la misma lista:

| Concepto (P0) | Columna VIVA en la lista (P9) | Escribe |
|---|---|---|
| `ESTADO` | `ESTADO_ASIGNACION` (`DISPONIBLE` / `ASIGNADO`) | P9 asignar / masiva / reversión |
| `ESTUDIANTE` | `ESTUDIANTE` | ídem |
| `SOLICITADO POR` | `SOLICITADO_POR` | ídem |
| `SEDE SOLICITANTE` | `SEDE_ASIGNACION` | ídem |
| `CONFIRMADO POR` | `USUARIO_ASIGNACION` | ídem |
| `FECHA CONFIRMACIÓN` | `FECHA_HORA_ASIGNACION` (fecha y hora) | ídem |
| `OBSERVACIÓN` | `OBSERVACION` | ídem |
| *(sin equivalente en P0)* | `CODIGO_ESTUDIANTE` | P9 asignar (puede ir vacío) |
| *(sin equivalente en P0)* | `ULTIMA_REVERSION_ID` | P9 reversión (no se borra nunca) |

## 3. Clasificación de cada columna que preguntaste

| Campo | 1 · nombre interno/equivalente de una de las 26 | 2 · columna adicional real de `Depositos_Activos` | 3 · pertenece a otra lista | 4 · solo en el snapshot simulado |
|---|---|---|---|---|
| `ESTADO_ASIGNACION` | **Sí** — equivalente vivo de `ESTADO` (la columna física de P0 es `MOTOR_ESTADO`, constante) | — | — | No |
| `USUARIO_ASIGNACION` | **Sí** — equivalente vivo de `CONFIRMADO POR` | — | — | No |
| `FECHA_HORA_ASIGNACION` | **Sí** — equivalente vivo de `FECHA CONFIRMACIÓN` | — | — | No |
| `CODIGO_ESTUDIANTE` | No (P0 no tiene columna equivalente) | **Sí** (P8 #29; el flujo V4.2 sigue escribiéndolo, puede ir `""`) | — | No |
| `ULTIMA_REVERSION_ID` | No | **Sí** (P9-reversión: «solo adiciones», texto 255, opcional, sin índice) | — | No |

* **Categoría 3 (otra lista):** `Depositos_Reversiones` (41 columnas propias: `SOLICITUD_UID`, `DEPOSITO_ID`, `CLAVE_BLOQUEO`, `SNAPSHOT_JSON`, `ESTADO_SOLICITUD`, `FASE_PROCESO`…, que además guarda **copias** de `ESTUDIANTE`, `CODIGO_ESTUDIANTE`, `USUARIO_ASIGNACION`, `FECHA_HORA_ASIGNACION`, `OBSERVACION`), `Depositos_Cargas` (bitácora de lotes P7/P8) y la lista `Confirmaciones_Masivas`, que solo existe como diseño. Nada de esto es columna de `Depositos_Activos`.
* **Categoría 4 (solo en la simulación):** ninguna de las cinco. Lo que existe **solo** en la simulación es el envoltorio del snapshot (`version`, `origen`, `fecha_corte`), los *valores* inventados (`ESTUDIANTE SIMULADO …`, usuarios `@example.invalid`, historia de reversiones simulada) y la traducción de presentación `ASIGNADO → CONFIRMADO`.
* **Columnas de sistema de SharePoint** (visibles en la captura; no están definidas en el esquema del repo): `ID`, `Creado`, `Creado por`, `Modificado`, `Modificado por`, `Título`, `Tipo`, `Datos adjuntos`, `Id. de activo de cumplimiento normativo`, `Número secundario de elemento`, `Recuento secundario de carpetas`, y las de etiquetas de retención / «El elemento es un registro». Ver §5.

## 4. Conclusión y contenido de AUDITORIA

**Las 26 columnas de P0 NO contenían toda la información persistida relevante:** faltaban `CODIGO_ESTUDIANTE` y `ULTIMA_REVERSION_ID`. Todo lo demás de la lista está cubierto: 19 columnas P0 sin cambios + 7 columnas vivas que ocupan las 7 columnas P0 homónimas.

**AUDITORIA = 28 columnas** (cambio mínimo, solo en AUDITORIA; EXTRACTO, P0, P7, P8 y P9 no cambian):

1. Las **26 de `COLUMNAS_LISTS`**, en su orden y con sus nombres exactos (las 7 operativas llevan el valor VIVO de la lista).
2. `CODIGO_ESTUDIANTE` y `ULTIMA_REVERSION_ID` **al final**, con su nombre interno real de la lista (texto, formato `@`: conserva ceros iniciales).

Qué NO duplica y por qué:

* **`MOTOR_*` (7 columnas):** son constantes de P0 que ningún flujo escribe (`CAMPOS_ESCRITOS` de P9 asignar y de reversión no incluye ninguna —lo comprueba una prueba—; la confirmación masiva declara escribir solo los mismos campos que la individual, `proto_masiva/CONFIRMACION_MASIVA.md`). Duplicarlas aportaría `DISPONIBLE`/`COCHABAMBA`/vacío. *Recomendación para P10-B:* antes de borrar, comparar `MOTOR_*` con esas constantes y advertir si alguna difiere (edición manual en SharePoint).
* **`ESTADO_ASIGNACION` crudo:** la traducción `ASIGNADO → CONFIRMADO` (`ESTADO_VISIBLE`) es 1:1 y reversible; no se pierde información.

## 5. Decisión abierta (única): columnas de sistema de SharePoint

`ID`, `Creado/Modificado` y `Creado por/Modificado por` existen en cualquier lista pero **no están en el esquema del repo** y no salen de P0 ni del snapshot actual; añadirlas exige que el lector real de la lista (P10-A.2) las entregue, y en la simulación habría que inventar sus valores, por eso **no se incluyeron**. Evaluación:

* `ID`: P9 lo guarda en su snapshot de reversión, pero la `CLAVE TRANSACCIÓN` ya identifica el registro y `Depositos_Reversiones` también la guarda: aporta poco.
* `Creado` ≈ `FECHA DE CARGA`/`LOTE DE CARGA`; `Modificado` ≈ `FECHA_HORA_ASIGNACION` (o la fecha de la reversión, que vive en `Depositos_Reversiones`).
* `Creado por`/`Modificado por`: en las filas visibles de la captura muestran la misma cuenta (la que ejecuta los flujos), así que **no** identifican a quien confirmó; ese dato es `USUARIO_ASIGNACION`.

**Recomendación:** no agregarlas. Si Gabriel quiere trazabilidad técnica de SharePoint, la opción de menor costo es solo `ID` al final de AUDITORIA; hay que decidirlo antes de P10-A.2.

## 6. Cuando la lista evolucione

* **En el repo ya está protegido:** `test_auditoria_cubre_cada_columna_real_de_depositos_activos` falla si el esquema de `Depositos_Activos` gana una columna que AUDITORIA no clasifica (fija/viva/adicional/reservada).
* **En ejecución (pendiente, P10-A.2):** el lector real debe avisar —no ignorar en silencio— de cualquier columna propia que no esté entre las 35 conocidas.
* **P10-B:** `Depositos_Reversiones` guarda por separado el historial de reversiones (`SOLICITUD_UID` = `ULTIMA_REVERSION_ID`); si se limpia, debe archivarse aparte antes.
