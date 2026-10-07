# Instalar y probar la CONFIRMACIÓN MASIVA en tu tenant — pasos exactos

> ## ⚠ Esta prueba ESCRIBE en `Depositos_Activos` REAL
> `P9_MASIVA_PROTO_CONFIRMAR` cambia depósitos a `ASIGNADO` (como la confirmación individual). **No hay rollback automático** y no se revierte lo ya confirmado.
> Haz las pruebas **solo con depósitos que de todos modos ibas a confirmar** (con su estudiante, solicitante y sede reales), o acuerda antes cómo se revertirán
> (la reversión vigente es por solicitud y aprobación). Empieza con **1 sola fila**.
>
> **No está validado en el tenant.** Trabaja en la copia `P9_PRUEBA_MASIVA`; no publiques sobre producción y no toques otros flujos. Todo esto lo haces tú a mano, acompañado: no se importó ni publicó nada desde el repositorio.

Archivos (rama `experiment/p9-masiva-prototipo`, carpeta `proto_masiva/`):

| Archivo | Para qué |
|---|---|
| `flows/P9_MASIVA_PROTO_CONFIRMAR.zip` | el flujo nuevo (opción A) |
| `flows/GUIA_ACCIONES_CONFIRMACION.md` | las mismas acciones, una por una, por si el ZIP no se pudiera importar (opción B) |
| `powerapps/CONFIRMACION_POWERFX.md` | las fórmulas A–Q de Power Apps (sobre tus controles reales), en tu sintaxis (`;` y `;;`) |
| `CONFIRMACION_MASIVA.md` | reglas, contratos, análisis de escala y lo no validado |

## PARTE 1 · Power Automate: importar el flujo NUEVO

El flujo es **nuevo** (no actualiza ninguno existente), así que no hace falta respaldar nada.

1. `make.powerautomate.com` → **Mis flujos** → **Importar** → **Importar paquete (heredado)** → **Cargar** → `P9_MASIVA_PROTO_CONFIRMAR.zip`.
2. En *Contenido del paquete*, fila **P9_MASIVA_PROTO_CONFIRMAR** (tipo *Flujo*) → **Acción de importación** → **Crear como nuevo**.
3. En la **única conexión** que pide (**SharePoint**) → **Seleccionar durante la importación** → elige **tu conexión existente de SharePoint** (la misma de `P9_ASIGNAR_DEPOSITO`) → **Guardar**.
4. **Importar** → espera «El paquete se importó correctamente».
5. **Mis flujos** → `P9_MASIVA_PROTO_CONFIRMAR` → **Editar**.

### Revisar 5 puntos antes de guardar (abre cada acción con un clic en su cabecera)

| # | Acción | Debe quedar así |
|---|---|---|
| 1 | Disparador **Power Apps (V2)** | **dos** entradas de tipo Texto, en este orden: `detalle_json` y `usuario_email` |
| 2 | `PARAM_MAX_FILAS_POR_LLAMADA` (Redactar, arriba) | **50**. Es el tope por llamada: se sube después de medir (ver Parte 3) |
| 3 | `Para_cada_fila` (dentro de `TRY` → … → `Lote_valido` → rama Sí) | ⋯ → **Configuración** → *Control de simultaneidad* **Activado** con *Grado de paralelismo* = **1** |
| 4 | `Leer_deposito` (dentro de `TRY_FILA`) | Dirección del sitio `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` · Método `GET` · ⋯ → Configuración → *Directiva de reintentos*: **Intervalo fijo, 2 reintentos, PT5S** (5 s es el mínimo que acepta Power Automate) |
| 5 | `Actualizar_deposito` (dentro de `TRY_FILA` → `Puede_confirmar` rama Sí) | Método `POST` · Encabezados `X-HTTP-Method: MERGE` e `IF-MATCH` = el ETag fresco (`@outputs('Revalidacion')?['etag']`) · ⋯ → Configuración → *Directiva de reintentos*: **Ninguna**. **No pongas nunca `*` en `IF-MATCH`.** |

Si una acción muestra ⚠ o campos vacíos, **vuelve a elegir la conexión de SharePoint** en esa acción; no cambies ninguna expresión.

6. **Guardar** («Su flujo está listo»). Si el *Comprobador de flujos* marca errores, **no sigas**: copia el texto exacto y pásamelo.
7. Comprueba que el flujo esté **Activado**.

**Opción B (solo si la importación fallara):** arma el flujo con `flows/GUIA_ACCIONES_CONFIRMACION.md`, que lista cada acción con su nombre, tipo y expresión.

## PARTE 2 · Power Apps (`P9_PRUEBA_MASIVA`, la COPIA)

La pantalla `P9_Confirmacion_Masiva` **ya existe en tu app con todos los controles** (`btnConfirmarMasivamenteP9`, `btnVerObservacionesP9`, `galObservacionesP9`…). El repositorio ya se
sincronizó con el **export real** de esa app (`powerapps/tenant/`, ver `SYNC_TENANT_UI.md`). **No pegues controles ni YAML**: solo se reemplazan **18 propiedades** (fórmulas) en 13 elementos.
Nada cambia de posición, tamaño ni estilo.

1. `make.powerapps.com` → **Aplicaciones** → `P9_PRUEBA_MASIVA` → **Editar**.
2. **Agregar el flujo nuevo:** panel izquierdo → **Power Automate** (icono ⚡) → **Agregar flujo** → `P9_MASIVA_PROTO_CONFIRMAR`.
3. **Pegar las fórmulas** de `powerapps/CONFIRMACION_POWERFX.md`, **de la A a la Q, en ese orden** (la **A primero**: define las variables y `colConfirmacionP9` que usan las demás): selecciona el control → elige
   la propiedad en la barra de fórmulas → **borra todo** → pega.
   - Los nombres del documento son los **reales de tu app** (p. ej. `Title1` es la etiqueta del título dentro de `galObservacionesP9`). Si alguno no existe, para y avísame; no lo recrees.
   - **D** va en `attXlsxP9` (dentro de `frmArchivoP9` → `dcAdjuntosP9`): propiedades **OnAddFile** y **OnRemoveFile**, la misma fórmula en las dos.
   - **C** quita `Set(varConfirmarMasivaVisible; false)` del `OnVisible` (el segundo modal está descartado).
   - **No cambian:** `Text` de `btnConfirmarMasivamenteP9`, `OnSelect` de `btnVerObservacionesP9`, `Title1_1`, `lblResMensajeP9.Visible`, `lblResTiempoTituloP9`, `Main_Screen` (lista completa al final de `CONFIRMACION_POWERFX.md`).
   - Todas las ramas de cada `IfError` terminan en `true`/`false` (la misma forma que Studio ya aceptó en la prevalidación): **no cambies eso a mano**.
4. **Comprobador de aplicaciones** (icono del estetoscopio): sin errores. Si marca error en:
   - `P9_MASIVA_PROTO_CONFIRMAR.Run(…)`: comprueba que IntelliSense pida **dos argumentos de texto** (`detalle_json`, `usuario_email`); si pide otra forma, avísame y se ajusta **solo esa línea**.
   - `ThisRecord.Value`: prueba `ThisRecord.<campo>` solo en esa línea y avísame qué firma aceptó.
   - `ShowColumns`/`JSON`/`OnAddFile`/`With` dentro de `ForAll`: copia el texto exacto del error.
5. Mira que el titular de dos líneas («CONFIRMACIÓN COMPLETADA / 1 de 1 depósitos confirmados.») quepa en `lblTitularResultadoP9`; si se corta, sube su alto (único ajuste visual posible).
6. **Guardar**. **No publiques sobre producción.** Reproduce con F5 desde la pantalla `P9_Confirmacion_Masiva`.

## PARTE 3 · Pruebas en el tenant (en este orden; no avances si una falla)

Prepara un Excel con filas **reales** de depósitos `DISPONIBLE` (los mismos que ya sabes que vas a confirmar). Pulsa **PREVALIDAR ARCHIVO** y comprueba que salen `VALIDO`.

| # | Prueba | Esperado |
|---|---|---|
| **T1** | **1 fila** → CONFIRMAR MASIVAMENTE (1) | «CONFIRMACIÓN COMPLETADA · 1 de 1 depósitos confirmados». El botón queda **Disabled**. En la lista (o en la galería de la app individual) el depósito está `ASIGNADO` con: `ESTUDIANTE`, `SOLICITADO_POR`, `SEDE_ASIGNACION`, `OBSERVACION` (vacía = vacía, no «null»), `USUARIO_ASIGNACION` = tu correo, `FECHA_HORA_ASIGNACION`, `CODIGO_ESTUDIANTE` vacío. **Compáralo con otro depósito confirmado con la app individual: deben tener la misma forma.** |
| **T2** | Con el mismo Excel, **PREVALIDAR de nuevo** | ese depósito sale `NO_DISPONIBLE` («ASIGNADO»); el botón queda en `(0)` y Disabled. Nada se duplica. |
| **T3** | **3 filas.** Después de PREVALIDAR y **antes** de CONFIRMAR, confirma la fila 2 con la **app individual** (otra pestaña) | resultado «CONFIRMACIÓN PARCIAL · 2 de 3»: la fila 2 `NO_DISPONIBLE`, las otras `CONFIRMADO`. «VER OBSERVACIONES (1)» muestra solo la no confirmada. |
| **T4** | **Doble clic rápido** en CONFIRMAR | el botón se bloquea tras el primer clic; en el *Historial de ejecuciones* hay **una sola** ejecución. |
| **T5** | **10 filas** | todas `CONFIRMADO`. Anota «TIEMPO DE PROCESAMIENTO» y, en el historial del flujo, la duración total y por fila. |
| **T6** | **50 filas** | si termina antes del timeout: `CONFIRMADO` en todas. **Si la app muestra «El flujo no respondió…»:** el flujo sigue ejecutándose (mira el historial); cuando termine, **PREVALIDAR de nuevo**: lo ya confirmado sale `NO_DISPONIBLE`, lo pendiente sigue `VALIDO`. No reintentes el clic sin PREVALIDAR. |
| T7 | **Archivo > máximo por llamada** (p. ej. con `PARAM_MAX_FILAS_POR_LLAMADA` = 50, envía 51 `VALIDO`) | «LOTE_EXCEDE_LIMITE… no se confirmó ningún depósito». Nada cambia en la lista. |

**Qué copiarme después de cada prueba:** el resultado en pantalla, el JSON de `tiempos_ms` (`total`, `filas`, `ms_por_fila`; sale en la respuesta del flujo, visible en el historial → acción `Responder_a_PowerApps` → *Salidas*), y la duración de la ejecución.

### Comprobaciones en el historial del flujo (una ejecución cualquiera)

- Por fila hay **un** `Leer_deposito` (GET) y, solo si la fila seguía válida, **un** `Actualizar_deposito` (POST) con el encabezado `IF-MATCH` = un valor entre comillas (p. ej. `"3"`), **nunca `*`**, y estado **204**.
- Si una fila falló, el bucle **siguió** con las demás (las demás `Para_cada_fila` en verde).
- Si ves `ERROR_NO_CONTROLADO`, abre la ejecución, busca la primera acción **roja** (será una de `Filas_*` o `Detalle_*`) y copia su error.

### Cómo decidir el máximo por llamada (sin inventar números)

1. Con T5 y T6 obtén `ms_por_fila` (y comprueba si el 50 terminó dentro del tiempo de espera de Power Apps).
2. Máximo seguro ≈ **(tiempo de espera de la app × 0,6) ÷ `ms_por_fila`**. Cámbialo en `PARAM_MAX_FILAS_POR_LLAMADA` (Redactar, arriba del flujo) → **Guardar**.
3. Si el máximo seguro resulta mucho menor que lo que necesitas, aplica la alternativa mínima de `CONFIRMACION_MASIVA.md` §7 (partir en trozos desde Power Apps): **no se crea hasta que las mediciones lo demuestren**.

## OPCIONAL · mensaje nuevo del límite de 1999 filas en la prevalidación

Cambió solo el **texto** del error para archivos de 2000 filas o más; el comportamiento ya existía. Si quieres verlo en el tenant: sigue `flows/ACTUALIZAR_FLUJO_PREVALIDACION.md` (opción A) con el **`P9_MASIVA_PROTO_PREVALIDAR.zip` regenerado** de esta rama. No es necesario para probar la confirmación.

## Si algo falla — volver atrás

- **Flujo:** Mis flujos → `P9_MASIVA_PROTO_CONFIRMAR` → **⋯ → Desactivar** (y **Eliminar** si quieres). No afecta a ningún otro flujo.
- **Power Apps:** restaura las fórmulas anteriores desde el historial de versiones de la app (**Configuración → Versiones**) o, propiedad por propiedad, desde `powerapps/tenant/P9_Confirmacion_Masiva.pa.yaml` (el export de tu app ANTES de integrar la confirmación).
- **Datos:** lo ya confirmado **no se revierte solo**. Para devolver un depósito a `DISPONIBLE` usa la reversión vigente (solicitud y aprobación).
