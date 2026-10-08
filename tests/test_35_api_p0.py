"""P0 · API sin estado (FastAPI) para Railway: POST /procesar-extracto y GET /health.

Se prueba con TestClient (sin desplegar). Usa el motor, P7 y el flujo P8 V5 EXISTENTES (el flujo, con SharePoint
simulado: p8/ensayo_wdl.py). No hay Railway, Power Automate ni tenant en estas pruebas."""
import base64
import json
import logging
import sys
import tempfile
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from helpers import EXTRACTOS, crear_xlsx_bnb  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from p0 import api, nucleo  # noqa: E402
from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado  # noqa: E402

pytestmark = pytest.mark.p0

TOKEN = "token-de-prueba-0123456789"
V5_ZIP = RAIZ / "P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES.zip"
CUENTA_BNB = "3000100705"  # BNB_CLINICA (registrada)


# ------------------------------------------------------------------ utilidades
@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("P0_API_TOKEN", TOKEN)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))  # para comprobar que no queda nada
    (tmp_path / "tmp").mkdir()
    return TestClient(api.app)


def H(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def enviar(c, nombre, datos, sede="CBBA", headers=None):
    return c.post("/procesar-extracto", headers=H() if headers is None else headers, json={
        "sede": sede, "nombre_archivo": nombre, "contenido_base64": base64.b64encode(datos).decode()})


def fixture(nombre):
    return (EXTRACTOS / nombre).read_bytes()


def bnb_xlsx(tmp_path, nombre, filas, cuenta=CUENTA_BNB):
    ruta = tmp_path / nombre
    crear_xlsx_bnb(ruta, cuenta, filas)
    return ruta.read_bytes()


def claves(resp):
    return [m["CLAVE_TRANSACCION"] for m in json.loads(resp.json()["json"]["texto"])["movimientos"]]


def p8_v5(*artefactos):
    """Carga los JSON (texto), en orden, con el flujo P8 V5 real (SharePoint simulado)."""
    with zipfile.ZipFile(V5_ZIP) as z:
        nombre = next(n for n in z.namelist() if n.endswith("definition.json"))
        definicion = json.loads(z.read(nombre))["properties"]["definition"]
    activos, bitacoras = {}, []
    for texto in artefactos:
        sp = SharePointSimulado(json.loads(texto), existentes=activos)
        EnsayoWDL(definicion, sp).ejecutar()
        activos = sp.activos
        bitacoras.append({k: v for k, v in sp.bitacoras[-1].items() if k.startswith("CANTIDAD_")})
    return activos, bitacoras


# ------------------------------------------------------------------ salud y autenticación
def test_health_sin_autenticacion_y_sin_datos_sensibles(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "servicio": "p0-extractos", "version": nucleo.VERSION}


def test_sin_token_o_con_token_incorrecto_no_procesa_nada(cliente):
    datos = fixture("bcp_me_1.xls")
    for headers in ({}, {"Authorization": "Bearer otro-token-distinto-0123"}, {"Authorization": TOKEN},
                    {"Authorization": "Basic " + TOKEN}):
        r = enviar(cliente, "bcp_me_1.xls", datos, headers=headers)
        assert r.status_code == 401 and r.json()["codigo_error"] == "NO_AUTORIZADO" and r.json()["ok"] is False


def test_si_el_servicio_no_tiene_secreto_configurado_rechaza_todo(cliente, monkeypatch):
    monkeypatch.delenv("P0_API_TOKEN")
    r = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"), headers=H(""))
    assert r.status_code == 503 and r.json()["codigo_error"] == "API_NO_CONFIGURADA"
    monkeypatch.setenv("P0_API_TOKEN", "corto")  # un secreto trivial tampoco vale
    assert enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"), headers=H("corto")).status_code == 503
    assert cliente.get("/health").status_code == 200


def test_la_documentacion_automatica_de_la_api_esta_desactivada(cliente):
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(ruta).status_code == 404


# ------------------------------------------------------------------ contrato de éxito
def test_exito_contrato_exacto(cliente):
    r = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"))
    j = r.json()
    assert r.status_code == 200 and j["ok"] is True and j["resultado"] == "PROCESADO"
    assert set(j) == {"ok", "resultado", "version", "sede", "archivo", "deteccion", "periodo", "procesado_en",
                      "movimientos", "publicar_json", "json", "duracion_ms"}
    assert j["archivo"] == {"nombre": "bcp_me_1.xls", "sha256": j["archivo"]["sha256"], "bytes": len(fixture("bcp_me_1.xls"))}
    assert j["deteccion"] == {"banco": "BCP", "cuenta_id": "BCP_ME", "moneda": "USD", "formato": "BCP_EXTRACTO_V1"}
    assert j["movimientos"] == 8 and j["publicar_json"] is True and j["sede"] == "CBBA"
    assert set(j["json"]) == {"nombre", "lote_id", "sha256", "bytes", "texto"}
    nombre = j["json"]["nombre"]
    assert nombre.startswith("DEPOSITOS_ACTIVOS__P7-") and nombre.endswith(".json") and j["json"]["lote_id"] in nombre
    texto = j["json"]["texto"]
    assert len(texto.encode("utf-8")) == j["json"]["bytes"]
    art = json.loads(texto)
    assert art["esquema"] == "P7_DEPOSITOS_ACTIVOS_V1" and len(art["columnas"]) == 26 and len(art["movimientos"]) == 8
    assert all(m["ARCHIVO_ORIGEN"] == "bcp_me_1.xls" for m in art["movimientos"])
    assert set(j["periodo"]) == {"anio", "mes", "carpeta"}


def test_el_texto_del_json_es_exactamente_la_salida_de_p7(cliente, monkeypatch):
    """No se reimplementa P7: lo que recibe Power Automate es byte a byte el artefacto de adaptador_m365.adaptar."""
    capturado = {}
    real = nucleo.etapa_p7

    def espia(lists, carpeta):
        r = real(lists, carpeta)
        capturado["bytes"] = Path(r["rutas"]["artefacto"]).read_bytes()
        return r

    monkeypatch.setattr(nucleo.ETAPAS, "p7", espia)
    j = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls")).json()
    assert j["json"]["texto"].encode("utf-8") == capturado["bytes"]
    import hashlib
    assert j["json"]["sha256"] == hashlib.sha256(capturado["bytes"]).hexdigest()


def test_multipart_equivale_al_json(cliente):
    datos = fixture("bcp_me_1.xls")
    r = cliente.post("/procesar-extracto", headers=H(), files={"archivo": ("bcp_me_1.xls", datos)},
                     data={"sede": "CBBA"})
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["movimientos"] == 8 and j["archivo"]["nombre"] == "bcp_me_1.xls"
    otro = enviar(cliente, "bcp_me_1.xls", datos).json()
    assert [m["CLAVE_TRANSACCION"] for m in json.loads(j["json"]["texto"])["movimientos"]] == \
        [m["CLAVE_TRANSACCION"] for m in json.loads(otro["json"]["texto"])["movimientos"]]


def test_extracto_sin_movimientos_es_exito_sin_json(cliente):
    j = enviar(cliente, "bisa_me_2.xls", fixture("bisa_me_2.xls")).json()
    assert j["ok"] and j["movimientos"] == 0 and j["publicar_json"] is False and j["json"] is None
    assert "sin movimientos" in j["advertencia"].lower()


def test_el_nombre_se_sanea_sin_rutas(cliente):
    j = enviar(cliente, "..\\..\\etc/otra\\bcp_me_1.xls", fixture("bcp_me_1.xls")).json()
    assert j["ok"] and j["archivo"]["nombre"] == "bcp_me_1.xls"


# ------------------------------------------------------------------ archivo por archivo, repetidos y solapados
def test_un_archivo_malo_no_afecta_al_siguiente(cliente):
    malo = enviar(cliente, "BCP.xls", b"esto no es un excel").json()
    bueno = enviar(cliente, "BISA.xls", fixture("bisa_mn_2.xls")).json()
    otro = enviar(cliente, "UNION.xls", fixture("union_mn_2.xls")).json()
    assert (malo["ok"], bueno["ok"], otro["ok"]) == (False, True, True)
    assert malo["codigo_error"] == "ARCHIVO_ILEGIBLE" and malo["etapa"] == "DETECCION"


def test_mismo_extracto_dos_veces_p8_no_duplica(cliente):
    datos = fixture("bcp_me_1.xls")
    a, b = enviar(cliente, "bcp_me_1.xls", datos), enviar(cliente, "bcp_me_1.xls", datos)
    assert claves(a) == claves(b) and len(claves(a)) == 8
    activos, bit = p8_v5(a.json()["json"]["texto"], b.json()["json"]["texto"])
    assert len(activos) == 8
    assert (bit[0]["CANTIDAD_NUEVA"], bit[1]["CANTIDAD_NUEVA"], bit[1]["CANTIDAD_YA_EXISTE"]) == (8, 0, 8)


def test_extractos_solapados_se_cargan_sin_duplicar(cliente, tmp_path):
    filas = [{"fecha": f"0{d}/08/2026", "cred": 10.0 * d, "saldo": 1000.0 + sum(10.0 * k for k in range(1, d + 1)),
              "cod": str(d)} for d in range(1, 6)]
    a = enviar(cliente, "a_1_al_4.xlsx", bnb_xlsx(tmp_path, "a.xlsx", filas[0:4]))
    b = enviar(cliente, "b_3_al_5.xlsx", bnb_xlsx(tmp_path, "b.xlsx", filas[2:5]))
    assert a.json()["ok"] and b.json()["ok"], (a.json(), b.json())
    activos, bit = p8_v5(a.json()["json"]["texto"], b.json()["json"]["texto"])
    assert len(activos) == 5 and sorted(x["CANTIDAD_YA_EXISTE"] for x in bit) == [0, 2]


def test_dos_solicitudes_simultaneas_se_procesan_sin_mezclarse(cliente):
    res = {}

    def llamar(nombre, fx):
        res[nombre] = enviar(cliente, nombre, fixture(fx)).json()

    hilos = [threading.Thread(target=llamar, args=("a.xls", "bcp_me_1.xls")),
             threading.Thread(target=llamar, args=("b.xls", "union_mn_2.xls"))]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert res["a.xls"]["ok"] and res["b.xls"]["ok"]
    assert (res["a.xls"]["movimientos"], res["b.xls"]["movimientos"]) == (8, 32)
    assert res["a.xls"]["deteccion"]["banco"] == "BCP" and res["b.xls"]["deteccion"]["banco"] == "BANCO UNIÓN"


# ------------------------------------------------------------------ errores estructurados
def _assert_error(j, codigo, etapa):
    assert j["ok"] is False and j["resultado"] == "ERROR" and j["codigo_error"] == codigo and j["etapa"] == etapa
    assert j["mensaje"] and set(j) >= {"ok", "resultado", "codigo_error", "etapa", "mensaje", "archivo", "periodo"}
    assert "json" not in j


def test_banco_no_reconocido(cliente):
    from openpyxl import Workbook
    import io
    wb = Workbook(); wb.active.append(["Banco Imaginario", "x"]); buf = io.BytesIO(); wb.save(buf)
    r = enviar(cliente, "otro.xlsx", buf.getvalue())
    assert r.status_code == 200
    _assert_error(r.json(), "SIN_FORMATO", "DETECCION")


def test_cuenta_no_registrada_y_el_numero_de_cuenta_va_enmascarado(cliente, tmp_path):
    datos = bnb_xlsx(tmp_path, "x.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0}], cuenta="3999999999")
    j = enviar(cliente, "x.xlsx", datos).json()
    _assert_error(j, "CUENTA_NO_REGISTRADA", "DETECCION")
    assert "3999999999" not in json.dumps(j) and "9999" in j["mensaje"]


def test_archivo_corrupto_vacio_y_extension(cliente):
    _assert_error(enviar(cliente, "roto.xls", b"basura").json(), "ARCHIVO_ILEGIBLE", "DETECCION")
    _assert_error(enviar(cliente, "vacio.xls", b"").json(), "ARCHIVO_VACIO", "ARCHIVO")
    _assert_error(enviar(cliente, "notas.txt", b"hola").json(), "EXTENSION_NO_SOPORTADA", "ARCHIVO")


def test_saldos_no_cuadran_sin_exponer_tablas(cliente, tmp_path):
    datos = bnb_xlsx(tmp_path, "m.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0, "cod": "1"},
                                          {"fecha": "06/08/2026", "cred": 50.0, "saldo": 9999.0, "cod": "2"}])
    j = enviar(cliente, "mal.xlsx", datos).json()
    _assert_error(j, "SALDOS_NO_CUADRAN", "MOTOR")
    assert "9999" not in j["mensaje"] and "8849" not in j["mensaje"]


def test_nombre_que_el_motor_ignora(cliente):
    _assert_error(enviar(cliente, "NORMALIZADO_bcp.xls", fixture("bcp_me_1.xls")).json(),
                  "ARCHIVO_EXCLUIDO_POR_NOMBRE", "MOTOR")


def test_error_de_p7(cliente, monkeypatch):
    def p7(lists, carpeta):
        raise ValueError("ERROR de contrato simulado")

    monkeypatch.setattr(nucleo.ETAPAS, "p7", p7)
    r = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"))
    assert r.status_code == 200
    _assert_error(r.json(), "P7_CONTRATO", "P7")


def test_p7_con_filas_invalidas_no_entrega_json(cliente, monkeypatch):
    real = nucleo.etapa_p7

    def p7(lists, carpeta):
        r = real(lists, carpeta)
        r["manifiesto"] = dict(r["manifiesto"], cantidad_error=1)
        art = Path(r["rutas"]["artefacto"])
        d = json.loads(art.read_text(encoding="utf-8"))
        d["omitidos"] = [{"fila": 3, "estado": "ERROR", "motivo": "texto > 255", "errores": [], "valores": {}}]
        art.write_text(json.dumps(d), encoding="utf-8")
        return r

    monkeypatch.setattr(nucleo.ETAPAS, "p7", p7)
    j = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls")).json()
    _assert_error(j, "P7_FILAS_INVALIDAS", "P7")
    assert "fila 3" in j["mensaje"]


def test_error_inesperado_es_500_y_no_revela_el_mensaje(cliente, monkeypatch, caplog):
    def motor(*a, **k):
        raise RuntimeError("VALOR-SECRETO-DEL-EXTRACTO 3000100152")

    monkeypatch.setattr(nucleo.ETAPAS, "motor", motor)
    with caplog.at_level(logging.DEBUG):
        r = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"))
    j = r.json()
    assert r.status_code == 500 and j["codigo_error"] == "ERROR_INESPERADO" and j["etapa"] == "MOTOR"
    assert "SECRETO" not in json.dumps(j) and "SECRETO" not in caplog.text and "3000100152" not in caplog.text
    assert "RuntimeError" in j["mensaje"]


# ------------------------------------------------------------------ año dinámico de punta a punta
@pytest.mark.parametrize("anio", [2026, 2027, 2028])
def test_extracto_de_cualquier_año_se_procesa(cliente, monkeypatch, tmp_path, anio):
    motor = nucleo._modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    monkeypatch.setattr(motor, "fecha_referencia", lambda: pd.Timestamp(f"{anio}-12-20"))
    datos = bnb_xlsx(tmp_path, "x.xlsx", [{"fecha": f"05/03/{anio}", "cred": 100.0, "saldo": 1100.0, "cod": "1"}])
    j = enviar(cliente, "x.xlsx", datos).json()
    assert j["ok"], j
    assert claves(type("R", (), {"json": lambda self: j})())[0].split("|")[2] == f"{anio}0305"


def test_año_fuera_de_rango_es_error_legible(cliente, monkeypatch, tmp_path):
    motor = nucleo._modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    monkeypatch.setattr(motor, "fecha_referencia", lambda: pd.Timestamp("2026-10-08"))
    datos = bnb_xlsx(tmp_path, "x.xlsx", [{"fecha": "05/03/2062", "cred": 100.0, "saldo": 1100.0}])
    j = enviar(cliente, "x.xlsx", datos).json()
    _assert_error(j, "ANIO_FUERA_DE_RANGO", "MOTOR")
    assert "2062" in j["mensaje"]


# ------------------------------------------------------------------ periodo AAAA/MM_MES para Power Automate
def test_los_nombres_de_mes_son_fijos():
    assert nucleo.MESES == ("01_ENERO", "02_FEBRERO", "03_MARZO", "04_ABRIL", "05_MAYO", "06_JUNIO", "07_JULIO",
                            "08_AGOSTO", "09_SEPTIEMBRE", "10_OCTUBRE", "11_NOVIEMBRE", "12_DICIEMBRE")


@pytest.mark.parametrize("fecha,esperado", [
    (datetime(2026, 10, 8), "2026/10_OCTUBRE"), (datetime(2026, 12, 31, 23, 59), "2026/12_DICIEMBRE"),
    (datetime(2027, 1, 1, 0, 1), "2027/01_ENERO"), (datetime(2028, 2, 29), "2028/02_FEBRERO")])
def test_periodo_en_exito_y_en_error(cliente, monkeypatch, fecha, esperado):
    monkeypatch.setattr(nucleo, "ahora_local", lambda cfg=None: fecha)
    ok = enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls")).json()
    mal = enviar(cliente, "roto.xls", b"basura").json()
    assert ok["periodo"]["carpeta"] == mal["periodo"]["carpeta"] == esperado
    assert ok["periodo"]["anio"] == fecha.year


def test_ahora_local_usa_la_zona_de_la_sede_y_tiene_respaldo():
    a = nucleo.ahora_local({"zona_horaria": "America/La_Paz"})
    assert a.utcoffset() == timedelta(hours=-4)
    assert nucleo.ahora_local({"zona_horaria": "No/Existe"}).utcoffset() == timedelta(hours=-4)


# ------------------------------------------------------------------ solicitudes inválidas
def test_solicitudes_invalidas(cliente, monkeypatch):
    datos = fixture("bcp_me_1.xls")
    r = enviar(cliente, "bcp_me_1.xls", datos, sede="XXX")
    assert (r.status_code, r.json()["codigo_error"]) == (400, "SEDE_DESCONOCIDA")
    r = cliente.post("/procesar-extracto", headers=H(), json={"sede": "CBBA", "nombre_archivo": "x.xls"})
    assert (r.status_code, r.json()["codigo_error"]) == (400, "SOLICITUD_INVALIDA")
    r = cliente.post("/procesar-extracto", headers=H(), json={"sede": "CBBA", "nombre_archivo": "x.xls",
                                                              "contenido_base64": "###no-base64###"})
    assert (r.status_code, r.json()["codigo_error"]) == (400, "CONTENIDO_INVALIDO")
    r = cliente.post("/procesar-extracto", headers={**H(), "Content-Type": "text/plain"}, content=b"hola")
    assert (r.status_code, r.json()["codigo_error"]) == (400, "SOLICITUD_INVALIDA")
    r = cliente.post("/procesar-extracto", headers=H(), files={"otro": ("x.xls", datos)}, data={"sede": "CBBA"})
    assert (r.status_code, r.json()["codigo_error"]) == (400, "SOLICITUD_INVALIDA")
    monkeypatch.setenv("P0_MAX_BYTES", "1000")
    r = enviar(cliente, "bcp_me_1.xls", datos)
    assert (r.status_code, r.json()["codigo_error"]) == (413, "ARCHIVO_DEMASIADO_GRANDE")


# ------------------------------------------------------------------ sin estado y sin contenido bancario en logs
def test_no_queda_nada_en_disco_ni_en_el_repositorio(cliente, tmp_path):
    antes = sorted(p.name for p in RAIZ.iterdir())
    enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"))             # éxito
    enviar(cliente, "roto.xls", b"basura")                                 # error de detección
    enviar(cliente, "mal.xlsx", bnb_xlsx(tmp_path, "m.xlsx", [{"fecha": "05/08/2026", "cred": 1.0, "saldo": 5.0}]))
    assert list((tmp_path / "tmp").iterdir()) == []                        # el temporal se elimina siempre
    assert sorted(p.name for p in RAIZ.iterdir()) == antes                 # y no se escribe en el repositorio


def test_el_temporal_se_elimina_aunque_el_motor_falle(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(nucleo.ETAPAS, "motor", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"))
    assert list((tmp_path / "tmp").iterdir()) == []


def test_los_logs_son_solo_tecnicos(cliente, caplog, tmp_path):
    with caplog.at_level(logging.DEBUG):
        enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"))
        enviar(cliente, "x.xlsx", bnb_xlsx(tmp_path, "x.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0}],
                                           cuenta="3999999999"))
    texto = caplog.text
    assert "archivo=bcp_me_1.xls" in texto and "banco=BCP" in texto and "filas=8" in texto and "resultado=PROCESADO" in texto
    assert "codigo=CUENTA_NO_REGISTRADA" in texto and "etapa=DETECCION" in texto and "ms=" in texto
    art = json.loads(enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls")).json()["json"]["texto"])
    mov = art["movimientos"][0]
    for prohibido in ("3999999999", "301-5005425-2-71", "5005425", mov["CLAVE_TRANSACCION"], mov["DESCRIPCION"].strip(),
                      "movimientos", "DEPOSITOS_ACTIVOS__P7", TOKEN, "Bearer"):
        assert prohibido and prohibido not in texto, prohibido


def test_enmascarar():
    t = nucleo.enmascarar("cuenta 3000100152 y 12345", ["301-5005425-2-71"])
    assert "3000100152" not in t and "****0152" in t and "12345" in t
    t = nucleo.enmascarar("la cuenta '301-5005425-2-71' no está", ["301-5005425-2-71"])
    assert "5005425" not in t and "****5271" in t


# ------------------------------------------------------------------ varias sedes, un solo motor
def test_cbba_usa_el_registro_base_sin_copiarlo(tmp_path):
    assert nucleo.registro_para_sede(nucleo.config_sede("CBBA"), tmp_path) == nucleo.REGISTRO_BASE
    assert list(tmp_path.iterdir()) == []


def _sedes(tmp_path, monkeypatch, **sedes):
    ruta = tmp_path / "sedes.json"
    ruta.write_text(json.dumps({"sedes": sedes}), encoding="utf-8")
    monkeypatch.setattr(nucleo, "SEDES_JSON", ruta)


def test_otra_sede_comparte_formatos_y_tiene_sus_propias_cuentas(cliente, monkeypatch, tmp_path):
    adicionales = tmp_path / "cuentas_lpz.json"
    adicionales.write_text(json.dumps([{"id": "BNB_LPZ_1", "formato": "BNB_EXTRACTO_V1", "banco": "BNB",
                                        "cuenta": "3777777777", "moneda": "BOB", "activa": True}]), encoding="utf-8")
    _sedes(tmp_path, monkeypatch, LPZ={"nombre": "La Paz", "cuentas": [], "cuentas_adicionales": str(adicionales)},
           CBBA={"cuentas": "TODAS", "cuentas_adicionales": None})
    lpz = bnb_xlsx(tmp_path, "l.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0}], cuenta="3777777777")
    ok = enviar(cliente, "lpz.xlsx", lpz, sede="LPZ").json()
    assert ok["ok"], ok
    assert claves(type("R", (), {"json": lambda self: ok})())[0].startswith("BNB|3777777777|20260805")
    # una cuenta de CBBA presentada en LPZ no está registrada para esa sede; y la de LPZ no existe en CBBA
    _assert_error(enviar(cliente, "bcp_me_1.xls", fixture("bcp_me_1.xls"), sede="LPZ").json(), "CUENTA_NO_REGISTRADA", "DETECCION")
    _assert_error(enviar(cliente, "lpz.xlsx", lpz, sede="CBBA").json(), "CUENTA_NO_REGISTRADA", "DETECCION")


def test_sede_con_subconjunto_de_cuentas_base_y_errores_de_configuracion(tmp_path):
    reg = nucleo.registro_para_sede({"cuentas": ["BCP_ME"]}, tmp_path / "t", sede="SCZ")
    assert [c["id"] for c in json.loads(reg.read_text(encoding="utf-8"))["CUENTAS"]] == ["BCP_ME"]
    with pytest.raises(nucleo.ConfigError, match="inexistentes"):
        nucleo.registro_para_sede({"cuentas": ["NO_EXISTE"]}, tmp_path / "t")
    ad = tmp_path / "ad.json"
    ad.write_text(json.dumps([{"id": "BCP_ME", "formato": "BCP_EXTRACTO_V1"}]), encoding="utf-8")
    with pytest.raises(nucleo.ConfigError, match="repetidos"):
        nucleo.registro_para_sede({"cuentas": "TODAS", "cuentas_adicionales": str(ad)}, tmp_path / "t")


# ------------------------------------------------------------------ despliegue (archivos para Railway)
def test_dockerfile_requirements_y_start_command():
    docker = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "uvicorn" in docker and "p0.api:app" in docker and "${PORT" in docker and "--workers 1" in docker
    assert "USER " in docker and "TZ=" in docker and "P0_API_TOKEN=" not in docker  # sin secretos en la imagen
    for modulo in ("motor_control_depositos_cbba.py", "motor_generico.py", "deteccion_registro.py", "captura_origen.py",
                   "registro_bancos.json", "adaptador_m365.py", "p0/"):
        assert modulo in docker, modulo
    req = (RAIZ / "requirements-p0.txt").read_text(encoding="utf-8").lower()
    for paquete in ("fastapi", "uvicorn", "python-multipart", "pandas", "numpy", "xlrd", "openpyxl", "python-calamine"):
        assert paquete in req, paquete
    assert "pytest" not in req
    cfg = json.loads((RAIZ / "railway.json").read_text(encoding="utf-8"))
    assert cfg["deploy"]["healthcheckPath"] == "/health" and cfg["build"]["builder"] == "DOCKERFILE"


def test_dockerignore_deja_fuera_extractos_reales_y_tests():
    di = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "*" in [l.strip() for l in di]  # lista blanca: solo entra lo permitido
    permitidos = {l[1:].strip() for l in di if l.startswith("!")}
    assert not any(p.startswith(("tests", "ejemplos", "ORIGEN")) or p.endswith((".xls", ".xlsx", ".zip")) for p in permitidos)
    assert {"p0/**", "motor_control_depositos_cbba.py", "registro_bancos.json"} <= permitidos


def test_el_codigo_y_los_archivos_de_despliegue_no_traen_secretos():
    import re
    asignacion = re.compile(r"P0_API_TOKEN[\"']?\s*[:=]\s*[\"'][^\"']+[\"']")
    for f in [*(RAIZ / "p0").glob("*"), RAIZ / "Dockerfile", RAIZ / "railway.json", RAIZ / ".dockerignore",
              RAIZ / "requirements-p0.txt"]:
        if f.is_file():
            assert not asignacion.search(f.read_text(encoding="utf-8")), f.name
    assert 'os.environ.get("P0_API_TOKEN"' in (RAIZ / "p0" / "api.py").read_text(encoding="utf-8")
