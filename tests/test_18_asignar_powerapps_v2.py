"""P9_ASIGNAR_DEPOSITO_POWERAPPS_V2: el único cambio permitido respecto del flujo validado en el tenant es el trigger.
Pruebas locales (intérprete WDL + SharePoint simulado); no certifican la importación ni el trigger en Microsoft 365."""
import copy
import hashlib
import json
import sys
import threading
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from p9 import contrato as C  # noqa: E402
from p9.asignar import convertir_powerapps_v2 as V2  # noqa: E402
from p9.ensayo import EnsayoP9, SharePointP9, entradas_asignar  # noqa: E402
from p9.wdl import contar_acciones, recorrer  # noqa: E402

pytestmark = pytest.mark.p9

BASE_ZIP, NUEVO_ZIP = V2.BASE_ZIP, V2.NUEVO_ZIP
SHA_BASE = "90890c1f4bd5ee741c1b61f862cde5085ed51b8e08f0f8f5949b694d79b05a85"
EJEMPLO = RAIZ / "ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json"


def leer(ruta):
    with zipfile.ZipFile(ruta) as z:
        definicion = next(n for n in z.namelist() if n.endswith("/definition.json"))
        return {n: z.read(n) for n in z.namelist()}, definicion


BASE_ARCHIVOS, RUTA_DEF = leer(BASE_ZIP)
NUEVO_ARCHIVOS, _ = leer(NUEVO_ZIP)
BASE = json.loads(BASE_ARCHIVOS[RUTA_DEF])["properties"]["definition"]
NUEVA = json.loads(NUEVO_ARCHIVOS[RUTA_DEF])["properties"]["definition"]


def filas():
    return [{**m, "IMPORTE": float(m["IMPORTE"])} for m in json.loads(EJEMPLO.read_text(encoding="utf-8"))["movimientos"]]


def sp(opciones=("DISPONIBLE", "ASIGNADO")):
    return SharePointP9(filas(), opciones=opciones)


def correr(definicion, servidor, id_, clave, **kw):
    e = EnsayoP9(definicion, servidor, entradas_asignar(id_, clave, **kw)).ejecutar()
    assert e.estado_final == "Succeeded"
    return e


# ------------------------------------------------------------------ base intacta y generación reproducible
def test_la_base_es_exactamente_el_zip_validado_en_el_tenant_y_no_se_modifica():
    assert hashlib.sha256(BASE_ZIP.read_bytes()).hexdigest() == SHA_BASE
    assert hashlib.sha256((RAIZ / "P9_HABILITAR_ESTADO_ASIGNADO.zip").read_bytes()).hexdigest() == "e85771495d8a12ca910c821c52de9afaf61b345784687917d70e8c7691d2ca5d"


def test_generacion_reproducible_y_sin_efectos_sobre_la_base():
    antes = (NUEVO_ZIP.read_bytes(), V2.DEFINICION_V2.read_bytes(), V2.DIFF_MD.read_bytes(), BASE_ZIP.read_bytes())
    V2.generar()
    assert (NUEVO_ZIP.read_bytes(), V2.DEFINICION_V2.read_bytes(), V2.DIFF_MD.read_bytes(), BASE_ZIP.read_bytes()) == antes
    assert NUEVO_ZIP.name == "P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip"


# ------------------------------------------------------------------ el trigger
def test_trigger_power_apps_v2_y_no_manual_button():
    manual = NUEVA["triggers"]["manual"]
    assert list(NUEVA["triggers"]) == ["manual"] and manual["type"] == "Request" and manual["kind"] == "PowerAppV2"
    assert BASE["triggers"]["manual"]["kind"] == "Button"  # «Manually trigger a flow»: el que Power Apps no lista
    assert '"Button"' not in json.dumps(NUEVA) and "Button" not in json.dumps(NUEVA["triggers"])
    assert "Manually" not in NUEVO_ARCHIVOS[RUTA_DEF].decode()


def test_exactamente_8_entradas_en_orden_y_con_los_tipos_pedidos():
    esquema = NUEVA["triggers"]["manual"]["inputs"]["schema"]
    claves = list(esquema["properties"])
    assert claves == ["number", "text", "text_1", "text_2", "text_3", "text_4", "text_5", "text_6"] and len(claves) == 8
    nombres = ["ID", "CLAVE_TRANSACCION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "OBSERVACION", "USUARIO_ASIGNACION"]
    logicos = [c[1] for c in C.ENTRADAS]
    assert logicos == ["id", "clave", "estudiante", "codigo_estudiante", "solicitado_por", "sede_asignacion", "observacion", "usuario"]
    assert [esquema["properties"][k]["type"] for k in claves] == ["number"] + ["string"] * 7
    assert [esquema["properties"][k]["x-ms-content-hint"] for k in claves] == ["NUMBER"] + ["TEXT"] * 7
    assert [esquema["properties"][k]["title"] for k in claves][1:] == nombres[1:]  # el 1.º conserva su título actual «ID SharePoint»
    assert esquema["required"] == ["number", "text", "text_1", "text_2", "text_3", "text_4", "text_6"]  # OBSERVACION opcional, como antes
    assert esquema == BASE["triggers"]["manual"]["inputs"]["schema"]  # y es idéntico al del flujo validado


def test_la_firma_run_corresponde_a_la_entrada_remapeada():
    """`Entrada` lee las mismas claves del trigger en el mismo orden: no hubo que remapear nada."""
    assert NUEVA["actions"]["Entrada"] == BASE["actions"]["Entrada"]
    origen = [v for v in NUEVA["actions"]["Entrada"]["inputs"].values()]
    esperado = ["number", "text", "text_1", "text_2", "text_3", "text_4", "text_5", "text_6"]
    assert [next(k for k in esperado if f"['{k}']" in v) for v in origen] == esperado


def test_exactamente_6_salidas_en_la_respuesta_a_power_apps():
    respuesta = NUEVA["actions"]["Responder_a_PowerApps"]
    assert respuesta["type"] == "Response" and respuesta["kind"] == "PowerApp"
    salidas = ["resultado", "codigo", "mensaje", "estado_actual", "asignado_por", "fecha_hora_asignacion"]
    assert list(respuesta["inputs"]["body"]) == salidas == list(respuesta["inputs"]["schema"]["properties"]) == list(C.SALIDAS)
    assert respuesta == BASE["actions"]["Responder_a_PowerApps"]


# ------------------------------------------------------------------ regresión: el trigger es lo único que cambió
def test_el_trigger_es_el_unico_cambio_en_la_definicion():
    cambios = list(V2.cambios(BASE, NUEVA))
    assert cambios == [("triggers.manual.kind", "Button", "PowerAppV2")]
    restaurado = copy.deepcopy(NUEVA)
    restaurado["triggers"]["manual"]["kind"] = "Button"
    assert restaurado == BASE
    assert NUEVA["actions"] == BASE["actions"] and NUEVA["parameters"] == BASE["parameters"] and NUEVA["contentVersion"] == BASE["contentVersion"]


def test_a_nivel_de_bytes_la_unica_diferencia_es_la_cadena_del_kind():
    base, nuevo = BASE_ARCHIVOS[RUTA_DEF], NUEVO_ARCHIVOS[RUTA_DEF]
    assert base.count(b'"kind":"Button"') == 1 and nuevo.count(b'"kind":"PowerAppV2"') == 1
    assert base.replace(b'"kind":"Button"', b'"kind":"PowerAppV2"') == nuevo
    for nombre in BASE_ARCHIVOS:
        if nombre != RUTA_DEF:
            assert BASE_ARCHIVOS[nombre] == NUEVO_ARCHIVOS[nombre], nombre  # manifiestos, mapas e IDs: idénticos
    assert list(BASE_ARCHIVOS) == list(NUEVO_ARCHIVOS)
    envoltura = json.loads(NUEVO_ARCHIVOS[RUTA_DEF])
    assert envoltura["properties"]["displayName"] == "P9_ASIGNAR_DEPOSITO"  # la firma sigue siendo P9_ASIGNAR_DEPOSITO.Run(...)
    assert json.loads(NUEVO_ARCHIVOS["manifest.json"])["details"]["displayName"] == "P9_ASIGNAR_DEPOSITO"


def test_numero_de_acciones_identico():
    assert contar_acciones(NUEVA["actions"]) == contar_acciones(BASE["actions"]) == 35
    assert [n for n, _ in recorrer(NUEVA["actions"])] == [n for n, _ in recorrer(BASE["actions"])]  # mismos nombres, mismo orden


def test_acciones_sharepoint_get_merge_y_etag_identicas_al_validado():
    for nombre in ("PARAM_SITIO_SHAREPOINT", "PARAM_LISTA_DEPOSITOS_ACTIVOS"):
        assert NUEVA["actions"][nombre] == BASE["actions"][nombre]
    nuevas, base = dict(recorrer(NUEVA["actions"])), dict(recorrer(BASE["actions"]))
    http_n = {n: a for n, a in nuevas.items() if a["type"] == "OpenApiConnection"}
    http_b = {n: a for n, a in base.items() if a["type"] == "OpenApiConnection"}
    assert list(http_n) == ["Leer_deposito", "Actualizar_deposito"] and http_n == http_b
    assert nuevas["Leer_deposito"] == base["Leer_deposito"]  # GET
    assert nuevas["Actualizar_deposito"] == base["Actualizar_deposito"]  # MERGE
    cabeceras = nuevas["Actualizar_deposito"]["inputs"]["parameters"]["parameters/headers"]
    assert cabeceras["X-HTTP-Method"] == "MERGE" and cabeceras["IF-MATCH"] == "@outputs('ETag')"
    for nombre in ("ETag", "Deposito", "Ahora", "Cuerpo_actualizacion", "Validar_entrada", "Entrada"):
        assert nuevas[nombre] == base[nombre], nombre


def test_condiciones_y_manejo_de_resultados_identicos():
    nuevas, base = dict(recorrer(NUEVA["actions"])), dict(recorrer(BASE["actions"]))
    condiciones = [n for n, a in base.items() if a["type"] == "If"]
    assert len(condiciones) == 8 and all(nuevas[n] == base[n] for n in condiciones)
    resultados = [n for n in base if n.startswith("Resultado_")]
    assert {"Resultado_ASIGNADO", "Resultado_NO_DISPONIBLE", "Resultado_CONFLICTO", "Resultado_CLAVE_NO_COINCIDE", "Resultado_ENTRADA_INVALIDA"} <= set(resultados)
    assert all(nuevas[n] == base[n] for n in resultados)
    assert NUEVA["actions"]["CATCH"] == BASE["actions"]["CATCH"] and NUEVA["actions"]["TRY"] == BASE["actions"]["TRY"]


# ------------------------------------------------------------------ paridad funcional con el simulador
ESCENARIOS = ["normal", "ya_asignado", "clave_incorrecta", "obligatorio_vacio", "estado_sin_habilitar", "fallo_lectura", "fallo_escritura", "etag_cambiado"]


def ejecutar_escenario(definicion, escenario):
    servidor = sp(opciones=("DISPONIBLE",) if escenario == "estado_sin_habilitar" else ("DISPONIBLE", "ASIGNADO"))
    clave = filas()[0]["CLAVE_TRANSACCION"]
    if escenario == "ya_asignado":
        correr(definicion, servidor, 1, clave, estudiante="Primero", usuario="a@univalle.edu")
    if escenario == "fallo_lectura":
        servidor.fallos["Leer_deposito"] = ("Failed", 500)
    if escenario == "fallo_escritura":
        servidor.fallos["Actualizar_deposito"] = ("TimedOut", 0)
    if escenario == "etag_cambiado":
        def otro(id_, etag):
            servidor.items[id_]["version"] += 1
            servidor.al_actualizar = None
        servidor.al_actualizar = otro
    kw = {"estudiante": "  "} if escenario == "obligatorio_vacio" else {}
    e = correr(definicion, servidor, 1, "X" + clave if escenario == "clave_incorrecta" else clave, **kw)
    return e.respuesta, copy.deepcopy(servidor.items), [(c["metodo"], c["uri"], c["cabeceras"], c["cuerpo"]) for c in servidor.llamadas]


@pytest.mark.parametrize("escenario", ESCENARIOS)
def test_logica_funcional_identica_a_la_version_validada(escenario):
    assert ejecutar_escenario(NUEVA, escenario) == ejecutar_escenario(BASE, escenario)


def test_resultados_esperados_con_el_flujo_v2():
    assert ejecutar_escenario(NUEVA, "normal")[0]["resultado"] == "ASIGNADO"
    assert ejecutar_escenario(NUEVA, "ya_asignado")[0]["resultado"] == "NO_DISPONIBLE"
    assert ejecutar_escenario(NUEVA, "clave_incorrecta")[0]["codigo"] == "CLAVE_NO_COINCIDE"
    assert ejecutar_escenario(NUEVA, "etag_cambiado")[0]["resultado"] == "CONFLICTO"
    assert ejecutar_escenario(NUEVA, "fallo_escritura")[0]["codigo"] == "ACTUALIZACION_NO_CONFIRMADA"


@pytest.mark.parametrize("repeticion", range(5))
def test_concurrencia_con_if_match_identica(repeticion):
    servidor = sp()
    servidor.barrera = threading.Barrier(2)
    resultados = {}

    def intento(q):
        resultados[q] = EnsayoP9(NUEVA, servidor, entradas_asignar(3, filas()[2]["CLAVE_TRANSACCION"], usuario=q)).ejecutar().respuesta["resultado"]
    hilos = [threading.Thread(target=intento, args=(q,)) for q in ("a", "b")]
    [h.start() for h in hilos]
    [h.join(30) for h in hilos]
    assert sorted(resultados.values()) == ["ASIGNADO", "CONFLICTO"] and servidor.items[3]["version"] == 2


def test_la_documentacion_del_diff_esta_actualizada():
    texto = V2.DIFF_MD.read_text(encoding="utf-8")
    assert V2.informe() == texto
    assert "Nodos JSON que cambiaron (1)" in texto and "properties.definition.triggers.manual.kind" in texto
