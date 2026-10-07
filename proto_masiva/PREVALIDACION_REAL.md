# P9 CONFIRMACIÓN MASIVA — Prevalidación REAL contra `Depositos_Activos` (solo lectura)

> **Estado (actualizado 2026-10-07): validada MANUALMENTE en tu tenant** para lo que confirmaste: carga XLSX, múltiples filas, consulta a `Depositos_Activos`, `OK`/`OBSERVADO`, `VALIDO`, `NO_DISPONIBLE`
> (para `ASIGNADO`), `NO_ENCONTRADO`, `DUPLICADO_ARCHIVO`, `FILA_INCOMPLETA`, mensaje por fila y que **no modifica** `Depositos_Activos`. **Lo demás de la sección «Qué NO está validado» sigue sin validar**
> (p. ej. el día de borde de la ventana de 2 meses, `MONEDA_NO_COINCIDE`, `ASIGNACION_AMBIGUA`, volumen y tiempos grandes).
> **Fase siguiente:** la confirmación (`CONFIRMACION_MASIVA.md`) es la parte que ESCRIBE; esta prevalidación sigue siendo de solo lectura.

Rama `experiment/p9-masiva-prototipo`. Todo vive bajo `proto_masiva/`. Producción (`3b407e2`), confirmación individual, reversión, PDF, V4.2 y `Main_Screen` no se tocan.

## 1 · Arquitectura (sin N+1)

```
Power Apps ──XLSX──► P9_MASIVA_PROTO_PREVALIDAR
  validar archivo → copia temporal → Excel Online lee tblConfirmacionMasiva → valida estructura          (ya validado en tenant)
  → NUEVO: normaliza las filas (Select) y detecta duplicados del archivo
  → NUEVO: UN GET a Depositos_Activos  (CRÉDITO + ventana de la galería individual)
  → NUEVO: resuelve cada fila en memoria (Select / Filter array / split), SIN «Apply to each» y SIN una llamada a SharePoint por fila
  → intenta borrar la copia → responde: resumen + detalle_json
```

- **Una sola llamada** a SharePoint para todo el archivo, tenga 10 o 100 filas (`Enviar una solicitud HTTP a SharePoint`, el mismo patrón ya validado en `P9_ASIGNAR_DEPOSITO` V4.2 para leer un depósito; aquí con `GET` de la colección). El método es siempre `GET` y la política de reintentos «ninguna».
- Las filas se cruzan con los depósitos por una **clave en memoria**. El número de coincidencias de una fila es el número de apariciones de su clave en un índice de texto del universo; el detalle del depósito sale de ese mismo índice. No hay bucles.
- **Sin escrituras:** el flujo no contiene `MERGE`, `POST`, `PATCH`, `PUT`, `DELETE` hacia la lista, ni `ETag`/`If-Match`, ni acciones de crear/actualizar elemento (las pruebas lo verifican sobre la definición generada y el SharePoint simulado rechaza cualquier método distinto de `GET`).
- Diseñado para **10–100 filas**. Con más filas funciona (en el simulador 1000 filas se resuelven) pero **no se ha medido en el tenant**: el coste es proporcional a *filas × tamaño del universo* (cada fila busca su clave en el texto del índice). `PARAM_MAX_FILAS` sigue en 0 (sin tope); si las mediciones lo piden, se fija ahí.

## 2 · Internal names REALES de `Depositos_Activos`

La prevalidación usa **exactamente** estos nombres (nombre interno = nombre técnico, sin espacios ni acentos):

| Campo | Nombre interno | Tipo SharePoint | Evidencia en el repositorio |
|---|---|---|---|
| ID del elemento | `Id` | número | `$select=Id,…` en `Leer_deposito` de `P9_ASIGNAR_DEPOSITO` V4.2 (`p9/asignar/flujo_asignar_powerapps_v4_2_definition.json`) |
| CLAVE_TRANSACCION | `CLAVE_TRANSACCION` | texto, única, indexada | V4.2 (`$select`); `p8/esquema_listas_p8.json` |
| BANCO | `BANCO` | texto, indexada | `item/BANCO` en `p8/flujo_p8_definition.json`; `esquema_listas_p8.json`; galería `galDepositosP9_1` |
| CUENTA_BANCARIA | `CUENTA_BANCARIA` | texto | ídem |
| CODIGO_ASIGNACION | `CODIGO_ASIGNACION` | texto | ídem (la galería lo filtra con `StartsWith`) |
| IMPORTE | `IMPORTE` | **número, 2 decimales** | ídem |
| MONEDA | `MONEDA` | texto | ídem |
| FECHA_MOVIMIENTO | `FECHA_MOVIMIENTO` | fecha (solo fecha), indexada | ídem |
| TIPO_MOVIMIENTO | `TIPO_MOVIMIENTO` | texto, **valor `CRÉDITO` (con tilde)** | `DISENO_LISTA_DEPOSITOS_ACTIVOS.md` fila 11 («`CRÉDITO` / `DÉBITO`»); galería: `TIPO_MOVIMIENTO = "CRÉDITO"` |
| ESTADO | `ESTADO_ASIGNACION` | **opción** (`DISPONIBLE`, `ASIGNADO`) | V4.2: `equals(…['ESTADO_ASIGNACION'],'DISPONIBLE')` leído como **texto** con `odata=verbose`; `P9_HABILITAR_ESTADO_ASIGNADO` |

Sitio `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` y lista `296c450a-25d6-415b-ad10-c909c74817cb` (`p9/contrato.py`, los mismos de V4.2).

**Lo que el repositorio NO demuestra** (hay que confirmarlo en el tenant): que la propiedad del resultado se llame exactamente `Id` en la respuesta de la colección (V4.2 pide `Id` en el `$select` y lee otras propiedades; no consta que lea `Id` del resultado), y que existan **otros estados** además de `DISPONIBLE` y `ASIGNADO` (el flujo devuelve el estado real tal cual, sin suponer cuál es «confirmado»).

> Nota: el texto de ayuda de la galería dice «DISPONIBLE o CONFIRMADO», pero el filtro de la galería usa `ASIGNADO`; el estado real es `ASIGNADO`.

## 3 · Universo elegible: la regla EXACTA reutilizada

Se tomó de `galDepositosP9_1.Items` en `p9/reversion/powerapps/Main_Screen.yaml` (alrededor de las líneas 468-478), sin reinterpretar «2 meses»:

```
TIPO_MOVIMIENTO = "CRÉDITO"
FECHA_MOVIMIENTO >= DateAdd(Today(), -2, TimeUnit.Months)
FECHA_MOVIMIENTO <= Today()
```

(el texto «Últimos 2 meses (desde dd/mm/aaaa)» de la pantalla usa la misma `DateAdd(Today(), -2, TimeUnit.Months)`; ejemplo del 06/10/2026 → desde 06/08/2026).

Equivalencia en el flujo:

| Power Apps | Flujo |
|---|---|
| `Today()` (fecha local del dispositivo) | `convertTimeZone(utcNow(),'UTC','SA Western Standard Time','yyyy-MM-dd')` (Bolivia, UTC-4, sin horario de verano) → `Hoy_local` |
| `DateAdd(Today(), -2, Months)` | `formatDateTime(addToTime(<hoy>T00:00:00Z,-2,'Month'),'yyyy-MM-dd')` → `Desde_local` (recorta al último día del mes, igual que `DateAdd`: 30/04 → 28/02) |
| filtro delegado de la galería | `$filter=TIPO_MOVIMIENTO eq 'CRÉDITO' and FECHA_MOVIMIENTO ge datetime'<desde>T00:00:00Z' and FECHA_MOVIMIENTO le datetime'<hoy>T00:00:00Z'` |

**Se omite a propósito el filtro de estado de la galería** (`DISPONIBLE` o `ASIGNADO`): así un depósito ya asignado se distingue como `NO_DISPONIBLE` (con su estado real) y no se confunde con `NO_ENCONTRADO`. La ventana temporal y el tipo son los de la galería.

## 4 · Normalización

| Campo | Regla |
|---|---|
| Textos | `trim`. Las comparaciones de `BANCO`, `CUENTA_BANCARIA` y `CODIGO_ASIGNACION` son **sin distinguir mayúsculas** (minúsculas en ambos lados). Las **tildes sí cuentan** (`BANCO UNIÓN` ≠ `BANCO UNION`: son los valores del selector real). |
| `CUENTA_BANCARIA`, `CODIGO_ASIGNACION` | **Siempre texto. Nunca se convierten a número**: `0696870039` y `001234` conservan sus ceros y `001234` ≠ `1234`. (Si el Excel ya entregó el valor como número, los ceros ya se perdieron en Excel y no se pueden recuperar: la plantilla fija estas columnas como texto.) |
| `IMPORTE` | Debe ser texto/número con **solo dígitos y punto decimal**, **1–2 decimales como máximo**, **> 0**, ≤ 15 caracteres. Se rechazan: coma decimal, miles, signo, notación científica, texto, más de 2 decimales. Se compara como **entero de centavos** (`int(formatNumber(float(x)*100,'0'))`), en ambos lados (Excel y `IMPORTE` del depósito): nunca como texto y sin redondeos a ojo. Una diferencia de 0,01 es otro importe. |
| `MONEDA` | `trim` + mayúsculas; solo `BOB` o `USD`. |
| `OBSERVACION` | opcional. |
| `SEDE` | requerida; vacía = `FILA_INCOMPLETA`. **No se autocompleta nunca.** |

## 5 · Resultados por fila (9 estados) y orden de resolución

Clave base: **`BANCO` + `CUENTA_BANCARIA` + `CODIGO_ASIGNACION` + `IMPORTE`**. `MONEDA` **no** forma parte de la clave: se compara después, para distinguir `NO_ENCONTRADO` de `MONEDA_NO_COINCIDE`.

Orden (el primero que se cumple gana):

| # | `resultado` | Cuándo | ¿Busca el depósito? |
|---|---|---|---|
| 1 | `FILA_INCOMPLETA` | falta alguno de `BANCO`, `CUENTA_BANCARIA`, `CODIGO_ASIGNACION`, `IMPORTE`, `MONEDA`, `ESTUDIANTE`, `SOLICITADO_POR`, `SEDE` | no |
| 2 | `IMPORTE_INVALIDO` | `IMPORTE` no cumple la regla de la sección 4 | no |
| 3 | `MONEDA_INVALIDA` | `MONEDA` no es `BOB`/`USD` | no |
| 4 | `DUPLICADO_ARCHIVO` | otra fila **del mismo archivo** tiene la misma clave base | no |
| 5 | `NO_ENCONTRADO` | 0 depósitos del universo con esa clave | sí |
| 6 | `ASIGNACION_AMBIGUA` | más de 1 depósito con esa clave (`coincidencias` = cuántos) | sí |
| 7 | `MONEDA_NO_COINCIDE` | exactamente 1 depósito, pero su moneda es otra | sí (devuelve `moneda_deposito`) |
| 8 | `NO_DISPONIBLE` | exactamente 1 depósito, pero `ESTADO_ASIGNACION` ≠ `DISPONIBLE` | sí (devuelve el `estado_actual` real) |
| 9 | `VALIDO` | exactamente 1 depósito, moneda igual y `DISPONIBLE` | sí |

**Duplicados:** se detectan sobre las filas cuya clave se puede calcular (BANCO, CUENTA, CÓDIGO e IMPORTE válido), **antes** de aplicar el resto de reglas: **todas** las filas repetidas quedan `DUPLICADO_ARCHIVO` (si las filas 2 y 8 apuntan al mismo depósito, **ambas** lo son; no queda una válida y las siguientes bloqueadas). Una fila que además tenga otro error con precedencia (p. ej. `FILA_INCOMPLETA`) conserva ese resultado, pero su pareja completa **sigue** marcada `DUPLICADO_ARCHIVO`.
Las filas totalmente en blanco se ignoran (no cuentan), pero conservan su posición.

`fila_excel` = `fila_tabla` + 5 (la plantilla oficial tiene el encabezado en la fila 5). **Es una suposición sobre la plantilla oficial**: el conector de Excel no entrega el número de fila; `fila_tabla` (posición dentro de la tabla, 1 = primera fila de datos) es siempre fiable.

## 6 · Contrato de respuesta (`Responder a Power Apps`, todo TEXTO)

«Responder a Power Apps» solo devuelve **valores simples**: no se puede devolver un arreglo de objetos. Por eso `detalle_json` es **texto JSON**.

| Salida | Contenido |
|---|---|
| `resultado` | **`OK`** (todas las filas válidas) · **`OBSERVADO`** (al menos una fila con observación; **no es un error técnico**) · **`ERROR`** (error técnico; sin detalle por fila) |
| `codigo` | `PREVALIDACION_OK` · `PREVALIDACION_CON_ERRORES` · o el del error técnico (abajo) |
| `mensaje` | texto para el usuario, p. ej. `1 de 10 filas válidas; 9 con observaciones. Prevalidación de solo lectura: no se confirmó ningún depósito.` |
| `archivo`, `tabla_encontrada`, `filas_leidas`, `copia_temporal_eliminada`, `tiempos_ms` | **se conservan** (`tiempos_ms` añade `depositos=`: `crear=…;excel=…;depositos=…;borrar=…;total=…`) |
| `filas_totales`, `filas_validas`, `filas_con_error` | recuentos como texto (`"0"` en errores técnicos) |
| `depositos_consultados` | cuántos depósitos devolvió la lectura (el universo): útil para comprobar la ventana y el volumen |
| `detalle_json` | texto JSON: arreglo con un objeto por fila (`"[]"` en errores técnicos). Esquema: `flows/esquema_detalle_json.json` |

Códigos de **error técnico** (`resultado = "ERROR"`): `SIN_ARCHIVO`, `NO_ES_XLSX`, `ERROR_COPIA_ARCHIVO`, `ERROR_LECTURA_EXCEL`, `ARCHIVO_BLOQUEADO`, `TABLA_NO_ENCONTRADA`, `ESTRUCTURA_INVALIDA`, `ARCHIVO_VACIO` (cero filas), `DEMASIADAS_FILAS`, **`ERROR_SHAREPOINT`** (la lectura de `Depositos_Activos` falló; incluye el HTTP), **`DEPOSITOS_DEMASIADOS`** (SharePoint indica más depósitos que el tope de lectura de 5000: se avisa en vez de marcar `NO_ENCONTRADO` por datos que no se leyeron) y `ERROR_NO_CONTROLADO` (equivale al «error interno»).

### `detalle_json` — un objeto por fila (20 campos, siempre presentes)

`fila_excel`, `fila_tabla`, `resultado`, `mensaje`, `deposito_id` (entero o `null`), `clave_transaccion`, `estado_actual`, `fecha_movimiento`, `moneda_deposito`, `coincidencias`, `banco`, `cuenta_bancaria`, `codigo_asignacion`, `importe` (número o `null`), `importe_original`, `moneda`, `estudiante`, `solicitado_por`, `sede`, `observacion`.
`deposito_id`, `clave_transaccion`, `estado_actual`, `fecha_movimiento` y `moneda_deposito` solo se rellenan si hay **un único** depósito (`VALIDO`, `MONEDA_NO_COINCIDE`, `NO_DISPONIBLE`). **No se devuelve ningún ETag**: la prevalidación no reserva nada.

Ejemplos reales de la salida del flujo simulado: `flows/ejemplos_respuesta/*.json` (se generan ejecutando el flujo; un test comprueba que no se desfasan).

## 7 · Concurrencia — PREVALIDAR no reserva nada (para la fase de confirmación, NO implementada)

Entre PREVALIDAR y CONFIRMAR otro usuario puede confirmar, revertir o cambiar un depósito: es correcto y esperado. La **futura** confirmación masiva deberá, **por fila**, y **sin fiarse del resultado de la prevalidación**:

1. **releer** el depósito por `deposito_id` (ID);
2. validar que su `CLAVE_TRANSACCION` sigue siendo la esperada;
3. validar que su estado sigue siendo `DISPONIBLE`;
4. obtener un **ETag concreto y fresco** de esa lectura;
5. escribir con `If-Match` (ETag), **sin reintentos**;
6. tratar `412` como `CONFLICTO`;
7. escribir los mismos 8 campos atómicos de la confirmación individual V4.2.

Nada de esto existe en este checkpoint.

## 8 · Qué NO está validado en tenant (solo el tenant lo confirma)

1. **Todo el flujo nuevo.** No se ha importado ni ejecutado en Power Automate. Las pruebas usan un intérprete local de expresiones y un SharePoint/Excel falsos.
2. **El `$filter` de la lectura.** El valor `'CRÉDITO'` va con tilde **sin codificar** y las fechas como `datetime'…T00:00:00Z'`. Si SharePoint o el conector no los aceptan, la lectura falla con `ERROR_SHAREPOINT` (ruidoso, no silencioso). Por eso existe la comprobación `depositos_consultados` frente al contador de la galería (ver guía de pruebas).
3. **Los límites del día de la ventana.** FECHA_MOVIMIENTO es solo-fecha; cómo guarda SharePoint la hora/zona de esos valores puede desplazar el día de borde. Se comprueba con un depósito del día exacto `hoy - 2 meses`.
4. **Funciones de expresión en el runtime real:** `split` con un separador de **varios caracteres**, `indexOf`, `formatNumber(x,'0')`, `int()`, `convertTimeZone` con `SA Western Standard Time`, `addToTime(…,'Month')` (recorte de fin de mes), indexación `array?[item()]` dentro de `Select`, y que `string()` de un número dé el mismo texto que el JSON (`1500.5`). El simulador interpreta estas funciones como Python: **un comportamiento distinto del runtime real no se detectaría aquí.** Además: la expresión más larga mide 1.233 caracteres y el anidamiento llega a 10 niveles (`replace` encadenados) y 9 (`if` encadenados); no se ha contrastado con los límites de longitud/anidamiento de expresiones del runtime (no se pudo consultar la documentación de Microsoft desde el entorno de construcción).
5. **Tipos de celda de Excel Online:** que `IMPORTE` llegue como número (o texto), que las celdas vacías lleguen como `""`/`null`, y que `CUENTA_BANCARIA`/`CODIGO_ASIGNACION` lleguen como texto (la plantilla los fija como texto).
6. **Volumen y tiempo.** No se conoce el tamaño real del universo (CRÉDITO + 2 meses). El tope de lectura es 5000 (`$top`); por encima SharePoint devuelve `__next` y el flujo responde `DEPOSITOS_DEMASIADOS`. `FECHA_MOVIMIENTO` y `TIPO_MOVIMIENTO` están indexadas (`P9_HABILITAR_ESTADO_ASIGNADO`), pero el comportamiento del umbral de vista de 5000 con tu volumen real solo se ve en el tenant. Tiempos: sin medir.
7. **El tamaño de `detalle_json`** frente a los límites de respuesta de Power Automate/Power Apps (no verificado; ~0,5 KB por fila en el simulador).
8. **Power Apps:** `Table(ParseJSON(...))` con `ThisRecord.Value.<campo>` y `Value()` de un `null`. Las fórmulas no se ejecutaron en Studio.
9. **Otros estados** de `ESTADO_ASIGNACION` distintos de `DISPONIBLE`/`ASIGNADO` (se devuelven tal cual como `NO_DISPONIBLE`).

## 9 · Pruebas

`OPENPYXL_LXML=False python -m pytest proto_masiva -q` (ver `ESTADO_CHECKPOINT_TENANT.md` §7). `tests/test_07_prevalidacion_real.py`: los 15 escenarios pedidos más límites, ventana de fechas (zona horaria, fin de mes, cruce de año), sin N+1, sin escrituras, esquema de `detalle_json` y **40 escenarios aleatorios cruzados fila a fila con un oráculo independiente** (`tests/oraculo_prevalidacion.py`: las mismas reglas en Python puro). Se comprobó con mutaciones (ventana de 3 meses, duplicados a partir de 3, importe truncado, sin chequeo de estado, sin chequeo de moneda, clave sensible a mayúsculas, `fila_excel` desalineado, código convertido a número) que cada defecto hace fallar la suite.

Pasos para llevar esta versión al tenant: `flows/ACTUALIZAR_FLUJO_PREVALIDACION.md`. Fórmulas de Power Apps: `powerapps/PREVALIDACION_POWERFX.md`.
