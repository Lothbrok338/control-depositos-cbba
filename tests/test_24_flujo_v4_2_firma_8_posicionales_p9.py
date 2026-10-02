"""P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES (definitiva).

Historial verificado en el tenant: V4 quitó `text_2` de `required` → Power Apps pidió 6–7 argumentos; V4.1 lo restauró pero dejó `text_5` (OBSERVACION) opcional → Power Apps
pidió 7 posicionales + un registro final («Text donde se espera Record»). V4.2 pone los 8 inputs en `required` (presencia técnica, no contenido): 8 posicionales, sin registro.
Pruebas locales (intérprete WDL + SharePoint REST simulado + revisión estática del YAML): no certifican cómo Studio calcula la firma; prueban el contrato del paquete y que la
llamada del frontend coincide con él."""
import copy
import hashlib
import json
import re
import sys
import threading
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from p9 import contrato as C  # noqa: E402
from p9.asignar import convertir_powerapps_v3 as V3  # noqa: E402
from p9.asignar import convertir_powerapps_v4 as V4  # noqa: E402
from p9.asignar import convertir_powerapps_v4_1 as V41  # noqa: E402
from p9.asignar import convertir_powerapps_v4_2 as V42  # noqa: E402
from p9.asignar.convertir_powerapps_v2 import _json, _ruta_definicion  # noqa: E402
from p9.ensayo import EnsayoP9, SharePointP9, entradas_asignar  # noqa: E402
from p9.wdl import contar_acciones, recorrer  # noqa: E402

pytestmark = pytest.mark.p9

EJEMPLO = RAIZ / "ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json"
FRONTEND = RAIZ / "p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt"
SHA_V3 = "023db6b4a95b30320f27a1e4d0d38b09bcaac8889ec2e0d3e383d2eb3adb3a44"
SHA_V4 = "df1855a4892e28a650078cf99ad5d47e82bfb14b1628b3b848c8442726500184"
SHA_V41 = "2d656b642baa2e5caa8f41710ae21cffddf6f538e4172e1de3c0eb12f35490a2"
SHA_FRONTEND = "eb68f73700d259bfb4db43d787e4a2ff050ee8c08754b7b5138468f003e050c8"
CLAVES = ["number", "text", "text_1", "text_2", "text_3", "text_4", "text_5", "text_6"]
TITULOS = ["ID SharePoint", "CLAVE_TRANSACCION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "OBSERVACION", "USUARIO_ASIGNACION"]


def leer(ruta):
    with zipfile.ZipFile(ruta) as z:
        return {n: z.read(n) for n in z.namelist()}, _ruta_definicion(z)


V3_ARCH, RUTA = leer(V3.NUEVO_ZIP)
V41_ARCH, _ = leer(V41.NUEVO_ZIP)
V42_ARCH, _ = leer(V42.NUEVO_ZIP)
DEF_V3, DEF_V41, DEF = (json.loads(a[RUTA])["properties"]["definition"] for a in (V3_ARCH, V41_ARCH, V42_ARCH))
TRIGGER = DEF["triggers"]["manual"]["inputs"]["schema"]


def filas():
    return [{**m, "IMPORTE": float(m["IMPORTE"])} for m in json.loads(EJEMPLO.read_text(encoding="utf-8"))["movimientos"]]


def sp_nuevo():
    return SharePointP9(filas(), opciones=("DISPONIBLE", "ASIGNADO"))


def clave(n=1):
    return filas()[n - 1]["CLAVE_TRANSACCION"]


def correr(definicion, sp, entradas):
    r = EnsayoP9(definicion, sp, entradas).ejecutar()
    assert r.estado_final == "Succeeded" and tuple(r.respuesta) == C.SALIDAS
    return r


# ------------------------------------------------------------------ trigger: 8 inputs, los 8 en required
def test_el_trigger_tiene_exactamente_los_8_inputs_en_orden():
    props = TRIGGER["properties"]
    assert list(props) == CLAVES == [c[0] for c in C.ENTRADAS]
    assert [p["title"] for p in props.values()] == TITULOS == [c[4] for c in C.ENTRADAS]
    assert [p["type"] for p in props.values()] == ["number"] + ["string"] * 7
    assert all(p["x-ms-dynamically-added"] is True for p in props.values())
    assert DEF["triggers"]["manual"]["type"] == "Request" and DEF["triggers"]["manual"]["kind"] == "PowerAppV2"


def test_los_8_estan_en_required_en_el_orden_de_properties():
    assert TRIGGER["required"] == CLAVES == list(C.REQUERIDOS_TRIGGER_V4_2) == list(TRIGGER["properties"])
    assert "text_2" in TRIGGER["required"] and "text_5" in TRIGGER["required"]


def test_firma_run_son_8_posicionales_y_ningun_opcional():
    requeridos = set(TRIGGER["required"])
    posicionales = [k for k in TRIGGER["properties"] if k in requeridos]
    opcionales = [k for k in TRIGGER["properties"] if k not in requeridos]
    assert posicionales == CLAVES and opcionales == []  # sin opcionales => Power Apps no genera registro final
    props = TRIGGER["properties"]
    assert [(props[k]["title"], props[k]["type"]) for k in posicionales] == list(zip(TITULOS, ["number"] + ["string"] * 7))


def test_el_trigger_solo_difiere_de_v3_en_required_de_text_5():
    t3, t42 = DEF_V3["triggers"]["manual"]["inputs"]["schema"], TRIGGER
    assert t3["properties"] == t42["properties"] and json.dumps(t3["properties"]) == json.dumps(t42["properties"])  # incluso el orden
    assert set(t42["required"]) - set(t3["required"]) == {"text_5"} and set(t3["required"]) < set(t42["required"])  # lo único nuevo en `required` es text_5
    assert {k: v for k, v in t3.items() if k != "required"} == {k: v for k, v in t42.items() if k != "required"}


# ------------------------------------------------------------------ el cambio, y solo el cambio
def test_bases_pinned_cadena_reproducible_y_zip_v42():
    assert hashlib.sha256(V3.NUEVO_ZIP.read_bytes()).hexdigest() == SHA_V3
    assert hashlib.sha256(V4.NUEVO_ZIP.read_bytes()).hexdigest() == SHA_V4 == V41.BASE_SHA256
    assert hashlib.sha256(V41.NUEVO_ZIP.read_bytes()).hexdigest() == SHA_V41 == V42.BASE_SHA256
    assert V42_ARCH[RUTA] == _json(V42.transformar(json.loads(V41_ARCH[RUTA])))  # el ZIP versionado es exactamente la transformación de V4.1
    assert json.loads((RAIZ / "p9/asignar/flujo_asignar_powerapps_v4_2_definition.json").read_text(encoding="utf-8")) == DEF
    assert contar_acciones(DEF["actions"]) == contar_acciones(DEF_V3["actions"]) == 35


def test_v41_a_v42_solo_cambia_required_del_trigger():
    assert set(V41_ARCH) == set(V42_ARCH) and all(V41_ARCH[n] == V42_ARCH[n] for n in V41_ARCH if n != RUTA)
    assert DEF_V41["actions"] == DEF["actions"]  # ni una acción distinta (incluida Validar_entrada)
    assert {k: v for k, v in DEF_V41.items() if k != "triggers"} == {k: v for k, v in DEF.items() if k != "triggers"}
    assert DEF_V41["triggers"]["manual"]["inputs"]["schema"]["required"] == [c for c in CLAVES if c != "text_5"]  # el defecto de V4.1
    sin_required = lambda t: {k: v for k, v in t["manual"]["inputs"]["schema"].items() if k != "required"}
    assert sin_required(DEF_V41["triggers"]) == sin_required(DEF["triggers"])


def test_v3_a_v42_solo_cambian_required_y_validar_entrada():
    assert set(V3_ARCH) == set(V42_ARCH) and all(V3_ARCH[n] == V42_ARCH[n] for n in V3_ARCH if n != RUTA)
    assert {k for k in DEF_V3["actions"] if DEF_V3["actions"][k] != DEF["actions"][k]} == {"Validar_entrada"} and set(DEF_V3["actions"]) == set(DEF["actions"])
    assert {k: v for k, v in DEF_V3.items() if k not in ("actions", "triggers")} == {k: v for k, v in DEF.items() if k not in ("actions", "triggers")}


# ------------------------------------------------------------------ validación de negocio
def test_validar_entrada_no_exige_codigo_ni_observacion_y_si_los_demas():
    v3, v42 = DEF_V3["actions"]["Validar_entrada"]["inputs"], DEF["actions"]["Validar_entrada"]["inputs"]
    assert v3.replace("empty(outputs('Entrada')?['codigo_estudiante']),", "") == v42
    assert "empty(outputs('Entrada')?['codigo_estudiante'])" not in v42 and "empty(outputs('Entrada')?['observacion'])" not in v42
    for k in C.OBLIGATORIOS_TEXTO_V4:
        assert f"empty(outputs('Entrada')?['{k}'])" in v42, k
    assert C.OBLIGATORIOS_TEXTO_V4 == ("clave", "estudiante", "solicitado_por", "sede_asignacion", "usuario")
    assert DEF["actions"]["Entrada"]["inputs"]["codigo_estudiante"] == "@trim(coalesce(triggerBody()?['text_2'],''))"
    assert DEF["actions"]["Entrada"]["inputs"]["observacion"] == "@trim(coalesce(triggerBody()?['text_5'],''))"


@pytest.mark.parametrize("codigo,observacion", [("", ""), ("   ", "  "), ("", "Pago de matrícula"), ("E-1001", ""), ("E-1001", "x")])
def test_codigo_y_observacion_vacios_o_con_texto_permiten_continuar(codigo, observacion):
    sp = sp_nuevo()
    antes = copy.deepcopy(sp.items)
    r = correr(DEF, sp, entradas_asignar(1, clave(), codigo=codigo, observacion=observacion))
    assert r.respuesta["resultado"] == "ASIGNADO" and r.respuesta["asignado_por"] == "operador@univalle.edu"
    campos = sp.items[1]["campos"]
    assert (campos["CODIGO_ESTUDIANTE"], campos["OBSERVACION"], campos["ESTADO_ASIGNACION"]) == (codigo.strip(), observacion.strip(), "ASIGNADO")
    assert {i: it for i, it in sp.items.items() if i != 1} == {i: it for i, it in antes.items() if i != 1}
    assert [c["metodo"] for c in sp.llamadas] == ["GET", "POST"]
    merge = [c for c in sp.llamadas if c["cabeceras"].get("x-http-method") == "MERGE"][0]
    assert merge["cabeceras"]["if-match"] == '"1"' and set(merge["cuerpo"]) == set(C.CAMPOS_ESCRITOS)


@pytest.mark.parametrize("campo,valor", [("estudiante", " "), ("solicitado", ""), ("sede", "  "), ("usuario", "")])
def test_el_resto_de_obligatorios_siguen_bloqueando_si_estan_vacios(campo, valor):
    sp = sp_nuevo()
    r = correr(DEF, sp, entradas_asignar(1, clave(), codigo="", observacion="", **{campo: valor}))
    assert r.respuesta["codigo"] == "CAMPOS_OBLIGATORIOS" and sp.llamadas == []


def test_clave_obligatoria_limite_255_e_id_invalido_se_conservan():
    sp = sp_nuevo()
    assert correr(DEF, sp, entradas_asignar(1, "", codigo="", observacion="")).respuesta["codigo"] == "CAMPOS_OBLIGATORIOS"
    assert correr(DEF, sp, entradas_asignar(1, clave(), codigo="x" * 256, observacion="")).respuesta["codigo"] == "CAMPO_EXCEDE_255"
    assert correr(DEF, sp, entradas_asignar(0, clave(), codigo="", observacion="")).respuesta["codigo"] == "ID_INVALIDO"
    assert sp.llamadas == []


# ------------------------------------------------------------------ salidas, ETag / If-Match / MERGE, concurrencia
def test_salidas_y_logica_de_escritura_intactas_respecto_de_la_v3():
    a3, a42 = dict(recorrer(DEF_V3["actions"])), dict(recorrer(DEF["actions"]))
    assert {k: v for k, v in a3.items() if k != "Validar_entrada"} == {k: v for k, v in a42.items() if k != "Validar_entrada"}
    salidas = a42["Responder_a_PowerApps"]["inputs"]["schema"]["properties"]
    assert list(salidas) == list(C.SALIDAS) and all(s["x-ms-dynamically-added"] is True and s["type"] == "string" for s in salidas.values())
    cab = a42["Actualizar_deposito"]["inputs"]["parameters"]["parameters/headers"]
    assert cab["X-HTTP-Method"] == "MERGE" and cab["IF-MATCH"] == "@outputs('ETag')"
    assert "CODIGO_ESTUDIANTE" in json.dumps(a42["Cuerpo_actualizacion"]) and "OBSERVACION" in json.dumps(a42["Cuerpo_actualizacion"])


def test_26_columnas_del_motor_y_datos_historicos_intactos():
    sp = sp_nuevo()
    motor = lambda: {i: {c: it["campos"].get(c) for c in C.COLUMNAS_MOTOR_26} for i, it in sp.items.items()}
    antes = motor()
    correr(DEF, sp, entradas_asignar(1, clave(1), codigo="E-2001", observacion=""))
    for i in range(2, 6):
        correr(DEF, sp, entradas_asignar(i, clave(i), codigo="", observacion=""))
    assert motor() == antes
    assert sp.items[1]["campos"]["CODIGO_ESTUDIANTE"] == "E-2001" and sp.items[2]["campos"]["CODIGO_ESTUDIANTE"] == ""
    r = correr(DEF, sp, entradas_asignar(1, clave(1), codigo="", observacion=""))
    assert r.respuesta["resultado"] == "NO_DISPONIBLE" and sp.items[1]["campos"]["CODIGO_ESTUDIANTE"] == "E-2001"


def test_clave_incorrecta_ya_asignado_y_etag_desactualizado():
    sp = sp_nuevo()
    assert correr(DEF, sp, entradas_asignar(1, "X" + clave(), codigo="", observacion="")).respuesta["codigo"] == "CLAVE_NO_COINCIDE"
    assert correr(DEF, sp, entradas_asignar(1, clave(), codigo="", observacion="")).respuesta["resultado"] == "ASIGNADO"
    assert correr(DEF, sp, entradas_asignar(1, clave(), codigo="", observacion="", usuario="otro@univalle.edu")).respuesta["resultado"] == "NO_DISPONIBLE"
    sp2 = sp_nuevo()

    def otro(i, e):
        sp2.items[i]["version"] += 1
        sp2.al_actualizar = None
    sp2.al_actualizar = otro
    r = correr(DEF, sp2, entradas_asignar(2, clave(2), codigo="", observacion=""))
    assert r.respuesta["resultado"] == "CONFLICTO" and sp2.items[2]["campos"]["ESTADO_ASIGNACION"] == "DISPONIBLE"


@pytest.mark.parametrize("repeticion", range(10))
def test_dos_confirmaciones_concurrentes_solo_una_gana(repeticion):
    sp = sp_nuevo()
    sp.barrera = threading.Barrier(2)
    res = {}

    def intento(q):
        res[q] = EnsayoP9(DEF, sp, entradas_asignar(3, clave(3), codigo="", observacion="", usuario=q)).ejecutar().respuesta["resultado"]
    hilos = [threading.Thread(target=intento, args=(q,)) for q in "ab"]
    [h.start() for h in hilos]
    [h.join(30) for h in hilos]
    assert sorted(res.values()) == ["ASIGNADO", "CONFLICTO"]


# ------------------------------------------------------------------ frontend: 8 posicionales, sin registro opcional
def llamada_frontend():
    txt = FRONTEND.read_text(encoding="utf-8")
    assert txt.count("P9_ASIGNAR_DEPOSITO.Run(") == 1
    run = re.search(r"P9_ASIGNAR_DEPOSITO\.Run\((.*?)\n\s*\)\n\s*\)", txt, re.S)[1]
    return txt, run, [a.strip() for a in run.strip().split(",\n")]


def test_el_frontend_llama_run_con_exactamente_8_argumentos_posicionales():
    txt, run, args = llamada_frontend()
    assert args == ["varDepositoSeleccionado.ID", "varDepositoSeleccionado.CLAVE_TRANSACCION", "Trim(txtEstudianteP9.Text)", '""', "Trim(txtSolicitadoP9.Text)",
                    "Trim(txtSedeP9.Text)", "Trim(txtObservacionP9.Text)", "User().Email"]
    assert len(args) == len(TRIGGER["properties"]) == len(TRIGGER["required"]) == 8
    assert args[CLAVES.index("text_2")] == '""' and args[CLAVES.index("text_5")] == "Trim(txtObservacionP9.Text)" and args[CLAVES.index("text_6")] == "User().Email"
    assert "{" not in run and "}" not in run and "text_5" not in txt  # ningún registro opcional
    assert "txtCodigoEstudianteP9" not in txt and "lblCodigoEstudianteP9" not in txt
    assert hashlib.sha256(FRONTEND.read_bytes()).hexdigest() == SHA_FRONTEND


@pytest.mark.parametrize("observacion", ["", "Pago de matrícula"])
def test_la_llamada_posicional_llega_bien_al_flujo(observacion):
    _, _, args = llamada_frontend()
    valores = {"varDepositoSeleccionado.ID": 1, "varDepositoSeleccionado.CLAVE_TRANSACCION": clave(), "Trim(txtEstudianteP9.Text)": "Ana Perez", '""': "",
               "Trim(txtSolicitadoP9.Text)": "Mesa de ayuda", "Trim(txtSedeP9.Text)": "COCHABAMBA", "User().Email": "operador@univalle.edu",
               "Trim(txtObservacionP9.Text)": observacion}
    cuerpo = {k: valores[a] for k, a in zip(TRIGGER["required"], args)}  # posicional -> clave del trigger, en el orden de `required`
    assert list(cuerpo) == CLAVES and cuerpo["text_5"] == observacion and cuerpo["text_6"] == "operador@univalle.edu" and cuerpo["text_2"] == ""
    sp = sp_nuevo()
    r = correr(DEF, sp, cuerpo)
    assert r.respuesta["resultado"] == "ASIGNADO"
    campos = sp.items[1]["campos"]
    assert (campos["USUARIO_ASIGNACION"], campos["OBSERVACION"], campos["CODIGO_ESTUDIANTE"], campos["ESTUDIANTE"]) == ("operador@univalle.edu", observacion, "", "Ana Perez")
