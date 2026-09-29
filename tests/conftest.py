import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from helpers import EXTRACTOS, FIXTURES, FORMATOS_OK, RAIZ, cargar_motor

_RESULTADOS = []


@pytest.fixture(scope="session")
def motor():
    return cargar_motor()


@pytest.fixture(scope="session")
def ruta_fixture():
    return lambda formato: str(EXTRACTOS / FIXTURES[formato])


@pytest.fixture(scope="session")
def normalizado(motor):
    """Normaliza cada fixture valido una sola vez: {formato: (df, validacion)}."""
    ts = pd.Timestamp("2026-01-01 00:00:00")
    out = {}
    for fm in FORMATOS_OK:
        ruta = str(EXTRACTOS / FIXTURES[fm])
        df = motor.normalizar_archivo(ruta, fm, "LOTE_TEST", ts, nombre_origen=FIXTURES[fm])
        out[fm] = (df, motor.validar_archivo(ruta, fm, df))
    return out


@pytest.fixture(scope="session")
def corrida_lote(motor, tmp_path_factory):
    """Corre ejecutar_motor una vez con los 12 fixtures validos."""
    base = tmp_path_factory.mktemp("lote12")
    entrada, salida = base / "entrada", base / "salida"
    entrada.mkdir()
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], entrada / FIXTURES[fm])
    ruta = salida / "NORMALIZADO.xlsx"
    res = motor.ejecutar_motor(str(entrada), str(ruta))
    return res, salida


# ---- Recoleccion de resultados para el informe PASS/FAIL ----
def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        estado = report.outcome
        motivo = ""
        if hasattr(report, "wasxfail"):
            estado = "XFAIL" if report.outcome == "skipped" else "XPASS"
            motivo = report.wasxfail
        elif report.outcome == "failed" and "XPASS(strict)" in str(report.longrepr):
            estado, motivo = "XPASS", "el defecto ya no falla: quitar marca xfail"
        elif report.outcome == "failed":
            estado = "FAIL"
            motivo = str(report.longrepr).strip().splitlines()[-1][:300] if report.longrepr else ""
        elif report.outcome == "passed":
            estado = "PASS"
        elif report.outcome == "skipped":
            estado = "SKIP"
        _RESULTADOS.append({"id": report.nodeid, "estado": estado, "motivo": motivo})


def pytest_sessionfinish(session, exitstatus):
    d = RAIZ / "reports"
    d.mkdir(exist_ok=True)
    (d / "resultados.json").write_text(json.dumps(_RESULTADOS, ensure_ascii=False, indent=1), encoding="utf-8")
