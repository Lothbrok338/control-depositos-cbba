# P9 CONFIRMACIÓN MASIVA — Confirmar solo las filas que siguen siendo VALIDO

> **Estado: implementada y probada con un SharePoint SIMULADO; NO validada en tu tenant.** El flujo **escribe** en `Depositos_Activos` (confirma depósitos): léelo antes de probar.
> Esta fase termina con el flujo listo para probar manualmente en `P9_PRUEBA_MASIVA`. No se importó nada, no se tocó el tenant, no se publicó ninguna app.

Rama `experiment/p9-masiva-prototipo`. Todo vive bajo `proto_masiva/`. `P9_ASIGNAR_DEPOSITO` (V4.2), confirmación individual, reversión, PDF, motor, P8 y el esquema de `Depositos_Activos` **no se tocaron**: V4.2 se usó solo como referencia (el repositorio lo comprueba con tests).

## 1 · UX y arquitectura

```
… PREVALIDAR (colPrevalidacionP9, solo en memoria) → revisar observaciones → UN clic: CONFIRMAR MASIVAMENTE (N)
        Power Apps ─ JSON(solo las filas VALIDO) + User().Email ─► P9_MASIVA_PROTO_CONFIRMAR   (la app ESPERA la respuesta)
              por cada fila, UNA DETRÁS DE OTRA:  releer el depósito → ¿algo relevante cambió? → ETag fresco → MERGE con If-Match → anotar el resultado
        ◄─ resultado global + detalle por fila ─ Power Apps muestra «47 de 50 confirmados · 3 requieren revisión» (mismo panel, sin segundo modal)
```

No hay: segundo modal, doble confirmación, lotes persistentes, historial de lotes, listas nuevas, rollback global, sondeo ni temporizador. El resultado por fila vive solo en `colConfirmacionP9` (memoria de la app).

- **Un flujo nuevo**, `P9_MASIVA_PROTO_CONFIRMAR` (Power Apps V2, 2 entradas de texto `detalle_json` y `usuario_email`). **No modifica** `P9_MASIVA_PROTO_PREVALIDAR` (salvo el mensaje del límite de 1999 filas, ver §8).
- **Secuencial** (`Apply to each` con concurrencia 1) y **un `Scope` por fila**: un error en una fila se convierte en el resultado de esa fila y el bucle **continúa**. Sin concurrencia hasta medir.
- **No se confía en la prevalidación:** cada depósito se **relee** antes de escribir y se descarta cualquier ETag anterior.

## 2 · Cómo se preservó V4.2 (fuente de verdad: `p9/asignar/flujo_asignar_powerapps_v4_2_definition.json`)

| Elemento | V4.2 (validado en tenant) | Confirmación masiva |
|---|---|---|
| Sitio / lista | `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` · `296c450a-25d6-415b-ad10-c909c74817cb` | **idénticos** (`p9/contrato.py`) |
| Lectura por ID | `GET _api/web/lists(guid'…')/items(<ID>)?$select=Id,CLAVE_TRANSACCION,ESTADO_ASIGNACION,USUARIO_ASIGNACION,FECHA_HORA_ASIGNACION`, `Accept: application/json;odata=verbose`, resultado en `body.d` | misma URI y cabecera; el `$select` **añade** `TIPO_MOVIMIENTO, FECHA_MOVIMIENTO, BANCO, CUENTA_BANCARIA, CODIGO_ASIGNACION, IMPORTE, MONEDA` (los mismos nombres internos ya usados por la prevalidación) |
| Reintentos de la lectura | ninguno | **2 reintentos fijos (PT2S)** — única diferencia: es solo lectura y mitiga errores transitorios 429/5xx |
| Comprobación de clave | `CLAVE_TRANSACCION` ≠ la enviada → `CLAVE_NO_COINCIDE` | → `CONFLICTO_DATOS` |
| Comprobación de estado | `ESTADO_ASIGNACION` ≠ `DISPONIBLE` → `NO_DISPONIBLE` | igual: `NO_DISPONIBLE` (con el estado real) |
| ETag | `coalesce(d.__metadata.etag, headers.ETag, '')`; vacío → `SIN_ETAG` (no escribe) | **la misma expresión**, sobre la lectura **de esa fila**; vacío → `ERROR_FILA` (no escribe) |
| Escritura | `POST` + `X-HTTP-Method: MERGE` + `IF-MATCH: <ETag>`, `Accept`/`Content-Type: application/json;odata=nometadata`, cuerpo `string(Cuerpo_actualizacion)` | **la misma llamada**, URI idéntica, mismas cabeceras (el test compara cabecera a cabecera) |
| Reintentos del MERGE | **ninguno** | **ninguno** (`retryPolicy: none`) |
| 412 | `CONFLICTO` | `CONFLICTO` y **continúa** con las demás filas |
| 404 al leer | `DEPOSITO_NO_ENCONTRADO` | `NO_ENCONTRADO` |
| Otros fallos del MERGE | `ACTUALIZACION_NO_CONFIRMADA` («verifique el depósito antes de reintentar») | `ERROR_FILA` con el mismo consejo; `estado_final = DESCONOCIDO` |

Además (exigido por esta fase, V4.2 no lo comprobaba): `TIPO_MOVIMIENTO = CRÉDITO`, `FECHA_MOVIMIENTO` dentro de la **misma ventana de 2 meses** de la galería (hoy-2 meses ≤ fecha ≤ hoy, hora de Bolivia, igual que la prevalidación), y `BANCO`, `CUENTA_BANCARIA`, `CODIGO_ASIGNACION`, `IMPORTE`, `MONEDA` iguales a lo prevalidado (texto sin distinguir mayúsculas ni espacios; `IMPORTE` en centavos enteros).

## 3 · Campos escritos (exactamente los 8 de V4.2, en su orden)

| Campo | Valor | Misma fuente que V4.2 |
|---|---|---|
| `ESTADO_ASIGNACION` | `ASIGNADO` | literal |
| `ESTUDIANTE` | `estudiante` de la fila (recortado) | sí |
| `CODIGO_ESTUDIANTE` | **`""`** | la confirmación individual envía `""` (`Main_Screen.yaml`, 4.º argumento de `P9_ASIGNAR_DEPOSITO.Run`) |
| `SOLICITADO_POR` | `solicitado_por` (recortado) | sí |
| `SEDE_ASIGNACION` | `sede` (recortada; nunca se autocompleta) | sí |
| `OBSERVACION` | texto recortado, **`""` si está vacío (nunca `null`)** | igual que V4.2 (`trim(coalesce(…,''))`) |
| `USUARIO_ASIGNACION` | `usuario_email` = `User().Email` | la app individual pasa `User().Email` |
| `FECHA_HORA_ASIGNACION` | `utcNow()` **por fila** | misma semántica que `Ahora` de V4.2 |

**Ningún otro campo de `Depositos_Activos` se escribe** (el simulador rechaza un cuerpo con otras claves y los tests comprueban que el resto de columnas no cambia). Limitación heredada: `usuario_email` lo envía el cliente, igual que en la confirmación individual (el flujo no puede verificar la identidad).

## 4 · Mecanismo ETag / If-Match

1. `Leer_deposito` (GET por ID) devuelve el elemento **con su ETag actual** (`d.__metadata.etag`).
2. `ETag_fresco` toma ese valor; si falta → `ERROR_FILA`, **no se escribe**.
3. `Actualizar_deposito` envía `IF-MATCH: <ese ETag>` — **nunca `*`** (el simulador aborta la prueba si aparece) y **sin reintentos**.
4. Si otro usuario tocó el elemento entre la lectura y la escritura, SharePoint responde **412** → `CONFLICTO` y no se aplica nuestra confirmación.
5. No existe ningún ETag guardado entre filas ni entre la prevalidación y la confirmación; el ETag **no viaja** a Power Apps.

## 5 · Fallos parciales — sin rollback global

Lo confirmado **permanece confirmado**. Ejemplo (probado): 50 filas VALIDO; una la asignó otro usuario y dos sufren un conflicto de concurrencia → **47 `CONFIRMADO`, 2 `CONFLICTO`, 1 `NO_DISPONIBLE`**, resultado global `PARCIAL`; las 47 siguen en `ASIGNADO` y no se escribe nada para «revertir».

Resultados por fila: `CONFIRMADO`, `NO_ENCONTRADO`, `NO_DISPONIBLE`, `CONFLICTO` (412), `CONFLICTO_DATOS` (cambió clave, tipo, fecha o BANCO/CUENTA/CÓDIGO/IMPORTE/MONEDA) y `ERROR_FILA` (fila mal formada, fallo técnico al leer o escribir, sin ETag).
Orden de las comprobaciones: **ID → CLAVE → ESTADO → TIPO → FECHA → BANCO → CUENTA → CÓDIGO → IMPORTE → MONEDA**. Si ya estaba `ASIGNADO` por otro usuario (datos iguales) → `NO_DISPONIBLE`; si la clave cambió (otro depósito) → `CONFLICTO_DATOS`.
Una fila mal formada (ID no válido, campos vacíos, >255 caracteres, importe o moneda inválidos) es `ERROR_FILA` **sin llamar a SharePoint**.

**Reenviar el mismo lote no duplica nada:** las filas ya confirmadas salen `NO_DISPONIBLE` (estado `ASIGNADO`) y no se vuelve a escribir.

## 6 · Contratos

**Entrada** (`Run(detalle_json; usuario_email)`, ambas de texto, ambas requeridas):

- `detalle_json`: arreglo JSON con las filas `VALIDO` de `colPrevalidacionP9`, producido por `JSON(ShowColumns(Filter(colPrevalidacionP9; resultado = "VALIDO"); "fila_excel"; "deposito_id"; "clave_transaccion"; "banco"; "cuenta_bancaria"; "codigo_asignacion"; "importe"; "moneda"; "estudiante"; "solicitado_por"; "sede"; "observacion"); JSONFormat.Compact)`. **No se envían filas observadas.** No hay `codigo_estudiante`: lo escribe el flujo como `""`.
- `usuario_email`: `User().Email`.

**Salida** (8 textos): `resultado` (`OK` todas confirmadas · `PARCIAL` algunas o ninguna confirmadas · `ERROR` no se pudo iniciar/procesar el lote), `codigo`, `mensaje`, `filas_recibidas`, `filas_confirmadas`, `filas_no_confirmadas`, `detalle_json`, `tiempos_ms` (`total=…;filas=…;ms_por_fila=…`).

| `resultado` | `codigo` | Cuándo |
|---|---|---|
| `OK` | `CONFIRMACION_OK` | todas confirmadas |
| `PARCIAL` | `CONFIRMACION_PARCIAL` | al menos una confirmada y al menos una no |
| `PARCIAL` | `NINGUNA_CONFIRMADA` | se procesó el lote pero ninguna se confirmó (la UI muestra «NO SE CONFIRMÓ NINGÚN DEPÓSITO») |
| `ERROR` | `ENTRADA_INVALIDA` | faltan entradas o `detalle_json` no es un arreglo JSON; no se toca SharePoint |
| `ERROR` | `SIN_FILAS` | arreglo vacío |
| `ERROR` | `LOTE_EXCEDE_LIMITE` | más filas que el máximo por llamada (o que 1999); **no se confirma nada** |
| `ERROR` | `ERROR_NO_CONTROLADO` | fallo fuera de las filas: el proceso se interrumpió; **algunos depósitos pueden haberse confirmado** y el resumen cuenta lo ya anotado |

**`detalle_json`** (texto JSON, un objeto por fila recibida; esquema `flows/esquema_detalle_confirmacion_json.json`, ejemplos `flows/ejemplos_respuesta_confirmacion/`): `fila_excel`, `deposito_id`, `resultado`, `mensaje`, `estado_final`, `banco`, `cuenta_bancaria`, `codigo_asignacion`, `importe`, `moneda`. **No devuelve ETag.** `estado_final` = `ASIGNADO` si se confirmó; el estado real leído si no estaba `DISPONIBLE`; `DESCONOCIDO` tras un intento de escritura que falló **sin** 412 (no se sabe si SharePoint lo aplicó: re-PREVALIDAR); vacío si no se llegó a leer o hubo 412.

## 7 · Escala: qué se sabe y qué NO

**No se afirma que 1999 confirmaciones síncronas funcionen.** Es un flujo síncrono: la app espera la respuesta. Análisis (todo lo numérico es **estimación o recuerdo, no medido**):

1. **Tiempo por fila.** Cada fila hace 1 GET + 1 POST a SharePoint más 7 acciones internas (9 acciones por fila en el camino feliz, contando el `Scope`). El único dato propio disponible es que, en las mediciones de la prevalidación, `CrearArchivo` tardó ~1,7–2,2 s. **Si** cada llamada a SharePoint costara del orden de 1–2 s, una fila costaría ~3–5 s y 50 filas ~2,5–4 min. **Eso es una hipótesis**: se mide en el tenant con 1, 3, 10 y 50 filas (`tiempos_ms` devuelve `total`, `filas` y `ms_por_fila`).
2. **Timeout Power Apps → flujo.** Recuerdo un límite del orden de **120 s** de espera de la respuesta síncrona (no pude consultar la documentación de Microsoft desde el entorno de construcción: **verifícalo**). Si se supera, la app recibe un error **pero el flujo sigue ejecutándose** y sigue confirmando.
3. **Qué pasa si hay timeout (diseñado para ser seguro):** la app muestra «el flujo no respondió… es posible que haya seguido confirmando» y **bloquea el botón** hasta volver a PREVALIDAR. Al prevalidar, las filas ya confirmadas aparecen `NO_DISPONIBLE` (estado `ASIGNADO`); lo pendiente sigue `VALIDO`. Ninguna fila se confirma dos veces (estado + ETag).
4. **Secuencial vs concurrencia.** V1 es secuencial (correcto y trazable). Subir la concurrencia sin medir aumentaría el riesgo de 429 y de conflictos; no se hace.
5. **Throttling de SharePoint.** Recuerdo un límite de la conexión del orden de 600 llamadas por minuto (**verificar**); a ~1 fila cada pocos segundos el flujo secuencial queda muy por debajo. Un 429 en la **lectura** se reintenta 2 veces; en el **MERGE no** (ERROR_FILA, «verifique antes de reintentar»).
6. **Límites de solicitudes de Power Platform por licencia.** 9 acciones por fila × 1999 filas ≈ 18.000 acciones: puede superar la cuota diaria de ciertas licencias (**verificar la tuya**).
7. **Tope por llamada configurable.** El flujo trae `PARAM_MAX_FILAS_POR_LLAMADA = 50` (Redactar al inicio): si la app envía más, **rechaza toda la llamada** (`LOTE_EXCEDE_LIMITE`, sin confirmar nada) en vez de arriesgar un timeout a medias. **Se sube solo después de medir**: valor seguro ≈ (tiempo máximo de espera × 0,6) ÷ `ms_por_fila`. El límite de negocio del archivo es **1999** (`PARAM_MAX_FILAS_ARCHIVO`); `min(…)` de ambos manda.

### Si un único flujo síncrono no alcanza — alternativa mínima (NO implementada, solo propuesta)

Conservando **un solo clic** y **sin historial persistente de lotes**: **partir en trozos desde Power Apps**. El botón envía las filas `VALIDO` en trozos de N ≤ lo medido como seguro, llamando al **mismo** flujo una vez por trozo y acumulando los resultados en `colConfirmacionP9` (memoria). No hay lista, ni estado, ni sondeo; cada trozo es independiente y el flujo no cambia.
Costes: la app debe permanecer abierta (si se cierra, los trozos restantes no se envían: no pasa nada grave, quedan `VALIDO` y se vuelve a PREVALIDAR); ForAll en Power Apps **no garantiza** ejecutar trozos en orden ni uno a uno (los trozos son disjuntos y cada depósito tiene su ETag, así que seguiría siendo correcto, pero aumentaría la carga simultánea en SharePoint); no se puede cancelar a mitad. **No se crea hasta demostrar con mediciones que hace falta.**
Descartado: responder antes y seguir en segundo plano (obliga a sondeo/estado), colas o listas de lotes (infraestructura no pedida).

## 8 · Límite de negocio: máximo 1999 filas (prevalidación)

La paginación de Excel está en 2000. Si la lectura alcanza 2000 filas o más, **se rechaza el archivo completo** (nada de lectura parcial silenciosa) con: «El archivo tiene 2000 filas o más y el máximo permitido es 1999. No se procesó ninguna fila: divida el archivo en partes más pequeñas.» (`DEMASIADAS_FILAS`). 1999 filas se prevalidan completas (probado en el simulador). **Esto cambia el texto del mensaje en `P9_MASIVA_PROTO_PREVALIDAR`**: el comportamiento ya existía; para ver el mensaje nuevo en el tenant hay que reimportar ese flujo (opcional, cosmético; ver `flows/INSTRUCCIONES_CONFIRMAR.md`).

## 9 · Qué NO está validado en tenant

1. **El flujo entero**: no se importó ni se ejecutó. Las pruebas usan un intérprete local de expresiones y un SharePoint falso (con ETags, 412 y carreras simuladas). Un comportamiento distinto del runtime real **no se detectaría aquí**: `actions('X')?['status']` dentro del `Scope` de una iteración, `json()`, `min`/`max`, `int(formatNumber(…))`, `convertTimeZone`, indexación por `item()`.
2. **La escritura real a escala**: V4.2 está validado fila a fila; una secuencia larga no. Tiempos, timeout, 429 y cuotas: sin medir (§7).
3. **El tamaño de `detalle_json` como entrada** (327 bytes por fila medidos con una fila típica; ~650 KB para 1999) frente al límite de entradas de texto del desencadenador de Power Apps: no verificado.
4. **Power Apps:** la sintaxis `JSON(ShowColumns(…); JSONFormat.Compact)` pasada a `Run`, `Table(ParseJSON(…))` con `ThisRecord.Value`, y `OnAddFile`/`OnRemoveFile` del control de adjuntos. Las fórmulas no se ejecutaron en Studio.
5. **La pantalla del repositorio es una reconstrucción** de la UX que ya armaste a mano (no hay export del tenant): posiciones, nombres de las etiquetas internas de la galería y el texto traducido de cada estado pueden diferir de los tuyos.
6. La propiedad `Id` del resultado de la lectura por ID (V4.2 la pide en el `$select` pero no consta que la lea).
7. **Esta prueba ESCRIBE en `Depositos_Activos` real.** No hay rollback automático. Los pasos de prueba (`flows/INSTRUCCIONES_CONFIRMAR.md`) usan depósitos que de todos modos se van a confirmar.

## 10 · Pruebas

`OPENPYXL_LXML=False python -m pytest proto_masiva -q`. `tests/test_08_confirmacion_masiva.py`: los 20 escenarios pedidos (uno por cada cambio de dato, 412, error técnico, lote mixto, 47/2/1, 8 campos de V4.2 comparados con el JSON de V4.2, sin otros campos, retry none, nunca `If-Match: *`, sin rollback) más: ETag fresco por fila, orden secuencial GET/POST, entrada inválida, límites 50/1999, filas mal formadas, mismo depósito dos veces, reenvío idempotente, fallo global, contrato y esquema, y las fórmulas de Power Fx. Se comprobó con **12 mutaciones** (`If-Match: *`, MERGE con reintentos, quitar cada comprobación de estado/clave/banco/importe/moneda/fecha, 412 sin distinguir, concurrencia 5, `CODIGO_ESTUDIANTE` desde la fila, campo extra en el cuerpo, procesar filas mal formadas) que cada defecto hace fallar la suite.

Pasos para llevarlo al tenant: **`flows/INSTRUCCIONES_CONFIRMAR.md`** · Power Fx: **`powerapps/CONFIRMACION_POWERFX.md`** · opción manual: `flows/GUIA_ACCIONES_CONFIRMACION.md`.
