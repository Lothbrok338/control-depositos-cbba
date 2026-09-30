"""P3 → P6: registro_bancos.json + motor_generico.py (única normalización desde P6).

Antes `test_06_sombra_p3.py`. P6 retiró el comparador genérico ↔ legado y la referencia en sombra; las pruebas que
solo comparaban contra los normalizar_* legados se retiraron con ellos (la equivalencia con el motor original queda
fijada por las doradas: test_02, test_09). Reglas que estas pruebas protegen:
  * el registro es válido, tiene las 13 cuentas del contrato y sus hojas / encabezados son los del motor original
    (contrato congelado en helpers.HOJAS / helpers.ENCABEZADOS);
  * un registro inválido se detecta; agregar una cuenta de un formato conocido es solo configuración;
  * el motor genérico no reutiliza lógica bancaria: solo primitivas de conversión y lectura del motor;
  * el registro GOBIERNA la normalización y la validación productivas (un cambio del registro cambia exactamente
    la columna o el saldo que describe);
  * sin registro válido o sin motor_generico.py la producción se detiene antes de escribir.
"""
import ast
import copy
import importlib.util
import json
import shutil
import sys

import pandas as pd
import pytest

from helpers import (CONTRATO, ENCABEZADOS, EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN, HOJAS, RAIZ, crear_xlsx_bnb)

pytestmark = pytest.mark.registro

REPO = RAIZ.parent
TS = pd.Timestamp("2026-01-01 00:00:00")
FIJO = pd.Timestamp("2026-08-21 09:00:00")


# ------------------------------- fixtures -------------------------------
@pytest.fixture(scope="session")
def mg():
    spec = importlib.util.spec_from_file_location("motor_generico_bajo_prueba", REPO / "motor_generico.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def registro(mg):
    return mg.Registro.cargar(REPO / "registro_bancos.json")


@pytest.fixture(scope="session")
def generico(mg, registro, motor):
    return mg.MotorGenerico(registro, motor)


def _procesar(gen, ruta, cuenta_id, nombre="x"):
    """Normaliza y valida UN extracto con el motor genérico (misma secuencia que la producción)."""
    df, ctx = gen.normalizar(str(ruta), cuenta_id, "L", TS, nombre_origen=nombre)
    return df, gen.validar(str(ruta), cuenta_id, df, ctx), ctx


# ------------------------------- 1. REGISTRO -------------------------------
def test_registro_es_valido(registro):
    assert registro.validar() == []


def test_registro_tiene_las_13_cuentas_actuales_y_coinciden_con_el_contrato(registro):
    ids = {c["id"] for c in registro.cuentas}
    assert ids == set(CONTRATO) and len(registro.cuentas) == 13
    for c in registro.cuentas:
        assert (c["banco"], c["cuenta"], c["moneda"]) == CONTRATO[c["id"]], c["id"]
        assert c["activa"] is True


def test_registro_hojas_y_encabezados_son_los_del_motor_original(registro):
    """El registro reproduce HOJAS_VALIDAS y ENCABEZADOS_ESPERADOS del motor original (retirados en P6; su copia
    congelada vive en helpers)."""
    for c in registro.cuentas:
        fmt = registro.formato(c["formato"])
        assert HOJAS[c["id"]] in fmt["hojas_aceptadas"], c["id"]
        assert fmt["encabezados"]["puntaje"] == ENCABEZADOS[c["id"]], c["id"]


def test_registro_formatos_de_la_misma_familia_se_comparten(registro):
    por_formato = {}
    for c in registro.cuentas:
        por_formato.setdefault(c["formato"], []).append(c["id"])
    assert por_formato == {
        "BISA_EXTRACTO_V1": ["BISA_MN", "BISA_ME"],
        "BNB_EXTRACTO_V1": ["BNB_MN", "BNB_ME", "BNB_AHORRO", "BNB_CLINICA"],
        "BCP_EXTRACTO_V1": ["BCP_MN", "BCP_ME"],
        "UNION_FECHAS_V1": ["UNION_MN", "UNION_ME"],
        "ECO_EXTRACTO_V1": ["ECO_CTA_CTE", "ECO_AHORRO"],
        "BMSC_EXCEL_V1": ["BMSC"],
    }
    assert registro.formato("UNION_ULTIMOS12_V1")["aceptado"] is False


def _mutar(registro, fn):
    d = copy.deepcopy(registro.datos)
    fn(d)
    return d


MUTACIONES_INVALIDAS = {
    "id_duplicado": lambda d: d["CUENTAS"].append(dict(d["CUENTAS"][0], cuenta="1234567")),
    "formato_inexistente": lambda d: d["CUENTAS"][0].update(formato="NO_EXISTE"),
    "misma_cuenta_y_formato": lambda d: d["CUENTAS"].append(dict(d["CUENTAS"][2], id="OTRA")),
    "cuenta_contenida_en_otra": lambda d: d["CUENTAS"].append(
        {"id": "X", "formato": "BNB_EXTRACTO_V1", "banco": "BNB", "cuenta": "300010015", "moneda": "BOB"}),
    "cuenta_a_formato_no_aceptado": lambda d: d["CUENTAS"].append(
        {"id": "X", "formato": "UNION_ULTIMOS12_V1", "banco": "U", "cuenta": "1", "moneda": "BOB"}),
    "cuenta_sin_moneda": lambda d: d["CUENTAS"][0].update(moneda=""),
    "falta_rol_obligatorio": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["campos"].pop("SALDO"),
    "puntaje_minimo_invalido": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["encabezados"].update(puntaje_minimo=0),
    "modo_importe_invalido": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["importe"].update(modo="OTRO"),
    "depositante_campo_inexistente": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["depositante"].update(campo="NADA"),
    "info_campo_inexistente": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["info_adicional"]["partes"].append({"campo": "NADA"}),
    "filtro_fecha_invalido": lambda d: d["FORMATOS"]["ECO_EXTRACTO_V1"].update(filtro_fecha="OTRO"),
    "firma_vacia": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"].update(firma={}),
    "fuente_saldo_invalida": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["saldo"]["inicial"].update(fuente="MAGIA"),
    "formato_no_aceptado_sin_mensaje": lambda d: d["FORMATOS"]["UNION_ULTIMOS12_V1"].pop("mensaje"),
}


@pytest.mark.parametrize("nombre", list(MUTACIONES_INVALIDAS))
def test_registro_invalido_se_detecta(mg, registro, nombre):
    reg = mg.Registro(_mutar(registro, MUTACIONES_INVALIDAS[nombre]))
    assert reg.validar(), f"la mutación '{nombre}' debió invalidar el registro"


def test_registro_json_roto_falla_con_mensaje(mg, tmp_path):
    ruta = tmp_path / "r.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    with pytest.raises(mg.RegistroError):
        mg.Registro.cargar(ruta)


# ------------------------------- 2. SIN LÓGICA BANCARIA DEL MOTOR -------------------------------
PROHIBIDOS = {
    "detectar_formato", "encontrar_fila_encabezado", "leer_tabla_movimientos", "validar_archivo",
    "normalizar_archivo", "normalizar_bnb", "normalizar_bcp", "normalizar_union", "normalizar_economico",
    "normalizar_bisa", "normalizar_bmsc", "texto_de_archivo", "descubrir_archivos", "ejecutar_motor",
    "ENCABEZADOS_ESPERADOS", "HOJAS_VALIDAS",
}


def test_motor_generico_no_usa_la_logica_bancaria_del_motor():
    """Todo motor_generico.py (no solo Registro y MotorGenerico, como en P3-P5: desde P6 ya no hay comparador)."""
    arbol = ast.parse((REPO / "motor_generico.py").read_text(encoding="utf-8"))
    usados = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Name):
            usados.add(n.id)
        elif isinstance(n, ast.Attribute):
            usados.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            usados.add(n.name)
    assert usados & PROHIBIDOS == set()


def test_primitivas_compartidas_son_solo_conversion_y_lectura(mg):
    """Las primitivas que el genérico toma del motor no contienen lógica por banco (salvo la estrategia con nombre)."""
    assert set(mg.PRIMITIVAS_MOTOR) == {
        "COLUMNAS_LISTS", "normalizar_texto", "buscar_columna", "buscar_columna_opcional", "numero", "codigo_texto",
        "normalizar_fecha", "normalizar_hora", "leer_excel_robusto", "leer_todas_hojas", "finalizar_dataframe",
        "ecuacion_saldo", "extraer_nombre_bnb"}    # extraer_nombre_bnb = estrategia 'legacy_bnb' (D-18/D-19 sin tocar)


def test_faltan_primitivas_error_claro(mg, registro):
    with pytest.raises(RuntimeError, match="no expone las primitivas requeridas"):
        mg.MotorGenerico(registro, {"numero": float})


def test_registro_no_se_modifica_al_normalizar(registro, generico, ruta_fixture):
    antes = json.dumps(registro.datos, sort_keys=True)
    _procesar(generico, ruta_fixture("BNB_ME"), "BNB_ME")
    assert json.dumps(registro.datos, sort_keys=True) == antes


# ------------------------------- 3. EXTRACTOS REALES -------------------------------
def test_bisa_me_sin_movimientos_deja_df_vacio_con_identidad(generico, ruta_fixture):
    df, val, ctx = _procesar(generico, ruta_fixture("BISA_ME"), "BISA_ME", "bisa_me_2.xls")
    assert ctx["sin_movimientos"] and len(df) == 0 and list(df.columns) == list(generico.L.COLUMNAS_LISTS)
    assert ctx["identidad"]["CUENTA BANCARIA"] == "0696872023" and val["ESTADO"] == "OK"


def test_generico_es_determinista(generico, ruta_fixture):
    a, va, _ = _procesar(generico, ruta_fixture("BCP_MN"), "BCP_MN")
    b, vb, _ = _procesar(generico, ruta_fixture("BCP_MN"), "BCP_MN")
    pd.testing.assert_frame_equal(a, b)
    assert va == vb


# ------------------------------- 4. CAMPO_CANONICO -------------------------------
@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_campo_canonico_cubre_todos_los_encabezados_reales(generico, registro, motor, ruta_fixture, formato):
    """Cada encabezado de tabla que entrega el banco tiene etiqueta común en el registro."""
    ruta = ruta_fixture(formato)
    hojas = motor.leer_todas_hojas(ruta)
    fmt = registro.formato(registro.cuenta(formato)["formato"])
    hoja = generico._hoja_aceptada(hojas, fmt)
    fila, _, _ = generico._fila_encabezado(hojas[hoja], fmt["encabezados"]["puntaje"])
    encabezados = [str(x) for x in hojas[hoja].loc[fila].tolist() if pd.notna(x) and str(x).strip()]
    assert encabezados
    sin = [e for e in encabezados
           if not registro.campo_canonico(registro.cuenta(formato)["formato"], e, motor.normalizar_texto)]
    assert sin == [], f"encabezados sin CAMPO_CANONICO en {formato}: {sin}"


def test_campo_canonico_ejemplos(registro, motor):
    n = motor.normalizar_texto
    assert registro.campo_canonico("BNB_EXTRACTO_V1", "Referencia", n) == "REFERENCIA"
    assert registro.campo_canonico("BNB_EXTRACTO_V1", "  código  de transacción ", n) == "CODIGO_TRANSACCION"
    assert registro.campo_canonico("BMSC_EXCEL_V1", "Nom.Destinatario", n) == "DESTINATARIO_NOMBRE"
    assert registro.campo_canonico("UNION_FECHAS_V1", "Nro de verificasion", n) == "NRO_VERIFICACION"
    assert registro.campo_canonico("BCP_EXTRACTO_V1", "Suc. Age.", n) == "SUCURSAL_AGENCIA"
    assert registro.campo_canonico("BNB_EXTRACTO_V1", "Columna nueva del banco", n) == ""


# ------------------------------- 5. CUENTA NUEVA POR CONFIGURACIÓN -------------------------------
def _detector(motor, registro):
    """Detección productiva (deteccion_registro.py) sobre un registro en memoria."""
    return motor.modulo_deteccion().DetectorRegistro(registro.datos, motor.normalizar_texto, motor.leer_todas_hojas)


def test_cuenta_nueva_de_formato_conocido_se_agrega_solo_con_configuracion(mg, registro, motor, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "nueva.xlsx", "9999999999", [
        {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0},
        {"fecha": "02/08/2026", "deb": 30.0, "saldo": 1070.0}])
    # sin registrar: se rechaza con motivo explícito
    sin = _detector(motor, registro).detectar(str(ruta))
    assert sin.estado == "CUENTA_NO_REGISTRADA" and "no está registrada" in sin.motivo
    assert motor.detectar_formato(str(ruta)) == "NO_RECONOCIDO"
    # registrada: UNA entrada de configuración, cero código
    nuevo = registro.con_cuenta("BNB_PRUEBA", "BNB_EXTRACTO_V1", "BNB", "9999999999", "USD")
    assert len(registro.cuentas) == 13 and len(nuevo.cuentas) == 14          # el registro original no cambia
    det = _detector(motor, nuevo).detectar(str(ruta))
    assert det.estado == "OK" and det.cuenta_id == "BNB_PRUEBA"
    df, val, _ = _procesar(mg.MotorGenerico(nuevo, motor), ruta, det.cuenta_id, "nueva.xlsx")
    assert set(df["BANCO"]) == {"BNB"} and set(df["CUENTA BANCARIA"]) == {"9999999999"}
    assert set(df["MONEDA"]) == {"USD"}
    assert df["IMPORTE"].tolist() == [100.0, 30.0] and df["TIPO MOVIMIENTO"].tolist() == ["CRÉDITO", "DÉBITO"]
    assert val["ESTADO"] == "OK"
    assert df["CLAVE TRANSACCIÓN"].iloc[0].startswith("BNB|9999999999|20260801|")


def test_cuenta_nueva_produce_lo_mismo_que_una_cuenta_conocida_con_el_mismo_contenido(mg, registro, motor, tmp_path):
    """Mismo contenido bajo una cuenta conocida (BNB_CLINICA) y bajo una cuenta nueva: solo cambian
    CUENTA/CLAVE; el resto de las columnas es idéntico (no hay lógica por cuenta)."""
    filas = [{"fecha": "02/08/2026", "deb": 30.0, "saldo": 1070.0, "adic": "Nombre: ACME; x"},
             {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0}]
    conocida = crear_xlsx_bnb(tmp_path / "c.xlsx", "3000100705", filas)
    nueva = crear_xlsx_bnb(tmp_path / "n.xlsx", "8888888888", filas)
    reg = registro.con_cuenta("BNB_NUEVA", "BNB_EXTRACTO_V1", "BNB", "8888888888", "BOB")
    gen = mg.MotorGenerico(reg, motor)
    a, va, _ = _procesar(gen, conocida, "BNB_CLINICA", "c.xlsx")
    b, vb, _ = _procesar(gen, nueva, "BNB_NUEVA", "c.xlsx")
    variables = ["CUENTA BANCARIA", "CLAVE TRANSACCIÓN"]
    pd.testing.assert_frame_equal(a.drop(columns=variables), b.drop(columns=variables))
    assert va == vb


def test_con_cuenta_rechaza_configuraciones_invalidas(registro):
    with pytest.raises(Exception):
        registro.con_cuenta("BNB_MN", "BNB_EXTRACTO_V1", "BNB", "1234567", "BOB")      # id repetido
    with pytest.raises(Exception):
        registro.con_cuenta("Z", "FORMATO_QUE_NO_EXISTE", "X", "1", "BOB")             # formato desconocido
    with pytest.raises(Exception):
        registro.con_cuenta("Z", "BNB_EXTRACTO_V1", "BNB", "3000100152", "BOB")        # cuenta ya registrada


# ------------------------------- 6. CASOS SINTÉTICOS (antes: equivalencia con el legado) -------------------------
def test_bnb_orden_descendente_valida_saldos(generico, tmp_path):
    """BNB suele venir de más reciente a más antiguo: la validación se ordena cronológicamente (saldo inicial
    reconstruido desde el movimiento más antiguo)."""
    ruta = crear_xlsx_bnb(tmp_path / "d.xlsx", "3000100705", [
        {"fecha": "03/08/2026", "hora": "09:00:00", "deb": 30.0, "saldo": 1170.0},
        {"fecha": "02/08/2026", "hora": "09:00:00", "cred": 70.0, "saldo": 1200.0},
        {"fecha": "01/08/2026", "hora": "09:00:00", "cred": 100.0, "saldo": 1130.0}])
    df, val, _ = _procesar(generico, ruta, "BNB_CLINICA", "d.xlsx")
    assert len(df) == 3 and val["ESTADO"] == "OK"
    assert (val["SALDO INICIAL"], val["SALDO FINAL"]) == (1030.0, 1170.0)


@pytest.mark.parametrize("filas,esperado", [
    ([{"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0}], [(100.0, "CRÉDITO")]),
    ([{"fecha": "01/08/2026", "deb": 5.5, "saldo": 994.5}, {"fecha": "01/08/2026", "hora": "11:00:00", "cred": 5.5, "saldo": 1000.0}],
     [(5.5, "DÉBITO"), (5.5, "CRÉDITO")]),
    ([{"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0}, {"fecha": "no es fecha", "cred": 5.0, "saldo": 5.0}],
     [(100.0, "CRÉDITO")]),                  # la fila sin fecha interpretable se descarta (comportamiento D-07)
], ids=["un_credito", "debito_y_credito", "fila_sin_fecha_interpretable"])
def test_bnb_sinteticos(generico, tmp_path, filas, esperado):
    ruta = crear_xlsx_bnb(tmp_path / "s.xlsx", "3000100705", filas)
    df, val, _ = _procesar(generico, ruta, "BNB_CLINICA", "s.xlsx")
    assert list(zip(df["IMPORTE"], df["TIPO MOVIMIENTO"])) == esperado
    assert val["ESTADO"] == "OK"


# ------------------------------- 7. EL REGISTRO GOBIERNA LA NORMALIZACIÓN -------------------------------
CASOS_REGISTRO = {
    "etiqueta_info_bisa": ("BISA_MN", lambda d: d["FORMATOS"]["BISA_EXTRACTO_V1"]["info_adicional"]["partes"][1].update(etiqueta="Suc"),
                           {"INFORMACIÓN ADICIONAL", "TEXTO DE BÚSQUEDA"}),
    "moneda_bnb_mn": ("BNB_MN", lambda d: [c.update(moneda="USD") for c in d["CUENTAS"] if c["id"] == "BNB_MN"],
                      {"MONEDA"}),
    "depositante_bnb_vacio": ("BNB_MN", lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["depositante"].update(estrategia="VACIO"),
                              {"DEPOSITANTE / ORIGINANTE", "TEXTO DE BÚSQUEDA"}),
    "bcp_sin_excluir_saldos": ("BCP_MN", lambda d: d["FORMATOS"]["BCP_EXTRACTO_V1"].update(filas_excluir=[]),
                               "(filas)"),
    "eco_filtro_fecha": ("ECO_CTA_CTE", lambda d: d["FORMATOS"]["ECO_EXTRACTO_V1"].update(filtro_fecha="PANDAS_DAYFIRST"),
                         "(filas)"),
    "bmsc_separador_info": ("BMSC", lambda d: d["FORMATOS"]["BMSC_EXCEL_V1"]["info_adicional"].update(separador=" / "),
                            {"INFORMACIÓN ADICIONAL", "TEXTO DE BÚSQUEDA"}),
}


@pytest.mark.parametrize("nombre", list(CASOS_REGISTRO))
def test_un_cambio_del_registro_cambia_exactamente_lo_que_describe(mg, registro, motor, normalizado, ruta_fixture, nombre):
    fm, fn, esperado = CASOS_REGISTRO[nombre]
    reg = mg.Registro(_mutar(registro, fn))
    assert reg.validar() == []
    df, _, _ = _procesar(mg.MotorGenerico(reg, motor), ruta_fixture(fm), fm, FIXTURES[fm])
    base, _ = normalizado[fm]
    df = df.drop(columns=["LOTE DE CARGA", "FECHA DE CARGA"])
    base = base.drop(columns=["LOTE DE CARGA", "FECHA DE CARGA"])
    if esperado == "(filas)":
        assert len(df) != len(base)
        return
    distintas = {c for c in base.columns if not df[c].equals(base[c])}
    assert distintas == esperado, distintas


def test_una_fuente_de_saldo_distinta_que_da_el_mismo_resultado_no_cambia_la_validacion(mg, registro, motor, normalizado, ruta_fixture):
    reg = mg.Registro(_mutar(registro, lambda d: d["FORMATOS"]["ECO_EXTRACTO_V1"]["saldo"].update(
        final={"fuente": "ULTIMA_FILA"}, inicial={"fuente": "RECONSTRUIDO"})))
    _, val, _ = _procesar(mg.MotorGenerico(reg, motor), ruta_fixture("ECO_CTA_CTE"), "ECO_CTA_CTE")
    _, base = normalizado["ECO_CTA_CTE"]
    assert val["ESTADO"] == base["ESTADO"] == "OK"
    assert round(val["SALDO FINAL"], 2) == round(base["SALDO FINAL"], 2)


def test_una_fuente_de_saldo_equivocada_rompe_la_validacion(mg, registro, motor, ruta_fixture):
    reg = mg.Registro(_mutar(registro, lambda d: d["FORMATOS"]["BISA_EXTRACTO_V1"]["saldo"].update(
        inicial={"fuente": "CELDA_FIJA", "fila": 9, "columna": 7})))
    _, val, _ = _procesar(mg.MotorGenerico(reg, motor), ruta_fixture("BISA_MN"), "BISA_MN")
    assert val["ESTADO"] != "OK"


# ------------------------------- 8. INTEGRACIÓN -------------------------------
def test_lote_la_produccion_generica_es_identica_a_la_dorada_del_legado(corrida_lote):
    """LISTS.csv y NORMALIZADO.xlsx productivos (motor genérico) = doradas generadas con el motor ORIGINAL."""
    from helpers import leer_csv_texto
    res, salida = corrida_lote
    pd.testing.assert_frame_equal(leer_csv_texto(salida / "LISTS.csv"), leer_csv_texto(GOLDEN / "LOTE_12_LISTS.csv"))
    x = pd.read_excel(salida / "NORMALIZADO.xlsx", sheet_name="LISTS", dtype=str)
    x = x.drop(columns=["LOTE DE CARGA", "FECHA DE CARGA"])
    e = pd.read_csv(GOLDEN / "LOTE_12_NORMALIZADO__LISTS.csv", dtype=str, keep_default_na=False).drop(
        columns=["LOTE DE CARGA", "FECHA DE CARGA"], errors="ignore")
    assert list(x.columns) == list(e.columns) and len(x) == len(e) == 4064
    assert x["CLAVE TRANSACCIÓN"].tolist() == e["CLAVE TRANSACCIÓN"].tolist()
    assert {p.name for p in salida.iterdir()} == {"LISTS.csv", "NORMALIZADO.xlsx", "ORIGEN.xlsx"}   # P6: sin SOMBRA_*


# Subconjunto de extractos pequeños: las variantes de integración corren el motor completo varias veces.
PEQUENO = ("BNB_ME", "BCP_ME", "BISA_ME", "BISA_MN", "ECO_AHORRO", "BMSC", "BNB_CLINICA", "BNB_AHORRO", "UNION_MN")


def _correr(motor, base, registro_env=None):
    ent, sal = base / "in", base / "out"
    ent.mkdir(parents=True)
    for fm in PEQUENO:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: FIJO))
        if registro_env is not None:
            mp.setenv("CBBA_REGISTRO_BANCOS", str(registro_env))
        else:
            mp.delenv("CBBA_REGISTRO_BANCOS", raising=False)
        return motor.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx")), sal


@pytest.fixture(scope="module")
def base_pequena(motor, tmp_path_factory):
    """Línea base: producción con el registro del repositorio (mismo reloj fijo)."""
    return _correr(motor, tmp_path_factory.mktemp("base_pequena"))


def _registro_alterado(registro, tmp_path, fn):
    ruta = tmp_path / "registro_alterado.json"
    ruta.write_text(json.dumps(_mutar(registro, fn), ensure_ascii=False), encoding="utf-8")
    return ruta


def test_el_registro_gobierna_la_normalizacion_productiva(motor, registro, tmp_path, base_pequena):
    """Un dato de NORMALIZACIÓN del registro (separador de INFORMACIÓN ADICIONAL de BMSC) cambia la producción
    solo en ese archivo y esas columnas."""
    ruta_reg = _registro_alterado(registro, tmp_path, lambda x: x["FORMATOS"]["BMSC_EXCEL_V1"]["info_adicional"].update(
        separador=" / "))
    base, _ = base_pequena
    con, _ = _correr(motor, tmp_path / "con", registro_env=ruta_reg)
    bmsc = con["df_final"]["ARCHIVO ORIGEN"] == "mercantil_1.xls"
    assert bmsc.any() and con["df_final"][bmsc]["INFORMACIÓN ADICIONAL"].str.contains(" / ").all()
    variables = ["INFORMACIÓN ADICIONAL", "TEXTO DE BÚSQUEDA"]
    pd.testing.assert_frame_equal(con["df_final"].drop(columns=variables), base["df_final"].drop(columns=variables))
    pd.testing.assert_frame_equal(con["df_final"][~bmsc], base["df_final"][~bmsc])
    pd.testing.assert_frame_equal(con["df_validacion"], base["df_validacion"])


def test_la_identidad_sale_del_registro(motor, registro, tmp_path):
    """BANCO / CUENTA / MONEDA salen del registro (fuente única): otra MONEDA para BNB_ME cambia la producción."""
    ruta_reg = _registro_alterado(registro, tmp_path, lambda x: [c.update(moneda="BOB") for c in x["CUENTAS"]
                                                                 if c["id"] == "BNB_ME"])
    con, _ = _correr(motor, tmp_path / "con", registro_env=ruta_reg)
    bnb_me = con["df_final"][con["df_final"]["ARCHIVO ORIGEN"] == FIXTURES["BNB_ME"]]
    assert len(bnb_me) and set(bnb_me["MONEDA"]) == {"BOB"}


@pytest.mark.parametrize("caso,texto", [
    ("json_roto", "no es JSON válido"),
    ("registro_invalido", "CUENTAS vacío"),
    ("archivo_inexistente", "no se pudo leer el registro"),
])
def test_p4_sin_registro_valido_la_produccion_se_detiene_con_error_claro(motor, registro, tmp_path, caso, texto):
    """El registro es la fuente productiva: si falta o está roto, el proceso se detiene ANTES de escribir."""
    ruta = tmp_path / "r.json"
    if caso == "json_roto":
        ruta.write_text("{ roto", encoding="utf-8")
    elif caso == "registro_invalido":
        ruta.write_text(json.dumps(_mutar(registro, lambda d: d["CUENTAS"].clear())), encoding="utf-8")
    else:
        ruta = tmp_path / "no_existe.json"
    with pytest.raises(ValueError, match="PROCESO DETENIDO") as e:
        _correr(motor, tmp_path / "con", registro_env=ruta)
    assert texto in str(e.value)
    assert not (tmp_path / "con" / "out").exists()


def test_p5_registro_valido_para_detectar_pero_no_para_normalizar_detiene_la_produccion(motor, registro, tmp_path):
    """Un registro que sirve para DETECTAR pero no para NORMALIZAR (importe.modo de BNB inválido) detiene el proceso
    antes de escribir nada."""
    ruta = _registro_alterado(registro, tmp_path, lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["importe"].update(
        modo="OTRO"))
    with pytest.raises(ValueError, match="PROCESO DETENIDO") as e:
        _correr(motor, tmp_path / "con", registro_env=ruta)
    assert "inválido para normalizar" in str(e.value) and "importe.modo" in str(e.value)
    assert not (tmp_path / "con" / "out").exists()


def test_p5_motor_sin_motor_generico_al_lado_se_detiene_con_error_claro(tmp_path):
    """motor_generico.py es la normalización productiva: sin él el proceso se detiene antes de escribir nada."""
    d = tmp_path / "sin_generico"
    d.mkdir()
    for f in ("motor_control_depositos_cbba.py", "captura_origen.py", "deteccion_registro.py", "registro_bancos.json"):
        shutil.copy(REPO / f, d / f)
    spec = importlib.util.spec_from_file_location("motor_sin_generico", d / "motor_control_depositos_cbba.py")
    aislado = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aislado)
    with pytest.raises(ValueError, match="PROCESO DETENIDO: no se encuentra motor_generico.py"):
        _correr(aislado, tmp_path / "con")
    assert not (tmp_path / "con" / "out").exists()


def test_archivos_de_sombra_de_corridas_anteriores_no_se_toman_como_extractos(motor, tmp_path):
    """Una carpeta puede conservar SOMBRA_REPORTE.json / SOMBRA_DIFERENCIAS.csv de corridas P3-P5: no son extractos."""
    for n in ("SOMBRA_REPORTE.json", "SOMBRA_DIFERENCIAS.csv"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    shutil.copy(EXTRACTOS / FIXTURES["BNB_ME"], tmp_path / "bnb.xls")
    assert set(motor.descubrir_archivos(str(tmp_path))) == {"bnb.xls"}
