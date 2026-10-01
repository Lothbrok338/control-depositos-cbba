"""P8.5: control de integridad de ORIGEN (Excel bancario -> LISTS.csv -> JSON -> certificación)."""
import copy
import json

import pytest

from p8 import construir_paquete_p8 as paquete
from p8 import control_origen as co
from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado

RAIZ = paquete.RAIZ
ORIGEN = RAIZ / "ORIGEN_EJEMPLO.xlsx"
LISTS = RAIZ / "tests/golden/LOTE_12_LISTS.csv"
LISTS_8 = RAIZ / "ejemplos_p7/motor/LISTS.csv"

# Movimientos por archivo en los 12 extractos reales del lote dorado (suma 4064).
ESPERADO = {
    "bcp_me_1.xls": ("BCP", "301-5005425-2-71", 8), "bcp_mn_3.xls": ("BCP", "301-5005684-3-97", 2331),
    "bisa_me_2.xls": ("", "", 0), "bisa_mn_2.xls": ("BISA", "0696870039", 1),
    "bnb_ahorro_2.xls": ("BNB", "3501936692", 95), "bnb_me_1_1.xls": ("BNB", "3400041236", 7),
    "bnb_mn_3.xls": ("BNB", "3000100152", 1184), "clinica_1.xls": ("BNB", "3000100705", 14),
    "economico_1.xlsx": ("BANCO ECONÓMICO", "3041210569", 388), "economico_ahorro.xlsx": ("BANCO ECONÓMICO", "3051446946", 1),
    "mercantil_1.xls": ("BMSC", "1000872489", 3), "union_mn_2.xls": ("BANCO UNIÓN", "10000003224552", 32),
}


@pytest.fixture(scope="module")
def datos():
    return co.leer_origen(ORIGEN), co.leer_lists(LISTS)


@pytest.fixture
def evaluar(datos):
    """evaluar(origen=mutador, lists=mutador): aplica cambios a COPIAS en memoria y devuelve {archivo: fila}."""
    def _evaluar(mod_origen=None, mod_lists=None):
        origen = copy.deepcopy(datos[0])
        por_archivo, sha, total = copy.deepcopy(datos[1][0]), datos[1][1], datos[1][2]
        if mod_origen:
            mod_origen(origen)
        if mod_lists:
            mod_lists(por_archivo)
            total = sum(len(v) for v in por_archivo.values())
        control = co.evaluar(origen, por_archivo, sha, total)
        return control, {f["ARCHIVO_ORIGEN"]: f for f in control["archivos"]}
    return _evaluar


def solo_error(filas, archivo):
    return {a for a, f in filas.items() if f["ESTADO_INTEGRIDAD_ORIGEN"] == "ERROR"} == {archivo}


# ---------------------------------------------------------------- datos reales

def test_los_12_formatos_reales_pasan_con_cuentas_y_totales_exactos(evaluar):
    control, filas = evaluar()
    assert set(filas) == set(ESPERADO)
    for archivo, (banco, cuenta, n) in ESPERADO.items():
        f = filas[archivo]
        assert (f["BANCO"], f["CUENTA"], f["MOVIMIENTOS_ORIGEN"], f["MOVIMIENTOS_NORMALIZADOS"]) == (banco, cuenta, n, n), archivo
        assert f["DIFERENCIA_ORIGEN"] == 0 and f["ESTADO_INTEGRIDAD_ORIGEN"] == "OK" and f["MOTIVOS"] == ""
    assert (control["total_archivos"], control["movimientos_origen"], control["movimientos_normalizados"]) == (12, 4064, 4064)
    assert control["integridad_origen"] == "OK" and control["archivos_error"] == 0
    assert control["origen_vacio_demostrado"] is False  # hay movimientos: no es un lote vacío


def test_salida_por_archivo_tiene_las_columnas_pedidas(evaluar):
    control, _ = evaluar()
    cabecera = co.csv_control(control).splitlines()[0].split(",")
    assert cabecera[:7] == ["ARCHIVO_ORIGEN", "BANCO", "CUENTA", "MOVIMIENTOS_ORIGEN", "MOVIMIENTOS_NORMALIZADOS",
                            "DIFERENCIA_ORIGEN", "ESTADO_INTEGRIDAD_ORIGEN"]
    assert {f["ESTADO_INTEGRIDAD_ORIGEN"] for f in control["archivos"]} <= {"OK", "ERROR"}


# ---------------------------------------------------------------- fallas que debe detectar

def test_movimiento_que_no_llego_a_lists_es_error_y_diferencia(evaluar):
    control, filas = evaluar(mod_lists=lambda l: l["bcp_me_1.xls"].pop())
    f = filas["bcp_me_1.xls"]
    assert (f["MOVIMIENTOS_ORIGEN"], f["MOVIMIENTOS_NORMALIZADOS"], f["DIFERENCIA_ORIGEN"]) == (8, 7, 1)
    assert "MAPA_vs_LISTS" in f["MOTIVOS"] and "CORRESPONDENCIA_1A1" in f["MOTIVOS"]
    assert solo_error(filas, "bcp_me_1.xls") and control["integridad_origen"] == "ERROR"


def test_fila_de_mas_o_repetida_en_lists_es_error(evaluar):
    _, filas = evaluar(mod_lists=lambda l: l["bnb_me_1_1.xls"].append(dict(l["bnb_me_1_1.xls"][0])))
    f = filas["bnb_me_1_1.xls"]
    assert f["DIFERENCIA_ORIGEN"] == -1 and "CORRESPONDENCIA_1A1" in f["MOTIVOS"] and solo_error(filas, "bnb_me_1_1.xls")


def test_clave_distinta_con_mismo_conteo_rompe_la_correspondencia(evaluar):
    def cambiar(l):
        l["clinica_1.xls"][0]["clave"] += "X"
    _, filas = evaluar(mod_lists=cambiar)
    f = filas["clinica_1.xls"]
    assert f["DIFERENCIA_ORIGEN"] == 0 and f["MOTIVOS"] == "CORRESPONDENCIA_1A1" and solo_error(filas, "clinica_1.xls")


@pytest.mark.parametrize("campo,valor", [("banco", "BCP"), ("cuenta", "3000100999")])
def test_cruce_de_banco_o_cuenta_con_el_archivo_es_error(evaluar, campo, valor):
    def cruzar(l):
        l["bnb_mn_3.xls"][5][campo] = valor
    _, filas = evaluar(mod_lists=cruzar)
    assert filas["bnb_mn_3.xls"]["MOTIVOS"] == "BANCO_CUENTA" and solo_error(filas, "bnb_mn_3.xls")


def test_archivo_con_movimientos_pero_sin_banco_cuenta_detectados_es_error(evaluar):
    def borrar(o):
        o["meta"]["economico_ahorro.xlsx"][0].update(banco="", cuenta="")
    _, filas = evaluar(mod_origen=borrar)
    assert filas["economico_ahorro.xlsx"]["MOTIVOS"] == "BANCO_CUENTA" and solo_error(filas, "economico_ahorro.xlsx")


def test_archivo_en_lists_sin_origen_es_error(evaluar):
    def agregar(l):
        l["fantasma.xls"] = [{"clave": "X|1", "banco": "BCP", "cuenta": "1"}]
    control, filas = evaluar(mod_lists=agregar)
    assert "ARCHIVO_SIN_ORIGEN" in filas["fantasma.xls"]["MOTIVOS"] and control["integridad_origen"] == "ERROR"


def test_mapa_sin_un_movimiento_de_origen_es_error(evaluar):
    _, filas = evaluar(mod_origen=lambda o: o["mapa"]["bnb_ahorro_2.xls"].pop())
    assert "ORIGEN_vs_MAPA" in filas["bnb_ahorro_2.xls"]["MOTIVOS"] and solo_error(filas, "bnb_ahorro_2.xls")


def test_metadatos_que_contradicen_el_recuento_propio_son_error(evaluar):
    def falsear(o):
        o["meta"]["mercantil_1.xls"][0]["filas_movimiento"] = "4"
    _, filas = evaluar(mod_origen=falsear)
    assert filas["mercantil_1.xls"]["MOTIVOS"] == "FILAS_MOVIMIENTO_METADATOS"


def test_fila_no_reconocida_que_parece_movimiento_es_error_pero_un_pie_numerico_no(evaluar):
    def inyectar(o):
        o["no_reconocidas"].setdefault("bcp_me_1.xls", {})[("HistoricalAccountExcel", "99")] = ["25/07/2026", "ABONO", "1,250.00"]
    _, filas = evaluar(mod_origen=inyectar)
    assert filas["bcp_me_1.xls"]["MOTIVOS"] == "FILAS_SOSPECHOSAS:1" and solo_error(filas, "bcp_me_1.xls")
    # Los pies reales (totales, saldos congelados) traen números pero no fechas: no son sospechosos.
    _, filas = evaluar()
    assert filas["union_mn_2.xls"]["ESTADO_INTEGRIDAD_ORIGEN"] == "OK"


# ---------------------------------------------------------------- lotes vacíos

def test_lote_vacio_solo_se_demuestra_con_archivos_que_traen_cero(evaluar):
    def todo_vacio(o):
        for a in o["meta"]:
            o["movimiento"][a], o["mapa"][a] = set(), []
            o["meta"][a][0]["filas_movimiento"] = "0"
        o["no_reconocidas"] = {}
    control, filas = evaluar(mod_origen=todo_vacio, mod_lists=lambda l: l.clear())
    assert control["integridad_origen"] == "OK" and control["origen_vacio_demostrado"] is True
    assert (control["movimientos_origen"], control["movimientos_normalizados"]) == (0, 0)
    # LISTS vacío pero el origen sí tenía movimientos: no se demuestra nada.
    control, _ = evaluar(mod_lists=lambda l: l.clear())
    assert control["integridad_origen"] == "ERROR" and control["origen_vacio_demostrado"] is False


def test_sin_ningun_archivo_no_hay_integridad():
    control = co.evaluar({"sha256": "x", "meta": {}, "movimiento": {}, "no_reconocidas": {}, "mapa": {}}, {}, "y", 0)
    assert control["integridad_origen"] == "ERROR" and control["origen_vacio_demostrado"] is False


# ---------------------------------------------------------------- sellado del artefacto

@pytest.fixture(scope="module")
def artefacto_de_12(datos, tmp_path_factory):
    ad = paquete._cargar_adaptador()
    r = ad.adaptar(LISTS, tmp_path_factory.mktemp("p7"), ahora="2026-10-01T00:00:00Z")
    return r["rutas"]["artefacto"]


def test_sellado_conserva_los_movimientos_byte_a_byte(datos, artefacto_de_12):
    control = co.evaluar(datos[0], *datos[1])
    texto = open(artefacto_de_12, encoding="utf-8").read()
    sellado = co.sellar_artefacto(texto, control)
    assert json.loads(sellado)["control_origen"] == control
    assert {k: v for k, v in json.loads(sellado).items() if k != "control_origen"} == json.loads(texto)
    original = texto.splitlines(keepends=True)
    assert [l for l in sellado.splitlines(keepends=True) if not l.startswith('"control_origen"')] == original


def test_sellado_rechaza_artefacto_de_otro_lists_o_ya_sellado(datos):
    control = co.evaluar(datos[0], *datos[1])
    ocho = open(RAIZ / "ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json", encoding="utf-8").read()
    with pytest.raises(ValueError, match="sha256 distinto"):
        co.sellar_artefacto(ocho, control)


def test_sellado_rechaza_conteo_distinto_y_doble_sellado(datos, artefacto_de_12):
    control = co.evaluar(datos[0], *datos[1])
    texto = open(artefacto_de_12, encoding="utf-8").read()
    with pytest.raises(ValueError, match="tantas filas"):
        co.sellar_artefacto(texto, {**control, "movimientos_normalizados": 4063})
    with pytest.raises(ValueError, match="ya está sellado"):
        co.sellar_artefacto(co.sellar_artefacto(texto, control), control)


# ---------------------------------------------------------------- cadena completa y CLI

def test_cadena_completa_excel_lists_json_sharepoint_queda_certificada(datos, artefacto_de_12):
    """12 extractos reales: ORIGEN.xlsx + LISTS.csv -> artefacto sellado -> flujo V7 (simulado)."""
    control = co.evaluar(datos[0], *datos[1])
    entrada = json.loads(co.sellar_artefacto(open(artefacto_de_12, encoding="utf-8").read(), control))
    definicion = json.loads(paquete.DEFINICION_SALIDA.read_text(encoding="utf-8"))
    sp = SharePointSimulado(entrada)
    EnsayoWDL(definicion, sp).ejecutar()
    b = sp.bitacoras[0]
    assert (b["CANTIDAD_ESPERADA"], b["CANTIDAD_CONFIRMADA"], b["CANTIDAD_FALTANTE"], b["CANTIDAD_DIFERENCIA"],
            b["CANTIDAD_ERROR"]) == (4064, 4064, 0, 0, 0)
    assert b["INTEGRIDAD_ORIGEN/Value"] == "OK" and b["ESTADO_CERTIFICACION/Value"] == "CERTIFICADO"
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO" and len(sp.activos) == 4064


def test_cli_escribe_csv_y_artefacto_sellado_sin_tocar_la_carpeta_del_motor(artefacto_de_12, tmp_path):
    salida = tmp_path / "salida"
    codigo = co.main([str(ORIGEN), str(LISTS), str(artefacto_de_12), "--salida", str(salida)])
    assert codigo == 0
    nombres = sorted(p.name for p in salida.iterdir())
    assert nombres[0].startswith("CONTROL_ORIGEN_P8_5__P7-6d5da35355cb") and nombres[1].startswith("DEPOSITOS_ACTIVOS__")
    assert json.loads((salida / nombres[1]).read_text(encoding="utf-8"))["control_origen"]["integridad_origen"] == "OK"
    with pytest.raises(SystemExit):
        co.main([str(ORIGEN), str(LISTS), "--salida", str(LISTS.parent)])
