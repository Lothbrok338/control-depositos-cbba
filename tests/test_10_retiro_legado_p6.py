"""P6: retiro controlado del legado de normalización.

Reglas que estas pruebas protegen:
  * ningún componente productivo (motor, deteccion_registro.py, motor_generico.py, captura_origen.py) define ni
    nombra los normalizar_* legados, validar_archivo, HOJAS_VALIDAS / ENCABEZADOS_ESPERADOS,
    encontrar_fila_encabezado, leer_tabla_movimientos, texto_de_archivo, aplicar_identidad_registro, la
    referencia en sombra ni la plantilla legada del registro;
  * las primitivas compartidas que usa el motor genérico siguen en el motor (no se duplican);
  * con SOLO los 5 archivos productivos en una carpeta aislada, los 12 extractos reales dan la salida aprobada
    (doradas del motor original) y no se escribe ningún archivo de sombra;
  * CBBA_MOTOR_SOMBRA ya no tiene efecto.
"""
import ast
import importlib.util
import json
import shutil

import pandas as pd
import pytest

from helpers import EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN, RAIZ, leer_csv_texto

pytestmark = pytest.mark.retiro

REPO = RAIZ.parent
FIJO = pd.Timestamp("2026-08-21 09:00:00")

PRODUCTIVOS = ("motor_control_depositos_cbba.py", "deteccion_registro.py", "motor_generico.py",
               "registro_bancos.json", "captura_origen.py")

RETIRADOS = {
    # motor_control_depositos_cbba.py
    "normalizar_bnb", "normalizar_bcp", "normalizar_union", "normalizar_economico", "normalizar_bisa",
    "normalizar_bmsc", "normalizar_archivo", "validar_archivo", "HOJAS_VALIDAS", "ENCABEZADOS_ESPERADOS",
    "encontrar_fila_encabezado", "leer_tabla_movimientos", "texto_de_archivo", "aplicar_identidad_registro",
    "sombra_estado",
    # motor_generico.py (comparador / sombra / detección P3 / CLI)
    "ejecutar_referencia_legado", "referencia_archivo", "sombra_archivo", "comparar_carpeta", "comparar_frames",
    "comparar_validacion", "comparar_deteccion", "armar_informe", "escribir_informe", "cargar_legado",
    "namespace_legado", "PRIMITIVAS_LEGADO", "MODO_REFERENCIA", "NOMBRE_REPORTE_JSON", "NOMBRE_REPORTE_CSV",
    "ResultadoGenerico", "procesar", "_zona_cabecera",
    # deteccion_registro.py
    "formato_legado", "cuenta_nueva", "hojas_legado", "encabezados_legado", "_formato_legado",
    "HOJA_INCOMPATIBLE", "plantilla_por_hoja",
}

# Nombre de CLAVE del contrato de captura_origen.py (sin cambios desde P1): el motor le pasa ahí la función del
# registro; no es la función legada retirada.
CLAVES_CONTRATO_CAPTURA = {"encontrar_fila_encabezado"}

PRIMITIVAS_COMPARTIDAS = ("COLUMNAS_LISTS", "normalizar_texto", "buscar_columna", "buscar_columna_opcional", "numero",
                          "codigo_texto", "normalizar_fecha", "normalizar_hora", "leer_excel_robusto",
                          "leer_todas_hojas", "finalizar_dataframe", "crear_clave", "valor_clave_numero",
                          "ecuacion_saldo", "extraer_nombre_bnb")


def _nombres_de_codigo(ruta):
    """Nombres definidos o usados en el CÓDIGO (sin docstrings ni comentarios) y literales de texto que no son
    docstrings (p. ej. claves de diccionario o variables de entorno)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    docstrings = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(n, clean=False) is not None:
            docstrings.add(id(n.body[0].value))
    nombres = set()
    for n in ast.walk(arbol):
        # claves literales del contrato de captura ({"clave": ...} o contrato["clave"]): no son la función legada
        claves = n.keys if isinstance(n, ast.Dict) else [n.slice] if isinstance(n, ast.Subscript) else []
        for k in claves:
            if isinstance(k, ast.Constant) and k.value in CLAVES_CONTRATO_CAPTURA:
                docstrings.add(id(k))
        if isinstance(n, ast.Name):
            nombres.add(n.id)
        elif isinstance(n, ast.Attribute):
            nombres.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            nombres.add(n.name)
        elif isinstance(n, ast.arg):
            nombres.add(n.arg)
        elif isinstance(n, ast.keyword) and n.arg:
            nombres.add(n.arg)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            nombres.add(n.value)
    return nombres


# =========================== 1. EL LEGADO NO EXISTE EN PRODUCCIÓN ===========================
@pytest.mark.parametrize("archivo", ["motor_control_depositos_cbba.py", "deteccion_registro.py", "motor_generico.py"])
def test_p6_componente_productivo_no_define_ni_nombra_el_legado(archivo):
    assert _nombres_de_codigo(REPO / archivo) & RETIRADOS == set()


def test_p6_captura_origen_no_llama_al_legado():
    """captura_origen.py (sin cambios desde P1) recibe el contrato del registro; no llama a ninguna función legada
    (la clave de contrato 'encontrar_fila_encabezado' es un nombre de clave, no la función retirada)."""
    assert _nombres_de_codigo(REPO / "captura_origen.py") & RETIRADOS == set()


def test_p6_el_modulo_del_motor_no_expone_el_legado(motor):
    assert sorted(n for n in RETIRADOS if hasattr(motor, n)) == []
    assert not any(n.startswith("normalizar_") and n not in ("normalizar_texto", "normalizar_fecha",
                                                             "normalizar_hora", "normalizar_extracto")
                   for n in dir(motor))


def test_p6_el_motor_generico_no_tiene_comparador_ni_modo_script(motor):
    src = (REPO / "motor_generico.py").read_text(encoding="utf-8")
    assert "__main__" not in src and "SOMBRA_REPORTE" not in _nombres_de_codigo(REPO / "motor_generico.py")
    mg = motor.modulo_generico()
    assert not hasattr(mg, "ejecutar_referencia_legado") and not hasattr(mg.MotorGenerico, "detectar")


def test_p6_el_registro_no_tiene_plantillas_legadas():
    d = json.loads((REPO / "registro_bancos.json").read_text(encoding="utf-8"))
    assert [fid for fid, f in d["FORMATOS"].items() if "legado" in f] == []
    assert "legado" not in d["_ayuda"]["campos_de_formato"]


def test_p6_las_primitivas_compartidas_siguen_en_el_motor_una_sola_vez(motor):
    """Se conservan (no se duplican en motor_generico.py ni en deteccion_registro.py)."""
    assert all(hasattr(motor, n) for n in PRIMITIVAS_COMPARTIDAS)
    for archivo in ("motor_generico.py", "deteccion_registro.py"):
        arbol = ast.parse((REPO / archivo).read_text(encoding="utf-8"))
        definidos = {n.name for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))} | \
                    {t.id for n in arbol.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        assert definidos & set(PRIMITIVAS_COMPARTIDAS) == set(), archivo


def test_p6_la_deteccion_ya_no_informa_campos_legados(motor, ruta_fixture):
    d = motor.detectar_extracto(ruta_fixture("BNB_ME")).como_dict()
    assert "FORMATO_LEGADO" not in d and "CUENTA_NUEVA" not in d
    assert list(d) == ["ESTADO", "MOTIVO", "CUENTA_ID", "FORMATO_REGISTRO", "BANCO", "CUENTA", "MONEDA", "HOJA",
                       "FILA_ENCABEZADO", "CUENTA_LEIDA", "CANDIDATOS", "OBSERVACIONES"]


# =========================== 2. PRODUCCIÓN SOLO CON LOS 5 ARCHIVOS PRODUCTIVOS ===========================
@pytest.fixture(scope="module")
def corrida_aislada(tmp_path_factory):
    """Los 5 archivos productivos solos en una carpeta (sin tests/, sin copia del legado) + los 12 extractos
    reales. CBBA_MOTOR_SOMBRA=1 para demostrar que ya no tiene efecto."""
    base = tmp_path_factory.mktemp("aislado")
    prod = base / "produccion"
    prod.mkdir()
    for f in PRODUCTIVOS:
        shutil.copy(REPO / f, prod / f)
    ent, sal = base / "in", base / "out"
    ent.mkdir()
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    spec = importlib.util.spec_from_file_location("motor_aislado_p6", prod / "motor_control_depositos_cbba.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: FIJO))
        mp.delenv("CBBA_REGISTRO_BANCOS", raising=False)
        mp.setenv("CBBA_MOTOR_SOMBRA", "1")
        res = m.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx"))
    return m, res, sal, prod


def test_p6_produccion_aislada_da_la_salida_aprobada(corrida_aislada):
    m, res, sal, prod = corrida_aislada
    assert sorted(p.name for p in prod.iterdir() if p.is_file()) == sorted(PRODUCTIVOS)
    pd.testing.assert_frame_equal(leer_csv_texto(sal / "LISTS.csv"), leer_csv_texto(GOLDEN / "LOTE_12_LISTS.csv"))
    assert list(pd.read_csv(sal / "LISTS.csv", encoding="utf-8-sig", nrows=0).columns) == list(m.COLUMNAS_LISTS)
    assert res["origen_estado"]["estado"] == "OK" and res["origen_estado"]["movimientos_mapeados"] == 4064
    assert set(res["df_validacion"]["ESTADO"]) == {"OK"}


def test_p6_sin_archivos_ni_estado_de_sombra(corrida_aislada):
    _, res, sal, _ = corrida_aislada
    assert sorted(p.name for p in sal.iterdir()) == ["LISTS.csv", "NORMALIZADO.xlsx", "ORIGEN.xlsx"]
    assert set(res) == {"df_final", "df_validacion", "resumen", "df_resultado_archivos", "df_deteccion_final",
                        "ruta_salida", "ruta_lists_csv", "origen_estado", "deteccion_estado"}


def test_p6_la_produccion_carga_sus_modulos_desde_la_carpeta_productiva(corrida_aislada):
    m, _, _, prod = corrida_aislada
    assert m.modulo_generico().__file__ == str(prod / "motor_generico.py")
    assert m.modulo_deteccion().__file__ == str(prod / "deteccion_registro.py")
