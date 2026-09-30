# ESPECIFICACIÓN · Flujo de Power Automate `P7 - CARGA DEPOSITOS ACTIVOS`

Estado: **P7 aprobado conceptualmente** (D-1 y D-2 aprobadas). Solo especificación: no hay flujo construido, no hay Power Apps.

> **Alcance de P7.** P7 valida **localmente** el puente P6 → artefacto M365 (`LISTS.csv` → JSON + manifiesto, clasificación `NUEVO` / `YA_EXISTE` / `ERROR`, determinismo). P7 **NO certifica** la integración end-to-end con SharePoint / Power Automate: nada de lo descrito aquí sobre la lista y el flujo se ha ejecutado contra un tenant de Microsoft 365. Esas validaciones quedan expresamente **pendientes para el piloto** (§9) y no bloquean P7. Diseño de la lista: `DISENO_LISTA_DEPOSITOS_ACTIVOS.md`. Generador del artefacto: `adaptador_m365.py`. Esquema para *Analizar JSON*: `esquema_parse_json_p7.json`. Ejemplo real: `ejemplos_p7/`.

Todo lo que dependa del entorno (sitio, listas, conexiones, carpeta, cuentas) es un **parámetro que se configura en la importación/despliegue** y aquí aparece como `<PARAMETRO>`. No se define ningún identificador, URL, credencial ni conexión.

## 1. Artefacto de intercambio: JSON (justificación)

| Criterio | JSON | CSV | XLSX |
|---|---|---|---|
| Lectura en Power Automate estándar | `json()` + *Analizar JSON*: propiedades con nombre en el contenido dinámico | **No existe acción estándar para analizar CSV**; hay que partir texto con `split()` | Solo con el conector *Excel Online (Business)*: exige **tabla** con nombre y archivo en OneDrive/SharePoint |
| Integridad de valores | Texto entre comillas: conserva comas, comillas, **saltos de línea**, acentos y espacios finales | Frágil: `DESCRIPCIÓN` / `TEXTO DE BÚSQUEDA` traen `,`, `"`, `|` y pueden traer saltos de línea → `split()` rompe columnas | Excel convierte tipos (números, fechas, ceros a la izquierda) y trunca celdas largas |
| Esquema / validación | Esquema JSON verificable (26 propiedades) | Solo posición de columnas | Nombres de columna sensibles a la tabla |
| Volumen | Una lectura (`Obtener contenido del archivo`) | Una lectura + parseo manual | *Listar filas* pagina (256 por defecto), bloquea el archivo y es lento |
| Dependencias (lado Python) | Ninguna (`json` estándar) | Ninguna | `openpyxl` (ya del proyecto, pero innecesaria) |

Se elige **JSON**: UTF-8 **sin BOM**, todos los valores como **texto exacto** del CSV (`"445.0"`, `""`), una fila por línea, orden de claves fijo (bytes deterministas). El adaptador se ejecuta con solo la biblioteca estándar.

## 2. Entradas del flujo

Por cada lote, el adaptador (`python adaptador_m365.py <LISTS.csv> <carpeta_m365>`) genera dos archivos en una carpeta **distinta** de la del motor:

| Archivo | Uso |
|---|---|
| `DEPOSITOS_ACTIVOS__<lote_id>.json` | **Entrada del flujo.** `lote_id` = `P7-` + 12 primeros hex del SHA-256 de `LISTS.csv` (mismo archivo → mismo lote). |
| `MANIFIESTO_P7__<lote_id>.json` | Trazabilidad (lote, fecha/hora, cantidades, rango de fechas, bancos, cuentas, hash y nombre del archivo fuente, artefacto y su hash). Se archiva junto al JSON; el flujo no lo necesita. |

**Contrato fail-fast:** antes de leer nada, el adaptador comprueba que su contrato de columnas es exactamente el de P6 (26 columnas, mismo nombre y orden), tanto en su tabla interna como en el `COLUMNAS_LISTS` del código del motor cuando éste está junto al adaptador, y que el encabezado de `LISTS.csv` coincide. Cualquier desviación detiene el proceso con `ERROR de contrato` (código de salida 2) y **no escribe ningún archivo**. No modifica P6.

Estructura del artefacto (todos los valores son cadenas):

```json
{
"esquema": "P7_DEPOSITOS_ACTIVOS_V1",
"lote_id": "P7-…", "archivo_fuente": "LISTS.csv", "sha256_archivo_fuente": "…",
"columnas": ["CLAVE_TRANSACCION", "CODIGO_ASIGNACION", …, "FECHA_CARGA"],
"movimientos": [ {26 claves técnicas: filas válidas, con CLAVE única dentro del archivo} ],
"omitidos": [ {"fila": 3, "estado": "ERROR" | "YA_EXISTE", "motivo": "…", "errores": [...], "valores": {26 claves}} ]
}
```

- `movimientos`: lo único que el flujo **envía a la lista** (tras comprobar la CLAVE).
- `omitidos`: filas que el adaptador ya resolvió: `ERROR` (obligatorio vacío, número/fecha inválidos, texto de una línea > 255, clave mal formada o incoherente) y `YA_EXISTE` con motivo `REPETIDA_EN_LOTE` (segunda aparición de la misma clave dentro del archivo). Nunca se crean elementos con ellas.
- Un `LISTS.csv` sin movimientos produce un artefacto válido con `movimientos: []`.

## 3. Salidas

**Depositos_Activos** (lista de movimientos): un elemento por CLAVE nueva, con `ESTADO_ASIGNACION = DISPONIBLE`.

**Depositos_Cargas** — **bitácora oficial de procesamiento por lote** (decisión D-2, aprobada). El flujo escribe **un registro por ejecución**, tanto si termina bien como si falla. No sustituye al manifiesto ni a los archivos JSON: es el registro de ejecución.

| Nombre técnico | Tipo en Microsoft Lists | Oblig. | Contenido |
|---|---|---|---|
| `LOTE_ID` | Texto de una línea · indexada (**sin** valores únicos: reprocesar el mismo lote crea otro registro) | Sí | `lote_id` del artefacto (`P7-…`) |
| `FECHA_HORA_PROCESO` | Fecha y hora | Sí | `utcNow()` al cerrar el flujo |
| `ARCHIVO_FUENTE` | Texto de una línea | Sí | `archivo_fuente` del artefacto (normalmente `LISTS.csv`) |
| `SHA256` | Texto de una línea | Sí | `sha256_archivo_fuente` (huella del `LISTS.csv` de origen) |
| `CANTIDAD_RECIBIDA` | Número (0 decimales) | Sí | `length(movimientos) + length(omitidos)` |
| `CANTIDAD_VALIDA` | Número (0 decimales) | Sí | `CANTIDAD_RECIBIDA` − omitidos con `estado = 'ERROR'` (igual a `cantidad_valida` del manifiesto) |
| `CANTIDAD_NUEVA` | Número (0 decimales) | Sí | Elementos creados en `Depositos_Activos` |
| `CANTIDAD_YA_EXISTE` | Número (0 decimales) | Sí | Claves que ya estaban en la lista + repetidas dentro del archivo |
| `CANTIDAD_ERROR` | Número (0 decimales) | Sí | Filas `ERROR` del adaptador + elementos que no se pudieron crear |
| `ESTADO_LOTE` | Opción | Sí | `COMPLETADO` · `COMPLETADO_CON_ERRORES` · `FALLIDO` (ver abajo) |
| `MENSAJE_ERROR` | Varias líneas (texto sin formato) | No | Vacío si `COMPLETADO`. Si `COMPLETADO_CON_ERRORES`: JSON con `fila` / `clave` / `motivo` de cada error. Si `FALLIDO`: el mensaje del paso que falló |
| `ARCHIVO_JSON` | Texto de una línea | No | *Adicional:* nombre del artefacto procesado |
| `ID_EJECUCION_FLUJO` | Texto de una línea | No | *Adicional:* `workflow()?['run']?['name']` (para localizar la ejecución en Power Automate) |

`Title` no se usa (opcional, oculto), igual que en `Depositos_Activos`.

**Invariante de conteo** (el flujo lo comprueba antes de cerrar): `CANTIDAD_RECIBIDA = CANTIDAD_NUEVA + CANTIDAD_YA_EXISTE + CANTIDAD_ERROR`. Si no se cumple, `ESTADO_LOTE = COMPLETADO_CON_ERRORES` y `MENSAJE_ERROR` lo indica (nunca se cierra un lote con conteos que no cuadran).

**`ESTADO_LOTE`:**

| Valor | Cuándo |
|---|---|
| `COMPLETADO` | El flujo terminó, `CANTIDAD_ERROR = 0` y el invariante se cumple (incluye lote vacío y lote donde todo era `YA_EXISTE`) |
| `COMPLETADO_CON_ERRORES` | El flujo terminó, pero `CANTIDAD_ERROR > 0` o el invariante no cuadra. Los movimientos sin error sí quedaron cargados |
| `FALLIDO` | El flujo se interrumpió (contrato del JSON inválido, lista inaccesible, etc.). Los datos disponibles del artefacto se registran; reprocesar es seguro |

Creación de la lista: como `Depositos_Activos` (`DISENO_LISTA_DEPOSITOS_ACTIVOS.md` §5): nombre `Depositos_Cargas`, columnas con su **nombre técnico** al crearlas, `Title` no obligatorio, índices en `LOTE_ID` y `FECHA_HORA_PROCESO`. Los usuarios operativos no necesitan escribir en ella: solo el flujo (permiso *Colaborar*) y lectura para quien audite.

## 4. Parámetros de despliegue (sin valores)

| Parámetro | Descripción |
|---|---|
| `<SITIO_SHAREPOINT>` | Sitio que aloja las listas y la carpeta de entrada |
| `<LISTA_DEPOSITOS_ACTIVOS>` | Lista `Depositos_Activos` de ese sitio |
| `<LISTA_DEPOSITOS_CARGAS>` | Lista `Depositos_Cargas` |
| `<CARPETA_ENTRADA_M365>` | Carpeta de la biblioteca donde se depositan los `DEPOSITOS_ACTIVOS__*.json` (cómo llegan allí —subida manual, sincronización— queda fuera de P7) |
| `<CONEXION_SHAREPOINT>` | Conexión (cuenta con permiso *Colaborar* sobre ambas listas) |

Recomendación: definirlos como **variables de entorno de una solución** para que la importación pida los valores y el flujo no contenga identificadores.

## 5. Flujo, paso a paso

**Desencadenador — SharePoint: *Cuando se crea un archivo en una carpeta*** (`<SITIO_SHAREPOINT>`, `<CARPETA_ENTRADA_M365>`). Condición del desencadenador:

```
@and(startsWith(triggerOutputs()?['body/{FilenameWithExtension}'], 'DEPOSITOS_ACTIVOS__'),
     endsWith(triggerOutputs()?['body/{FilenameWithExtension}'], '.json'))
```

Todo lo siguiente va dentro de un ámbito **`Ambito_principal`**; un ámbito paralelo `Ambito_fallo` (*configurar ejecución posterior*: falló / expiró) registra el lote como `FALLIDO`.

1. **Inicializar variables** (enteros `varNuevos`, `varYaExisten`, `varErrores` = 0; matriz `varDetalle` = `[]`; cadena `varMensaje` = `''`).
2. **Obtener contenido del archivo** (SharePoint) del archivo del desencadenador.
3. **Analizar JSON** — Contenido: `json(base64ToString(outputs('Obtener_contenido_del_archivo')?['body']?['$content']))` (si el conector devuelve el JSON ya interpretado, usar `body(...)`; confirmar en el piloto). Esquema: contenido de `esquema_parse_json_p7.json`.
4. **Condición de contrato:** `esquema = 'P7_DEPOSITOS_ACTIVOS_V1'` **y** `length(columnas) = 26`. Si no se cumple → **Terminar** (Error) con el motivo; cae en `Ambito_fallo`.
5. **Condición: `length(movimientos) > 0`.** Si es 0, saltar a 8 con `CANTIDAD_NUEVA = 0` (lote vacío válido).
6. **Comprobar CLAVE en `Depositos_Activos` (una consulta por lote, no por fila):**
   1. *Seleccionar* `fechas` = `item()?['FECHA_MOVIMIENTO']` sobre `movimientos`.
   2. *Redactar* `fMin` = `first(sort(body('Seleccionar_fechas')))`; `fMax` = `last(sort(body('Seleccionar_fechas')))`.
   3. **Obtener elementos** (`<LISTA_DEPOSITOS_ACTIVOS>`): *Consulta de filtro* `FECHA_MOVIMIENTO ge '@{outputs('fMin')}' and FECHA_MOVIMIENTO le '@{outputs('fMax')}'`, *Recuento de elementos principales* 5000, **Paginación activada** (umbral 5000). Limitar columnas a `CLAVE_TRANSACCION`. Confirmar la sintaxis del filtro de fecha en el piloto.
   4. *Seleccionar* `claves_existentes` = `item()?['CLAVE_TRANSACCION']` sobre `outputs('Obtener_elementos')?['body/value']`.
   5. *Filtrar matriz* `nuevos` sobre `movimientos`: `@not(contains(body('Seleccionar_claves_existentes'), item()?['CLAVE_TRANSACCION']))`.
   - Si la consulta queda truncada (más de 5000 existentes en el rango) un movimiento existente podría verse como nuevo: **lo detiene la unicidad de la lista** (paso 7), nunca se duplica.
7. **Aplicar a cada** elemento de `body('Filtrar_matriz_nuevos')` — **concurrencia = 1** (los contadores no son seguros en paralelo):
   1. **Crear elemento** (`<LISTA_DEPOSITOS_ACTIVOS>`), mapeo del §6 de `DISENO_LISTA_DEPOSITOS_ACTIVOS.md`: cada columna técnica ← `item()?['<COLUMNA>']` (con la conversión de número/fecha), `ESTADO_ASIGNACION Value` ← `DISPONIBLE`. Los campos operativos restantes no se envían.
   2. Si **tiene éxito** → *Incrementar variable* `varNuevos`.
   3. Si **falla** (*configurar ejecución posterior*: falló) → **Obtener elementos** con filtro `CLAVE_TRANSACCION eq '@{replace(item()?['CLAVE_TRANSACCION'], '''', '''''')}'`, recuento 1:
      - devuelve ≥ 1 → **`YA_EXISTE`** (otra ejecución la creó entre la consulta y la creación): `varYaExisten` + 1.
      - devuelve 0 → **`ERROR`**: `varErrores` + 1 y *Anexar a variable de matriz* `varDetalle` con `{clave, motivo: <mensaje de error de Crear elemento>}`.
   La decisión no depende del texto del error de unicidad: siempre se **confirma consultando**.
8. **Cerrar los conteos:**
   - `CANTIDAD_RECIBIDA` = `length(movimientos) + length(omitidos)`.
   - `CANTIDAD_NUEVA` = `varNuevos`.
   - `CANTIDAD_YA_EXISTE` = `(length(movimientos) − length(nuevos)) + varYaExisten + <omitidos con estado YA_EXISTE>` (*Filtrar matriz* sobre `omitidos` con `estado = 'YA_EXISTE'`).
   - `CANTIDAD_ERROR` = `varErrores` + `<omitidos con estado ERROR>`; los ERROR de `omitidos` (`fila`, `motivo`) se añaden a `varDetalle`.
   - `CANTIDAD_VALIDA` = `CANTIDAD_RECIBIDA − <omitidos con estado ERROR>`.
   - **Invariante:** `CANTIDAD_RECIBIDA = CANTIDAD_NUEVA + CANTIDAD_YA_EXISTE + CANTIDAD_ERROR`. Si no cuadra, `varMensaje` = «conteos inconsistentes» (y el estado será `COMPLETADO_CON_ERRORES`).
9. **Registrar el resultado del lote (bitácora):** *Crear elemento* en `<LISTA_DEPOSITOS_CARGAS>` con `LOTE_ID`, `FECHA_HORA_PROCESO` (`utcNow()`), `ARCHIVO_FUENTE`, `SHA256`, `CANTIDAD_RECIBIDA`, `CANTIDAD_VALIDA`, `CANTIDAD_NUEVA`, `CANTIDAD_YA_EXISTE`, `CANTIDAD_ERROR`, `ARCHIVO_JSON`, `ID_EJECUCION_FLUJO`, `ESTADO_LOTE` (`COMPLETADO` si `CANTIDAD_ERROR = 0` y el invariante cuadra; si no, `COMPLETADO_CON_ERRORES`) y `MENSAJE_ERROR` (vacío si `COMPLETADO`; si no, `string(varDetalle)` y `varMensaje`).
10. **`Ambito_fallo`** (se ejecuta si `Ambito_principal` falló o expiró): *Crear elemento* en `<LISTA_DEPOSITOS_CARGAS>` con `ESTADO_LOTE = FALLIDO`, `MENSAJE_ERROR` = `result('Ambito_principal')` y los campos del artefacto que se hayan podido leer (`LOTE_ID`, `ARCHIVO_FUENTE`, `SHA256`, conteos parciales); los campos obligatorios sin dato se rellenan con `0` / `'DESCONOCIDO'`. Reprocesar es seguro (la carga es idempotente).

## 6. Resultado por movimiento: `NUEVO` · `YA_EXISTE` · `ERROR`

| Estado | Quién lo decide | Condición | Efecto en `Depositos_Activos` |
|---|---|---|---|
| `NUEVO` | Flujo (paso 6/7) | CLAVE válida, no está en la lista | Se crea con `ESTADO_ASIGNACION = DISPONIBLE` |
| `YA_EXISTE` | Flujo (paso 6/7.3) o adaptador (`REPETIDA_EN_LOTE`) | CLAVE ya en la lista, o repetida en el mismo archivo | **Ninguno** |
| `ERROR` | Adaptador (validación) o flujo (fallo al crear no explicado por duplicado) | Fila inválida / no se pudo crear | **Ninguno**; queda en `MENSAJE_ERROR` de la bitácora |

`python adaptador_m365.py <LISTS.csv> <carpeta> --claves-existentes claves.txt` reproduce **fuera de Power Automate** esta misma clasificación (`CLASIFICACION_P7__<lote>.csv`), útil para ensayar y conciliar antes de cargar (`claves.txt`: una CLAVE por línea, exportada de la lista).

## 7. Idempotencia

- Mismo archivo procesado dos veces → mismas claves → `CANTIDAD_NUEVA = 0`, todo `YA_EXISTE`, **cero elementos nuevos** (capa 1: comparación con la lista; capa 2: valores únicos exigidos en `CLAVE_TRANSACCION`).
- Extracto nuevo con fechas solapadas → solo entran los movimientos no cargados.
- El flujo **no modifica ni elimina** elementos existentes (no actualiza los ya asignados por Power Apps).
- Dos ejecuciones simultáneas: gana la primera en crear; la segunda recibe el rechazo de unicidad y lo registra como `YA_EXISTE`.

## 8. Pruebas de aceptación en el piloto (con las listas vacías)

1. Cargar `ejemplos_p7/m365/DEPOSITOS_ACTIVOS__*.json` (8 movimientos): bitácora con `CANTIDAD_RECIBIDA = 8`, `CANTIDAD_NUEVA = 8`, `ESTADO_LOTE = COMPLETADO`; 8 elementos `DISPONIBLE` en `Depositos_Activos`, cada valor igual al de `LISTS.csv` (importes con 2 decimales y espacios finales de `DESCRIPCIÓN` incluidos).
2. Volver a depositar el mismo archivo (otro nombre o *Volver a cargar*): segundo registro en la bitácora con `CANTIDAD_NUEVA = 0`, `CANTIDAD_YA_EXISTE = 8`; la lista sigue con 8 elementos.
3. Artefacto con un elemento repetido en el archivo y una fila con error: `CANTIDAD_YA_EXISTE` y `CANTIDAD_ERROR` reflejan `omitidos`; `ESTADO_LOTE = COMPLETADO_CON_ERRORES`; `MENSAJE_ERROR` lista la fila.
4. Lote vacío (`movimientos: []`): `CANTIDAD_RECIBIDA = 0`, `COMPLETADO`, sin error.
5. JSON con `esquema` distinto: registro `FALLIDO` con el motivo; ningún elemento creado.
6. Dos ejecuciones simultáneas del mismo archivo: 8 elementos, sin duplicados; los conteos de ambos registros suman 8 creados en total.
7. Fecha del movimiento: `2026-07-07` queda como 7 de julio en la lista.

## 9. Pendientes del piloto y decisiones

**Validaciones que requieren un tenant de Microsoft 365 (pendientes; no bloquean P7):**
- Que la fecha `2026-07-07` quede como 7 de julio (zona horaria del sitio).
- Sintaxis del filtro por fecha en *Obtener elementos* y comportamiento de la paginación (5000).
- Si *Obtener contenido del archivo* devuelve el JSON ya interpretado o en `$content` (paso 3).
- Mensaje/código de *Crear elemento* al violar la unicidad, y comparación de claves con acentos.
- Que el invariante de conteo y los tipos (Número, Opción, Fecha y hora) de la bitácora se comporten como se espera.
- **Rendimiento con lotes de ~4000 elementos:** **no se optimiza en P7**; se mide en el piloto (≈4000 creaciones secuenciales, límites de solicitudes de la licencia).

**Decisiones:**
- **D-1 (aprobada):** las 26 columnas de P6 se conservan; las columnas del motor que chocan con campos operativos usan prefijo `MOTOR_*` y podrán ocultarse en Power Apps.
- **D-2 (aprobada):** `Depositos_Cargas` es la bitácora oficial de procesamiento por lote (no `RESULTADO_P7__*.json`).
- Cómo llega el JSON a la carpeta (sincronización, subida manual, otro flujo) no forma parte de P7.
- Un archivo **sobrescrito con el mismo nombre** no dispara *Cuando se crea un archivo*: depositarlo con otro nombre o ejecutar manualmente.
- `FECHA DE CARGA` no se modifica (defecto D-15 del motor, documentado).
