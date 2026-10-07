# Llevar la prevalidación REAL a tu tenant — pasos exactos

> **Esta versión NO está validada en el tenant.** Sigue los pasos en una **copia** (`P9_PRUEBA_MASIVA`); no publiques nada sobre producción y no toques ningún otro flujo.
> Antes de empezar, la versión actual del flujo (la validada: COMPLETADO / 3 filas) **se respalda** (paso 1). La prevalidación es de **solo lectura**: no escribe en `Depositos_Activos`.

Archivos que necesitas (rama `experiment/p9-masiva-prototipo`, carpeta `proto_masiva/`):

| Archivo | Para qué |
|---|---|
| `flows/P9_MASIVA_PROTO_PREVALIDAR.zip` | el flujo actualizado (opción A) |
| `flows/GUIA_ACCIONES_PREVALIDACION.md` | las mismas acciones, una por una, con sus expresiones (opción B, si el ZIP no se pudiera usar) |
| `powerapps/PREVALIDACION_POWERFX.md` | las 5 fórmulas que cambian en la pantalla de Power Apps |

## PARTE 1 · Power Automate

### 1 · Respaldar el flujo actual (30 segundos)

1. `make.powerautomate.com` → **Mis flujos**.
2. En la fila `P9_MASIVA_PROTO_PREVALIDAR` → **⋯ (Más acciones)** → **Exportar** → **Paquete (.zip)**.
3. Nombre del paquete: `P9_MASIVA_PROTO_PREVALIDAR_RESPALDO_VALIDADO` → **Exportar** → guarda el `.zip` descargado. Si algo sale mal, este ZIP restaura la versión que ya funcionaba.

### 2 · OPCIÓN A (recomendada): importar el ZIP actualizado

1. **Mis flujos** → **Importar** → **Importar paquete (heredado)** → **Cargar** → elige `P9_MASIVA_PROTO_PREVALIDAR.zip`.
2. En *Contenido del paquete*, fila **P9_MASIVA_PROTO_PREVALIDAR** (tipo *Flujo*): clic en **Acción de importación**:
   - Si ofrece **Actualizar** → elígela (reemplaza la definición del flujo existente y mantiene su vínculo con la app).
   - Si **solo** ofrece **Crear como nuevo** → elígela, pero **antes** renombra el flujo antiguo (Mis flujos → `P9_MASIVA_PROTO_PREVALIDAR` → **Editar** → arriba, el nombre → `P9_MASIVA_PROTO_PREVALIDAR_ANTIGUO` → **Guardar** → **Desactivar**). Dos flujos con el mismo nombre confunden a Power Apps.
3. En las **dos conexiones** (**SharePoint** y **Excel Online (Business)**) → **Seleccionar durante la importación** → elige **tus conexiones ya existentes** (las que usa el flujo actual) → **Guardar**.
4. **Importar**. Espera «El paquete se importó correctamente».
5. **Mis flujos** → `P9_MASIVA_PROTO_PREVALIDAR` → **Editar**.

### 3 · Revisar y completar 4 puntos (el paquete trae un único marcador sin resolver)

Abre cada acción con un clic en su cabecera:

1. **`Leer_tabla_Excel`** (está dentro de `TRY` → `Entrada_valida`). Debe quedar:
   - **Ubicación (Location):** `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` (ya viene en el paquete; si aparece vacío o distinto, elige *Escribir un valor personalizado* y pégala).
   - **Biblioteca de documentos (Document Library):** abre el desplegable y elige **OneDrive** (esto reemplaza el marcador `<CONFIGURAR_BIBLIOTECA_EXCEL>`; su identificador interno solo lo resuelve el diseñador).
   - **Archivo (File):** contenido dinámico **`Id`** de la acción `Crear_archivo`. Si quedó vacío, haz clic en el campo → pestaña *Contenido dinámico* → `Id` bajo *Crear archivo*.
   - **Tabla (Table):** valor personalizado `tblConfirmacionMasiva`.
   - **⋯ → Configuración:** *Paginación* activada, umbral **2000**; *Directiva de reintentos* = **Ninguna**.
2. **`Crear_archivo`**: *Ruta de acceso de la carpeta* `/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP`; *Nombre del archivo* y *Contenido del archivo* sin cambios (si aparece ⚠, vuelve a elegirlos con los desplegables).
3. **`Leer_depositos`** (acción nueva, dentro de `TRY` → … → `Hay_tope` → rama **No**): debe mostrar **Dirección del sitio** = `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`, **Método** `GET`. No cambies nada más; si aparece ⚠, vuelve a elegir la conexión de SharePoint.
4. **`Borrar_copia_temporal`**: sin cambios respecto de antes (la prueba de 10 s de espera que hiciste a mano **no** está en este paquete; no resolvió el error 423 y se decidió no seguir con eso).

### 4 · Guardar y comprobar

1. **Guardar** (arriba a la derecha). Debe decir «Su flujo está listo». Si el *Comprobador de flujos* marca errores, **no sigas**: copia el texto exacto del error y pásamelo.
2. Comprueba que el flujo esté **Activado** (Mis flujos → columna *Estado*).

### 2-B · OPCIÓN B (solo si la importación no fuera posible): armarlo a mano

Abre `flows/GUIA_ACCIONES_PREVALIDACION.md` y sigue sus 3 partes **en orden** (parámetros y variables nuevas → bloque de acciones que reemplaza a `Resultado_OK` → tres cambios en acciones existentes). Cada acción trae su nombre, tipo y expresión exactos. Después haz los puntos 1 a 4 de arriba.

## PARTE 2 · Power Apps (`P9_PRUEBA_MASIVA`, la COPIA)

1. `make.powerapps.com` → **Aplicaciones** → `P9_PRUEBA_MASIVA` → **Editar**.
2. **Refrescar el flujo** (cambiaron sus salidas): panel izquierdo → **Power Automate** (icono ⚡) → junto a `P9_MASIVA_PROTO_PREVALIDAR` → **⋯** → **Quitar**; luego **Agregar flujo** → elige `P9_MASIVA_PROTO_PREVALIDAR`. Mientras no lo vuelvas a agregar, `btnPrevalidarP9` mostrará un error rojo: es normal.
3. **Cambiar 5 fórmulas** con `powerapps/PREVALIDACION_POWERFX.md` (cada bloque está escrito con `;` y `;;`, tu configuración regional): `btnPrevalidarP9.OnSelect`, `lblEstadoP9.Fill`, `lblTitularResultadoP9.Text`, `lblResFilasP9.Text`, `lblAvisoPrototipoP9.Text`. Selecciona el control → elige la propiedad → borra todo → pega.
4. **Ver la colección** (temporal, sin diseñar nada): **Insertar** → **Tabla de datos** → `Items` = `colPrevalidacionP9` → marca `fila_excel`, `resultado`, `mensaje`, `deposito_id`, `estado_actual`.
5. **Comprobador de aplicaciones** (icono del estetoscopio): sin errores nuevos. Si marca error en `ThisRecord.Value`, anótalo y no sigas: solo esa línea se ajusta.
6. **Guardar**. **No publiques sobre producción.** Reproduce con F5 desde la pantalla `P9_Confirmacion_Masiva`.

## PARTE 3 · Pruebas mínimas en el tenant (con datos REALES, sin escribir nada)

Usa la **galería individual de la app P9** (solo lectura) para elegir depósitos reales. Para cada prueba, llena `Plantilla_Confirmacion_Masiva_P9.xlsx` con las filas indicadas (ESTUDIANTE, SOLICITADO_POR y SEDE pueden ser cualquier texto de prueba) y pulsa **PREVALIDAR ARCHIVO**.

| # | Qué cargar | Resultado esperado | Qué te dice |
|---|---|---|---|
| **T0** | cualquier fila válida | `depositos_consultados` **igual** al «N resultados visibles» de la galería individual, **sin filtros ni texto** (la galería muestra solo `DISPONIBLE` y `ASIGNADO`; si coincide, la ventana de fechas y el filtro CRÉDITO son los mismos) | valida el `$filter`, la fecha de «hoy» y los 2 meses |
| T1 | un crédito `DISPONIBLE` de la galería (BANCO, CUENTA, CÓDIGO, IMPORTE, MONEDA exactos) | `VALIDO`, `deposito_id` = ID del elemento en la lista, `estado_actual` = `DISPONIBLE`; global `OK` | el caso feliz |
| T2 | la misma fila con el importe +0,01 | `NO_ENCONTRADO` | no hay redondeo |
| T3 | la misma fila con la otra moneda | `MONEDA_NO_COINCIDE` y `moneda_deposito` con la real | moneda vs clave |
| T4 | un crédito `ASIGNADO` de la galería | `NO_DISPONIBLE`, `estado_actual` = `ASIGNADO` | estados |
| T5 | la fila de T1 dos veces | las **dos** `DUPLICADO_ARCHIVO` | duplicados |
| T6 | la fila de T1 con SEDE vacía | `FILA_INCOMPLETA` («Faltan datos obligatorios: SEDE.») | requeridos |
| T7 | si existe un depósito con `CODIGO_ASIGNACION` o cuenta con ceros iniciales (p. ej. BISA `0696870039`) | `VALIDO` conservando los ceros | texto, no número |
| T8 | si existe un depósito fechado exactamente `hoy − 2 meses` (y otro el día anterior) | el del día exacto `VALIDO`; el del día anterior `NO_ENCONTRADO` | el borde de la ventana |
| T9 | archivos de 10, 50 y 100 filas (`xlsx/medicion/` solo trae filas ficticias: sirven para medir **tiempo**, saldrán `NO_ENCONTRADO`) | anota `tiempos_ms` (App y flujo) en `MEDICION_TENANT.md` | rendimiento |

Comprobaciones en el **historial de ejecuciones** del flujo (Mis flujos → `P9_MASIVA_PROTO_PREVALIDAR` → *Historial de ejecuciones* → la ejecución):
- La acción `Leer_depositos` aparece **una sola vez** y su método es `GET`.
- **Ninguna** acción escribe en `Depositos_Activos`. En la lista, ordena por *Modificado*: ningún elemento debe aparecer modificado por la prueba.
- Si una prueba da `ERROR_SHAREPOINT`: abre `Leer_depositos` → *Salidas* y copia el **código de estado y el texto del error** (es lo que decide si el `$filter` o la tilde de `CRÉDITO` hay que ajustar).
- Si da un error `ERROR_NO_CONTROLADO`: abre la ejecución, busca la primera acción **roja** (será una de `Filas_*`, `Depositos_normalizados`, `Detalle_filas`…) y copia su error: indica qué expresión no se comporta como en las pruebas locales.

## Si algo falla — vuelve atrás

Mis flujos → Importar → Importar paquete (heredado) → carga `P9_MASIVA_PROTO_PREVALIDAR_RESPALDO_VALIDADO.zip` → **Actualizar**. En Power Apps, vuelve a quitar y agregar el flujo y, si ya habías cambiado las 5 fórmulas, restaura las anteriores (las de `P9_Confirmacion_Masiva.pa.yaml` del commit anterior `b2f16e1`).
