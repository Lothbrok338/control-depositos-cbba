# Actualizar la CONFIRMACIÓN MASIVA a «hasta 1999 filas con UN clic» — pasos exactos

> **Estado:** la **V1** (síncrona, 2 filas) funcionó de punta a punta en tu tenant (commit `82b279e`, `../VALIDACION_TENANT_V1.md`). **Esta versión (escala 1999) NO está validada en el tenant**: está probada con un SharePoint simulado.
> Diseño, límites de Microsoft verificados y riesgos: **`../ESCALA_1999.md`**.

> ## ⚠ Esta confirmación ESCRIBE en `Depositos_Activos` REAL
> Cambia depósitos a `ASIGNADO` (como la confirmación individual). **No hay rollback automático**: lo ya confirmado no se revierte (la reversión vigente es por solicitud y aprobación).
> Trabaja en la copia `P9_PRUEBA_MASIVA`; no publiques sobre producción y no toques otros flujos.

Se **actualizan los mismos artefactos** (no se crean copias con otro nombre): `P9_MASIVA_PROTO_CONFIRMAR` (evoluciona), `P9_PRUEBA_MASIVA` (misma pantalla) y se añade UN flujo de consulta: `P9_MASIVA_PROTO_ESTADO`.

| Archivo (rama `experiment/p9-masiva-prototipo`, carpeta `proto_masiva/`) | Para qué |
|---|---|
| `flows/P9_MASIVA_PROTO_CONFIRMAR.zip` | el flujo de confirmación actualizado (responde ACEPTADO y sigue procesando) |
| `flows/P9_MASIVA_PROTO_ESTADO.zip` | el flujo NUEVO de consulta de avance (solo lectura) |
| `powerapps/CONFIRMACION_POWERFX.md` | las fórmulas A–I (sobre tus controles reales) y cómo crear el Temporizador, en tu sintaxis (`;` y `;;`) |
| `flows/GUIA_ACCIONES_CONFIRMACION.md`, `flows/GUIA_ACCIONES_ESTADO.md` | las mismas acciones, una por una, si un ZIP no se pudiera importar (opción B) |
| `ESCALA_1999.md` | arquitectura, límites de Microsoft (DOCUMENTADO / INFERIDO), solicitudes estimadas y riesgos |
| `RUTAS_P9.md` | rutas físicas tras mover P9 a `Documents/CONTROL_DEPOSITOS/P9/` (**los TRES ZIP cambiaron**: también el de la prevalidación) |

**Qué cambió para ti:** (1) `P9_MASIVA_PROTO_CONFIRMAR` ya no devuelve el resultado final, devuelve `ACEPTADO` + `execution_uid` en segundos; (2) un Temporizador oculto consulta el avance cada 15 s con `P9_MASIVA_PROTO_ESTADO`;
(3) el tope de 50 filas desapareció (ahora 1999); (4) **hay que quitar y volver a agregar el flujo en Power Apps** (su contrato cambió).

## PARTE 1 · Power Automate

### 1.1 · Actualizar `P9_MASIVA_PROTO_CONFIRMAR` (mismo nombre, un solo flujo al final)

La V1 queda respaldada en Git (`git show 82b279e:proto_masiva/flows/P9_MASIVA_PROTO_CONFIRMAR.zip`); no necesitas exportar nada.

1. `make.powerautomate.com` → **Mis flujos** → **Importar** → **Importar paquete (heredado)** → **Cargar** → `P9_MASIVA_PROTO_CONFIRMAR.zip`.
2. En *Contenido del paquete*, fila **P9_MASIVA_PROTO_CONFIRMAR** → **Acción de importación**:
   - Si ofrece **Actualizar** → elígela (reemplaza la definición y mantiene el vínculo con la app).
   - Si **solo** ofrece **Crear como nuevo**: cancela, ve a **Mis flujos** → `P9_MASIVA_PROTO_CONFIRMAR` → **⋯** → **Eliminar**, y repite la importación con **Crear como nuevo**. Quedará **un solo flujo con el mismo nombre**
     (no lo renombres ni lo dejes «antiguo»: dos flujos con el mismo nombre confunden a Power Apps).
3. Conexión **SharePoint** → **Seleccionar durante la importación** → tu conexión existente (la misma de `P9_ASIGNAR_DEPOSITO`) → **Guardar** → **Importar**.
4. **Mis flujos** → `P9_MASIVA_PROTO_CONFIRMAR` → **Editar**.

### 1.2 · Importar `P9_MASIVA_PROTO_ESTADO` (flujo nuevo)

Igual que arriba con `P9_MASIVA_PROTO_ESTADO.zip` y **Crear como nuevo** (es nuevo). Misma conexión de SharePoint. Luego **Editar**.

### 1.2b · Actualizar `P9_MASIVA_PROTO_PREVALIDAR` (ruta de la carpeta temporal — único cambio)

Los recursos de P9 se movieron a `Documents/CONTROL_DEPOSITOS/P9/` y la prevalidación ya funcionando todavía escribe sus `TMP_*.xlsx` en la ruta antigua. **Asegúrate de que exista la carpeta `Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP`** y actualiza el flujo:
- **Opción mínima (sin reimportar):** `P9_MASIVA_PROTO_PREVALIDAR` → **Editar** → acción `PARAM_CARPETA` (Redactar, arriba) → cambia el valor a `/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` → **Guardar**. Es lo único que cambia en su paquete.
- **O** importa `P9_MASIVA_PROTO_PREVALIDAR.zip` con **Actualizar** (mismo procedimiento que 1.1).
No se toca la lógica ni Power Apps. Detalle y plantilla (se descarga por UniqueId, sin ruta): `../RUTAS_P9.md`.

### 1.3 · Revisar antes de guardar (abre cada acción con un clic en su cabecera)

**`P9_MASIVA_PROTO_CONFIRMAR`**

| # | Acción | Debe quedar así |
|---|---|---|
| 1 | Disparador **Power Apps (V2)** | **dos** entradas de tipo Texto, en este orden: `detalle_json` y `usuario_email` |
| 2 | `PARAM_MAX_FILAS_POR_LLAMADA` (Redactar, arriba) | **1999** (ya no 50). Junto a ella: `PARAM_INTERVALO_PROGRESO` = 25, `PARAM_MAX_DETALLE` = 300, `PARAM_CARPETA` = `/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` |
| 3 | `RESPONDER` (Condición) | **dos** acciones «Responder a una aplicación de PowerApps o a un flujo»: `Responder_aceptado` (rama Sí) y `Responder_error` (rama No). **No las muevas ni las pongas dentro del bucle** |
| 4 | `Para_cada_fila` (dentro de `PROCESAR` → rama Sí) | ⋯ → **Configuración** → *Control de simultaneidad* **Activado**, *Grado de paralelismo* = **1** |
| 5 | `Leer_deposito` (dentro de `TRY_FILA`) | Sitio `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` · `GET` · ⋯ → Configuración → *Directiva de reintentos*: **Intervalo fijo, 2 reintentos, PT5S** |
| 6 | `Actualizar_deposito` (dentro de `TRY_FILA` → `Puede_confirmar` rama Sí) | `POST` · `X-HTTP-Method: MERGE` · `IF-MATCH` = ETag fresco (`@outputs('Revalidacion')?['etag']`) · *Directiva de reintentos*: **Ninguna**. **Nunca `*`** |
| 7 | `Crear_estado` · `Escribir_progreso` · `Escribir_final_estado` · `Escribir_final_minimo` | acciones de **SharePoint** (*Crear archivo* / *Actualizar archivo*) con tu conexión; `Crear_estado`: reintentos **Ninguna**; las de *Actualizar archivo*: **Intervalo fijo, 2 reintentos, PT5S** |

**`P9_MASIVA_PROTO_ESTADO`**: disparador con **una** entrada de texto `execution_uid`; `Leer_estado` = *Obtener contenido del archivo con la ruta de acceso*, *Inferir tipo de contenido* **No**.

Si una acción muestra ⚠ o campos vacíos, **vuelve a elegir la conexión de SharePoint** en esa acción; no cambies ninguna expresión. **Guardar** → «Su flujo está listo» en ambos. Si el *Comprobador de flujos* marca errores, **no sigas**: copia el texto exacto.
Comprueba que los dos flujos estén **Activados**.

### 1.4 · La carpeta
Los archivos de estado `confirmacion_<execution_uid>.json` se crean en `Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` (**la carpeta debe existir ahí**: `Crear archivo` no la crea), **la misma carpeta técnica que usa la prevalidación** para sus `TMP_*.xlsx` (si ahí ves los `TMP_*`, ahí aparecerán los `confirmacion_*`).
No son historial; no se limpian solos (puedes borrarlos a mano; retención sugerida 24 h).

## PARTE 2 · Power Apps (`P9_PRUEBA_MASIVA`, la COPIA)

Los controles ya existen: **no pegues controles ni YAML**; solo fórmulas y **un** control nuevo (un Temporizador oculto). Detalle exacto en `powerapps/CONFIRMACION_POWERFX.md`.

1. `make.powerapps.com` → **Aplicaciones** → `P9_PRUEBA_MASIVA` → **Editar**.
2. Panel **Power Automate** (⚡): en `P9_MASIVA_PROTO_CONFIRMAR` → **⋯** → **Quitar de la aplicación** (saldrán errores rojos en `.Run`: son esperados). **Agregar flujo** → `P9_MASIVA_PROTO_ESTADO`. **Agregar flujo** → `P9_MASIVA_PROTO_CONFIRMAR`.
3. *Insertar → Entrada → Temporizador*; renómbralo **`tmrProgresoP9`**; `Duration` = `15000`, `Repeat` = `true`, `AutoStart` = `false`, `Start` = `Coalesce(varMonitorearP9; false)`, `Visible` = `false`.
4. Pega las fórmulas del documento **de la A a la I, en orden (la A primero: define las variables)**. La B va en `tmrProgresoP9` → `OnTimerEnd`; la D en `attXlsxP9` → `OnAddFile` **y** `OnRemoveFile`.
5. **Comprobador de aplicaciones** (estetoscopio): sin errores. Si marca error en `P9_MASIVA_PROTO_ESTADO.Run` / `P9_MASIVA_PROTO_CONFIRMAR.Run`, comprueba que IntelliSense pida **argumentos de texto** (`execution_uid`; `detalle_json`, `usuario_email`); si no, avísame.
6. **Guardar**. No publiques sobre producción.

Reglas de Studio de tu tenant que las fórmulas ya cumplen (no las deshagas a mano): `IfError` con ramas `true`/`false`; `ShowColumns` con los nombres de columna **sin comillas**.

## PARTE 3 · Primer uso real (qué observar y qué copiarme)

No hay un protocolo de «10, luego 50»: usa el flujo con un lote real. Lo que debe verse:

1. Al pulsar **CONFIRMAR MASIVAMENTE (N)** (N = 1…1999, **un solo clic**): en **segundos** el panel pasa a «CONFIRMACIÓN EN PROCESO · 0 % / 0 de N procesados», el botón queda **Disabled**.
2. Cada ~15 s avanza: «CONFIRMACIÓN EN PROCESO · 27 % / 350 de 1284 procesados · 347 confirmados · 3 requieren revisión».
3. Al terminar: «CONFIRMACIÓN COMPLETADA / 1278 de 1284 depósitos confirmados · 6 requieren revisión», `VER OBSERVACIONES (6)` con SOLO esas filas, tiempo total.
4. En `Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` aparece `confirmacion_<guid>.json` (puedes abrirlo: contadores, estado, y al final solo las no confirmadas).
5. En `Depositos_Activos` los confirmados están `ASIGNADO`.

**Qué copiarme después** (así se miden los tiempos reales, que NO se pueden suponer): N, el tiempo mostrado, y en el **Historial de ejecuciones** de `P9_MASIVA_PROTO_CONFIRMAR` la duración total, cuándo ejecutó `Responder_aceptado`
y la duración de una iteración de `Para_cada_fila`; el campo `tiempos_ms` del archivo de estado (`total=…;filas=…;ms_por_fila=…`). Y cualquier mensaje rojo de Power Apps o de Power Automate.

### Si algo no avanza
- **Power Automate → `P9_MASIVA_PROTO_CONFIRMAR` → Historial de ejecuciones:** la ejecución debe seguir «En ejecución» después de haber respondido; `Responder_aceptado` en verde; dentro de `PROCESAR` → `Para_cada_fila` avanzando.
- Si la app dice «ERROR_ESTADO»: no se pudo crear el archivo de estado (revisa `Crear_estado` y la carpeta); **no se confirmó nada**.
- Si la app dice «No se pudo consultar el progreso…»: el flujo puede seguir; vuelve a PREVALIDAR (lo ya confirmado sale `NO_DISPONIBLE`).
- Si el input es demasiado grande y Power Apps muestra «El flujo no respondió…» al pulsar: no se confirmó nada; avísame con el N (ver riesgo 1 de `ESCALA_1999.md`).

### Cuota de solicitudes
Una confirmación de 1999 filas ≈ 22.200 acciones + ≈ 2.900 por hora de seguimiento. Con licencia de Microsoft 365 (6.000/día por usuario) excede la asignación; con Power Automate Premium (40.000) cabe una por día. Superarlo **ralentiza** los flujos (documentado), no los bloquea hoy. Mira tu licencia antes de volúmenes grandes (`ESCALA_1999.md` §5).

## Si algo falla — volver atrás
- **Power Apps:** *Configuración → Versiones* → restaura la versión anterior de `P9_PRUEBA_MASIVA` (la V1 publicada); o propiedad por propiedad desde `powerapps/tenant_v1/P9_Confirmacion_Masiva.pa.yaml`.
- **Flujo:** importa el ZIP de la V1 (`git show 82b279e:proto_masiva/flows/P9_MASIVA_PROTO_CONFIRMAR.zip`) y quita/vuelve a agregar el flujo en la app; desactiva `P9_MASIVA_PROTO_ESTADO` (no afecta a otros flujos).
- **Datos:** lo ya confirmado **no se revierte solo**; usa la reversión vigente (solicitud y aprobación).
