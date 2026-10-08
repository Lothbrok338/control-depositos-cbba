"""P10-A.2 — decisiones de cada ciclo (p10/plan.py): bloqueo, modo, extractos a incorporar, grupos sucios, verificación."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p10 import plan as PL, estado as E  # noqa: E402
from p10.lista_simulada import ListaSimulada  # noqa: E402

pytestmark = pytest.mark.p10

PREF = "/personal/gtorricot_univalle_edu/Documents"
RUTA = "/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS/2026/10_OCTUBRE/08/a.xls"
GID = "BNB|3000100152|BOB|2026-10"


def lock(hasta="", completa="", etag='"3"'):
    return {"Id": 1, "CLAVE_CONTROL": "LOCK", "TIPO": "LOCK", "LOCK_HASTA": hasta, "LOCK_ID": "x" if hasta else "",
            "ULTIMA_COMPLETA": completa, "__metadata": {"etag": etag}}


def grupo(gid=GID, **kw):
    d = {"Id": 7, "CLAVE_CONTROL": "GRUPO|" + gid, "TIPO": "GRUPO", "PERIODO": gid.split("|")[3], "ESTADO": "OK",
         "VERSION_ESTADO": 1, "HASH_OPERATIVO": "", "ESTADO_BYTES": 100, "XLSX_BYTES": 200}
    d.update(kw)
    return d


def extracto(ruta=RUTA, **kw):
    d = {"Id": 9, "CLAVE_CONTROL": "EXTRACTO|" + ruta, "TIPO": "EXTRACTO", "ESTADO": "PROCESADO", "BYTES": 1000, "INTENTOS": 0, "GRUPOS": GID}
    d.update(kw)
    return d


# ---------------------------------------------------------------- ciclo
def test_sin_elemento_lock_el_ciclo_se_niega():
    r = PL.ciclo("2026-10-08T10:00:00", [])
    assert not r["ok"] and r["codigo_error"] == "LOCK_NO_EXISTE"


def test_lock_libre_vencido_u_ocupado():
    assert PL.ciclo("2026-10-08T10:00:00", [lock()])["lock"]["libre"]
    assert PL.ciclo("2026-10-08T10:00:00", [lock("2026-10-08T09:59:59")])["lock"]["libre"]          # vencido = abandonado
    r = PL.ciclo("2026-10-08T10:00:00", [lock("2026-10-08T10:20:00")])
    assert not r["lock"]["libre"] and r["lock"]["ocupado_hasta"] == "2026-10-08T10:20:00"


def test_el_lease_dura_lo_declarado_y_trae_el_etag_para_el_cas():
    r = PL.ciclo("2026-10-08T10:00:00", [lock()])["lock"]
    assert r["hasta_nuevo"] == "2026-10-08T10:40:00" and r["etag"] == '"3"' and r["item_id"] == 1


def test_modo_normal_de_dia_y_completo_la_primera_vez_pasadas_las_2am():
    assert PL.ciclo("2026-10-08T01:45:00", [lock()])["modo"] == "NORMAL"
    assert PL.ciclo("2026-10-08T10:00:00", [lock(completa="2026-10-08")])["limite_extractos"] == PL.MAX_EXTRACTOS_NORMAL
    r = PL.ciclo("2026-10-08T02:00:00", [lock()])
    assert r["modo"] == "COMPLETO" and r["limite_extractos"] == PL.MAX_EXTRACTOS_COMPLETO
    assert PL.ciclo("2026-10-08T02:15:00", [lock(completa="2026-10-08")])["modo"] == "NORMAL"       # ya corrió hoy
    assert PL.ciclo("2026-10-08T14:00:00", [lock(completa="2026-10-07")])["modo"] == "COMPLETO"      # recupera un día perdido
    assert PL.ciclo("2026-10-08T14:00:00", [lock(completa="2026-10-08")], forzar_completo=True)["modo"] == "COMPLETO"


def test_ventanas_de_meses():
    n = PL.ciclo("2026-10-08T10:00:00", [lock(completa="2026-10-08")])
    assert n["modo"] == "NORMAL" and n["meses_escanear"] == ["2026-10", "2026-09", "2026-08"] and n["meses_listar"] == ["2026-10", "2026-09"]
    assert n["grupos_a_verificar"] == []
    c = PL.ciclo("2026-10-08T03:00:00", [lock(), grupo("BNB|1|BOB|2026-02"), grupo()])
    assert "2026-02" in c["meses_escanear"] and c["meses_listar"][0] == "2026-10" and c["meses_listar"][-1] == "2026-10"
    assert sorted(c["grupos_a_verificar"]) == ["BNB|1|BOB|2026-02", GID]


def test_meses_desplazados_cruzan_el_anio():
    assert PL.mes_desplazado("2026-01", -1) == "2025-12" and PL.mes_desplazado("2026-12", 1) == "2027-01"
    assert PL.meses_entre("2026-11", "2027-02") == ["2026-11", "2026-12", "2027-01", "2027-02"]


def test_huellas_por_mes():
    ctrl = [lock(), {"CLAVE_CONTROL": "MES|2026-10", "TIPO": "MES", "PERIODO": "2026-10", "HUELLA": "abc"}]
    assert PL.ciclo("2026-10-08T10:00:00", ctrl)["huellas"] == {"2026-10": "abc"}


# ---------------------------------------------------------------- plan de extractos
def arch(nombre="a.xls", largo=1000, creado="2026-10-08T09:00:00Z", dia="08"):
    return {"ServerRelativeUrl": f"{PREF}/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS/2026/10_OCTUBRE/{dia}/{nombre}",
            "Name": nombre, "Length": str(largo), "TimeCreated": creado}


def test_extracto_nuevo_y_ya_procesado():
    p = PL.plan("2026-10-08T10:00:00", "NORMAL", [arch()], [], PREF, 10)
    assert [(e["razon"], e["ruta"], e["periodo"]) for e in p["extractos"]] == [("NUEVO", RUTA, "2026-10")]
    assert PL.plan("2026-10-08T10:00:00", "NORMAL", [arch()], [extracto()], PREF, 10)["extractos"] == []


def test_extracto_acumulativo_que_creció_se_reprocesa():
    p = PL.plan("2026-10-08T10:00:00", "NORMAL", [arch(largo=1700)], [extracto()], PREF, 10)
    assert [e["razon"] for e in p["extractos"]] == ["MODIFICADO"]


def test_reintentos_y_error_final():
    p = PL.plan("2026-10-08T10:00:00", "NORMAL", [arch()], [extracto(ESTADO="ERROR", INTENTOS=1)], PREF, 10)
    assert [(e["razon"], e["intentos"]) for e in p["extractos"]] == [("REINTENTO", 1)]
    p = PL.plan("2026-10-08T10:00:00", "NORMAL", [arch()], [extracto(ESTADO="ERROR_FINAL", INTENTOS=3)], PREF, 10)
    assert p["extractos"] == [] and p["error_final"] == 1
    p = PL.plan("2026-10-08T10:00:00", "NORMAL", [arch()], [extracto(ESTADO="ERROR", INTENTOS=3)], PREF, 10)
    assert p["extractos"] == [] and p["error_final"] == 1


def test_grupo_a_reconstruir_reencola_los_extractos_que_lo_alimentaron():
    ctrl = [extracto(), grupo(ESTADO="RECONSTRUIR")]
    assert [e["razon"] for e in PL.plan("2026-10-08T10:00:00", "NORMAL", [arch()], ctrl, PREF, 10)["extractos"]] == ["RECONSTRUIR"]


def test_orden_cronologico_limite_y_archivos_ajenos():
    archivos = [arch("b.xls", creado="2026-10-08T11:00:00Z"), arch("a.xls", creado="2026-10-08T09:00:00Z"),
                arch("~$a.xls"), arch("nota.txt"), arch("c.xlsx", creado="2026-10-08T12:00:00Z")]
    p = PL.plan("2026-10-08T13:00:00", "NORMAL", archivos, [], PREF, 2)
    assert [e["nombre"] for e in p["extractos"]] == ["a.xls", "b.xls"] and p["pendientes"] == 1


def test_la_ruta_de_onedrive_se_obtiene_quitando_el_prefijo_del_servidor():
    assert PL._ruta_onedrive(f"{PREF}/CONTROL_DEPOSITOS/x.xls", PREF) == "/CONTROL_DEPOSITOS/x.xls"


# ---------------------------------------------------------------- verificar
def test_verificar_detecta_perdidas_y_alteraciones():
    ctrl = [grupo()]
    ok = {"grupo_id": GID, "estado_existe": True, "estado_bytes": 100, "xlsx_existe": True, "xlsx_bytes": 200}
    assert PL.verificar(ctrl, [ok]) == {"ok": True, "reconstruir": [], "forzar": [], "correctos": 1}
    r = PL.verificar(ctrl, [dict(ok, estado_existe=False)])
    assert [x["motivo"] for x in r["reconstruir"]] == ["ESTADO_AUSENTE"]
    r = PL.verificar(ctrl, [dict(ok, estado_bytes=99)])
    assert [x["motivo"] for x in r["reconstruir"]] == ["ESTADO_ALTERADO"]
    r = PL.verificar(ctrl, [dict(ok, xlsx_existe=False)])
    assert [x["motivo"] for x in r["forzar"]] == ["XLSX_AUSENTE"] and not r["reconstruir"]
    r = PL.verificar(ctrl, [dict(ok, xlsx_bytes=201)])
    assert [x["motivo"] for x in r["forzar"]] == ["XLSX_ALTERADO"]
    assert PL.verificar([grupo(ESTADO="RECONSTRUIR")], [dict(ok, estado_existe=False)])["reconstruir"] == []   # ya está en cola


# ---------------------------------------------------------------- clasificar
def _lista_con(n=3):
    lst = ListaSimulada()
    claves = [f"BNB|3000100152|{20261000 + i}|X{i}" for i in range(1, n + 1)]
    for i, c in enumerate(claves):
        lst.items[i + 1] = {"Id": i + 1, "CLAVE_TRANSACCION": f"BNB|3000100152|202610{i + 1:02d}|{c}", "BANCO": "BNB",
                            "CUENTA_BANCARIA": "3000100152", "MONEDA": "BOB", "FECHA_MOVIMIENTO": f"2026-10-0{i + 1}T00:00:00Z",
                            "ESTADO_ASIGNACION": "DISPONIBLE", "LOTE_CARGA": "L", "FECHA_CARGA": "2026-10-08T10:00:00",
                            "ARCHIVO_ORIGEN": "a.xls", "Modified": "2026-10-08T14:00:00Z", "__etag": 1}
    return lst


def items(lst):
    return lst.consultar()[0]


def test_clasificar_grupo_sin_cambios_no_se_toca():
    lst = _lista_con()
    gr, _ = __import__("p10.sharepoint", fromlist=["x"]).agrupar(items(lst))
    h = E.hash_lista(gr[GID])
    r = PL.clasificar("2026-10", items(lst), [grupo(HASH_OPERATIVO=h)], "NORMAL", False)
    assert r["ok"] and r["sucios"] == [] and r["sin_estado"] == []


def test_clasificar_detecta_confirmacion_y_reversion():
    lst = _lista_con()
    h0 = E.hash_lista(__import__("p10.sharepoint", fromlist=["x"]).agrupar(items(lst))[0][GID])
    ctrl = [grupo(HASH_OPERATIVO=h0)]
    lst.confirmar(lst.items[2]["CLAVE_TRANSACCION"])
    r = PL.clasificar("2026-10", items(lst), ctrl, "NORMAL", False)
    assert [s["grupo_id"] for s in r["sucios"]] == [GID] and len(r["sucios"][0]["filas"]) == 3
    h1 = r["sucios"][0]["hash_lista"]
    lst.revertir(lst.items[2]["CLAVE_TRANSACCION"])
    r2 = PL.clasificar("2026-10", items(lst), [grupo(HASH_OPERATIVO=h1)], "NORMAL", False)
    assert [s["grupo_id"] for s in r2["sucios"]] == [GID]          # revertir también es un cambio (deja ULTIMA_REVERSION_ID)


def test_clasificar_grupo_sin_estado_espera_a_su_extracto():
    lst = _lista_con()
    assert PL.clasificar("2026-10", items(lst), [], "NORMAL", False)["sin_estado"] == [GID]
    assert PL.clasificar("2026-10", items(lst), [grupo(VERSION_ESTADO=0)], "NORMAL", False)["sin_estado"] == [GID]


def test_clasificar_error_agotado_se_reintenta_solo_en_el_ciclo_completo_o_si_cambia_la_lista():
    lst = _lista_con()
    h = E.hash_lista(__import__("p10.sharepoint", fromlist=["x"]).agrupar(items(lst))[0][GID])
    malo = grupo(ESTADO="ERROR", HASH_INTENTO=h, INTENTOS=3, HASH_OPERATIVO="")
    assert PL.clasificar("2026-10", items(lst), [malo], "NORMAL", False)["en_espera"] == [GID]
    assert [s["grupo_id"] for s in PL.clasificar("2026-10", items(lst), [malo], "COMPLETO", False)["sucios"]] == [GID]
    lst.confirmar(lst.items[1]["CLAVE_TRANSACCION"])
    assert [s["grupo_id"] for s in PL.clasificar("2026-10", items(lst), [malo], "NORMAL", False)["sucios"]] == [GID]


def test_clasificar_forzado_y_grupo_en_reconstruccion():
    lst = _lista_con()
    h = E.hash_lista(__import__("p10.sharepoint", fromlist=["x"]).agrupar(items(lst))[0][GID])
    ctrl = [grupo(HASH_OPERATIVO=h)]
    r = PL.clasificar("2026-10", items(lst), ctrl, "COMPLETO", False, forzar=[{"grupo_id": GID}])
    assert r["sucios"][0]["forzar_xlsx"]
    r = PL.clasificar("2026-10", [], ctrl, "COMPLETO", False, forzar=[{"grupo_id": GID}])
    assert r["sucios"][0]["filas"] is None and r["sucios"][0]["forzar_xlsx"]
    assert PL.clasificar("2026-10", items(lst), [grupo(ESTADO="RECONSTRUIR")], "NORMAL", False)["en_espera"] == [GID]


def test_clasificar_no_confunde_vecinos_de_otro_mes_ni_acepta_consultas_truncadas():
    lst = _lista_con()
    r = PL.clasificar("2026-09", items(lst), [], "NORMAL", False)
    assert r["fuera_de_periodo"] == 3 and r["sucios"] == [] and r["sin_estado"] == []
    r = PL.clasificar("2026-10", items(lst), [], "NORMAL", True)
    assert not r["ok"] and r["codigo_error"] == "MES_EXCEDE_LIMITE"


def test_clasificar_registra_anomalias_sin_detenerse():
    lst = _lista_con()
    malo = dict(items(lst)[0], CLAVE_TRANSACCION="")
    r = PL.clasificar("2026-10", [malo] + items(lst)[1:], [], "NORMAL", False)
    assert r["ok"] and len(r["anomalias"]) == 1
