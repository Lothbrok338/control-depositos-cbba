"""Generador del flujo FINAL `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD` y de su ZIP importable.

    python -m p0.flujo.construir

Power Automate SOLO orquesta; no recorre ni parsea movimientos:

  OneDrive (ENTRADA, .xls/.xlsx) ─► Get file content using path ─► HTTP POST a P0 en Railway (stateless)
      ok=true  ─► (publicar_json=true ─► crea el JSON P7 tal cual en CARGA_EXTRACTOS_BANCARIOS) ─► original a PROCESADOS/YYYY/MM_MES
      ok=false ─► <nombre>.error.json (respuesta de P0) + original a ERROR/YYYY/MM_MES
      fallo técnico (TRY/CATCH) ─► <nombre>.error.json {codigo_error, etapa, mensaje, fecha_hora} + original a ERROR/YYYY/MM_MES

El archivo original solo se borra de ENTRADA cuando su copia ya existe en destino; si algo falla antes, el extracto sigue en ENTRADA.
No toca P8, la API, P7 ni el motor. El token NO está en el repo: va un marcador `<PEGAR_P0_API_TOKEN_AQUI>` (ver INSTRUCCIONES_IMPORTACION.md).
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

from p9.wdl import FALLOS, TODOS, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable

CARPETA_SALIDA = Path(__file__).resolve().parent
RAIZ = CARPETA_SALIDA.parents[1]
NOMBRE_FLUJO = "P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD"
NOMBRE_ZIP = "P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V4.zip"
SPLIT_ON_DISPARADOR = "@triggerOutputs()?['body']"  # el cuerpo de OnNewFilesV2 es un array de BlobMetadata
CAMPOS_DISPARADOR = ("Id", "Name", "Path", "IsFolder")  # BlobMetadata de OnNewFilesV2
DESCRIPCION = ("Extractos bancarios (.xls/.xlsx) en OneDrive ENTRADA -> P0 en Railway -> JSON P7 en CARGA_EXTRACTOS_BANCARIOS; "
               "original a PROCESADOS o ERROR por año/mes. Solo orquesta: no recorre movimientos.")

URL_P0 = "https://p0-api-production-dd77.up.railway.app/procesar-extracto"
SEDE = "CBBA"
MARCADOR_TOKEN = "<PEGAR_P0_API_TOKEN_AQUI>"
BASE = "/CONTROL_DEPOSITOS/P0_EXTRACTOS"
CARPETA_ENTRADA = f"{BASE}/ENTRADA"
CARPETA_PROCESADOS = f"{BASE}/PROCESADOS"
CARPETA_ERROR = f"{BASE}/ERROR"
CARPETA_CARGA = f"{BASE}/CARGA_EXTRACTOS_BANCARIOS"
MESES = {"01": "01_ENERO", "02": "02_FEBRERO", "03": "03_MARZO", "04": "04_ABRIL", "05": "05_MAYO", "06": "06_JUNIO",
         "07": "07_JULIO", "08": "08_AGOSTO", "09": "09_SEPTIEMBRE", "10": "10_OCTUBRE", "11": "11_NOVIEMBRE", "12": "12_DICIEMBRE"}
ZONA_BOLIVIA = "SA Western Standard Time"  # UTC-04:00 sin horario de verano (La Paz)

API_OD = "/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness"
# Carpeta del disparador en el formato interno del conector (ruta con «/» codificada dos veces). Si el diseñador no la reconoce
# al importar, se vuelve a elegir ENTRADA con el selector (ver INSTRUCCIONES_IMPORTACION.md).
FOLDER_ID_ENTRADA = quote(quote(CARPETA_ENTRADA, safe=""), safe="")

# `secureData` solo lo admiten las acciones de conector (OpenApiConnection) y HTTP; Power Automate rechaza el paquete
# (SecureDataPropertyNotSupported) si aparece en SetVariable, Compose, If, Switch, Scope o Terminate.
TIPOS_CON_SECURE_DATA = ("Http", "OpenApiConnection")
SIN_REINTENTO = {"type": "none"}
CON_FALLO = ["Succeeded", "Failed", "TimedOut"]
SEGURO_TODO = {"secureData": {"properties": ["inputs", "outputs"]}}
SEGURO_SALIDA = {"secureData": {"properties": ["outputs"]}}
SEGURO_ENTRADA = {"secureData": {"properties": ["inputs"]}}

ESTADOS = ("PENDIENTE", "PROCESADO", "ERROR_NEGOCIO", "ERROR_TECNICO")
ETAPAS = ("INICIO", "OBTENER_CONTENIDO", "LLAMAR_P0", "EVALUAR_RESPUESTA", "PUBLICAR_JSON")
FECHA_BOLIVIA = f"convertTimeZone(utcNow(),'UTC','{ZONA_BOLIVIA}','yyyy-MM-ddTHH:mm:ss')"
FECHA_HORA_ERROR = f"concat({FECHA_BOLIVIA},'-04:00')"


# ---------------------------------------------------------------------------------------------- helpers
def od(operacion, parametros, reintento=SIN_REINTENTO, seguro=None):
    accion = {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_OD, "connectionName": "shared_onedriveforbusiness", "operationId": operacion},
        "parameters": parametros, "authentication": "@parameters('$authentication')", "retryPolicy": reintento}}
    if seguro:
        accion["runtimeConfiguration"] = seguro
    return accion


def fijar_error(codigo, etapa, mensaje):
    valor = {"codigo_error": codigo, "etapa": etapa, "mensaje": mensaje, "fecha_hora": "@" + FECHA_HORA_ERROR,
             "archivo": "@variables('varNombre')", "sede": "@outputs('PARAM_SEDE')"}
    return asignar("varError", valor)


def codigo_http(sc):
    """Código de error técnico según el HTTP devuelto por Railway (0 = sin respuesta)."""
    return (f"if(contains(createArray(0,408,502,503,504),{sc}),'P0_API_NO_DISPONIBLE',"
            f"if(contains(createArray(401,403),{sc}),'P0_API_NO_AUTORIZADO',"
            f"if(equals({sc},413),'P0_API_PAYLOAD_EXCEDIDO',"
            f"if(contains(createArray(400,422),{sc}),'P0_API_SOLICITUD_INVALIDA',"
            f"if(greaterOrEquals({sc},500),'P0_API_ERROR_SERVIDOR',concat('P0_API_HTTP_',string({sc})))))))")


def _stamp():
    return "formatDateTime(outputs('Ahora_Bolivia'),'yyyyMMddTHHmmss')"


def nombre_unico(prefijo, carpeta, nombre):
    """Calcula `<prefijo>_Nombre_final`: el nombre tal cual si está libre en `carpeta`; si ya existe, le inserta fecha-hora antes de la
    extensión. La consulta de existencia vive en un Scope propio: si el archivo no existe falla (404) y eso se maneja con runAfter."""
    n = f"outputs('{prefijo}_Nombre')"
    punto = f"lastIndexOf({n},'.')"
    final = (f"@if(equals(actions('{prefijo}_Probar_destino')?['status'],'Succeeded'),"
             f"concat(substring({n},0,{punto}),'_',{_stamp()},substring({n},{punto})),{n})")
    consulta = od("GetFileMetadataByPath", {"path": f"@concat({carpeta},'/',{n})"})
    nombre_final = compose(final)
    nombre_final["runAfter"] = {f"{prefijo}_Probar_destino": CON_FALLO}
    return {f"{prefijo}_Nombre": compose("@" + nombre),
            f"{prefijo}_Probar_destino": ambito(secuencia(**{f"{prefijo}_Consultar_destino": consulta})),
            f"{prefijo}_Nombre_final": nombre_final}


# ---------------------------------------------------------------------------------------------- disparador
def disparador():
    """«When a file is created (properties only)» = OnNewFilesV2: devuelve BlobMetadata (Id, Name, Path, IsFolder…), NO el contenido.
    OnNewFileV2 («When a file is created») devuelve el binario y deja Name/IsFolder en null, con lo que el filtro descartaba todo.
    OnNewFilesV2 entrega un ARRAY de BlobMetadata: `splitOn` lo separa y cada ejecución recibe UN elemento, de modo que
    `triggerBody()?['Name']`, `['IsFolder']` y `triggerOutputs()?['body/Path']` se refieren a ese archivo (mismo patrón que P8 V5).
    Las `conditions` se evalúan sobre cada elemento separado. Los únicos campos que usa el flujo están en CAMPOS_DISPARADOR;
    el contenido se lee con Get file content."""
    nombre = "coalesce(triggerBody()?['Name'],'')"
    condicion = (f"@and(not(equals(triggerBody()?['IsFolder'],true)),not(startsWith({nombre},'~$')),"
                 f"or(endsWith(toLower({nombre}),'.xls'),endsWith(toLower({nombre}),'.xlsx')))")
    return {"Cuando_se_crea_un_archivo": {
        "type": "OpenApiConnection", "recurrence": {"interval": 1, "frequency": "Minute"},
        "splitOn": SPLIT_ON_DISPARADOR,
        "inputs": {"host": {"apiId": API_OD, "connectionName": "shared_onedriveforbusiness", "operationId": "OnNewFilesV2"},
                   "parameters": {"folderId": FOLDER_ID_ENTRADA, "includeSubfolders": False},
                   "authentication": "@parameters('$authentication')"},
        "conditions": [{"expression": condicion}],
        "runtimeConfiguration": {"concurrency": {"runs": 1}}}}


# ---------------------------------------------------------------------------------------------- TRY
def llamar_p0():
    return {"type": "Http", "inputs": {
        "method": "POST", "uri": URL_P0,
        "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {MARCADOR_TOKEN}"},
        "body": {"sede": "@outputs('PARAM_SEDE')", "nombre_archivo": "@variables('varNombre')",
                 "contenido_base64": "@body('Get_file_content_using_path')?['$content']"},
        "retryPolicy": {"type": "fixed", "count": 3, "interval": "PT30S"}, "limit": {"timeout": "PT5M"}},
        "runtimeConfiguration": SEGURO_TODO}


def respuesta_ok():
    publicar = secuencia(
        Etapa_PUBLICAR_JSON=asignar("varEtapa", "PUBLICAR_JSON"),
        Crear_JSON_P7=od("CreateFile", {"folderPath": "@outputs('PARAM_CARPETA_CARGA')",
                                        "name": "@body('HTTP')?['json']?['nombre']",
                                        "body": "@body('HTTP')?['json']?['texto']"}, seguro=SEGURO_ENTRADA))
    return secuencia(
        Fijar_periodo_de_la_API=asignar("varPeriodoApi", "@coalesce(body('HTTP')?['periodo']?['carpeta'],'')"),
        Publicar_JSON=si("@equals(body('HTTP')?['publicar_json'],true)", publicar),
        Fijar_estado_PROCESADO=asignar("varEstado", "PROCESADO"))


def respuesta_no_ok():
    return secuencia(
        Fijar_periodo_de_la_API_error=asignar("varPeriodoApi", "@coalesce(body('HTTP')?['periodo']?['carpeta'],'')"),
        Guardar_respuesta_de_P0=asignar("varError", "@body('HTTP')"),
        Fijar_estado_ERROR_NEGOCIO=asignar("varEstado", "ERROR_NEGOCIO"))


def respuesta_invalida():
    return secuencia(
        Fijar_error_respuesta_invalida=fijar_error(
            "P0_RESPUESTA_INVALIDA", "EVALUAR_RESPUESTA",
            "P0 respondió HTTP 200 pero sin el campo booleano ok. Revise la API."),
        Fijar_estado_ERROR_TECNICO_invalida=asignar("varEstado", "ERROR_TECNICO"))


def http_no_200():
    sc = "outputs('HTTP')?['statusCode']"
    return secuencia(
        Fijar_error_http_inesperado=fijar_error(
            "@" + codigo_http(sc), "EVALUAR_RESPUESTA",
            f"@concat('Railway respondió HTTP ',string({sc}),' en lugar de 200.')"),
        Fijar_estado_ERROR_TECNICO_http=asignar("varEstado", "ERROR_TECNICO"))


def cuerpo_try():
    return secuencia(
        Etapa_OBTENER_CONTENIDO=asignar("varEtapa", "OBTENER_CONTENIDO"),
        Get_file_content_using_path=od("GetFileContentByPath", {"path": "@triggerOutputs()?['body/Path']", "inferContentType": False},
                                       seguro=SEGURO_SALIDA),
        Etapa_LLAMAR_P0=asignar("varEtapa", "LLAMAR_P0"),
        HTTP=llamar_p0(),
        Etapa_EVALUAR_RESPUESTA=asignar("varEtapa", "EVALUAR_RESPUESTA"),
        Evaluar_HTTP_200=si(
            "@equals(outputs('HTTP')?['statusCode'],200)",
            secuencia(Evaluar_ok=si(
                "@equals(body('HTTP')?['ok'],true)", respuesta_ok(),
                secuencia(Evaluar_ok_false=si("@equals(body('HTTP')?['ok'],false)", respuesta_no_ok(), respuesta_invalida())))),
            http_no_200()))


# ---------------------------------------------------------------------------------------------- CATCH
def captura_fallos():
    sc = "coalesce(actions('HTTP')?['outputs']?['statusCode'],0)"
    msg = lambda accion: f"take(coalesce(actions('{accion}')?['error']?['message'],'sin detalle'),500)"  # noqa: E731
    detalle_http = ("take(string(coalesce(actions('HTTP')?['outputs']?['body'],actions('HTTP')?['error']?['message'],'sin detalle')),500)")
    casos = {
        "Caso_OBTENER_CONTENIDO": {"case": "OBTENER_CONTENIDO", "actions": secuencia(Error_lectura_origen=fijar_error(
            "ORIGEN_NO_LEIDO", "OBTENER_CONTENIDO",
            f"@concat('No se pudo leer el archivo en OneDrive. ',{msg('Get_file_content_using_path')})"))},
        "Caso_LLAMAR_P0": {"case": "LLAMAR_P0", "actions": secuencia(Error_llamada_p0=fijar_error(
            "@" + codigo_http(sc), "LLAMAR_P0",
            f"@concat(if(equals({sc},0),'Sin respuesta de P0 en Railway (timeout o red). ',concat('Railway respondió HTTP ',string({sc}),'. ')),"
            f"{detalle_http})"))},
        "Caso_PUBLICAR_JSON": {"case": "PUBLICAR_JSON", "actions": secuencia(Error_publicacion_json=fijar_error(
            "P0_JSON_NO_PUBLICADO", "PUBLICAR_JSON",
            f"@concat('No se pudo crear el JSON P7 en CARGA_EXTRACTOS_BANCARIOS. ',{msg('Crear_JSON_P7')})"))}}
    por_defecto = secuencia(Error_no_controlado=fijar_error(
        "ERROR_NO_CONTROLADO", "@variables('varEtapa')", "@concat('Falló la etapa ',variables('varEtapa'),'. Revise el historial del flujo.')"))
    return secuencia(
        Clasificar_fallo_por_etapa={"type": "Switch", "expression": "@variables('varEtapa')", "cases": casos,
                                    "default": {"actions": por_defecto}},
        Fijar_estado_ERROR_TECNICO_catch=asignar("varEstado", "ERROR_TECNICO"))


# ---------------------------------------------------------------------------------------------- archivado final
def periodo_valido(v):
    return (f"and(not(empty({v})),greater(length({v}),6),equals(indexOf({v},'/'),4),equals(length(split({v},'/')),2),"
            f"not(contains({v},'..')),isInt(first(split({v},'/'))))")


def calcular_destino():
    v = "variables('varPeriodoApi')"
    return {
        "Ahora_Bolivia": compose("@" + FECHA_BOLIVIA),
        "Periodo_Bolivia": compose("@concat(formatDateTime(outputs('Ahora_Bolivia'),'yyyy'),'/',"
                                   "outputs('PARAM_MESES')?[formatDateTime(outputs('Ahora_Bolivia'),'MM')])"),
        "Periodo_Carpeta": compose(f"@if({periodo_valido(v)},{v},outputs('Periodo_Bolivia'))"),
        "Carpeta_Destino": compose("@concat(if(equals(variables('varEstado'),'PROCESADO'),outputs('PARAM_CARPETA_PROCESADOS'),"
                                   "outputs('PARAM_CARPETA_ERROR')),'/',outputs('Periodo_Carpeta'))")}


def archivar_error_json():
    acciones = nombre_unico("Error_json", "outputs('Carpeta_Destino')", "concat(variables('varNombre'),'.error.json')")
    acciones["Error_json_Crear"] = od("CreateFile", {
        "folderPath": "@outputs('Carpeta_Destino')", "name": "@outputs('Error_json_Nombre_final')",
        "body": "@string(variables('varError'))"}, seguro=SEGURO_ENTRADA)
    return secuencia(**acciones)


def archivar_original():
    acciones = nombre_unico("Original", "outputs('Carpeta_Destino')", "variables('varNombre')")
    copiar_y_borrar = secuencia(
        Original_Crear_copia=od("CreateFile", {"folderPath": "@outputs('Carpeta_Destino')", "name": "@outputs('Original_Nombre_final')",
                                               "body": "@body('Get_file_content_using_path')"}, seguro=SEGURO_ENTRADA),
        Original_Borrar_de_ENTRADA=od("DeleteFile", {"id": "@variables('varIdOrigen')"},
                                      reintento={"type": "fixed", "count": 2, "interval": "PT5S"}))
    mover = secuencia(Original_Mover_sin_contenido=od("MoveFile", {
        "id": "@variables('varIdOrigen')",
        "destination": "@concat(outputs('Carpeta_Destino'),'/',outputs('Original_Nombre_final'))", "overwrite": False}))
    acciones["Original_Hay_contenido"] = si("@equals(actions('Get_file_content_using_path')?['status'],'Succeeded')", copiar_y_borrar, mover)
    return secuencia(**acciones)


def bloque_archivar():
    """ERROR: primero el .error.json (crea año/mes si faltan), después el original. PROCESADOS: solo el original."""
    return secuencia(
        Escribir_error_json=si("@not(equals(variables('varEstado'),'PROCESADO'))", archivar_error_json()),
        Archivar_original=ambito(archivar_original()))


def construir_definicion():
    acciones = secuencia(
        PARAM_SEDE=compose(SEDE),
        PARAM_CARPETA_PROCESADOS=compose(CARPETA_PROCESADOS),
        PARAM_CARPETA_ERROR=compose(CARPETA_ERROR),
        PARAM_CARPETA_CARGA=compose(CARPETA_CARGA),
        PARAM_MESES=compose(MESES),
        Inicializar_varNombre=variable("varNombre", "string", "@coalesce(triggerOutputs()?['body/Name'],'')"),
        Inicializar_varIdOrigen=variable("varIdOrigen", "string", "@string(coalesce(triggerOutputs()?['body/Id'],''))"),
        Inicializar_varEtapa=variable("varEtapa", "string", "INICIO"),
        Inicializar_varEstado=variable("varEstado", "string", "PENDIENTE"),
        Inicializar_varPeriodoApi=variable("varPeriodoApi", "string", ""),
        Inicializar_varError=variable("varError", "object", {}),
        TRY=ambito(cuerpo_try()))
    acciones["CATCH"] = ambito(captura_fallos(), {"TRY": FALLOS})
    destino = secuencia(**calcular_destino())
    destino["Ahora_Bolivia"]["runAfter"] = {"TRY": TODOS, "CATCH": TODOS}
    acciones.update(destino)
    acciones["ARCHIVAR"] = ambito(bloque_archivar(), {"Carpeta_Destino": ["Succeeded"]})
    acciones["ARCHIVAR_FALLO"] = {"type": "Terminate", "runAfter": {"ARCHIVAR": FALLOS}, "inputs": {
        "runStatus": "Failed", "runError": {
            "code": "ARCHIVO_ORIGINAL_NO_ARCHIVADO",
            "message": "No se pudo archivar el extracto original; sigue en ENTRADA (o ya fue copiado a destino). Revise el historial."}}}
    acciones["CERRAR"] = si(
        "@not(or(equals(variables('varEstado'),'PROCESADO'),equals(variables('varEstado'),'ERROR_NEGOCIO')))",
        secuencia(Terminar_con_error_tecnico={"type": "Terminate", "inputs": {"runStatus": "Failed", "runError": {
            "code": "@coalesce(variables('varError')?['codigo_error'],'ERROR_NO_CONTROLADO')",
            "message": "@concat('Extracto movido a ERROR. Etapa: ',coalesce(variables('varError')?['etapa'],'?'))"}}}))
    acciones["CERRAR"]["runAfter"] = {"ARCHIVAR": ["Succeeded"]}
    return definicion(disparador(), acciones)


# ---------------------------------------------------------------------------------------------- paquete ZIP
FECHA_ZIP = (2026, 10, 8, 0, 0, 0)
CLAVE_CONEXION = "shared_onedriveforbusiness"
MARCADOR_CONEXION = "<CONEXION_ONEDRIVEFORBUSINESS>"


def _uuid(parte):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p0:{NOMBRE_FLUJO}:{parte}"))


def archivos_paquete(definition):
    flujo, interno, api, conexion = _uuid("resource"), _uuid("definition"), _uuid("onedrive:api"), _uuid("onedrive:connection")
    recursos = {
        flujo: {"type": "Microsoft.Flow/flows", "suggestedCreationType": "New", "creationType": "New, Update",
                "details": {"displayName": NOMBRE_FLUJO}, "configurableBy": "User", "hierarchy": "Root", "dependsOn": [api, conexion]},
        api: {"id": API_OD, "name": CLAVE_CONEXION, "type": "Microsoft.PowerApps/apis", "suggestedCreationType": "Existing",
              "details": {"displayName": "OneDrive for Business"}, "configurableBy": "System", "hierarchy": "Child", "dependsOn": []},
        conexion: {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing", "creationType": "Existing",
                   "details": {"displayName": MARCADOR_CONEXION}, "configurableBy": "User", "hierarchy": "Child", "dependsOn": [api]}}
    envoltura = {"name": interno, "id": f"/providers/Microsoft.Flow/flows/{interno}", "type": "Microsoft.Flow/flows",
                 "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows", "displayName": NOMBRE_FLUJO,
                                "definition": definition,
                                "connectionReferences": {CLAVE_CONEXION: {
                                    "connectionName": MARCADOR_CONEXION, "source": "Embedded", "id": API_OD, "tier": "NotSpecified",
                                    "apiName": "onedriveforbusiness", "isProcessSimpleApiReferenceConversionAlreadyDone": False}},
                                "flowFailureAlertSubscribed": False, "isManaged": False}}
    base = f"Microsoft.Flow/flows/{flujo}"
    return {
        "manifest.json": {"schema": "1.0", "details": {
            "displayName": NOMBRE_FLUJO, "description": DESCRIPCION, "createdTime": "2026-10-08T00:00:00Z",
            "packageTelemetryId": _uuid("telemetry"), "creator": "N/A", "sourceEnvironment": ""}, "resources": recursos},
        "Microsoft.Flow/flows/manifest.json": {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [flujo]}},
        f"{base}/apisMap.json": {CLAVE_CONEXION: api}, f"{base}/connectionsMap.json": {CLAVE_CONEXION: conexion},
        f"{base}/definition.json": envoltura}


def zip_bytes(definition) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta, contenido in archivos_paquete(definition).items():
            info = zipfile.ZipInfo(ruta, date_time=FECHA_ZIP)
            info.create_system, info.compress_type, info.external_attr = 3, zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, json.dumps(contenido, ensure_ascii=False, separators=(",", ":")))
    return buffer.getvalue()


PATRONES_PROTEGIDOS = ("p8/**/*", "P8_*.zip", "ENTREGABLES_P8_CONTROL_DEPOSITOS_CBBA.zip", "motor_control_depositos_cbba.py", "motor_generico.py",
                       "adaptador_m365.py", "captura_origen.py", "deteccion_registro.py", "historico.py", "registro_bancos.json",
                       "esquema_parse_json_p7.json", "ejemplos_p7/**/*", "ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md",
                       "p0/api.py", "p0/nucleo.py", "p0/sedes.json", "Dockerfile", ".dockerignore", "railway.json", "requirements-p0.txt")


def huellas_protegidas():
    """SHA-256 de P8, P7, motor y la API P0 (Railway): este flujo no los modifica; un test las vuelve a calcular."""
    import hashlib
    archivos = {p for patron in PATRONES_PROTEGIDOS for p in RAIZ.glob(patron) if p.is_file() and "__pycache__" not in p.parts}
    return {str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(archivos)}


def generar_huellas():
    destino = CARPETA_SALIDA / "huellas_protegidas.json"
    destino.write_text(json.dumps(huellas_protegidas(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return destino


def generar():
    d = construir_definicion()
    (CARPETA_SALIDA / f"{NOMBRE_FLUJO}_definition.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destino = RAIZ / NOMBRE_ZIP
    destino.write_bytes(zip_bytes(d))
    return destino, contar_acciones(d["actions"])


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["huellas"]:  # solo cuando se confirma que P8/API/P7/motor cambiaron A PROPÓSITO en otra tarea
        print(generar_huellas())
        raise SystemExit
    ruta, n = generar()
    print(ruta, f"({n} acciones)")
