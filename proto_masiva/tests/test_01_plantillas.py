"""Fixtures de los escenarios A-E (generar_xlsx.py): 9 columnas, sin TIPO_CAMBIO y cuentas 100 % inventadas.

Las plantillas DEFINITIVAS (Plantilla / Ejemplo) se prueban en test_05_plantillas_produccion.py.
"""
from pathlib import Path

import pytest
from openpyxl import load_workbook

from proto_masiva.contrato_plantilla import ENCABEZADOS

XLSX = Path(__file__).resolve().parents[1] / "xlsx"
FIXTURES = ("01_OK_3filas.xlsx", "02a_TABLA_VACIA_1fila_en_blanco.xlsx", "02b_TABLA_SOLO_ENCABEZADO.xlsx",
            "03_SIN_TABLA.xlsx", "04_TABLA_NOMBRE_DISTINTO.xlsx", "05_ENCABEZADO_CAMBIADO.xlsx")


@pytest.mark.parametrize("nombre", FIXTURES)
def test_fixtures_tienen_9_columnas_sin_TIPO_CAMBIO(nombre):
    ws = load_workbook(XLSX / nombre)["CARGA"]
    encabezados = tuple(c.value for c in ws[1] if c.value is not None)
    assert len(encabezados) == 9 and "TIPO_CAMBIO" not in encabezados
    if nombre.startswith("05_"):
        assert encabezados[1] == "CUENTA" and encabezados != ENCABEZADOS  # única variante intencionalmente distinta
    else:
        assert encabezados == ENCABEZADOS


@pytest.mark.parametrize("nombre", FIXTURES)
def test_fixtures_usan_solo_cuentas_inventadas(nombre):
    wb = load_workbook(XLSX / nombre)
    cuentas = {str(fila[1]) for hoja in wb.worksheets for fila in hoja.iter_rows(min_row=2, values_only=True) if fila[1]}
    assert all(c.startswith(("999", "0999", "9999")) for c in cuentas), cuentas


def test_los_fixtures_estan_situados_donde_los_leen_las_pruebas_de_escenarios():
    assert all((XLSX / n).exists() for n in FIXTURES)
