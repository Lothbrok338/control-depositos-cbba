# P8.5 · Certificación E2E: Excel bancario → LISTS.csv → JSON → SharePoint

Flujo: `P8_CARGA_DEPOSITOS_ACTIVOS_V7_CERTIFICACION_E2E_ORIGEN` (paquete `P8_CARGA_DEPOSITOS_ACTIVOS_V7_CERTIFICACION_E2E_ORIGEN.zip`).
Estado: **P8.5 = DESARROLLADO Y PROBADO LOCALMENTE** (rama `candidate/p8-5-certificacion-e2e`; SharePoint simulado). **Validación E2E real en tenant = PENDIENTE** para la prueba final del sistema (ver §8).
V5 no se modifica. Trigger, sitio, biblioteca, carpeta y GUID de listas son los de V5. El motor, los normalizadores y el adaptador P7 no se tocan.

La certificación tiene dos mitades que se combinan:
1. **Origen** (`p8/control_origen.py`, antes de subir): ¿todo lo que había en cada Excel llegó al LISTS.csv / JSON?
2. **SharePoint** (flujo V7): ¿todo lo que trae el JSON está realmente en `Depositos_Activos` con la misma identidad financiera?

## 1. Control de origen (nuevo paso, fuera de Power Automate)
Lee solo `ORIGEN.xlsx` y `LISTS.csv` que el motor ya produce, y "sella" el artefacto con un bloque `control_origen`:
```
python -m p8.control_origen ORIGEN.xlsx LISTS.csv DEPOSITOS_ACTIVOS__<lote>.json --salida <carpeta_nueva>
```
Se sube a SharePoint el artefacto **sellado** que queda en `--salida` (los movimientos van byte a byte iguales; solo se añade `control_origen`).
También escribe `CONTROL_ORIGEN_P8_5__<lote>.csv` con una fila por archivo:
`ARCHIVO_ORIGEN, BANCO, CUENTA, MOVIMIENTOS_ORIGEN, MOVIMIENTOS_NORMALIZADOS, DIFERENCIA_ORIGEN, ESTADO_INTEGRIDAD_ORIGEN` (+ `MOTIVOS`).
Termina con código 0 si `INTEGRIDAD_ORIGEN = OK` y 1 si no; el sellado se escribe en ambos casos.

Por archivo bancario (ARCHIVO ORIGEN), `OK` solo si se cumplen todos:
| Control | Qué verifica |
|---|---|
| Origen | filas con rol `MOVIMIENTO` en `DATOS_ORIGINALES` (recuento propio), iguales a `FILAS_MOVIMIENTO` de `METADATOS_EXTRACTO` |
| Mapa | movimientos de `MAPA_ORIGEN` = filas de origen |
| LISTS | filas de `LISTS.csv` de ese archivo = movimientos del mapa |
| 1:1 | mismas claves y mismas filas de Excel entre origen, mapa y LISTS; ninguna repetida |
| Banco/cuenta | `BANCO` y `CUENTA BANCARIA` de todas las filas = los detectados para el archivo; un archivo con movimientos pero sin banco/cuenta detectados es `ERROR` |
| Filas no reconocidas | ninguna fila `FILA_ESPECIAL`/`PIE` parece un movimiento (tiene fecha **y** número) |
Un archivo en LISTS.csv sin metadatos de origen es `ERROR`. `INTEGRIDAD_ORIGEN = OK` solo si hay al menos un archivo y **todos** están `OK`.

**Por qué el último control.** El rol `MOVIMIENTO` lo asigna P1 a las filas que el normalizador produjo. Un movimiento que el normalizador descartara en silencio quedaría como `FILA_ESPECIAL` o `PIE` y no aparecería en el recuento de origen. Ese control cierra esa brecha sin leer el Excel original ni tocar el motor. Es heurístico: una fila de pie con fecha y número sin etiqueta de saldo/total dará un `ERROR` falso que se revisa a mano. En los 12 extractos reales no da ninguno.
**Lote de carga:** no se exige que `ORIGEN.xlsx` y `LISTS.csv` tengan el mismo `LOTE DE CARGA`; la correspondencia exacta por clave y fila ya los liga (el ejemplo del repo viene de dos corridas distintas).

## 2. Cómo se liga con el JSON y con V7 (cero llamadas SharePoint)
El bloque `control_origen` viaja dentro del JSON que el flujo ya lee. V7 lo toma en dos acciones Set variable y marca `INTEGRIDAD_ORIGEN = OK` solo si:
`control_origen.integridad_origen = 'OK'` **y** `control_origen.sha256_lists = sha256_archivo_fuente` del JSON **y** `control_origen.movimientos_normalizados = CANTIDAD_RECIBIDA`.
Un JSON sin bloque, con otro hash o con otro total de filas queda en `ERROR`. El esquema de «Analizar JSON» declara `control_origen` como objeto opcional; `esquema_parse_json_p7.json` no cambia.

## 3. Certificación SharePoint (por fila) — sin consultas nuevas
Se compara el registro almacenado con el del JSON en 9 campos: `CLAVE_TRANSACCION`, `BANCO`, `CUENTA_BANCARIA`, `FECHA_MOVIMIENTO`, `HORA_MOVIMIENTO`, `CODIGO_ASIGNACION`, `TIPO_MOVIMIENTO`, `IMPORTE`, `SALDO`.
`LOTE_CARGA` y `ARCHIVO_ORIGEN` no se comparan (una transacción puede reaparecer en otra descarga) y se conservan. Resultado por fila: CONFIRMADO, DIFERENCIA (cubre cruces de banco/cuenta) o FALTANTE.
| Caso de la fila | Registro que se compara |
|---|---|
| Preconsulta la encuentra (YA_EXISTE) | el item de `Obtener_clave_preexistente` |
| `Crear_movimiento` tiene éxito (NUEVA) | el cuerpo de la respuesta del POST |
| Creación incierta y la reconsulta la encuentra | el item de `Reconsultar_CLAVE_TRANSACCION` |
| Creación falla y la reconsulta no la encuentra | sin registro: FALTANTE (y ERROR, como en V5) |

## 4. Regla final
`ESTADO_CERTIFICACION = CERTIFICADO` solo si **todo** esto se cumple:
`INTEGRIDAD_ORIGEN = OK` · `CANTIDAD_ESPERADA = CANTIDAD_CONFIRMADA` · `CANTIDAD_FALTANTE = 0` · `CANTIDAD_DIFERENCIA = 0` · `CANTIDAD_ERROR = 0`
y además: sin fallo estructural, procesamiento completo y conteos consistentes.
**Lote de 0 movimientos:** no se certifica por vacuidad. Solo se certifica si el control de origen demuestra que todos los archivos procesados tenían 0 movimientos (`origen_vacio_demostrado`).
`FALTANTE = ESPERADA − CONFIRMADA − DIFERENCIA` (incluye toda fila no confirmada). `ESTADO_LOTE` conserva su significado. Si no certifica, `MENSAJE_ERROR` trae el detalle aunque `ESTADO_LOTE` sea `COMPLETADO` (solo nombres de campos, p. ej. `DIF:BANCO;CUENTA_BANCARIA;`).
**Un JSON sin sellar (como los de V5) nunca certifica**: queda `NO_CERTIFICADO` con `INTEGRIDAD_ORIGEN = ERROR`, aunque todo esté en SharePoint.

## 5. Antes de importar V7: crear 6 columnas en `Depositos_Cargas` (una sola vez)
V7 las escribe; sin ellas la importación falla (Power Automate valida `item/*` contra la lista real). Definición exacta: `p8/esquema_certificacion_p8_5.json` (aparte de `esquema_listas_p8.json`, para no alterar el contrato del provisionador).
1. Abrir `Depositos_Cargas` → **+ Agregar columna**.
2. **Número** → nombre `CANTIDAD_ESPERADA` → decimales **0** → no obligatoria → **Guardar**. Repetir con `CANTIDAD_CONFIRMADA`, `CANTIDAD_FALTANTE` y `CANTIDAD_DIFERENCIA`.
3. **Elección** → `ESTADO_CERTIFICACION` → opciones `CERTIFICADO` y `NO_CERTIFICADO` (una por línea) → valores de relleno **No** → sin valor predeterminado → no obligatoria → **Guardar**.
4. **Elección** → `INTEGRIDAD_ORIGEN` → opciones `OK` y `ERROR` → valores de relleno **No** → sin predeterminado → no obligatoria → **Guardar**.
5. Escribir el nombre técnico exacto **al crear** la columna (el nombre interno no se puede cambiar). Las bitácoras anteriores quedan con estos campos vacíos (= no evaluadas).

## 6. Supuestos a confirmar en el primer run del tenant
- **POST de `Crear_movimiento` trae los campos almacenados.** Si no, las filas nuevas saldrían DIFERENCIA (falla hacia el lado seguro). Se ve abriendo sus salidas en el historial; solo entonces se justificaría una consulta nueva.
- **Fecha:** se compara la parte `AAAA-MM-DD` del valor devuelto. Un desfase por zona horaria saldría como DIFERENCIA en `FECHA_MOVIMIENTO`.
- **Texto:** se asume que `equals` distingue mayúsculas; un texto vacío puede volver `null` y se trata como vacío. **Números:** se comparan como números.
- **Parse JSON:** el bloque `control_origen` se declara como objeto opcional. Debe leerse sin problema; si `INTEGRIDAD_ORIGEN` saliera `ERROR` con un JSON bien sellado, es lo primero que revisar.
- **Misma tanda:** el control de origen asume que `ORIGEN.xlsx` y `LISTS.csv` son de la misma tanda de extractos.

## 7. Regla de alcance: archivos, bancos o cuentas ausentes (decisión)
La certificación E2E aplica **exclusivamente a los archivos que efectivamente fueron recibidos y procesados** en la carga.
La ausencia de un archivo, banco o cuenta esperado es solo una **ADVERTENCIA DE COBERTURA**, no un defecto de la carga. Motivo: hay cuentas que legítimamente no tienen movimientos durante días, semanas o meses.

Esa ausencia **no debe**:
- bloquear el procesamiento;
- cambiar `INTEGRIDAD_ORIGEN`;
- cambiar `ESTADO_CERTIFICACION`;
- generar `CANTIDAD_ERROR`;
- impedir `CERTIFICADO`.

Estado de implementación: **solo documentada.** V7 no agrega lógica para esta regla y no necesita ninguna para cumplirla: el control de origen y el flujo evalúan únicamente los archivos presentes en `ORIGEN.xlsx`/`LISTS.csv`, y nunca comparan contra una lista de archivos, bancos o cuentas esperados. Un extracto recibido sin movimientos (por ejemplo `bisa_me_2.xls` en el ejemplo real: 0 filas, sin banco ni cuenta detectados) queda `OK` en el control de origen.
La advertencia de cobertura en sí (detectar y avisar qué cuentas esperadas no llegaron) **no existe todavía**; si se construye, debe ser un aviso informativo separado, sin ninguna de las consecuencias anteriores.
Lo que sigue bloqueando la certificación es lo contrario: un archivo **sí recibido** cuyo contenido no cuadra (movimientos de origen que no llegaron, banco/cuenta cruzados, etc.).

## 8. Estado de P8.5 y prueba final pendiente
| Elemento | Estado |
|---|---|
| Control de origen (`p8/control_origen.py`), sellado del JSON y flujo V7 | **Desarrollado y probado localmente** (tests `test_12` a `test_15`; 12 extractos reales: Excel → LISTS → JSON sellado → V7 simulado = `CERTIFICADO`) |
| Importación y ejecución de V7 en el tenant | **Pendiente.** No se ha importado ni probado en el tenant |
| Validación E2E real en tenant | **Pendiente para la prueba final del sistema** |
| V6 | Eliminado: nunca se importó ni se validó; superseded por V7. No se versiona |

La prueba final se hará cuando esté construido el resto del flujo:
`Excel bancario → normalización → control de origen → JSON sellado → Power Automate V7 → Depositos_Activos → certificación E2E → flujo operativo de asignación.`
Antes de esa prueba, las 6 columnas de la sección 5 deben existir en `Depositos_Cargas`, y los supuestos de la sección 6 se confirman en el primer run.
Regla vigente (sección 7): la ausencia de un archivo/banco/cuenta esperado es solo una **advertencia de cobertura** y nunca bloquea la certificación de los archivos que sí fueron recibidos.
Nota: un comentario en `p8/construir_paquete_p8.py` (`construir_esquema_certificacion`) aún dice «importar V6»; se refiere a V7 y no se corrigió para no tocar código en este cierre.
