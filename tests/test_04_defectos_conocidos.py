"""DEFECTOS REALES diagnosticados. Cada test describe el comportamiento CORRECTO esperado y hoy FALLA
(xfail estricto). Al corregir el motor el test pasa -> pytest lo reporta como XPASS(strict) y hay que
quitar la marca. Codigos D-xx = numeracion de este informe.

Desde P5 los defectos de NORMALIZACION se prueban sobre la RUTA PRODUCTIVA (`normalizar_extracto`: motor
generico gobernado por registro_bancos.json), que es la que produce NORMALIZADO.xlsx / LISTS.csv. Los
normalizar_* legados ya no producen salida (solo referencia hasta P6)."""
import datetime as dt
import json
import os
import subprocess
import sys
import shutil

import pandas as pd
import pytest

from helpers import (EXTRACTOS, FIXTURES, MOTOR_PATH, crear_xlsx_bmsc_otra_cuenta, crear_xlsx_bnb)

pytestmark = pytest.mark.defecto


def defecto(codigo, texto):
    return pytest.mark.xfail(strict=True, reason=f"{codigo}: {texto}")


TS = pd.Timestamp("2026-01-01")


def normalizar_productivo(motor, ruta, cuenta_id, nombre="x.xlsx", normalizador=None):
    """P5: la normalizacion que produce la salida (motor generico + registro)."""
    df, _ = motor.normalizar_extracto(str(ruta), cuenta_id, "L", TS, nombre_origen=nombre, normalizador=normalizador)
    return df

# ------------------------------- NUMEROS -------------------------------
@defecto("D-01 NUMERO", "'1,234' (coma de miles sin decimales) se lee como 1.234 en vez de 1234")
def test_numero_coma_de_miles_sin_decimales(motor):
    assert motor.numero("1,234") == 1234.0


@defecto("D-02 NUMERO", "negativo entre parentesis '(1,234.56)' devuelve NaN")
def test_numero_negativo_entre_parentesis(motor):
    assert motor.numero("(1,234.56)") == -1234.56


@defecto("D-03 NUMERO", "miles con varios separadores y sin decimales '1.234.567' / '1,234,567' devuelven NaN")
def test_numero_miles_multiples(motor):
    assert motor.numero("1.234.567") == 1234567.0 and motor.numero("1,234,567") == 1234567.0


# ------------------------------- FECHAS / HORAS -------------------------------
@defecto("D-04 FECHA", "ISO '2026-04-03' con dayfirst=True se interpreta como 4 de marzo")
def test_fecha_iso_no_se_invierte(motor):
    assert motor.normalizar_fecha("2026-04-03") == dt.date(2026, 4, 3)


@defecto("D-05 HORA", "fraccion de dia de Excel (0.5) se devuelve como 0.5 en vez de '12:00:00'")
def test_hora_fraccion_de_dia_excel(motor):
    assert motor.normalizar_hora(0.5) == "12:00:00"


@defecto("D-06 FECHA", "el filtro de filas usa pd.to_datetime(dayfirst) y descarta EN SILENCIO fechas '24/Ago/2026' "
                       "(el Economico si las reconoce con normalizar_fecha): dos criterios distintos")
def test_bnb_fecha_con_mes_abreviado_no_se_pierde(motor, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "x.xlsx", "3000100705",
                          [{"fecha": "24/Ago/2026", "cred": 100.0, "saldo": 1100.0}])
    df = normalizar_productivo(motor, ruta, "BNB_CLINICA")
    assert len(df) == 1


@defecto("D-07 FILAS", "una fila con importe y fecha NO interpretable se descarta sin error ni conteo "
                       "(deberia bloquear o informar filas descartadas)")
def test_fila_con_importe_y_fecha_invalida_no_se_pierde_en_silencio(motor, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "x.xlsx", "3000100705", [
        {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0},
        {"fecha": "32/13/2026", "cred": 50.0, "saldo": 1150.0},
    ])
    with pytest.raises(ValueError):
        normalizar_productivo(motor, ruta, "BNB_CLINICA")


@defecto("D-08 AÑO", "el año 2026 esta fijo: un movimiento de 2027 bloquea toda la exportacion")
def test_movimiento_de_2027_no_bloquea(motor, tmp_path):
    ent = tmp_path / "in"; ent.mkdir()
    crear_xlsx_bnb(ent / "x.xlsx", "3000100705", [{"fecha": "05/01/2027", "cred": 100.0, "saldo": 1100.0}])
    res = motor.ejecutar_motor(str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx"))
    assert len(res["df_final"]) == 1


# ------------------------------- ENCABEZADO -------------------------------
# D-09: CORREGIDO EN P5 (ruta productiva cerrada ya en P4 por la deteccion). La normalizacion productiva (motor
# generico) exige encabezados.puntaje_minimo del registro antes de leer la tabla. La primitiva legada
# encontrar_fila_encabezado sigue igual, pero ya no interviene en la salida (solo referencia; se retira en P6).
def _hoja_bnb(ruta, filas):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Hoja 1"
    for f in filas:
        ws.append(f)
    wb.save(ruta)
    return ruta


def test_encabezado_sin_coincidencias_debe_fallar(motor, tmp_path):
    """D-09 (corregido en P5): sin ninguna fila de encabezado reconocible la normalizacion productiva falla con
    ValueError; nunca lee la tabla desde una fila cualquiera."""
    ruta = _hoja_bnb(tmp_path / "x.xlsx", [["Reporte", "x"], ["nada", "util"]])
    with pytest.raises(ValueError, match="encabezado de la tabla incompleto"):
        normalizar_productivo(motor, ruta, "BNB_MN")


def test_encabezado_parcial_tambien_falla_y_dice_que_falta(motor, tmp_path):
    """D-09 (corregido en P5): 3 de 7 encabezados = error con la lista de los que faltan."""
    ruta = _hoja_bnb(tmp_path / "x.xlsx", [["Cuenta:", "3000100152"], ["Fecha", "Hora", "Saldo"],
                                           ["01/08/2026", "10:00:00", 100]])
    with pytest.raises(ValueError, match=r"\(3/7\); faltan: DESCRIPCION, CODIGO DE TRANSACCION, DEBITOS, CREDITOS"):
        normalizar_productivo(motor, ruta, "BNB_MN")


# ------------------------------- DETECCION DE CUENTA -------------------------------
# D-10 y D-11: CORREGIDOS EN P4 (deteccion por registro_bancos.json). Ya no son xfail: son regresion.
def test_cuenta_dentro_de_glosa_no_cambia_la_deteccion(motor, tmp_path):
    """D-10 (corregido en P4): la cuenta se lee solo en la celda rotulada de la cabecera; un BNB_CLINICA cuya
    glosa menciona la cuenta de BNB_MN sigue siendo BNB_CLINICA."""
    ruta = crear_xlsx_bnb(tmp_path / "x.xlsx", "3000100705", [
        {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0, "adic": "Transferencia desde cuenta 3000100152"}])
    assert motor.detectar_formato(str(ruta)) == "BNB_CLINICA"


def test_bmsc_con_otra_cuenta_no_se_acepta(motor, tmp_path):
    """D-11 (corregido en P4): BMSC exige que la cuenta de la cabecera este registrada (1000872489)."""
    ruta = crear_xlsx_bmsc_otra_cuenta(tmp_path / "x.xlsx", "9999999999")
    assert motor.detectar_formato(str(ruta)) == "NO_RECONOCIDO"


# D-12: CORREGIDO EN P5. La normalizacion productiva no tiene ramas por cuenta: BANCO / CUENTA BANCARIA / MONEDA
# salen de la entrada de CUENTAS del registro. El 'else' de normalizar_union sigue en el legado (solo referencia).
def test_formato_union_nuevo_no_hereda_cuenta_ajena(motor, tmp_path):
    """D-12 (corregido en P5): una cuenta UNION nueva (solo registro) recibe SU cuenta y moneda, nunca las de
    UNION_ME (20000003224544 / USD) ni las de UNION_MN."""
    from helpers import RAIZ
    d = json.loads((RAIZ.parent / "registro_bancos.json").read_text(encoding="utf-8"))
    d["CUENTAS"].append({"id": "UNION_XX", "formato": "UNION_FECHAS_V1", "banco": "BANCO UNIÓN",
                         "cuenta": "30000009990001", "moneda": "EUR", "activa": True})
    reg = tmp_path / "registro.json"
    reg.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    df = normalizar_productivo(motor, EXTRACTOS / FIXTURES["UNION_MN"], "UNION_XX", nombre="union_mn_2.xls",
                               normalizador=motor.normalizador_registro(str(reg)))
    assert len(df) == 32
    assert set(df["CUENTA BANCARIA"]) == {"30000009990001"} and set(df["MONEDA"]) == {"EUR"}
    assert all(c.startswith("BANCO UNIÓN|30000009990001|") for c in df["CLAVE TRANSACCIÓN"])


# ------------------------------- ARCHIVOS VACIOS / COLUMNAS -------------------------------
@defecto("D-16 VACIOS", "un extracto BNB con encabezado y SIN movimientos lanza KeyError y bloquea todo el lote "
                        "(solo BISA maneja 'sin movimientos', y por un efecto colateral de dropna)")
def test_bnb_sin_movimientos_no_bloquea(motor, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "x.xlsx", "3000100705", [])
    df = normalizar_productivo(motor, ruta, "BNB_CLINICA")
    assert len(df) == 0


@defecto("D-16b VACIOS", "un UNION_ME por fechas SIN movimientos (formato confirmado por codigo legado + captura real, con 'Nro de verificasion') lanza KeyError "
                         "y bloquearia todo el lote. Probado con PROXY SINTETICO: confirmar con el archivo real vacio")
def test_union_me_vacio_no_bloquea(motor, tmp_path):
    from helpers import crear_xlsx_union_me_vacio
    ruta = crear_xlsx_union_me_vacio(tmp_path / "u.xlsx")
    df = normalizar_productivo(motor, ruta, "UNION_ME", nombre="u.xlsx")
    assert len(df) == 0


@defecto("D-17 COLUMNAS", "si la columna requerida 'Adicionales' viene completamente vacia el dia del extracto, "
                          "dropna(axis=1) la elimina y buscar_columna lanza KeyError (bloquea todo el lote)")
def test_bnb_con_adicionales_vacio_no_bloquea(motor, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "x.xlsx", "3000100705",
                          [{"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0, "adic": ""}])
    df = normalizar_productivo(motor, ruta, "BNB_CLINICA")
    assert len(df) == 1


# ------------------------------- SALIDAS / ENTORNO -------------------------------
@defecto("D-13 SALIDAS", "si una corrida falla, NORMALIZADO.xlsx y LISTS.csv de la corrida anterior quedan en la "
                         "carpeta y un proceso posterior podria cargarlos como si fueran nuevos")
def test_corrida_fallida_no_deja_salidas_viejas(motor, tmp_path):
    ent, sal = tmp_path / "in", tmp_path / "out"
    ent.mkdir(); sal.mkdir()
    (sal / "NORMALIZADO.xlsx").write_bytes(b"VIEJO"); (sal / "LISTS.csv").write_bytes(b"VIEJO")
    pd.DataFrame({"a": [1]}).to_excel(ent / "desconocido.xlsx", index=False)
    with pytest.raises(ValueError):
        motor.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx"))
    assert not (sal / "NORMALIZADO.xlsx").exists() and not (sal / "LISTS.csv").exists()


def _correr_script(tmp_path, env_extra):
    ent = tmp_path / "in"; ent.mkdir()
    shutil.copy(EXTRACTOS / FIXTURES["BISA_MN"], ent / FIXTURES["BISA_MN"])
    env = {**os.environ, **env_extra}
    r = subprocess.run([sys.executable, str(MOTOR_PATH), str(ent), str(tmp_path / "out" / "NORMALIZADO.xlsx")],
                       capture_output=True, env=env, timeout=120)
    return r, tmp_path / "out"


@defecto("D-14 CONSOLA", "los print con emojis fallan con UnicodeEncodeError si la salida se redirige con codificacion "
                         "cp1252 (p. ej. Windows con redireccion a archivo/pipe)")
def test_motor_corre_con_stdout_cp1252(tmp_path):
    r, _ = _correr_script(tmp_path, {"PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-300:]


@defecto("D-15 ZONA HORARIA", "LOTE DE CARGA y FECHA DE CARGA usan la hora local de la maquina: en un servidor UTC "
                              "se desfasan 4 h respecto de Bolivia")
def test_fecha_de_carga_en_hora_de_bolivia(tmp_path):
    from zoneinfo import ZoneInfo
    r, out = _correr_script(tmp_path, {"TZ": "UTC", "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-300:]
    fc = pd.read_csv(out / "LISTS.csv", encoding="utf-8-sig")["FECHA DE CARGA"].iloc[0]
    esperado = pd.Timestamp(dt.datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None))
    assert abs(pd.Timestamp(fc) - esperado) < pd.Timedelta(minutes=10)
