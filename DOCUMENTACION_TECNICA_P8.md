# P8_CARGA_DEPOSITOS_ACTIVOS_V3_HASH_SHA256

Estado: revisión P8 V3 de la bitácora SHA256, aprobada para publicación en `candidate/p8-m365-pilot` y prueba en tenant. Validación de esta revisión en Microsoft 365 pendiente. P7/P6, motor, adaptador, doradas y Depositos_Activos conservados. Sin merge a main ni checkpoint.

**Compatibilidad V3:** el campo lógico y visible `SHA256` de Depositos_Cargas tiene InternalName `HASH_SHA256`. El flujo escribe `item/HASH_SHA256` con el mismo valor de `sha256_archivo_fuente` entregado por P7. Usar este paquete de carga actualizado junto a `P8_PROVISIONAR_LISTAS_V3_HASH_SHA256.zip`; las versiones anteriores escribían en otro nombre interno y no son compatibles con Cargas V3.

## 1. Entregables

- `P8_CARGA_DEPOSITOS_ACTIVOS_V3_HASH_SHA256.zip`: paquete de carga para importar. El flujo, el recurso del manifiesto y el paquete tienen el nombre visible `P8_CARGA_DEPOSITOS_ACTIVOS_V3_HASH_SHA256`. Usa identificadores de paquete distintos de versiones anteriores y se importa como nuevo. Conserva la estructura real de `NORMALIZADOR_POWER_AUTOMATE.zip`. No contiene URL de sitio, carpeta, usuario, tenant, conexión ni credencial real.
- `p8/flujo_p8_definition.json`: definición legible y versionable del flujo.
- `p8/esquema_listas_p8.json`: contrato completo de las dos listas, con tipos, obligatoriedad, índices, unicidad y opciones.
- `p8/construir_paquete_p8.py`: generador reproducible del JSON, el contrato de listas y el ZIP.
- `p8/definicion.py`: constructor de las acciones WDL corregidas.
- `p8/ensayo_wdl.py`: intérprete local limitado al subconjunto WDL usado aquí; recorre expresiones, acciones y `runAfter` con SharePoint simulado. No reemplaza el runtime de Microsoft.
- `p8/validar_p8.py`: inspección del paquete y ensayo del WDL para primera carga y reproceso; cuenta consultas e intentos reales del conector simulado.
- `tests/test_12_flujo_p8.py`: pruebas de fallos estructurales, timeout, reconsulta fallida, límites de diagnóstico, contrato y piloto ampliado.
- `p8/piloto_ampliado/`: segundo conjunto de cuatro movimientos, CSV y trazabilidad de cada fila; generado con `python -m p8.preparar_piloto`.
- `REPORTE_CORRECCION_P8.md` y `p8/evidencias/`: resultados comparativos de las suites y evidencia local.

Para regenerar y validar:

```bash
python p8/construir_paquete_p8.py
python -m p8.validar_p8
```

Los UUID del paquete son internos, deterministas y generados localmente. No identifican recursos de Microsoft 365. Al importar, Power Automate solicita una conexión SharePoint real.

## 2. Flujo implementado

Nombre exacto: `P8_CARGA_DEPOSITOS_ACTIVOS_V3_HASH_SHA256`.

```text
Archivo nuevo en carpeta SharePoint
  └─ solo DEPOSITOS_ACTIVOS__*.json
       └─ CONFIGURACION
            └─ TRY
                 ├─ Obtener contenido
                 ├─ Analizar JSON con esquema_parse_json_p7.json
                 ├─ validar esquema y las 26 columnas exactas
                 ├─ clasificar omitidos de P7
                 ├─ preconsultar cada CLAVE_TRANSACCION (todas antes de crear)
                 └─ por movimiento, con fila original
                      ├─ clave confirmada en preconsulta → YA_EXISTE
                      ├─ Crear movimiento
                      └─ si falla o expira: reconsultar CLAVE_TRANSACCION
                           ├─ existe → YA_EXISTE
                           └─ no existe → ERROR
                           └─ reconsulta falla o expira → ERROR de fila
            ├─ CATCH: identifica fallo estructural sin degradar errores de fila manejados
            └─ FINALLY: escribir una bitácora en Depositos_Cargas
                 └─ solo con escritura confirmada → Terminar
```

El disparador tiene concurrencia 1 para el piloto. La unicidad sigue protegiendo frente a ejecuciones simultáneas si esa configuración cambia más adelante.

El flujo no modifica elementos existentes. En un movimiento nuevo copia las 26 propiedades P7 y escribe únicamente `ESTADO_ASIGNACION = DISPONIBLE` entre los 8 campos operativos. No rellena los otros 7 campos operativos.

## 3. Defensa contra duplicados

La capa 1 ejecuta `Preconsultar_claves`, una consulta indexada exacta por cada `CLAVE_TRANSACCION`, antes de iniciar cualquier creación. Usa `GetItems`, filtro `CLAVE_TRANSACCION eq '…'` y `$top = 1` porque la columna es única. Una respuesta confirma existencia en SharePoint, incluyendo su comparación de acentos/mayúsculas; se guarda la clave original del JSON en `varClavesExistentes` para reconocerla después.

Decisión específica de P8 piloto: se retiró el filtro por `FECHA_MOVIMIENTO`. Así ninguna conversión UTC de «Solo fecha» puede excluir el primer o el último día. P7 permanece congelado; se conserva la columna Fecha y su índice. Hay ocho consultas previas para el primer piloto y cuatro para el segundo; no se optimiza volumen.

Si falla alguna preconsulta, la etapa queda `PRECONSULTA`, se registra `FALLIDO` y no comienza ninguna creación. El valor de `Claves_en_preconsulta` es evidencia de la capa 1: en el reproceso debe ser 8, con **cero ejecuciones de `Crear_movimiento`**. Obtener conteos 0/8 después de ocho rechazos de unicidad no supera esta prueba.

La capa 2 exige valores únicos en `Depositos_Activos.CLAVE_TRANSACCION`. Si `Crear elemento` falla **o termina en timeout**, ejecuta la reconsulta exacta; los apóstrofos se duplican para OData sin cambiar el valor almacenado:

- si la clave existe, cuenta `YA_EXISTE`;
- si no existe, cuenta `ERROR`;
- si falla/expira la reconsulta, `CATCH_RECONSULTA` cuenta `ERROR` y conserva fila, clave, estado y código HTTP de ambas acciones. Nunca se presume duplicado.

`Cerrar_fila` admite todos los estados de la condición previa y cuenta exactamente un resultado. Los bucles son secuenciales. Al finalizar se verifica el número de filas clasificadas; un Scope que refleje fallos de hijos manejados no transforma el lote en `FALLIDO`. Si todas las filas fueron tratadas pero alguna tiene error, el resultado es `COMPLETADO_CON_ERRORES`. Se desactivan los reintentos automáticos de las acciones SharePoint para que cada intento sea visible y un POST incierto pase por reconsulta.

Esta segunda consulta cubre la carrera entre dos ejecuciones: si ambas ven una clave ausente, una la crea y la otra recibe el rechazo de unicidad; la segunda confirma que ya existe y la clasifica correctamente.

## 4. Trigger y lectura binaria explícita

Se usa SharePoint «Cuando se crea un archivo (solo propiedades)», operación `GetOnNewFileItems`, con `splitOn` sobre `body/value`. Tras esa separación, sus propiedades son:

| Uso | Propiedad del trigger |
|---|---|
| Nombre con extensión y `ARCHIVO_JSON` | `triggerBody()?['{FilenameWithExtension}']` |
| Identificador para leer el contenido | `triggerBody()?['{Identifier}']` |
| Excluir carpetas | `triggerBody()?['{IsFolder}']` |

No se usa el ID numérico del elemento de biblioteca para leer bytes. La condición del trigger es:

```text
@and(
  equals(triggerBody()?['{IsFolder}'],false),
  startsWith(coalesce(triggerBody()?['{FilenameWithExtension}'],''),'DEPOSITOS_ACTIVOS__'),
  endsWith(coalesce(triggerBody()?['{FilenameWithExtension}'],''),'.json')
)
```

`Obtener_contenido_del_archivo` usa `GetFileContent`, el identificador anterior e **`inferContentType = false`**: camino binario, contenido genérico en el sobre `$content`. `Analizar_JSON` incorpora sin cambios `esquema_parse_json_p7.json` y decodifica explícitamente Base64:

```text
json(base64ToString(body('Obtener_contenido_del_archivo')?['$content']))
```

Durante el piloto, abrir la ejecución y revisar las salidas de `Obtener_contenido_del_archivo`:

- confirmar `inferContentType: false` en las entradas y `$content` en las salidas;
- confirmar la expresión exacta anterior en `Analizar_JSON`;
- confirmar que `Analizar_JSON` muestra `esquema = P7_DEPOSITOS_ACTIVOS_V1`, 26 nombres en `columnas` y 8 objetos en `movimientos`.

No hay detección automática de dos representaciones. Si el tenant devuelve un objeto JSON interpretado pese a esta configuración, se detiene el piloto: se registra `FALLIDO` en `PARSE_JSON`. Con la salida real revisada, el camino alternativo es `inferContentType = true` y contenido de Parse JSON `body('Obtener_contenido_del_archivo')`, sin leer `$content`. Debe aplicarse como un cambio conjunto y validado, no mezclarse con el camino binario entregado.

Referencias del conector y acciones: https://learn.microsoft.com/connectors/sharepointonline/ y https://learn.microsoft.com/power-automate/guidance/coding-guidelines/error-handling . Los campos de sitio, biblioteca, carpeta y conexión permanecen parametrizables; ninguna referencia es una URL de tenant.

## 5. Crear `Depositos_Activos`

1. En el sitio elegido: Microsoft Lists → Nueva lista → Lista en blanco.
2. Nombre exacto: `Depositos_Activos`.
3. En Configuración de la lista, editar `Title`, marcarla no obligatoria y ocultarla de la vista. No eliminarla.
4. Crear primero cada columna con el nombre técnico exacto de esta tabla. El nombre interno queda fijado al crear; no empezar con nombres con espacios o acentos y renombrarlos después.
5. En columnas numéricas usar 2 decimales y no porcentaje. En varias líneas usar texto sin formato.
6. Crear índices con la lista vacía.

### 5.1 Las 26 columnas P7

| Nombre técnico | Tipo | Obligatoria | Índice / regla |
|---|---|---:|---|
| `CLAVE_TRANSACCION` | Texto de una línea (255) | Sí | Valores únicos exigidos; indexada |
| `CODIGO_ASIGNACION` | Texto de una línea | No | Conserva ceros iniciales |
| `BANCO` | Texto de una línea | Sí | Indexada |
| `CUENTA_BANCARIA` | Texto de una línea | Sí | |
| `MONEDA` | Texto de una línea | Sí | |
| `FECHA_MOVIMIENTO` | Fecha y hora, solo fecha | Sí | Indexada |
| `HORA_MOVIMIENTO` | Texto de una línea | No | |
| `IMPORTE` | Número, 2 decimales | Sí | |
| `DEBITO` | Número, 2 decimales | No | Vacío se envía como nulo |
| `CREDITO` | Número, 2 decimales | No | Vacío se envía como nulo |
| `TIPO_MOVIMIENTO` | Texto de una línea | Sí | |
| `SALDO` | Número, 2 decimales | Sí | |
| `DESCRIPCION` | Varias líneas, texto sin formato | No | |
| `DEPOSITANTE_ORIGINANTE` | Varias líneas, texto sin formato | No | |
| `INFORMACION_ADICIONAL` | Varias líneas, texto sin formato | No | |
| `MOTOR_ESTADO` | Texto de una línea | No | Reservada P7 |
| `MOTOR_ESTUDIANTE` | Texto de una línea | No | Reservada P7 |
| `MOTOR_SOLICITADO_POR` | Texto de una línea | No | Reservada P7 |
| `MOTOR_SEDE_SOLICITANTE` | Texto de una línea | No | Reservada P7 |
| `MOTOR_CONFIRMADO_POR` | Texto de una línea | No | Reservada P7 |
| `MOTOR_FECHA_CONFIRMACION` | Texto de una línea | No | Reservada P7 |
| `MOTOR_OBSERVACION` | Varias líneas, texto sin formato | No | Reservada P7 |
| `TEXTO_BUSQUEDA` | Varias líneas, texto sin formato | No | |
| `ARCHIVO_ORIGEN` | Texto de una línea | Sí | |
| `LOTE_CARGA` | Texto de una línea | Sí | Indexada |
| `FECHA_CARGA` | Texto de una línea | Sí | Copiar sin transformar; defecto D-15 vigente |

### 5.2 Los 8 campos operativos

| Nombre técnico | Tipo | Obligatoria | Configuración inicial |
|---|---|---:|---|
| `ESTADO_ASIGNACION` | Opción | Sí | Único valor actual `DISPONIBLE`; predeterminado `DISPONIBLE`; sin valores de relleno; indexada |
| `ESTUDIANTE` | Texto de una línea | No | Vacío |
| `CODIGO_ESTUDIANTE` | Texto de una línea | No | Vacío |
| `SOLICITADO_POR` | Texto de una línea | No | Vacío |
| `SEDE_ASIGNACION` | Texto de una línea | No | Vacío |
| `USUARIO_ASIGNACION` | Texto de una línea | No | Vacío |
| `FECHA_HORA_ASIGNACION` | Fecha y hora, incluir hora | No | Vacío |
| `OBSERVACION` | Varias líneas, texto sin formato | No | Vacío |

No agregar estados operativos adicionales en P8. Se definirán con Power Apps en otra fase.

## 6. Crear `Depositos_Cargas`

Usar `P8_PROVISIONAR_LISTAS_V3_HASH_SHA256.zip` para crear y verificar automáticamente `Depositos_Cargas` en el sitio. El provisionador deja la columna de sistema `Title` no obligatoria y conserva su visibilidad. No es necesario crear columnas manualmente; la tabla siguiente documenta el contrato técnico:

| Nombre técnico | Tipo | Obligatoria | Índice / valores |
|---|---|---:|---|
| `LOTE_ID` | Texto de una línea | Sí | Indexada; no única porque el reproceso crea otra bitácora |
| `FECHA_HORA_PROCESO` | Fecha y hora, incluir hora | Sí | Indexada; valor `utcNow()` del flujo |
| `ARCHIVO_FUENTE` | Texto de una línea | Sí | |
| `HASH_SHA256` | Texto de una línea | Sí | Nombre lógico y visible: `SHA256` |
| `CANTIDAD_RECIBIDA` | Número, 0 decimales | Sí | |
| `CANTIDAD_VALIDA` | Número, 0 decimales | Sí | |
| `CANTIDAD_NUEVA` | Número, 0 decimales | Sí | |
| `CANTIDAD_YA_EXISTE` | Número, 0 decimales | Sí | |
| `CANTIDAD_ERROR` | Número, 0 decimales | Sí | |
| `ESTADO_LOTE` | Opción | Sí | `COMPLETADO`, `COMPLETADO_CON_ERRORES`, `FALLIDO`; sin relleno |
| `MENSAJE_ERROR` | Varias líneas, texto sin formato | No | |
| `ARCHIVO_JSON` | Texto de una línea | No | Nombre del archivo disparador |
| `ID_EJECUCION_FLUJO` | Texto de una línea | No | `workflow()?['run']?['name']` |

El contrato P8 representa explícitamente `nombre_tecnico=HASH_SHA256`, `nombre_logico=SHA256` y `nombre_visible=SHA256` solo para esta columna. El constructor de carga resuelve el nombre técnico desde ese mismo contrato. No cambia la propiedad P7 `sha256_archivo_fuente`, el algoritmo, el valor ni las 26 columnas de movimientos. El provisionador crea primero el campo con nombre/título HASH_SHA256 y después cambia solo su título visible a SHA256 por GUID; la verificación exige ambos valores exactos.

Para actualizar el piloto, seguir `DOCUMENTACION_PROVISION_P8.md`: conservar Activos, recrear Cargas solo si sigue vacía y la eliminación es manual, comprobar provisión OK, importar/configurar esta versión de carga y desactivar la anterior antes de activar el nuevo trigger. Una Cargas con datos no se migra ni se borra automáticamente. Si la lista fue recreada, seleccionar su identificador actual en la configuración del flujo. El ZIP general anterior es histórico y no contiene esta actualización.

El flujo crea un registro final por ejecución. `ARCHIVO_JSON` se inicializa desde el trigger antes de leer el archivo. JSON ilegible, versión/columnas inválidas o propiedad obligatoria ausente alcanzan `FINALLY` y escriben `FALLIDO`; los metadatos todavía desconocidos, incluido HASH_SHA256, usan `DESCONOCIDO` y los conteos desconocidos, 0. No se invoca `Terminar` dentro de `TRY` ni `CATCH`.

`Finalizar_ejecucion` solo admite `FINALLY = Succeeded`; por tanto `Terminar_FALLIDO` ocurre después de la escritura confirmada. Si SharePoint está inaccesible o rechaza la propia bitácora, ningún flujo puede garantizar persistencia allí: la ejecución queda fallida, no invoca `Terminar_procesado` y conserva el historial para diagnóstico/reproceso. Esta limitación externa está cubierta por una prueba local y requiere supervisión en el piloto.

Los conteos se cierran con:

```text
CANTIDAD_RECIBIDA = CANTIDAD_NUEVA + CANTIDAD_YA_EXISTE + CANTIDAD_ERROR
```

Si el invariante no cuadra, el lote queda `COMPLETADO_CON_ERRORES`. En un fallo estructural, `FINALLY` cuenta como error las filas sin resultado confirmado y conserva los creados/existentes conocidos. `CANTIDAD_VALIDA` conserva el significado P7: recibida menos omitidos ERROR, aunque después una creación falle. Si no llegó a validarse el contrato, su valor es 0.

### 6.1 Diagnóstico acotado

`MENSAJE_ERROR` es vacío en un lote completado sin errores. En otro caso contiene JSON estructurado con `etapa`, `archivo`, `mensaje`, `ejecucion`, `cantidad_error`, `errores` y `detalle_omitido`.

- Máximo **8 detalles**, cada uno reducido a menos de 800 caracteres serializados; límite final **8000 caracteres**. Si el sobre excediera el límite, se conserva la cabecera y se sustituye el detalle por una indicación para consultar el historial. El texto sigue siendo JSON válido.
- Cada error de fila contiene `fila`, `CLAVE_TRANSACCION`, `motivo` controlado y `codigo` resumido (estado `Failed`/`TimedOut`, código HTTP; 0 si no hubo respuesta HTTP). Las claves normales se conservan hasta 255 caracteres; solo un detalle excepcionalmente grande reduce su clave a 64 y la fila permite localizar el original.
- `fila` es la posición original de datos, base 1. Se reconstruye con el rango 1..recibida excluyendo `omitidos[].fila`; no se usa el índice reducido de candidatos nuevos.
- No se serializa `result()` ni cuerpos, cabeceras o mensajes arbitrarios del conector. Los omitidos remiten a la fila de entrada mediante un motivo controlado, sin copiar texto libre que pueda contener credenciales.
- Las etapas estructurales son `LECTURA`, `PARSE_JSON`, `CONTRATO`, `PRECONSULTA` y `MOVIMIENTOS`. `ID_EJECUCION_FLUJO` permite abrir los detalles técnicos autorizados en el historial.

## 7. Conexión y carpeta de entrada

1. Crear o elegir una biblioteca de documentos de SharePoint en el mismo sitio de las listas.
2. Crear una carpeta de piloto. Su ruta real sustituirá `<CARPETA_ENTRADA_M365>`.
3. La cuenta de la conexión SharePoint necesita:
   - lectura de la biblioteca y carpeta de entrada;
   - agregar y leer elementos en `Depositos_Activos`;
   - agregar elementos en `Depositos_Cargas`.
4. No guardar credenciales en el flujo ni en el repositorio.
5. Depositar únicamente entradas con patrón `DEPOSITOS_ACTIVOS__*.json`. El disparador rechaza `MANIFIESTO_P7__*.json` porque no comienza con ese prefijo.

El disparador es «Cuando se crea un archivo (solo propiedades)». Sobrescribir un archivo existente puede no dispararlo. Para reprocesar, crear un archivo nuevo con otro nombre que conserve el prefijo y la extensión `.json`.

## 8. Importar y parametrizar el flujo

1. Power Automate → Mis flujos → Importar → Importar paquete heredado.
2. Subir `P8_CARGA_DEPOSITOS_ACTIVOS_V3_HASH_SHA256.zip` y elegir **Crear como nuevo**. Comprobar el nombre visible exacto antes de activar el flujo.
3. En el recurso del flujo elegir Crear como nuevo.
4. En el recurso de conexión SharePoint elegir la conexión autorizada para el sitio piloto.
5. Importar y mantener el flujo desactivado mientras se configura.
6. Abrir el flujo y editar el disparador `Cuando_se_crea_un_archivo`:
   - Dirección del sitio: elegir el sitio real;
   - Nombre de biblioteca: elegir la biblioteca real;
   - Carpeta: elegir la carpeta real.
7. Abrir el ámbito `CONFIGURACION` y sustituir `<SITIO_SHAREPOINT>` en `PARAM_SITIO_SHAREPOINT` por la URL seleccionada desde el conector. Los nombres `Depositos_Activos` y `Depositos_Cargas` ya están definidos; si la interfaz exige identificadores, seleccionarlos desde sus desplegables y dejar que Power Automate escriba el valor real.
8. Revisar que todas las acciones SharePoint usen la conexión elegida. Guardar.
9. Verificar que la condición del disparador siga siendo exactamente el prefijo `DEPOSITOS_ACTIVOS__` y el sufijo `.json`.
10. Activar el flujo.

No escribir manualmente URL o GUID si el diseñador ofrece un selector. El paquete deja estos valores como marcadores precisamente para que el tenant los resuelva.

## 9. Piloto de 8 movimientos

### 9.1 Primera ejecución

Precondición: ambas listas vacías.

1. Copiar `ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json` a la carpeta de entrada.
2. Esperar la ejecución y abrir su historial.
3. Confirmar que `Analizar_JSON` leyó 8 movimientos y 0 omitidos.
4. Confirmar en `Depositos_Cargas`:
   - `CANTIDAD_RECIBIDA = 8`
   - `CANTIDAD_VALIDA = 8`
   - `CANTIDAD_NUEVA = 8`
   - `CANTIDAD_YA_EXISTE = 0`
   - `CANTIDAD_ERROR = 0`
   - `ESTADO_LOTE = COMPLETADO`
5. Confirmar 8 elementos en `Depositos_Activos`, todos con `ESTADO_ASIGNACION = DISPONIBLE`.
6. Comparar las 8 `CLAVE_TRANSACCION` con el JSON. Deben coincidir exactamente, incluidos acentos.
7. Usar como testigo **`FECHA_MOVIMIENTO = 2026-07-09`**: debe mostrarse como **9 de julio de 2026** y coincidir con el segmento **`20260709`** de `CLAVE_TRANSACCION`, nunca 7 de septiembre. Confirmar también los extremos 7 y 31 de julio. `FECHA_CARGA` conserva el texto P7 sin transformación.

### 9.2 Reproceso

1. Copiar el mismo contenido como un archivo nuevo, por ejemplo `DEPOSITOS_ACTIVOS__P7-3af418fcadd6__REPROCESO.json`.
2. Confirmar una segunda bitácora:
   - `CANTIDAD_RECIBIDA = 8`
   - `CANTIDAD_VALIDA = 8`
   - `CANTIDAD_NUEVA = 0`
   - `CANTIDAD_YA_EXISTE = 8`
   - `CANTIDAD_ERROR = 0`
   - `ESTADO_LOTE = COMPLETADO`
3. Confirmar que `Depositos_Activos` sigue teniendo 8 elementos, no 16.
4. En una vista o exportación, agrupar por `CLAVE_TRANSACCION`: cada clave debe tener frecuencia 1.
5. En el historial, `Claves_en_preconsulta = 8`. Revisar las ocho iteraciones de `Aplicar_a_cada_movimiento`: `Crear_movimiento` debe estar omitido en todas y tener **0 intentos**. Si hubo algún intento, el piloto de capa 1 falla aunque las cantidades finales cuadren.

### 9.3 Pruebas adicionales del piloto

- Intentar crear manualmente una novena fila con una clave ya existente: SharePoint debe rechazarla por unicidad.
- Confirmar que cada filtro OData es por `CLAVE_TRANSACCION` exacta; la fecha no interviene en la consulta. Verificar primera y última clave del lote.
- Confirmar la comparación de una clave con `CRÉDITO` y acento.
- Provocar un fallo controlado de creación en una lista de prueba y comprobar que la reconsulta distingue `YA_EXISTE` de `ERROR`.
- Verificar que un JSON con `esquema` distinto termina `FALLIDO` y no crea movimientos.
- Repetir con JSON ilegible y propiedad obligatoria ausente: verificar bitácora `FALLIDO` y `ARCHIVO_JSON` correcto antes de que la ejecución finalice.
- Provocar error/timeout de creación y fallo de reconsulta en una copia de piloto controlada: debe contar una fila ERROR, continuar y cerrar `COMPLETADO_CON_ERRORES`. Revisar `fila`, `CLAVE_TRANSACCION`, `motivo` y `codigo`.

### 9.4 Segundo conjunto de cuatro movimientos

Tras superar el piloto de ocho, subir `p8/piloto_ampliado/DEPOSITOS_ACTIVOS__P7-b4d991f026be.json`. Sus valores son copias exactas de filas existentes de `tests/golden/LOTE_12_LISTS.csv`; `TRAZABILIDAD.json` enlaza cada fila con la dorada y el fixture real, y fija el SHA-256 de la fuente. Se usa el serializador P7 sin cambiarlo.

| Fila piloto | Fixture | Fila de datos en dorada | Cobertura |
|---|---|---:|---|
| 1 | `union_mn_2.xls` | 9 | `BANCO UNIÓN`, `Ó`, espacio en clave, hora vacía |
| 2 | `bnb_mn_3.xls` | 24 | `DEPOSITANTE_ORIGINANTE` no vacío |
| 3 | `bcp_mn_3.xls` | 28 | `DEBITO = 458.82`, movimiento DÉBITO |
| 4 | `bnb_mn_3.xls` | 2319 | `CREDITO = -640.0` existente en la fuente; conservar signo |

Esperado: recibida 4, válida 4, nueva 4, existe 0, error 0; `COMPLETADO`. En la misma lista usada para los ocho anteriores, total 12. Reprocesar con nombre nuevo y contenido idéntico: cuatro coincidencias en preconsulta, cero intentos de crear, existe 4, nueva/error 0; total sigue en 12. No alterar importes, signo, hora, acentos, originante ni `FECHA_CARGA` para hacer pasar la prueba.

El crédito negativo se comprobó también en el Excel original `tests/fixtures/extractos/bnb_mn_3.xls`, hoja `Hoja 1`: transacción `3P8A146051`, fecha `11/08/2026`, hora `10:50:28`, crédito `-640.00`. La nueva muestra conserva el valor serializado por el motor/P7 (`-640.0`).

## 10. Pendientes que requieren tenant real

- Importar el ZIP y dejar que el tenant resuelva la conexión y los selectores de sitio, biblioteca, carpeta y listas.
- Confirmar las propiedades del trigger y la salida binaria de `Obtener_contenido_del_archivo` con `inferContentType = false`.
- Confirmar consultas exactas, ocho claves en preconsulta y cero intentos de creación en el reproceso. Verificar visualmente 9 de julio y los extremos del lote.
- Confirmar el comportamiento real de la columna única y las claves con acentos.
- Confirmar los tipos dinámicos que el conector genera para las columnas Opción y Número.
- Ejecutar los dos conjuntos del piloto y sus reprocesos; registrar evidencia del historial y de ambas listas.
- Medir después el comportamiento con cerca de 4000 movimientos. Esta versión realiza preconsultas y creaciones secuenciales para claridad; no está optimizada para ese volumen.

No se ha construido Power Apps y no se ha cambiado `FECHA_CARGA` ni el defecto D-15.
