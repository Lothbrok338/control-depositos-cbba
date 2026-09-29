"""Contrato de salida: 26 columnas y CLAVE TRANSACCION. Estas pruebas NO deben cambiar."""
import datetime as dt
import pandas as pd
import pytest
from helpers import COLUMNAS_LISTS_CONTRATO

pytestmark = pytest.mark.regresion


def test_columnas_lists_exactas(motor):
    assert motor.COLUMNAS_LISTS == COLUMNAS_LISTS_CONTRATO
    assert len(motor.COLUMNAS_LISTS) == 26


def test_clave_transaccion_formula_congelada(motor):
    fila = {"FECHA MOVIMIENTO": pd.Timestamp("2026-04-03"), "HORA MOVIMIENTO": "14:43:49",
            "BANCO": "BCP", "CUENTA BANCARIA": "301-5005684-3-97", "CÓDIGO DE ASIGNACIÓN": "123.0",
            "TIPO MOVIMIENTO": "CRÉDITO", "IMPORTE": 10.5, "SALDO": 100.0}
    assert motor.crear_clave(fila) == "BCP|301-5005684-3-97|20260403|144349|123|CRÉDITO|10.50|100.00"


def test_clave_sin_hora_ni_saldo(motor):
    fila = {"FECHA MOVIMIENTO": pd.Timestamp("2026-04-03"), "HORA MOVIMIENTO": "",
            "BANCO": "BANCO UNIÓN", "CUENTA BANCARIA": "1", "CÓDIGO DE ASIGNACIÓN": "9",
            "TIPO MOVIMIENTO": "DÉBITO", "IMPORTE": 1, "SALDO": float("nan")}
    assert motor.crear_clave(fila) == "BANCO UNIÓN|1|20260403||9|DÉBITO|1.00|"


@pytest.mark.parametrize("valor,esperado", [
    ("1,234.56", 1234.56), ("1.234,56", 1234.56), ("Bs 1.000,00", 1000.0), ("1234,5", 1234.5),
    ("-1,234.56", -1234.56), ("            236,880.41", 236880.41), (" 63.826,52", 63826.52),
    (25.0, 25.0), ("", None),
])
def test_numero_casos_validos(motor, valor, esperado):
    r = motor.numero(valor)
    assert (pd.isna(r) if esperado is None else abs(r - esperado) < 1e-9)


@pytest.mark.parametrize("valor,esperado", [
    ("01/Ago/2026", dt.date(2026, 8, 1)), ("24/08/2026", dt.date(2026, 8, 24)),
    ("17/08/26", dt.date(2026, 8, 17)), ("2026-08-24", dt.date(2026, 8, 24)),
    (pd.Timestamp("2026-08-24 10:00"), dt.date(2026, 8, 24)),
])
def test_normalizar_fecha_casos_validos(motor, valor, esperado):
    assert motor.normalizar_fecha(valor) == esperado


@pytest.mark.parametrize("valor,esperado", [
    ("9:05", "09:05:00"), ("14:43:49", "14:43:49"), (dt.time(9, 5), "09:05:00"),
    (pd.Timestamp("2026-01-01 09:05:33"), "09:05:33"),
])
def test_normalizar_hora_casos_validos(motor, valor, esperado):
    assert motor.normalizar_hora(valor) == esperado


def test_codigo_texto(motor):
    assert motor.codigo_texto(123.0) == "123"
    assert motor.codigo_texto("123.0") == "123"
    assert motor.codigo_texto("AB-1") == "AB-1"
