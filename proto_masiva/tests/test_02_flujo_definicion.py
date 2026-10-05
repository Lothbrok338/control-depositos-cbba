"""Estructura del flujo generado y de su ZIP (sin ejecutar nada)."""
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

from p9.wdl import contar_acciones, recorrer
from proto_masiva import generar_plantillas as G
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
    assert contar_acciones(DEF["actions"]) == 52


def test_disparador_solo_con_PENDIENTE_y_una_ejecucion_a_la_vez():
    (nombre, t), = DEF["triggers"].items()
    assert t["inputs"]["host"]["operationId"] == "GetOnUpdatedItems"
    assert t["inputs"]["parameters"]["table"] == F.LISTA == "P9_MASIVA_PROTO_LOTES"
    assert t["conditions"] == [{"expression": "@equals(triggerBody()?['ESTADO'],'PENDIENTE')"}]
    assert t["runtimeConfiguration"]["concurrency"]["runs"] == 1


def test_cada_bloque_es_una_cadena_con_una_sola_raiz_sin_acciones_en_paralelo():
    for ruta, acciones in bloques(DEF["actions"]):
        assert all("runAfter" in a for a in acciones.values()), ruta
        raices = [n for n, a in acciones.items() if not a["runAfter"]]
        assert len(raices) == 1, (ruta, raices)  # regresión: Etapa_excel corría en paralelo con la copia
        for n, a in acciones.items():
            assert set(a["runAfter"]) <= set(acciones), (ruta, n)


def test_toda_referencia_a_acciones_y_variables_existe():
    nombres = {n for n, _ in recorrer(DEF["actions"])}
    for ref in re.findall(r"(?:outputs|body)\('([A-Za-z_0-9]+)'\)", TEXTO):
        assert ref in nombres, ref
    variables = {v["name"] for _, a in recorrer(DEF["actions"]) if a["type"] == "InitializeVariable" for v in a["inputs"]["variables"]}
    for ref in re.findall(r"variables\('([A-Za-z_0-9]+)'\)", TEXTO):
        assert ref in variables, ref


def test_try_catch_y_escritura_final_siempre_se_ejecuta():
    a = DEF["actions"]
    assert a["CATCH"]["runAfter"] == {"TRY": ["Failed", "TimedOut"]}
    assert set(a["Cuerpo_final"]["runAfter"]) == {"TRY", "CATCH"}
    assert all(set(v) == {"Succeeded", "Failed", "Skipped", "TimedOut"} for v in a["Cuerpo_final"]["runAfter"].values())
    assert a["Escribir_resultado"]["runAfter"] == {"Cuerpo_final": ["Succeeded"]}


def test_el_unico_destino_de_escritura_es_el_lote_y_nunca_produccion():
    escrituras = [a for _, a in recorrer(DEF["actions"]) if a["type"] == "OpenApiConnection"
                  and a["inputs"]["host"]["operationId"] == "HttpRequest"]
    assert len(escrituras) == 2
    for a in escrituras:
        p = a["inputs"]["parameters"]
        assert p["parameters/method"] == "POST" and p["parameters/headers"]["X-HTTP-Method"] == "MERGE"
        assert "GetByTitle(''',outputs('PARAM_LISTA')" in p["parameters/uri"]
        assert a["inputs"]["retryPolicy"] == {"type": "fixed", "count": 2, "interval": "PT5S"}
    for prohibido in ("Depositos_Activos", "Depositos_Reversiones", "TIPO_CAMBIO", "ETag", "CLAVE_TRANSACCION", "ESTADO_ASIGNACION"):
        assert prohibido not in TEXTO, prohibido


def test_if_match_comodin_solo_en_la_lista_de_estado_del_prototipo():
    assert TEXTO.count('"IF-MATCH": "*"') == 2  # las dos escrituras del lote; en Depositos_Activos sería inaceptable


def test_el_flujo_no_vuelve_a_escribir_PENDIENTE():
    cuerpos = [DEF["actions"][n]["inputs"] for n in ("Cuerpo_procesando", "Cuerpo_final")]
    assert cuerpos[0]["ESTADO"] == "PROCESANDO"
    assert "PENDIENTE" not in json.dumps(cuerpos)
    estados = {a["inputs"]["value"]["estado"] for _, a in recorrer(DEF["actions"])
               if a["type"] == "SetVariable" and a["inputs"]["name"] == "varResultado"}
    assert estados == {"COMPLETADO", "ERROR"}


def test_lectura_de_excel_tabla_exacta_paginacion_y_sin_reintentos():
    excel = DEF["actions"]["TRY"]["actions"]["Hay_adjunto"]["actions"]["Es_xlsx"]["actions"]["Leer_tabla_Excel"]
    p = excel["inputs"]["parameters"]
    assert excel["inputs"]["host"]["operationId"] == "GetItems"
    assert p["table"] == "tblConfirmacionMasiva"
    assert p["file"] == "@body('Crear_archivo')?['Id']"
    assert p["source"] == F.PLACEHOLDER_UBICACION and p["drive"] == F.PLACEHOLDER_BIBLIOTECA
    assert excel["inputs"]["retryPolicy"] == {"type": "none"}
    assert excel["runtimeConfiguration"]["paginationPolicy"]["minimumItemCount"] == 2000


def test_encabezados_esperados_son_los_de_la_plantilla():
    assert DEF["actions"]["PARAM_ENCABEZADOS"]["inputs"] == list(G.ENCABEZADOS)
    assert len(G.ENCABEZADOS) == 9


def test_zip_importable_con_dos_conexiones_y_definicion_igual():
    z = zipfile.ZipFile(BytesIO((CARPETA / f"{F.NOMBRE_FLUJO}.zip").read_bytes()))
    nombres = z.namelist()
    assert "manifest.json" in nombres and "Microsoft.Flow/flows/manifest.json" in nombres
    definicion = next(n for n in nombres if n.endswith("/definition.json"))
    envoltura = json.loads(z.read(definicion))
    assert envoltura["properties"]["definition"] == DEF
    assert set(envoltura["properties"]["connectionReferences"]) == {"shared_sharepointonline", "shared_excelonlinebusiness"}
    manifiesto = json.loads(z.read("manifest.json"))
    assert manifiesto["details"]["displayName"] == "P9_MASIVA_PROTO_PREVALIDAR"
    assert {r["name"] for r in manifiesto["resources"].values() if r["type"] == "Microsoft.PowerApps/apis"} == \
        {"shared_sharepointonline", "shared_excelonlinebusiness"}
    assert all(i.date_time == F.FECHA_ZIP for i in z.infolist())


def test_no_se_modifico_ningun_flujo_ni_artefacto_de_produccion():
    import subprocess
    repo = CARPETA.parents[1]
    salida = subprocess.run(["git", "status", "--porcelain", "--", ":!proto_masiva"], cwd=repo, capture_output=True, text=True).stdout
    assert salida.strip() == ""
