# SharePoint para el camino directo: 1 lista vacía + 1 carpeta temporal

Se eliminó todo el diseño de lotes: **no hay** `P9_MASIVA_PROTO_LOTES`, ni `Confirmaciones_Masivas`, ni `Confirmaciones_Masivas_Detalle`, ni `LOTE_UID`, ni estados persistentes, ni copia permanente del Excel. El único material que necesita el prototipo es:

## 1 · Lista vehículo `P9_MASIVA_PROTO_ADJUNTO` (vacía, siempre)

**Por qué existe.** En Power Apps el control de adjuntos solo vive dentro de un *formulario*, y un formulario necesita un origen de datos. Esa lista es **únicamente un vehículo técnico** para alojar el control de adjuntos: **nunca se le escribe nada** (no hay `SubmitForm` ni `Patch`) y **no guarda lotes, estados, historial, trazabilidad ni archivos permanentes**. **No es parte de la lógica de negocio:** ni el flujo ni la validación la leen, la escriben ni la necesitan (el flujo ni siquiera la referencia). Debe quedar con **0 elementos**.

1. Microsoft Lists / Contenido del sitio → **+ Nueva → Lista → Lista en blanco** → nombre `P9_MASIVA_PROTO_ADJUNTO` → Crear. No hace falta añadir columnas.
2. Engranaje → *Configuración de la lista* → *Configuración avanzada* → *Datos adjuntos:* **Habilitados** (es lo predeterminado) → Aceptar.
3. (Opcional) Si en tu Studio puedes sacar el control de adjuntos de su tarjeta y usarlo suelto en la pantalla (`Items` vacío), el formulario y esta lista dejan de hacer falta. No está probado; el prototipo usa el camino con formulario.

## 2 · Carpetas en el OneDrive (sitio personal `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`)

| Carpeta | Uso | Contenido esperado |
|---|---|---|
| `P9_MASIVA_TEMP` | Copia temporal que crea el flujo en cada ejecución | **Observado:** el borrado de la copia devuelve HTTP 423 (Locked), así que **quedan `TMP_<guid>.xlsx`** acumulados. Se aceptan por ahora; se borran a mano. No hay limpiador |
| `P9_MASIVA_PROTO` | Plantilla que descarga el botón DESCARGAR PLANTILLA | Solo `Plantilla_Confirmacion_Masiva_P9.xlsx` (y, si quieres, el Ejemplo) |

**[HISTÓRICO — anterior a la reorganización a `Documents/CONTROL_DEPOSITOS/P9/`, ver `../RUTAS_P9.md`]** **Estructura real encontrada en el tenant (observada, no corregida):** existe una carpeta llamada `Documents` **dentro** de la raíz `Documents`, y `P9_MASIVA_PROTO` está en la anidada: `/personal/gtorricot_univalle_edu/Documents/Documents/P9_MASIVA_PROTO/Plantilla_Confirmacion_Masiva_P9.xlsx` (UniqueId `84b7ef88-43aa-43d2-8d1c-0f0b682dafbd`). Además aparecen **dos carpetas `P9_MASIVA_TEMP`** (una en cada `Documents`) y se desconoce en cuál escribe el flujo. **No se reorganiza ni se borra nada desde Git; revisar antes de producción** (`../ESTADO_CHECKPOINT_TENANT.md`).

La plantilla se descarga por **UniqueId** (`/_layouts/15/download.aspx?UniqueId=…`), no por ruta. El UniqueId pertenece al archivo actual: para actualizar la plantilla usa *Reemplazar* o sube una **nueva versión**; si la borras y la recreas, el UniqueId cambia y hay que actualizar el botón de Power Apps.

Permisos: el flujo necesita crear (y borrar) archivos en `P9_MASIVA_TEMP`; los usuarios de la app necesitan **leer** el archivo de la plantilla. **Prueba multiusuario pendiente** (hoy todo se probó con la cuenta del propietario). Los usuarios no necesitan acceso a `P9_MASIVA_TEMP`: el flujo trabaja con su propia conexión.

## 3 · Eliminar al terminar el prototipo

Contenido del sitio → ⋯ junto a `P9_MASIVA_PROTO_ADJUNTO` → **Eliminar**; OneDrive → las carpetas `P9_MASIVA_TEMP` (las dos) y `P9_MASIVA_PROTO` → **Eliminar**; Papelera del sitio → **Vaciar**. Antes, desactiva y borra el flujo (`flows/INSTRUCCIONES_FLUJO.md`).
