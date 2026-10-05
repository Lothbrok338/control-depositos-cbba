"""Generador del flujo PROTOTIPO `P9_MASIVA_PROTO_PREVALIDAR` y de su ZIP importable.

    python -m proto_masiva.flows.construir

Arquitectura (la única): la app crea el lote con el XLSX adjunto -> pone ESTADO = PENDIENTE -> este flujo
(disparado al modificarse un elemento con ESTADO = PENDIENTE) -> PROCESANDO -> COMPLETADO | ERROR -> la app
sondea la lista. NO usa «Respuesta temprana». NO toca Depositos_Activos ni ninguna lista de producción.

Reutiliza (solo lectura) los helpers WDL de p9/wdl.py. Operaciones ya validadas en el tenant por flujos P8/P9:
HttpRequest (SharePoint), GetOnNewItems/GetOnNewFileItems, GetFileContent. NO validadas todavía en tenant (nombres
internos tomados de memoria; ver flows/INSTRUCCIONES_FLUJO.md): GetOnUpdatedItems, GetAttachments,
GetAttachmentContent, CreateFile, Excel Online GetItems.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path

from p9.wdl import FALLOS, TODOS, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable
from proto_masiva.generar_plantillas import ENCABEZADOS, TABLA

CARPETA_SALIDA = Path(__file__).resolve().parent
NOMBRE_FLUJO = "P9_MASIVA_PROTO_PREVALIDAR"
SITIO = "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu"
LISTA = "P9_MASIVA_PROTO_LOTES"
CARPETA_TEMP = "/Documents/P9_MASIVA_PROTO"
PLACEHOLDER_UBICACION = "<CONFIGURAR_UBICACION_EXCEL>"
PLACEHOLDER_BIBLIOTECA = "<CONFIGURAR_BIBLIOTECA_EXCEL>"
API_SP = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
API_XL = "/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness"
MAX_FILAS_PAGINACION = 2000

ESTADOS_TERMINALES = ("COMPLETADO", "ERROR")
# Columnas de P9_MASIVA_PROTO_LOTES que este flujo escribe (todas deben existir en sharepoint/esquema_*.json).
CAMPOS_ESCRITOS = ("ESTADO", "MENSAJE", "CODIGO_RESULTADO", "TABLA_ENCONTRADA", "FILAS_LEIDAS", "FECHA_ESTADO",
                   "ARCHIVO_NOMBRE")
CODIGOS = ("OK", "ARCHIVO_VACIO", "ESTRUCTURA_INVALIDA", "TABLA_NO_ENCONTRADA", "ARCHIVO_BLOQUEADO", "ERROR_LECTURA_EXCEL",
           "SIN_ADJUNTO", "NO_ES_XLSX", "ERROR_ADJUNTO", "ERROR_COPIA_ARCHIVO", "ERROR_NO_CONTROLADO")


# ---------------------------------------------------------------------------------------------- helpers
def _sp(operacion, parametros, **extra):
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": operacion},
        "parameters": parametros, "authentication": "@parameters('$authentication')", **extra}}


def _uri_lote(sufijo=""):
    return ("@concat('_api/web/lists/GetByTitle(''',outputs('PARAM_LISTA'),''')/items(',"
            f"string(outputs('Lote')?['id']),')'{',' + sufijo if sufijo else ''})")


def _escribir_lote(cuerpo):
    """MERGE sobre el lote. `IF-MATCH: *` SOLO aquí: es la lista de estado del prototipo, de un único escritor
    (este flujo). Nunca se usa en Depositos_Activos. Idempotente, por eso admite 2 reintentos fijos."""
    return _sp("HttpRequest", {
        "dataset": "@outputs('PARAM_SITIO')", "parameters/method": "POST", "parameters/uri": _uri_lote(),
        "parameters/headers": {"Accept": "application/json;odata=nometadata",
                               "Content-Type": "application/json;odata=nometadata",
                               "X-HTTP-Method": "MERGE", "IF-MATCH": "*"},
        "parameters/body": f"@string(outputs('{cuerpo}'))"},
        retryPolicy={"type": "fixed", "count": 2, "interval": "PT5S"})


def resultado(estado, codigo, mensaje, tabla="", filas=0):
    return {"estado": estado, "codigo": codigo, "mensaje": mensaje, "tabla": tabla, "filas": filas}


def fijar(nombre, estado, codigo, mensaje, tabla="", filas=0):
    return secuencia(**{nombre: asignar("varResultado", resultado(estado, codigo, mensaje, tabla, filas))})


def _encadenar(acciones, previa):
    """`secuencia` deja la primera acción de un bloque con runAfter vacío; al incrustar el bloque tras `previa` hay que enlazarla."""
    primera = next(iter(acciones))
    assert acciones[primera]["runAfter"] == {}
    acciones[primera]["runAfter"] = {previa: ["Succeeded"]}
    return acciones


def _vacia(campo):
    return f"empty(item()?['{campo}'])"


# ---------------------------------------------------------------------------------------------- flujo
def disparador():
    return {"Cuando_un_lote_queda_PENDIENTE": {
        "type": "OpenApiConnection", "recurrence": {"frequency": "Minute", "interval": 1},
        "splitOn": "@triggerOutputs()?['body/value']",
        "inputs": {"host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": "GetOnUpdatedItems"},
                   "parameters": {"dataset": SITIO, "table": LISTA}, "authentication": "@parameters('$authentication')"},
        "conditions": [{"expression": "@equals(triggerBody()?['ESTADO'],'PENDIENTE')"}],
        "runtimeConfiguration": {"concurrency": {"runs": 1}}}}


def leer_y_clasificar():
    """Después de copiar el archivo: lee la tabla y decide el resultado de negocio."""
    sin_datos = "and(" + ",".join(_vacia(h) for h in ENCABEZADOS) + ")"
    estructura_ok = secuencia(
        Filas_con_datos={"type": "Query", "inputs": {"from": "@outputs('Filas_brutas')", "where": f"@not({sin_datos})"}},
        Cantidad_con_datos=compose("@length(body('Filas_con_datos'))"),
        Hay_datos=si("@greater(outputs('Cantidad_con_datos'),0)",
                     fijar("Resultado_OK", "COMPLETADO", "OK", "Archivo leído correctamente", "SI",
                           "@outputs('Cantidad_con_datos')"),
                     fijar("Resultado_ARCHIVO_VACIO", "ERROR", "ARCHIVO_VACIO",
                           "La tabla no tiene filas con datos. Complete la plantilla y vuelva a intentar.", "SI", 0)))
    revisar_encabezados = secuencia(
        Encabezados_faltantes={"type": "Query", "inputs": {
            "from": "@outputs('PARAM_ENCABEZADOS')", "where": "@not(contains(first(outputs('Filas_brutas')),item()))"}},
        Estructura=si("@greater(length(body('Encabezados_faltantes')),0)",
                      fijar("Resultado_ESTRUCTURA_INVALIDA", "ERROR", "ESTRUCTURA_INVALIDA",
                            "@concat('Faltan o cambiaron encabezados: ',join(body('Encabezados_faltantes'),', '),"
                            "'. Use la plantilla oficial.')", "SI", 0),
                      estructura_ok))
    return secuencia(
        Etapa_excel=asignar("varEtapa", "EXCEL"),
        Leer_tabla_Excel={"type": "OpenApiConnection", "inputs": {
            "host": {"apiId": API_XL, "connectionName": "shared_excelonlinebusiness", "operationId": "GetItems"},
            "parameters": {"source": PLACEHOLDER_UBICACION, "drive": PLACEHOLDER_BIBLIOTECA,
                           "file": "@body('Crear_archivo')?['Id']", "table": TABLA},
            "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "none"}},
            "runtimeConfiguration": {"paginationPolicy": {"minimumItemCount": MAX_FILAS_PAGINACION}}},
        Filas_brutas=compose("@coalesce(body('Leer_tabla_Excel')?['value'],createArray())"),
        Hay_filas=si("@greater(length(outputs('Filas_brutas')),0)", revisar_encabezados,
                     fijar("Resultado_TABLA_SIN_FILAS", "ERROR", "ARCHIVO_VACIO",
                           "La tabla no tiene filas. Complete la plantilla y vuelva a intentar.", "SI", 0)))


def cuerpo_principal():
    con_adjunto = secuencia(
        Adjunto=compose("@first(body('Obtener_adjuntos'))"),
        Nombre_adjunto=compose("@coalesce(outputs('Adjunto')?['DisplayName'],outputs('Adjunto')?['Name'],'')"),
        Guardar_nombre=asignar("varArchivo", "@outputs('Nombre_adjunto')"),
        Es_xlsx=si("@endsWith(toLower(outputs('Nombre_adjunto')),'.xlsx')", secuencia(
            Etapa_contenido=asignar("varEtapa", "CONTENIDO"),
            Obtener_contenido_adjunto=_sp("GetAttachmentContent", {
                "dataset": "@outputs('PARAM_SITIO')", "table": "@outputs('PARAM_LISTA')",
                "id": "@outputs('Lote')?['id']", "attachmentId": "@outputs('Adjunto')?['Id']"}),
            Etapa_copia=asignar("varEtapa", "COPIA"),
            Nombre_copia=compose("@concat(outputs('Lote')?['uid'],'_',formatDateTime(utcNow(),'yyyyMMddHHmmss'),'.xlsx')"),
            Crear_archivo=_sp("CreateFile", {
                "dataset": "@outputs('PARAM_SITIO')", "folderPath": "@outputs('PARAM_CARPETA')",
                "name": "@outputs('Nombre_copia')", "body": "@body('Obtener_contenido_adjunto')"}),
            **_encadenar(leer_y_clasificar(), "Crear_archivo")),
            fijar("Resultado_NO_ES_XLSX", "ERROR", "NO_ES_XLSX", "El archivo adjunto no es .xlsx. Use la plantilla oficial.")))
    return secuencia(
        Etapa_adjuntos=asignar("varEtapa", "ADJUNTOS"),
        Obtener_adjuntos=_sp("GetAttachments", {
            "dataset": "@outputs('PARAM_SITIO')", "table": "@outputs('PARAM_LISTA')", "id": "@outputs('Lote')?['id']"}),
        Hay_adjunto=si("@greater(length(body('Obtener_adjuntos')),0)", con_adjunto,
                       fijar("Resultado_SIN_ADJUNTO", "ERROR", "SIN_ADJUNTO",
                             "El lote no tiene archivo adjunto. Adjunte el Excel y vuelva a intentar.")))


def captura_fallos():
    """CATCH: clasifica solo con lo que sabemos que corrió (varEtapa). Códigos HTTP del conector Excel: a confirmar en tenant."""
    estado_excel = "outputs('Leer_tabla_Excel')?['statusCode']"
    detalle = ("take(coalesce(outputs('Leer_tabla_Excel')?['body']?['error']?['message'],''),200)")
    excel = si(f"@equals({estado_excel},404)",
               fijar("Fallo_TABLA_NO_ENCONTRADA", "ERROR", "TABLA_NO_ENCONTRADA",
                     f"No se encontró la tabla {TABLA} en el archivo. Use la plantilla oficial.", "NO", 0),
               secuencia(Fallo_excel_no_404=si(
                   f"@equals({estado_excel},423)",
                   fijar("Fallo_ARCHIVO_BLOQUEADO", "ERROR", "ARCHIVO_BLOQUEADO",
                         "El archivo está bloqueado. Ciérrelo e intente de nuevo."),
                   fijar("Fallo_ERROR_LECTURA_EXCEL", "ERROR", "ERROR_LECTURA_EXCEL",
                         f"@concat('No se pudo leer el Excel (HTTP ',string({estado_excel}),'). ',{detalle})"))))
    def etapa_es(valor):
        return f"@equals(variables('varEtapa'),'{valor}')"
    return secuencia(Clasificar_fallo=si(
        etapa_es("EXCEL"), secuencia(Fallo_en_excel=excel),
        secuencia(Fallo_no_excel=si(
            etapa_es("COPIA"), fijar("Fallo_ERROR_COPIA", "ERROR", "ERROR_COPIA_ARCHIVO",
                                     "No se pudo copiar el archivo a la carpeta temporal."),
            secuencia(Fallo_no_copia=si(
                f"@or(equals(variables('varEtapa'),'ADJUNTOS'),equals(variables('varEtapa'),'CONTENIDO'))",
                fijar("Fallo_ERROR_ADJUNTO", "ERROR", "ERROR_ADJUNTO", "No se pudo leer el archivo adjunto del lote."),
                fijar("Fallo_ERROR_NO_CONTROLADO", "ERROR", "ERROR_NO_CONTROLADO",
                      "Error inesperado al procesar el lote. Vuelva a intentar o avise al administrador.")))))))


def construir_definicion():
    acciones = secuencia(
        PARAM_SITIO=compose(SITIO),
        PARAM_LISTA=compose(LISTA),
        PARAM_CARPETA=compose(CARPETA_TEMP),
        PARAM_ENCABEZADOS=compose(list(ENCABEZADOS)),
        Lote=compose({"id": "@coalesce(triggerBody()?['ID'],0)",
                      "uid": "@coalesce(triggerBody()?['LOTE_UID'],concat('LOTE-',string(coalesce(triggerBody()?['ID'],0))))"}),
        Inicializar_varEtapa=variable("varEtapa", "string", "INICIO"),
        Inicializar_varArchivo=variable("varArchivo", "string", ""),
        Inicializar_varResultado=variable("varResultado", "object", resultado(
            "ERROR", "ERROR_NO_CONTROLADO", "El lote no se procesó. Vuelva a intentar.")),
        Cuerpo_procesando=compose({"ESTADO": "PROCESANDO", "MENSAJE": "Procesando el archivo...", "CODIGO_RESULTADO": "",
                                   "TABLA_ENCONTRADA": "", "FILAS_LEIDAS": 0, "FECHA_ESTADO": "@utcNow()"}),
        Marcar_PROCESANDO=_escribir_lote("Cuerpo_procesando"),
        TRY=ambito(cuerpo_principal()),
    )
    acciones["CATCH"] = ambito(captura_fallos(), {"TRY": FALLOS})
    acciones["Cuerpo_final"] = compose({
        "ESTADO": "@variables('varResultado')?['estado']", "MENSAJE": "@variables('varResultado')?['mensaje']",
        "CODIGO_RESULTADO": "@variables('varResultado')?['codigo']",
        "TABLA_ENCONTRADA": "@variables('varResultado')?['tabla']", "FILAS_LEIDAS": "@variables('varResultado')?['filas']",
        "FECHA_ESTADO": "@utcNow()",
        "ARCHIVO_NOMBRE": "@if(empty(variables('varArchivo')),coalesce(triggerBody()?['ARCHIVO_NOMBRE'],''),variables('varArchivo'))"})
    acciones["Cuerpo_final"]["runAfter"] = {"TRY": TODOS, "CATCH": TODOS}
    acciones["Escribir_resultado"] = _escribir_lote("Cuerpo_final")
    acciones["Escribir_resultado"]["runAfter"] = {"Cuerpo_final": ["Succeeded"]}
    return definicion(disparador(), acciones)


# ---------------------------------------------------------------------------------------------- paquete ZIP
CONEXIONES = {"shared_sharepointonline": ("SharePoint", "sharepointonline"),
              "shared_excelonlinebusiness": ("Excel Online (Business)", "excelonlinebusiness")}
FECHA_ZIP = (2026, 10, 5, 0, 0, 0)


def _uuid(parte):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p9:masiva-proto:{NOMBRE_FLUJO}:{parte}"))


def archivos_paquete(definition):
    flujo, interno = _uuid("resource"), _uuid("definition")
    recursos, referencias, apis, conexiones, dependencias = {}, {}, {}, {}, []
    for clave, (titulo, nombre_api) in CONEXIONES.items():
        api_id = f"/providers/Microsoft.PowerApps/apis/{clave}"
        r_api, r_con = _uuid(clave + ":api"), _uuid(clave + ":connection")
        dependencias += [r_api, r_con]
        recursos[r_api] = {"id": api_id, "name": clave, "type": "Microsoft.PowerApps/apis", "suggestedCreationType": "Existing",
                           "details": {"displayName": titulo}, "configurableBy": "System", "hierarchy": "Child", "dependsOn": []}
        recursos[r_con] = {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing",
                           "creationType": "Existing", "details": {"displayName": f"<CONEXION_{clave.upper()}>"},
                           "configurableBy": "User", "hierarchy": "Child", "dependsOn": [r_api]}
        referencias[clave] = {"connectionName": f"<CONEXION_{clave.upper()}>", "source": "Embedded", "id": api_id,
                              "tier": "NotSpecified", "apiName": nombre_api,
                              "isProcessSimpleApiReferenceConversionAlreadyDone": False}
        apis[clave], conexiones[clave] = r_api, r_con
    recursos[flujo] = {"type": "Microsoft.Flow/flows", "suggestedCreationType": "New", "creationType": "New, Update",
                       "details": {"displayName": NOMBRE_FLUJO}, "configurableBy": "User", "hierarchy": "Root",
                       "dependsOn": dependencias}
    envoltura = {"name": interno, "id": f"/providers/Microsoft.Flow/flows/{interno}", "type": "Microsoft.Flow/flows",
                 "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows", "displayName": NOMBRE_FLUJO,
                                "definition": definition, "connectionReferences": referencias,
                                "flowFailureAlertSubscribed": False, "isManaged": False}}
    base = f"Microsoft.Flow/flows/{flujo}"
    return {
        "manifest.json": {"schema": "1.0", "details": {
            "displayName": NOMBRE_FLUJO, "description": "PROTOTIPO: lee el XLSX adjunto de un lote y cuenta filas. No toca Depositos_Activos.",
            "createdTime": "2026-10-05T00:00:00Z", "packageTelemetryId": _uuid("telemetry"), "creator": "N/A",
            "sourceEnvironment": ""}, "resources": recursos},
        "Microsoft.Flow/flows/manifest.json": {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [flujo]}},
        f"{base}/apisMap.json": apis, f"{base}/connectionsMap.json": conexiones, f"{base}/definition.json": envoltura}


def zip_bytes(definition) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta, contenido in archivos_paquete(definition).items():
            info = zipfile.ZipInfo(ruta, date_time=FECHA_ZIP)
            info.create_system, info.compress_type, info.external_attr = 3, zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, json.dumps(contenido, ensure_ascii=False, separators=(",", ":")))
    return buffer.getvalue()


def generar():
    d = construir_definicion()
    (CARPETA_SALIDA / f"{NOMBRE_FLUJO}_definition.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destino = CARPETA_SALIDA / f"{NOMBRE_FLUJO}.zip"
    destino.write_bytes(zip_bytes(d))
    return destino, contar_acciones(d["actions"])


if __name__ == "__main__":
    ruta, n = generar()
    print(ruta, f"({n} acciones)")
