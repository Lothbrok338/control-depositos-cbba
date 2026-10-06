# Importar y revisar el flujo PROTOTIPO `P9_MASIVA_PROTO_PREVALIDAR` (camino directo)

Qué hace, de principio a fin y **sin guardar nada**:

```
Power Apps ──XLSX──► [valida nombre/extensión] → [crea copia TMP_<guid>.xlsx en Documents/P9_MASIVA_TEMP]
                     → [Excel Online: lee tblConfirmacionMasiva] → [valida estructura y cuenta filas]
                     → [BORRA la copia, pase lo que pase] → responde a Power Apps
```

Respuesta (todo texto): `resultado` (`COMPLETADO`/`ERROR`), `codigo`, `mensaje`, `archivo`, `tabla_encontrada`, `filas_leidas`, `copia_temporal_eliminada` (`SI`/`NO`/`NO_APLICA`) y `tiempos_ms` (`crear=…;excel=…;borrar=…;total=…`, para medir). Si falla el borrado de la copia, el resultado de negocio **no cambia**: solo se informa.

No hay listas, lotes, estados, sondeo ni respuesta anticipada: la app espera la respuesta del flujo. El flujo no toca `Depositos_Activos`.

Archivos: `construir.py` (generador), `P9_MASIVA_PROTO_PREVALIDAR_definition.json`, `P9_MASIVA_PROTO_PREVALIDAR.zip` (paquete heredado, mismo formato que los ZIP P8/P9 ya importados).

## Antes: crear la carpeta temporal

`sharepoint/INSTRUCCIONES_VEHICULO.md` §2 (`Documents/P9_MASIVA_TEMP`).

## 1 · Importar

1. Power Automate → **Mis flujos → Importar → Importar paquete (heredado)** → sube el ZIP.
2. *Contenido del paquete* → la acción del flujo → **Crear como nuevo**. En las dos conexiones (SharePoint, Excel Online (Business)) → **Seleccionar al importar** → tu conexión.
3. **Importar**. Queda apagado o con avisos: sigue el paso 2.

## 2 · Revisar 4 puntos (obligatorio la primera vez)

Estos nombres de operación y la forma de la entrada de archivo **no están validados en tu tenant**: los tomé de memoria porque `learn.microsoft.com` está bloqueado desde el entorno donde construí el flujo. El disparador Power Apps (V2) y la acción *Respuesta a Power Apps* sí son los mismos que usa la V4.2 validada. Si un paso aparece con ⚠ o parámetros vacíos, **vuelve a seleccionar sus campos con los desplegables**; la lógica no cambia.

| # | Dónde | Qué comprobar / elegir |
|---|---|---|
| 1 | Disparador *Power Apps (V2)* | Debe tener **una** entrada de tipo **Archivo (File)** llamada `file`. Si no la reconoce: borra la entrada y créala con *Agregar una entrada → Archivo*. Las acciones leen `triggerBody()?['file']?['name']` y `…['contentBytes']` (contenido en base64) |
| 2 | `Crear_archivo` | Carpeta = `/Documents/P9_MASIVA_TEMP`; nombre = salida de `Nombre_copia`; contenido = `base64ToBinary(…contentBytes…)` (tal como está) |
| 3 | `Leer_tabla_Excel` | **Ubicación** y **Biblioteca de documentos**: reemplaza `<CONFIGURAR_UBICACION_EXCEL>` / `<CONFIGURAR_BIBLIOTECA_EXCEL>` eligiendo OneDrive for Business y su biblioteca (el sitio de P9 es tu OneDrive). **Archivo** = contenido dinámico `Id` de `Crear_archivo`. **Tabla** = escribe `tblConfirmacionMasiva` (valor personalizado). En **⋯ → Configuración**: *Paginación* activada con umbral **2000**; *Directiva de reintentos* = Ninguna |
| 4 | `Borrar_copia_temporal` | Sitio y **Identificador de archivo** = la variable `varArchivoId` (el `Id` de la copia). Reintentos: *Intervalo fijo, 2, PT5S* |

Si al cambiar Ubicación/Biblioteca se borran Archivo/Tabla, vuelve a ponerlos como dice la tabla.

## 3 · Guardar y dejar encendido

**Guardar**, sin avisos, flujo **Activado**. En Power Apps: *Power Automate → Agregar flujo → P9_MASIVA_PROTO_PREVALIDAR*.

## Parámetros del flujo (acciones `PARAM_…` al inicio)

| Parámetro | Valor | Significado |
|---|---|---|
| `PARAM_CARPETA` | `/Documents/P9_MASIVA_TEMP` | Carpeta de la copia temporal |
| `PARAM_PAGINACION` | `2000` | Debe ser igual al umbral de paginación de `Leer_tabla_Excel`. Si la lectura **alcanza** ese número, el flujo responde `DEMASIADAS_FILAS` en vez de devolver un recuento posiblemente truncado |
| `PARAM_MAX_FILAS` | `0` | **0 = sin tope.** Aquí se fija el máximo de filas por archivo si las mediciones muestran tiempos de espera reales. No se ha fijado ningún valor porque aún no se ha medido |

## Si falla la importación: armarlo a mano (≈ 14 acciones)

Mismo orden que `P9_MASIVA_PROTO_PREVALIDAR_definition.json`: (1) disparador Power Apps V2 con entrada Archivo; (2) validar nombre `.xlsx`; (3) *Crear archivo* con el contenido; (4) *Enumerar filas presentes en una tabla* (`tblConfirmacionMasiva`, paginación 2000); (5) comprobar filas, encabezados (los 9) y filas con datos; (6) *Eliminar archivo* **en un ámbito que se ejecute siempre** (con éxito o con fallo); (7) *Respuesta a Power Apps* con las 8 salidas de texto.

## Qué mirar en la primera prueba con `03_SIN_TABLA.xlsx`

Esperado: `ERROR / TABLA_NO_ENCONTRADA`. Si aparece `ERROR_LECTURA_EXCEL (HTTP 400…)`, el conector responde 400 y no 404 cuando falta la tabla: en el ámbito `CATCH`, acción `Fallo_en_excel`, cambia `equals(statusCode, 404)` por `or(equals(…,400),equals(…,404))`. El mensaje ya trae el HTTP y el texto del error para decidirlo.

## Eliminar al terminar

Power Automate → Mis flujos → `P9_MASIVA_PROTO_PREVALIDAR` → ⋯ → **Desactivar** y luego **Eliminar**.
