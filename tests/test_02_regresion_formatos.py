"""Regresion por banco/formato con extractos REALES. Un test por formato en cada propiedad."""
import re
import pandas as pd
import pytest
from helpers import (CONTRATO, ENCABEZADOS, FIXTURES, FORMATOS_OK, GOLDEN, HOJAS, a_texto,
                     contar_movimientos_independiente, leer_csv_texto, saldo_encadenado_ok)

pytestmark = pytest.mark.regresion
TODOS = list(FIXTURES)


@pytest.mark.parametrize("formato", TODOS)
def test_deteccion_formato(motor, ruta_fixture, formato):
    assert motor.detectar_formato(ruta_fixture(formato)) == formato


def _fila_encabezado(motor, raw, formato):
    """Fila de encabezado con los encabezados esperados del contrato (helpers.ENCABEZADOS): mayor puntaje,
    primera en empate. Desde P6 el motor ya no tiene encontrar_fila_encabezado / ENCABEZADOS_ESPERADOS."""
    return motor.normalizador_registro()._fila_encabezado(raw, ENCABEZADOS[formato])


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_hoja_y_encabezado_reales(motor, ruta_fixture, formato):
    hojas = motor.leer_todas_hojas(ruta_fixture(formato))
    assert HOJAS[formato] in hojas
    raw = hojas[HOJAS[formato]]
    fila, puntaje, total = _fila_encabezado(motor, raw, formato)
    assert puntaje == total, "el encabezado real debe coincidir con todos los encabezados esperados"
    det = motor.detectar_extracto(ruta_fixture(formato))
    assert (det.hoja, det.fila_encabezado) == (HOJAS[formato], fila)


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_contrato_banco_cuenta_moneda(normalizado, formato):
    df, _ = normalizado[formato]
    if len(df) == 0:
        pytest.skip("extracto sin movimientos: sin filas que verificar")
    banco, cuenta, moneda = CONTRATO[formato]
    assert set(df["BANCO"]) == {banco}
    assert set(df["CUENTA BANCARIA"]) == {cuenta}
    assert set(df["MONEDA"]) == {moneda}
    assert set(df["SEDE SOLICITANTE"]) == {"COCHABAMBA"}
    assert set(df["ESTADO"]) == {"DISPONIBLE"}
    assert set(df["ARCHIVO ORIGEN"]) == {FIXTURES[formato]}


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_igual_a_referencia_dorada(normalizado, formato):
    df, _ = normalizado[formato]
    actual = a_texto(df)
    esperado = (GOLDEN / f"{formato}.csv").read_text(encoding="utf-8")
    if actual != esperado:
        a, e = actual.splitlines(), esperado.splitlines()
        primera = next((i for i, (x, y) in enumerate(zip(a, e)) if x != y), min(len(a), len(e)))
        pytest.fail(f"difiere de la dorada: filas {len(a)-1} vs {len(e)-1}; primera diferencia en linea {primera+1}:\n"
                    f"  actual : {a[primera] if primera < len(a) else '<fin>'}\n"
                    f"  dorada : {e[primera] if primera < len(e) else '<fin>'}")


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_conteo_movimientos_oraculo_independiente(motor, ruta_fixture, normalizado, formato):
    df, _ = normalizado[formato]
    assert len(df) == contar_movimientos_independiente(motor, ruta_fixture(formato), formato)


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_saldo_encadenado_fila_a_fila(normalizado, formato):
    df, _ = normalizado[formato]
    ok, orden = saldo_encadenado_ok(df)
    assert ok, f"la cadena de saldos no cierra fila a fila (orden probado: {orden})"


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_validacion_de_saldos_ok(normalizado, formato):
    _, val = normalizado[formato]
    assert val["ESTADO"] == "OK" and abs(val["DIFERENCIA"]) <= 0.01


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_integridad_estructural(normalizado, formato):
    df, _ = normalizado[formato]
    assert not df["CLAVE TRANSACCIÓN"].duplicated().any()
    assert not (df["CÓDIGO DE ASIGNACIÓN"].fillna("") == "").any()
    assert df["IMPORTE"].notna().all() and (df["IMPORTE"] > 0).all()
    assert not (df["DÉBITO"].notna() & df["CRÉDITO"].notna()).any()
    assert set(df["TIPO MOVIMIENTO"]) <= {"CRÉDITO", "DÉBITO"}
    assert (pd.to_datetime(df["FECHA MOVIMIENTO"]).dt.year == 2026).all()


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_clave_consistente_con_columnas(motor, normalizado, formato):
    df, _ = normalizado[formato]
    for _, fila in df.head(50).iterrows():
        assert motor.crear_clave(fila) == fila["CLAVE TRANSACCIÓN"]


# --- Cuenta ubicada en cabecera y unica (hoy verdadero en datos reales) ---
@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_cuenta_real_aparece_en_cabecera_y_es_unica(motor, ruta_fixture, formato):
    todas = {c for _, c, _ in CONTRATO.values()}
    hojas = motor.leer_todas_hojas(ruta_fixture(formato))
    hoja = HOJAS[formato]
    raw = hojas[hoja]
    fila_hdr, _, _ = _fila_encabezado(motor, raw, formato)
    zona = " ".join(raw.iloc[:fila_hdr].fillna("").astype(str).values.flatten())
    zona = motor.normalizar_texto(zona)
    halladas = {c for c in todas if c in zona}
    assert halladas == {CONTRATO[formato][1]}


# --- Comportamiento actual con fixtures atipicos ---
def test_bisa_me_sin_movimientos_es_valido(normalizado):
    df, val = normalizado["BISA_ME"]
    assert len(df) == 0 and val["ESTADO"] == "OK"


def test_totales_pie_de_pagina_coinciden(normalizado):
    """Los totales impresos por el banco al pie deben igualar lo normalizado."""
    esperados = {"UNION_MN": 143466.20, "BISA_MN": 1139.00}
    for fm, total in esperados.items():
        df, _ = normalizado[fm]
        assert abs(df["CRÉDITO"].sum() - total) < 0.01, fm
        assert df["DÉBITO"].fillna(0).sum() == 0


# =====================  UNION_ME  (formato UNION_FECHAS_V1)  =====================
# ESTRUCTURA UNION_ME = CONFIRMADA por codigo legado (HOJAS_VALIDAS, ENCABEZADOS_ESPERADOS, detectar_formato y
# normalizar_union del motor original; desde P6 viven en registro_bancos.json) + captura real: hoja
# ExtractoMovimientosFechas, columnas
#   Fecha Movimiento | AG | Descripcion | Nro Documento | Monto | Saldo | Nro de verificasion   (cuenta 20000003224544)
# COMPORTAMIENTO CON MOVIMIENTOS = PENDIENTE de fixture real (la unica muestra disponible esta VACIA).
from helpers import UNION_ME_VACIO_REAL, UNION_ULTIMOS12, crear_xlsx_union_me_vacio

PENDIENTE_MOV = "REQUIERE MUESTRA REAL CON MOVIMIENTOS (UNION_ME)"


def test_union_ultimos12_no_es_fixture_de_union_me_y_se_rechaza(motor):
    """Negativo: el reporte 'Ultimos 12 Movimientos' (hoja ExtractoMovimientosUltimos) NO es un extracto
    UNION_ME valido. El motor debe rechazarlo con error visible, nunca normalizarlo en silencio."""
    assert UNION_ULTIMOS12.exists()
    with pytest.raises((ValueError, KeyError)):
        motor.normalizar_extracto(str(UNION_ULTIMOS12), "UNION_ME", "L", pd.Timestamp("2026-01-01"),
                                  nombre_origen="union_ultimos12.xls")


def _registro_union():
    import json
    from helpers import RAIZ
    d = json.loads((RAIZ.parent / "registro_bancos.json").read_text(encoding="utf-8"))
    cuentas = {c["id"]: c for c in d["CUENTAS"]}
    return cuentas, d["FORMATOS"][cuentas["UNION_ME"]["formato"]]


def test_union_me_contrato_legado_en_el_registro(motor):
    """Contrato legado autoritativo (antes constantes del motor; desde P6 solo en registro_bancos.json), comparado con
    el contrato congelado de las pruebas."""
    cuentas, fmt = _registro_union()
    assert cuentas["UNION_ME"]["formato"] == cuentas["UNION_MN"]["formato"] == "UNION_FECHAS_V1"   # compartido
    assert fmt["hojas_aceptadas"] == [HOJAS["UNION_ME"]] == ["ExtractoMovimientosFechas"]
    assert fmt["encabezados"]["puntaje"] == ENCABEZADOS["UNION_ME"] == ["FECHA MOVIMIENTO", "DESCRIPCION",
                                                                         "NRO DOCUMENTO", "MONTO", "SALDO"]
    assert "AG" not in fmt["encabezados"]["puntaje"]                                             # AG es opcional
    assert "NRO DE VERIFICASION" not in " ".join(fmt["encabezados"]["puntaje"])                  # no se exige
    assert "NRO DE VERIFICASION" not in [c.upper() for c in motor.COLUMNAS_LISTS]                # y no entra a las 26


def test_union_me_registro_asigna_cuenta_y_moneda():
    """El registro asigna cuenta 20000003224544 / USD a UNION_ME (antes en el codigo de normalizar_union)."""
    cuentas, fmt = _registro_union()
    c = cuentas["UNION_ME"]
    assert (c["banco"], c["cuenta"], c["moneda"]) == CONTRATO["UNION_ME"]
    assert fmt["campos"]["AG"]["requerido"] is False                                             # AG opcional
    alias = " ".join(a for cfg in fmt["campos"].values() for a in cfg.get("alias", []))
    assert "verificasion" not in alias.lower()          # no entra a las 26 columnas (va a ORIGEN e historico)


def test_union_me_estructura_proxy_sintetico_se_detecta(motor, tmp_path):
    """PROXY SINTETICO (no es el archivo real): hoja ExtractoMovimientosFechas + cuenta 20000003224544."""
    ruta = crear_xlsx_union_me_vacio(tmp_path / "u.xlsx")
    assert motor.detectar_formato(str(ruta)) == "UNION_ME"
    assert motor.detectar_extracto(str(ruta)).hoja == HOJAS["UNION_ME"] == "ExtractoMovimientosFechas"


def _real_vacio():
    if not UNION_ME_VACIO_REAL.exists():
        pytest.skip("ARCHIVO ESTRUCTURAL REAL PENDIENTE: colocar el extracto vacio en "
                    "tests/fixtures/extractos/union_me_vacio.xls")
    return str(UNION_ME_VACIO_REAL)


def test_union_me_fixture_estructural_real_detecta_y_tiene_hoja_y_columnas(motor):
    ruta = _real_vacio()
    assert motor.detectar_formato(ruta) == "UNION_ME"
    hojas = motor.leer_todas_hojas(ruta)
    assert "ExtractoMovimientosFechas" in hojas
    txt = motor.normalizar_texto(" ".join(hojas["ExtractoMovimientosFechas"].fillna("").astype(str).values.flatten()))
    for col in ["FECHA MOVIMIENTO", "AG", "DESCRIPCION", "NRO DOCUMENTO", "MONTO", "SALDO", "NRO DE VERIFICASION"]:
        assert col in txt, f"falta la columna {col} en la hoja"
    assert "20000003224544" in txt


def test_union_me_fixture_estructural_real_sin_movimientos_no_bloquea(motor):
    """Un UNION_ME sin movimientos debe tratarse como SIN MOVIMIENTOS (ver D-16b en test_04)."""
    ruta = _real_vacio()
    df, _ = motor.normalizar_extracto(ruta, "UNION_ME", "L", pd.Timestamp("2026-01-01"), nombre_origen="union_me_vacio.xls")
    assert len(df) == 0


@pytest.mark.skip(reason=PENDIENTE_MOV + ": normalizacion de movimientos, golden y conteo contra oraculo independiente")
def test_union_me_movimientos_normalizan():
    ...


@pytest.mark.skip(reason=PENDIENTE_MOV + ": validacion de saldos (inicial/final, cadena fila a fila, totales de pie)")
def test_union_me_saldos_validan():
    ...


@pytest.mark.skip(reason=PENDIENTE_MOV + ": debitos con todas sus columnas originales (Monto negativo, Nro Documento, "
                         "AG, Nro de verificasion)")
def test_union_me_debitos_conservan_campos():
    ...


@pytest.mark.skip(reason=PENDIENTE_MOV + ": 'Nro de verificasion' debe conservarse en DATOS_ORIGINALES y en EXTRACTO_HISTORICO "
                         "(hoy el motor NO lo lee: se pierde)")
def test_union_me_nro_de_verificasion_se_conserva():
    ...
