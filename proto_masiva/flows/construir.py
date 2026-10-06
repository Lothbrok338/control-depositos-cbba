"""Generador del flujo PROTOTIPO DIRECTO `P9_MASIVA_PROTO_PREVALIDAR` y de su ZIP importable.

    python -m proto_masiva.flows.construir

Camino directo y síncrono, SIN listas, SIN lotes, SIN estados persistentes, SIN sondeo:

  Power Apps ──(XLSX)──► flujo: valida el archivo → crea una COPIA TEMPORAL en una carpeta → lee tblConfirmacionMasiva con
  Excel Online → valida estructura → BORRA la copia → responde a Power Apps (resultado, mensaje, filas_leidas, tiempos).

No toca Depositos_Activos. Solo usa una carpeta de biblioteca (copia temporal) y Excel Online. La respuesta lleva los tiempos por
etapa para MEDIR en el tenant; el flujo NO fija ningún límite de filas (PARAM_MAX_FILAS = 0), salvo detectar que la lectura alcanzó el
umbral de paginación configurado para no devolver un recuento truncado.

Operaciones ya validadas en tu tenant por flujos anteriores: disparador Power Apps V2 + Response PowerApp (P9_ASIGNAR_DEPOSITO V4.2).
NO validadas todavía en tenant (nombres internos de memoria; ver flows/INSTRUCCIONES_FLUJO.md): entrada de tipo File del disparador,
CreateFile, DeleteFile y Excel Online GetItems.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path

from p9.wdl import FALLOS, TODOS, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable
from proto_masiva.contrato_plantilla import ENCABEZADOS, NOMBRE_TABLA as TABLA

CARPETA_SALIDA = Path(__file__).resolve().parent
NOMBRE_FLUJO = "P9_MASIVA_PROTO_PREVALIDAR"
SITIO = "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu"
CARPETA_TEMP = "/Documents/P9_MASIVA_TEMP"
PLACEHOLDER_UBICACION = "<CONFIGURAR_UBICACION_EXCEL>"
PLACEHOLDER_BIBLIOTECA = "<CONFIGURAR_BIBLIOTECA_EXCEL>"
API_SP = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
API_XL = "/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness"
PAGINACION = 2000   # umbral de paginación de la lectura de Excel (config.); si la lectura lo alcanza se avisa en vez de contar de menos
MAX_FILAS = 0       # 0 = sin tope. Se fijará SOLO después de medir en el tenant (MEDICION_TENANT.md)

SALIDAS = ("resultado", "codigo", "mensaje", "archivo", "tabla_encontrada", "filas_leidas", "copia_temporal_eliminada", "tiempos_ms")
CODIGOS = ("OK", "ARCHIVO_VACIO", "ESTRUCTURA_INVALIDA", "TABLA_NO_ENCONTRADA", "ARCHIVO_BLOQUEADO", "ERROR_LECTURA_EXCEL",
           "SIN_ARCHIVO", "NO_ES_XLSX", "ERROR_COPIA_ARCHIVO", "DEMASIADAS_FILAS", "ERROR_NO_CONTROLADO")


# ---------------------------------------------------------------------------------------------- helpers
def _sp(operacion, parametros, **extra):
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": operacion},
        "parameters": parametros, "authentication": "@parameters('$authentication')", **extra}}


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


def _ms(final, inicio):
    return f"div(sub({final},{inicio}),10000)"


# ---------------------------------------------------------------------------------------------- flujo
def disparador():
    """Power Apps (V2) con UNA entrada de tipo Archivo (File): la app la llama con un registro {name, contentBytes}."""
    archivo = {"title": "file", "type": "object", "x-ms-dynamically-added": True,
               "description": "Archivo XLSX seleccionado en la app", "x-ms-content-hint": "FILE",
               "properties": {"name": {"type": "string"}, "contentBytes": {"type": "string", "format": "byte"}}}
    return {"manual": {"type": "Request", "kind": "PowerAppV2", "inputs": {"schema": {
        "type": "object", "properties": {"file": archivo}, "required": ["file"]}}}}


def leer_y_clasificar():
    """Después de copiar el archivo: lee la tabla y decide el resultado de negocio."""
    sin_datos = "and(" + ",".join(_vacia(h) for h in ENCABEZADOS) + ")"
    cantidad_ok = secuencia(
        Hay_tope=si("@and(greater(outputs('PARAM_MAX_FILAS'),0),greater(outputs('Cantidad_con_datos'),outputs('PARAM_MAX_FILAS')))",
                    fijar("Resultado_DEMASIADAS_FILAS_MAX", "ERROR", "DEMASIADAS_FILAS",
                          "@concat('El archivo tiene ',string(outputs('Cantidad_con_datos')),' filas y el máximo permitido es ',"
                          "string(outputs('PARAM_MAX_FILAS')),'. Divida el archivo.')", "SI", "@outputs('Cantidad_con_datos')"),
                    fijar("Resultado_OK", "COMPLETADO", "OK", "Archivo leído correctamente", "SI", "@outputs('Cantidad_con_datos')")))
    estructura_ok = secuencia(
        Filas_con_datos={"type": "Query", "inputs": {"from": "@outputs('Filas_brutas')", "where": f"@not({sin_datos})"}},
        Cantidad_con_datos=compose("@length(body('Filas_con_datos'))"),
        Hay_datos=si("@greater(outputs('Cantidad_con_datos'),0)", cantidad_ok,
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
    con_filas = secuencia(
        Limite_de_lectura=si("@greaterOrEquals(length(outputs('Filas_brutas')),outputs('PARAM_PAGINACION'))",
                             fijar("Resultado_DEMASIADAS_FILAS_LECTURA", "ERROR", "DEMASIADAS_FILAS",
                                   "@concat('La lectura alcanzó el límite de ',string(outputs('PARAM_PAGINACION')),"
                                   "' filas: el recuento podría estar incompleto. Divida el archivo.')", "SI", 0),
                             revisar_encabezados))
    return secuencia(
        Etapa_excel=asignar("varEtapa", "EXCEL"),
        Leer_tabla_Excel={"type": "OpenApiConnection", "inputs": {
            "host": {"apiId": API_XL, "connectionName": "shared_excelonlinebusiness", "operationId": "GetItems"},
            "parameters": {"source": PLACEHOLDER_UBICACION, "drive": PLACEHOLDER_BIBLIOTECA,
                           "file": "@body('Crear_archivo')?['Id']", "table": TABLA},
            "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "none"}},
            "runtimeConfiguration": {"paginationPolicy": {"minimumItemCount": PAGINACION}}},
        Filas_brutas=compose("@coalesce(body('Leer_tabla_Excel')?['value'],createArray())"),
        Hay_filas=si("@greater(length(outputs('Filas_brutas')),0)", con_filas,
                     fijar("Resultado_TABLA_SIN_FILAS", "ERROR", "ARCHIVO_VACIO",
                           "La tabla no tiene filas. Complete la plantilla y vuelva a intentar.", "SI", 0)))


def flujo_valido():
    return secuencia(
        Etapa_copia=asignar("varEtapa", "COPIA"),
        Nombre_copia=compose("@concat('TMP_',guid(),'.xlsx')"),
        Crear_archivo=_sp("CreateFile", {
            "dataset": "@outputs('PARAM_SITIO')", "folderPath": "@outputs('PARAM_CARPETA')",
            "name": "@outputs('Nombre_copia')", "body": "@base64ToBinary(outputs('Entrada')?['base64'])"},
            retryPolicy={"type": "none"}),
        Guardar_id_de_la_copia=asignar("varArchivoId", "@string(body('Crear_archivo')?['Id'])"),
        Marca_T1=asignar("varT1", "@ticks(utcNow())"),
        **_encadenar(leer_y_clasificar(), "Marca_T1"),
        Marca_T2=asignar("varT2", "@ticks(utcNow())"))


def cuerpo_principal():
    return secuencia(Entrada_valida=si(
        "@empty(outputs('Validar_entrada'))", flujo_valido(),
        secuencia(Entrada_invalida=si(
            "@equals(outputs('Validar_entrada'),'SIN_ARCHIVO')",
            fijar("Resultado_SIN_ARCHIVO", "ERROR", "SIN_ARCHIVO", "No se recibió ningún archivo. Adjunte el Excel y vuelva a intentar."),
            fijar("Resultado_NO_ES_XLSX", "ERROR", "NO_ES_XLSX", "El archivo no es .xlsx. Use la plantilla oficial.")))))


def captura_fallos():
    """CATCH: clasifica solo con lo que sabemos que corrió (varEtapa). Códigos HTTP del conector Excel: a confirmar en tenant."""
    estado_excel = "outputs('Leer_tabla_Excel')?['statusCode']"
    detalle = "take(coalesce(outputs('Leer_tabla_Excel')?['body']?['error']?['message'],''),200)"
    excel = si(f"@equals({estado_excel},404)",
               fijar("Fallo_TABLA_NO_ENCONTRADA", "ERROR", "TABLA_NO_ENCONTRADA",
                     f"No se encontró la tabla {TABLA} en el archivo. Use la plantilla oficial.", "NO", 0),
               secuencia(Fallo_excel_no_404=si(
                   f"@equals({estado_excel},423)",
                   fijar("Fallo_ARCHIVO_BLOQUEADO", "ERROR", "ARCHIVO_BLOQUEADO", "El archivo está bloqueado. Ciérrelo e intente de nuevo."),
                   fijar("Fallo_ERROR_LECTURA_EXCEL", "ERROR", "ERROR_LECTURA_EXCEL",
                         f"@concat('No se pudo leer el Excel (HTTP ',string({estado_excel}),'). ',{detalle})"))))
    return secuencia(Clasificar_fallo=si(
        "@equals(variables('varEtapa'),'EXCEL')", secuencia(Fallo_en_excel=excel),
        secuencia(Fallo_no_excel=si(
            "@equals(variables('varEtapa'),'COPIA')",
            fijar("Fallo_ERROR_COPIA", "ERROR", "ERROR_COPIA_ARCHIVO", "No se pudo crear la copia temporal del archivo."),
            fijar("Fallo_ERROR_NO_CONTROLADO", "ERROR", "ERROR_NO_CONTROLADO",
                  "Error inesperado al procesar el archivo. Vuelva a intentar o avise al administrador.")))))


def construir_definicion(max_filas=MAX_FILAS):
    acciones = secuencia(
        PARAM_SITIO=compose(SITIO),
        PARAM_CARPETA=compose(CARPETA_TEMP),
        PARAM_ENCABEZADOS=compose(list(ENCABEZADOS)),
        PARAM_PAGINACION=compose(PAGINACION),
        PARAM_MAX_FILAS=compose(max_filas),
        Entrada=compose({"nombre": "@trim(coalesce(triggerBody()?['file']?['name'],''))",
                         "base64": "@coalesce(triggerBody()?['file']?['contentBytes'],'')"}),
        Inicializar_varT0=variable("varT0", "integer", "@ticks(utcNow())"),
        Inicializar_varT1=variable("varT1", "integer", 0),
        Inicializar_varT2=variable("varT2", "integer", 0),
        Inicializar_varT3=variable("varT3", "integer", 0),
        Inicializar_varT4=variable("varT4", "integer", 0),
        Inicializar_varEtapa=variable("varEtapa", "string", "ENTRADA"),
        Inicializar_varArchivoId=variable("varArchivoId", "string", ""),
        Inicializar_varBorrada=variable("varBorrada", "string", "NO_APLICA"),
        Inicializar_varResultado=variable("varResultado", "object", resultado(
            "ERROR", "ERROR_NO_CONTROLADO", "El archivo no se procesó. Vuelva a intentar.")),
        Validar_entrada=compose(
            "@if(or(empty(outputs('Entrada')?['nombre']),empty(outputs('Entrada')?['base64'])),'SIN_ARCHIVO',"
            "if(not(endsWith(toLower(outputs('Entrada')?['nombre']),'.xlsx')),'NO_ES_XLSX',''))"),
        TRY=ambito(cuerpo_principal()),
    )
    acciones["CATCH"] = ambito(captura_fallos(), {"TRY": FALLOS})
    # Limpieza: borra la copia temporal si se creó, pase lo que pase. Un fallo aquí NO cambia el resultado: solo se informa.
    acciones["LIMPIEZA"] = ambito(secuencia(Hay_copia_temporal=si(
        "@not(empty(variables('varArchivoId')))",
        secuencia(Borrar_copia_temporal=_sp("DeleteFile", {"dataset": "@outputs('PARAM_SITIO')", "id": "@variables('varArchivoId')"},
                                            retryPolicy={"type": "fixed", "count": 2, "interval": "PT5S"}),
                  Marcar_borrada=asignar("varBorrada", "SI")))), {"TRY": TODOS, "CATCH": TODOS})
    acciones["LIMPIEZA_FALLO"] = ambito(secuencia(Marcar_no_borrada=asignar("varBorrada", "NO")), {"LIMPIEZA": FALLOS})
    acciones["Marca_T3"] = asignar("varT3", "@ticks(utcNow())")
    acciones["Marca_T3"]["runAfter"] = {"LIMPIEZA": TODOS, "LIMPIEZA_FALLO": TODOS}
    acciones["Marca_T4"] = asignar("varT4", "@ticks(utcNow())")
    acciones["Marca_T4"]["runAfter"] = {"Marca_T3": ["Succeeded"]}
    t = lambda n: f"variables('varT{n}')"  # noqa: E731
    acciones["Tiempos"] = compose(
        "@concat('crear=',string(if(greater(" + t(1) + ",0)," + _ms(t(1), t(0)) + ",0)),"
        "';excel=',string(if(greater(" + t(2) + ",0)," + _ms(t(2), t(1)) + ",0)),"
        "';borrar=',string(if(greater(" + t(3) + ",0)," + _ms(t(3), f"max({t(2)},{t(1)},{t(0)})") + ",0)),"
        "';total=',string(" + _ms(t(4), t(0)) + "))")
    acciones["Tiempos"]["runAfter"] = {"Marca_T4": ["Succeeded"]}
    cuerpo = {"resultado": "@variables('varResultado')?['estado']", "codigo": "@variables('varResultado')?['codigo']",
              "mensaje": "@variables('varResultado')?['mensaje']", "archivo": "@outputs('Entrada')?['nombre']",
              "tabla_encontrada": "@variables('varResultado')?['tabla']",
              "filas_leidas": "@string(variables('varResultado')?['filas'])",
              "copia_temporal_eliminada": "@variables('varBorrada')", "tiempos_ms": "@outputs('Tiempos')"}
    esquema = {"type": "object", "properties": {k: {"title": k, "type": "string", "x-ms-dynamically-added": True} for k in SALIDAS}}
    acciones["Responder_a_PowerApps"] = {"type": "Response", "kind": "PowerApp", "runAfter": {"Tiempos": TODOS},
                                         "inputs": {"statusCode": 200, "body": cuerpo, "schema": esquema}}
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
            "displayName": NOMBRE_FLUJO, "description": "PROTOTIPO directo: recibe un XLSX, lee tblConfirmacionMasiva y responde. Sin listas ni lotes. No toca Depositos_Activos.",
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
