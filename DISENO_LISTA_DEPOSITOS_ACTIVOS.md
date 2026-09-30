# DISEÑO · Microsoft List `Depositos_Activos` (P7)

Estado: **P7 aprobado conceptualmente** (D-1 y D-2 aprobadas). El motor P6 no se modifica: `LISTS.csv` sigue saliendo exactamente igual y es la única fuente de alimentación de la lista. Flujo de carga: `ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md`. Capa de adaptación: `adaptador_m365.py`.

> **Alcance de P7.** P7 valida **localmente** el puente P6 → artefacto M365. P7 **NO certifica** la integración end-to-end con SharePoint / Power Automate: la lista y el flujo aquí descritos no se han ejecutado contra un tenant de Microsoft 365. Las validaciones que lo requieren están pendientes para el piloto (ver §7 y `ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md` §9) y no bloquean P7.

```
motor P6 → LISTS.csv ──(adaptador_m365.py)──► DEPOSITOS_ACTIVOS__<lote>.json + MANIFIESTO_P7__<lote>.json
                                                    │
                                     flujo "P7 - CARGA DEPOSITOS ACTIVOS" (Power Automate)
                                                    ▼
                                         Microsoft List Depositos_Activos
```

## 1. Contrato del motor (solo lectura; verificado en el código actual)

| Elemento | Dónde (`motor_control_depositos_cbba.py`) | Qué hace |
|---|---|---|
| `COLUMNAS_LISTS` | línea 181 | **Única fuente de verdad** de las 26 columnas bancarias y su orden. |
| `valor_clave_numero(valor)` | línea 804 | Número → texto con **2 decimales** (`445.0` → `445.00`); vacío/NaN → `""`. |
| `crear_clave(row)` | línea 812 | Construye la clave del movimiento (ver §2). |
| `finalizar_dataframe(...)` | línea 849 | Asigna las columnas de seguimiento (`ESTADO`=`DISPONIBLE`, `SEDE SOLICITANTE`=`COCHABAMBA`, el resto vacío), `ARCHIVO ORIGEN`, `LOTE DE CARGA`, `FECHA DE CARGA`, `TEXTO DE BÚSQUEDA`; **calcula `CLAVE TRANSACCIÓN` con `crear_clave`** y devuelve `df[COLUMNAS_LISTS]`. Lo invoca `motor_generico.py` (línea 814). |
| `LISTS.csv` | paso 10-B de `ejecutar_motor` | `df_final[COLUMNAS_LISTS].to_csv(..., encoding="utf-8-sig")`: 26 columnas, UTF-8 con BOM. |

## 2. Clave única lógica: `CLAVE TRANSACCIÓN`

```
BANCO | CUENTA BANCARIA | AAAAMMDD | HHMMSS | CÓDIGO DE ASIGNACIÓN | TIPO MOVIMIENTO | IMPORTE (2 dec.) | SALDO (2 dec.)
BCP|301-5005425-2-71|20260707|144349|547521|CRÉDITO|445.00|22768.54
```

Verificado sobre el lote de referencia (`tests/golden/LOTE_12_LISTS.csv`, 12 formatos, 4064 movimientos): **4064 claves, 0 repetidas**; longitud máxima **79** caracteres (límite de texto de una línea: 255); sin saltos de línea; contiene acentos (`CRÉDITO`, `DÉBITO`, `BANCO UNIÓN`). La hora puede ir vacía (32 movimientos de Banco Unión no traen hora): la clave sigue siendo válida (`…|20260710||…|`).

Cómo se usa para no duplicar en Microsoft Lists:

1. **Es la identidad del movimiento.** La lista guarda la clave en `CLAVE_TRANSACCION` con **valores únicos exigidos** (columna indexada). Es la red de seguridad definitiva: aunque el flujo falle, se ejecute dos veces o dos ejecuciones corran a la vez, SharePoint rechaza el segundo elemento.
2. **No depende del archivo ni del lote.** Excluye `ARCHIVO ORIGEN`, `LOTE DE CARGA` y `FECHA DE CARGA`; por eso volver a correr el motor sobre los mismos extractos (o sobre extractos con fechas solapadas) produce las mismas claves → `YA_EXISTE`.
3. **Nunca se recalcula fuera del motor.** El adaptador y el flujo la copian tal cual. No se aplica `trim`, `upper`, ni reformateo. El adaptador solo comprueba que la clave sea coherente con las demás columnas de la misma fila (8 partes; banco, cuenta, fecha, hora, código, tipo, importe y saldo iguales); si no, la fila es `ERROR` y no se carga.
4. **Comparación exacta.** En filtros OData se duplica el apóstrofo (`'` → `''`). SharePoint compara texto sin distinguir mayúsculas; irrelevante porque la clave es determinista, pero conviene confirmarlo en el piloto con una clave con acentos.
5. **Límite conocido.** Si un banco corrigiera retroactivamente el `SALDO` o el `IMPORTE` de un movimiento ya cargado, sería otra clave y entraría como elemento nuevo (la clave incluye ambos valores). Es el comportamiento vigente de P6, no se altera.

## 3. Las 26 columnas de `COLUMNAS_LISTS`

- **Nombre técnico** = nombre *interno* de la columna en Microsoft Lists y clave del JSON. Solo ASCII, sin espacios: los acentos y espacios producen nombres internos ilegibles (`_x0020_`). El adaptador conserva el **valor** exacto de cada columna; solo cambia el nombre de la clave JSON (tabla `COLUMNAS_M365` de `adaptador_m365.py`, verificada por prueba contra `COLUMNAS_LISTS`).
- **Nombre para mostrar** (sugerido): el nombre original de `COLUMNAS_LISTS`, salvo las 7 columnas `MOTOR_*`, que se muestran con su nombre técnico.
- **Oblig.**: la columna se marca *Obligatoria* en la lista y el adaptador rechaza (`ERROR`) filas donde venga vacía. Criterio: 0 vacíos en las 4064 filas de los 12 formatos y necesaria para la identidad/consulta del movimiento. Las demás pueden venir vacías (p. ej. `HORA`, `DÉBITO`, `CRÉDITO`, `DEPOSITANTE`).
- **Origen**: todas provienen **directamente del motor** (columna de `LISTS.csv`). `finalizar_dataframe` fija algunas (marcadas *motor-const.*) con un valor constante o vacío.

| # | Columna en `COLUMNAS_LISTS` | Nombre técnico | Tipo en Microsoft Lists | Oblig. | Origen / notas |
|---|---|---|---|---|---|
| 1 | CLAVE TRANSACCIÓN | `CLAVE_TRANSACCION` | Texto de una línea (255) · **valores únicos exigidos · indexada** | **Sí** | Motor (`crear_clave`). **Clave única lógica.** |
| 2 | CÓDIGO DE ASIGNACIÓN | `CODIGO_ASIGNACION` | Texto de una línea | No | Motor. Texto (no número): conserva ceros a la izquierda. |
| 3 | BANCO | `BANCO` | Texto de una línea · indexada | **Sí** | Motor. Texto y no Opción: un banco nuevo en `registro_bancos.json` no debe romper la carga. |
| 4 | CUENTA BANCARIA | `CUENTA_BANCARIA` | Texto de una línea | **Sí** | Motor. Texto (guiones, ceros a la izquierda). |
| 5 | MONEDA | `MONEDA` | Texto de una línea | **Sí** | Motor (`BOB` / `USD`). |
| 6 | FECHA MOVIMIENTO | `FECHA_MOVIMIENTO` | Fecha (solo fecha) · indexada | **Sí** | Motor (`AAAA-MM-DD`). |
| 7 | HORA MOVIMIENTO | `HORA_MOVIMIENTO` | Texto de una línea | No | Motor (`HH:MM:SS` o vacía). Lists no tiene tipo "solo hora". |
| 8 | IMPORTE | `IMPORTE` | Número (2 decimales) | **Sí** | Motor. |
| 9 | DÉBITO | `DEBITO` | Número (2 decimales) | No | Motor (vacío si es crédito). |
| 10 | CRÉDITO | `CREDITO` | Número (2 decimales) | No | Motor (vacío si es débito). |
| 11 | TIPO MOVIMIENTO | `TIPO_MOVIMIENTO` | Texto de una línea | **Sí** | Motor (`CRÉDITO` / `DÉBITO`). |
| 12 | SALDO | `SALDO` | Número (2 decimales) | **Sí** | Motor (saldo validado por P6). |
| 13 | DESCRIPCIÓN | `DESCRIPCION` | Varias líneas (texto sin formato) | No | Motor. Máx. observado 90; largo abierto → varias líneas. |
| 14 | DEPOSITANTE / ORIGINANTE | `DEPOSITANTE_ORIGINANTE` | Varias líneas (texto sin formato) | No | Motor. Máx. observado 152. |
| 15 | INFORMACIÓN ADICIONAL | `INFORMACION_ADICIONAL` | Varias líneas (texto sin formato) | No | Motor. Máx. observado 198. |
| 16 | ESTADO | `MOTOR_ESTADO` | Texto de una línea | No | Motor-const. `DISPONIBLE`. **Reservada**: el estado operativo es `ESTADO_ASIGNACION` (§4). |
| 17 | ESTUDIANTE | `MOTOR_ESTUDIANTE` | Texto de una línea | No | Motor-const. vacía. Reservada (ver §4). |
| 18 | SOLICITADO POR | `MOTOR_SOLICITADO_POR` | Texto de una línea | No | Motor-const. vacía. Reservada. |
| 19 | SEDE SOLICITANTE | `MOTOR_SEDE_SOLICITANTE` | Texto de una línea | No | Motor-const. `COCHABAMBA`. Reservada. |
| 20 | CONFIRMADO POR | `MOTOR_CONFIRMADO_POR` | Texto de una línea | No | Motor-const. vacía. Reservada. |
| 21 | FECHA CONFIRMACIÓN | `MOTOR_FECHA_CONFIRMACION` | Texto de una línea | No | Motor-const. vacía. Texto para conservarla exacta; reservada. |
| 22 | OBSERVACIÓN | `MOTOR_OBSERVACION` | Varias líneas (texto sin formato) | No | Motor-const. vacía. Reservada. |
| 23 | TEXTO DE BÚSQUEDA | `TEXTO_BUSQUEDA` | Varias líneas (texto sin formato) | No | Motor. Máx. observado 386 (> 255: no cabe en una línea). |
| 24 | ARCHIVO ORIGEN | `ARCHIVO_ORIGEN` | Texto de una línea | **Sí** | Motor (nombre del extracto original). |
| 25 | LOTE DE CARGA | `LOTE_CARGA` | Texto de una línea · indexada | **Sí** | Motor (`AAAAMMDD_HHMMSS` de la corrida del motor; **no** es el lote P7). |
| 26 | FECHA DE CARGA | `FECHA_CARGA` | Texto de una línea | **Sí** | Motor (`AAAA-MM-DD HH:MM:SS.ffffff`). Texto para conservar exacta la marca del motor (sin zona horaria; ver riesgo D-15 del motor). |

Columnas de una línea: el adaptador marca `ERROR` cualquier valor de más de 255 caracteres (Lists rechazaría el elemento).

## 4. Campos OPERATIVOS (no forman parte de `COLUMNAS_LISTS`; los usará Power Apps)

El adaptador **no los emite**: el flujo solo completa `ESTADO_ASIGNACION`; el resto nace vacío.

| Nombre técnico | Tipo en Microsoft Lists | Oblig. en la carga | Nota |
|---|---|---|---|
| `ESTADO_ASIGNACION` | Opción (valor inicial **`DISPONIBLE`**, sin "rellenar"), indexada | **Sí** | El flujo escribe `DISPONIBLE` en todo movimiento nuevo. Los demás estados no están definidos todavía: se añaden en la fase Power Apps (no se inventan aquí). |
| `ESTUDIANTE` | Texto de una línea | No | |
| `CODIGO_ESTUDIANTE` | Texto de una línea | No | Texto: conserva ceros. |
| `SOLICITADO_POR` | Texto de una línea | No | Alternativa: Persona. |
| `SEDE_ASIGNACION` | Texto de una línea | No | Lista de sedes no definida: no se crea una Opción. |
| `USUARIO_ASIGNACION` | Texto de una línea (correo/UPN) | No | Más simple en `Patch` que Persona; el auditor nativo (`Modificado por`) queda como respaldo. |
| `FECHA_HORA_ASIGNACION` | Fecha y hora (con hora) | No | Power Apps: `Now()`. |
| `OBSERVACION` | Varias líneas (texto sin formato) | No | Sin acento. Distinta de `MOTOR_OBSERVACION`. |

**Decisión D-1 (nombres) — aprobada.** `ESTUDIANTE`, `SOLICITADO POR` y `OBSERVACIÓN` ya existen en `COLUMNAS_LISTS` y chocarían con `ESTUDIANTE`, `SOLICITADO_POR` y `OBSERVACION` de los campos operativos (y `ESTADO` / `SEDE SOLICITANTE` con `ESTADO_ASIGNACION` / `SEDE_ASIGNACION` en significado). Los campos operativos conservan exactamente los nombres pedidos; las 7 columnas homónimas del motor llevan prefijo `MOTOR_` y quedan **reservadas** (el motor las fija constantes; nunca se actualizan). Se conservan las 26 columnas del contrato P6 (no se elimina información) y se crean en la lista; podrán ocultarse de vistas y formularios y, después, en Power Apps.

## 5. Creación de la lista (una sola vez, clic a clic)

1. **Microsoft Lists → + Nueva lista → Lista en blanco →** Nombre `Depositos_Activos` (sin espacios, para que la URL interna sea igual) **→ Crear**.
2. **Columna Title:** engranaje **→ Configuración de la lista →** clic en `Title` **→** *Requerir que esta columna contenga información:* **No → Aceptar**. No se usa; ocultarla de vistas y formularios.
3. **Crear cada columna** con **+ Agregar columna → tipo → Nombre = nombre técnico de las tablas §3 y §4** (el nombre interno se fija al crear y **no se puede cambiar después**: no crear la columna con acentos o espacios). Después, editar la columna y cambiar solo el nombre para mostrar (§3). En números: 2 decimales, sin porcentaje. En `ESTADO_ASIGNACION`: valor `DISPONIBLE`, valor predeterminado `DISPONIBLE`, "Permitir valores de relleno" = No.
4. **Únicos + índices** (hacerlo **con la lista vacía**; una lista que ya superó 5000 elementos no permite crear índices):
   - `CLAVE_TRANSACCION` → editar columna → *Requerir información:* Sí → *Exigir valores únicos:* **Sí**.
   - **Configuración de la lista → Columnas indexadas → Crear un índice nuevo** para `FECHA_MOVIMIENTO`, `BANCO`, `ESTADO_ASIGNACION`, `LOTE_CARGA`.
5. **Vista por defecto:** mostrar `CLAVE_TRANSACCION`, `FECHA_MOVIMIENTO`, `BANCO`, `CUENTA_BANCARIA`, `IMPORTE`, `TIPO_MOVIMIENTO`, `ESTADO_ASIGNACION`; ocultar las `MOTOR_*`.
6. Permisos: el flujo (o su cuenta de conexión) necesita *Colaborar* sobre la lista; los usuarios de Power Apps, *Editar* pero no *Eliminar*. Se define en el despliegue.

## 5b. Segunda lista: `Depositos_Cargas` (bitácora oficial de lotes — D-2 aprobada)

Se crea igual que `Depositos_Activos` (§5). Registra **un elemento por ejecución del flujo**: `LOTE_ID`, `FECHA_HORA_PROCESO`, `ARCHIVO_FUENTE`, `SHA256`, `CANTIDAD_RECIBIDA`, `CANTIDAD_VALIDA`, `CANTIDAD_NUEVA`, `CANTIDAD_YA_EXISTE`, `CANTIDAD_ERROR`, `ESTADO_LOTE` (`COMPLETADO` / `COMPLETADO_CON_ERRORES` / `FALLIDO`) y `MENSAJE_ERROR` (más `ARCHIVO_JSON` e `ID_EJECUCION_FLUJO`). Definición completa de columnas, tipos, estados e invariante de conteo: `ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md` §3.

## 6. Conversión de tipos en el flujo

El artefacto conserva **todos los valores como texto exacto del CSV** (`"445.0"`, `""`, `"2026-07-07"`). El flujo convierte solo al mapear:

| Tipo en Lists | Expresión en la acción *Crear elemento* |
|---|---|
| Texto / varias líneas | `item()?['BANCO']` |
| Fecha (obligatoria) | `item()?['FECHA_MOVIMIENTO']` (ya es `AAAA-MM-DD`; el adaptador rechaza otro formato) |
| Número (opcional) | `if(empty(item()?['DEBITO']), null, float(item()?['DEBITO']))` |
| Número (obligatorio) | `float(item()?['IMPORTE'])` |
| Opción `ESTADO_ASIGNACION` | valor fijo `DISPONIBLE` |

## 7. Riesgos y verificaciones pendientes para el piloto (requieren tenant; no bloquean P7)

- **Fecha solo fecha:** confirmar en el piloto que `2026-07-07` queda como 7 de julio (zona horaria del sitio). Si hubiera desfase, cambiar `FECHA_MOVIMIENTO` a texto `AAAA-MM-DD`: la clave no cambia.
- **Índice y umbral de 5000:** los índices deben existir antes de crecer la lista; los filtros por `CLAVE_TRANSACCION` / `FECHA_MOVIMIENTO` no superan el umbral, los filtros por columnas sin índice sí pueden fallar con más de 5000 elementos.
- **Unicidad:** verificar el mensaje/código exacto que devuelve *Crear elemento* al violar la unicidad (el flujo no depende del texto: confirma con una consulta, ver la especificación del flujo).
- **`FECHA DE CARGA`** sale con la hora local de la máquina que corre el motor (defecto D-15 ya conocido y no tocado en P7).
- **Volumen (~4000 elementos por lote):** no se optimiza en P7; se mide en el piloto.
