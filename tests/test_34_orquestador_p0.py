"""P0 · orquestador de entrada de extractos: ENTRADA -> motor -> P7 -> carpeta de P8 -> PROCESADOS / ERROR.

Usa el motor, P7 y el flujo P8 V5 EXISTENTES (el flujo, con SharePoint simulado: p8/ensayo_wdl.py). Sin Microsoft 365:
la carga real a Depositos_Activos y la sincronizacion de OneDrive no se prueban aqui."""
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from helpers import EXTRACTOS, crear_xlsx_bnb

RAIZ = Path(__file__).resolve().parent.parent  # raiz del repositorio

sys.path.insert(0, str(RAIZ))
from p0 import orquestador as P0  # noqa: E402
from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado  # noqa: E402

pytestmark = pytest.mark.p0

CUENTA_BNB = "3000100705"  # BNB_CLINICA (registrada)
V5_ZIP = RAIZ / "P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES.zip"


# ------------------------------------------------------------------ utilidades
class Entorno:
    def __init__(self, base, sedes_json=None, sede="CBBA", ahora=datetime(2026, 10, 15, 9, 30, 0), **kw):
        self.docs = base / "Documents"
        self.raiz = self.docs / "CONTROL_DEPOSITOS" / "P0_EXTRACTOS"
        self.p8 = self.raiz / "CARGA_EXTRACTOS_BANCARIOS"
        for c in (self.raiz / "ENTRADA", self.raiz / "PROCESADOS", self.raiz / "ERROR", self.p8):
            c.mkdir(parents=True)
        self.ahora = ahora  # reloj de P0 en las pruebas: define AAAA/MM_MES de PROCESADOS y ERROR
        args = {"estable_s": 0.0}
        if sedes_json:
            args["sedes_json"] = sedes_json
        self.cfg = P0.cargar_config(sede, documentos=str(self.docs), trabajo=base / "trabajo", **args, **kw)
        P0.validar_config(self.cfg)
        self.orq = P0.Orquestador(self.cfg, reloj=lambda: self.ahora, esperar=lambda s: None)

    def poner(self, nombre, origen=None, contenido=None):
        destino = self.cfg.entrada / nombre
        if origen is not None:
            shutil.copy(origen, destino)
        else:
            destino.write_bytes(contenido)
        return destino

    def fixture(self, nombre_fixture, como=None):
        return self.poner(como or nombre_fixture, EXTRACTOS / nombre_fixture)

    def nombres(self, carpeta):
        return sorted(p.name for p in carpeta.iterdir())

    def procesados(self):  # PROCESADOS/AAAA/MM_MES del reloj actual
        return P0.carpeta_mes(self.cfg.procesados, self.ahora)

    def errores(self):
        return P0.carpeta_mes(self.cfg.error, self.ahora)

    def en(self, base):
        """Nombres en base/AAAA/MM_MES (lista vacia si esa carpeta no existe)."""
        c = P0.carpeta_mes(base, self.ahora)
        return self.nombres(c) if c.is_dir() else []

    def jsons_p8(self):
        return sorted(self.p8.glob("DEPOSITOS_ACTIVOS__*.json"))


@pytest.fixture
def env(tmp_path):
    return Entorno(tmp_path)


def _extracto_bnb(ruta, filas, cuenta=CUENTA_BNB):
    return crear_xlsx_bnb(ruta, cuenta, filas)


def _claves(ruta_json):
    return [m["CLAVE_TRANSACCION"] for m in json.loads(Path(ruta_json).read_text(encoding="utf-8"))["movimientos"]]


def _p8_v5(*jsons):
    """Carga los JSON, en orden, con el flujo P8 V5 real (SharePoint simulado). Devuelve (activos, bitacoras)."""
    with zipfile.ZipFile(V5_ZIP) as z:
        nombre = next(n for n in z.namelist() if n.endswith("definition.json"))
        definicion = json.loads(z.read(nombre))["properties"]["definition"]
    activos, bitacoras = {}, []
    for j in jsons:
        sp = SharePointSimulado(json.loads(Path(j).read_text(encoding="utf-8")), existentes=activos)
        EnsayoWDL(definicion, sp).ejecutar()
        activos = sp.activos
        bitacoras.append({k: v for k, v in sp.bitacoras[-1].items() if k.startswith("CANTIDAD_")})
    return activos, bitacoras


def _evidencia_error(env, nombre):
    return json.loads((env.errores() / f"{nombre}.error.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ circuito feliz
def test_archivo_valido_se_publica_y_pasa_a_procesados(env):
    env.fixture("bcp_me_1.xls")
    (r,) = env.orq.ciclo()
    assert r.estado == "PROCESADO" and r.movimientos == 8 and not r.codigo
    assert env.nombres(env.cfg.entrada) == []
    assert env.en(env.cfg.procesados) == ["bcp_me_1.xls", "bcp_me_1.xls.p0.json"]
    (j,) = env.jsons_p8()
    art = json.loads(j.read_text(encoding="utf-8"))
    assert art["esquema"] == "P7_DEPOSITOS_ACTIVOS_V1" and len(art["movimientos"]) == 8 and len(art["columnas"]) == 26
    assert all(m["ARCHIVO_ORIGEN"] == "bcp_me_1.xls" for m in art["movimientos"])  # el motor ve el nombre original
    ev = json.loads((env.procesados() / "bcp_me_1.xls.p0.json").read_text(encoding="utf-8"))
    assert ev["json_publicado"] == j.name and ev["lote_id"] == art["lote_id"] and ev["movimientos"] == 8
    assert not (env.cfg.trabajo / "corridas").exists() or not list((env.cfg.trabajo / "corridas").iterdir())


def test_el_json_publicado_es_exactamente_la_salida_de_p7(env, tmp_path):
    """No se reimplementa P7: el JSON entregado a P8 es byte a byte el de adaptador_m365.adaptar sobre el LISTS.csv."""
    capturado = {}
    real = P0.etapa_p7

    def espia(lists, carpeta):
        r = real(lists, carpeta)
        capturado["artefacto"] = Path(r["rutas"]["artefacto"]).read_bytes()
        return r

    env.orq.etapas.p7 = espia
    env.fixture("bcp_me_1.xls")
    env.orq.ciclo()
    (j,) = env.jsons_p8()
    assert j.read_bytes() == capturado["artefacto"]


def test_dos_archivos_validos_se_procesan_independientes(env):
    env.fixture("bcp_me_1.xls")
    env.fixture("union_mn_2.xls")
    res = env.orq.ciclo()
    assert [r.estado for r in res] == ["PROCESADO", "PROCESADO"]
    assert len(env.jsons_p8()) == 2
    assert env.nombres(env.cfg.entrada) == []
    assert sorted(r.movimientos for r in res) == [8, 32]


def test_extracto_sin_movimientos_es_procesado_sin_json(env):
    env.fixture("bisa_me_2.xls")  # cuenta valida sin movimientos
    (r,) = env.orq.ciclo()
    assert r.estado == "PROCESADO" and r.movimientos == 0 and r.json_publicado == ""
    assert env.jsons_p8() == [] and "bisa_me_2.xls" in env.en(env.cfg.procesados)


# ------------------------------------------------------------------ un archivo malo no detiene a los demas
def test_varios_archivos_cada_uno_con_su_resultado(env):
    env.fixture("bisa_mn_2.xls", como="BISA.xls")
    env.fixture("bcp_me_1.xls", como="BCP_ME.xls")
    env.poner("BCP.xls", contenido=b"esto no es un excel")
    env.fixture("union_mn_2.xls", como="UNION.xls")
    res = {r.archivo: r for r in env.orq.ciclo()}
    assert {n: r.estado for n, r in res.items()} == {
        "BISA.xls": "PROCESADO", "BCP_ME.xls": "PROCESADO", "BCP.xls": "ERROR", "UNION.xls": "PROCESADO"}
    assert env.nombres(env.cfg.entrada) == []
    assert "BCP.xls" in env.en(env.cfg.error) and "BCP.xls.error.json" in env.en(env.cfg.error)
    assert len(env.jsons_p8()) == sum(1 for r in res.values() if r.estado == "PROCESADO" and r.movimientos)
    assert res["BCP.xls"].json_publicado == ""  # el archivo malo no publica nada


def test_error_deja_evidencia_minima_legible(env):
    env.poner("roto.xls", contenido=b"basura")
    (r,) = env.orq.ciclo()
    ev = _evidencia_error(env, "roto.xls")
    assert set(ev) >= {"nombre_archivo", "fecha_hora", "etapa", "codigo_error", "mensaje"}
    assert (ev["nombre_archivo"], ev["etapa"], ev["codigo_error"]) == ("roto.xls", "DETECCION", "ARCHIVO_ILEGIBLE")
    datetime.fromisoformat(ev["fecha_hora"])
    assert "Excel" in ev["mensaje"] and r.estado == "ERROR"
    assert env.jsons_p8() == [] and env.nombres(env.cfg.entrada) == []


def test_archivo_vacio_y_extension_no_soportada(env):
    env.poner("vacio.xls", contenido=b"")
    env.poner("notas.txt", contenido=b"hola")
    res = {r.archivo: r for r in env.orq.ciclo()}
    assert res["vacio.xls"].codigo == "ARCHIVO_VACIO" and res["notas.txt"].codigo == "EXTENSION_NO_SOPORTADA"
    assert {"vacio.xls", "notas.txt"} <= set(env.en(env.cfg.error))


def test_banco_no_reconocido(env, tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); wb.active.append(["Banco Imaginario", "x"]); wb.save(env.cfg.entrada / "otro.xlsx")
    (r,) = env.orq.ciclo()
    assert (r.estado, r.etapa, r.codigo) == ("ERROR", "DETECCION", "SIN_FORMATO")
    assert "otro.xlsx" in env.en(env.cfg.error)


def test_cuenta_no_registrada(env):
    _extracto_bnb(env.cfg.entrada / "bnb_otra.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0}],
                  cuenta="3999999999")
    (r,) = env.orq.ciclo()
    assert (r.estado, r.etapa, r.codigo) == ("ERROR", "DETECCION", "CUENTA_NO_REGISTRADA")
    assert "3999999999" in r.mensaje or "registrada" in r.mensaje.lower()


def test_error_del_motor_se_traduce_a_codigo_legible(env):
    # saldo final inconsistente con los movimientos -> el motor bloquea la exportacion
    _extracto_bnb(env.cfg.entrada / "mal.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0, "cod": "1"},
                                                  {"fecha": "06/08/2026", "cred": 50.0, "saldo": 9999.0, "cod": "2"}])
    (r,) = env.orq.ciclo()
    assert (r.estado, r.etapa, r.codigo) == ("ERROR", "MOTOR", "SALDOS_NO_CUADRAN")
    assert "mal.xlsx" in env.en(env.cfg.error) and env.jsons_p8() == []


def test_nombre_que_el_motor_ignora(env):
    env.fixture("bcp_me_1.xls", como="NORMALIZADO_bcp.xls")
    (r,) = env.orq.ciclo()
    assert (r.estado, r.codigo) == ("ERROR", "ARCHIVO_EXCLUIDO_POR_NOMBRE")


# ------------------------------------------------------------------ fallos de P7 y de publicacion
def test_error_de_p7_va_a_error_y_no_detiene_a_los_demas(env):
    real = P0.etapa_p7

    def p7(lists, carpeta):
        if "union" in Path(lists).parts[-3].lower():  # carpeta de trabajo con el nombre del archivo
            raise ValueError("ERROR de contrato simulado")
        return real(lists, carpeta)

    env.orq.etapas.p7 = p7
    env.fixture("union_mn_2.xls")
    env.fixture("bcp_me_1.xls")
    res = {r.archivo: r for r in env.orq.ciclo()}
    assert (res["union_mn_2.xls"].estado, res["union_mn_2.xls"].etapa, res["union_mn_2.xls"].codigo) == \
        ("ERROR", "P7", "P7_CONTRATO")
    assert res["bcp_me_1.xls"].estado == "PROCESADO"
    assert "union_mn_2.xls" in env.en(env.cfg.error) and len(env.jsons_p8()) == 1


def test_p7_con_filas_invalidas_no_publica_un_extracto_incompleto(env, tmp_path):
    real = P0.etapa_p7

    def p7(lists, carpeta):
        r = real(lists, carpeta)
        r["manifiesto"] = dict(r["manifiesto"], cantidad_error=1)
        art = Path(r["rutas"]["artefacto"])
        d = json.loads(art.read_text(encoding="utf-8"))
        d["omitidos"] = [{"fila": 3, "estado": "ERROR", "motivo": "texto > 255", "errores": [], "valores": {}}]
        art.write_text(json.dumps(d), encoding="utf-8")
        return r

    env.orq.etapas.p7 = p7
    env.fixture("bcp_me_1.xls")
    (r,) = env.orq.ciclo()
    assert (r.estado, r.codigo) == ("ERROR", "P7_FILAS_INVALIDAS") and "fila 3" in r.mensaje
    assert env.jsons_p8() == [] and "bcp_me_1.xls" in env.en(env.cfg.error)


def test_error_al_publicar_el_json_deja_el_extracto_en_error(env):
    def publicar(ruta_json, destino, ahora):
        raise P0.ErrorP0("PUBLICACION", "PUBLICACION_FALLIDA", "disco lleno (simulado)")

    env.orq.etapas.publicar = publicar
    env.fixture("bcp_me_1.xls")
    (r,) = env.orq.ciclo()
    assert (r.estado, r.etapa, r.codigo) == ("ERROR", "PUBLICACION", "PUBLICACION_FALLIDA")
    assert "bcp_me_1.xls" in env.en(env.cfg.error) and env.en(env.cfg.procesados) == []


def test_carpeta_de_p8_desaparece_durante_la_corrida(env):
    shutil.rmtree(env.p8)
    env.fixture("bcp_me_1.xls")
    (r,) = env.orq.ciclo()
    assert (r.estado, r.codigo) == ("ERROR", "CARPETA_CARGA_NO_EXISTE")
    assert env.en(env.cfg.procesados) == []


def test_el_extracto_se_mueve_a_procesados_solo_despues_de_publicar(env):
    visto = {}
    real = P0.etapa_publicar

    def publicar(ruta_json, destino, ahora):
        visto["en_entrada"] = "bcp_me_1.xls" in env.nombres(env.cfg.entrada)
        visto["en_procesados"] = "bcp_me_1.xls" in env.en(env.cfg.procesados)
        return real(ruta_json, destino, ahora)

    env.orq.etapas.publicar = publicar
    env.fixture("bcp_me_1.xls")
    env.orq.ciclo()
    assert visto == {"en_entrada": True, "en_procesados": False}
    assert "bcp_me_1.xls" in env.en(env.cfg.procesados)


def test_si_no_se_puede_mover_el_original_no_se_republica_en_cada_ciclo(env, monkeypatch):
    def mover(*a, **k):
        raise PermissionError("archivo en uso (simulado)")

    monkeypatch.setattr(P0.shutil, "move", mover)
    env.fixture("bcp_me_1.xls")
    (r,) = env.orq.ciclo()
    assert r.estado == "PROCESADO" and "No se pudo mover" in r.advertencia
    assert env.nombres(env.cfg.entrada) == ["bcp_me_1.xls"] and len(env.jsons_p8()) == 1
    assert env.orq.ciclo() == [] and len(env.jsons_p8()) == 1  # no se genera un JSON nuevo por ciclo


def test_un_error_inesperado_tampoco_detiene_los_demas(env):
    real = P0.etapa_p7

    def p7(lists, carpeta):
        if "bcp" in str(lists):
            raise RuntimeError("explosion inesperada")
        return real(lists, carpeta)

    env.orq.etapas.p7 = p7
    env.fixture("bcp_me_1.xls")
    env.fixture("union_mn_2.xls")
    res = {r.archivo: r for r in env.orq.ciclo()}
    assert res["bcp_me_1.xls"].codigo == "ERROR_INESPERADO" and res["bcp_me_1.xls"].etapa == "P7"
    assert res["union_mn_2.xls"].estado == "PROCESADO"


# ------------------------------------------------------------------ repetidos y solapados (idempotencia en P8)
def test_mismo_extracto_dos_veces_p8_no_duplica(env):
    env.fixture("bcp_me_1.xls")
    env.orq.ciclo()
    env.fixture("bcp_me_1.xls")  # mismo nombre y contenido, otro dia
    (r2,) = env.orq.ciclo()
    assert r2.estado == "PROCESADO"
    a, b = env.jsons_p8()
    assert _claves(a) == _claves(b) and len(_claves(a)) == 8
    activos, bitacoras = _p8_v5(a, b)
    assert len(activos) == 8
    assert (bitacoras[0]["CANTIDAD_NUEVA"], bitacoras[1]["CANTIDAD_NUEVA"], bitacoras[1]["CANTIDAD_YA_EXISTE"]) == (8, 0, 8)
    # el segundo original no pisa al primero en PROCESADOS
    assert len([n for n in env.en(env.cfg.procesados) if n.endswith(".xls")]) == 2


def test_mismo_extracto_con_otro_nombre_en_la_misma_corrida(env):
    """Antes (motor por lote) esto detenia todo: 'No cargues dos archivos de la misma cuenta'."""
    env.fixture("bcp_me_1.xls", como="copia_a.xls")
    env.fixture("bcp_me_1.xls", como="copia_b.xls")
    res = env.orq.ciclo()
    assert [r.estado for r in res] == ["PROCESADO", "PROCESADO"]
    activos, _ = _p8_v5(*env.jsons_p8())
    assert len(activos) == 8


def test_extractos_solapados_se_cargan_sin_duplicar(env):
    filas = [{"fecha": f"0{d}/08/2026", "cred": 10.0 * d, "saldo": 1000.0 + sum(10.0 * k for k in range(1, d + 1)),
              "cod": str(d)} for d in range(1, 6)]
    _extracto_bnb(env.cfg.entrada / "a_1_al_4.xlsx", filas[0:4])
    _extracto_bnb(env.cfg.entrada / "b_3_al_5.xlsx", filas[2:5])  # se solapan 2 movimientos
    res = env.orq.ciclo()
    assert [r.estado for r in res] == ["PROCESADO", "PROCESADO"], [r.mensaje for r in res]
    assert sorted(r.movimientos for r in res) == [3, 4]
    activos, bitacoras = _p8_v5(*env.jsons_p8())
    assert len(activos) == 5  # 4 + 3 - 2 repetidos
    assert sorted(b["CANTIDAD_YA_EXISTE"] for b in bitacoras) == [0, 2]


# ------------------------------------------------------------------ año dinamico de punta a punta
@pytest.mark.parametrize("anio", [2026, 2027, 2028])
def test_extracto_de_cualquier_año_llega_a_p8(env, monkeypatch, anio):
    motor = P0._modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    monkeypatch.setattr(motor, "fecha_referencia", lambda: pd.Timestamp(f"{anio}-12-20"))
    _extracto_bnb(env.cfg.entrada / "x.xlsx", [{"fecha": f"05/03/{anio}", "cred": 100.0, "saldo": 1100.0, "cod": "1"}])
    (r,) = env.orq.ciclo()
    assert r.estado == "PROCESADO", r.mensaje
    (j,) = env.jsons_p8()
    assert _claves(j)[0].split("|")[2] == f"{anio}0305"


def test_año_fuera_de_rango_es_error_legible(env, monkeypatch):
    motor = P0._modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    monkeypatch.setattr(motor, "fecha_referencia", lambda: pd.Timestamp("2026-10-08"))
    _extracto_bnb(env.cfg.entrada / "x.xlsx", [{"fecha": "05/03/2062", "cred": 100.0, "saldo": 1100.0}])
    (r,) = env.orq.ciclo()
    assert (r.estado, r.codigo) == ("ERROR", "ANIO_FUERA_DE_RANGO") and "2062" in r.mensaje


# ------------------------------------------------------------------ descubrimiento
def test_archivos_transitorios_se_ignoran(env):
    for n in ("~$bcp.xlsx", "descarga.xls.crdownload", "x.tmp", ".oculto.xls", "desktop.ini", "x.xls.p0tmp"):
        env.poner(n, contenido=b"x")
    (env.cfg.entrada / "subcarpeta").mkdir()
    assert env.orq.ciclo() == [] and len(env.nombres(env.cfg.entrada)) == 7
    assert env.en(env.cfg.error) == []


def test_archivo_recien_copiado_espera_a_estar_estable(tmp_path):
    e = Entorno(tmp_path)
    e.cfg.estable_s = 30.0
    ruta = e.fixture("bcp_me_1.xls")
    assert e.orq.ciclo() == [] and ruta.exists()  # recien creado: aun podria estar copiandose
    viejo = time.time() - 120
    os.utime(ruta, (viejo, viejo))
    (r,) = e.orq.ciclo()
    assert r.estado == "PROCESADO"


def test_orden_de_procesamiento_por_antiguedad(env):
    a = env.fixture("bcp_me_1.xls", como="b_nuevo.xls")
    b = env.fixture("union_mn_2.xls", como="a_viejo.xls")
    os.utime(b, (time.time() - 500, time.time() - 500))
    assert [r.archivo for r in env.orq.ciclo()] == ["a_viejo.xls", "b_nuevo.xls"]


# ------------------------------------------------------------------ varias sedes, un solo motor
def _sedes(tmp_path, **sedes):
    ruta = tmp_path / "sedes.json"
    ruta.write_text(json.dumps({"sedes": sedes}), encoding="utf-8")
    return ruta


def test_cbba_usa_el_registro_base_sin_copiarlo(env):
    assert env.cfg.registro == P0.REGISTRO_BASE


def test_otra_sede_comparte_formatos_y_tiene_sus_propias_cuentas(tmp_path):
    adicionales = tmp_path / "cuentas_lpz.json"
    adicionales.write_text(json.dumps([{"id": "BNB_LPZ_1", "formato": "BNB_EXTRACTO_V1", "banco": "BNB",
                                        "cuenta": "3777777777", "moneda": "BOB", "activa": True}]), encoding="utf-8")
    sedes = _sedes(tmp_path, LPZ={"nombre": "La Paz", "carpeta_p0": "CONTROL_DEPOSITOS/P0_EXTRACTOS",
                                  "carpeta_carga": "CARGA_EXTRACTOS_BANCARIOS", "cuentas": [], "cuentas_adicionales": str(adicionales)})
    e = Entorno(tmp_path, sedes_json=sedes, sede="LPZ")
    ids = [c["id"] for c in json.loads(e.cfg.registro.read_text(encoding="utf-8"))["CUENTAS"]]
    assert ids == ["BNB_LPZ_1"]
    # cuenta de LPZ (nueva, solo una entrada de registro) -> procesada con el MISMO motor y formatos
    _extracto_bnb(e.cfg.entrada / "lpz.xlsx", [{"fecha": "05/08/2026", "cred": 100.0, "saldo": 1100.0}], cuenta="3777777777")
    # cuenta de CBBA presentada en LPZ -> no registrada para esa sede
    e.fixture("bcp_me_1.xls")
    res = {r.archivo: r for r in e.orq.ciclo()}
    assert res["lpz.xlsx"].estado == "PROCESADO", res["lpz.xlsx"].mensaje
    assert res["bcp_me_1.xls"].estado == "ERROR"
    (j,) = e.jsons_p8()
    assert _claves(j)[0].startswith("BNB|3777777777|20260805")


def test_sede_con_subconjunto_de_cuentas_base(tmp_path):
    reg = P0.registro_para_sede({"cuentas": ["BCP_ME"]}, tmp_path / "t", sede="SCZ")
    assert [c["id"] for c in json.loads(reg.read_text(encoding="utf-8"))["CUENTAS"]] == ["BCP_ME"]
    with pytest.raises(P0.ConfigError, match="inexistentes"):
        P0.registro_para_sede({"cuentas": ["NO_EXISTE"]}, tmp_path / "t")


def test_cuentas_adicionales_con_id_repetido_es_error_de_configuracion(tmp_path):
    ad = tmp_path / "ad.json"
    ad.write_text(json.dumps([{"id": "BCP_ME", "formato": "BCP_EXTRACTO_V1"}]), encoding="utf-8")
    with pytest.raises(P0.ConfigError, match="repetidos"):
        P0.registro_para_sede({"cuentas": "TODAS", "cuentas_adicionales": str(ad)}, tmp_path / "t")


# ------------------------------------------------------------------ configuracion, bloqueo, linea de comandos
def test_config_crea_las_carpetas_base_pero_no_años_ni_meses(tmp_path):
    docs = tmp_path / "Documents"
    raiz = docs / "CONTROL_DEPOSITOS" / "P0_EXTRACTOS"
    raiz.mkdir(parents=True)
    cfg = P0.cargar_config("CBBA", documentos=str(docs), trabajo=tmp_path / "t")
    P0.validar_config(cfg)
    assert sorted(p.name for p in raiz.iterdir()) == ["CARGA_EXTRACTOS_BANCARIOS", "ENTRADA", "ERROR", "PROCESADOS"]
    assert cfg.carga == raiz / "CARGA_EXTRACTOS_BANCARIOS"
    assert list((raiz / "PROCESADOS").iterdir()) == [] and list((raiz / "ERROR").iterdir()) == []  # nada por adelantado
    assert not (docs / "P8_PILOTO").exists()  # la carpeta piloto anterior ya no es el destino


def test_config_no_crea_un_arbol_falso_si_la_ruta_esta_mal(tmp_path):
    cfg = P0.cargar_config("CBBA", documentos=str(tmp_path / "typo"), trabajo=tmp_path / "t")
    with pytest.raises(P0.ConfigError, match="no existe la carpeta"):
        P0.validar_config(cfg)
    assert not (tmp_path / "typo").exists()


def test_config_sede_desconocida_y_ruta_relativa_sin_documentos(tmp_path, monkeypatch):
    monkeypatch.delenv("CBBA_DOCUMENTOS", raising=False)
    with pytest.raises(P0.ConfigError, match="no definida"):
        P0.cargar_config("XXX", documentos=str(tmp_path))
    with pytest.raises(P0.ConfigError, match="--documentos"):
        P0.cargar_config("CBBA")


def test_candado_impide_dos_instancias_y_reemplaza_uno_vencido(tmp_path):
    with P0.candado(tmp_path) as lock:
        with pytest.raises(P0.ConfigError, match="otra instancia"):
            with P0.candado(tmp_path):
                pass
        assert lock.exists()
    assert not lock.exists()
    lock.write_text("x")
    viejo = time.time() - P0.LOCK_VENCE_S - 10
    os.utime(lock, (viejo, viejo))
    with P0.candado(tmp_path):
        pass


def test_linea_de_comandos_una_vez(tmp_path, capsys):
    e = Entorno(tmp_path)
    e.fixture("bcp_me_1.xls")
    e.poner("roto.xls", contenido=b"basura")
    rc = P0.main(["--sede", "CBBA", "--documentos", str(e.docs), "--trabajo", str(tmp_path / "trabajo2"),
                  "--una-vez", "--estable", "0"])
    assert rc == 0
    assert "bcp_me_1.xls" in e.en(e.cfg.procesados) and "roto.xls" in e.en(e.cfg.error)
    assert P0.main(["--sede", "CBBA", "--documentos", str(tmp_path / "no_existe"), "--una-vez"]) == 2
    for h in list(P0.log.handlers):  # cierra el archivo de log
        h.close(); P0.log.removeHandler(h)


# ------------------------------------------------------------------ estructura final: AAAA/MM_MES y CARGA_EXTRACTOS_BANCARIOS
def _arbol(base):
    return sorted(str(p.relative_to(base)).replace(os.sep, "/") for p in base.rglob("*") if p.is_dir())


def test_los_nombres_de_mes_son_fijos_e_independientes_del_idioma(env):
    assert P0.MESES == ("01_ENERO", "02_FEBRERO", "03_MARZO", "04_ABRIL", "05_MAYO", "06_JUNIO", "07_JULIO",
                        "08_AGOSTO", "09_SEPTIEMBRE", "10_OCTUBRE", "11_NOVIEMBRE", "12_DICIEMBRE")
    for m in range(1, 13):
        assert P0.carpeta_mes(Path("PROCESADOS"), datetime(2026, m, 1)) == Path("PROCESADOS") / "2026" / P0.MESES[m - 1]


def test_exito_va_a_procesados_año_mes(env):
    env.fixture("bcp_me_1.xls")
    (r,) = env.orq.ciclo()
    destino = env.cfg.procesados / "2026" / "10_OCTUBRE"
    assert r.estado == "PROCESADO" and Path(r.destino) == destino / "bcp_me_1.xls"
    assert env.nombres(destino) == ["bcp_me_1.xls", "bcp_me_1.xls.p0.json"]
    assert env.nombres(env.cfg.procesados) == ["2026"] and env.nombres(env.cfg.procesados / "2026") == ["10_OCTUBRE"]
    assert env.nombres(env.cfg.entrada) == []


def test_error_va_a_error_año_mes_con_su_error_json(env):
    env.poner("roto.xls", contenido=b"basura")
    (r,) = env.orq.ciclo()
    destino = env.cfg.error / "2026" / "10_OCTUBRE"
    assert r.estado == "ERROR" and Path(r.destino) == destino / "roto.xls"
    assert env.nombres(destino) == ["roto.xls", "roto.xls.error.json"]
    assert json.loads((destino / "roto.xls.error.json").read_text(encoding="utf-8"))["codigo_error"] == "ARCHIVO_ILEGIBLE"
    assert env.nombres(env.cfg.procesados) == []  # un error no crea carpetas en PROCESADOS


def test_el_json_se_publica_en_carga_extractos_bancarios_y_no_en_subcarpetas(env):
    env.fixture("bcp_me_1.xls")
    env.orq.ciclo()
    (j,) = env.jsons_p8()
    assert j.parent == env.cfg.carga and env.cfg.carga.name == "CARGA_EXTRACTOS_BANCARIOS"
    assert j.parent.parent.name == "P0_EXTRACTOS" and j.name.startswith("DEPOSITOS_ACTIVOS__") and j.suffix == ".json"
    assert [p for p in env.cfg.carga.iterdir() if p.is_dir()] == []
    assert not (env.docs / "P8_PILOTO").exists()


def test_los_meses_se_crean_solo_cuando_se_usan_sin_adelantar_nada(env):
    assert _arbol(env.cfg.procesados) == [] and _arbol(env.cfg.error) == []
    env.fixture("bcp_me_1.xls")
    env.orq.ciclo()
    assert _arbol(env.cfg.procesados) == ["2026", "2026/10_OCTUBRE"] and _arbol(env.cfg.error) == []
    env.ahora = datetime(2026, 11, 3, 8, 0)  # el mes siguiente se crea al usarse; octubre no se toca
    env.fixture("union_mn_2.xls")
    env.poner("malo.xls", contenido=b"x")
    env.orq.ciclo()
    assert _arbol(env.cfg.procesados) == ["2026", "2026/10_OCTUBRE", "2026/11_NOVIEMBRE"]
    assert _arbol(env.cfg.error) == ["2026", "2026/11_NOVIEMBRE"]
    assert env.nombres(env.cfg.procesados / "2026" / "10_OCTUBRE") == ["bcp_me_1.xls", "bcp_me_1.xls.p0.json"]


def test_cambio_de_diciembre_a_enero_crea_el_año_nuevo(env):
    env.ahora = datetime(2026, 12, 31, 23, 58)
    env.fixture("bcp_me_1.xls")
    env.poner("roto_dic.xls", contenido=b"x")
    env.orq.ciclo()
    env.ahora = datetime(2027, 1, 1, 0, 2)
    env.fixture("union_mn_2.xls")
    env.poner("roto_ene.xls", contenido=b"x")
    env.orq.ciclo()
    assert _arbol(env.cfg.procesados) == ["2026", "2026/12_DICIEMBRE", "2027", "2027/01_ENERO"]
    assert _arbol(env.cfg.error) == ["2026", "2026/12_DICIEMBRE", "2027", "2027/01_ENERO"]
    assert "bcp_me_1.xls" in env.nombres(env.cfg.procesados / "2026" / "12_DICIEMBRE")
    assert "union_mn_2.xls" in env.nombres(env.cfg.procesados / "2027" / "01_ENERO")
    assert "roto_ene.xls.error.json" in env.nombres(env.cfg.error / "2027" / "01_ENERO")


def test_misma_carpeta_mes_con_nombres_repetidos_no_pisa_nada(env):
    for _ in range(3):  # mismo nombre y mismo segundo (reloj fijo): se conservan los tres
        env.fixture("bcp_me_1.xls")
        env.orq.ciclo()
    xls = [n for n in env.en(env.cfg.procesados) if n.endswith(".xls")]
    assert len(xls) == 3 and len(set(xls)) == 3
    assert len(env.jsons_p8()) == 3


def test_entrada_es_plana_las_subcarpetas_no_se_procesan(env):
    sub = env.cfg.entrada / "2026" / "10_OCTUBRE"
    sub.mkdir(parents=True)
    shutil.copy(EXTRACTOS / "bcp_me_1.xls", sub / "dentro.xls")
    assert env.orq.ciclo() == [] and (sub / "dentro.xls").exists()
