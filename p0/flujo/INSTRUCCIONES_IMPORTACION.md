# P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD — importación

Paquete: `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V2.zip` (raíz del repo). Generador: `python -m p0.flujo.construir`. Definición legible: `p0/flujo/P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_definition.json`.

Power Automate solo orquesta: lee el archivo de OneDrive, hace un POST a P0 (Railway) y guarda lo que P0 devuelve. No recorre ni parsea movimientos. P0 sigue sin guardar nada (sin DB, volumen ni bucket).

## Qué hace

| Paso | Detalle |
|---|---|
| Disparador | OneDrive for Business · *When a file is created* · `/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA` · cada 1 min · concurrencia 1 · solo `.xls`/`.xlsx` (ignora carpetas, `~$*` y otras extensiones) |
| Leer | *Get file content using path* (`triggerOutputs()?['body/Path']`), Infer Content Type = No |
| P0 | `POST https://p0-api-production-dd77.up.railway.app/procesar-extracto` con `{"sede":"CBBA","nombre_archivo":…,"contenido_base64":body('Get_file_content_using_path')?['$content']}` |
| `ok=true` + `publicar_json=true` | Crea `json.nombre` con `json.texto` (sin transformar) en `CARGA_EXTRACTOS_BANCARIOS` → P8 V5 lo toma |
| `ok=true` + `publicar_json=false` | No crea JSON; el original se archiva igual como procesado |
| Original (éxito) | → `PROCESADOS/<periodo.carpeta>` (ej. `2026/10_OCTUBRE`) |
| `ok=false` (HTTP 200) | `<archivo>.error.json` con la respuesta de P0 + original → `ERROR/<periodo.carpeta>` |
| Fallo técnico (sin respuesta, 401, 413, 5xx, fallo al leer, JSON no creado…) | `<archivo>.error.json` `{codigo_error, etapa, mensaje, fecha_hora, archivo, sede}` + original → `ERROR/<año>/<MM_MES>` con hora Bolivia (UTC-4); la ejecución queda en **Failed** para que se vea |
| Nombre repetido | Si ya existe en destino, se inserta `_yyyyMMddTHHmmss` antes de la extensión; nunca se sobrescribe |

Códigos técnicos: `P0_API_NO_DISPONIBLE` (sin respuesta, 408/502/503/504), `P0_API_NO_AUTORIZADO` (401/403), `P0_API_PAYLOAD_EXCEDIDO` (413), `P0_API_SOLICITUD_INVALIDA` (400/422), `P0_API_ERROR_SERVIDOR` (≥500), `P0_API_HTTP_<n>`, `P0_RESPUESTA_INVALIDA` (200 sin `ok` booleano), `P0_JSON_NO_PUBLICADO`, `ORIGEN_NO_LEIDO`, `ERROR_NO_CONTROLADO`.

El original solo se borra de ENTRADA cuando su copia ya existe en destino (copiar → borrar). Si falla antes, el extracto sigue en ENTRADA y la ejecución queda Failed (`ARCHIVO_ORIGINAL_NO_ARCHIVADO`). Los años/meses no se crean por adelantado: existen solo cuando se escribe un archivo en ellos.

## Importar (clic a clic)

1. Power Automate → **My flows** → **Import** → **Import Package (Legacy)** → **Upload** → `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V2.zip`.
2. En *Related resources* → **OneDrive for Business** → **Select during import** → elige tu conexión OneDrive for Business (`gtorricot@univalle.edu`) → **Save** → **Import**.
3. Abre el flujo → **Edit**.

## Único dato manual: el token (`P0_API_TOKEN`)

1. En el flujo, abre la acción **HTTP** → bloque **Headers**.
2. En la fila `Authorization`, el valor es `Bearer <PEGAR_P0_API_TOKEN_AQUI>`. Reemplaza **solo** `<PEGAR_P0_API_TOKEN_AQUI>` por el token real (el valor final es la palabra `Bearer`, un espacio y el token).
3. **Save**. Nunca pegues el token en Git ni en un correo. La acción HTTP ya trae **Secure Inputs/Outputs** activos: el token no se muestra en el historial.

Si pegas mal el token, P0 devolverá 401 y el extracto irá a `ERROR/…` con `P0_API_NO_AUTORIZADO`: no se pierde.
Cuando el flujo viva dentro de una Solution, conviene mover el token a una Environment Variable de tipo *Secret*; este paquete (importación heredada) no puede referenciarla.

## Verificar tras importar (2 minutos)

- **Disparador**: debe mostrar la carpeta `ENTRADA`. El paquete la trae con el formato interno del conector; si el diseñador la marca en rojo o vacía, vuelve a elegirla con el icono de carpeta (`/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA`), *Include subfolders = No*, *Infer Content Type = No*. Es el único punto del flujo que no se pudo comprobar sin tenant.
- **Secure Inputs/Outputs** (⋯ → *Settings*): HTTP (inputs+outputs), Get file content (outputs), Crear_JSON_P7 (inputs), Original_Crear_copia (inputs) y Error_json_Crear (inputs). Power Automate no admite Secure Inputs/Outputs en acciones de variable, Compose, condiciones ni ámbitos, por eso solo esas cinco lo llevan.
- **Concurrency** del disparador = 1 (⋯ → *Settings*).
- Activar el flujo (*Turn on*).

## Prueba mínima en el tenant

1. Suelta `bcp mn.xls` en ENTRADA. Esperado: ejecución *Succeeded*; JSON nuevo en `CARGA_EXTRACTOS_BANCARIOS` (P8 V5 lo procesa); original en `PROCESADOS/2026/10_OCTUBRE/` (o el período que devuelva P0); ENTRADA vacía.
2. Vuelve a soltar el mismo archivo: el original aparece como `bcp mn_<fecha-hora>.xls` en la misma carpeta (no sobrescribe).
3. Para ver el camino de error: cambia temporalmente el token por uno inválido y suelta un archivo → ejecución *Failed* (`P0_API_NO_AUTORIZADO`), original + `.error.json` en `ERROR/<año>/<MM_MES>`. Restituye el token.

Supuestos del conector que se confirman con la primera corrida: que *Create file* de OneDrive crea las carpetas año/mes si no existen (el paquete depende de ello en lugar de una acción «crear carpeta», que el conector no tiene), y que la ruta `Path` del disparador incluye el nombre del archivo.

## No toca

P8 (V5 ya escucha `CARGA_EXTRACTOS_BANCARIOS`), la API de Railway, P7 ni el motor. `p0/flujo/huellas_protegidas.json` fija las huellas SHA-256 de esos archivos y `tests/test_36_flujo_p0_cloud.py` las verifica.
