"""Generador del flujo PROTOTIPO DIRECTO `P9_MASIVA_PROTO_PREVALIDAR` y de su ZIP importable.

    python -m proto_masiva.flows.construir

Camino directo y síncrono, SIN lotes, SIN estados persistentes, SIN sondeo:

  Power Apps ──(XLSX)──► flujo: valida el archivo → crea una COPIA TEMPORAL en una carpeta → lee tblConfirmacionMasiva con
  Excel Online → valida estructura → PREVALIDA CADA FILA contra Depositos_Activos (SOLO LECTURA, un único GET) → BORRA la copia →
  responde a Power Apps (resumen + detalle_json por fila + tiempos).

PREVALIDACIÓN REAL (flows/prevalidacion.py, ../PREVALIDACION_REAL.md): lee Depositos_Activos con UN GET (CRÉDITO + ventana de la galería
individual) y resuelve las filas en memoria. NO escribe en Depositos_Activos (ni MERGE, ni POST, ni ETag): la confirmación futura releerá
cada depósito por ID y obtendrá su ETag fresco. La respuesta lleva los tiempos por etapa para MEDIR en el tenant; el flujo NO fija ningún
límite de filas (PARAM_MAX_FILAS = 0), salvo detectar que la lectura alcanzó el umbral de paginación configurado para no devolver un
recuento truncado.

Validado en el tenant (ver ESTADO_CHECKPOINT_TENANT.md): disparador Power Apps V2 con UNA entrada de tipo File (`file`), CreateFile,
Excel Online GetItems sobre tblConfirmacionMasiva y Response PowerApp: el Ejemplo de 3 filas devolvió COMPLETADO / 3 filas leídas.
Observado y NO resuelto: DeleteFile responde HTTP 423 (Locked) porque Excel Online retiene la copia; quedan TMP_*.xlsx en la carpeta
temporal y el flujo lo informa en `copia_temporal_eliminada = NO` sin cambiar el resultado de negocio. Este generador NO incluye el
Delay de 10 s que se probó a mano en el tenant (no resolvió el 423).

Excel Online en el tenant: Location = SITIO (valor real, ver más abajo); Document Library = «OneDrive» (se elige en el diseñador:
su identificador interno es opaco y no se versiona, por eso `PLACEHOLDER_BIBLIOTECA` es el único marcador que queda);
File = Id dinámico de Crear_archivo; Table = tblConfirmacionMasiva.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path

from p9.wdl import FALLOS, TODOS, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable
from proto_masiva.contrato_plantilla import ENCABEZADOS, NOMBRE_TABLA as TABLA
from proto_masiva.flows import prevalidacion as PV

CARPETA_SALIDA = Path(__file__).resolve().parent
NOMBRE_FLUJO = "P9_MASIVA_PROTO_PREVALIDAR"
SITIO = "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu"
# Nueva estructura física de P9 en el OneDrive (los recursos se movieron DESPUÉS de generar los primeros paquetes): Documents/CONTROL_DEPOSITOS/P9/.
# ÚNICA fuente de la carpeta temporal: la usan TRES flujos (esta prevalidación para sus TMP_*.xlsx, y confirmación/estado para confirmacion_<uid>.json).
RAIZ_P9 = "/Documents/CONTROL_DEPOSITOS/P9"
CARPETA_TEMP = f"{RAIZ_P9}/P9_MASIVA_TEMP"
CARPETA_TEMP_ANTIGUA = "/Documents/P9_MASIVA_TEMP"   # ruta ANTERIOR a la reorganización: ningún artefacto debe volver a contenerla (test_10)
UBICACION_EXCEL = SITIO   # «Location» de Excel Online en el tenant: el sitio personal (OneDrive for Business). VALIDADO en tenant
PLACEHOLDER_BIBLIOTECA = "<CONFIGURAR_BIBLIOTECA_EXCEL>"   # «Document Library» = OneDrive: se elige en el diseñador (id interno opaco)
API_SP = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
API_XL = "/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness"
PAGINACION = 2000   # umbral de paginación de la lectura de Excel (config.); si la lectura lo alcanza se avisa en vez de contar de menos
MAX_FILAS = 0       # 0 = sin tope. Se fijará SOLO después de medir en el tenant (MEDICION_TENANT.md)

SALIDAS = ("resultado", "codigo", "mensaje", "archivo", "tabla_encontrada", "filas_leidas", "copia_temporal_eliminada", "tiempos_ms")
# Salidas añadidas por la prevalidación real (todas TEXTO: «Responder a Power Apps» solo devuelve valores simples; detalle_json es un
# arreglo JSON serializado que la app convierte con ParseJSON). Las 8 anteriores se conservan para no romper la pantalla actual.
SALIDAS_NUEVAS = PV.SALIDAS_NUEVAS
SALIDAS_RESPUESTA = SALIDAS + SALIDAS_NUEVAS
CODIGOS = (PV.CODIGO_OK, PV.CODIGO_OBSERVADO, "ARCHIVO_VACIO", "ESTRUCTURA_INVALIDA", "TABLA_NO_ENCONTRADA", "ARCHIVO_BLOQUEADO",
           "ERROR_LECTURA_EXCEL", "SIN_ARCHIVO", "NO_ES_XLSX", "ERROR_COPIA_ARCHIVO", "DEMASIADAS_FILAS", PV.CODIGO_SHAREPOINT,
           PV.CODIGO_UNIVERSO, "ERROR_NO_CONTROLADO")
RESULTADOS_GLOBALES = ("OK", "OBSERVADO", "ERROR")


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
                    PV.prevalidar_filas(fijar(
                        "Resultado_DEPOSITOS_DEMASIADOS", "ERROR", PV.CODIGO_UNIVERSO,
                        "@concat('Depositos_Activos devolvió más de ',string(outputs('PARAM_TOPE_DEPOSITOS')),' CRÉDITOS de los últimos 2 meses: "
                        "el resultado podría estar incompleto. Avise al administrador.')", "SI", "@outputs('Cantidad_con_datos')"))))
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
                                   "@concat('El archivo tiene ',string(outputs('PARAM_PAGINACION')),' filas o más y el máximo permitido es ',"
                                   "string(sub(outputs('PARAM_PAGINACION'),1)),'. No se procesó ninguna fila: divida el archivo en partes más pequeñas.')",
                                   "SI", 0),
                             revisar_encabezados))
    return secuencia(
        Etapa_excel=asignar("varEtapa", "EXCEL"),
        Leer_tabla_Excel={"type": "OpenApiConnection", "inputs": {
            "host": {"apiId": API_XL, "connectionName": "shared_excelonlinebusiness", "operationId": "GetItems"},
            "parameters": {"source": UBICACION_EXCEL, "drive": PLACEHOLDER_BIBLIOTECA,
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
            secuencia(Fallo_no_copia=si(
                "@equals(variables('varEtapa'),'DEPOSITOS')",
                fijar("Fallo_ERROR_SHAREPOINT", "ERROR", PV.CODIGO_SHAREPOINT,
                      "@concat('No se pudo leer Depositos_Activos (HTTP ',string(outputs('Leer_depositos')?['statusCode']),"
                      "'). Vuelva a intentar o avise al administrador.')", "SI"),
                fijar("Fallo_ERROR_NO_CONTROLADO", "ERROR", "ERROR_NO_CONTROLADO",
                      "Error inesperado al procesar el archivo. Vuelva a intentar o avise al administrador.")))))))


def construir_definicion(max_filas=MAX_FILAS):
    acciones = secuencia(
        PARAM_SITIO=compose(SITIO),
        PARAM_CARPETA=compose(CARPETA_TEMP),
        PARAM_ENCABEZADOS=compose(list(ENCABEZADOS)),
        PARAM_PAGINACION=compose(PAGINACION),
        PARAM_MAX_FILAS=compose(max_filas),
        PARAM_LISTA_DEPOSITOS_ACTIVOS=compose(PV.LISTA_DEPOSITOS_ID),
        PARAM_TOPE_DEPOSITOS=compose(PV.TOPE_DEPOSITOS),
        Entrada=compose({"nombre": "@trim(coalesce(triggerBody()?['file']?['name'],''))",
                         "base64": "@coalesce(triggerBody()?['file']?['contentBytes'],'')"}),
        Inicializar_varT0=variable("varT0", "integer", "@ticks(utcNow())"),
        Inicializar_varT1=variable("varT1", "integer", 0),
        Inicializar_varT2=variable("varT2", "integer", 0),
        Inicializar_varT3=variable("varT3", "integer", 0),
        Inicializar_varT4=variable("varT4", "integer", 0),
        Inicializar_varT5=variable("varT5", "integer", 0),
        Inicializar_varT6=variable("varT6", "integer", 0),
        Inicializar_varEtapa=variable("varEtapa", "string", "ENTRADA"),
        Inicializar_varArchivoId=variable("varArchivoId", "string", ""),
        Inicializar_varBorrada=variable("varBorrada", "string", "NO_APLICA"),
        Inicializar_varTotales=variable("varTotales", "string", "0"),
        Inicializar_varValidas=variable("varValidas", "string", "0"),
        Inicializar_varConError=variable("varConError", "string", "0"),
        Inicializar_varUniverso=variable("varUniverso", "string", "0"),
        Inicializar_varDetalle=variable("varDetalle", "string", "[]"),
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
        "';excel=',string(if(greater(" + t(5) + ",0)," + _ms(t(5), t(1)) + ",if(greater(" + t(2) + ",0)," + _ms(t(2), t(1)) + ",0))),"
        "';depositos=',string(if(greater(" + t(6) + ",0)," + _ms(t(6), t(5)) + ",0)),"
        "';borrar=',string(if(greater(" + t(3) + ",0)," + _ms(t(3), f"max({t(2)},{t(1)},{t(0)})") + ",0)),"
        "';total=',string(" + _ms(t(4), t(0)) + "))")
    acciones["Tiempos"]["runAfter"] = {"Marca_T4": ["Succeeded"]}
    cuerpo = {"resultado": "@variables('varResultado')?['estado']", "codigo": "@variables('varResultado')?['codigo']",
              "mensaje": "@variables('varResultado')?['mensaje']", "archivo": "@outputs('Entrada')?['nombre']",
              "tabla_encontrada": "@variables('varResultado')?['tabla']",
              "filas_leidas": "@string(variables('varResultado')?['filas'])",
              "copia_temporal_eliminada": "@variables('varBorrada')", "tiempos_ms": "@outputs('Tiempos')",
              "filas_totales": "@variables('varTotales')", "filas_validas": "@variables('varValidas')",
              "filas_con_error": "@variables('varConError')", "depositos_consultados": "@variables('varUniverso')",
              "detalle_json": "@variables('varDetalle')"}
    assert tuple(cuerpo) == SALIDAS_RESPUESTA
    esquema = {"type": "object", "properties": {k: {"title": k, "type": "string", "x-ms-dynamically-added": True}
                                                for k in SALIDAS_RESPUESTA}}
    acciones["Responder_a_PowerApps"] = {"type": "Response", "kind": "PowerApp", "runAfter": {"Tiempos": TODOS},
                                         "inputs": {"statusCode": 200, "body": cuerpo, "schema": esquema}}
    return definicion(disparador(), acciones)


# ---------------------------------------------------------------------------------------------- paquete ZIP
CONEXIONES = {"shared_sharepointonline": ("SharePoint", "sharepointonline"),
              "shared_excelonlinebusiness": ("Excel Online (Business)", "excelonlinebusiness")}
FECHA_ZIP = (2026, 10, 5, 0, 0, 0)


DESCRIPCION_FLUJO = ("PROTOTIPO directo: recibe un XLSX, lee tblConfirmacionMasiva y prevalida cada fila contra Depositos_Activos "
                     "(SOLO LECTURA, un GET). Sin lotes. No confirma ni modifica ningún depósito.")


def _uuid(parte, nombre=NOMBRE_FLUJO):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p9:masiva-proto:{nombre}:{parte}"))


def archivos_paquete(definition, nombre=NOMBRE_FLUJO, conexiones_flujo=None, descripcion=DESCRIPCION_FLUJO):
    """Paquete heredado de un flujo. Con los valores por defecto es el de P9_MASIVA_PROTO_PREVALIDAR (sin cambios byte a byte);
    `construir_confirmar.py` lo reutiliza con su nombre, su única conexión (SharePoint) y su descripción."""
    _uuid_ = lambda parte: _uuid(parte, nombre)  # noqa: E731
    flujo, interno = _uuid_("resource"), _uuid_("definition")
    recursos, referencias, apis, conexiones, dependencias = {}, {}, {}, {}, []
    for clave, (titulo, nombre_api) in (conexiones_flujo or CONEXIONES).items():
        api_id = f"/providers/Microsoft.PowerApps/apis/{clave}"
        r_api, r_con = _uuid_(clave + ":api"), _uuid_(clave + ":connection")
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
                       "details": {"displayName": nombre}, "configurableBy": "User", "hierarchy": "Root",
                       "dependsOn": dependencias}
    envoltura = {"name": interno, "id": f"/providers/Microsoft.Flow/flows/{interno}", "type": "Microsoft.Flow/flows",
                 "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows", "displayName": nombre,
                                "definition": definition, "connectionReferences": referencias,
                                "flowFailureAlertSubscribed": False, "isManaged": False}}
    base = f"Microsoft.Flow/flows/{flujo}"
    return {
        "manifest.json": {"schema": "1.0", "details": {
            "displayName": nombre, "description": descripcion,
            "createdTime": "2026-10-05T00:00:00Z", "packageTelemetryId": _uuid_("telemetry"), "creator": "N/A",
            "sourceEnvironment": ""}, "resources": recursos},
        "Microsoft.Flow/flows/manifest.json": {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [flujo]}},
        f"{base}/apisMap.json": apis, f"{base}/connectionsMap.json": conexiones, f"{base}/definition.json": envoltura}


def zip_bytes(definition, **paquete) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta, contenido in archivos_paquete(definition, **paquete).items():
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
