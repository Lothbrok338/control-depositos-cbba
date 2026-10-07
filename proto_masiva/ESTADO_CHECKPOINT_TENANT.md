# P9 CONFIRMACIÓN MASIVA — Estado del checkpoint (prototipo validado parcialmente en tenant)

Fecha del checkpoint: 2026-10-06 · Rama `experiment/p9-masiva-prototipo` · Base anterior `5fc535c`.
Producción (`3b407e2`, `candidate/p9-reversion-pendiente-ux`) **no se tocó**: todo vive bajo `proto_masiva/`.

Este documento separa **tres estados que no deben confundirse**: **TENANT VALIDATED** (se ejecutó en el tenant y dio el resultado indicado), **OBSERVADO PERO NO RESUELTO** (se vio en el tenant y se decidió no resolverlo todavía) y **PENDIENTE** (no se ha hecho o no se ha probado en el tenant). Lo que no está en la primera tabla **no** está validado en tenant.

## Alcance funcional (diseño final, simple y síncrono)

```
Power Apps (P9_PRUEBA_MASIVA, pantalla P9_Confirmacion_Masiva)
  → el usuario descarga la plantilla XLSX → la completa → la adjunta → PREVALIDAR ARCHIVO
  → Power Automate (P9_MASIVA_PROTO_PREVALIDAR) recibe el archivo
  → crea una copia temporal TMP_<guid>.xlsx → Excel Online lee tblConfirmacionMasiva
  → valida estructura y cuenta filas → intenta borrar la copia → responde a Power Apps
```

**Todavía NO hay confirmación real de depósitos.** No existen: lotes, `LOTE_UID`, historial, lista `Confirmaciones_Masivas`, detalle persistente, sondeo, temporizador, procesamiento asíncrono, rollback global ni copia permanente del Excel. El Excel del usuario es su respaldo. No se consulta ni se modifica `Depositos_Activos`.

## 1 · TENANT VALIDATED

| # | Qué | Evidencia observada |
|---|---|---|
| 1 | **Descarga de la plantilla por UniqueId** | Al pegar `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu/_layouts/15/download.aspx?UniqueId=84b7ef88-43aa-43d2-8d1c-0f0b682dafbd` en el navegador, `Plantilla_Confirmacion_Masiva_P9.xlsx` **se descarga físicamente**; no abre Excel Online ni de escritorio. (Probado pegando la URL en el navegador; ver «Pendiente» sobre el clic del botón en la app.) |
| 2 | **Control de adjuntos en Power Apps** | `frmArchivoP9` (formulario de edición, `DataSource = P9_MASIVA_PROTO_ADJUNTO`, `FormMode.New`) con la tarjeta `dcAdjuntosP9` y el control `attXlsxP9` (`MaxAttachments = 1`, `MaxAttachmentSize = 10`, `Update = attXlsxP9.Attachments`). Sin `SubmitForm` ni `Patch`. |
| 3 | **Registro de archivo hacia el flujo** | `First(attXlsxP9.Attachments)` entrega `Name` y `Value`. |
| 4 | **Llamada `.Run({name, contentBytes})`** | `P9_MASIVA_PROTO_PREVALIDAR.Run({name: archivoP9.Name, contentBytes: archivoP9.Value})` funciona. El disparador (Power Apps V2) tiene **una** entrada de tipo Archivo llamada `file`. |
| 5 | **CreateFile (copia temporal)** | El flujo creó la copia en la carpeta temporal. |
| 6 | **Excel Online sobre el sitio personal** | *Leer tabla Excel / List rows present in a table* funcionó con: **Location** = `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`; **Document Library** = `OneDrive`; **File** = `Id` dinámico devuelto por *Crear archivo*; **Table** = `tblConfirmacionMasiva`. |
| 7 | **Lectura de la tabla y retorno a Power Apps** | Con `Ejemplo_Confirmacion_Masiva_P9.xlsx`: **COMPLETADO · ARCHIVO RECIBIDO · TABLA ENCONTRADA · 3 FILAS LEÍDAS**, mensaje «Archivo leído correctamente». |
| 8 | **Plantilla en Excel de escritorio** | Desplegable de bancos, cuentas dependientes (BCP muestra sus 2 cuentas), BISA y `CODIGO_ASIGNACION` conservan los ceros iniciales, `MONEDA` BOB/USD. |

Solo el **Ejemplo de 3 filas** se ejecutó de punta a punta. Ninguna otra prueba se debe llamar «validada en tenant».

## 2 · OBSERVADO PERO NO RESUELTO

| # | Qué se observó | Decisión actual |
|---|---|---|
| 1 | **`DeleteFile` devuelve HTTP 423 Locked** (`Microsoft.SharePoint.SPException` / `SPFileLockException`): Excel Online mantiene bloqueada la copia temporal tras leerla. Se probó a mano un **Delay de 10 s** y reintentos *Intervalo fijo, 2, PT5S*; **el archivo seguía sin eliminarse**. | **No se sigue resolviendo ahora.** Se acepta que queden `TMP_*.xlsx` en `P9_MASIVA_TEMP`. No se crea limpiador, lista de limpieza ni infraestructura. El flujo informa `copia_temporal_eliminada = NO` sin cambiar el resultado de negocio. El generador (`flows/construir.py`) conserva los reintentos *fixed, 2, PT5S* y **no** incluye el Delay probado a mano. |
| 2 | **Los labels «Copia temporal / NO se pudo eliminar» se ocultaron** en la app (`lblResCopiaTituloP9`, `lblResCopiaP9`) porque el usuario no necesita verlos. | El YAML los conserva con `Visible = false` (los 30 controles siguen existiendo). La lógica del flujo no se tocó. |
| 3 | **Carpetas `Documents/Documents` anidadas.** En el OneDrive de `gtorricot@univalle.edu` existe una carpeta llamada `Documents` dentro de la raíz `Documents`, y `P9_MASIVA_PROTO` quedó dentro de la anidada. | No se reorganiza desde Git ni se borra nada. Revisar **antes de producción**. |
| 4 | **Dos carpetas `P9_MASIVA_TEMP`** (una en cada `Documents`, según el listado de carpetas del servidor). Se desconoce en cuál escribe el flujo. | Igual: no se corrige aquí. El flujo de prevalidación funciona; no se tocan rutas en este checkpoint. |

Ruta real de la plantilla (devuelta por SharePoint): `/personal/gtorricot_univalle_edu/Documents/Documents/P9_MASIVA_PROTO/Plantilla_Confirmacion_Masiva_P9.xlsx` · **UniqueId** `84b7ef88-43aa-43d2-8d1c-0f0b682dafbd`. Por eso fallaban las rutas `…/Documents/P9_MASIVA_PROTO/…` (devolvían 404/«no existe»), el parámetro `SourceUrl` de `download.aspx` ruta-relativo, y el enlace compartido (`/:x:/g/…`), que abre Excel y no descarga.

**El UniqueId pertenece al archivo actual.** Si el archivo se borra y se crea otro, el UniqueId puede cambiar y habrá que actualizar la URL. Para actualizar la plantilla, **reemplazar el archivo o subir una nueva versión**, no borrar y recrear.

## 3 · Mediciones observadas (solo observaciones, no se generalizan)

Dos ejecuciones reales durante la validación (el archivo usado en cada una no quedó registrado en este checkpoint):

| | Power Apps | Flujo total | Crear archivo | Excel | Borrar |
|---|---|---|---|---|---|
| Ejecución 1 | 14,108 s | 10,443 s | 1,684 s | 5,259 s | 3,439 s |
| Ejecución 2 (tras agregar Delay y reintentos en el tenant) | 22,004 s | 19,216 s | 2,177 s | 3,738 s | 13,268 s |

El protocolo de medición por tamaño (10…2000 filas) **sigue sin ejecutarse**: ver `MEDICION_TENANT.md`.

## 4 · PENDIENTE (no validado en tenant)

- ~~Botón «IMPORTACIÓN MASIVA» en `Main_Screen`~~ → **agregado y probado manualmente en `P9_PRUEBA_MASIVA` (2026-10-07):** navegación Main_Screen → pantalla → VOLVER → Main_Screen validada. Sigue sin export en el repo; `Main_Screen` de producción no se tocó.
- **Clic del botón DESCARGAR PLANTILLA dentro de la app** con `Launch("<URL por UniqueId>")`: la URL se validó pegada en el navegador; no se registró una prueba del clic en la app publicada ni en otros navegadores/equipos.
- **Smoke tests adicionales**: plantilla vacía → `ARCHIVO_VACIO`; `03_SIN_TABLA.xlsx` → `TABLA_NO_ENCONTRADA` (supuesto: Excel responde 404); `05_ENCABEZADO_CAMBIADO.xlsx` → `ESTRUCTURA_INVALIDA`; `04_TABLA_NOMBRE_DISTINTO.xlsx` → `TABLA_NO_ENCONTRADA`; archivo abierto; archivos no `.xlsx`.
- **Mediciones por tamaño** (10, 50, 100, 250, 500, 1000, 2000 filas) y decisión de un máximo de filas (`PARAM_MAX_FILAS` sigue en 0).
- **Comportamiento de la plantilla en Excel Online** (listas desplegables y reglas de color): solo se probó Excel de escritorio.
- **Prevalidación real contra `Depositos_Activos`** y **confirmación masiva real** (ver «Diseño futuro»).
- **Prueba multiusuario**: permisos de lectura de otros usuarios sobre la plantilla y concurrencia.
- **Limpieza de la arquitectura de carpetas** antes de producción (Documents anidados, dos `P9_MASIVA_TEMP`, plantilla en un OneDrive personal).

## 5 · Plantilla `Plantilla_Confirmacion_Masiva_P9.xlsx`

9 columnas exactas: `BANCO`, `CUENTA_BANCARIA`, `CODIGO_ASIGNACION`, `IMPORTE`, `MONEDA`, `ESTUDIANTE`, `SOLICITADO_POR`, `SEDE`, `OBSERVACION`. **No existe `TIPO_CAMBIO`**: el tipo de cambio USD no participa en la confirmación; se pedirá solo al imprimir el comprobante, como en la confirmación individual. `CODIGO_ESTUDIANTE` no está en la plantilla y la confirmación futura lo enviará como `""`. Futuros campos requeridos: `ESTUDIANTE`, `SOLICITADO_POR`, `SEDE` (`OBSERVACION` opcional; `SEDE` vacía será error, sin autocompletar).

Bancos: BNB, BCP, BISA, BANCO UNIÓN, BANCO ECONÓMICO, BMSC (13 cuentas, ver `catalogo_bancos_p9.json`). «(Todos)» solo existe como comodidad visual en Power Apps; no es un banco.

## 5b · Fases siguientes

**Prevalidación real — validada manualmente en el tenant (2026-10-07)**, según lo confirmado por Gabriel: carga XLSX, `tblConfirmacionMasiva`, varias filas, consulta a `Depositos_Activos`, resultado global `OK`/`OBSERVADO`, `VALIDO`, `NO_DISPONIBLE` (para `ASIGNADO`), `NO_ENCONTRADO`, `DUPLICADO_ARCHIVO`, `FILA_INCOMPLETA`, fila + mensaje, y que no modifica `Depositos_Activos`; al pegar varias filas desde la primera de la tabla, Excel la amplía sola. **Sigue sin validar** lo que no se mencionó (día de borde de la ventana de 2 meses, volumen y tiempos grandes, multiusuario).

**Confirmación masiva — implementada localmente, NO validada en tenant:** `CONFIRMACION_MASIVA.md`.

### Detalle de la prevalidación real (histórico)

La sección 6 describía la prevalidación contra `Depositos_Activos` como diseño futuro. **Ya está implementada** (solo lectura) y probada con un tenant simulado:
`PREVALIDACION_REAL.md`. **Nada de ella está en la lista «TENANT VALIDATED» de este documento**: no se ha importado ni ejecutado en Power Automate ni en Power Apps.
La **confirmación real** (releer por ID, ETag, `If-Match`, MERGE, `412` = `CONFLICTO`) sigue **sin implementar**.

## 6 · Diseño futuro — NO IMPLEMENTADO, NO VALIDADO (la parte de confirmación; la prevalidación ya existe, ver 5b)

Solo como referencia para las siguientes etapas; **nada de esto existe en el código de este checkpoint**.

- **Prevalidación contra `Depositos_Activos`:** solo `CREDIT`, misma ventana de los últimos 2 meses que la galería individual. Coincidencia por `BANCO` + `CUENTA_BANCARIA` + `CODIGO_ASIGNACION` + `IMPORTE`; `MONEDA` se valida. Más de una coincidencia → `ASIGNACION_AMBIGUA`. Sin fecha en V1. Duplicados dentro del mismo Excel: se bloquean todas las filas involucradas.
- **Confirmación real por fila,** preservando exactamente V4.2: relectura, `ID`, `CLAVE_TRANSACCION`, estado `DISPONIBLE`, ETag concreto, `If-Match`, reintentos ninguno, MERGE, `412` = `CONFLICTO` y los mismos 8 campos atómicos de la confirmación individual.

## 7 · Cómo se ejecutan las pruebas

`OPENPYXL_LXML=False python -m pytest proto_masiva -q`. Con `lxml` instalado, `openpyxl` serializa distinto y dos pruebas que comparan byte a byte los `.xlsx` versionados con la salida del generador (`test_05…es_determinista`, `test_06…pesan_poco`) fallan por el entorno, no por el repositorio.
