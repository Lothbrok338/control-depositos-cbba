> **SUPERADO por el prototipo funcional (ver `RESULTADO_PROTOTIPO.md`).** Este documento es el kit de MEDICIÓN de la Fase 0.5 (Response temprano vs. trigger, tiempos).
> El prototipo funcional usa UNA sola arquitectura (estado `PENDIENTE` + disparador + sondeo), sin Response temprano, y **reutiliza el nombre**
> `P9_MASIVA_PROTO_PREVALIDAR` y `P9_MASIVA_PROTO_LOTES` con otro diseño y otras columnas. **No mezcles ambos kits en el mismo tenant**: usa
> `flows/`, `powerapps/` y `sharepoint/`. Las pruebas de tiempos de este runbook siguen siendo opcionales, no hechas.

# P9 MASIVA — Fase 0.5: prototipo de infraestructura (RUNBOOK)

**Estado: NO EJECUTADO.** Este kit lo prepara Claude Code sin acceso al tenant (el conector Microsoft 365 de la sesión está desconectado y solo ofrece búsqueda/lectura). Todo resultado va en `REGISTRO_RESULTADOS.md` y debe medirlo el usuario. Nada de lo marcado «HIPÓTESIS» es un hecho.

Alcance: solo infraestructura. Sin `Depositos_Activos`, sin matching, sin ETag, sin confirmación, sin listas de producción. Plantilla de prueba de **9 columnas** (sin TIPO_CAMBIO, por la actualización de decisiones que prevalece); si prefieres probar con 10, es un cambio de una línea en `generar_xlsx.py`.

Nombres temporales (no reutilizan ninguno de producción):

| Recurso | Nombre |
|---|---|
| Lista | `P9_MASIVA_PROTO_LOTES` |
| Carpeta | `Documents/P9_MASIVA_PROTO` (misma biblioteca que usa P8: `/Documents/P8_PILOTO`) |
| Flujo A+B1 | `P9_MASIVA_PROTO_PREVALIDAR` |
| Flujo B2 | `P9_MASIVA_PROTO_TRIGGER` |
| Flujo lectura | `P9_MASIVA_PROTO_LEER` |
| Pantalla | `P9_MASIVA_PROTO_PANTALLA` (en una app **nueva** de prueba, no en la de producción) |

## 0. Preparación (una vez)

1. Archivos: `python proto_masiva/generar_xlsx.py` → `proto_masiva/xlsx/` (6 ficheros, 0 datos reales).
2. Sitio: el mismo de P9 (`https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`).
3. **Lista** `P9_MASIVA_PROTO_LOTES` → Lista en blanco. Columnas (nombre interno exacto, todas «Texto de una línea» salvo indicación):
   - `Title` = LOTE_UID (déjala opcional)
   - `ESTADO` (texto; valores: CARGADO, PENDIENTE, PROCESANDO, COMPLETADO, ERROR). Texto y no Opción, para no depender de `.Value` en el prototipo.
   - `MENSAJE` (varias líneas, texto sin formato)
   - `T_PENDIENTE_MOD` (texto) · `T_FLUJO_INICIO` (texto) · `T_ARCHIVO_COPIADO` (texto) · `T_EXCEL_LEIDO` (texto) · `T_FIN` (texto) · `T_RESPONSE` (texto)
   - `FILAS_LEIDAS` (número, 0 decimales)
   - Adjuntos: habilitados (por defecto sí).
4. **Carpeta**: Documentos → nueva carpeta `P9_MASIVA_PROTO`.
5. Crea una **app de lienzo nueva** «P9_MASIVA_PROTO» (en blanco, tableta). No toques la app de producción.

Todas las marcas de tiempo de los flujos se guardan como texto con `utcNow('yyyy-MM-ddTHH:mm:ss.fff')` (UTC; Bolivia = UTC−4). Resolución del reloj de SharePoint: segundos (`Modified`).

## PRUEBA A — carga del XLSX

### A.1 Flujo `P9_MASIVA_PROTO_PREVALIDAR` (compartido con la prueba B1)

Disparador: **Power Apps (V2)** con 2 entradas, en este orden: `LOTE_ID` (Número), `ESCENARIO` (Texto: `NINGUNO` | `FALLO_CAPTURADO` | `FALLO_NO_CAPTURADO`). Conserva exactamente 2 entradas, ambas obligatorias.

1. **Obtener elemento** (SharePoint → Get item): sitio, lista `P9_MASIVA_PROTO_LOTES`, Id = `LOTE_ID`.
2. **Redactar** `T_INICIO` = `utcNow('yyyy-MM-ddTHH:mm:ss.fff')`.
3. **Responder a Power Apps** (Respond to a PowerApp or flow) con 3 salidas de texto: `resultado` = `ACEPTADO`, `lote_uid` = `Title` del elemento, `t_response` = `T_INICIO`. **Esta acción va aquí, inmediatamente, antes de cualquier trabajo.**
4. **Actualizar elemento**: `ESTADO` = `PROCESANDO`, `T_FLUJO_INICIO` = `T_INICIO`, `T_RESPONSE` = `T_INICIO`, `MENSAJE` = `Flujo continúa tras Response`.
5. **Retraso** 20 segundos (simula trabajo; permite ver PROCESANDO en la pantalla).
6. **Condición** `ESCENARIO` = `FALLO_NO_CAPTURADO` → Sí: acción **Terminar** (estado **Error**, código `PROTO`, mensaje `fallo deliberado fuera de TRY`). Sin rama No.
7. **Ámbito `TRY`**:
   1. **Obtener datos adjuntos** (Get attachments): sitio, lista, Id = `LOTE_ID`.
   2. **Obtener contenido de datos adjuntos** (Get attachment content): Id = `LOTE_ID`, File Identifier = `Id` del primer adjunto (`first(body('Obtener_datos_adjuntos'))?['Id']`).
   3. **Crear archivo** (SharePoint → Create file): carpeta `/Documents/P9_MASIVA_PROTO`, nombre `@{Title}.xlsx`, contenido = contenido del adjunto.
   4. **Redactar** `T_COPIADO` = `utcNow(...)` → **Actualizar elemento** `T_ARCHIVO_COPIADO`.
   5. **Retraso** de `N` segundos (ver «Matriz de ejecuciones»: 0, 5, 10).
   6. **Condición** `ESCENARIO` = `FALLO_CAPTURADO` → Sí: acción **Redactar** con `@{div(1,0)}` (falla dentro del TRY). Sin rama No.
   7. **Excel Online (Business) → Enumerar filas presentes en una tabla** (List rows present in a table): Ubicación = sitio, Biblioteca = Documentos, Archivo = *Id del archivo creado* (del paso 3), Tabla = `tblConfirmacionMasiva`.
      - En **Configuración** de esta acción: **Directiva de reintentos = Ninguno** en las ejecuciones 1–3; **Intervalo fijo, 4 reintentos, PT5S** en las 4–6. Paginación desactivada.
   8. **Redactar** `T_LEIDO` = `utcNow(...)`.
   9. **Actualizar elemento**: `ESTADO` = `COMPLETADO`, `T_EXCEL_LEIDO` = `T_LEIDO`, `T_FIN` = `T_LEIDO`, `FILAS_LEIDAS` = `length(body('Enumerar_filas…')?['value'])`, `MENSAJE` = `Leídas @{…} filas; primera clave: @{first(body(...)?['value'])?['CODIGO_ASIGNACION']}`.
8. **Ámbito `CATCH`** (Configurar ejecución posterior de `TRY`: *ha fallado*, *se ha agotado el tiempo de espera*): **Actualizar elemento** `ESTADO` = `ERROR`, `T_FIN` = `utcNow(...)`, `MENSAJE` = `@{result('TRY')}` (o `@{actions('Enumerar_filas…')?['error']?['message']}`, para guardar el texto real del error).

Guarda y prueba el flujo una vez de forma manual. Anota la **URL del flujo** de la pestaña «Detalles».

### A.2 Pantalla de prueba (app nueva)

Origen de datos: `P9_MASIVA_PROTO_LOTES` (SharePoint) y el flujo `P9_MASIVA_PROTO_PREVALIDAR` (Power Apps → pestaña Power Automate → Agregar flujo).

1. Inserta **Formulario de edición** `frmLote`: `DataSource = P9_MASIVA_PROTO_LOTES`, `Item = Blank()` y `DefaultMode = FormMode.New`. Deja solo las tarjetas **Title**, **ESTADO** y **Datos adjuntos**.
   - `Title` → `DefaultSelectedItems`/`Default` = `GUID()` (texto). `ESTADO` → `Default` = `"CARGADO"`.
   - En la tarjeta de datos adjuntos activa la propiedad que limita a 1 archivo (`MaxAttachments = 1`) y `MaxAttachmentSize = 5` (MB).
2. Botón `btnCrear` → `OnSelect`: `Set(varT0, Now()); SubmitForm(frmLote)`.
3. `frmLote.OnSuccess`: `Set(varLote, frmLote.LastSubmit); Set(varTCreado, Now()); Notify("Lote creado: " & varLote.ID & " en " & DateDiff(varT0, varTCreado, TimeUnit.Milliseconds) & " ms")`.
4. Botón `btnB1` → `OnSelect`:
   ```
   Set(varTB1a, Now());
   Set(varResp, P9_MASIVA_PROTO_PREVALIDAR.Run(varLote.ID, drpEscenario.Selected.Value));
   Set(varTB1b, Now());
   Set(varMsB1, DateDiff(varTB1a, varTB1b, TimeUnit.Milliseconds));
   Set(varSondeo, true); Set(varTicks, 0)
   ```
   `drpEscenario` = lista desplegable con `["NINGUNO","FALLO_CAPTURADO","FALLO_NO_CAPTURADO"]`.
5. Etiquetas: `Text(varMsB1) & " ms · resultado: " & varResp.resultado`.

### A.3 Matriz de ejecuciones de la Prueba A

Sube cada vez el archivo indicado con el control de adjuntos (el nombre de adjunto da igual).

| Nº | Archivo | Retry del Excel | Delay antes de Excel | Para qué |
|---|---|---|---|---|
| A1 | `01_OK_3filas.xlsx` | Ninguno | 0 s | ¿Excel lee la tabla justo tras crear el archivo? |
| A2 | `01_OK_3filas.xlsx` | Ninguno | 0 s | Repetir (la primera vez puede ser distinta) |
| A3 | `01_OK_3filas.xlsx` | Ninguno | 0 s | Tercera repetición |
| A4 | `01_OK_3filas.xlsx` | 4 × PT5S | 0 s | ¿Basta el retry? |
| A5 | `01_OK_3filas.xlsx` | Ninguno | 5 s | ¿Basta un Delay corto? |
| A6 | `01_OK_3filas.xlsx` | Ninguno | 10 s | Delay largo |

Con A1–A6 se responde: tiempo hasta archivo disponible (`T_ARCHIVO_COPIADO` − `Created` del lote), tiempo hasta lectura (`T_EXCEL_LEIDO` − `T_ARCHIVO_COPIADO`), y si hace falta Delay o retry. Anota además si `Get attachments` encontró el adjunto en cuanto `OnSuccess` lanzó el flujo (si falla: **el adjunto tardó más que el SubmitForm**, apúntalo; no lo des por hecho).

### A.4 Flujo `P9_MASIVA_PROTO_LEER` (casos de archivo, tabla, encabezado, vacío)

Disparador **Activar manualmente un flujo** con 1 entrada de texto `RUTA` (ej. `/P9_MASIVA_PROTO/02a_TABLA_VACIA_1fila_en_blanco.xlsx`).

1. **Enumerar filas presentes en una tabla**: Archivo = `RUTA`, Tabla = `tblConfirmacionMasiva`, retry = Ninguno.
2. **Redactar**: `length(body('Enumerar_filas…')?['value'])` y `string(first(body('Enumerar_filas…')?['value']))` para ver las claves reales (así se ve qué hace el conector con un encabezado cambiado).
3. En la vista de ejecución anota: estado, código HTTP y **mensaje exacto del error**.

Sube a mano los 5 archivos restantes a `Documents/P9_MASIVA_PROTO` y lanza `LEER` con cada ruta:

| Nº | Archivo | Caso |
|---|---|---|
| H | `03_SIN_TABLA.xlsx` y `04_TABLA_NOMBRE_DISTINTO.xlsx` | falta `tblConfirmacionMasiva` |
| I | `05_ENCABEZADO_CAMBIADO.xlsx` | `CUENTA_BANCARIA` → `CUENTA` |
| J | `02a_…` y `02b_…` | tabla vacía (con 1 fila en blanco / solo encabezado) |
| G | `01_OK_3filas.xlsx` **abierto** | ver abajo |

**Caso G (archivo abierto)**, tres ejecuciones de `LEER` sobre `01_OK_3filas.xlsx`:
1. Abierto en **Excel Online** (navegador, tu usuario).
2. Abierto en **Excel de escritorio** (tu usuario).
3. Abierto en Excel Online por **otro usuario** (si puedes pedir ayuda a alguien).
Anota resultado, mensaje de error y tiempo de cada una, y si al cerrarlo el flujo vuelve a funcionar.

## PRUEBA B — asincronía

### B1. Response temprano (ya incluido en `P9_MASIVA_PROTO_PREVALIDAR`)

La respuesta se envía en el paso 3, antes del trabajo. Se miden:

| Dato | Cómo |
|---|---|
| Tiempo de respuesta a Power Apps | `varMsB1` (milisegundos medidos por la propia app) |
| ¿Continuó el flujo tras responder? | En la lista: `ESTADO` pasa a `PROCESANDO` y luego a `COMPLETADO` mientras la app ya mostró ACEPTADO; en el historial de ejecuciones, la ejecución dura ≥ 20 s |
| ¿Actualiza el lote? | Valores finales de `ESTADO`, `T_FIN`, `FILAS_LEIDAS` |
| Fallo posterior capturado | Escenario `FALLO_CAPTURADO` → debe terminar en `ERROR` con `MENSAJE` |
| Fallo posterior no capturado | Escenario `FALLO_NO_CAPTURADO` → mira si el lote queda en `PROCESANDO` para siempre (⇒ haría falta un vigilante) y cómo se ve la ejecución |
| Cierre de la app durante el proceso | Lanza B1 con `NINGUNO` y **cierra la app** a los 5 s: ¿llega el lote a `COMPLETADO`? |

Repite B1 **5 veces** (con `NINGUNO`) para tener una distribución, no un valor.

### B2. Alternativa por estado

Flujo `P9_MASIVA_PROTO_TRIGGER`:

1. Disparador SharePoint **Cuando se crea o modifica un elemento** (lista `P9_MASIVA_PROTO_LOTES`). En **Configuración → Condiciones del desencadenador**: `@equals(triggerOutputs()?['body/ESTADO'],'PENDIENTE')`. Eso evita que sus propias actualizaciones lo re-disparen.
2. **Redactar** `T_INI` = `utcNow('yyyy-MM-ddTHH:mm:ss.fff')`.
3. **Actualizar elemento**: `ESTADO` = `PROCESANDO`, `T_FLUJO_INICIO` = `T_INI`, `T_PENDIENTE_MOD` = `triggerOutputs()?['body/Modified']`.
4. **Retraso** 20 s.
5. **Actualizar elemento**: `ESTADO` = `COMPLETADO`, `T_FIN` = `utcNow(...)`, `MENSAJE` = `B2 completado`.

Latencia del trigger = `T_FLUJO_INICIO` − `T_PENDIENTE_MOD` (resolución de 1 s; úsala como orden de magnitud). Botón en la app: `btnB2` → `Patch(P9_MASIVA_PROTO_LOTES, varLote, {ESTADO: "PENDIENTE"}); Set(varSondeo, true); Set(varTicks, 0)`. Para B2 crea un lote nuevo con `btnCrear` y no hace falta que tenga adjunto. **Repite 5 veces.** Anota también la latencia con el flujo sin usar durante >1 h (trigger «frío»), si te es posible.

### Sondeo desde Power Apps

- Temporizador `tmrSondeo`: `Duration = Coalesce(varIntervaloMs, 3000)`, `Repeats = true`, `AutoStart = false`, `Start = Coalesce(varSondeo, false)`.
- `OnTimerEnd`:
  ```
  Set(varTicks, Coalesce(varTicks, 0) + 1);
  Refresh(P9_MASIVA_PROTO_LOTES);
  Set(varLoteVivo, LookUp(P9_MASIVA_PROTO_LOTES, ID = varLote.ID));
  If(varLoteVivo.ESTADO = "COMPLETADO" || varLoteVivo.ESTADO = "ERROR",
     Set(varSondeo, false); Set(varTVisto, Now()))
  ```
- Etiquetas: `LOTE_UID` (`varLoteVivo.Title`), `ESTADO`, `MENSAJE`, `Text(varLoteVivo.Modified, "dd/mm/yyyy hh:nn:ss")`, `varTicks`.
- Retraso de la pantalla = `varTVisto` − hora real de `T_FIN` (acuérdate de que `T_FIN` está en UTC y `Now()` en hora local: Bolivia = UTC−4).
- Prueba intervalos `varIntervaloMs` = **2000, 3000, 5000, 10000** (2 lotes por valor). Para cada uno anota: segundos entre el cambio real y el que ve la pantalla, número de `Refresh`, y si la pantalla se queda congelada o parpadea.

## Antes de dar nada por válido

- Anota fecha/hora, usuario, licencia del flujo y la versión del conector si el entorno la muestra.
- Si algo falla por permisos o licencia (p. ej. el conector Excel pide Premium), escríbelo como **LIMITACIÓN** en el registro; no lo cuentes como un fallo del patrón.
- Cuando acabes, aplica la limpieza de la sección final de `REGISTRO_RESULTADOS.md`.
