"""Estructura del flujo directo generado y de su ZIP (sin ejecutar nada)."""
import json
import re
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

from p9.wdl import contar_acciones, recorrer
from proto_masiva import contrato_plantilla as P
from proto_masiva.flows import construir as F

CARPETA = Path(F.__file__).resolve().parent
DEF = F.construir_definicion()
TEXTO = json.dumps(DEF, ensure_ascii=False)


def bloques(acciones, ruta="raiz"):
    yield ruta, acciones
    for nombre, a in acciones.items():
        if "actions" in a:
            yield from bloques(a["actions"], f"{ruta}/{nombre}")
        if "else" in a:
            yield from bloques(a["else"]["actions"], f"{ruta}/{nombre}/else")


def test_los_archivos_versionados_son_la_salida_actual_del_generador():
    assert json.loads((CARPETA / f"{F.NOMBRE_FLUJO}_definition.json").read_text(encoding="utf-8")) == DEF
    assert (CARPETA / f"{F.NOMBRE_FLUJO}.zip").read_bytes() == F.zip_bytes(DEF)
    assert contar_acciones(DEF["actions"]) == 107  # 64 de la prevalidación estructural + 43 de la prevalidación real


def test_disparador_power_apps_v2_con_una_sola_entrada_de_tipo_archivo():
    (nombre, t), = DEF["triggers"].items()
    assert (t["type"], t["kind"]) == ("Request", "PowerAppV2")  # el mismo tipo de disparador que la V4.2 validada en tenant
    esquema = t["inputs"]["schema"]
    assert list(esquema["properties"]) == ["file"] and esquema["required"] == ["file"]
    archivo = esquema["properties"]["file"]
    assert archivo["x-ms-content-hint"] == "FILE" and set(archivo["properties"]) == {"name", "contentBytes"}
    assert "conditions" not in t and "recurrence" not in t and "splitOn" not in t  # no es un disparador por lista ni por sondeo


def test_cada_bloque_es_una_cadena_con_una_sola_raiz_sin_acciones_en_paralelo():
    for ruta, acciones in bloques(DEF["actions"]):
        assert all("runAfter" in a for a in acciones.values()), ruta
        raices = [n for n, a in acciones.items() if not a["runAfter"]]
        assert len(raices) == (1 if acciones else 0), (ruta, raices)  # un `else` sin acciones es válido
        for n, a in acciones.items():
            assert set(a["runAfter"]) <= set(acciones), (ruta, n)


def test_toda_referencia_a_acciones_y_variables_existe():
    nombres = {n for n, _ in recorrer(DEF["actions"])}
    for ref in re.findall(r"(?:outputs|body)\('([A-Za-z_0-9]+)'\)", TEXTO):
        assert ref in nombres, ref
    variables = {v["name"] for _, a in recorrer(DEF["actions"]) if a["type"] == "InitializeVariable" for v in a["inputs"]["variables"]}
    assert variables == {"varT0", "varT1", "varT2", "varT3", "varT4", "varT5", "varT6", "varEtapa", "varArchivoId", "varBorrada",
                         "varResultado", "varTotales", "varValidas", "varConError", "varUniverso", "varDetalle"}
    for ref in re.findall(r"variables\('([A-Za-z_0-9]+)'\)", TEXTO):
        assert ref in variables, ref


def test_try_catch_limpieza_y_respuesta_siempre_se_ejecutan():
    a = DEF["actions"]
    todos = ["Succeeded", "Failed", "Skipped", "TimedOut"]
    assert a["CATCH"]["runAfter"] == {"TRY": ["Failed", "TimedOut"]}
    assert a["LIMPIEZA"]["runAfter"] == {"TRY": todos, "CATCH": todos}  # la copia se borra pase lo que pase
    assert a["LIMPIEZA_FALLO"]["runAfter"] == {"LIMPIEZA": ["Failed", "TimedOut"]}  # y un fallo al borrar NO cambia el resultado
    assert a["Marca_T3"]["runAfter"] == {"LIMPIEZA": todos, "LIMPIEZA_FALLO": todos}
    assert a["Responder_a_PowerApps"]["runAfter"] == {"Tiempos": todos}


def test_respuesta_a_power_apps_con_las_8_salidas_originales_mas_5_de_prevalidacion_todas_en_texto():
    r = DEF["actions"]["Responder_a_PowerApps"]
    assert (r["type"], r["kind"]) == ("Response", "PowerApp") and r["inputs"]["statusCode"] == 200
    assert list(r["inputs"]["body"]) == list(F.SALIDAS_RESPUESTA) == list(r["inputs"]["schema"]["properties"])
    assert F.SALIDAS_RESPUESTA[:8] == F.SALIDAS and len(F.SALIDAS_RESPUESTA) == 13  # las 8 de siempre se conservan en su orden
    assert all(p["type"] == "string" for p in r["inputs"]["schema"]["properties"].values())  # como la V4.2 validada en tenant


def test_solo_hay_cuatro_operaciones_y_la_unica_contra_listas_es_un_GET_de_solo_lectura():
    ops = {a["inputs"]["host"]["operationId"] for _, a in recorrer(DEF["actions"]) if a["type"] == "OpenApiConnection"}
    assert ops == {"CreateFile", "GetItems", "DeleteFile", "HttpRequest"}
    http = [(n, a) for n, a in recorrer(DEF["actions"]) if a["type"] == "OpenApiConnection" and a["inputs"]["host"]["operationId"] == "HttpRequest"]
    assert [n for n, _ in http] == ["Leer_depositos"]  # UNA sola llamada a SharePoint para todo el archivo: sin N+1
    assert http[0][1]["inputs"]["parameters"]["parameters/method"] == "GET" and http[0][1]["inputs"]["retryPolicy"] == {"type": "none"}
    # NINGUNA escritura sobre Depositos_Activos: ni MERGE/POST/PATCH/PUT/DELETE, ni ETag/If-Match, ni acciones de crear/actualizar elemento
    for prohibido in ("MERGE", "IF-MATCH", "If-Match", "ETag", "X-HTTP-Method", "'POST'", "'PATCH'", "'PUT'", "'DELETE'", "PostItem", "PatchItem",
                      "UpdateItem", "CreateItem", "DeleteItem", "GetByTitle", "LOTE", "PENDIENTE", "PROCESANDO", "Depositos_Reversiones",
                      "TIPO_CAMBIO", "GetOnUpdatedItems", "GetAttachments"):
        assert prohibido not in TEXTO, prohibido
    assert not [n for n, a in recorrer(DEF["actions"]) if a["type"] in ("Foreach", "Until")]  # sin Apply to each: nada se repite por fila


def test_politicas_de_reintento_crear_y_leer_sin_reintento_borrar_con_dos():
    acciones = dict(recorrer(DEF["actions"]))
    assert acciones["Crear_archivo"]["inputs"]["retryPolicy"] == {"type": "none"}
    assert acciones["Leer_tabla_Excel"]["inputs"]["retryPolicy"] == {"type": "none"}
    assert acciones["Borrar_copia_temporal"]["inputs"]["retryPolicy"] == {"type": "fixed", "count": 2, "interval": "PT5S"}


def test_la_copia_temporal_va_a_su_carpeta_con_nombre_unico_y_se_borra_por_id():
    acciones = dict(recorrer(DEF["actions"]))
    assert DEF["actions"]["PARAM_CARPETA"]["inputs"] == F.CARPETA_TEMP == "/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP"
    crear = acciones["Crear_archivo"]["inputs"]["parameters"]
    assert crear["folderPath"] == "@outputs('PARAM_CARPETA')" and crear["body"] == "@base64ToBinary(outputs('Entrada')?['base64'])"
    assert acciones["Nombre_copia"]["inputs"] == "@concat('TMP_',guid(),'.xlsx')"  # nunca choca ni sobrescribe
    assert acciones["Borrar_copia_temporal"]["inputs"]["parameters"]["id"] == "@variables('varArchivoId')"
    assert acciones["Guardar_id_de_la_copia"]["inputs"]["value"] == "@string(body('Crear_archivo')?['Id'])"


def test_lectura_de_excel_tabla_exacta_paginacion_y_archivo_recien_creado():
    excel = dict(recorrer(DEF["actions"]))["Leer_tabla_Excel"]
    p = excel["inputs"]["parameters"]
    assert excel["inputs"]["host"]["operationId"] == "GetItems"
    assert p["table"] == "tblConfirmacionMasiva" == P.NOMBRE_TABLA
    assert p["file"] == "@body('Crear_archivo')?['Id']"
    assert p["source"] == F.UBICACION_EXCEL == F.SITIO == "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu"  # validado en tenant
    assert p["drive"] == F.PLACEHOLDER_BIBLIOTECA  # el id interno de la biblioteca OneDrive es opaco: se elige en el diseñador
    assert "<CONFIGURAR_UBICACION_EXCEL>" not in json.dumps(DEF)
    assert excel["runtimeConfiguration"]["paginationPolicy"]["minimumItemCount"] == F.PAGINACION


def test_no_inventa_limites_de_filas_el_maximo_esta_desactivado_hasta_medir():
    assert F.MAX_FILAS == 0 and DEF["actions"]["PARAM_MAX_FILAS"]["inputs"] == 0
    assert DEF["actions"]["PARAM_PAGINACION"]["inputs"] == F.PAGINACION  # configuración de lectura, no un límite de negocio
    assert F.construir_definicion(max_filas=123)["actions"]["PARAM_MAX_FILAS"]["inputs"] == 123


def test_encabezados_esperados_son_los_del_contrato_unico():
    assert DEF["actions"]["PARAM_ENCABEZADOS"]["inputs"] == list(P.ENCABEZADOS) and len(P.ENCABEZADOS) == 9


def test_zip_importable_con_dos_conexiones_y_definicion_igual():
    z = zipfile.ZipFile(BytesIO((CARPETA / f"{F.NOMBRE_FLUJO}.zip").read_bytes()))
    nombres = z.namelist()
    assert "manifest.json" in nombres and "Microsoft.Flow/flows/manifest.json" in nombres
    envoltura = json.loads(z.read(next(n for n in nombres if n.endswith("/definition.json"))))
    assert envoltura["properties"]["definition"] == DEF
    assert set(envoltura["properties"]["connectionReferences"]) == {"shared_sharepointonline", "shared_excelonlinebusiness"}
    manifiesto = json.loads(z.read("manifest.json"))
    assert manifiesto["details"]["displayName"] == "P9_MASIVA_PROTO_PREVALIDAR"
    assert all(i.date_time == F.FECHA_ZIP for i in z.infolist())


def test_no_se_modifico_ningun_flujo_ni_artefacto_de_produccion():
    repo = CARPETA.parents[1]
    salida = subprocess.run(["git", "status", "--porcelain", "--", ":!proto_masiva"], cwd=repo, capture_output=True, text=True).stdout
    assert salida.strip() == ""
