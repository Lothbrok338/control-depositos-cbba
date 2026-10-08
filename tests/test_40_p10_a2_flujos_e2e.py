"""P10-A.2 — los flujos REALES (JSON generado) ejecutados con el intérprete local sobre un tenant simulado.

Extractos reales (tests/fixtures/extractos), motor real de P0 y generador aprobado de A.1 detrás del servicio p10-api real (TestClient).
SharePoint/OneDrive son simulados (p10/tenant_simulado.py): se prueba la LÓGICA de extremo a extremo, no la plataforma.
"""
import base64
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from p10 import api, estado as E  # noqa: E402
from p10.ensayo_wdl import Ejecucion  # noqa: E402
from p10.flujo import construir as F  # noqa: E402
from p10.tenant_simulado import TenantSimulado  # noqa: E402

pytestmark = pytest.mark.p10

FIXTURE = RAIZ / "tests/fixtures/extractos/bnb_ahorro_2.xls"
GID = "BNB|3501936692|BOB|2026-08"
XLSX = "/CONTROL_DEPOSITOS/P10_HISTORICO/2026/08_AGOSTO/BNB/EXTRACTO_HISTORICO_BNB_3501936692_BOB_2026-08.xlsx"
ESTADO = "/CONTROL_DEPOSITOS/P10_ESTADO/2026/08_AGOSTO/BNB/ESTADO_P10_BNB_3501936692_BOB_2026-08.json.gz"
EXTRACTO = "/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS/2026/10_OCTUBRE/08/bnb_ahorro_2.xls"


def con_dominio(d):
    return json.loads(json.dumps(d).replace(F.MARCADOR_DOMINIO, "p10-prueba"))


@pytest.fixture(scope="module")
def defs():
    return con_dominio(F.construir_definicion_sync()), con_dominio(F.construir_definicion_prov())


class Banco:
    """Un tenant con la lista ya provisionada (por el propio flujo de provisión)."""

    def __init__(self, defs, monkeypatch):
        monkeypatch.setenv("P10_API_TOKEN", "t" * 24)
        self.sync, self.prov = defs
        self.t = TenantSimulado(api.app)
        self.t.poner_hora_local("2026-10-08T10:00:00")
        self.n = 0
        r = Ejecucion(self.prov, self.t).ejecutar()
        assert r.estado_final == "Succeeded", (r.error_final, [(k, v) for k, v in r.errores.items()])

    def ciclo(self, hora_local=None):
        if hora_local:
            self.t.poner_hora_local(hora_local)
        self.n += 1
        return Ejecucion(self.sync, self.t, f"corrida-{self.n:04d}").ejecutar()

    def control(self, clave=None):
        its = self.t.listas["P10_Control"].items
        return its if clave is None else next((i for i in its if i["CLAVE_CONTROL"] == clave), None)

    def estado(self):
        return E.desempaquetar(self.t.archivos[ESTADO]["contenido"])

    def auditoria(self, ruta=XLSX):
        ws = load_workbook(io.BytesIO(self.t.archivos[ruta]["contenido"]))["AUDITORIA"]
        filas = list(ws.iter_rows(values_only=True))
        return [dict(zip(filas[0], f)) for f in filas[1:]]

    def soltar(self, nombre="bnb_ahorro_2.xls", dia="08", mes="10_OCTUBRE"):
        self.t.soltar_en_procesados(nombre, FIXTURE.read_bytes(), 2026, mes, dia)

    def cargar_lista_p8(self):
        """P8: carga la lista Depositos_Activos con los movimientos del estado (sin estado operativo todavía)."""
        _, _, filas, _ = E.entradas_generador(self.estado())
        self.t.depositos.cargar(filas)

    def claves(self):
        return sorted(i["CLAVE_TRANSACCION"] for i in self.t.depositos.items.values())

    def total_acciones(self, r):
        return len(r.orden)


@pytest.fixture()
def b(defs, monkeypatch):
    return Banco(defs, monkeypatch)


def sha(x):
    return hashlib.sha256(x).hexdigest()


# ====================================================================== provisión
def test_la_provision_crea_la_lista_con_todas_las_columnas_indices_y_lock_y_es_idempotente(b):
    lista = b.t.listas["P10_Control"]
    from p10.control_lista import NOMBRES_CONTROL
    assert set(NOMBRES_CONTROL) <= set(lista.campos)
    assert "CLAVE_CONTROL" in lista.unicos and {"CLAVE_CONTROL", "TIPO", "PERIODO"} <= lista.indexados
    assert lista.campos["Title"]["requerido"] is False
    assert [i["CLAVE_CONTROL"] for i in lista.items] == ["LOCK"]
    r = Ejecucion(b.prov, b.t).ejecutar()                                   # 2ª vez: nada se duplica ni falla
    assert r.estado_final == "Succeeded" and len(lista.items) == 1 and len(lista.campos) == len(NOMBRES_CONTROL) + 1


def test_la_provision_avisa_si_falta_una_columna(b):
    del b.t.listas["P10_Control"].campos["HUELLA"]
    b.t.fallar("HttpRequest", "createfieldasxml", veces=1, http=500)         # la reparación también falla
    r = Ejecucion(b.prov, b.t).ejecutar()
    assert r.estado_final == "Failed"                                        # la ejecución queda en rojo; no certifica


# ====================================================================== ENTRADA -> PROCESADOS -> histórico
def test_extracto_nuevo_en_procesados_genera_estado_xlsx_y_control(b):
    b.soltar()
    r = b.ciclo()
    assert r.estado_final == "Succeeded" and r.variables["varDetalles"] == []
    assert XLSX in b.t.archivos and ESTADO in b.t.archivos
    wb = load_workbook(io.BytesIO(b.t.archivos[XLSX]["contenido"]))
    assert wb.sheetnames == ["EXTRACTO", "AUDITORIA"] and len(b.auditoria()) == 95
    g = b.control("GRUPO|" + GID)
    assert g["ESTADO"] == "OK" and g["VERSION_ESTADO"] == 1 and g["MOVIMIENTOS"] == 95 and g["HASH_XLSX"] == sha(b.t.archivos[XLSX]["contenido"])
    assert b.control("EXTRACTO|" + EXTRACTO)["ESTADO"] == "PROCESADO"
    lock = b.control("LOCK")
    assert lock["LOCK_HASTA"] == "" and lock["LOCK_ID"] == "" and lock["ULTIMA_COMPLETA"] == "2026-10-08"


def test_el_xlsx_que_escribe_el_flujo_es_el_que_el_generador_aprobado_regenera_desde_el_estado_guardado(b):
    from p10 import sincronizacion as S
    b.soltar()
    b.ciclo()
    contenido, _ = S.construir_xlsx(b.estado(), S.registro_de_sede("CBBA"))
    assert b.t.archivos[XLSX]["contenido"] == contenido


def test_un_ciclo_sin_novedades_no_llama_a_extracto_ni_a_sincronizar_ni_escribe_archivos(b):
    b.soltar()
    b.ciclo()
    b.t.registro.clear()
    b.t.api_llamadas.clear()
    antes = {k: v["contenido"] for k, v in b.t.archivos.items()}
    r = b.ciclo("2026-10-08T10:15:00")
    assert r.estado_final == "Succeeded"
    assert set(b.t.api_llamadas) <= {"/p10/ciclo", "/p10/plan"}
    assert {k: v["contenido"] for k, v in b.t.archivos.items()} == antes
    escrituras = [op for op, _ in b.t.registro if op in ("CreateFile", "UpdateFile") or op in ("HttpRequest:POST",) and False]
    assert escrituras == []
    assert b.total_acciones(r) <= 40, b.total_acciones(r)           # consumo de un ciclo ocioso (presupuesto diario de Power Automate)


def test_el_mismo_extracto_acumulativo_otro_dia_no_cambia_nada(b):
    b.soltar()
    b.ciclo()
    xlsx0, estado0 = b.t.archivos[XLSX]["contenido"], b.t.archivos[ESTADO]["contenido"]
    b.soltar(dia="09")
    b.t.avanzar(days=1)
    r = b.ciclo("2026-10-09T09:00:00")
    assert r.estado_final == "Succeeded"
    def valores(x):
        wb = load_workbook(io.BytesIO(x))
        return {ws.title: [[c.value for c in fila] for fila in ws.iter_rows()] for ws in wb}
    assert valores(b.t.archivos[XLSX]["contenido"]) == valores(xlsx0)       # mismo contenido (solo cambia la fecha de corte del archivo) and b.t.archivos[ESTADO]["contenido"] == estado0
    assert b.control("EXTRACTO|" + EXTRACTO.replace("/08/", "/09/"))["ESTADO"] == "PROCESADO"


# ====================================================================== Power Apps -> histórico
def test_confirmar_y_revertir_en_power_apps_actualizan_el_historico_del_mes_del_movimiento(b):
    b.soltar()
    b.ciclo()
    b.cargar_lista_p8()
    c1 = b.claves()[3]
    b.t.avanzar(hours=1)
    b.t.depositos.confirmar(c1, estudiante="MARIA PEREZ", usuario="caja@univalle.edu", codigo_estudiante="E-123")
    r = b.ciclo("2026-10-12T09:30:00")                                 # confirmado el 12/10: el movimiento es de AGOSTO
    assert r.estado_final == "Succeeded"
    fila = next(f for f in b.auditoria() if f["CLAVE TRANSACCIÓN"] == c1)
    assert fila["ESTADO"] == "CONFIRMADO" and fila["ESTUDIANTE"] == "MARIA PEREZ" and fila["CODIGO_ESTUDIANTE"] == "E-123"
    assert fila["CONFIRMADO POR"] == "caja@univalle.edu" and fila["FECHA CONFIRMACIÓN"] is not None
    assert b.control("GRUPO|" + GID)["HASH_OPERATIVO"]
    assert not any(k for k in b.t.archivos if "2026/10_OCTUBRE/BNB" in k)         # no se creó ningún histórico de octubre
    b.t.avanzar(hours=2)
    b.t.depositos.revertir(c1)
    r = b.ciclo("2026-10-12T11:45:00")
    assert r.estado_final == "Succeeded"
    fila = next(f for f in b.auditoria() if f["CLAVE TRANSACCIÓN"] == c1)
    assert fila["ESTADO"] == "DISPONIBLE" and fila["ESTUDIANTE"] is None and fila["ULTIMA_REVERSION_ID"]


def test_un_cambio_en_la_lista_actualiza_solo_el_grupo_afectado(b):
    b.soltar()
    b.ciclo()
    b.cargar_lista_p8()
    b.ciclo("2026-10-08T10:15:00")                                       # P8 cargó la lista: se toma una vez
    b.t.api_llamadas.clear()
    b.t.registro.clear()
    b.t.avanzar(minutes=20)
    b.t.depositos.confirmar(b.claves()[0], estudiante="X")
    b.ciclo("2026-10-08T10:45:00")
    assert b.t.api_llamadas.count("/p10/sincronizar") == 1 and "/p10/extracto" not in b.t.api_llamadas
    assert [op for op, _ in b.t.registro if op in ("CreateFile", "UpdateFile")] == ["UpdateFile", "UpdateFile"]   # xlsx y estado


def test_orden_de_confirmacion_del_control_xlsx_primero_estado_despues_control_al_final(b):
    b.soltar()
    b.ciclo()
    b.cargar_lista_p8()
    b.t.registro.clear()
    b.t.depositos.confirmar(b.claves()[0], estudiante="X")
    b.ciclo("2026-10-08T10:15:00")
    ops = [(op, d) for op, d in b.t.registro if op in ("UpdateFile", "HttpRequest:POST")]
    orden = [d for op, d in ops if op == "UpdateFile"]
    assert orden == [XLSX, ESTADO]                                             # el XLSX se escribe antes que el estado
    ult_archivo = max(i for i, (op, _) in enumerate(b.t.registro) if op == "UpdateFile")
    assert any(op == "HttpRequest:POST" for op, _ in b.t.registro[ult_archivo + 1:])    # y el control después de ambos


# ====================================================================== recuperación
def test_xlsx_borrado_o_alterado_se_regenera_en_el_ciclo_completo_de_la_noche(b):
    b.soltar()
    b.ciclo()
    original = b.t.archivos[XLSX]["contenido"]
    del b.t.archivos[XLSX]
    r = b.ciclo("2026-10-09T02:05:00")
    assert r.estado_final == "Succeeded" and b.t.archivos[XLSX]["contenido"] == original
    b.t.archivos[XLSX]["contenido"] = original[:-20] + b"X" * 20             # alterado
    r = b.ciclo("2026-10-10T02:05:00")
    assert b.t.archivos[XLSX]["contenido"] == original
    r = b.ciclo("2026-10-11T02:05:00")                                       # intacto: no se reescribe
    assert [op for op, d in b.t.registro if op == "UpdateFile" and d == XLSX].__len__() == 1


def test_estado_borrado_se_reconstruye_desde_los_extractos_y_queda_igual(b):
    b.soltar()
    b.ciclo()
    b.cargar_lista_p8()
    b.t.depositos.confirmar(b.claves()[1], estudiante="ANA")
    b.ciclo("2026-10-08T10:30:00")
    xlsx0, est0 = b.t.archivos[XLSX]["contenido"], b.estado()
    del b.t.archivos[ESTADO]
    r1 = b.ciclo("2026-10-09T02:05:00")                                      # nocturno: detecta, marca RECONSTRUIR
    g = b.control("GRUPO|" + GID)
    assert g["ESTADO"] in ("RECONSTRUIR", "OK")
    for hora in ("2026-10-09T02:20:00", "2026-10-09T02:35:00", "2026-10-09T02:50:00"):
        b.ciclo(hora)
    g = b.control("GRUPO|" + GID)
    assert g["ESTADO"] == "OK" and not g.get("RECONSTRUIR_DESDE")
    est1 = b.estado()
    assert set(est1["movimientos"]) == set(est0["movimientos"]) and est1["operativo"]["filas"] == est0["operativo"]["filas"]
    # los movimientos que ya están en la lista conservan su lote y fecha de carga: el XLSX queda idéntico al de antes de la pérdida
    def valores(x):
        wb = load_workbook(io.BytesIO(x))
        return {ws.title: [[c.value for c in fila] for fila in ws.iter_rows()] for ws in wb}
    assert valores(b.t.archivos[XLSX]["contenido"]) == valores(xlsx0)       # mismo contenido (solo cambia la fecha de corte del archivo)


def test_estado_corrupto_o_restaurado_a_una_version_vieja_se_detecta_y_reconstruye(b):
    b.soltar()
    b.ciclo()
    b.cargar_lista_p8()
    viejo = b.t.archivos[ESTADO]["contenido"]
    b.t.depositos.confirmar(b.claves()[0], estudiante="X")
    b.ciclo("2026-10-08T10:15:00")
    xlsx_ok = b.t.archivos[XLSX]["contenido"]
    b.t.archivos[ESTADO]["contenido"] = viejo                                # alguien restauró una versión anterior
    b.t.depositos.confirmar(b.claves()[1], estudiante="Y")
    b.ciclo("2026-10-08T10:30:00")
    assert b.control("GRUPO|" + GID)["ESTADO"] == "RECONSTRUIR"
    for hora in ("10:45", "11:00", "11:15"):
        b.ciclo(f"2026-10-08T{hora}:00")
    assert b.control("GRUPO|" + GID)["ESTADO"] == "OK"
    filas = {f["CLAVE TRANSACCIÓN"]: f["ESTADO"] for f in b.auditoria()}
    assert filas[b.claves()[0]] == "CONFIRMADO" and filas[b.claves()[1]] == "CONFIRMADO"
    assert xlsx_ok != b.t.archivos[XLSX]["contenido"]


def test_falla_del_servicio_deja_el_extracto_pendiente_libera_el_lock_y_el_siguiente_ciclo_lo_completa(b):
    b.soltar()
    b.t.fallar("api", "/p10/extracto", veces=1, http=503)
    r = b.ciclo()
    assert r.estado_final == "Failed" and r.error_final[0] == "P10_CICLO_CON_ERRORES"
    assert b.control("EXTRACTO|" + EXTRACTO) is None and XLSX not in b.t.archivos
    assert b.control("LOCK")["LOCK_HASTA"] == "" and b.control("LOCK")["ULTIMA_COMPLETA"] == ""
    r = b.ciclo("2026-10-08T10:15:00")
    assert r.estado_final == "Succeeded" and XLSX in b.t.archivos and b.control("LOCK")["ULTIMA_COMPLETA"] == "2026-10-08"


def test_falla_al_escribir_el_estado_no_confirma_el_control_y_el_reintento_converge(b):
    b.soltar()
    b.t.fallar("CreateFile", "ESTADO_P10", veces=1)
    r = b.ciclo()
    assert r.estado_final == "Failed" and XLSX in b.t.archivos and ESTADO not in b.t.archivos
    assert b.control("GRUPO|" + GID) is None and b.control("EXTRACTO|" + EXTRACTO) is None
    r = b.ciclo("2026-10-08T10:15:00")
    assert r.estado_final == "Succeeded" and ESTADO in b.t.archivos and b.control("GRUPO|" + GID)["ESTADO"] == "OK"
    assert b.control("EXTRACTO|" + EXTRACTO)["ESTADO"] == "PROCESADO"


def test_caida_del_ciclo_entre_estado_y_control_se_recupera_sin_duplicados_ni_falsa_alteracion(b):
    b.soltar()
    b.t.caida = {"op": "CreateFile", "contiene": "ESTADO_P10", "despues_de": 0}
    r = b.ciclo()                                                            # muere al intentar crear el estado
    assert r.estado_final == "Cancelled" and b.control("LOCK")["LOCK_HASTA"] != ""
    r = b.ciclo("2026-10-08T10:20:00")                                       # lock vigente: no hace nada
    assert r.estado_final == "Succeeded" and b.t.api_llamadas.count("/p10/extracto") == 1
    r = b.ciclo("2026-10-08T11:10:00")                                       # lock vencido (60 min): retoma
    assert r.estado_final == "Succeeded" and b.control("GRUPO|" + GID)["ESTADO"] == "OK"
    assert len([k for k in b.t.archivos if "P10_ESTADO" in k]) == 1


def test_caida_con_el_estado_ya_escrito_y_el_control_sin_confirmar_no_dispara_reconstruccion(b):
    b.soltar()
    b.ciclo()
    b.cargar_lista_p8()
    b.t.depositos.confirmar(b.claves()[0], estudiante="X")
    b.t.caida = {"op": "HttpRequest:POST", "contiene": "/items", "despues_de": 0}
    # el primer POST del ciclo es el de bloqueo; la caída se arma para después de escribir estado: cuenta de escrituras
    b.t.caida = None
    b.t.caida = {"op": "UpdateFile", "contiene": "ESTADO_P10", "despues_de": 0}
    r = b.ciclo("2026-10-08T10:30:00")
    assert r.estado_final == "Cancelled"                                       # murió justo antes de escribir el estado
    r = b.ciclo("2026-10-08T11:40:00")
    assert r.estado_final == "Succeeded" and b.control("GRUPO|" + GID)["ESTADO"] == "OK"
    fila = next(f for f in b.auditoria() if f["CLAVE TRANSACCIÓN"] == b.claves()[0])
    assert fila["ESTADO"] == "CONFIRMADO"


# ====================================================================== concurrencia y bloqueo
def test_con_el_bloqueo_vigente_otra_ejecucion_no_toca_nada(b):
    b.soltar()
    lock = b.control("LOCK")
    lock["LOCK_HASTA"], lock["LOCK_ID"] = "2026-10-08T10:50:00", "otra-ejecucion"
    r = b.ciclo()
    assert r.estado_final == "Succeeded" and not b.t.api_llamadas[1:] and XLSX not in b.t.archivos
    assert lock["LOCK_ID"] == "otra-ejecucion"


def test_si_otra_ejecucion_toma_el_bloqueo_entre_la_lectura_y_la_toma_se_pierde_la_carrera_sin_trabajar(b):
    b.soltar()
    b.t.fallar("HttpRequest", "/items(1)", veces=1, http=412)               # ETag distinto: la otra ejecución llegó antes
    r = b.ciclo()
    assert r.estado_final == "Succeeded" and XLSX not in b.t.archivos and "/p10/extracto" not in b.t.api_llamadas


def test_sin_token_el_flujo_falla_antes_de_tocar_datos(b):
    del b.t.archivos["/CONTROL_DEPOSITOS/P10_CONFIG/P10_API_TOKEN.txt"]
    b.soltar()
    r = b.ciclo()
    assert r.estado_final == "Failed" and b.t.api_llamadas == [] and b.control("LOCK")["LOCK_HASTA"] == ""
    b.t.archivar_token()
    b.t.token = "mal-token-mal-token-0000"
    b.t.archivos["/CONTROL_DEPOSITOS/P10_CONFIG/P10_API_TOKEN.txt"]["contenido"] = b"incorrecto-incorrecto-1"
    r = b.ciclo()
    assert r.estado_final == "Failed" and XLSX not in b.t.archivos


# ====================================================================== extractos con error y meses antiguos
def test_un_extracto_que_el_motor_rechaza_se_anota_con_intentos_y_deja_de_reintentarse(b):
    b.t.soltar_en_procesados("roto.xls", b"esto no es un excel", 2026, "10_OCTUBRE", "08")
    ruta = "/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS/2026/10_OCTUBRE/08/roto.xls"
    estados = []
    for h in ("10:00", "10:15", "10:30", "10:45"):
        b.ciclo(f"2026-10-08T{h}:00")
        it = b.control("EXTRACTO|" + ruta)
        estados.append((it["ESTADO"], it["INTENTOS"]))
    assert estados == [("ERROR", 1), ("ERROR", 2), ("ERROR_FINAL", 3), ("ERROR_FINAL", 3)]


def test_un_extracto_de_un_mes_anterior_se_incorpora_en_el_ciclo_completo(b):
    b.soltar(mes="08_AGOSTO", dia="20")
    b.ciclo("2026-10-08T01:00:00")                                           # antes de las 2: NORMAL no mira agosto
    assert XLSX not in b.t.archivos
    b.ciclo("2026-10-08T02:00:00")                                           # COMPLETO sí
    assert XLSX in b.t.archivos


# ====================================================================== estructura de los flujos
def contar(acciones):
    return sum(1 + contar(a.get("actions", {})) + contar(a.get("else", {}).get("actions", {})) for a in acciones.values())


def profundidad(acciones, nivel=1):
    m = nivel
    for a in acciones.values():
        for hijos in (a.get("actions", {}), a.get("else", {}).get("actions", {})):
            if hijos:
                m = max(m, profundidad(hijos, nivel + 1))
    return m


def todas(acciones):
    for n, a in acciones.items():
        yield n, a
        yield from todas(a.get("actions", {}))
        yield from todas(a.get("else", {}).get("actions", {}))


def textos(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from textos(x)
    elif isinstance(v, list):
        for x in v:
            yield from textos(x)


@pytest.mark.parametrize("cual", [0, 1])
def test_los_flujos_cumplen_los_limites_de_power_automate(defs, cual):
    d = defs[cual]
    assert contar(d["actions"]) <= 500 and profundidad(d["actions"]) <= 8
    nombres = [n for n, _ in todas(d["actions"])]
    assert len(nombres) == len(set(nombres)) and all(len(n) <= 80 and n.replace("_", "").isalnum() for n in nombres)
    for n, a in todas(d["actions"]):
        sd = a.get("runtimeConfiguration", {}).get("secureData")
        assert not sd or a["type"] in ("Http", "OpenApiConnection"), n


@pytest.mark.parametrize("cual", [0, 1])
def test_todas_las_expresiones_se_analizan_y_usan_solo_funciones_de_wdl(defs, cual):
    from p10.ensayo_wdl import Analizador, FUNCIONES_PERMITIDAS

    def funciones(n):
        if n[0] == "fn":
            yield n[1]
            for a in n[2]:
                yield from funciones(a)
        elif n[0] == "idx":
            yield from funciones(n[1])
            yield from funciones(n[2])

    for t in textos(defs[cual]["actions"]):
        if t.startswith("@") and not t.startswith("@@"):
            assert set(funciones(Analizador(t[1:]).completo())) <= FUNCIONES_PERMITIDAS, t


@pytest.mark.parametrize("cual", [0, 1])
def test_todo_runafter_apunta_a_una_accion_hermana_existente(defs, cual):
    def revisar(acciones):
        for n, a in acciones.items():
            for dep in a.get("runAfter", {}):
                assert dep in acciones, (n, dep)
            revisar(a.get("actions", {}))
            revisar(a.get("else", {}).get("actions", {}))
    revisar(defs[cual]["actions"])


def test_el_flujo_sincronizador_tiene_un_solo_disparador_con_concurrencia_uno_y_recurrencia_de_15_minutos(defs):
    t = next(iter(defs[0]["triggers"].values()))
    assert t["type"] == "Recurrence" and t["runtimeConfiguration"]["concurrency"]["runs"] == 1
    assert t["recurrence"]["schedule"]["minutes"] == [0, 15, 30, 45] and t["recurrence"]["schedule"]["hours"] == [str(h) for h in range(6, 23)]


def test_el_token_nunca_esta_en_el_flujo_ni_en_el_repositorio(defs):
    texto = json.dumps(defs)
    assert "Bearer " in texto and "t" * 24 not in texto
    assert "base64ToString(body('Leer_token')" in texto
    for a in (n for n in todas(defs[0]["actions"])):
        if a[1]["type"] == "Http":
            assert a[1]["runtimeConfiguration"]["secureData"]["properties"] == ["inputs", "outputs"]


def test_los_zip_son_deterministas_y_declaran_las_conexiones_que_usan():
    import zipfile
    a, b_ = F.zip_bytes(F.NOMBRE_SYNC, F.DESCRIPCIONES[F.NOMBRE_SYNC], F.construir_definicion_sync()), F.zip_bytes(
        F.NOMBRE_SYNC, F.DESCRIPCIONES[F.NOMBRE_SYNC], F.construir_definicion_sync())
    assert a == b_ and sha(a) == sha((RAIZ / F.ZIP_SYNC).read_bytes()) == sha(a)
    with zipfile.ZipFile(io.BytesIO(a)) as z:
        refs = [n for n in z.namelist() if n.endswith("definition.json")]
        d = json.loads(z.read(refs[0]))
        assert set(d["properties"]["connectionReferences"]) == {"shared_sharepointonline", "shared_onedriveforbusiness"}
    with zipfile.ZipFile(io.BytesIO((RAIZ / F.ZIP_PROV).read_bytes())) as z:
        d = json.loads(z.read([n for n in z.namelist() if n.endswith("definition.json")][0]))
        assert set(d["properties"]["connectionReferences"]) == {"shared_sharepointonline"}


def test_los_claves_de_control_que_emite_el_servicio_existen_en_la_lista_provisionada():
    """Todo campo que el servicio devuelve en `control` debe ser una columna de P10_Control (SharePoint rechaza columnas inexistentes)."""
    from p10.control_lista import NOMBRES_CONTROL
    from p10 import sincronizacion as S
    r = S.procesar_extracto(FIXTURE.read_bytes(), FIXTURE.name, "CBBA", EXTRACTO, "2026-10-08T10:00:00")
    bad = S.procesar_extracto(b"x", "x.xls", "CBBA", EXTRACTO, "2026-10-08T10:00:00")
    s = S.sincronizar_grupo("CBBA", GID, None, [base64.b64decode(r["grupos"][0]["parcial_b64"])], None, "2026-10-08T10:00:00")
    corrupto = S.sincronizar_grupo("CBBA", GID, b"basura", [], None, "2026-10-08T10:00:00")
    for c in (r["control"], bad["control"], s["control"], corrupto["control"]):
        assert set(c) <= set(NOMBRES_CONTROL), set(c) - set(NOMBRES_CONTROL)
