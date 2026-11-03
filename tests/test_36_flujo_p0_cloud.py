"""Validación ESTÁTICA del flujo final P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD y de su ZIP (no ejecuta nada ni toca el tenant)."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from p0.flujo import construir as F
from p9.wdl import contar_acciones, recorrer

pytestmark = pytest.mark.p0
RAIZ = F.RAIZ
DEF = F.construir_definicion()
TEXTO = json.dumps(DEF, ensure_ascii=False)
ACCIONES = dict(recorrer(DEF["actions"]))
RUTA_ZIP = RAIZ / F.NOMBRE_ZIP
RUTA_DEF = F.CARPETA_SALIDA / f"{F.NOMBRE_FLUJO}_definition.json"
DOC = F.CARPETA_SALIDA / "INSTRUCCIONES_IMPORTACION.md"


def bloques(acciones, ruta="raiz"):
    yield ruta, acciones
    for nombre, a in acciones.items():
        if "actions" in a:
            yield from bloques(a["actions"], f"{ruta}/{nombre}")
        if "else" in a:
            yield from bloques(a["else"]["actions"], f"{ruta}/{nombre}/else")
        for caso, c in a.get("cases", {}).items():
            yield from bloques(c["actions"], f"{ruta}/{nombre}/{caso}")
        if "default" in a:
            yield from bloques(a["default"]["actions"], f"{ruta}/{nombre}/default")


def todas(acciones):
    for _, bloque in bloques(acciones):
        yield from bloque.items()


TODAS = dict(todas(DEF["actions"]))


def tipos():
    return {a["type"] for a in TODAS.values()}


def expresiones(nodo):
    if isinstance(nodo, str):
        if nodo.startswith("@"):
            yield nodo
    elif isinstance(nodo, dict):
        for v in nodo.values():
            yield from expresiones(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from expresiones(v)


# ------------------------------------------------------------------ artefactos versionados
def test_artefactos_versionados_son_la_salida_actual_del_generador():
    assert json.loads(RUTA_DEF.read_text(encoding="utf-8")) == DEF
    assert RUTA_ZIP.read_bytes() == F.zip_bytes(DEF)
    assert F.zip_bytes(DEF) == F.zip_bytes(F.construir_definicion())  # determinista
    assert F.NOMBRE_ZIP == "P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V5.zip" and F.NOMBRE_FLUJO == "P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD"


def test_zip_estructura_e_idiomas_de_importacion():
    with zipfile.ZipFile(RUTA_ZIP) as z:
        nombres = z.namelist()
        assert z.testzip() is None
        contenido = {n: json.loads(z.read(n)) for n in nombres}
    assert len(nombres) == 5 and "manifest.json" in nombres and "Microsoft.Flow/flows/manifest.json" in nombres
    (flujo_id,) = contenido["Microsoft.Flow/flows/manifest.json"]["flowAssets"]["assetPaths"]
    base = f"Microsoft.Flow/flows/{flujo_id}"
    assert set(nombres) >= {f"{base}/apisMap.json", f"{base}/connectionsMap.json", f"{base}/definition.json"}
    assert list(contenido[f"{base}/apisMap.json"]) == ["shared_onedriveforbusiness"]
    assert list(contenido[f"{base}/connectionsMap.json"]) == ["shared_onedriveforbusiness"]
    manifest = contenido["manifest.json"]
    assert manifest["details"]["displayName"] == "P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD"
    tipos_recursos = sorted(r["type"] for r in manifest["resources"].values())
    assert tipos_recursos == ["Microsoft.Flow/flows", "Microsoft.PowerApps/apis", "Microsoft.PowerApps/apis/connections"]
    envoltura = contenido[f"{base}/definition.json"]
    refs = envoltura["properties"]["connectionReferences"]
    assert list(refs) == ["shared_onedriveforbusiness"]
    assert refs["shared_onedriveforbusiness"]["connectionName"] == "<CONEXION_ONEDRIVEFORBUSINESS>"
    assert envoltura["properties"]["definition"] == DEF


# ------------------------------------------------------------------ disparador
def test_disparador_onedrive_for_business_entrada_xls_xlsx_concurrencia_1():
    (nombre, t), = DEF["triggers"].items()
    assert t["type"] == "OpenApiConnection" and t["inputs"]["host"]["operationId"] == "OnNewFilesV2"  # properties only (BlobMetadata)
    assert t["inputs"]["host"]["connectionName"] == "shared_onedriveforbusiness" and t["inputs"]["host"]["apiId"].endswith("shared_onedriveforbusiness")
    p = t["inputs"]["parameters"]
    assert unquote(unquote(p["folderId"])) == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA"
    assert p == {"folderId": p["folderId"], "includeSubfolders": False}
    assert t["runtimeConfiguration"]["concurrency"]["runs"] == 1
    cond = t["conditions"][0]["expression"]
    assert "IsFolder" in cond and ".xls'" in cond and ".xlsx'" in cond and "toLower" in cond
    for ext in (".csv", ".pdf", ".xlsm", ".txt"):
        assert ext not in cond
    # OnNewFilesV2 devuelve un ARRAY de BlobMetadata: sin splitOn, triggerBody()?['IsFolder'] falla («Array elements can only be selected
    # using an integer index»). Con splitOn cada ejecución recibe un único elemento (mismo patrón que el trigger de P8 V5).
    assert t["splitOn"] == "@triggerOutputs()?['body']"


def test_el_disparador_es_properties_only_y_todo_lo_que_lee_del_existe_en_blobmetadata():
    # Regresión: OnNewFileV2 devuelve el binario; Name/IsFolder llegaban null y el filtro descartaba todos los archivos.
    assert DEF["triggers"]["Cuando_se_crea_un_archivo"]["inputs"]["host"]["operationId"] != "OnNewFileV2"
    assert "OnNewFileV2" not in TEXTO.replace("OnNewFilesV2", "")
    usados = set(re.findall(r"triggerBody\(\)\?\['([^']+)'\]", TEXTO)) | set(re.findall(r"triggerOutputs\(\)\?\['body/([^']+)'\]", TEXTO))
    assert usados == {"Name", "IsFolder", "Path", "Id"} and usados <= set(F.CAMPOS_DISPARADOR)
    assert not re.findall(r"triggerBody\(\)(?!\?\[)", TEXTO) and "$content" not in json.dumps(DEF["triggers"])  # nada del binario
    assert "FilenameWithExtension" not in TEXTO and "{IsFolder}" not in TEXTO  # nombres de SharePoint, no de OneDrive
    # el contenido sale solo de la acción Get file content, que usa el Path del disparador
    assert TODAS["Get_file_content_using_path"]["inputs"]["parameters"]["path"] == "@triggerOutputs()?['body/Path']"


def test_solo_onedrive_for_business_sin_sharepoint_ni_otros_conectores():
    hosts = {a["inputs"]["host"]["apiId"] for a in TODAS.values() if a["type"] == "OpenApiConnection"}
    hosts.add(DEF["triggers"]["Cuando_se_crea_un_archivo"]["inputs"]["host"]["apiId"])
    assert hosts == {"/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness"}
    assert "sharepoint" not in TEXTO.lower() and "excel" not in TEXTO.lower()


# ------------------------------------------------------------------ contenido + HTTP
def test_get_file_content_using_path_dinamico_sin_inferir_tipo():
    a = TODAS["Get_file_content_using_path"]
    assert a["inputs"]["host"]["operationId"] == "GetFileContentByPath"
    assert a["inputs"]["parameters"] == {"path": "@triggerOutputs()?['body/Path']", "inferContentType": False}
    assert a["runtimeConfiguration"]["secureData"]["properties"] == ["outputs"]


def test_http_post_a_railway_con_body_base64_exacto():
    a = TODAS["HTTP"]
    assert a["type"] == "Http" and a["inputs"]["method"] == "POST"
    assert a["inputs"]["uri"] == "https://p0-api-production-dd77.up.railway.app/procesar-extracto"
    assert a["inputs"]["headers"] == {"Content-Type": "application/json", "Authorization": "Bearer <PEGAR_P0_API_TOKEN_AQUI>"}
    assert a["inputs"]["body"] == {
        "sede": "@outputs('PARAM_SEDE')", "nombre_archivo": "@variables('varNombre')",
        "contenido_base64": "@body('Get_file_content_using_path')?['$content']"}
    assert DEF["actions"]["PARAM_SEDE"]["inputs"] == "CBBA"
    assert TODAS["Inicializar_varNombre"]["inputs"]["variables"][0]["value"] == "@coalesce(triggerOutputs()?['body/Name'],'')"
    assert a["runtimeConfiguration"]["secureData"]["properties"] == ["inputs", "outputs"]
    assert a["inputs"]["retryPolicy"] == {"type": "fixed", "count": 3, "interval": "PT30S"}  # seguro: la API es stateless y P8 evita duplicados
    assert a["inputs"]["limit"] == {"timeout": "PT5M"}


def test_token_real_no_esta_versionado():
    assert F.MARCADOR_TOKEN == "<PEGAR_P0_API_TOKEN_AQUI>"
    candidatos = [RUTA_DEF.read_text(encoding="utf-8"), DOC.read_text(encoding="utf-8"), Path(F.__file__).read_text(encoding="utf-8")]
    with zipfile.ZipFile(RUTA_ZIP) as z:
        candidatos += [z.read(n).decode("utf-8") for n in z.namelist()]
    for texto in candidatos:
        for token in re.findall(r"Bearer\s+([^\s\"'`)]+)", texto):
            assert token in ("<PEGAR_P0_API_TOKEN_AQUI>", "{MARCADOR_TOKEN}"), token
    assert "Bearer <PEGAR_P0_API_TOKEN_AQUI>" in TEXTO and TEXTO.count("Authorization") == 1
    assert TEXTO.replace("<PEGAR_P0_API_TOKEN_AQUI>", "").count("P0_API_TOKEN") == 0  # el marcador es el único lugar


SECURE_ESPERADO = {
    "Get_file_content_using_path": {"outputs"},
    "HTTP": {"inputs", "outputs"},
    "Crear_JSON_P7": {"inputs"},
    "Original_Crear_copia": {"inputs"},
    "Error_json_Crear": {"inputs"},
}


def test_secure_inputs_outputs_exactamente_donde_corresponde():
    con_secure = {n: set(a["runtimeConfiguration"]["secureData"]["properties"])
                  for n, a in TODAS.items() if "secureData" in a.get("runtimeConfiguration", {})}
    assert con_secure == SECURE_ESPERADO
    # el contenido del Excel (Base64) y el JSON bancario salen de HTTP/conectores protegidos; el resto de acciones no los referencian
    for nombre, a in TODAS.items():
        entradas = json.dumps(a.get("inputs", {}))
        if "$content" in entradas or "texto'" in entradas or "body('Get_file_content_using_path')" in entradas:
            assert nombre in SECURE_ESPERADO, nombre


def test_secure_data_solo_en_acciones_que_power_automate_admite():
    # Regresión: «SecureDataPropertyNotSupported ... action 'Fijar_error_http_inesperado' of type 'SetVariable'»
    assert F.TIPOS_CON_SECURE_DATA == ("Http", "OpenApiConnection")
    for nombre, a in TODAS.items():
        rc = a.get("runtimeConfiguration", {})
        if "secureData" in rc:
            assert a["type"] in F.TIPOS_CON_SECURE_DATA, (nombre, a["type"])
        propio = {k: v for k, v in a.items() if k not in ("actions", "else", "cases", "default")}  # sin los hijos del contenedor
        assert "secureData" not in propio and "secureInputs" not in json.dumps(a) and "secureOutputs" not in json.dumps(a), nombre
        if a["type"] in ("SetVariable", "InitializeVariable", "Compose", "If", "Switch", "Scope", "Terminate"):
            assert "secureData" not in json.dumps(propio), (nombre, a["type"])
    assert "secureData" not in json.dumps(DEF["triggers"])
    # y los únicos runtimeConfiguration de acciones son secureData (el disparador lleva solo concurrency)
    assert all(set(a.get("runtimeConfiguration", {})) <= {"secureData"} for a in TODAS.values())


# ------------------------------------------------------------------ decisiones y publicación
def test_condicion_ok_y_condicion_publicar_json():
    http200 = TODAS["Evaluar_HTTP_200"]
    assert http200["expression"] == "@equals(outputs('HTTP')?['statusCode'],200)"
    assert TODAS["Evaluar_ok"]["expression"] == "@equals(body('HTTP')?['ok'],true)"
    assert TODAS["Evaluar_ok_false"]["expression"] == "@equals(body('HTTP')?['ok'],false)"
    assert TODAS["Publicar_JSON"]["expression"] == "@equals(body('HTTP')?['publicar_json'],true)"
    assert "Crear_JSON_P7" in TODAS["Publicar_JSON"]["actions"]
    assert TODAS["Publicar_JSON"]["else"]["actions"] == {}  # publicar_json=false: no crea JSON; igualmente se archiva como PROCESADO
    assert "Fijar_estado_PROCESADO" in TODAS["Evaluar_ok"]["actions"] and "Publicar_JSON" in TODAS["Evaluar_ok"]["actions"]
    rama_ok = TODAS["Evaluar_ok"]["actions"]
    assert rama_ok["Fijar_estado_PROCESADO"]["runAfter"] == {"Publicar_JSON": ["Succeeded"]}


def test_json_p7_se_crea_en_carga_extractos_sin_transformar():
    a = TODAS["Crear_JSON_P7"]
    assert a["inputs"]["host"]["operationId"] == "CreateFile"
    assert DEF["actions"]["PARAM_CARPETA_CARGA"]["inputs"] == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS"
    assert a["inputs"]["parameters"] == {"folderPath": "@outputs('PARAM_CARPETA_CARGA')",
                                         "name": "@body('HTTP')?['json']?['nombre']",
                                         "body": "@body('HTTP')?['json']?['texto']"}  # sin string(), base64, json(), replace(), etc.
    assert a["inputs"]["retryPolicy"] == {"type": "none"}


# ------------------------------------------------------------------ rutas, año/mes, no sobrescritura
def test_rutas_finales_y_meses():
    assert F.CARPETA_ENTRADA == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA"
    assert DEF["actions"]["PARAM_CARPETA_PROCESADOS"]["inputs"] == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS"
    assert DEF["actions"]["PARAM_CARPETA_ERROR"]["inputs"] == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/ERROR"
    assert list(DEF["actions"]["PARAM_MESES"]["inputs"].values()) == [
        "01_ENERO", "02_FEBRERO", "03_MARZO", "04_ABRIL", "05_MAYO", "06_JUNIO", "07_JULIO", "08_AGOSTO", "09_SEPTIEMBRE",
        "10_OCTUBRE", "11_NOVIEMBRE", "12_DICIEMBRE"]
    assert list(DEF["actions"]["PARAM_MESES"]["inputs"]) == [f"{m:02d}" for m in range(1, 13)]


def test_periodo_de_la_api_o_hora_bolivia_con_validacion():
    assert TODAS["Fijar_periodo_de_la_API"]["inputs"]["value"] == "@coalesce(body('HTTP')?['periodo']?['carpeta'],'')"
    assert TODAS["Fijar_periodo_de_la_API_error"]["inputs"]["value"] == "@coalesce(body('HTTP')?['periodo']?['carpeta'],'')"
    assert "SA Western Standard Time" in TODAS["Ahora_Bolivia"]["inputs"]  # UTC-4 Bolivia
    assert "yyyy" in TODAS["Periodo_Bolivia"]["inputs"] and "PARAM_MESES" in TODAS["Periodo_Bolivia"]["inputs"]
    elegido = TODAS["Periodo_Carpeta"]["inputs"]
    assert "variables('varPeriodoApi')" in elegido and "outputs('Periodo_Bolivia')" in elegido and "'..'" in elegido
    assert TODAS["Carpeta_Destino"]["inputs"].count("outputs('Periodo_Carpeta')") == 1
    assert "PARAM_CARPETA_PROCESADOS" in TODAS["Carpeta_Destino"]["inputs"] and "PARAM_CARPETA_ERROR" in TODAS["Carpeta_Destino"]["inputs"]
    assert "convertTimeZone(utcNow(),'UTC','SA Western Standard Time'" in TODAS["Error_llamada_p0"]["inputs"]["value"]["fecha_hora"]


def test_procesados_lleva_subcarpeta_dd_del_dia_de_procesamiento_en_bolivia_y_error_no():
    assert TODAS["Dia_Bolivia"]["inputs"] == "@formatDateTime(outputs('Ahora_Bolivia'),'dd')"
    assert "SA Western Standard Time" in TODAS["Ahora_Bolivia"]["inputs"]  # Bolivia UTC-4; no depende de las fechas de los movimientos
    assert "movimiento" not in TODAS["Dia_Bolivia"]["inputs"].lower() and "periodo" not in TODAS["Dia_Bolivia"]["inputs"].lower()
    assert TODAS["Carpeta_Destino"]["inputs"] == (
        "@concat(if(equals(variables('varEstado'),'PROCESADO'),outputs('PARAM_CARPETA_PROCESADOS'),outputs('PARAM_CARPETA_ERROR')),"
        "'/',outputs('Periodo_Carpeta'),if(equals(variables('varEstado'),'PROCESADO'),concat('/',outputs('Dia_Bolivia')),''))")
    # el día solo se agrega en la rama PROCESADO; ERROR, ENTRADA y CARGA conservan sus rutas
    assert TODAS["Carpeta_Destino"]["inputs"].count("Dia_Bolivia") == 1
    assert DEF["actions"]["PARAM_CARPETA_ERROR"]["inputs"] == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/ERROR"
    assert DEF["actions"]["PARAM_CARPETA_PROCESADOS"]["inputs"] == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS"
    assert DEF["actions"]["PARAM_CARPETA_CARGA"]["inputs"] == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS"
    assert F.CARPETA_ENTRADA == "/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA"
    # la cadena de cálculo: Ahora_Bolivia -> Periodo_Bolivia -> Periodo_Carpeta -> Dia_Bolivia -> Carpeta_Destino
    cadena = ["Ahora_Bolivia", "Periodo_Bolivia", "Periodo_Carpeta", "Dia_Bolivia", "Carpeta_Destino"]
    for previa, nombre in zip(cadena, cadena[1:]):
        assert DEF["actions"][nombre]["runAfter"] == {previa: ["Succeeded"]}


def test_anio_mes_se_crean_solo_al_escribir_el_archivo_real_sin_carpetas_anticipadas():
    # No hay acciones de crear carpetas ni de generar meses futuros: el año/mes solo existe porque CreateFile escribe dentro de él.
    assert not [n for n, a in TODAS.items() if a["type"] == "OpenApiConnection" and "older" in a["inputs"]["host"]["operationId"]]
    assert "Foreach" not in tipos() and "Until" not in tipos()
    copia = TODAS["Original_Crear_copia"]["inputs"]["parameters"]
    assert copia["folderPath"] == "@outputs('Carpeta_Destino')" and copia["body"] == "@body('Get_file_content_using_path')"
    assert TODAS["Error_json_Crear"]["inputs"]["parameters"]["folderPath"] == "@outputs('Carpeta_Destino')"


def test_no_sobrescribe_nombre_existente_agrega_fecha_hora():
    for pref in ("Original", "Error_json"):
        sonda = TODAS[f"{pref}_Consultar_destino"]
        assert sonda["inputs"]["host"]["operationId"] == "GetFileMetadataByPath"
        assert "outputs('Carpeta_Destino')" in sonda["inputs"]["parameters"]["path"] and f"outputs('{pref}_Nombre')" in sonda["inputs"]["parameters"]["path"]
        final = TODAS[f"{pref}_Nombre_final"]
        assert set(final["runAfter"][f"{pref}_Probar_destino"]) == {"Succeeded", "Failed", "TimedOut"}
        assert "yyyyMMddTHHmmss" in final["inputs"] and "lastIndexOf" in final["inputs"]
    mover = TODAS["Original_Mover_sin_contenido"]["inputs"]
    assert mover["host"]["operationId"] == "MoveFile" and mover["parameters"]["overwrite"] is False
    assert TODAS["Original_Crear_copia"]["inputs"]["parameters"]["name"] == "@outputs('Original_Nombre_final')"
    assert TODAS["Error_json_Crear"]["inputs"]["parameters"]["name"] == "@outputs('Error_json_Nombre_final')"
    assert "overwrite\": true" not in TEXTO.lower()


def test_el_original_solo_se_borra_de_entrada_si_la_copia_se_creo():
    copiar = TODAS["Original_Hay_contenido"]["actions"]
    assert list(copiar) == ["Original_Crear_copia", "Original_Borrar_de_ENTRADA"]
    assert copiar["Original_Borrar_de_ENTRADA"]["runAfter"] == {"Original_Crear_copia": ["Succeeded"]}
    assert TODAS["Original_Borrar_de_ENTRADA"]["inputs"]["parameters"] == {"id": "@variables('varIdOrigen')"}
    # sin contenido (falló la lectura) se mueve por Id, sin perder el extracto
    assert "Original_Mover_sin_contenido" in TODAS["Original_Hay_contenido"]["else"]["actions"]
    assert TODAS["Original_Hay_contenido"]["expression"] == "@equals(actions('Get_file_content_using_path')?['status'],'Succeeded')"


# ------------------------------------------------------------------ errores
def test_error_de_negocio_ok_false_va_a_error_con_respuesta_de_p0():
    assert TODAS["Guardar_respuesta_de_P0"]["inputs"] == {"name": "varError", "value": "@body('HTTP')"}
    assert TODAS["Fijar_estado_ERROR_NEGOCIO"]["inputs"]["value"] == "ERROR_NEGOCIO"
    assert TODAS["Error_json_Crear"]["inputs"]["parameters"]["body"] == "@string(variables('varError'))"
    assert TODAS["Error_json_Nombre"]["inputs"] == "@concat(variables('varNombre'),'.error.json')"
    assert TODAS["Escribir_error_json"]["expression"] == "@not(equals(variables('varEstado'),'PROCESADO'))"
    assert "PARAM_CARPETA_PROCESADOS" in TODAS["Carpeta_Destino"]["inputs"]
    assert "if(equals(variables('varEstado'),'PROCESADO')" in TODAS["Carpeta_Destino"]["inputs"]


def test_try_catch_y_codigos_de_error_tecnico():
    assert set(DEF["actions"]["CATCH"]["runAfter"]) == {"TRY"} and set(DEF["actions"]["CATCH"]["runAfter"]["TRY"]) == {"Failed", "TimedOut"}
    assert DEF["actions"]["TRY"]["type"] == "Scope" and DEF["actions"]["CATCH"]["type"] == "Scope"
    campos = TODAS["Error_llamada_p0"]["inputs"]["value"]
    assert {"codigo_error", "etapa", "mensaje", "fecha_hora"} <= set(campos)
    codigos = {c for c in ("P0_API_NO_DISPONIBLE", "P0_API_NO_AUTORIZADO", "P0_API_PAYLOAD_EXCEDIDO", "P0_API_ERROR_SERVIDOR",
                           "P0_RESPUESTA_INVALIDA", "P0_JSON_NO_PUBLICADO", "ORIGEN_NO_LEIDO", "ERROR_NO_CONTROLADO") if c in TEXTO}
    assert {"P0_API_NO_DISPONIBLE", "P0_API_NO_AUTORIZADO", "P0_API_PAYLOAD_EXCEDIDO", "P0_API_ERROR_SERVIDOR", "P0_RESPUESTA_INVALIDA",
            "P0_JSON_NO_PUBLICADO", "ORIGEN_NO_LEIDO", "ERROR_NO_CONTROLADO"} <= codigos
    assert set(TODAS["Clasificar_fallo_por_etapa"]["cases"]) == {"Caso_OBTENER_CONTENIDO", "Caso_LLAMAR_P0", "Caso_PUBLICAR_JSON"}
    codigo = F.codigo_http("X")
    for c in (401, 413):
        assert str(c) in codigo
    # el archivado ocurre tras TRY y CATCH, también cuando hubo fallo; el Terminate Failed deja visible el fallo técnico
    assert set(DEF["actions"]["Ahora_Bolivia"]["runAfter"]) == {"TRY", "CATCH"}
    assert DEF["actions"]["ARCHIVAR"]["runAfter"] == {"Carpeta_Destino": ["Succeeded"]}
    assert DEF["actions"]["ARCHIVAR_FALLO"]["type"] == "Terminate" and set(DEF["actions"]["ARCHIVAR_FALLO"]["runAfter"]["ARCHIVAR"]) == {"Failed", "TimedOut"}
    assert DEF["actions"]["CERRAR"]["runAfter"] == {"ARCHIVAR": ["Succeeded"]}
    assert "ERROR_NEGOCIO" in DEF["actions"]["CERRAR"]["expression"]  # el error de negocio es un resultado normal; el técnico marca la ejecución Failed


# ------------------------------------------------------------------ P0 solo orquesta
def test_no_hay_apply_to_each_ni_parse_json_ni_filtros_sobre_movimientos():
    assert tipos().isdisjoint({"Foreach", "Until", "ParseJson", "Query", "Select", "Table", "Join", "Filter"})
    assert "movimientos" not in TEXTO.lower()
    assert "parse_json" not in TEXTO.lower() and "Apply_to_each" not in TEXTO
    assert tipos() <= {"Scope", "If", "Switch", "Compose", "InitializeVariable", "SetVariable", "OpenApiConnection", "Http", "Terminate"}
    assert contar_acciones(DEF["actions"]) == 59


# ------------------------------------------------------------------ integridad estructural
def test_nombres_unicos_runafter_y_referencias_validas():
    nombres = [n for _, b in bloques(DEF["actions"]) for n in b]
    assert len(nombres) == len(set(nombres))
    for ruta, acciones in bloques(DEF["actions"]):
        assert all("runAfter" in a for a in acciones.values()), ruta
        raices = [n for n, a in acciones.items() if not a["runAfter"]]
        assert len(raices) == (1 if acciones else 0), (ruta, raices)
        for n, a in acciones.items():
            assert set(a["runAfter"]) <= set(acciones), (ruta, n)
    conocidas = set(nombres)
    for ref in re.findall(r"(?:outputs|body|actions)\('([A-Za-z_0-9]+)'\)", TEXTO):
        assert ref in conocidas, ref
    variables = {v["name"] for a in TODAS.values() if a["type"] == "InitializeVariable" for v in a["inputs"]["variables"]}
    assert variables == {"varNombre", "varIdOrigen", "varEtapa", "varEstado", "varPeriodoApi", "varError"}
    for ref in re.findall(r"variables\('([A-Za-z_0-9]+)'\)", TEXTO):
        assert ref in variables, ref
    for a in TODAS.values():
        if a["type"] == "SetVariable":
            assert a["inputs"]["name"] in variables
    for estado in re.findall(r"'(PENDIENTE|PROCESADO|ERROR_NEGOCIO|ERROR_TECNICO)'", TEXTO):
        assert estado in F.ESTADOS


FUNCIONES = {"and", "or", "not", "equals", "contains", "concat", "coalesce", "if", "empty", "length", "split", "first", "string", "take",
             "substring", "lastIndexOf", "indexOf", "isInt", "greater", "greaterOrEquals", "startsWith", "endsWith", "toLower",
             "createArray", "formatDateTime", "convertTimeZone", "utcNow", "outputs", "body", "actions", "variables",
             "triggerOutputs", "triggerBody", "parameters"}


def verificar_expresion(e):
    assert not e.startswith("@@") and "@{" not in e, e
    cuerpo, i, nivel, texto = e[1:], 0, 0, False
    while i < len(cuerpo):
        c = cuerpo[i]
        if texto:
            if c == "'":
                if cuerpo[i + 1:i + 2] == "'":
                    i += 1
                else:
                    texto = False
        elif c == "'":
            texto = True
        elif c == "(":
            nivel += 1
        elif c == ")":
            nivel -= 1
            assert nivel >= 0, e
        i += 1
    assert not texto and nivel == 0, e
    sin_literales = re.sub(r"'(?:[^']|'')*'", "''", cuerpo)
    for f in re.findall(r"([A-Za-z_]+)\(", sin_literales):
        assert f in FUNCIONES, (f, e)


def test_sintaxis_de_todas_las_expresiones():
    todas_las_expresiones = list(expresiones(DEF))
    assert len(todas_las_expresiones) > 60
    for e in todas_las_expresiones:
        verificar_expresion(e)


# ------------------------------------------------------------------ P8 / API / P7 / motor intactos
def test_p8_p7_motor_y_api_no_fueron_modificados():
    huellas = json.loads((F.CARPETA_SALIDA / "huellas_protegidas.json").read_text(encoding="utf-8"))
    assert any(r.startswith("p8/") for r in huellas) and "P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES.zip" in huellas
    assert "motor_generico.py" in huellas and "adaptador_m365.py" in huellas and "esquema_parse_json_p7.json" in huellas
    for ruta, esperado in huellas.items():
        assert hashlib.sha256((RAIZ / ruta).read_bytes()).hexdigest() == esperado, ruta
    for ruta in ("p0/api.py", "p0/nucleo.py", "p0/sedes.json", "Dockerfile", "railway.json", "requirements-p0.txt"):
        assert ruta in huellas, ruta  # la API de Railway y su imagen no se tocan
    assert huellas == F.huellas_protegidas()  # y no se agregó ni quitó ningún archivo protegido


def test_documentacion_de_importacion_cubre_los_puntos_manuales():
    texto = DOC.read_text(encoding="utf-8")
    for clave in ("<PEGAR_P0_API_TOKEN_AQUI>", "Authorization", "OneDrive for Business", "ENTRADA", "CARGA_EXTRACTOS_BANCARIOS",
                  "P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V5.zip", "Secure"):
        assert clave in texto, clave
