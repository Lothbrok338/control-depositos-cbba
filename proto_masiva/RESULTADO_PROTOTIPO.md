# P9 CONFIRMACIÓN MASIVA — Prototipo DIRECTO (sin lotes), datos ficticios

> **Fase actual: CONFIRMACIÓN MASIVA (solo las filas VALIDO, con ETag fresco) — implementada y probada localmente, NO validada en tenant: `CONFIRMACION_MASIVA.md`, pasos en `flows/INSTRUCCIONES_CONFIRMAR.md`.**
> Fase anterior: PREVALIDACIÓN REAL contra `Depositos_Activos` (solo lectura) — validada manualmente en el tenant.
> Reglas, internal names reales, contrato de respuesta, `detalle_json` y límites: **`PREVALIDACION_REAL.md`**. Pasos para el tenant: **`flows/ACTUALIZAR_FLUJO_PREVALIDACION.md`**.
> Lo descrito abajo como «TENANT VALIDATED» se refiere al **checkpoint estructural anterior** (Ejemplo de 3 filas → COMPLETADO); con la nueva versión el resultado de ese mismo archivo
> pasa a ser `OK`/`OBSERVADO` según haya o no depósitos coincidentes, y eso aún no se ha ejecutado en el tenant.

> ## ESTADO DE VALIDACIÓN (leer primero) — checkpoint 2026-10-06
>
> El detalle completo, con evidencia, está en **`ESTADO_CHECKPOINT_TENANT.md`**. Tres estados, que no se deben confundir:
>
> - **TENANT VALIDATED** (se ejecutó en Microsoft 365 con el Ejemplo de 3 filas): descarga de la plantilla por UniqueId (URL pegada en el navegador); control de adjuntos `frmArchivoP9`/`attXlsxP9`; registro de archivo; `.Run({name, contentBytes})`; `CreateFile`; Excel Online (Location = sitio personal, Document Library = OneDrive, File = `Id` dinámico, Table = `tblConfirmacionMasiva`); lectura de **3 filas**; retorno a Power Apps (**COMPLETADO**).
> - **OBSERVADO PERO NO RESUELTO:** `DeleteFile` → HTTP **423 Locked** (quedan `TMP_*.xlsx` en la carpeta temporal; los labels «Copia temporal» están ocultos); `Documents/Documents` anidados; dos carpetas `P9_MASIVA_TEMP`.
> - **PENDIENTE:** botón de `Main_Screen` (no agregado en el tenant); resto de smoke tests (vacía, sin tabla, encabezado cambiado, otra tabla); mediciones por tamaño; prevalidación real contra `Depositos_Activos`; confirmación masiva real; prueba multiusuario; limpieza de carpetas antes de producción.
>
> Las pruebas automáticas de este repositorio **son sintéticas/locales** (tenant simulado): no sustituyen al tenant. **Nunca se ha escrito en `Depositos_Activos`** ni se tocó ningún artefacto de producción; todos los cambios están bajo `proto_masiva/`. A partir de la fase «prevalidación real» el flujo **lo LEE** (un GET de solo lectura; ver `PREVALIDACION_REAL.md`), cosa que **todavía no está validada en el tenant**. **No hay confirmación real de depósitos todavía.**

Rama `experiment/p9-masiva-prototipo` (checkpoint de producción `3b407e2` intacto).

## QUÉ CAMBIÓ (decisión funcional: sin trazabilidad de lotes)

**Eliminado del diseño y del repositorio del prototipo:** `P9_MASIVA_PROTO_LOTES`, `Confirmaciones_Masivas`, `Confirmaciones_Masivas_Detalle`, `LOTE_UID`, historial de lotes, estados persistentes `PENDIENTE`/`PROCESANDO`, copia permanente del Excel, temporizador/sondeo y procesamiento asíncrono basado en listas. (También se eliminó el kit anterior de medición `RUNBOOK.md` / `REGISTRO_RESULTADOS.md`, que giraba en torno a esa lista.)

```
Main_Screen ──[IMPORTACIÓN MASIVA]──► P9_Confirmacion_Masiva
   DESCARGAR PLANTILLA · ADJUNTAR EXCEL · PREVALIDAR ARCHIVO
        │  .Run({name, contentBytes})          ← la app ESPERA la respuesta
        ▼
   flujo P9_MASIVA_PROTO_PREVALIDAR
        valida nombre/extensión → crea copia TMP_<guid>.xlsx en Documents/P9_MASIVA_TEMP
        → Excel Online lee tblConfirmacionMasiva → valida estructura, cuenta filas
        → INTENTA borrar la copia (en el tenant devuelve 423 Locked: ver ESTADO_CHECKPOINT_TENANT.md) → responde
        ▼
   la pantalla muestra:  ARCHIVO RECIBIDO · TABLA ENCONTRADA · 3 FILAS LEÍDAS
                         + mensaje, tiempo de la app, tiempos del flujo, ¿copia eliminada?
```

Si la app se cierra durante el proceso, se vuelve a cargar el Excel (no hay reanudación). La confirmación futura detectará lo ya confirmado por el estado real del depósito (`YA_CONFIRMADO` / `NO_DISPONIBLE`), no por un historial de lotes.

**El único artefacto residual** es la lista `P9_MASIVA_PROTO_ADJUNTO`: **vacía y nunca escrita**. Es **solo un vehículo técnico** para alojar el control de adjuntos: en Power Apps ese control solo vive dentro de un formulario y un formulario necesita un origen de datos. **No guarda lotes, estados, historial, trazabilidad ni archivos permanentes y no es parte de la lógica de negocio** (el flujo ni la referencia). Si en tu Studio puedes usar el control de adjuntos suelto, se elimina también (`sharepoint/INSTRUCCIONES_VEHICULO.md`).

## QUÉ SE PROBÓ [VALIDADO LOCALMENTE]

`OPENPYXL_LXML=False python -m pytest proto_masiva/tests -q -p no:cacheprovider` → **142 pasan** (con `lxml` instalado, dos pruebas de igualdad byte a byte de los `.xlsx` fallan por el entorno; ver `ESTADO_CHECKPOINT_TENANT.md` §7). Son pruebas **sintéticas/locales**, no validación de tenant.

| Archivo de pruebas | Cubre | Pruebas |
|---|---|---|
| `test_01_plantillas.py` | los 6 fixtures de A–E: 9 columnas, sin TIPO_CAMBIO, cuentas inventadas | 13 |
| `test_02_flujo_definicion.py` | estructura del flujo y del ZIP, disparador, cadena sin pasos en paralelo, referencias válidas, reintentos, solo 3 operaciones y ninguna lista, sin lotes ni estados, `PARAM_MAX_FILAS = 0` | 14 |
| `test_03_escenarios_sinteticos.py` | escenarios A–E y casos anómalos, fallos de copia/Excel/borrado, tamaño, tiempos, aislamiento | 36 |
| `test_04_powerapps.py` | YAML, 30 controles, la app llama al flujo con el archivo, sin temporizador ni lotes, salidas del flujo = las que usa la app, botón de `Main_Screen`, lista vehículo solo como vehículo técnico, descarga por UniqueId, `OnVisible` final, labels de copia ocultos | 23 |
| `test_05_plantillas_produccion.py` | Plantilla vacía y Ejemplo (catálogo extraído, 14 plantillas defectuosas rechazadas, fórmulas evaluadas en LibreOffice) | 43 |
| `test_06_medicion.py` | los 7 archivos de medición y que el protocolo no traiga cifras inventadas | 13 |

| # | Archivo (`xlsx/`) | Resultado en simulación |
|---|---|---|
| A | `Ejemplo_Confirmacion_Masiva_P9.xlsx` | `COMPLETADO · OK · filas_leidas = 3 · tabla = SI`, copia eliminada |
| B | `Plantilla_…P9.xlsx` (vacía), `02a_…`, `02b_…` | `ERROR · ARCHIVO_VACIO` (controlado; el flujo no falla) |
| C | `03_SIN_TABLA.xlsx` | `ERROR · TABLA_NO_ENCONTRADA` (**supuesto: Excel responde 404**) |
| D | `05_ENCABEZADO_CAMBIADO.xlsx` | `ERROR · ESTRUCTURA_INVALIDA` (nombra `CUENTA_BANCARIA`) |
| E | `04_TABLA_NOMBRE_DISTINTO.xlsx` | `ERROR · TABLA_NO_ENCONTRADA` |

Además, con tenant simulado: sin archivo / no-xlsx (`SIN_ARCHIVO`, `NO_ES_XLSX`; no se crea nada), xlsx corrupto (`ERROR_LECTURA_EXCEL`, no se confunde con tabla ausente), fallo al crear la copia, Excel bloqueado/500/404, **fallo al borrar la copia (el resultado de negocio no cambia; solo se informa `copia_temporal_eliminada = NO`)**, 1000 filas sin tope, y 2000 filas → `DEMASIADAS_FILAS` (la lectura alcanzó el umbral de paginación: se avisa en vez de contar de menos). Reintroduje a propósito 5 defectos (no borrar si falla Excel, que el borrado bloquee la respuesta, contar filas en blanco, quitar el aviso de umbral, clasificar mal la etapa de copia): las pruebas los detectan.

## QUÉ NO SE PROBÓ: tiempos y límites

La pregunta «¿el flujo directo termina en tiempos razonables, y hasta cuántas filas?» **sigue sin responderse por tamaño**. Solo hay dos mediciones sueltas de la validación (ver `MEDICION_TENANT.md`, «Observaciones sueltas»): una de ~14 s en la app y otra de ~22 s tras agregar a mano un Delay y reintentos al borrado. **No se generalizan.**

- El flujo **devuelve sus propios tiempos** (`crear / excel / borrar / total`) y la pantalla muestra además el tiempo medido por la app.
- `xlsx/medicion/Filas_NNNN.xlsx`: 10, 50, 100, 250, 500, 1000 y 2000 filas ficticias (17–94 KB). El protocolo y la tabla de `MEDICION_TENANT.md` siguen **en blanco** (`NO MEDIDO`).
- Si aparece un tiempo de espera real, la decisión ya tomada es **fijar un máximo de filas por archivo**: `PARAM_MAX_FILAS` (hoy 0 = sin tope) y no crear lotes. **No se fijó ningún máximo.** El umbral de paginación (2000) es la configuración de lectura de Excel, no un límite de negocio.
- Las mediciones son de **prevalidación (lectura)**; la confirmación hará además una lectura y una escritura por fila y tendrá su propio máximo.

## ESTADO DE LOS PASOS EN EL TENANT

| Paso | Estado |
|---|---|
| Lista vacía `P9_MASIVA_PROTO_ADJUNTO` con adjuntos habilitados | Hecho (el control de adjuntos funciona) |
| Carpetas `P9_MASIVA_TEMP` y `P9_MASIVA_PROTO` + plantilla subida | Hecho, con la salvedad de los `Documents` anidados y dos `P9_MASIVA_TEMP` (observado, no resuelto) |
| Flujo `P9_MASIVA_PROTO_PREVALIDAR` importado, configurado (Excel: sitio personal / OneDrive / `Id` / `tblConfirmacionMasiva`) y guardado | Hecho y probado con el Ejemplo |
| App `P9_PRUEBA_MASIVA` (copia) con la pantalla `P9_Confirmacion_Masiva`, `frmArchivoP9` + `attXlsxP9` y los 30 controles | Hecho y probado con el Ejemplo |
| `OnVisible` final (sin variable de URL) y labels de copia temporal ocultos | Hecho |
| Botón `IMPORTACIÓN MASIVA` en `Main_Screen` | Agregado y probado manualmente en `P9_PRUEBA_MASIVA` (navegación ida y vuelta) |
| Prevalidación real | Validada manualmente en el tenant (ver `ESTADO_CHECKPOINT_TENANT.md` §5b) |
| **Confirmación masiva** | **Implementada localmente (`CONFIRMACION_MASIVA.md`), NO validada en tenant. ESCRIBE en `Depositos_Activos`** |

## QUÉ SIGUE SIN ESTAR VALIDADO EN TENANT

- **Todo tiempo y todo límite por tamaño** (ver arriba).
- Las respuestas de error: plantilla vacía (`ARCHIVO_VACIO`), sin tabla (`TABLA_NO_ENCONTRADA`, supuesto HTTP 404), encabezado cambiado (`ESTRUCTURA_INVALIDA`), otra tabla, archivo abierto, no-xlsx.
- El clic de `btnDescargarPlantillaP9` con `Launch("<URL por UniqueId>")` dentro de la app (la URL sí se validó en el navegador).
- Listas desplegables y reglas de color de la plantilla en Excel Online (en Excel de escritorio se validaron las listas).
- Permisos y comportamiento con otros usuarios (prueba multiusuario).
- Cualquier parte de la prevalidación real contra `Depositos_Activos` y de la confirmación real.

## SIGUIENTES PASOS (en orden)

1. Smoke tests pendientes en el tenant, con los archivos de `xlsx/` (`MEDICION_TENANT.md`, tabla «Comportamiento»).
2. Mediciones por tamaño con `xlsx/medicion/` y, solo si hacen falta, `PARAM_MAX_FILAS`.
3. Integrar el botón en `Main_Screen` (`powerapps/BOTON_MAIN_SCREEN.txt`) en la copia `P9_PRUEBA_MASIVA`.
4. Prueba con un segundo usuario (permiso de lectura de la plantilla y flujo).
5. Antes de producción: ordenar las carpetas (`Documents` anidados, dos `P9_MASIVA_TEMP`) y mover la plantilla fuera de un OneDrive personal.
6. Después: prevalidación real y confirmación real, **en etapas separadas** (`ESTADO_CHECKPOINT_TENANT.md`, «Diseño futuro»).
7. Al terminar el prototipo, elimina lo temporal (`sharepoint/INSTRUCCIONES_VEHICULO.md` §3).

## MAPA DE ARCHIVOS (todo bajo `proto_masiva/`)

`CONFIRMACION_MASIVA.md` · `PREVALIDACION_REAL.md` · `ESTADO_CHECKPOINT_TENANT.md` · `flows/{prevalidacion.py, esquema_detalle_json.json, ejemplos_respuesta/, GUIA_ACCIONES_PREVALIDACION.md, ACTUALIZAR_FLUJO_PREVALIDACION.md, guia_manual.py}` · `powerapps/{PREVALIDACION_POWERFX.md, generar_powerfx.py}` · `xlsx/{Plantilla,Ejemplo}_Confirmacion_Masiva_P9.xlsx` · `xlsx/medicion/Filas_NNNN.xlsx` · `xlsx/` (6 fixtures de A–E) · `contrato_plantilla.py` · `catalogo_p9.py` + `catalogo_bancos_p9.json` · `generar_plantillas_produccion.py` · `generar_medicion.py` · `generar_xlsx.py` (fixtures) · `PLANTILLA_PRODUCCION.md` · `MEDICION_TENANT.md` · `SYNC_TENANT_UI.md` · `VALIDACION_TENANT_V1.md` · `ESCALA_1999.md` · `powerapps/{tenant/ y tenant_v1/ (exports REALES del tenant), auditar_iferror.py, P9_Confirmacion_Masiva.pa.yaml, …_CONTROLES_PEGAR.yaml, BOTON_MAIN_SCREEN.txt, BOTON_MAIN_SCREEN_PEGAR.yaml, Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml, INSTRUCCIONES_PEGADO.md, aplicar_boton.py, derivar_pegar.py}` · `flows/{construir.py, P9_MASIVA_PROTO_PREVALIDAR_definition.json, P9_MASIVA_PROTO_PREVALIDAR.zip, INSTRUCCIONES_FLUJO.md}` · `sharepoint/INSTRUCCIONES_VEHICULO.md` · `tests/`.
