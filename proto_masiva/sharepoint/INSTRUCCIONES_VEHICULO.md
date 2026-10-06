# SharePoint para el camino directo: 1 lista vacía + 1 carpeta temporal

Se eliminó todo el diseño de lotes: **no hay** `P9_MASIVA_PROTO_LOTES`, ni `Confirmaciones_Masivas`, ni `Confirmaciones_Masivas_Detalle`, ni `LOTE_UID`, ni estados persistentes, ni copia permanente del Excel. El único material que necesita el prototipo es:

## 1 · Lista vehículo `P9_MASIVA_PROTO_ADJUNTO` (vacía, siempre)

**Por qué existe.** En Power Apps el control de adjuntos solo vive dentro de un *formulario*, y un formulario necesita un origen de datos. Esa lista es **únicamente un vehículo técnico** para alojar el control de adjuntos: **nunca se le escribe nada** (no hay `SubmitForm` ni `Patch`) y **no guarda lotes, estados, historial, trazabilidad ni archivos permanentes**. **No es parte de la lógica de negocio:** ni el flujo ni la validación la leen, la escriben ni la necesitan (el flujo ni siquiera la referencia). Debe quedar con **0 elementos**.

1. Microsoft Lists / Contenido del sitio → **+ Nueva → Lista → Lista en blanco** → nombre `P9_MASIVA_PROTO_ADJUNTO` → Crear. No hace falta añadir columnas.
2. Engranaje → *Configuración de la lista* → *Configuración avanzada* → *Datos adjuntos:* **Habilitados** (es lo predeterminado) → Aceptar.
3. (Opcional) Si en tu Studio puedes sacar el control de adjuntos de su tarjeta y usarlo suelto en la pantalla (`Items` vacío), el formulario y esta lista dejan de hacer falta. No está probado; el prototipo usa el camino con formulario.

## 2 · Carpetas en Documentos del mismo sitio

| Carpeta | Uso | Contenido esperado |
|---|---|---|
| `Documents/P9_MASIVA_TEMP` | Copia temporal que crea y **borra** el flujo en cada ejecución | **Vacía** en condiciones normales. Si el flujo informa «no se pudo eliminar», queda un `TMP_<guid>.xlsx` que se borra a mano |
| `Documents/P9_MASIVA_PROTO` | Plantilla que descarga el botón DESCARGAR PLANTILLA | Solo `Plantilla_Confirmacion_Masiva_P9.xlsx` (y, si quieres, el Ejemplo) |

Permisos: el flujo necesita crear y borrar archivos en `P9_MASIVA_TEMP`; los usuarios de la app, **leer** `P9_MASIVA_PROTO`. Los usuarios no necesitan acceso a `P9_MASIVA_TEMP`: el flujo trabaja con su propia conexión.

## 3 · Eliminar al terminar el prototipo

Contenido del sitio → ⋯ junto a `P9_MASIVA_PROTO_ADJUNTO` → **Eliminar**; Documentos → carpetas `P9_MASIVA_TEMP` y `P9_MASIVA_PROTO` → **Eliminar**; Papelera del sitio → **Vaciar**. Antes, desactiva y borra el flujo (`flows/INSTRUCCIONES_FLUJO.md`).
