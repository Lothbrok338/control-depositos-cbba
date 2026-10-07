# P9 · Sincronización de la UI REAL del tenant (checkpoint «sync tenant-validated mass UI»)

Rama `experiment/p9-masiva-prototipo` · base `88aef9570b156a919d74c2ef4c408b78632c21ac`. No se tocó `main`, producción, ni el tenant.

## Fuente de verdad

Export `.msapp` de la app **`P9_PRUEBA_MASIVA`** (`Properties.json`: `AppName = P9_PRUEBA_MASIVA`; guardada y publicada por Gabriel), sha256
`666b7f611ec44c55f4ce096ff7cc5b3dcb23ef4877a6baacec38ad5ea1da0630`. Un `.msapp` es un ZIP: el YAML de las pantallas está en `Src/`. Se copiaron **verbatim**:

| Origen en el `.msapp` | Copia en el repo (verbatim) | Fuente única que consumen generadores y tests |
|---|---|---|
| `Src/P9_Confirmacion_Masiva.pa.yaml` (sha256 `93d97ac2…194d`) | `powerapps/tenant/P9_Confirmacion_Masiva.pa.yaml` | `powerapps/P9_Confirmacion_Masiva.pa.yaml` (idéntico byte a byte en este checkpoint) |
| `Src/Main_Screen.pa.yaml` (sha256 `26f26fef…384b`) | `powerapps/tenant/Main_Screen.pa.yaml` | `powerapps/Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml` (idéntico byte a byte) |

`COMPROBANTE PDF` y `App` del export no se copian: no forman parte de esta fase. El `.msapp` no se versiona (solo su hash).
El export confirma lo que ya se sabía del tenant: la app tiene las fuentes `Depositos_Activos`, `P9_MASIVA_PROTO_ADJUNTO` y los flujos `P9_ASIGNAR_DEPOSITO`, `P9_SOLICITAR_REVERSION`, `P9_MASIVA_PROTO_PREVALIDAR`; **`P9_MASIVA_PROTO_CONFIRMAR` NO está agregado todavía**.

> El YAML de Power Apps usa siempre sintaxis canónica (`,` argumentos, `;` sentencias). Gabriel trabaja en configuración regional `es-ES`
> (`;` argumentos, `;;` sentencias); `generar_powerfx.regional()` hace la conversión para los `.md`.

## Diferencias REALES: tenant vs YAML reconstruido de `88aef95`

`P9_Confirmacion_Masiva`: el tenant tiene **44 controles**; la reconstrucción tenía 35 (y no tenía el formulario). 66 propiedades difieren.

| # | Tema | Reconstruido (88aef95) | TENANT REAL (prevalece) |
|---|---|---|---|
| 1 | Formulario del adjunto | **ausente** (solo en la guía) | `frmArchivoP9` (`DataSource = P9_MASIVA_PROTO_ADJUNTO`, `FormMode.New`, 540×140 en 30,215) → `dcAdjuntosP9` (+`DataCardKey1`, `ErrorMessage1`, `StarVisible1`) → `attXlsxP9` (`MaxAttachments = 1`) |
| 2 | Etiquetas dentro de `galObservacionesP9` | `lblObsTituloP9`, `lblObsMensajeP9` (nombres inventados) | `Title1` (título, **negrita**, tamaño 14), `Subtitle1`, `Separator1`, `Rectangle1`, `Title1_1` (mensaje, tamaño 11, normal). Los nombres reales son los de la plantilla de galería de Studio |
| 3 | Galería `galObservacionesP9` | `Items` = `If(!IsBlank(varResultadoConfirmacionP9), …colConfirmacionP9…, …colPrevalidacionP9…)`, `Visible = Coalesce(varVerObservacionesP9, false)`, `TemplateSize 66`, 240 de alto en 640,245 (ancho `Parent.Width - 680`) | `Items = Filter(colPrevalidacionP9, resultado <> "VALIDO")`, `Visible = varVerObservacionesP9`, `Fill`/`TemplateFill` blancos, `TemplateSize 85`, **706×483 en 620,95** (cubre todo el panel de resultado, con el scroll nativo de la galería) |
| 4 | `btnPrevalidarP9.OnSelect` | `IfError(ClearCollect(...), Notify(...))` (tabla vs booleano) y salida sin booleano | **`IfError(ClearCollect(...);; true, Notify(...);; false)` y `IfError(... ;; true, ... ;; false)` externo**: ramas booleanas, aceptado por Studio |
| 5 | `btnPrevalidarP9.DisplayMode` | incluía `varProcesandoConfirmacionP9` | solo `varProcesandoP9`, sin adjunto o sin `.xlsx` |
| 6 | `OnVisible` de la pantalla | 11 sentencias (variables de confirmación, `Clear(colConfirmacionP9)`) sin `varConfirmarMasivaVisible` | 7 sentencias; **conserva `Set(varConfirmarMasivaVisible, false)`** (obsoleta: segundo modal descartado) y no tiene variables de confirmación |
| 7 | `btnConfirmarMasivamenteP9` | `OnSelect` completo (llama a `P9_MASIVA_PROTO_CONFIRMAR.Run`), verde `RGBA(46,125,50)`, 330×46 en 20,506, tamaño 11 | **`OnSelect = Set(varConfirmarMasivaVisible, true)`** (sin flujo); `Text` con conteo de VALIDO; `DisplayMode` = `!varProcesandoP9 && CountRows(VALIDO) > 0`; vino tinto `RGBA(123,22,50)`, **220×42 en 344,452**, tamaño 10 |
| 8 | `btnVerObservacionesP9` | blanco con borde vino tinto, `DisplayMode` según confirmación, 260×32 en 640,495 | `Visible = CountRows(no VALIDO) > 0`, sin `DisplayMode`, sin borde, vino tinto relleno, **220×42 en 910,467**, tamaño 10 |
| 9 | Ocultar resumen al ver observaciones | `Visible = !Coalesce(varVerObservacionesP9, false)` en las **11** etiquetas del resumen | solo `lblResMensajeP9` lleva `Visible = !varVerObservacionesP9`; el resto queda **cubierto por la galería blanca** (que tapa el panel) |
| 10 | Tiempo | `lblResTiempoP9` en 640,466 tamaño 10 con `Text(Coalesce(varMsConfirmacionP9, varMsAppP9) / 1000, "0.0")`; título «TIEMPO DE PROCESAMIENTO» (Y=442) | `Text(Round(varMsAppP9 / 1000, 1), "0,0") & " segundos"` (coma decimal) en 800,450 tamaño 9, color gris; `lblResTiempoTituloP9` = «Tiempo de Procesamiento» (Y=460) |
| 11 | `lblResMensajeP9` | mensaje del flujo | `Concat(Filter(no VALIDO), "Fila X · TÍTULO: mensaje")` con `Visible = !varVerObservacionesP9` (alto 87) |
| 12 | Estado / titular | incluían ramas de confirmación | `lblEstadoP9` y `lblTitularResultadoP9` solo de prevalidación (`lblTitular` alto 50) |
| 13 | Textos | subtítulo/aviso de la confirmación | `lblSubtituloMasivaP9`: «Prototipo directo · prevalida un archivo Excel. No confirma ningún depósito.» · `lblAvisoPrototipoP9`: «Prevalidación de SOLO LECTURA» |
| 14 | Spinner | `LoadingSpinnerColor = RGBA(123, 22, 50, 1)` | `RGBA(0, 120, 212, 1)` |

`Main_Screen` frente a la **producción** (`p9/reversion/powerapps/Main_Screen.yaml`, intacta): solo difiere por (a) `btnImportacionMasivaP9` (nuevo, último hijo de `cntControlDepositosP9`, `Text = "IMPORTACION MASIVA"` **sin tilde**, 173×32 en 828,27, `Visible = Not(Coalesce(mostrarConfirmacion, false))`, `OnSelect` navega a `P9_Confirmacion_Masiva`); (b) `btnActualizarP9_1.X` 1010 → **1019**; (c) `cmbCuentaP9_1`: `Visible = Not(Coalesce(mostrarConfirmacion, false))` (fix de la superposición con el panel VER/CONFIRMAR) y `DisplayFields`/`SearchFields` = `["Cuenta"]` (producción: `["Label"]`).

## Qué quedó en el checkpoint (sin cambios de diseño)

Todo lo anterior tal como está en el tenant: prevalidación real con el `IfError` booleano, `btnVerObservacionesP9` / `galObservacionesP9` (título y mensaje separados, fondo blanco, scroll de la galería, resumen oculto), tiempo humanizado, navegación `Main_Screen ⇄ P9_Confirmacion_Masiva`, `btnImportacionMasivaP9`, los `Visible` con `mostrarConfirmacion`, `btnConfirmarMasivamenteP9` en su estado ACTUAL y `varConfirmarMasivaVisible` (registrada, obsoleta).
Derivados regenerados desde el export: `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml`, `BOTON_MAIN_SCREEN_PEGAR.yaml` (bloque real del botón), `PREVALIDACION_POWERFX.md`. `aplicar_boton.py` ya no escribe nada (el archivo con botón es el export real).

## Observado en el export y NO tocado (decisión de Gabriel)

- `Subtitle1` (dentro de la galería) muestra `ThisItem.clave_transaccion` y se solapa verticalmente con `Title1_1` (Y 27 vs 28). Como la galería está validada visualmente, no se cambió; si en pantalla se ve doble texto, es el origen.
- `cmbCuentaP9_1` muestra solo el número de cuenta (no «MN · 3000…»): es un ajuste del tenant, no de producción.
- El checker de la app del export solo reporta accesibilidad (`TabIndex`, foco, etiquetas), una variable sin usar y un `CountRows` sobre galería: sin errores de fórmula.
- El tenant no llamaba aún al flujo de confirmación: en el commit del checkpoint (`48d00b5`) `test_08` #36–43 (Power Fx de la confirmación) quedaron en rojo a propósito; se reconcilian en el commit de integración (sección siguiente).

## Fase 2 · Integración de la confirmación sobre la pantalla REAL (commit siguiente al checkpoint)

`P9_MASIVA_PROTO_CONFIRMAR` (flujo y ZIP) **no se modificó**: `P9_MASIVA_PROTO_CONFIRMAR.zip` es idéntico byte a byte al adjunto (sha256 `0f5c1bef…3e2`) y su revisión no encontró ningún error funcional
(GET fresco por fila, ETag fresco, `IF-MATCH` concreto, `MERGE` sin reintentos, `Foreach` secuencial, `CATCH_FILA` que continúa, `Responder_a_PowerApps` siempre se ejecuta).

`powerapps/P9_Confirmacion_Masiva.pa.yaml` = export del tenant + **18 propiedades de fórmula en 13 elementos** (los mismos 44 controles; geometría y estilo idénticos; lo prueba `test_08 #44`):

| Elemento | Propiedad(es) | Cambio |
|---|---|---|
| `btnConfirmarMasivamenteP9` | `OnSelect`, `DisplayMode` | `OnSelect` llama a `P9_MASIVA_PROTO_CONFIRMAR.Run(JSON(solo VALIDO), User().Email)` en UN clic, sin modal; `IfError` con ramas `true`/`false`. `DisplayMode` también bloquea mientras confirma y tras confirmar ese resultado. `Text` no cambia |
| Pantalla | `OnVisible` | se quita `varConfirmarMasivaVisible`; se añade el reinicio de la confirmación |
| `attXlsxP9` | `OnAddFile`, `OnRemoveFile` | reinician resultado, variables y colecciones al cambiar de archivo |
| `btnPrevalidarP9` | `DisplayMode`, `OnSelect` | no prevalida mientras se confirma; prevalidar reinicia la confirmación. El resto es la fórmula REAL del tenant |
| `btnVerObservacionesP9` | `Text`, `Visible` | cuenta las observaciones de la prevalidación o, tras confirmar, las filas NO confirmadas |
| `galObservacionesP9` / `Title1` | `Items` / `Text` | tras confirmar muestra las filas no confirmadas (misma forma de 4 columnas, incl. `clave_transaccion` por `With`+`LookUp`); el título conoce `CONFLICTO`, `CONFLICTO_DATOS`, `ERROR_FILA` en mayúsculas, como el resto |
| `lblEstadoP9` | `Text`, `Fill` | estados `CONFIRMANDO` y `PARCIAL` |
| `lblTitularResultadoP9` | `Text` | resultado de la confirmación en DOS líneas (cabe en el alto 50 del tenant) |
| `lblResMensajeP9` / `lblResTiempoP9` | `Text` | mensaje del flujo / tiempo de la confirmación con el mismo formato «8,9 segundos» |
| `lblSubtituloMasivaP9` / `lblAvisoPrototipoP9` | `Text` | ya no dicen «No confirma ningún depósito» / «SOLO LECTURA» |

Decisiones por prevalecer el tenant: NO se aplica la fórmula «Visible de las 11 etiquetas del resumen» del diseño anterior (el tenant oculta el resumen con la galería blanca y `lblResMensajeP9.Visible`); NO se añade `DisplayMode` a `btnVerObservacionesP9` (el tenant no lo tiene);
se conserva el rótulo «Tiempo de Procesamiento» y el texto `IMPORTACION MASIVA` sin tilde.

### Auditoría de `IfError` (compatibilidad de tipos)

`auditar_iferror.py` comprueba que la última sentencia de cada argumento de cada `IfError` sea `true`/`false`. Resultado: el YAML reconstruido de `88aef95` tenía el patrón rechazado por Studio en **dos** fórmulas
(`btnPrevalidarP9.OnSelect` y `btnConfirmarMasivamenteP9.OnSelect`, 2 de 4 `IfError`); el export del tenant ya tenía corregida la primera; la integración corrige la segunda con la misma forma. Hoy: 4 `IfError`, 0 incompatibles
(tests `test_04` ×3 y `test_08 #45`, mutados para comprobar que fallan si se reintroduce el patrón).
