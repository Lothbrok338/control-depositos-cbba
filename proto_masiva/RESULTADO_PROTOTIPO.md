# P9 CONFIRMACIÓN MASIVA — Prototipo DIRECTO (sin lotes), datos ficticios

> ## ESTADO DE VALIDACIÓN (leer primero)
>
> - **139/139 pruebas son sintéticas/locales**: usan un tenant simulado dentro de este repositorio, no Power Automate, SharePoint ni Excel Online reales.
> - **NO hay validación real en tenant.** Nada se ha ejecutado todavía en Microsoft 365, y **no se ha medido ningún tiempo ni límite**. `MEDICION_TENANT.md` está en blanco a propósito.
> - **Nombres internos de varias operaciones de Power Automate siguen por validar** (entrada de tipo Archivo del disparador, `CreateFile`, `DeleteFile`, Excel `GetItems`): se escribieron de memoria, sin poder consultar la documentación de Microsoft.
> - **El control de adjuntos y la forma de la llamada `.Run({name, contentBytes})` requieren validación manual en Studio.**
> - **No se ha tocado `Depositos_Activos`** ni ningún artefacto de producción: el prototipo no lo consulta ni lo modifica, y todos los cambios están bajo `proto_masiva/`.

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
        → BORRA la copia (pase lo que pase) → responde
        ▼
   la pantalla muestra:  ARCHIVO RECIBIDO · TABLA ENCONTRADA · 3 FILAS LEÍDAS
                         + mensaje, tiempo de la app, tiempos del flujo, ¿copia eliminada?
```

Si la app se cierra durante el proceso, se vuelve a cargar el Excel (no hay reanudación). La confirmación futura detectará lo ya confirmado por el estado real del depósito (`YA_CONFIRMADO` / `NO_DISPONIBLE`), no por un historial de lotes.

**El único artefacto residual** es la lista `P9_MASIVA_PROTO_ADJUNTO`: **vacía y nunca escrita**. Es **solo un vehículo técnico** para alojar el control de adjuntos: en Power Apps ese control solo vive dentro de un formulario y un formulario necesita un origen de datos. **No guarda lotes, estados, historial, trazabilidad ni archivos permanentes y no es parte de la lógica de negocio** (el flujo ni la referencia). Si en tu Studio puedes usar el control de adjuntos suelto, se elimina también (`sharepoint/INSTRUCCIONES_VEHICULO.md`).

## QUÉ SE PROBÓ [VALIDADO LOCALMENTE]

`python -m pytest proto_masiva/tests -q -p no:cacheprovider` → **139 pasan**.

| Archivo de pruebas | Cubre | Pruebas |
|---|---|---|
| `test_01_plantillas.py` | los 6 fixtures de A–E: 9 columnas, sin TIPO_CAMBIO, cuentas inventadas | 13 |
| `test_02_flujo_definicion.py` | estructura del flujo y del ZIP, disparador, cadena sin pasos en paralelo, referencias válidas, reintentos, solo 3 operaciones y ninguna lista, sin lotes ni estados, `PARAM_MAX_FILAS = 0` | 14 |
| `test_03_escenarios_sinteticos.py` | escenarios A–E y casos anómalos, fallos de copia/Excel/borrado, tamaño, tiempos, aislamiento | 36 |
| `test_04_powerapps.py` | YAML, 30 controles, la app llama al flujo con el archivo, sin temporizador ni lotes, salidas del flujo = las que usa la app, botón de `Main_Screen`, lista vehículo solo como vehículo técnico | 20 |
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

La pregunta «¿el flujo directo termina en tiempos razonables?» **solo se responde en el tenant**. Está preparado, sin ninguna cifra supuesta:

- El flujo **devuelve sus propios tiempos** (`crear / excel / borrar / total`) y la pantalla muestra además el tiempo medido por la app.
- `xlsx/medicion/Filas_NNNN.xlsx`: 10, 50, 100, 250, 500, 1000 y 2000 filas ficticias (17–94 KB).
- `MEDICION_TENANT.md`: protocolo y tabla **en blanco** (`NO MEDIDO`).
- Si aparece un tiempo de espera real, la decisión ya tomada es **fijar un máximo de filas por archivo**: `PARAM_MAX_FILAS` (hoy 0 = sin tope) y no crear lotes. **No se fijó ningún máximo.** El umbral de paginación (2000) es la configuración de lectura de Excel, no un límite de negocio; sirve para no devolver un recuento truncado.
- Las mediciones son de **prevalidación (lectura)**; la confirmación hará además una lectura y una escritura por fila y tendrá su propio máximo.

## QUÉ NECESITO HACER YO

**En SharePoint** (`sharepoint/INSTRUCCIONES_VEHICULO.md`): lista vacía `P9_MASIVA_PROTO_ADJUNTO` con adjuntos habilitados; carpetas `Documents/P9_MASIVA_TEMP` (temporal, vacía) y `Documents/P9_MASIVA_PROTO` (con la Plantilla).

**En Power Automate** (`flows/INSTRUCCIONES_FLUJO.md`): importar `P9_MASIVA_PROTO_PREVALIDAR.zip` y **revisar 4 puntos** (entrada de tipo Archivo del disparador, `Crear_archivo`, `Leer_tabla_Excel`, `Borrar_copia_temporal`).

**En Power Apps** (`powerapps/INSTRUCCIONES_PEGADO.md`), en una **copia** de la app: agregar la lista vehículo y el flujo; crear la pantalla; **un solo control manual** (el formulario `frmArchivoP9` con el control de adjuntos renombrado `attXlsxP9`); pegar `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml`; escribir `OnVisible`; añadir un botón a `Main_Screen` (`powerapps/BOTON_MAIN_SCREEN.txt`: 79 → 80 controles, ninguno otro cambia).

## QUÉ SIGUE SIN ESTAR VALIDADO EN TENANT

- **Todo tiempo y todo límite** (ver arriba).
- Nombres internos de `CreateFile`, `DeleteFile`, Excel `GetItems` y la **entrada de tipo Archivo** del disparador.
- Que `.Run({name, contentBytes})` sea la forma de llamada que acepta tu Studio.
- Que el control de adjuntos conserve `attXlsxP9.Attachments` **sin enviar el formulario**.
- El comportamiento real de Excel Online: código HTTP con tabla ausente (supuesto 404), tabla vacía, encabezado cambiado, archivo abierto, tiempo hasta poder leer un archivo recién creado, y si retiene el archivo e impide borrarlo (el flujo lo informa en `copia_temporal_eliminada`).
- `Launch(…?download=1)` y los permisos de los usuarios.

## PASOS PARA GABRIEL

1. Crea la lista vacía `P9_MASIVA_PROTO_ADJUNTO` y las carpetas `P9_MASIVA_TEMP` y `P9_MASIVA_PROTO`; sube la Plantilla a la segunda.
2. Power Automate: importa el ZIP del flujo y revisa los 4 puntos de `flows/INSTRUCCIONES_FLUJO.md`; déjalo **Activado**.
3. Power Apps: guarda una **copia** de la app P9; agrega la lista vehículo y el flujo.
4. Crea la pantalla `P9_Confirmacion_Masiva` y el formulario `frmArchivoP9` (control de adjuntos = `attXlsxP9`).
5. Pega los controles y escribe `OnVisible` (`powerapps/INSTRUCCIONES_PEGADO.md`, pasos 4–5).
6. Pega el botón en `Main_Screen` (`BOTON_MAIN_SCREEN.txt`) y revisa el comprobador de aplicaciones.
7. Prueba con `Ejemplo_Confirmacion_Masiva_P9.xlsx` (debe dar COMPLETADO y 3 filas). Si `.Run(...)` marca error, anota qué firma pide Studio.
8. Haz las pruebas de comportamiento y mide con los 7 archivos de `xlsx/medicion/` (3 ejecuciones cada uno) en `MEDICION_TENANT.md`.
9. Verifica que `Documents/P9_MASIVA_TEMP` quedó vacía y anota si hubo `copia_temporal_eliminada = NO`.
10. Con las medidas, decidimos el máximo de filas (si hace falta). Al terminar, elimina lo temporal (`sharepoint/INSTRUCCIONES_VEHICULO.md` §3).

## MAPA DE ARCHIVOS (todo bajo `proto_masiva/`)

`xlsx/{Plantilla,Ejemplo}_Confirmacion_Masiva_P9.xlsx` · `xlsx/medicion/Filas_NNNN.xlsx` · `xlsx/` (6 fixtures de A–E) · `contrato_plantilla.py` · `catalogo_p9.py` + `catalogo_bancos_p9.json` · `generar_plantillas_produccion.py` · `generar_medicion.py` · `generar_xlsx.py` (fixtures) · `PLANTILLA_PRODUCCION.md` · `MEDICION_TENANT.md` · `powerapps/{P9_Confirmacion_Masiva.pa.yaml, …_CONTROLES_PEGAR.yaml, BOTON_MAIN_SCREEN.txt, BOTON_MAIN_SCREEN_PEGAR.yaml, Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml, INSTRUCCIONES_PEGADO.md, aplicar_boton.py, derivar_pegar.py}` · `flows/{construir.py, P9_MASIVA_PROTO_PREVALIDAR_definition.json, P9_MASIVA_PROTO_PREVALIDAR.zip, INSTRUCCIONES_FLUJO.md}` · `sharepoint/INSTRUCCIONES_VEHICULO.md` · `tests/`.
