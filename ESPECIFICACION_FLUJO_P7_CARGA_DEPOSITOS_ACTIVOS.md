# ESPECIFICACIÓN · Flujo de Power Automate `P7 - CARGA DEPOSITOS ACTIVOS`

Estado: **P7 en revisión**. Solo especificación: no hay flujo construido, no hay Power Apps. Diseño de la lista: `DISENO_LISTA_DEPOSITOS_ACTIVOS.md`. Generador del artefacto: `adaptador_m365.py`. Esquema para *Analizar JSON*: `esquema_parse_json_p7.json`. Ejemplo real: `ejemplos_p7/`.

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

**Depositos_Cargas** (lista de resultados por ejecución; se crea junto con la anterior — *propuesta de P7*, ver decisión D-2):

| Nombre técnico | Tipo | Contenido |
|---|---|---|
| `Title` | Texto | `lote_id` del artefacto |
| `ARCHIVO_JSON` | Texto | Nombre del artefacto procesado |
| `ARCHIVO_FUENTE` | Texto | `archivo_fuente` (normalmente `LISTS.csv`) |
| `SHA256_FUENTE` | Texto | `sha256_archivo_fuente` |
| `FECHA_HORA_PROCESO` | Fecha y hora | `utcNow()` al cerrar el flujo |
| `RECIBIDOS` | Número | `length(movimientos) + length(omitidos)` |
| `NUEVOS` | Número | Elementos creados |
| `YA_EXISTEN` | Número | Claves que ya estaban + repetidas en el archivo |
| `ERRORES` | Número | Filas `ERROR` + elementos que no se pudieron crear |
| `ESTADO_LOTE` | Opción | `COMPLETADO` · `COMPLETADO_CON_ERRORES` · `FALLIDO` |
| `DETALLE_ERRORES` | Varias líneas | JSON con `fila` / `clave` / `motivo` de cada error |
| `ID_EJECUCION_FLUJO` | Texto | `workflow()?['run']?['name']` |

Cada ejecución crea **un** registro (reprocesar el mismo archivo deja un segundo registro con `NUEVOS = 0`: es el rastro deseado, no un duplicado de movimientos).

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

1. **Inicializar variables** (enteros `varNuevos`, `varYaExisten`, `varErrores` = 0; matriz `varDetalle` = `[]`).
2. **Obtener contenido del archivo** (SharePoint) del archivo del desencadenador.
3. **Analizar JSON** — Contenido: `json(base64ToString(outputs('Obtener_contenido_del_archivo')?['body']?['$content']))` (si el conector devuelve el JSON ya interpretado, usar `body(...)`; confirmar en el piloto). Esquema: contenido de `esquema_parse_json_p7.json`.
4. **Condición de contrato:** `esquema = 'P7_DEPOSITOS_ACTIVOS_V1'` **y** `length(columnas) = 26`. Si no se cumple → **Terminar** (Error) con el motivo; cae en `Ambito_fallo`.
5. **Condición: `length(movimientos) > 0`.** Si es 0, saltar a 9 con `NUEVOS = 0` (lote vacío válido).
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
8. **Contar lo ya resuelto:**
   - `YA_EXISTEN` = `(length(movimientos) − length(nuevos)) + varYaExisten + <omitidos con estado YA_EXISTE>` (*Filtrar matriz* sobre `omitidos` con `estado = 'YA_EXISTE'`).
   - `ERRORES` = `varErrores` + `<omitidos con estado ERROR>`; añadir estos últimos (`fila`, `motivo`) a `DETALLE_ERRORES`.
9. **Registrar el resultado del lote:** *Crear elemento* en `<LISTA_DEPOSITOS_CARGAS>` con los campos del §3. `ESTADO_LOTE` = `COMPLETADO` si `ERRORES = 0`, si no `COMPLETADO_CON_ERRORES`.
10. `Ambito_fallo`: *Crear elemento* en `<LISTA_DEPOSITOS_CARGAS>` con `ESTADO_LOTE = FALLIDO`, `DETALLE_ERRORES` = `result('Ambito_principal')` y los datos del artefacto que se hayan podido leer. Reprocesar es seguro (la carga es idempotente).

## 6. Resultado por movimiento: `NUEVO` · `YA_EXISTE` · `ERROR`

| Estado | Quién lo decide | Condición | Efecto en `Depositos_Activos` |
|---|---|---|---|
| `NUEVO` | Flujo (paso 6/7) | CLAVE válida, no está en la lista | Se crea con `ESTADO_ASIGNACION = DISPONIBLE` |
| `YA_EXISTE` | Flujo (paso 6/7.3) o adaptador (`REPETIDA_EN_LOTE`) | CLAVE ya en la lista, o repetida en el mismo archivo | **Ninguno** |
| `ERROR` | Adaptador (validación) o flujo (fallo al crear no explicado por duplicado) | Fila inválida / no se pudo crear | **Ninguno**; queda en `DETALLE_ERRORES` |

`python adaptador_m365.py <LISTS.csv> <carpeta> --claves-existentes claves.txt` reproduce **fuera de Power Automate** esta misma clasificación (`CLASIFICACION_P7__<lote>.csv`), útil para ensayar y conciliar antes de cargar (`claves.txt`: una CLAVE por línea, exportada de la lista).

## 7. Idempotencia

- Mismo archivo procesado dos veces → mismas claves → `NUEVOS = 0`, todo `YA_EXISTE`, **cero elementos nuevos** (capa 1: comparación con la lista; capa 2: valores únicos exigidos en `CLAVE_TRANSACCION`).
- Extracto nuevo con fechas solapadas → solo entran los movimientos no cargados.
- El flujo **no modifica ni elimina** elementos existentes (no actualiza los ya asignados por Power Apps).
- Dos ejecuciones simultáneas: gana la primera en crear; la segunda recibe el rechazo de unicidad y lo registra como `YA_EXISTE`.

## 8. Pruebas de aceptación en el piloto (con la lista vacía)

1. Cargar `ejemplos_p7/DEPOSITOS_ACTIVOS__*.json` (8 movimientos): `NUEVOS = 8`, 8 elementos `DISPONIBLE`; cada valor igual al de `LISTS.csv` (incluidos importes con 2 decimales y espacios finales de `DESCRIPCIÓN`).
2. Volver a depositar el mismo archivo (otro nombre o *Volver a cargar*): `NUEVOS = 0`, `YA_EXISTEN = 8`, la lista sigue con 8 elementos.
3. Artefacto con un elemento repetido en el archivo y una fila con error: `YA_EXISTEN` y `ERRORES` reflejan `omitidos`.
4. Lote vacío (`movimientos: []`): termina sin error, `RECIBIDOS = 0`.
5. Dos ejecuciones simultáneas del mismo archivo: 8 elementos, sin duplicados.
6. Fecha del movimiento: `2026-07-07` queda como 7 de julio en la lista.

## 9. Límites y decisiones abiertas

- **D-2** `Depositos_Cargas` es un objeto nuevo (no pedido explícitamente; el registro del resultado necesita un destino). Alternativa: un archivo `RESULTADO_P7__<lote>.json` en una carpeta de resultados.
- **Volumen:** un lote de 4000 movimientos ≈ 4000 creaciones secuenciales (~1 s c/u); revisar los límites de solicitudes diarias de la licencia. En operación diaria los lotes son mucho menores; procesar un archivo por corrida del motor.
- **Cómo llega el JSON a la carpeta** (sincronización, subida manual, otro flujo) no forma parte de P7.
- Un archivo **sobrescrito con el mismo nombre** no dispara *Cuando se crea un archivo*: depositarlo con otro nombre o volver a ejecutar manualmente.
