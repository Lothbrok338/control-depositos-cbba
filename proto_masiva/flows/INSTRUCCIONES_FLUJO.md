# Importar y revisar el flujo PROTOTIPO `P9_MASIVA_PROTO_PREVALIDAR`

Arquitectura: la app crea el lote con el XLSX adjunto y lo deja en `PENDIENTE` → **este flujo se dispara solo** cuando un elemento de `P9_MASIVA_PROTO_LOTES` queda en `PENDIENTE` → `PROCESANDO` → `COMPLETADO` o `ERROR` → la app consulta el estado. No hay «Respuesta temprana» ni se llama al flujo desde Power Apps (no hay que agregarlo en la app).

Archivos: `construir.py` (generador), `P9_MASIVA_PROTO_PREVALIDAR_definition.json`, `P9_MASIVA_PROTO_PREVALIDAR.zip` (paquete heredado, mismo formato que los ZIP P8/P9 que ya importaste).

## Antes: crear la lista

`sharepoint/INSTRUCCIONES_LISTA.md`. El flujo depende de ella.

## 1 · Importar

1. Power Automate → **Mis flujos → Importar → Importar paquete (heredado)** → sube `P9_MASIVA_PROTO_PREVALIDAR.zip`.
2. En *Contenido del paquete* clic en la acción del flujo → **Crear como nuevo**. En las dos conexiones (SharePoint, Excel Online (Business)) → **Seleccionar al importar** → elige o crea tu conexión.
3. **Importar**. Tras importar queda apagado o con avisos: sigue el paso 2.

## 2 · Revisar 5 puntos (obligatorio la primera vez)

Estos nombres de operación NO están validados en tu tenant: los tomé de memoria porque `learn.microsoft.com` está bloqueado desde el entorno donde construí el flujo. Si un paso aparece con ⚠ o parámetros vacíos, **vuelve a seleccionar sus campos con los desplegables**; no cambia la lógica.

| # | Acción en el flujo | Qué comprobar / elegir |
|---|---|---|
| 1 | Disparador *Cuando un lote queda PENDIENTE* | Dirección del sitio = el sitio P9; Nombre de lista = `P9_MASIVA_PROTO_LOTES`. En **⋯ → Configuración**: *Condición del desencadenador* = `@equals(triggerBody()?['ESTADO'],'PENDIENTE')` y *Control de simultaneidad* = activado, grado 1. |
| 2 | `Obtener_adjuntos` | Sitio, lista, **Id** = Id del elemento (contenido dinámico `ID` del disparador, ya referenciado desde la acción `Lote`). |
| 3 | `Obtener_contenido_adjunto` | Sitio, lista, **Id** del elemento, **Identificador de archivo** = `Id` del adjunto (del primero devuelto por `Obtener_adjuntos`). |
| 4 | `Crear_archivo` | Carpeta = `/Documents/P9_MASIVA_PROTO`; nombre = salida de `Nombre_copia`; contenido = *Contenido del adjunto*. |
| 5 | `Leer_tabla_Excel` | **Ubicación** y **Biblioteca de documentos**: reemplaza `<CONFIGURAR_UBICACION_EXCEL>` / `<CONFIGURAR_BIBLIOTECA_EXCEL>` eligiendo OneDrive for Business y su biblioteca (el sitio de P9 es tu OneDrive). **Archivo** = contenido dinámico `Id` de `Crear_archivo`. **Tabla** = escribe `tblConfirmacionMasiva` (valor personalizado). En **⋯ → Configuración**: *Paginación* = activada, umbral 2000; *Directiva de reintentos* = Ninguna. |

Si al cambiar Ubicación/Biblioteca se borran Archivo/Tabla, vuelve a ponerlos como dice la tabla.

## 3 · Guardar y encender

**Guardar**, comprueba que no queden avisos y que el flujo esté **Activado**. Luego prueba con `ESTADO = PENDIENTE` (pruebas en `powerapps/INSTRUCCIONES_PEGADO.md`, paso 10).

## Si la importación falla: armarlo a mano (15 acciones)

Mismo orden que `P9_MASIVA_PROTO_PREVALIDAR_definition.json` (ábrelo en un editor como referencia):
1. Disparador SharePoint **Cuando se crea o modifica un elemento** + condición de arriba.
2. *Actualizar elemento* (o *Enviar solicitud HTTP a SharePoint*) → `ESTADO = PROCESANDO`.
3. **Ámbito TRY**: *Obtener datos adjuntos* → *Obtener contenido de datos adjuntos* → *Crear archivo* (carpeta temporal) → *Enumerar filas presentes en una tabla* (`tblConfirmacionMasiva`, paginación 2000) → condiciones: ¿hay filas? ¿existen los 9 encabezados? ¿hay filas con datos? → fijar `ESTADO/CODIGO_RESULTADO/FILAS_LEIDAS/MENSAJE`.
4. **Ámbito CATCH** (ejecutar si TRY *ha fallado* o *tiempo agotado*): si falló *Enumerar filas*: código 404 → `TABLA_NO_ENCONTRADA`, 423 → `ARCHIVO_BLOQUEADO`, otro → `ERROR_LECTURA_EXCEL`; si falló un paso anterior → `ERROR_ADJUNTO` / `ERROR_COPIA_ARCHIVO`.
5. *Actualizar elemento* final (ejecutar tras TRY y CATCH, **cualquier resultado**): escribe el estado final. **Nunca** vuelvas a escribir `ESTADO = PENDIENTE` desde el flujo (se redispararía en bucle).

## Qué mirar en la primera prueba con `03_SIN_TABLA.xlsx`

El resultado esperado es `ERROR / TABLA_NO_ENCONTRADA`. Si aparece `ERROR_LECTURA_EXCEL (HTTP 400…)`, el conector responde 400 y no 404 cuando no hay tabla: en el CATCH, acción `Fallo_en_excel`, cambia la condición `equals(statusCode, 404)` por `or(equals(…,400),equals(…,404))`. El mensaje del lote ya trae el HTTP y el texto del error para decidirlo.

## Eliminar al terminar

Power Automate → Mis flujos → `P9_MASIVA_PROTO_PREVALIDAR` → ⋯ → **Desactivar** y luego **Eliminar**. Las copias `*.xlsx` quedan en `Documents/P9_MASIVA_PROTO` (se borran con la carpeta).
