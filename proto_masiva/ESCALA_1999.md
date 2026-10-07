# P9 CONFIRMACIÓN MASIVA — Escala hasta 1999 filas con UN solo clic

> **Estado: implementada y probada con un SharePoint SIMULADO. NO validada en el tenant.**
> «1999 soportado por diseño» **no** significa «1999 validado en rendimiento». Lo que SÍ funcionó en el tenant es la **V1 síncrona** (2 filas, commit `82b279e`, ver `VALIDACION_TENANT_V1.md`).
> Esta versión **evoluciona** los mismos artefactos (no hay copias paralelas): `P9_MASIVA_PROTO_CONFIRMAR` (mismo nombre) + un flujo de consulta nuevo, `P9_MASIVA_PROTO_ESTADO`.

Rama `experiment/p9-masiva-prototipo`. La lógica por fila (GET fresco, ETag fresco, `IF-MATCH` concreto, MERGE sin reintentos, 412 = CONFLICTO, 8 campos de V4.2) **no cambió**; el cambio es CÓMO se
recorren las filas (en segundo plano) y CÓMO se informa el avance.

## 1 · Qué se verificó de Microsoft (y con qué certeza)

Clasificación: **DOCUMENTADO** (lo dice la documentación oficial de Microsoft) · **SIMULADO** (probado con el SharePoint falso del repositorio) · **INFERIDO** (deducido, no confirmado) · **PENDIENTE** (solo el uso real lo dirá).

| Dato | Valor | Certeza | Fuente |
|---|---|---|---|
| Tiempo máximo de una llamada entrante (Power Apps → flujo) | **120 s** (2 min) | DOCUMENTADO | [Límites de Power Automate · «Inbound request»](https://learn.microsoft.com/en-us/power-automate/limits-and-config) |
| ¿El flujo puede responder y seguir ejecutando acciones DESPUÉS? | **Sí.** «actions after the response action continue running beyond this limit, enabling a flow to respond and continue running other operations» | DOCUMENTADO | misma fila |
| ¿Sigue ejecutándose si se cierra Power Apps? | **Sí.** «continues to run even if you close Power Apps» | DOCUMENTADO | [Iniciar un flujo desde una aplicación de lienzo](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/using-logic-flows) |
| Duración máxima de una ejecución | **30 días** | DOCUMENTADO | Límites de Power Automate · «Run duration» |
| Acciones por definición de flujo | **500** (este flujo: 94) | DOCUMENTADO | Límites · «Actions per workflow» |
| Elementos en un «Aplicar a cada uno» | **5.000** (perfil Low) / **100.000** (resto); concurrencia 1–50 | DOCUMENTADO | Límites · «Apply to each array item / concurrency» |
| Directiva de reintentos | mínimo **5 s**, máximo 1 día, hasta 90 intentos | DOCUMENTADO | Límites · «Retry» (por eso `Leer_deposito` usa `PT5S`) |
| `string()`, `concat()`, `base64()` | **≤ 131.072 caracteres** | DOCUMENTADO | Límites · «Expression evaluation limit» |
| Tamaño de mensaje | **100 MB** | DOCUMENTADO | Límites · «Message size» |
| Variables por flujo | 250 (usamos 11) | DOCUMENTADO | Límites · «Variables per workflow» |
| Solicitudes de Power Platform | **100.000 / 5 min**; por 24 h: Low 10.000 · **Medium 200.000** · High 500.000. Los flujos disparados por Power Apps están en el perfil **Medium** | DOCUMENTADO | Límites · «Power platform requests» y «Performance profiles» |
| Qué cuenta como solicitud | **cada acción**, exitosa o fallida, incluidos reintentos | DOCUMENTADO | [Límites y asignaciones de solicitudes](https://learn.microsoft.com/en-us/power-platform/admin/api-request-limits-allocations) |
| Solicitudes por licencia y por 24 h | Power Automate Premium 40.000/usuario · Microsoft 365 y Free **6.000**/usuario (periodo de transición: 10.000 por flujo) | DOCUMENTADO | misma página |
| Si se excede | «flows slow down» (se ralentizan); la aplicación estricta aún no rige | DOCUMENTADO | misma página |
| Conector SharePoint | **600 llamadas por conexión cada 60 s**; excederlo da HTTP 429 | DOCUMENTADO* | [Conector SharePoint](https://learn.microsoft.com/en-us/connectors/sharepointonline/) |
| ¿La acción «Enviar una solicitud HTTP a SharePoint» consume esas 600? | no confirmado | **NO CONFIRMADO** | — |
| **Tamaño máximo del input de TEXTO del trigger Power Apps (V2)** | **no existe un límite documentado** | **NO DOCUMENTADO** | búsqueda sin resultado oficial |
| Tiempo real por fila en el tenant | única medición: V1 con 2 filas ≈ 11 s extremo a extremo | PENDIENTE | no se extrapola |

\* La documentación en línea (`learn.microsoft.com`) no era accesible desde el entorno de construcción: los límites de Power Automate, Power Platform y Power Apps se leyeron del **código fuente público de esa
documentación** (repositorios `MicrosoftDocs/power-automate-docs`, `MicrosoftDocs/power-platform`, `MicrosoftDocs/powerapps-docs`, 2026-10-07). El límite de 600 llamadas del conector de SharePoint se obtuvo del
resultado de una búsqueda sobre la página del conector (no se leyó la página completa). **Verifica los números vigentes de TU licencia en el centro de administración.**

## 2 · Arquitectura elegida

```
Power Apps  ── Run(detalle_json, usuario_email) ─►  P9_MASIVA_PROTO_CONFIRMAR
                                                    PREPARAR   validar · contar · crear confirmacion_<uid>.json (PROCESANDO)   ← 35 acciones, NO dependen de N
                                         ◄─ ACEPTADO + execution_uid ──  RESPONDER   (en segundos)
                                                    PROCESAR   (el flujo SIGUE)  preparar filas → Para_cada_fila (secuencial)
                                                               cada 25 filas: actualiza el estado (solo contadores)
                                                    FINALIZAR  estado TERMINADO + SOLO las filas no confirmadas
Power Apps  ── cada 15 s (Temporizador) ── Run(execution_uid) ─►  P9_MASIVA_PROTO_ESTADO (solo lectura) ─► avance / resultado final
```

- **Un solo clic hasta 1999.** El clic envía las N filas `VALIDO` y recibe `ACEPTADO` en segundos. El procesamiento ocurre DESPUÉS de responder, donde ya no aplica el límite de 120 s (DOCUMENTADO) y puede durar hasta 30 días.
- **Mismo `P9_MASIVA_PROTO_CONFIRMAR`**: evoluciona (mismo nombre, mismas dos entradas de texto). **No** se creó `_V2`, `_1999`, `_TEST` ni copias.
- **`P9_MASIVA_PROTO_ESTADO`**: único flujo nuevo, necesario porque Power Apps no puede leer un archivo de `P9_MASIVA_TEMP` y el flujo de confirmación ya respondió. Es de solo lectura. **No hace falta un worker** (el flujo
  puede continuar tras responder, documentado).
- **Transferencia del payload de 1999 filas:** directa por la entrada de texto `detalle_json` (≈ 0,55–0,6 MB; ≈ 300 bytes por fila). **No** se usa archivo intermedio: el límite documentado de mensaje es 100 MB y no hay límite
  documentado para el input de texto del trigger. Es la única hipótesis **INFERIDA** de la arquitectura (ver §6); el JSON solo pasa por `json()`, `length()`, `Select` y `Query`, **nunca** por `string()`/`concat()`/`base64()`
  (límite de 131.072 caracteres): lo verifica `test_el_payload_nunca_pasa_por_string_concat_ni_base64`.
- **Progreso:** archivo `confirmacion_<execution_uid>.json` en `Documents/P9_MASIVA_TEMP` (la misma carpeta técnica que ya usa la prevalidación). Se crea con `PROCESANDO`, se actualiza cada **25 filas** (solo contadores, < 1 KB) y se
  cierra con `TERMINADO` (o `ERROR` si el proceso se interrumpe) con **solo las filas no confirmadas** (como máximo 300, ver §4). No es historial ni lote: un archivo por ejecución, sin limpieza automática (se puede borrar a mano; retención sugerida: 24 h).
- **Si Power Apps se cierra:** el backend continúa (DOCUMENTADO). En esta versión NO se recupera el seguimiento al volver (fuera de alcance): se vuelve a PREVALIDAR y lo ya confirmado aparece `NO_DISPONIBLE`.
- **Sin rollback global; sin cambios en la lógica por fila:** `GET` fresco, `ETag` fresco, `IF-MATCH` concreto (nunca `*`), `MERGE` sin reintentos, `412` = `CONFLICTO`, `Leer_deposito` 2 reintentos fijos `PT5S`, secuencial (concurrencia 1), los 8 campos de V4.2.

## 3 · Contrato

| | `P9_MASIVA_PROTO_CONFIRMAR` (respuesta TEMPRANA, 5 textos) | `P9_MASIVA_PROTO_ESTADO` (entrada: `execution_uid`; 9 textos) |
|---|---|---|
| Éxito | `resultado=ACEPTADO` · `codigo=PROCESAMIENTO_INICIADO` · `mensaje` · `execution_uid` · `filas_recibidas` | `estado` (PROCESANDO / TERMINADO / ERROR / NO_ENCONTRADO) · `filas_totales` · `filas_procesadas` · `filas_confirmadas` · `filas_no_confirmadas` · `porcentaje` · `mensaje` · `detalle_json` · `tiempos_ms` |
| Error antes de procesar | `resultado=ERROR` · `codigo` = `ENTRADA_INVALIDA` · `SIN_FILAS` · `LOTE_EXCEDE_LIMITE` · `ERROR_ESTADO` (no se confirmó nada; `execution_uid` vacío) | — |

`detalle_json` (solo al terminar): arreglo con las filas **no confirmadas** (`fila_excel, deposito_id, resultado, mensaje, estado_final, banco, cuenta_bancaria, codigo_asignacion, importe, moneda`; `resultado` ∈ `NO_ENCONTRADO,
NO_DISPONIBLE, CONFLICTO, CONFLICTO_DATOS, ERROR_FILA`). Ejemplos generados: `flows/ejemplos_respuesta_confirmacion/` (incluye un estado intermedio «50 de 60 procesados»).

**El contrato de `P9_MASIVA_PROTO_CONFIRMAR` CAMBIÓ** (antes devolvía 8 textos con el resultado final): hay que **quitar y volver a agregar el flujo** en Power Apps (ver `flows/INSTRUCCIONES_CONFIRMAR.md`).

## 4 · El límite de 131.072 caracteres obliga a limitar el detalle

El archivo de estado se escribe con `string()` (≤ 131.072 caracteres, DOCUMENTADO). Por eso **no se guardan las filas confirmadas** (solo se cuentan) y el detalle de no confirmadas se limita a **300 entradas**
(≈ 330 bytes cada una = ≈ 100.000 caracteres, con margen). Si hubiera más, `detalle_truncado = true`, los contadores siguen siendo exactos y el mensaje dice qué hacer (volver a PREVALIDAR). Si aun así la escritura fallara
(textos anormalmente largos), un **respaldo mínimo** escribe el estado final sin detalle. Con 21 fallidas de 1999 (el ejemplo pedido) el archivo final pesa ≈ 6 KB.

## 5 · Estimación de solicitudes para 1999 filas

Medida con la ejecución simulada (`test_solicitudes_estimadas_para_1999_filas`); **cada acción cuenta como una solicitud de Power Platform** (DOCUMENTADO):

| Concepto | Cantidad |
|---|---|
| Acciones por fila (camino feliz: Scope, GET, Cambio, ETag, Revalidación, Condición, Cuerpo, MERGE, +1 confirmada, +1 procesada, +1 condición de avance) | ≈ **11,1** |
| Acciones de `P9_MASIVA_PROTO_CONFIRMAR` para 1999 filas | **≈ 22.200** |
| de ellas, llamadas a SharePoint: 1999 GET + hasta 1999 MERGE + 1 crear + 79 avances + 1 final | **≈ 4.060** (con 21 fallidas) · ≈ 4.080 si las 1999 se confirman |
| Avances de estado (1 cada 25 filas) | 79 escrituras |
| Seguimiento: `P9_MASIVA_PROTO_ESTADO` cada 15 s ejecuta 12 acciones | ≈ **2.900 acciones por hora** de confirmación |

- **Límite diario:** perfil Medium = 200.000 solicitudes/24 h (DOCUMENTADO) → una confirmación de 1999 filas usa ≈ 11 % (más el seguimiento). **Pero** la asignación **por licencia** puede ser mucho menor: con Microsoft 365 / Free
  (6.000 por usuario; 10.000 en la transición) una sola confirmación de 1999 filas **la excedería**; con Power Automate Premium (40.000) cabe una. Superar el límite **ralentiza** los flujos (DOCUMENTADO), no los bloquea hoy.
  **Verifica tu licencia antes de confirmar volúmenes grandes.**
- **SharePoint (600 llamadas/min por conexión):** el procesamiento es secuencial, ≈ 2 llamadas por fila; solo se alcanzaría si cada fila tardara < 0,2 s. A 5 s por fila serían ≈ 24 llamadas/min (INFERIDO). Un 429 en la lectura se reintenta
  (2 × `PT5S`); en el MERGE **no** se reintenta (queda `ERROR_FILA`, «verifique antes de reintentar»).
- **Duración:** el tiempo por fila es PENDIENTE de medir. Solo como orden de magnitud (NO como dato): a 3–5 s por fila, 1999 filas serían ≈ 1,7–2,8 h, muy por debajo de los 30 días.

## 6 · Qué está validado y qué no

| | Estado |
|---|---|
| Respuesta a Power Apps ANTES de la primera lectura de un depósito; trabajo previo independiente de N (35 acciones) | SIMULADO |
| Procesamiento posterior a la respuesta, avance cada 25, estado inicial / intermedio / final, detalle solo de fallidas | SIMULADO |
| 1 / 50 / 51 / 1999 filas; 1999 con 12 NO_DISPONIBLE + 5 CONFLICTO + 4 ERROR_FILA → 1978 confirmadas, 21 no confirmadas; 2000 rechazadas | SIMULADO |
| Payload de 1999 filas (≈ 0,6 MB típico; ≈ 8,6 MB en un peor caso absurdo) vs 100 MB | SIMULADO + DOCUMENTADO (100 MB) |
| `string()` > 131.072 → respaldo mínimo; fallo al escribir un avance no detiene las confirmaciones | SIMULADO |
| Flujo de estado: avance, final, NO_ENCONTRADO, `execution_uid` inválido (lista blanca, sin rutas) | SIMULADO |
| Doble clic bloqueado; Temporizador se detiene (TERMINADO / ERROR / 5 fallos seguidos); `ShowColumns` sin comillas; `IfError` 0 incompatibles | ESTÁTICO (YAML/Power Fx) |
| El flujo continúa tras responder y tras cerrar Power Apps | DOCUMENTADO (no probado en el tenant) |
| Input de texto de ≈ 0,6 MB en el trigger Power Apps V2 | **INFERIDO** (sin límite documentado) |
| `CreateFile` / `UpdateFile` / `GetFileContentByPath` sobre `Documents/P9_MASIVA_TEMP` en el tenant (rutas, `Id`) | **PENDIENTE** (la carpeta y `CreateFile` sí se validaron con la prevalidación; `UpdateFile` y la lectura por ruta no) |
| Control Temporizador (versión del tipo en el YAML) y fórmulas en Studio | **PENDIENTE** |
| Tiempo por fila, 10 / 50 / 500 / 1999 reales, throttling, cuota por licencia | **PENDIENTE** (el uso real dará las métricas) |

### Riesgos conocidos (no ocultos)
1. **Input grande:** si Power Apps o el trigger rechazaran ≈ 0,6 MB, la llamada fallaría con «El flujo no respondió…» sin confirmar nada (el flujo ni arranca). Alternativa mínima ya identificada, **no implementada**: enviar por trozos con el mismo `execution_uid`.
2. **Estado colgado:** si SharePoint rechazara TODAS las escrituras del estado (avance y final), los depósitos SÍ se confirmarían pero el archivo quedaría en `PROCESANDO` (probado: `test_limitacion_conocida…`). Power Apps seguiría consultando; salir de la pantalla lo reinicia y PREVALIDAR muestra la realidad.
3. **Ejecución cancelada a mano** en Power Automate: igual que (2); lo confirmado queda confirmado.
4. **Cuota de solicitudes por licencia** (§5).
5. **Archivos `confirmacion_*.json`** se acumulan en `P9_MASIVA_TEMP` (como los `TMP_*.xlsx` de la prevalidación): no hay limpieza automática.
