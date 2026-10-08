# P0 · Automatización de la entrada de extractos (API en Railway + Power Automate)

**Resumen.** Gabriel deja extractos en `ENTRADA`. Un flujo de Power Automate los detecta y los envía a una **API Python sin estado en Railway**, que ejecuta el motor bancario y P7 que ya existían y devuelve el JSON. El flujo guarda ese JSON en `CARGA_EXTRACTOS_BANCARIOS` (donde escucha P8 V5) y mueve el extracto original a `PROCESADOS/AAAA/MM_MES` o `ERROR/AAAA/MM_MES`. **Railway no guarda nada** y no depende de ningún equipo personal.

```
SharePoint/OneDrive  CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA/<extracto>.xls|xlsx     ← único paso manual de Gabriel
   │  Power Automate (flujo P0): detecta el archivo y obtiene su contenido binario
   ▼  HTTP POST  https://<servicio>.up.railway.app/procesar-extracto   (Bearer token)
Railway · API P0 (sin estado, en memoria/temporal, se borra al terminar)
   │  detección P4 → motor_control_depositos_cbba.ejecutar_motor → adaptador_m365.adaptar (P7)
   ▼  respuesta: { ok, json.texto = DEPOSITOS_ACTIVOS__P7-….json, banco, movimientos, periodo AAAA/MM_MES }
Power Automate
   ├─ ok: guarda json.texto en  P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS/  →  P8 V5  →  Depositos_Activos
   │      y mueve el original a  PROCESADOS/AAAA/MM_MES/
   └─ error: guarda <archivo>.error.json y mueve el original a  ERROR/AAAA/MM_MES/
```

Estructura de carpetas (la maneja Power Automate; la API no ve SharePoint):

```
CONTROL_DEPOSITOS/P0_EXTRACTOS/
├── ENTRADA/                       plana
├── PROCESADOS/AAAA/MM_MES/        p. ej. PROCESADOS/2026/10_OCTUBRE/
├── ERROR/AAAA/MM_MES/             el original y su <archivo>.error.json
└── CARGA_EXTRACTOS_BANCARIOS/     los DEPOSITOS_ACTIVOS__*.json que escucha P8
```

`MM_MES`: 01_ENERO … 12_DICIEMBRE (nombres fijos). La API devuelve en cada respuesta el `periodo` de la fecha de procesamiento en hora de la sede (America/La_Paz), p. ej. `"carpeta": "2026/10_OCTUBRE"`, para que el flujo no tenga que calcularlo; en diciembre→enero cambia sola a `2027/01_ENERO`.

## 1. Qué cambió respecto del P0 local anterior

* **Eliminado:** el orquestador local que vigilaba carpetas del disco (`python -m p0`, `p0/__main__.py`), sus candados, `PROCESADOS/ERROR` en disco, `--documentos`, la dependencia de OneDrive sincronizado y `tests/test_34_orquestador_p0.py`.
* **Reutilizado (el código del orquestador pasó a `p0/nucleo.py`):** las etapas de detección → motor → P7, la traducción de errores del motor a códigos, el registro de bancos por sede, `procesar archivo por archivo`, la regla de no entregar un extracto con filas inválidas para P7.
* **Nuevo:** `p0/api.py` (FastAPI), `Dockerfile`, `.dockerignore`, `requirements-p0.txt`, `railway.json`, `tests/test_35_api_p0.py`.
* **Sin cambios:** motor bancario (salvo el control del año ya hecho antes, ver §8), P7, P8, `registro_bancos.json`, lógica de duplicados.

## 2. Contrato de `POST /procesar-extracto`

**Autenticación:** cabecera `Authorization: Bearer <P0_API_TOKEN>`. Sin la variable `P0_API_TOKEN` (≥ 16 caracteres) en el servidor, la API rechaza todo con 503 (falla cerrada). `GET /health` no pide token.

**Petición (recomendada para Power Automate): `Content-Type: application/json`**

```json
{ "sede": "CBBA", "nombre_archivo": "bcp_me_1.xls", "contenido_base64": "<Base64 del .xls/.xlsx>" }
```

También se acepta `multipart/form-data` con los campos `sede` y `archivo` (y opcional `nombre_archivo`). Máximo `P0_MAX_BYTES` (30 MB por defecto) → 413.

**Respuesta de éxito — HTTP 200, `ok: true`:**

```json
{
  "ok": true, "resultado": "PROCESADO", "version": "P0-API-1", "sede": "CBBA",
  "archivo": { "nombre": "bcp_me_1.xls", "sha256": "…", "bytes": 50688 },
  "deteccion": { "banco": "BCP", "cuenta_id": "BCP_ME", "moneda": "USD", "formato": "BCP_EXTRACTO_V1" },
  "movimientos": 8,
  "publicar_json": true,
  "json": { "nombre": "DEPOSITOS_ACTIVOS__P7-ad0542d8a88a.json", "lote_id": "P7-ad0542d8a88a",
            "sha256": "…", "bytes": 7830, "texto": "<contenido exacto del JSON de P7 (UTF-8)>" },
  "periodo": { "anio": 2026, "mes": "10_OCTUBRE", "carpeta": "2026/10_OCTUBRE" },
  "procesado_en": "2026-10-08T10:19:28-04:00", "duracion_ms": 1294
}
```

`json.texto` es **byte a byte la salida de `adaptador_m365.adaptar`** (P7): es lo que el flujo debe guardar como archivo, sin volver a serializarlo. Si el extracto es válido pero no tiene movimientos: `movimientos: 0`, `publicar_json: false`, `json: null` y `advertencia` (no hay nada que cargar; el original se archiva en PROCESADOS).

**Respuesta de error de negocio — HTTP 200, `ok: false`** (el extracto se rechazó; el flujo lo manda a ERROR):

```json
{
  "ok": false, "resultado": "ERROR", "version": "P0-API-1", "sede": "CBBA",
  "etapa": "DETECCION", "codigo_error": "CUENTA_NO_REGISTRADA",
  "mensaje": "CUENTA_NO_REGISTRADA: formato BNB_EXTRACTO_V1 reconocido, pero la cuenta '****9999' de la cabecera no está registrada…",
  "archivo": { "nombre": "…", "sha256": "…", "bytes": 1234 }, "deteccion": null,
  "periodo": { "anio": 2026, "mes": "10_OCTUBRE", "carpeta": "2026/10_OCTUBRE" },
  "procesado_en": "…", "duracion_ms": 311
}
```

Los números de cuenta de los mensajes salen enmascarados (`****9999`) y no se incluyen tablas de saldos ni filas del extracto.

**Errores de la propia API** (mismo cuerpo `ok:false`, `etapa: "API"`, sin `archivo`):

| HTTP | `codigo_error` | Cuándo |
|---|---|---|
| 400 | `SOLICITUD_INVALIDA`, `CONTENIDO_INVALIDO`, `SEDE_DESCONOCIDA` | JSON/multipart mal formado, Base64 inválido, sede inexistente |
| 401 | `NO_AUTORIZADO` | token ausente o incorrecto |
| 413 | `ARCHIVO_DEMASIADO_GRANDE` | supera `P0_MAX_BYTES` |
| 500 | `ERROR_INESPERADO` / `CONFIGURACION_INVALIDA` | fallo interno (el mensaje solo trae el tipo de excepción) |
| 503 | `API_NO_CONFIGURADA` | falta `P0_API_TOKEN` |

Códigos de negocio (`ok:false`, HTTP 200):

| `codigo_error` | Etapa | Significado |
|---|---|---|
| `EXTENSION_NO_SOPORTADA`, `ARCHIVO_VACIO` | ARCHIVO | No es .xls/.xlsx o está vacío |
| `ARCHIVO_ILEGIBLE` | DETECCION | Corrupto o no es un Excel real |
| `SIN_FORMATO`, `NO_RECONOCIDO`, `RECHAZADO`, `ENCABEZADO_INCOMPLETO`, `SIN_CUENTA`, `AMBIGUO` | DETECCION | No coincide con un formato bancario del registro (p. ej. el reporte «Últimos 12 movimientos» de Unión) |
| `CUENTA_NO_REGISTRADA` | DETECCION | Formato reconocido pero la cuenta no está registrada para la sede |
| `SALDOS_NO_CUADRAN`, `AUDITORIA_ESTRUCTURAL`, `ANIO_FUERA_DE_RANGO`, `NORMALIZACION_FALLIDA`, `FALLO_MOTOR` | MOTOR | El motor bloqueó la exportación |
| `ARCHIVO_EXCLUIDO_POR_NOMBRE` | MOTOR | El nombre contiene `NORMALIZADO` o parece salida del sistema (el motor lo ignora) |
| `P7_CONTRATO`, `P7_FILAS_INVALIDAS` | P7 | Contrato de 26 columnas roto, o P7 marcó filas inválidas (no se entrega un extracto incompleto) |

## 3. Sin estado y sin contenido bancario en logs

* No hay base de datos, volumen ni bucket. Cada solicitud escribe el archivo en un directorio temporal propio (`tempfile.TemporaryDirectory`) que se **elimina siempre** (éxito, error o excepción). Ni el extracto ni el JSON se guardan; viven solo en la respuesta.
* **Logs** (`registrar_tecnico`, único punto de logging): `archivo`, `sha` (12 caracteres), `etapa`, `banco`, `filas`, `resultado`, `codigo`, `ms`. Nunca movimientos, números de cuenta completos, claves, descripciones, mensajes de error del motor ni JSON. Una excepción inesperada se registra y se responde solo con el nombre de su tipo. Probado en `tests/test_35_api_p0.py`.
* Una solicitud a la vez por proceso (el motor cambia una variable de entorno y redirige `stdout` por corrida): `--workers 1` más un candado. Si hace falta más caudal, se suben réplicas de Railway (cada una sin estado).
* Trazabilidad histórica: el original queda en `PROCESADOS`; los históricos normalizados los generará y archivará P10.

## 4. Despliegue en Railway (paso a paso)

No se creó ningún recurso en Railway. Usa un proyecto **nuevo** (no mezclar con `CAJAS-GABO-DEV`).

1. En Railway: **New Project → Deploy from GitHub repo** → `Lothbrok338/control-depositos-cbba` → rama `experiment/p9-masiva-prototipo` (más adelante, la rama definitiva). Railway detecta el `Dockerfile` de la raíz y `railway.json` (builder Dockerfile, healthcheck `/health`).
2. **No** agregues base de datos, volumen ni bucket.
3. Servicio → **Variables → New Variable**: `P0_API_TOKEN` = un secreto largo aleatorio, generado por ti, p. ej. `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Guárdalo también para Power Automate. (Opcional: `P0_MAX_BYTES`.) No lo pongas en el repositorio.
4. Servicio → **Settings → Networking → Generate Domain**. Anota la URL `https://<servicio>.up.railway.app`.
5. Espera a que el despliegue quede *Active* y comprueba en el navegador: `https://<servicio>.up.railway.app/health` → `{"status":"ok","servicio":"p0-extractos",…}`.
6. Prueba la API con un extracto pequeño (desde tu equipo; el token solo en tu terminal):
   `curl -s -X POST https://<servicio>.up.railway.app/procesar-extracto -H "Authorization: Bearer <TOKEN>" -F sede=CBBA -F archivo=@bcp_me_1.xls | head -c 600`
   Debe devolver `"ok":true,"movimientos":8`.
7. El servicio fija `TZ` a UTC-4 para que `FECHA DE CARGA` quede en hora de Bolivia (defecto D-15 del motor: usa la hora de la máquina).

## 5. Flujo de Power Automate (paso a paso)

> **Paquete listo para importar:** `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V4.zip` (generador `p0/flujo/construir.py`, guía `p0/flujo/INSTRUCCIONES_IMPORTACION.md`). Implementa este §5 con **OneDrive for Business** en lugar de SharePoint; abajo queda la descripción manual de referencia.

Nombre sugerido: `P0_INGESTA_EXTRACTOS_CBBA`. **No** se construyó ni importó nada en el tenant; los nombres exactos de acciones pueden variar según el idioma del diseñador y deben verificarse en la primera armada.

1. **Disparador:** SharePoint → *Cuando se crea un archivo (solo propiedades)* → sitio y biblioteca de `CONTROL_DEPOSITOS`, carpeta `…/P0_EXTRACTOS/ENTRADA`. En **⋯ → Configuración → Control de simultaneidad: Activado, grado 1**. En **Condiciones del desencadenador** agrega:
   `@and(equals(triggerBody()?['{IsFolder}'],false), or(endsWith(toLower(triggerBody()?['{FilenameWithExtension}']),'.xls'), endsWith(toLower(triggerBody()?['{FilenameWithExtension}']),'.xlsx')))`
2. **Ámbito `PROCESAR`** (Control → Ámbito) con:
   1. SharePoint → *Obtener contenido del archivo* → Identificador de archivo: `Identificador` del disparador; **Inferir tipo de contenido: No**. En **⋯ → Configuración**: *Entradas/Salidas seguras: Activado*.
   2. **HTTP** → Método `POST`, URI `https://<servicio>.up.railway.app/procesar-extracto`, Encabezados: `Authorization` = `Bearer <TOKEN>` (guárdalo como *variable de entorno de la solución* de tipo secreto, no en texto), `Content-Type` = `application/json`. Cuerpo:
      ```
      {
        "sede": "CBBA",
        "nombre_archivo": "@{triggerBody()?['{FilenameWithExtension}']}",
        "contenido_base64": "@{body('Obtener_contenido_del_archivo')?['$content']}"
      }
      ```
      **⋯ → Configuración:** *Entradas/Salidas seguras: Activado* (así el contenido bancario no queda en el historial de ejecuciones), *Tiempo de espera* `PT5M`, *Directiva de reintentos* fija: 3 reintentos, intervalo `PT30S` (es seguro reintentar: la API no tiene estado y P8 evita duplicados).
   3. **Condición** `@equals(body('HTTP')?['ok'], true)`.
      * **Sí:** Condición `@equals(body('HTTP')?['publicar_json'], true)` → **Sí:** SharePoint → *Crear archivo* en `…/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS`, Nombre `@{body('HTTP')?['json']?['nombre']}`, Contenido `@{body('HTTP')?['json']?['texto']}`. (Entradas seguras activadas.) Después, en ambos casos, **archivar en PROCESADOS** (paso 4 con `@{body('HTTP')?['periodo']?['carpeta']}`).
      * **No:** SharePoint → *Crear archivo* en `…/P0_EXTRACTOS/ERROR/@{body('HTTP')?['periodo']?['carpeta']}`, Nombre `@{triggerBody()?['{FilenameWithExtension}']}.error.json`, Contenido `@{string(body('HTTP'))}`; y **mover a ERROR** (paso 4).
3. **Ámbito `CATCH`** (*Configurar ejecución posterior*: solo si `PROCESAR` **falló** o **expiró**; cubre Railway caído, 401, 413, 500): calcula la carpeta con `@{formatDateTime(convertTimeZone(utcNow(),'UTC','SA Western Standard Time'),'yyyy')}/@{split('01_ENERO,02_FEBRERO,03_MARZO,04_ABRIL,05_MAYO,06_JUNIO,07_JULIO,08_AGOSTO,09_SEPTIEMBRE,10_OCTUBRE,11_NOVIEMBRE,12_DICIEMBRE',',')[sub(int(formatDateTime(convertTimeZone(utcNow(),'UTC','SA Western Standard Time'),'MM')),1)]}`; crea `<archivo>.error.json` con `{"ok":false,"etapa":"API","codigo_error":"P0_API_NO_DISPONIBLE","mensaje":"La API no respondió o rechazó la solicitud"}` y mueve el original a ERROR (paso 4).
4. **Archivar el original** (PROCESADOS o ERROR): crear la carpeta del año y la del mes (SharePoint → *Crear nueva carpeta*; configura la acción siguiente para ejecutarse **tanto si esta tuvo éxito como si falló**, porque puede fallar cuando la carpeta ya existe), copiar el archivo al destino `…/PROCESADOS/AAAA/MM_MES/` (o `ERROR/…`) y **eliminar el archivo de ENTRADA** solo después de que la copia haya tenido éxito. Si tu conector ofrece *Mover archivo*, úsalo en su lugar.
5. **P8 V5** debe escuchar la carpeta nueva: Power Automate → flujo V5 → editar → disparador → *Carpeta* → `/Documents/CONTROL_DEPOSITOS/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS` (hoy escucha `/Documents/P8_PILOTO`).

Nota: la API ya no resuelve la colisión de nombres en `PROCESADOS`/`ERROR` (no ve las carpetas). Si el mismo nombre de archivo puede llegar dos veces el mismo mes, añade un prefijo de fecha al nombre archivado (`@{formatDateTime(utcNow(),'yyyyMMdd_HHmmss')}__<nombre>`); el nombre original sigue quedando en `ARCHIVO ORIGEN` de los datos, porque la API recibe el original.

## 6. Duplicados y repetidos

Sin cambios: el mismo extracto (o dos que se solapan) genera un JSON más y **P8 evita duplicados con `CLAVE_TRANSACCION`**. Cada extracto es una solicitud independiente: un archivo malo no afecta a los demás.

## 7. Varias sedes

Un solo motor y una sola API. `sede` viaja en cada solicitud; `p0/sedes.json` define por sede `zona_horaria`, `cuentas` (`"TODAS"` o lista de ids del registro) y `cuentas_adicionales` (archivo con entradas propias de `CUENTAS`). La API construye el registro efectivo (formatos comunes + cuentas de la sede) en el directorio temporal de la solicitud. CBBA usa `registro_bancos.json` tal cual. Una cuenta de otra sede sale como `CUENTA_NO_REGISTRADA`. Cada sede tendrá su flujo de Power Automate (con su `sede` y sus carpetas). Pendiente (no hecho): flujo P8 por sede y un registro de cuentas fuera de `registro_bancos.json` cuando sean muchas.

## 8. Año ya no fijo en 2026

El control del paso 6 del motor protegía contra fechas mal leídas, no contra «otro año de trabajo». Regla actual (`anios_fuera_de_rango`): cada año debe estar en **[`ANIO_MINIMO_DATOS` (2026, primer año de operación; no vence), año de la fecha del servidor]**. 2027, 2028… son válidos cuando el reloj ya está en ese año y un extracto que cruza diciembre/enero también. Fuera de rango → `ANIO_FUERA_DE_RANGO`.

## 9. Lo que NO se validó

* No se desplegó nada en Railway ni se tocó el tenant. No se pudo construir la imagen (el entorno de trabajo no tiene demonio de Docker). Sí se arrancó la API real con `uvicorn` desde una carpeta que contiene **solo** los archivos que copia el `Dockerfile`, y respondió `/health` y un extracto real de prueba por HTTP.
* No se probó el flujo de Power Automate: la expresión `body('Obtener_contenido_del_archivo')?['$content']` (Base64 del binario con *Inferir tipo de contenido: No*), la creación de carpetas de año/mes y el borrado del original deben confirmarse en la primera ejecución real.
* Las pruebas de duplicados usan el flujo P8 V5 con SharePoint **simulado**.
* P8.5 / `control_origen` sigue fuera. El zip de V5 versionado sigue apuntando a `/Documents/P8_PILOTO` (se edita en el tenant, §5.5).

## 10. Pruebas

`pytest -m p0` (`tests/test_33_anio_dinamico_p0.py`, `tests/test_35_api_p0.py`).
