# Crear la lista PROTOTIPO `P9_MASIVA_PROTO_LOTES` (10 minutos)

Fuente de verdad: `esquema_P9_MASIVA_PROTO_LOTES.json` (un test comprueba que el flujo solo escribe columnas de este esquema). Lista TEMPORAL; no es la definitiva.

Sitio: el mismo de P9 (`https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`).

## 1 · Crear la lista

1. Microsoft Lists / Contenido del sitio → **+ Nueva → Lista → Lista en blanco**.
2. Nombre: `P9_MASIVA_PROTO_LOTES` (exacto, sin espacios) → **Crear**.
3. Engranaje → **Configuración de la lista** → clic en la columna **Title** → *Requerir que esta columna contenga información:* **No** → Aceptar. (Si queda obligatoria, la app no podrá crear el lote.)
4. Misma pantalla → **Configuración avanzada** → *Datos adjuntos:* **Habilitados** (es lo predeterminado) → Aceptar.

## 2 · Crear las columnas

**Importante:** el nombre interno se fija al crear la columna y no se puede cambiar. Créalas con el nombre exacto de la tabla (sin tildes ni espacios).

| Nombre | Tipo | Detalle |
|---|---|---|
| `LOTE_UID` | Una línea de texto | — |
| `ESTADO` | Una línea de texto | **Texto, no Opción** |
| `ARCHIVO_NOMBRE` | Una línea de texto | — |
| `MENSAJE` | Varias líneas de texto | Texto sin formato (desactivar texto enriquecido) |
| `CODIGO_RESULTADO` | Una línea de texto | — |
| `TABLA_ENCONTRADA` | Una línea de texto | — |
| `FILAS_LEIDAS` | Número | 0 posiciones decimales |
| `FECHA_CREACION` | Fecha y hora | Incluir hora |
| `FECHA_ESTADO` | Fecha y hora | Incluir hora |

Para cada una: **+ Agregar columna** → tipo → escribe el nombre → Guardar. Ninguna es obligatoria y ninguna lleva valor predeterminado.

## 3 · Carpeta temporal y plantilla

1. En **Documentos** del mismo sitio crea la carpeta `P9_MASIVA_PROTO`.
2. Sube ahí `xlsx/Plantilla_Confirmacion_Masiva_P9.xlsx` (el botón DESCARGAR PLANTILLA de la app apunta a este archivo).
3. Verifica que los usuarios de la app tengan permiso de **lectura** sobre esa carpeta y **edición** sobre la lista.

## 4 · Comprobación rápida

Abre la lista y confirma que ves las 9 columnas (hasta `FECHA_ESTADO`) y que **+ Nuevo elemento** permite guardar sin escribir Title.

## 5 · Eliminar al terminar el prototipo

Contenido del sitio → ⋯ junto a `P9_MASIVA_PROTO_LOTES` → **Eliminar**; Documentos → carpeta `P9_MASIVA_PROTO` → **Eliminar**; Papelera del sitio → **Vaciar**. (Primero desactiva y borra el flujo, ver `flows/INSTRUCCIONES_FLUJO.md`.)
