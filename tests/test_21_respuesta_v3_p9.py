"""P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA: único cambio respecto de V2 = los 6 outputs tipados de «Responder a PowerApps»;
y contrato del frontend autoritativo (P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt, validado en el tenant) contra la firma real del flujo.
Pruebas locales: no certifican que Power Apps/Power Automate reconozcan los outputs (solo el tenant lo comprueba)."""
import copy
import hashlib
import json
import re
import sys
import threading
import zipfile
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from p9 import contrato as C  # noqa: E402
from p9.asignar import convertir_powerapps_v3 as V3  # noqa: E402
from p9.ensayo import EnsayoP9, SharePointP9, entradas_asignar  # noqa: E402
from p9.wdl import contar_acciones, recorrer  # noqa: E402

pytestmark = pytest.mark.p9

SHA_V2 = "4a73ee22f9246cf8170cb9e8934ed7006f7a087f1aca460f0abac77a0e913dc6"
SALIDAS = ["resultado", "codigo", "mensaje", "estado_actual", "asignado_por", "fecha_hora_asignacion"]
EJEMPLO = RAIZ / "ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json"
FRONTEND = RAIZ / "p9/powerapps/P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt"


def leer(ruta):
    with zipfile.ZipFile(ruta) as z:
        d = next(n for n in z.namelist() if n.endswith("/definition.json"))
        return {n: z.read(n) for n in z.namelist()}, d


V2_ARCH, RUTA = leer(V3.BASE_ZIP)
V3_ARCH, _ = leer(V3.NUEVO_ZIP)
V2 = json.loads(V2_ARCH[RUTA])["properties"]["definition"]
NUEVA = json.loads(V3_ARCH[RUTA])["properties"]["definition"]
RESP = NUEVA["actions"]["Responder_a_PowerApps"]


def filas():
    return [{**m, "IMPORTE": float(m["IMPORTE"])} for m in json.loads(EJEMPLO.read_text(encoding="utf-8"))["movimientos"]]


# ------------------------------------------------------------------ estructura real de varRespuesta (lo que había que inspeccionar)
def test_estructura_real_de_varrespuesta_y_todas_las_acciones_que_la_escriben():
    acciones = dict(recorrer(V2["actions"]))
    ini = acciones["Inicializar_varRespuesta"]["inputs"]["variables"][0]
    assert ini["name"] == "varRespuesta" and ini["type"] == "object" and list(ini["value"]) == SALIDAS
    escritoras = {n: a for n, a in acciones.items() if a["type"] == "SetVariable" and a["inputs"]["name"] == "varRespuesta"}
    assert len(escritoras) == 10 and all(list(a["inputs"]["value"]) == SALIDAS for a in escritoras.values())  # misma estructura en todas
    assert all(isinstance(v, str) for a in escritoras.values() for v in a["inputs"]["value"].values())  # todos los valores son texto
    # y el cuerpo de la respuesta ya leía esas claves exactas
    assert V2["actions"]["Responder_a_PowerApps"]["inputs"]["body"] == {k: f"@variables('varRespuesta')?['{k}']" for k in SALIDAS}


# ------------------------------------------------------------------ V3: exactamente 6 outputs
def test_exactamente_6_outputs_de_texto_marcados_como_outputs_del_diseñador():
    assert RESP["type"] == "Response" and RESP["kind"] == "PowerApp" and RESP["inputs"]["statusCode"] == 200
    props = RESP["inputs"]["schema"]["properties"]
    assert RESP["inputs"]["schema"]["type"] == "object" and list(props) == SALIDAS and len(props) == 6
    assert all(p == {"title": k, "x-ms-dynamically-added": True, "type": "string"} for k, p in props.items())
    assert list(RESP["inputs"]["body"]) == SALIDAS == list(C.SALIDAS)
    assert RESP["inputs"]["body"] == {k: f"@variables('varRespuesta')?['{k}']" for k in SALIDAS}  # mapeo a la variable real
    assert [k for k in RESP["inputs"]["schema"] if k not in ("type", "properties")] == []  # sin required ni extras


# ------------------------------------------------------------------ V3: el único cambio funcional
def test_la_respuesta_es_el_unico_cambio_respecto_de_v2():
    cambios = list(V3.cambios(V2, NUEVA))
    base = "actions.Responder_a_PowerApps.inputs.schema.properties"
    assert sorted(c[0] for c in cambios) == sorted(f"{base}.{k}.x-ms-dynamically-added" for k in SALIDAS)
    assert all(c[1] == "<ausente>" and c[2] is True for c in cambios) and len(cambios) == 6
    restaurado = copy.deepcopy(NUEVA)
    for p in restaurado["actions"]["Responder_a_PowerApps"]["inputs"]["schema"]["properties"].values():
        del p["x-ms-dynamically-added"]
    assert restaurado == V2


def test_a_nivel_de_bytes_solo_cambian_las_6_marcas():
    a, b = V2_ARCH[RUTA], V3_ARCH[RUTA]
    marcadas = b"".join(b'"%s":{"title":"%s","type":"string"}' % (k.encode(), k.encode()) for k in SALIDAS)
    assert a.count(b'"title":"resultado","type":"string"') == 1
    reemplazado = a
    for k in SALIDAS:
        reemplazado = reemplazado.replace(b'"title":"%s","type":"string"' % k.encode(), b'"title":"%s","x-ms-dynamically-added":true,"type":"string"' % k.encode())
    assert reemplazado == b and b.count(b"x-ms-dynamically-added") == 6 + a.count(b"x-ms-dynamically-added")
    assert marcadas not in b  # ya no queda ninguna propiedad sin marca
    for n in V2_ARCH:
        if n != RUTA:
            assert V2_ARCH[n] == V3_ARCH[n], n  # manifiestos, mapas e IDs idénticos
    assert list(V2_ARCH) == list(V3_ARCH)


def test_base_pinned_generacion_reproducible_y_acciones():
    assert hashlib.sha256(V3.BASE_ZIP.read_bytes()).hexdigest() == SHA_V2
    antes = (V3.NUEVO_ZIP.read_bytes(), V3.DEFINICION_V3.read_bytes(), V3.DIFF_MD.read_bytes(), V3.BASE_ZIP.read_bytes())
    V3.generar()
    assert (V3.NUEVO_ZIP.read_bytes(), V3.DEFINICION_V3.read_bytes(), V3.DIFF_MD.read_bytes(), V3.BASE_ZIP.read_bytes()) == antes
    assert contar_acciones(NUEVA["actions"]) == contar_acciones(V2["actions"]) == 35
    assert [n for n, _ in recorrer(NUEVA["actions"])] == [n for n, _ in recorrer(V2["actions"])]
    assert V3.DIFF_MD.read_text(encoding="utf-8") == V3.informe() and "Nodos JSON que cambiaron (6)" in V3.DIFF_MD.read_text(encoding="utf-8")


def test_8_entradas_trigger_identicos_a_v2():
    assert NUEVA["triggers"] == V2["triggers"]
    manual = NUEVA["triggers"]["manual"]
    assert manual["type"] == "Request" and manual["kind"] == "PowerAppV2"
    esquema = manual["inputs"]["schema"]
    claves = list(esquema["properties"])
    assert claves == ["number", "text", "text_1", "text_2", "text_3", "text_4", "text_5", "text_6"]
    assert [esquema["properties"][k]["type"] for k in claves] == ["number"] + ["string"] * 7
    assert NUEVA["actions"]["Entrada"] == V2["actions"]["Entrada"]


def test_sharepoint_etag_if_match_y_merge_identicos():
    n, v = dict(recorrer(NUEVA["actions"])), dict(recorrer(V2["actions"]))
    http_n = {k: a for k, a in n.items() if a["type"] == "OpenApiConnection"}
    assert list(http_n) == ["Leer_deposito", "Actualizar_deposito"] and http_n == {k: a for k, a in v.items() if a["type"] == "OpenApiConnection"}
    cab = n["Actualizar_deposito"]["inputs"]["parameters"]["parameters/headers"]
    assert cab["X-HTTP-Method"] == "MERGE" and cab["IF-MATCH"] == "@outputs('ETag')"
    for nombre in ("PARAM_SITIO_SHAREPOINT", "PARAM_LISTA_DEPOSITOS_ACTIVOS", "ETag", "Deposito", "Ahora", "Cuerpo_actualizacion", "Validar_entrada", "Entrada"):
        assert n[nombre] == v[nombre], nombre
    sin_respuesta = lambda d: {k: a for k, a in d["actions"].items() if k != "Responder_a_PowerApps"}
    assert sin_respuesta(NUEVA) == sin_respuesta(V2)  # TODA la lógica de negocio idéntica
    assert [k for k, a in dict(recorrer(NUEVA["actions"])).items() if a["type"] == "If"] == [k for k, a in dict(recorrer(V2["actions"])).items() if a["type"] == "If"]


@pytest.mark.parametrize("escenario", ["normal", "ya_asignado", "clave_incorrecta", "obligatorio_vacio", "etag_cambiado", "fallo_escritura"])
def test_comportamiento_identico_y_respuesta_con_las_6_claves(escenario):
    def correr(definicion):
        sp = SharePointP9(filas(), opciones=("DISPONIBLE", "ASIGNADO"))
        clave = filas()[0]["CLAVE_TRANSACCION"]
        if escenario == "ya_asignado":
            EnsayoP9(definicion, sp, entradas_asignar(1, clave)).ejecutar()
        if escenario == "fallo_escritura":
            sp.fallos["Actualizar_deposito"] = ("TimedOut", 0)
        if escenario == "etag_cambiado":
            def otro(i, e):
                sp.items[i]["version"] += 1
                sp.al_actualizar = None
            sp.al_actualizar = otro
        kw = {"estudiante": " "} if escenario == "obligatorio_vacio" else {}
        e = EnsayoP9(definicion, sp, entradas_asignar(1, "X" + clave if escenario == "clave_incorrecta" else clave, **kw)).ejecutar()
        return e.respuesta, copy.deepcopy(sp.items), [(c["metodo"], c["uri"], c["cabeceras"], c["cuerpo"]) for c in sp.llamadas]
    nuevo = correr(NUEVA)
    assert nuevo == correr(V2)
    assert list(nuevo[0]) == SALIDAS and all(isinstance(v, str) for v in nuevo[0].values())  # las 6 claves, todas texto


def test_concurrencia_identica():
    sp = SharePointP9(filas(), opciones=("DISPONIBLE", "ASIGNADO"))
    sp.barrera = threading.Barrier(2)
    res = {}

    def intento(q):
        res[q] = EnsayoP9(NUEVA, sp, entradas_asignar(3, filas()[2]["CLAVE_TRANSACCION"], usuario=q)).ejecutar().respuesta["resultado"]
    h = [threading.Thread(target=intento, args=(q,)) for q in "ab"]
    [t.start() for t in h]
    [t.join(30) for t in h]
    assert sorted(res.values()) == ["ASIGNADO", "CONFLICTO"]


# ------------------------------------------------------------------ frontend autoritativo contra la firma REAL del flujo V3
FRONT_TXT = FRONTEND.read_text(encoding="utf-8")
FRONT = yaml.safe_load(FRONT_TXT)


def nodos(items):
    for it in items:
        (n, c), = it.items()
        yield n, c
        yield from nodos(c.get("Children", []))


FRONT_CTRL = dict(nodos(FRONT))


def test_el_frontend_autoritativo_es_un_control_manual_layout_intacto():
    # copia EXACTA del archivo que el usuario tiene pegado en el tenant (frontend final autoritativo; no se modifica)
    assert hashlib.sha256(FRONTEND.read_bytes()).hexdigest() == "595a95b4434f4e0f9d1a2737a35dcfaf0f993db1e3193c9050a5187bb828fc64"
    assert list(FRONT[0]) == ["cntControlDepositosP9"] and FRONT[0]["cntControlDepositosP9"]["Variant"] == "ManualLayout"
    for prohibido in ("Patch(", "SubmitForm(", "Remove(", "AutoLayout", "Screens:", "Form@"):
        assert prohibido not in FRONT_TXT, prohibido


def test_run_del_frontend_coincide_con_los_8_inputs_del_flujo():
    run = re.search(r"P9_ASIGNAR_DEPOSITO\.Run\((.*?)\n\s*\)\n\s*\)", FRONT_TXT, re.S)[1]
    args = [a.strip() for a in run.strip().split(",\n")]
    assert FRONT_TXT.count("P9_ASIGNAR_DEPOSITO.Run(") == 1 and len(args) == 8
    assert [bool(re.search(p, a)) for a, p in zip(args, [r"varDepositoSeleccionado\.ID$", r"varDepositoSeleccionado\.CLAVE_TRANSACCION$", r"txtEstudianteP9", r"txtCodigoEstudianteP9",
                                                      r"txtSolicitadoP9", r"txtSedeP9", r"txtObservacionP9", r"User\(\)\.Email$"])] == [True] * 8
    entradas = NUEVA["triggers"]["manual"]["inputs"]["schema"]["properties"]
    assert len(entradas) == 8 and [entradas[k]["type"] for k in entradas][0] == "number"  # firma: (número, 7 textos), igual que los 8 argumentos


def test_el_frontend_solo_lee_outputs_que_el_flujo_v3_define():
    leidos = set(re.findall(r"varRespuestaP9\.([A-Za-z_]+)", FRONT_TXT))
    assert leidos == {"resultado", "codigo", "mensaje"} and leidos <= set(RESP["inputs"]["schema"]["properties"])
    assert re.search(r"Switch\(\s*varRespuestaP9\.resultado,", FRONT_TXT)
    for r in ("ASIGNADO", "NO_DISPONIBLE", "CONFLICTO"):
        assert f'"{r}"' in FRONT_TXT


def test_no_hace_falta_modificar_el_frontend():
    """Firma .Run() y nombres de outputs coinciden con el flujo V3: btnConfirmarDepositoP9.OnSelect no requiere cambios."""
    onselect = FRONT_CTRL["btnConfirmarDepositoP9"]["Properties"]["OnSelect"]
    assert re.search(r"Set\(\s*varRespuestaP9,\s*P9_ASIGNAR_DEPOSITO\.Run\(", onselect)  # Set(varRespuestaP9, Run(...)) como se pidió
    assert onselect.index("P9_ASIGNAR_DEPOSITO.Run(") < onselect.index("Refresh(Depositos_Activos)", onselect.index("P9_ASIGNAR_DEPOSITO.Run("))
    assert not (RAIZ / "P9_CONTROL_DEPOSITOS_COMPLETO_V2.txt").exists()
