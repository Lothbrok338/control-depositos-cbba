# P9 CONFIRMACIÓN MASIVA — Prototipo funcional (datos ficticios)

> ## ESTADO DE VALIDACIÓN (leer primero)
>
> - **82/82 pruebas son sintéticas/locales**: usan un tenant simulado dentro de este repositorio, no Power Automate, SharePoint ni Excel Online reales.
> - **NO hay validación real en tenant.** Nada de lo descrito aquí se ha ejecutado todavía en Microsoft 365.
> - **Nombres internos de algunas operaciones de Power Automate siguen por validar** (`GetOnUpdatedItems`, `GetAttachments`, `GetAttachmentContent`, `CreateFile`, Excel `GetItems`): se escribieron de memoria, sin poder consultar la documentación de Microsoft.
> - **La latencia del disparador de SharePoint sigue por medir.**
> - **El control de adjuntos y el temporizador requieren validación manual en Studio** (se crean a mano; el formulario, `OnSuccess` y `Launch(...?download=1)` tampoco están probados).
> - **No se ha tocado `Depositos_Activos`** ni ningún artefacto de producción: el prototipo no lo consulta ni lo modifica, y todos los cambios están bajo `proto_masiva/`.

Rama `experiment/p9-masiva-prototipo`, partiendo de `941dac9` (checkpoint de producción `3b407e2` intacto). **Nada de esto se ha probado todavía en tu tenant.** Etiquetas: **[VALIDADO LOCALMENTE]** = probado con un tenant simulado en este repositorio; **[REQUIERE VALIDACIÓN TENANT]** = solo se sabrá al ejecutarlo en Microsoft 365.

## QUÉ FUNCIONA

```
Main_Screen ──[IMPORTACIÓN MASIVA]──► P9_Confirmacion_Masiva
   DESCARGAR PLANTILLA · ADJUNTAR EXCEL · PREVALIDAR ARCHIVO
        │ crea el lote en P9_MASIVA_PROTO_LOTES (con el XLSX adjunto) → ESTADO = PENDIENTE
        ▼
   flujo P9_MASIVA_PROTO_PREVALIDAR (se dispara solo con ESTADO = PENDIENTE)
        PROCESANDO → copia el XLSX a Documents/P9_MASIVA_PROTO → lee tblConfirmacionMasiva → cuenta filas
        → COMPLETADO | ERROR (con código y mensaje)
        ▲
   la pantalla consulta el lote cada 5 s y muestra:
        ARCHIVO RECIBIDO · TABLA ENCONTRADA · 3 FILAS LEÍDAS
```

Una sola arquitectura: estado en la lista + disparador + sondeo. **No usa «Respuesta temprana»** (nunca se probó que el flujo siga después de responder). **No consulta ni modifica `Depositos_Activos`**, ni usa ETag, ni confirma nada.

Existen de verdad (en este repo): la plantilla Excel, la pantalla, el botón, el flujo (JSON + ZIP importable), el esquema de la lista, las instrucciones y 82 pruebas.

## QUÉ SE PROBÓ

82 pruebas, todas pasan (`python -m pytest proto_masiva/tests -q -p no:cacheprovider`):

| Archivo de pruebas | Cubre | Pruebas |
|---|---|---|
| `test_01_plantillas.py` | 9 columnas exactas, una tabla `tblConfirmacionMasiva`, sin TIPO_CAMBIO, Texto/2 decimales/BOB-USD, 3 filas y vacía, **cero cuentas reales**, bytes deterministas | 21 |
| `test_02_flujo_definicion.py` | estructura del flujo y del ZIP, cadena de acciones sin pasos en paralelo, referencias válidas, solo escribe en el lote, `IF-MATCH: *` únicamente en la lista de estado, nunca reescribe `PENDIENTE` | 12 |
| `test_03_escenarios_sinteticos.py` | escenarios A–E y los casos anómalos (abajo) con un tenant simulado | 32 |
| `test_04_powerapps.py` | YAML válido, 30 controles únicos, referencias resolubles, fórmulas balanceadas, botón = original + 1 bloque | 17 |

Además, durante el trabajo las pruebas detectaron **un defecto real de mi primer borrador** (`Etapa_excel` corría en paralelo con la copia) y quedó corregido y protegido con una prueba estructural. Reintroduje a propósito 4 defectos (reescribir `PENDIENTE`, escribir en otra lista, no validar encabezados, contar filas en blanco): las pruebas los detectan.

El simulador usa el intérprete WDL del repo (P8, solo lectura) más conectores falsos. **No es Power Automate**: no valida nombres de operación, tiempos ni códigos HTTP reales.

## RESULTADO DE CADA PRUEBA

| # | Archivo (en `xlsx/`) | Resultado esperado y obtenido en simulación | Estado |
|---|---|---|---|
| A | `Plantilla_Confirmacion_Masiva_P9.xlsx` (3 filas) | `COMPLETADO · OK · FILAS_LEIDAS = 3 · Tabla = SI` · «Archivo leído correctamente» | [VALIDADO LOCALMENTE] · [REQUIERE VALIDACIÓN TENANT] |
| A′ | `01_OK_3filas.xlsx` | idéntico a A | ídem |
| B | `Plantilla_…_VACIA.xlsx`, `02a_…`, `02b_…` | `ERROR · ARCHIVO_VACIO · Tabla = SI · 0 filas`. **Decisión:** una importación sin filas no se marca COMPLETADO (no hay nada que confirmar). Resultado controlado: el flujo no falla | ídem |
| C | `03_SIN_TABLA.xlsx` | `ERROR · TABLA_NO_ENCONTRADA · Tabla = NO` | ídem. **Supuesto:** el conector Excel responde 404 |
| D | `05_ENCABEZADO_CAMBIADO.xlsx` | `ERROR · ESTRUCTURA_INVALIDA` · «Faltan o cambiaron encabezados: CUENTA_BANCARIA…» | ídem |
| E | `04_TABLA_NOMBRE_DISTINTO.xlsx` | `ERROR · TABLA_NO_ENCONTRADA` | ídem. Mismo supuesto 404 |

Otros casos simulados (todos terminan en estado final controlado): lote sin adjunto (`SIN_ADJUNTO`), adjunto que no es `.xlsx` (`NO_ES_XLSX`), XLSX corrupto (`ERROR_LECTURA_EXCEL`, no se confunde con tabla ausente), archivo bloqueado 423 (`ARCHIVO_BLOQUEADO`), fallos de adjuntos/copia/Excel (`ERROR_ADJUNTO`, `ERROR_COPIA_ARCHIVO`, `ERROR_LECTURA_EXCEL`), reintento tras ERROR, un lote que no está en `PENDIENTE` nunca dispara, el flujo nunca se redispara con sus propias escrituras, y si falla la **última** escritura el flujo falla de forma visible y el lote queda en `PROCESANDO` (riesgo conocido, abajo).

## QUÉ NECESITO HACER YO EN POWER APPS

Detalle en `powerapps/INSTRUCCIONES_PEGADO.md`. Resumen: en una **copia** de la app, agregar la lista como origen de datos; crear la pantalla `P9_Confirmacion_Masiva`; **tres controles se crean a mano** porque no hay forma fiable de pegarlos en YAML: el formulario `frmLoteP9` (solo con «Datos adjuntos», control renombrado `attXlsxP9`), y el temporizador `tmrSondeoP9`; pegar `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml`; escribir a mano `OnVisible`/`OnHidden`; y añadir **un botón** a `Main_Screen` (`powerapps/BOTON_MAIN_SCREEN.txt`, bloque en `BOTON_MAIN_SCREEN_PEGAR.yaml`). El botón es el único control nuevo de `Main_Screen`: 79 → 80 controles, ningún otro cambia; `Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml` es el original + ese bloque (prueba: quitando el bloque queda byte a byte igual).

## QUÉ NECESITO IMPORTAR/CREAR EN POWER AUTOMATE Y SHAREPOINT

1. **Lista** `P9_MASIVA_PROTO_LOTES` (9 columnas) y carpeta `Documents/P9_MASIVA_PROTO` con la plantilla: `sharepoint/INSTRUCCIONES_LISTA.md`.
2. **Importar** `flows/P9_MASIVA_PROTO_PREVALIDAR.zip` (Importar paquete heredado) con conexiones SharePoint y **Excel Online (Business)**, y **revisar 5 puntos** (`flows/INSTRUCCIONES_FLUJO.md`): disparador, adjuntos, contenido, crear archivo y lectura de Excel (ubicación/biblioteca de Excel hay que elegirlas: no puedo conocerlas).

## QUÉ SIGUE SIN ESTAR VALIDADO EN TENANT

- **Nombres internos de 5 operaciones/parámetros** (`GetOnUpdatedItems`, `GetAttachments`, `GetAttachmentContent`, `CreateFile`, Excel `GetItems`): los escribí de memoria; `learn.microsoft.com` está bloqueado desde este entorno. Son lo más probable que pida un reajuste en el diseñador (2 minutos por acción). Lo que ya está validado en tu tenant por flujos anteriores: `HttpRequest` a SharePoint, `GetOnNewItems`, `GetFileContent`.
- **Latencia del disparador de SharePoint**: no medida. Es la parte lenta del diseño (el sondeo de la app es 5 s, pero el flujo puede tardar ~1 min en arrancar). Si resulta inaceptable, hay que cambiar de patrón.
- **Que `OnSuccess` del formulario corra después de subir el adjunto** (de lo que depende no tener que esperar adjuntos en el flujo; si no, el flujo responde `SIN_ADJUNTO` y se reintenta con PREVALIDAR).
- **Comportamiento real del conector Excel**: código HTTP con tabla ausente (supuesto 404; si es 400, ver `INSTRUCCIONES_FLUJO.md`), tabla vacía, encabezado cambiado, archivo abierto, tiempo hasta poder leer un archivo recién creado (la simulación no lo reproduce; no se agregó Delay ni reintento por no tener evidencia de que haga falta).
- **Control de adjuntos, temporizador y `Launch(...?download=1)`** en tu Studio; permisos de los usuarios sobre la carpeta y la lista.
- Todo lo anterior son hipótesis hasta que lo ejecutes.

**Riesgos conocidos (no resueltos en el prototipo):** si SharePoint rechaza la escritura final, el lote queda en `PROCESANDO` y la app dejará de sondear a los 6 min (botón ACTUALIZAR ESTADO; falta un vigilante); `IF-MATCH: *` se usa solo en la lista de estado del prototipo, de un único escritor — **no** se hereda a `Depositos_Activos`.

## PASOS PARA GABRIEL

1. Crea la lista `P9_MASIVA_PROTO_LOTES` y la carpeta `P9_MASIVA_PROTO` con la plantilla (`sharepoint/INSTRUCCIONES_LISTA.md`, ~10 min).
2. Sube también a esa carpeta los archivos de prueba que quieras usar (están en `xlsx/`).
3. Power Automate: importa `flows/P9_MASIVA_PROTO_PREVALIDAR.zip`, mapea SharePoint y Excel Online (Business).
4. Abre el flujo y revisa los 5 puntos de `flows/INSTRUCCIONES_FLUJO.md`; guarda y deja el flujo **Activado**.
5. Power Apps: guarda una **copia** de la app P9 y agrega la lista como origen de datos.
6. Crea la pantalla `P9_Confirmacion_Masiva`, el formulario `frmLoteP9` (renombra el control de adjuntos `attXlsxP9`) y el temporizador `tmrSondeoP9` (`powerapps/INSTRUCCIONES_PEGADO.md`, pasos 2–4).
7. Pega `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml` sobre la pantalla y escribe `OnVisible`/`OnHidden` (pasos 5–6).
8. En `Main_Screen`, pega el botón (`BOTON_MAIN_SCREEN.txt`, opción A) y comprueba que no hay errores nuevos en el comprobador.
9. Prueba con los 5 archivos de la tabla A–E (F5 desde `Main_Screen` → IMPORTACIÓN MASIVA) y anota, para cada uno, el **estado final, el código y el tiempo** desde PREVALIDAR hasta COMPLETADO/ERROR. Si algún resultado difiere de lo esperado, copia el `MENSAJE` del lote: lleva el código HTTP real.
10. Cuando termines, elimina todo lo temporal (`sharepoint/INSTRUCCIONES_LISTA.md` §5 y `flows/INSTRUCCIONES_FLUJO.md`, última sección) y pásame los resultados.

## DECISIONES TOMADAS (por simplicidad)

Estado `ESTADO` como texto (no Opción); tabla vacía = `ERROR/ARCHIVO_VACIO`; filas totalmente en blanco no cuentan; 5 s de sondeo con tope de 6 min; copia temporal con nombre `LOTE_UID_aaaaMMddHHmmss.xlsx` (nunca choca al reintentar); sin autocompletar nada; sin `TIPO_CAMBIO` en plantilla, flujo ni pantalla; paginación de Excel a 2000 filas.

## MAPA DE ARCHIVOS (todo bajo `proto_masiva/`)

`xlsx/Plantilla_Confirmacion_Masiva_P9(.VACIA).xlsx` (+6 fixtures de A–E) · `generar_plantillas.py` · `powerapps/{P9_Confirmacion_Masiva.pa.yaml, …_CONTROLES_PEGAR.yaml, BOTON_MAIN_SCREEN.txt, BOTON_MAIN_SCREEN_PEGAR.yaml, Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml, INSTRUCCIONES_PEGADO.md, aplicar_boton.py, derivar_pegar.py}` · `flows/{construir.py, P9_MASIVA_PROTO_PREVALIDAR_definition.json, P9_MASIVA_PROTO_PREVALIDAR.zip, INSTRUCCIONES_FLUJO.md}` · `sharepoint/{esquema_P9_MASIVA_PROTO_LOTES.json, INSTRUCCIONES_LISTA.md}` · `tests/` · `RUNBOOK.md` y `REGISTRO_RESULTADOS.md` (kit anterior de medición, marcado como superado).
