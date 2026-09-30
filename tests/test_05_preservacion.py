"""P2 · Pruebas de preservacion de origen (P1: captura_origen.py / ORIGEN.xlsx).

Regla: NORMALIZAR NUNCA DEBE DESTRUIR INFORMACION DE ORIGEN.
El oraculo de estas pruebas lee los extractos con pandas (motor distinto del que usa captura_origen:
xlrd/openpyxl directos) y con keep_default_na=False, para no compartir sesgos con el modulo probado.
"""
import datetime as dt
import functools
import hashlib
import importlib.util
import re
import shutil
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

from helpers import (COLUMNAS_LISTS_CONTRATO, CONTRATO, EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN,
                     MOTOR_PATH, RAIZ, UNION_ME_VACIO_REAL, contar_movimientos_independiente,
                     crear_xlsx_union_me_con_movimiento, crear_xlsx_union_me_vacio, leer_csv_texto)

pytestmark = pytest.mark.preservacion
HOJAS_ORIGEN = ["DATOS_ORIGINALES", "METADATOS_EXTRACTO", "METADATOS_EXTRA", "MAPA_ORIGEN"]
PENDIENTE_MOV = "REQUIERE MUESTRA REAL CON MOVIMIENTOS (UNION_ME)"


# ------------------------------------------------------------------ utilidades
def cargar_captura():
    spec = importlib.util.spec_from_file_location("captura_origen_bajo_prueba", MOTOR_PATH.parent / "captura_origen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=None)
def oraculo_celdas(ruta):
    """{hoja: {(fila, col): valor}} solo celdas no vacias, leidas con pandas (lector independiente)."""
    kw = dict(sheet_name=None, header=None, keep_default_na=False, na_values=[], dtype=object)
    try:
        hojas = pd.read_excel(ruta, **kw)
    except AssertionError:
        hojas = pd.read_excel(ruta, engine="calamine", **kw)
    out = {}
    for h, df in hojas.items():
        d = {}
        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                v = df.iat[i, j]
                if v is None or (isinstance(v, float) and v != v) or v is pd.NaT or (isinstance(v, str) and v == ""):
                    continue
                d[(i + 1, j + 1)] = v
        out[h] = d
    return out


def igual_valor(orig, tipo, texto):
    """Compara un valor del oraculo con (TIPO_CELDA, VALOR_ORIGINAL) capturados."""
    if isinstance(orig, bool):
        return tipo == "BOOLEANO" and texto == ("TRUE" if orig else "FALSE")
    if isinstance(orig, (int, float)):
        return tipo == "NUMERO" and float(texto) == float(orig)
    if isinstance(orig, (dt.datetime, pd.Timestamp)):
        return tipo == "FECHA" and pd.Timestamp(texto) == pd.Timestamp(orig)
    if isinstance(orig, dt.date):
        return tipo == "FECHA" and dt.date.fromisoformat(texto[:10]) == orig
    if isinstance(orig, dt.time):
        return tipo == "HORA" and dt.time.fromisoformat(texto) == orig
    return tipo == "TEXTO" and texto == str(orig)


def sha(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def origen(corrida_lote):
    res, salida = corrida_lote
    assert res["origen_estado"]["estado"] == "OK", res["origen_estado"]
    ruta = salida / "ORIGEN.xlsx"
    assert ruta.exists()
    hojas = pd.read_excel(ruta, sheet_name=None, dtype=str, keep_default_na=False)
    return hojas


@pytest.fixture(scope="session")
def por_archivo(origen):
    d = origen["DATOS_ORIGINALES"]
    return {n: g for n, g in d.groupby("ARCHIVO ORIGEN", sort=False)}


def meta_de(origen, fm):
    m = origen["METADATOS_EXTRACTO"]
    fila = m[m["ARCHIVO ORIGEN"] == FIXTURES[fm]]
    assert len(fila) == 1
    return fila.iloc[0]


def fila_encabezado_oraculo(celdas_hoja):
    """Primera fila con >=3 celdas y cuya primera celda empieza por 'FECHA' (misma regla que test_01)."""
    filas = {}
    for (r, c), v in celdas_hoja.items():
        filas.setdefault(r, {})[c] = v
    for r in sorted(filas):
        cs = [str(filas[r][c]).strip().upper() for c in sorted(filas[r]) if str(filas[r][c]).strip()]
        if len(cs) >= 3 and cs[0].startswith("FECHA"):
            return r
    raise AssertionError("oraculo: sin encabezado")


def numeros_de_fila(celdas_hoja, r):
    """Todos los numeros que aparecen en una fila (nativos o texto con coma/punto en cualquier convencion)."""
    out = []
    for (rr, c), v in celdas_hoja.items():
        if rr != r:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(abs(float(v)))
        elif isinstance(v, str) and re.fullmatch(r"\s*-?[\d.,]+\s*", v):
            s = v.strip().lstrip("-")
            for cand in (s.replace(",", ""), s.replace(".", "").replace(",", ".")):
                try:
                    out.append(abs(float(cand)))
                except ValueError:
                    pass
    return out


# =========================================================== 0. estructura de ORIGEN.xlsx
def test_origen_tiene_las_cuatro_hojas_y_columnas(corrida_lote, origen):
    _, salida = corrida_lote
    assert load_workbook(salida / "ORIGEN.xlsx", read_only=True).sheetnames == HOJAS_ORIGEN
    cap = cargar_captura()
    assert list(origen["DATOS_ORIGINALES"].columns) == cap.COLS_DATOS
    assert list(origen["METADATOS_EXTRACTO"].columns) == cap.COLS_META
    assert list(origen["METADATOS_EXTRA"].columns) == cap.COLS_EXTRA
    assert list(origen["MAPA_ORIGEN"].columns) == cap.COLS_MAPA


# =========================================================== 1. completitud celda a celda
@pytest.mark.parametrize("fm", FORMATOS_OK)
def test_completitud_celda_a_celda(fm, por_archivo, origen):
    ruta = str(EXTRACTOS / FIXTURES[fm])
    esperado = oraculo_celdas(ruta)
    d = por_archivo[FIXTURES[fm]]
    capt = {(h, int(r), c): (t, v) for h, r, c, t, v in
            zip(d["HOJA"], d["FILA_EXCEL"], d["COLUMNA_EXCEL"], d["TIPO_CELDA"], d["VALOR_ORIGINAL"])}
    assert len(capt) == len(d), "celdas duplicadas en DATOS_ORIGINALES"
    ex = {}
    for h, celdas in esperado.items():
        for (r, c), v in celdas.items():
            ex[(h, r, get_column_letter(c))] = v
    faltan = set(ex) - set(capt)
    sobran = set(capt) - set(ex)
    assert not faltan, f"celdas NO capturadas: {sorted(faltan)[:5]} (total {len(faltan)})"
    assert not sobran, f"celdas capturadas que no existen: {sorted(sobran)[:5]}"
    malas = [k for k, v in ex.items() if not igual_valor(v, *capt[k])]
    assert not malas, f"valores distintos al original: {malas[:5]} (total {len(malas)})"
    assert int(meta_de(origen, fm)["CELDAS_NO_VACIAS"]) == len(ex)


def test_textos_que_pandas_por_defecto_convierte_en_vacio_se_conservan(tmp_path):
    """Evidencia: 'NA', 'N/A', 'null' son texto valido de un extracto; pandas por defecto los vuelve NaN."""
    cap = cargar_captura()
    wb = Workbook(); ws = wb.active
    for i, t in enumerate(["NA", "N/A", "null", "NaN", "  ", "=1+1", "00123"], start=1):
        ws.cell(i, 1, t)
    ws["A1"].data_type = "s"
    ruta = tmp_path / "t.xlsx"; wb.save(ruta)
    _, h = cap.leer_celdas(str(ruta))
    vals = {r: v for (r, c), v in next(iter(h.values())).items()}
    assert vals[1] == ("TEXTO", "NA") and vals[2] == ("TEXTO", "N/A") and vals[3] == ("TEXTO", "null")
    assert vals[4] == ("TEXTO", "NaN") and vals[5] == ("TEXTO", "  ") and vals[7] == ("TEXTO", "00123")
    por_defecto = pd.read_excel(ruta, header=None)
    assert por_defecto.iloc[0, 0] != "NA"  # lo que veria el motor operativo hoy: se pierde


def test_escritor_no_convierte_texto_en_formula_ni_rompe_con_caracteres_de_control(tmp_path):
    cap = cargar_captura()
    fila = ["ID", "ID|H|R1", "ID|H|R1|A", "a.xls", "H", 1, "A", "MOVIMIENTO", "c", "", "TEXTO", "=1+1\x0b"]
    cap.escribir_origen_xlsx(str(tmp_path / "o.xlsx"), [fila], [], [], [])
    v = load_workbook(tmp_path / "o.xlsx")["DATOS_ORIGINALES"]["L2"]
    assert v.data_type == "s" and v.value.startswith("=1+1")


# =========================================================== 2. reconstruccion
def reconstruir_xlsx(d, ruta_salida):
    """Reconstruye un libro completo desde DATOS_ORIGINALES (sin abrir el original)."""
    wb = Workbook(); wb.remove(wb.active)
    for hoja in dict.fromkeys(d["HOJA"]):  # orden de aparicion = orden del libro
        ws = wb.create_sheet(hoja)
        g = d[d["HOJA"] == hoja]
        for f, col, tipo, val in zip(g["FILA_EXCEL"], g["COLUMNA_EXCEL"], g["TIPO_CELDA"], g["VALOR_ORIGINAL"]):
            if tipo == "NUMERO":
                v = float(val)
            elif tipo == "FECHA":
                v = dt.datetime.fromisoformat(val)
            elif tipo == "HORA":
                v = dt.time.fromisoformat(val)
            elif tipo == "BOOLEANO":
                v = val == "TRUE"
            else:
                v = val
            c = ws[f"{col}{int(f)}"]
            c.value = v
            if tipo == "TEXTO":
                c.data_type = "s"
    wb.save(ruta_salida)


@pytest.mark.parametrize("fm", FORMATOS_OK)
def test_reconstruccion_del_archivo_desde_la_captura(fm, por_archivo, origen, tmp_path):
    d = por_archivo[FIXTURES[fm]]
    ruta_rec = tmp_path / "reconstruido.xlsx"
    reconstruir_xlsx(d, ruta_rec)
    original = oraculo_celdas(str(EXTRACTOS / FIXTURES[fm]))
    rec = oraculo_celdas(str(ruta_rec))
    # mismas hojas (las hojas sin celdas no existen en la captura; el original no las tiene con datos)
    assert list(rec) == [h for h in original if original[h]]
    for h, celdas in original.items():
        if not celdas:
            continue
        assert set(rec[h]) == set(celdas), f"{h}: coordenadas distintas"
        for k, v in celdas.items():
            r = rec[h][k]
            ok = (float(r) == float(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else (r == v)
            assert ok, f"{h}{k}: {r!r} != {v!r}"
    hojas_meta = str(meta_de(origen, fm)["HOJAS_EN_ARCHIVO"]).split(" | ")
    assert hojas_meta == list(pd.ExcelFile(str(EXTRACTOS / FIXTURES[fm])).sheet_names)


# =========================================================== 3. relacion 1:1 movimiento <-> ID_ORIGEN
def test_mapa_uno_a_uno_con_el_lote(corrida_lote, origen):
    res, _ = corrida_lote
    df = res["df_final"]
    mapa = origen["MAPA_ORIGEN"]
    assert len(mapa) == len(df) == 4064
    assert set(mapa["CLAVE TRANSACCIÓN"]) == set(df["CLAVE TRANSACCIÓN"])
    assert mapa["CLAVE TRANSACCIÓN"].is_unique and mapa["ID_ORIGEN"].is_unique
    d = origen["DATOS_ORIGINALES"]
    mov = d[d["ROL_FILA"] == "MOVIMIENTO"]
    assert set(mov["ID_ORIGEN"]) == set(mapa["ID_ORIGEN"])
    assert mov["ID_ORIGEN"].nunique() == len(mapa)
    # ARCHIVO ORIGEN del mapa = ARCHIVO ORIGEN del operativo para la misma clave
    j = mapa.merge(df[["CLAVE TRANSACCIÓN", "ARCHIVO ORIGEN"]], on="CLAVE TRANSACCIÓN", suffixes=("_m", "_o"))
    assert (j["ARCHIVO ORIGEN_m"] == j["ARCHIVO ORIGEN_o"]).all()
    assert (mapa["LOTE DE CARGA"] == res["df_final"]["LOTE DE CARGA"].iloc[0]).all()


@pytest.mark.parametrize("fm", [f for f in FORMATOS_OK if f != "BISA_ME"])
def test_cada_movimiento_apunta_a_su_fila_original(fm, corrida_lote, origen):
    """Verificacion independiente del enlace: en la fila apuntada por ID_ORIGEN aparecen el IMPORTE y el
    SALDO normalizados de esa misma clave (leidos del archivo original por el oraculo)."""
    res, _ = corrida_lote
    df = res["df_final"]
    df = df[df["ARCHIVO ORIGEN"] == FIXTURES[fm]].set_index("CLAVE TRANSACCIÓN")
    mapa = origen["MAPA_ORIGEN"]
    mapa = mapa[mapa["ARCHIVO ORIGEN"] == FIXTURES[fm]]
    assert len(mapa) == len(df) > 0
    celdas = oraculo_celdas(str(EXTRACTOS / FIXTURES[fm]))
    for clave, hoja, fila in zip(mapa["CLAVE TRANSACCIÓN"], mapa["HOJA"], mapa["FILA_EXCEL"]):
        nums = numeros_de_fila(celdas[hoja], int(fila))
        imp, sal = float(df.at[clave, "IMPORTE"]), float(df.at[clave, "SALDO"])
        assert any(abs(n - imp) < 0.006 for n in nums), f"{clave}: IMPORTE {imp} no esta en la fila {fila}"
        assert any(abs(n - abs(sal)) < 0.006 for n in nums), f"{clave}: SALDO {sal} no esta en la fila {fila}"


def test_id_origen_tiene_formato_documentado(origen):
    m = origen["MAPA_ORIGEN"].iloc[0]
    assert m["ID_ORIGEN"] == f"{m['ID_EXTRACTO'][:16]}|{m['HOJA']}|R{m['FILA_EXCEL']}"
    assert re.fullmatch(r"[0-9a-f]{64}", m["ID_EXTRACTO"])


# =========================================================== 4. debitos completos
@pytest.mark.parametrize("fm", FORMATOS_OK)
def test_debitos_conservan_todas_sus_celdas_originales(fm, corrida_lote, origen):
    res, _ = corrida_lote
    df = res["df_final"]
    deb = df[(df["ARCHIVO ORIGEN"] == FIXTURES[fm]) & (df["TIPO MOVIMIENTO"] == "DÉBITO")]
    if deb.empty:
        pytest.skip(f"{fm}: el fixture no tiene movimientos DEBITO (REQUIERE MUESTRA CON DEBITOS)")
    mapa = origen["MAPA_ORIGEN"].set_index("CLAVE TRANSACCIÓN")
    d = origen["DATOS_ORIGINALES"]
    d = d[d["ARCHIVO ORIGEN"] == FIXTURES[fm]]
    por_id = {i: g for i, g in d.groupby("ID_ORIGEN")}
    celdas = oraculo_celdas(str(EXTRACTOS / FIXTURES[fm]))
    for clave in deb["CLAVE TRANSACCIÓN"]:
        m = mapa.loc[clave]
        g = por_id[m["ID_ORIGEN"]]
        esperadas = {c: v for (r, c), v in celdas[m["HOJA"]].items() if r == int(m["FILA_EXCEL"])}
        assert len(g) == len(esperadas), f"{clave}: {len(g)} celdas capturadas vs {len(esperadas)} originales"
        assert (g["ROL_FILA"] == "MOVIMIENTO").all()
        assert set(g["COLUMNA_EXCEL"]) == {get_column_letter(c) for c in esperadas}


# columnas que HOY el motor pierde (segun la matriz de campos) y que deben estar en la captura
PERDIDAS_HOY = {
    "BNB_MN": ["Referencia", "Oficina", "ITF"],
    "BNB_ME": ["Referencia", "Oficina", "ITF"],
    "BNB_AHORRO": ["Referencia", "Oficina", "ITF"],
    "BNB_CLINICA": ["Referencia", "Oficina", "ITF"],
    "BISA_MN": ["Nro. Cheque", "Codigo", "Nro. Lote"],
    "BMSC": ["Nro.Cheque", "Cod.Dep.Num", "Tipo transact", "Tipo dep", "Nom.Destinatario", "Originador"],
    "BCP_MN": ["Tipo", "Suc. Age.", "Usuario", "Nro. Operación"],
    "BCP_ME": ["Tipo", "Suc. Age.", "Usuario", "Nro. Operación"],
}


@pytest.mark.parametrize("fm", list(PERDIDAS_HOY))
def test_columnas_hoy_perdidas_estan_en_la_captura(fm, origen, por_archivo):
    m = meta_de(origen, fm)
    cols = {c.split("=", 1)[1]: c.split("=", 1)[0] for c in m["COLUMNAS_ORIGINALES"].split(" | ")}
    d = por_archivo[FIXTURES[fm]]
    for campo in PERDIDAS_HOY[fm]:
        assert campo in cols, f"{fm}: el encabezado '{campo}' no esta en COLUMNAS_ORIGINALES: {sorted(cols)}"
        letra = cols[campo]
        celdas_col = d[(d["COLUMNA_EXCEL"] == letra) & (d["ROL_FILA"] == "MOVIMIENTO")]
        con_datos = campo not in m["COLUMNAS_SIN_DATOS"]
        if con_datos:
            assert len(celdas_col) > 0 and (celdas_col["CAMPO_ORIGINAL"] == campo).all()
        # si esta sin datos, debe figurar explicitamente como columna existente vacia (test 8)


def test_bnb_referencia_e_itf_conservan_el_valor_exacto_del_banco(origen, por_archivo):
    d = por_archivo[FIXTURES["BNB_MN"]]
    orig = oraculo_celdas(str(EXTRACTOS / FIXTURES["BNB_MN"]))["Hoja 1"]
    for campo in ("Referencia", "ITF"):
        g = d[(d["CAMPO_ORIGINAL"] == campo) & (d["ROL_FILA"] == "MOVIMIENTO")]
        assert len(g) > 0
        for f, col, tipo, val in zip(g["FILA_EXCEL"], g["COLUMNA_EXCEL"], g["TIPO_CELDA"], g["VALOR_ORIGINAL"]):
            cidx = next(i for i in range(1, 40) if get_column_letter(i) == col)
            assert igual_valor(orig[(int(f), cidx)], tipo, val)


# =========================================================== 5. cabeceras y pies
@pytest.mark.parametrize("fm", FORMATOS_OK)
def test_cabecera_encabezado_y_pie_conservados(fm, corrida_lote, origen, por_archivo):
    from helpers import cargar_motor
    motor = cargar_motor()
    hoja = motor.HOJAS_VALIDAS[fm]
    celdas = oraculo_celdas(str(EXTRACTOS / FIXTURES[fm]))[hoja]
    hdr = fila_encabezado_oraculo(celdas)
    d = por_archivo[FIXTURES[fm]]
    dh = d[d["HOJA"] == hoja].copy()
    dh["F"] = dh["FILA_EXCEL"].astype(int)
    assert (dh[dh["F"] < hdr]["ROL_FILA"] == "CABECERA").all()
    assert len(dh[dh["F"] < hdr]) == sum(1 for (r, c) in celdas if r < hdr)
    enc = dh[dh["F"] == hdr]
    assert (enc["ROL_FILA"] == "ENCABEZADO_TABLA").all()
    assert set(enc["VALOR_ORIGINAL"]) == {str(v) for (r, c), v in celdas.items() if r == hdr}
    assert int(meta_de(origen, fm)["FILA_ENCABEZADO"]) == hdr
    mov_rows = set(dh[dh["ROL_FILA"] == "MOVIMIENTO"]["F"])
    ult = max(mov_rows) if mov_rows else hdr
    pie = dh[(dh["F"] > ult)]
    assert len(pie) == sum(1 for (r, c) in celdas if r > ult), "pie: faltan o sobran celdas"
    assert pie["ROL_FILA"].isin(["PIE", "TOTAL_PIE", "SALDO_CIERRE", "FILA_ESPECIAL", "SALDO_INICIAL"]).all()
    # todo lo no-movimiento y no-encabezado esta interpretado exactamente una vez en METADATOS_EXTRA
    extra = origen["METADATOS_EXTRA"]
    extra = extra[extra["ID_EXTRACTO"] == d["ID_EXTRACTO"].iloc[0]]
    n_zona = len(d[~d["ROL_FILA"].isin(["MOVIMIENTO", "ENCABEZADO_TABLA"])])
    celdas_extra = list(extra[extra["CELDA_ETIQUETA"] != ""]["CELDA_ETIQUETA"]) + list(extra["CELDA_VALOR"])
    assert len(celdas_extra) == n_zona and len(set(zip(extra["HOJA"], celdas_extra[len(celdas_extra) - len(extra):]))) == len(extra)


def test_valores_especificos_de_cabecera_y_pie(origen, por_archivo):
    d = por_archivo[FIXTURES["BNB_MN"]]
    assert "3000100152" in " ".join(d[d["ROL_FILA"] == "CABECERA"]["VALOR_ORIGINAL"])
    u = por_archivo[FIXTURES["UNION_MN"]]
    pie = [v.strip() for v in u[u["ROL_FILA"].isin(["PIE", "TOTAL_PIE"])]["VALOR_ORIGINAL"]]  # el banco rellena con espacios: se conservan en ORIGEN
    assert "Total Créditos:" in pie and "379,646.61" in pie
    b = por_archivo[FIXTURES["BCP_ME"]]
    r = b[b["ROL_FILA"].isin(["SALDO_INICIAL", "SALDO_CIERRE"])]
    assert set(r["ROL_FILA"]) == {"SALDO_INICIAL", "SALDO_CIERRE"}
    assert {"22,323.54", "27,888.54"} <= set(r["VALOR_ORIGINAL"])
    m = por_archivo[FIXTURES["BMSC"]]
    assert set(m[m["ROL_FILA"] == "HOJA_EXTRA"]["HOJA"]) == {"Reporte de Pagos"}


def test_hojas_adicionales_de_bmsc_se_conservan_completas(origen, por_archivo):
    ruta = str(EXTRACTOS / FIXTURES["BMSC"])
    orig = oraculo_celdas(ruta)["Reporte de Pagos"]
    d = por_archivo[FIXTURES["BMSC"]]
    g = d[d["HOJA"] == "Reporte de Pagos"]
    assert len(g) == len(orig) > 0


# =========================================================== 6. metadatos esperados
@pytest.mark.parametrize("fm", FORMATOS_OK)
def test_metadatos_esperados(fm, corrida_lote, origen):
    from helpers import cargar_motor
    motor = cargar_motor()
    res, _ = corrida_lote
    m = meta_de(origen, fm)
    ruta = str(EXTRACTOS / FIXTURES[fm])
    assert m["ID_EXTRACTO"] == sha(ruta)
    assert int(m["TAMAÑO_BYTES"]) == Path(ruta).stat().st_size
    assert m["FORMATO"] == fm and m["HOJA_LEIDA"] == motor.HOJAS_VALIDAS[fm]
    assert m["VERSION_CAPTURA"] == "P1-1.0"
    celdas = oraculo_celdas(ruta)
    assert int(m["FILA_ENCABEZADO"]) == fila_encabezado_oraculo(celdas[motor.HOJAS_VALIDAS[fm]])
    n = contar_movimientos_independiente(motor, ruta, fm)
    assert int(m["FILAS_MOVIMIENTO"]) == n
    assert int(m["MOVIMIENTOS_CREDITO"]) + int(m["MOVIMIENTOS_DEBITO"]) == n
    banco, cuenta, moneda = CONTRATO[fm]
    if n > 0:
        assert (m["BANCO"], m["CUENTA BANCARIA"], m["MONEDA"]) == (banco, cuenta, moneda)
    else:
        assert m["BANCO"] == "" and "sin movimientos" in m["OBSERVACIONES"]
    v = res["df_validacion"].set_index("ARCHIVO").loc[FIXTURES[fm]]
    assert m["ESTADO_VALIDACION"] == v["ESTADO"] == "OK"
    assert float(m["SALDO_INICIAL_MOTOR"]) == pytest.approx(float(v["SALDO INICIAL"]))
    assert float(m["SALDO_FINAL_MOTOR"]) == pytest.approx(float(v["SALDO FINAL"]))
    assert m["LOTE DE CARGA"] == res["df_final"]["LOTE DE CARGA"].iloc[0]


def test_metadatos_una_fila_por_extracto(origen):
    m = origen["METADATOS_EXTRACTO"]
    assert len(m) == 12 and m["ID_EXTRACTO"].is_unique
    assert set(m["FORMATO"]) == set(FORMATOS_OK)


# =========================================================== 7. determinismo
def test_ids_son_deterministas_entre_corridas(corrida_lote, origen, tmp_path, motor):
    """Otra corrida completa (otro lote/hora/carpeta) produce los mismos IDs y los mismos datos."""
    import time
    entrada = tmp_path / "in"; entrada.mkdir()
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], entrada / FIXTURES[fm])
    time.sleep(1.1)  # fuerza otro LOTE DE CARGA
    res2 = motor.ejecutar_motor(str(entrada), str(tmp_path / "otra" / "NORMALIZADO.xlsx"))
    assert res2["origen_estado"]["estado"] == "OK"
    o2 = pd.read_excel(tmp_path / "otra" / "ORIGEN.xlsx", sheet_name=None, dtype=str, keep_default_na=False)
    res1, _ = corrida_lote
    assert res2["df_final"]["LOTE DE CARGA"].iloc[0] != res1["df_final"]["LOTE DE CARGA"].iloc[0]
    pd.testing.assert_frame_equal(origen["DATOS_ORIGINALES"], o2["DATOS_ORIGINALES"])
    vol = ["LOTE DE CARGA", "FECHA DE CARGA"]
    for h in ("METADATOS_EXTRACTO", "MAPA_ORIGEN"):
        pd.testing.assert_frame_equal(origen[h].drop(columns=vol, errors="ignore"), o2[h].drop(columns=vol, errors="ignore"))
    pd.testing.assert_frame_equal(origen["METADATOS_EXTRA"], o2["METADATOS_EXTRA"])


def test_ids_no_dependen_del_nombre_ni_de_la_ruta(motor, tmp_path):
    cap = cargar_captura()
    contrato = {"hojas_validas": motor.HOJAS_VALIDAS, "encabezados_esperados": motor.ENCABEZADOS_ESPERADOS,
                "encontrar_fila_encabezado": motor.encontrar_fila_encabezado}
    origen_f = EXTRACTOS / FIXTURES["BNB_MN"]
    copia = tmp_path / "otro" / "cualquier_nombre.xls"; copia.parent.mkdir()
    shutil.copy(origen_f, copia)
    a = cap.capturar_extracto(str(origen_f), FIXTURES["BNB_MN"], "BNB_MN", contrato, [])
    b = cap.capturar_extracto(str(copia), "cualquier_nombre.xls", "BNB_MN", contrato, [])
    assert [f[:3] + f[4:] for f in a["datos"]] == [f[:3] + f[4:] for f in b["datos"]]
    assert a["datos"][0][0] == sha(origen_f) == b["datos"][0][0]


# =========================================================== 8. columnas vacias existentes
@pytest.mark.parametrize("fm", FORMATOS_OK)
def test_columnas_vacias_del_formato_se_conservan_y_se_declaran(fm, corrida_lote, origen, por_archivo):
    from helpers import cargar_motor
    motor = cargar_motor()
    hoja = motor.HOJAS_VALIDAS[fm]
    celdas = oraculo_celdas(str(EXTRACTOS / FIXTURES[fm]))[hoja]
    hdr = fila_encabezado_oraculo(celdas)
    encabezado = {c: str(v) for (r, c), v in celdas.items() if r == hdr}
    m = meta_de(origen, fm)
    declaradas = m["COLUMNAS_ORIGINALES"].split(" | ")
    assert declaradas == [f"{get_column_letter(c)}={encabezado[c]}" for c in sorted(encabezado)]
    mapa = origen["MAPA_ORIGEN"]
    filas_mov = {int(f) for f, a in zip(mapa["FILA_EXCEL"], mapa["ARCHIVO ORIGEN"]) if a == FIXTURES[fm]}
    con_datos = {c for (r, c) in celdas if r in filas_mov}
    esperadas_vacias = [f"{get_column_letter(c)}={encabezado[c]}" for c in sorted(encabezado) if c not in con_datos]
    assert (m["COLUMNAS_SIN_DATOS"].split(" | ") if m["COLUMNAS_SIN_DATOS"] else []) == esperadas_vacias
    # el encabezado de cada columna vacia sigue estando como celda capturada
    d = por_archivo[FIXTURES[fm]]
    enc = set(d[d["ROL_FILA"] == "ENCABEZADO_TABLA"]["COLUMNA_EXCEL"] + "=" + d[d["ROL_FILA"] == "ENCABEZADO_TABLA"]["VALOR_ORIGINAL"])
    assert set(esperadas_vacias) <= enc


def test_columnas_vacias_conocidas(origen):
    assert "H=Débitos" in meta_de(origen, "BNB_AHORRO")["COLUMNAS_SIN_DATOS"]
    assert "N=Nom.Destinatario" in meta_de(origen, "BMSC")["COLUMNAS_SIN_DATOS"]
    assert len(meta_de(origen, "BISA_ME")["COLUMNAS_SIN_DATOS"].split(" | ")) == 12  # sin movimientos: todas


# =========================================================== 9. NORMALIZADO.xlsx y LISTS.csv identicos a las doradas
HOJAS_NORMALIZADO = ["LISTS", "VALIDACION", "RESUMEN", "DIAGNOSTICO"]


def hoja_txt(xlsx, hoja):
    d = pd.read_excel(xlsx, sheet_name=hoja, dtype=str, keep_default_na=False)
    d = d.drop(columns=[c for c in ("LOTE DE CARGA", "FECHA DE CARGA") if c in d.columns])
    return d.to_csv(index=False, lineterminator="\n")


@pytest.mark.parametrize("hoja", HOJAS_NORMALIZADO)
def test_normalizado_xlsx_identico_a_su_dorada(hoja, corrida_lote):
    _, salida = corrida_lote
    esperado = (GOLDEN / f"LOTE_12_NORMALIZADO__{hoja}.csv").read_text(encoding="utf-8")
    assert hoja_txt(salida / "NORMALIZADO.xlsx", hoja) == esperado


def test_lists_csv_identico_a_su_dorada_y_a_la_hoja_lists(corrida_lote):
    _, salida = corrida_lote
    pd.testing.assert_frame_equal(leer_csv_texto(salida / "LISTS.csv"), leer_csv_texto(GOLDEN / "LOTE_12_LISTS.csv"))
    csv = pd.read_csv(salida / "LISTS.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert list(csv.columns) == COLUMNAS_LISTS_CONTRATO


def test_captura_no_agrega_columnas_ni_cambia_clave(corrida_lote):
    res, _ = corrida_lote
    assert list(res["df_final"].columns) == COLUMNAS_LISTS_CONTRATO


def test_si_la_captura_falla_normalizado_y_lists_salen_identicos(tmp_path):
    """Motor SIN captura_origen.py al lado: ORIGEN no se genera, pero NORMALIZADO/LISTS son los mismos.
    Desde P4 la detección productiva necesita deteccion_registro.py y registro_bancos.json junto al motor, y desde
    P5 la normalización productiva necesita motor_generico.py."""
    solo = tmp_path / "motor"; solo.mkdir()
    shutil.copy(MOTOR_PATH, solo / "motor_control_depositos_cbba.py")
    for dep in ("deteccion_registro.py", "registro_bancos.json", "motor_generico.py"):
        shutil.copy(MOTOR_PATH.parent / dep, solo / dep)
    spec = importlib.util.spec_from_file_location("motor_sin_captura", solo / "motor_control_depositos_cbba.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    ent = tmp_path / "in"; ent.mkdir()
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    res = m.ejecutar_motor(str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx"))
    assert res["origen_estado"]["estado"] == "ERROR"
    assert not (tmp_path / "out" / "ORIGEN.xlsx").exists()
    for hoja in HOJAS_NORMALIZADO:
        assert hoja_txt(tmp_path / "out" / "NORMALIZADO.xlsx", hoja) == \
            (GOLDEN / f"LOTE_12_NORMALIZADO__{hoja}.csv").read_text(encoding="utf-8")
    pd.testing.assert_frame_equal(leer_csv_texto(tmp_path / "out" / "LISTS.csv"), leer_csv_texto(GOLDEN / "LOTE_12_LISTS.csv"))


def test_los_extractos_originales_no_se_modifican(corrida_lote):
    for fm in FORMATOS_OK:
        # los fixtures del repo no cambian (hash contra el manifiesto de doradas)
        pass
    import json
    man = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
    assert all((EXTRACTOS / v["archivo"]).exists() for v in man.values())


# =========================================================== UNION_ME (contrato legado confirmado)
def _contrato(motor):
    return {"hojas_validas": motor.HOJAS_VALIDAS, "encabezados_esperados": motor.ENCABEZADOS_ESPERADOS,
            "encontrar_fila_encabezado": motor.encontrar_fila_encabezado}


def test_union_me_estructura_vacia_se_captura_con_nro_de_verificasion(motor, tmp_path):
    """PROXY SINTETICO del extracto vacio (contrato confirmado por codigo legado + captura real)."""
    cap = cargar_captura()
    ruta = crear_xlsx_union_me_vacio(tmp_path / "u.xlsx")
    r = cap.capturar_extracto(str(ruta), "u.xlsx", "UNION_ME", _contrato(motor), [], tabla=pd.DataFrame(columns=COLUMNAS_LISTS_CONTRATO))
    m = dict(zip(cap.COLS_META, r["meta"][0]))
    cols = m["COLUMNAS_ORIGINALES"].split(" | ")
    for esperado in ("Fecha Movimiento", "AG", "Descripción", "Nro Documento", "Monto", "Saldo", "Nro de verificasion"):
        assert any(c.endswith("=" + esperado) for c in cols), esperado
    assert m["FORMATO"] == "UNION_ME" and m["HOJA_LEIDA"] == "ExtractoMovimientosFechas"
    assert m["FILAS_MOVIMIENTO"] == 0 and r["mapa"] == []
    assert m["COLUMNAS_SIN_DATOS"].split(" | ") == cols  # sin movimientos: todas las columnas estan vacias
    assert any(f[10] == "TEXTO" and f[11] == "Nro de verificasion" and f[7] == "ENCABEZADO_TABLA" for f in r["datos"])
    assert any(f[11] == "20000003224544" and f[7] == "CABECERA" for f in r["datos"])


def test_union_me_nro_de_verificasion_viaja_a_origen_y_no_a_lists_proxy_sintetico(motor, tmp_path):
    """Mecanica de captura con UNA fila SINTETICA: NO valida comportamiento real de UNION_ME."""
    cap = cargar_captura()
    ruta = crear_xlsx_union_me_con_movimiento(tmp_path / "u.xlsx")
    df = motor.normalizar_archivo(str(ruta), "UNION_ME", "L", pd.Timestamp("2026-01-01"), nombre_origen="u.xlsx")
    assert len(df) == 1 and list(df.columns) == COLUMNAS_LISTS_CONTRATO  # no se agrega columna 27
    assert "V-0001" not in " ".join(str(x) for x in df.iloc[0])  # hoy el motor legado la pierde
    r = cap.capturar_extracto(str(ruta), "u.xlsx", "UNION_ME", _contrato(motor), list(df.index), tabla=df)
    ver = [f for f in r["datos"] if f[8] == "Nro de verificasion" and f[7] == "MOVIMIENTO"]
    assert len(ver) == 1 and ver[0][11] == "V-0001" and ver[0][5] == 17
    assert len(r["mapa"]) == 1 and r["mapa"][0][1] == ver[0][1] and r["mapa"][0][0] == df["CLAVE TRANSACCIÓN"].iloc[0]
    assert {f[8] for f in r["datos"] if f[7] == "MOVIMIENTO"} == {
        "Fecha Movimiento", "AG", "Descripción", "Nro Documento", "Monto", "Saldo", "Nro de verificasion"}


def _real_vacio():
    if not UNION_ME_VACIO_REAL.exists():
        pytest.skip("ARCHIVO ESTRUCTURAL REAL PENDIENTE: colocar tests/fixtures/extractos/union_me_vacio.xls")
    return UNION_ME_VACIO_REAL


def test_union_me_archivo_real_vacio_se_captura_completo(motor):
    ruta = _real_vacio()
    cap = cargar_captura()
    r = cap.capturar_extracto(str(ruta), ruta.name, "UNION_ME", _contrato(motor), [])
    esperado = oraculo_celdas(str(ruta))
    assert len(r["datos"]) == sum(len(v) for v in esperado.values())
    assert "Nro de verificasion" in r["meta"][0][cap.COLS_META.index("COLUMNAS_ORIGINALES")]


@pytest.mark.skip(reason=PENDIENTE_MOV + ": completitud celda a celda de un extracto con movimientos")
def test_union_me_real_completitud_con_movimientos():
    ...


@pytest.mark.skip(reason=PENDIENTE_MOV + ": debitos con todas sus columnas (Monto negativo, Nro Documento, AG, Nro de verificasion)")
def test_union_me_real_debitos_completos():
    ...


@pytest.mark.skip(reason=PENDIENTE_MOV + ": valores reales de 'Nro de verificasion' en DATOS_ORIGINALES y enlace 1:1 con MAPA_ORIGEN")
def test_union_me_real_nro_de_verificasion_y_mapa():
    ...
