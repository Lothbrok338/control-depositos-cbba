"""P0 · el control del año del motor ya no esta fijo en 2026 (antes: D-08).

Que protege el control: que una fecha mal interpretada (año de 2 digitos, texto ilegible) no entre como movimiento.
Regla equivalente y dinamica: ANIO_MINIMO_DATOS (2026, primer año de operacion; no vence) <= año <= año de la fecha
del equipo. Un extracto que cruza diciembre/enero es valido. El reloj se fija en las pruebas con `fecha_referencia`."""
import pandas as pd
import pytest

from helpers import crear_xlsx_bnb

pytestmark = pytest.mark.p0

CUENTA = "3000100705"  # BNB_CLINICA


def _hoy(motor, monkeypatch, fecha):
    monkeypatch.setattr(motor, "fecha_referencia", lambda: pd.Timestamp(fecha))


# ------------------------------------------------------------------ funcion pura
@pytest.mark.parametrize("anio", [2026, 2027, 2028, 2030, 2035, 2050])
def test_cualquier_año_razonable_es_valido_cuando_el_equipo_ya_esta_en_ese_año(motor, anio):
    assert motor.anios_fuera_de_rango([anio], hoy=pd.Timestamp(f"{anio}-03-15")) == []


@pytest.mark.parametrize("anio", [2026, 2027, 2028])
def test_el_año_corriente_y_los_anteriores_hasta_el_minimo_son_validos(motor, anio):
    assert motor.anios_fuera_de_rango(range(2026, anio + 1), hoy=pd.Timestamp(f"{anio}-12-31")) == []


def test_rechaza_años_anteriores_al_primer_año_de_operacion(motor):
    assert motor.anios_fuera_de_rango([2025, 1926, 26], hoy=pd.Timestamp("2027-01-01")) == [26, 1926, 2025]


def test_rechaza_años_futuros_respecto_del_equipo(motor):
    # fecha mal interpretada (p. ej. 2062 por un año de 2 digitos) o equipo con fecha atrasada
    assert motor.anios_fuera_de_rango([2026, 2062], hoy=pd.Timestamp("2026-10-08")) == [2062]
    assert motor.anios_fuera_de_rango([2027], hoy=pd.Timestamp("2026-12-31")) == [2027]


def test_acepta_floats_de_pandas(motor):
    assert motor.anios_fuera_de_rango([2026.0, 2027.0], hoy=pd.Timestamp("2027-06-01")) == []


def test_sin_fecha_de_referencia_usa_el_reloj_del_equipo(motor):
    assert motor.anios_fuera_de_rango([pd.Timestamp.now().year]) == []
    assert motor.anios_fuera_de_rango([pd.Timestamp.now().year + 1]) == [pd.Timestamp.now().year + 1]


# ------------------------------------------------------------------ de punta a punta (ejecutar_motor)
def _extracto(ruta, filas):
    return crear_xlsx_bnb(ruta, CUENTA, filas)


@pytest.mark.parametrize("anio", [2026, 2027, 2028])
def test_motor_acepta_el_año(motor, tmp_path, monkeypatch, anio):
    _hoy(motor, monkeypatch, f"{anio}-06-30")
    ent = tmp_path / "in"; ent.mkdir()
    _extracto(ent / "x.xlsx", [{"fecha": f"05/01/{anio}", "cred": 100.0, "saldo": 1100.0, "cod": "11"},
                              {"fecha": f"06/01/{anio}", "cred": 50.0, "saldo": 1150.0, "cod": "12"}])
    res = motor.ejecutar_motor(str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx"))
    assert len(res["df_final"]) == 2
    assert set(res["df_final"]["FECHA MOVIMIENTO"].dt.year) == {anio}


def test_motor_acepta_extracto_que_cruza_diciembre_y_enero(motor, tmp_path, monkeypatch):
    _hoy(motor, monkeypatch, "2027-01-10")  # antes de P0 esto bloqueaba toda la exportacion
    ent = tmp_path / "in"; ent.mkdir()
    _extracto(ent / "x.xlsx", [{"fecha": "30/12/2026", "cred": 100.0, "saldo": 1100.0, "cod": "11"},
                              {"fecha": "02/01/2027", "cred": 50.0, "saldo": 1150.0, "cod": "12"}])
    res = motor.ejecutar_motor(str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx"))
    assert sorted(res["df_final"]["FECHA MOVIMIENTO"].dt.year.unique()) == [2026, 2027]


def test_motor_bloquea_año_futuro_y_nombra_el_rango(motor, tmp_path, monkeypatch):
    _hoy(motor, monkeypatch, "2026-10-08")
    ent = tmp_path / "in"; ent.mkdir()
    _extracto(ent / "x.xlsx", [{"fecha": "05/01/2062", "cred": 100.0, "saldo": 1100.0}])
    with pytest.raises(ValueError, match=r"rango válido 2026–2026.*\[2062\].*2026-10-08"):
        motor.ejecutar_motor(str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx"))
    assert not (tmp_path / "out" / "NORMALIZADO.xlsx").exists()  # no se escribe nada


def test_motor_bloquea_año_anterior_al_primer_año_de_operacion(motor, tmp_path, monkeypatch):
    _hoy(motor, monkeypatch, "2027-02-01")
    ent = tmp_path / "in"; ent.mkdir()
    _extracto(ent / "x.xlsx", [{"fecha": "05/01/2025", "cred": 100.0, "saldo": 1100.0}])
    with pytest.raises(ValueError, match=r"EXPORTACIÓN BLOQUEADA.*\[2025\]"):
        motor.ejecutar_motor(str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx"))
