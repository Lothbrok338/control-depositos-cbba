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
    d = {"Id": 7, "BANCO": gid.split("|")[0], "CLAVE_CONTROL": "GRUPO|" + gid, "TIPO": "GRUPO", "PERIODO": gid.split("|")[3], "ESTADO": "OK",
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
    assert r["hasta_nuevo"] == "2026-10-08T11:00:00" and r["etag"] == '"3"' and r["item_id"] == 1


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
    assert n["modo"] == "NORMAL" and n["meses_listar"] == ["2026-10", "2026-09"]
    assert n["grupos_a_verificar"] == [] and n["slices"] == []
    conc = {"HASH_OPERATIVO": "h"}                                           # grupos ya conciliados con la lista
    c = PL.ciclo("2026-10-08T03:00:00", [lock(), grupo("BNB|1|BOB|2026-02", **conc), grupo(**conc)])
    assert c["meses_listar"][0] == "2026-08" and c["meses_listar"][-1] == "2026-10"       # desde mes_inicio
    assert c["grupos_a_verificar"] == [GID]                                   # jueves: solo la ventana de 3 meses
    d = PL.ciclo("2026-10-11T03:00:00", [lock(), grupo("BNB|1|BOB|2026-02", **conc), grupo(**conc)])    # domingo: todos los meses conocidos
    assert sorted(d["grupos_a_verificar"]) == ["BNB|1|BOB|2026-02", GID]
    assert PL.ciclo("2026-10-08T03:00:00", [lock(), grupo(ESTADO="RECONSTRUIR")])["grupos_a_verificar"] == []
    # la conciliación nocturna cubre BANCO+MES de la ventana; el domingo, todos los meses conocidos
    assert [(x["banco"], x["periodo"]) for x in c["slices"]] == [("BNB", "2026-10")]
    assert sorted((x["banco"], x["periodo"]) for x in d["slices"]) == [("BNB", "2026-02"), ("BNB", "2026-10")]


def test_meses_desplazados_cruzan_el_anio():
    assert PL.mes_desplazado("2026-01", -1) == "2025-12" and PL.mes_desplazado("2026-12", 1) == "2027-01"
    assert PL.meses_entre("2026-11", "2027-02") == ["2026-11", "2026-12", "2027-01", "2027-02"]


def test_cursor_de_lectura_de_la_lista():
    r = PL.ciclo("2026-10-08T10:00:00", [lock(completa="2026-10-08")])
    assert r["cursor_desde"] == "2026-10-08T13:00:00Z"                           # sin cursor: la última hora (hora UTC)
    con = lock(completa="2026-10-08")
    con["CURSOR_LISTA"] = "2026-10-08T13:55:00Z"
    assert PL.ciclo("2026-10-08T10:00:00", [con])["cursor_desde"] == "2026-10-08T13:55:00Z"


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


# ---------------------------------------------------------------- meses con trabajo pendiente
def test_grupos_con_error_o_en_reconstruccion_se_concilian_aunque_la_lista_no_cambie():
    n = lambda *g: [(x["banco"], x["periodo"]) for x in PL.ciclo(
        "2026-10-08T10:00:00", [lock(completa="2026-10-08"), *g])["slices"]]   # noqa: E731
    assert n(grupo(HASH_OPERATIVO="h")) == []                               # conciliado y sin error: nada pendiente
    assert n(grupo(ESTADO="ERROR", INTENTOS=1)) == [("BNB", "2026-10")]
    assert n(grupo(ESTADO="ERROR", INTENTOS=3)) == []                      # agotado: espera al ciclo completo
    assert n(grupo(ESTADO="RECONSTRUIR")) == [("BNB", "2026-10")]
    assert n(grupo("BNB|1|BOB|2026-02", ESTADO="RECONSTRUIR"), grupo("BCP|2|BOB|2026-10", ESTADO="ERROR")) == [
        ("BCP", "2026-10"), ("BNB", "2026-02")]


def test_clave_de_extracto_larga_se_reemplaza_por_su_huella():
    corta = PL.clave_extracto("/a/b.xls")
    assert corta == "EXTRACTO|/a/b.xls"
    larga = PL.clave_extracto("/x/" + "n" * 300 + ".xls")
    assert len(larga) < 255 and larga.startswith("EXTRACTO|#") and larga == PL.clave_extracto("/x/" + "n" * 300 + ".xls")


# ---------------------------------------------------------------- reconstrucción
def _marcado(desde="2026-10-08T10:00:00"):
    return grupo(ESTADO="RECONSTRUIR", VERSION_ESTADO=0, RECONSTRUIR_DESDE=desde)


def test_reconstruir_exige_reincorporar_todos_los_extractos_aunque_superen_el_limite():
    rutas = [RUTA.replace("a.xls", f"e{i}.xls") for i in range(4)]
    ctrl = [_marcado(), *[extracto(r, ULTIMA_SYNC="2026-10-07T09:00:00", Id=20 + i) for i, r in enumerate(rutas)]]
    archivos = [arch(f"e{i}.xls", creado=f"2026-10-0{i + 1}T09:00:00Z") for i in range(4)]
    p = PL.plan("2026-10-08T12:00:00", "NORMAL", archivos, ctrl, PREF, 1)
    assert [e["razon"] for e in p["extractos"]] == ["RECONSTRUIR"] * 4 and p["pendientes"] == 0
    assert p["extractos"][0]["item_id"] == 20
    ctrl[1]["ULTIMA_SYNC"] = "2026-10-08T12:05:00"                          # ya reincorporado después de la marca
    p = PL.plan("2026-10-08T12:10:00", "NORMAL", archivos, ctrl, PREF, 1)
    assert [e["nombre"] for e in p["extractos"]] == ["e1.xls", "e2.xls", "e3.xls"]


def test_la_marca_reconstruir_solo_se_quita_cuando_no_quedan_extractos_pendientes():
    lst = _lista_con()
    marca = _marcado()
    pend = extracto(ULTIMA_SYNC="2026-10-07T09:00:00")
    r = PL.clasificar("2026-10", items(lst), [marca, pend], "NORMAL", False)
    assert r["en_espera"] == [GID] and r["sucios"] == []
    hecho = extracto(ULTIMA_SYNC="2026-10-08T10:30:00")
    r = PL.clasificar("2026-10", items(lst), [marca, hecho], "NORMAL", False)
    assert [(s["grupo_id"], s["finalizar"]) for s in r["sucios"]] == [(GID, True)]


def test_grupo_en_reconstruccion_sin_filas_en_la_lista_tambien_se_finaliza():
    r = PL.clasificar("2026-10", [], [_marcado(), extracto(ULTIMA_SYNC="2026-10-08T10:30:00")], "NORMAL", False)
    assert [(s["grupo_id"], s["filas"], s["finalizar"]) for s in r["sucios"]] == [(GID, None, True)]


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


def test_clasificar_verificacion_completa():
    lst = _lista_con()
    h = E.hash_lista(__import__("p10.sharepoint", fromlist=["x"]).agrupar(items(lst))[0][GID])
    ctrl = [grupo(HASH_OPERATIVO=h)]
    r = PL.clasificar("2026-10", items(lst), ctrl, "COMPLETO", False, verificar=[GID])
    assert r["sucios"][0]["verificar_xlsx"] and not r["sucios"][0]["finalizar"]
    r = PL.clasificar("2026-10", [], ctrl, "COMPLETO", False, verificar=[GID])
    assert r["sucios"][0]["filas"] is None and r["sucios"][0]["verificar_xlsx"]
    assert PL.clasificar("2026-10", [], ctrl, "NORMAL", False)["sucios"] == []


def test_clasificar_no_confunde_vecinos_de_otro_mes_ni_acepta_consultas_truncadas():
    lst = _lista_con()
    r = PL.clasificar("2026-09", items(lst), [], "NORMAL", False)
    assert r["fuera_de_periodo"] == 3 and r["sucios"] == [] and r["sin_estado"] == []
    r = PL.clasificar("2026-10", items(lst), [], "NORMAL", True)
    assert not r["ok"] and r["codigo_error"] == "REBANADA_EXCEDE_LIMITE"


def test_clasificar_registra_anomalias_sin_detenerse():
    lst = _lista_con()
    malo = dict(items(lst)[0], CLAVE_TRANSACCION="")
    r = PL.clasificar("2026-10", [malo] + items(lst)[1:], [], "NORMAL", False)
    assert r["ok"] and len(r["anomalias"]) == 1


def test_grupo_con_error_se_reintenta_aunque_la_lista_no_haya_cambiado():
    lst = _lista_con()
    h = E.hash_lista(__import__("p10.sharepoint", fromlist=["x"]).agrupar(items(lst))[0][GID])
    r = PL.clasificar("2026-10", items(lst), [grupo(ESTADO="ERROR", HASH_OPERATIVO=h, INTENTOS=1)], "NORMAL", False)
    assert [s["grupo_id"] for s in r["sucios"]] == [GID]


def test_clasificar_por_banco_ignora_los_grupos_de_otros_bancos():
    lst = _lista_con()
    otro = grupo("BCP|9|BOB|2026-10", ESTADO="RECONSTRUIR", RECONSTRUIR_DESDE="2026-10-08T09:00:00")
    r = PL.clasificar("2026-10", items(lst), [otro], "NORMAL", False, banco="BNB")
    assert r["sucios"] == [] and r["en_espera"] == [] and r["sin_estado"] == [GID]
    r = PL.clasificar("2026-10", [], [otro], "NORMAL", False, banco="BCP")
    assert [(s["grupo_id"], s["finalizar"]) for s in r["sucios"]] == [("BCP|9|BOB|2026-10", True)]


# ---------------------------------------------------------------- lectura incremental (delta)
def _con_modificado(lst, hora="2026-10-08T14:00:00Z"):
    return [dict(i, Modified=hora) for i in items(lst)]


def test_delta_entrega_las_filas_cambiadas_de_cada_grupo_con_estado_y_avanza_el_cursor():
    lst = _lista_con(3)
    fila = _con_modificado(lst, "2026-10-08T13:00:00Z")[:2]
    r = PL.delta(fila, [grupo()], "2026-10-08T10:00:00")
    assert r["ok"] and [s["grupo_id"] for s in r["sucios"]] == [GID] and len(r["sucios"][0]["filas"]) == 2
    assert r["sucios"][0]["parcial_lista"] is True and r["sin_estado"] == []
    assert r["cursor_nuevo"] == "2026-10-08T13:00:00Z"


def test_delta_no_avanza_el_cursor_sobre_filas_recientes_pero_si_sobre_grupos_sin_estado():
    lst = _lista_con(3)
    reciente = _con_modificado(lst, "2026-10-08T13:58:00Z")          # 2 min antes de las 10:00 locales (14:00Z): aún no asienta
    r = PL.delta(reciente, [grupo()], "2026-10-08T10:00:00")
    assert r["cursor_nuevo"] == "" and len(r["sucios"]) == 1
    viejas = _con_modificado(lst, "2026-10-08T12:00:00Z")
    r = PL.delta(viejas, [], "2026-10-08T10:00:00")                  # el grupo aún no tiene estado: su extracto no llegó
    assert r["sin_estado"] == [GID] and r["sucios"] == [] and r["cursor_nuevo"] == "2026-10-08T12:00:00Z"   # NO retiene el cursor (lo concilia su BANCO+MES)
    mezcla = _con_modificado(lst, "2026-10-08T12:00:00Z")[:1] + _con_modificado(lst, "2026-10-08T13:00:00Z")[1:]
    r = PL.delta(mezcla, [grupo(VERSION_ESTADO=0)], "2026-10-08T10:00:00")
    assert r["cursor_nuevo"] == "2026-10-08T13:00:00Z"
    r = PL.delta(viejas, [], "2026-10-08T10:00:00", cursor_desde="2026-10-08T12:30:00Z")
    assert r["cursor_nuevo"] == ""                                   # el cursor nunca retrocede


def test_delta_con_la_pagina_llena_relee_la_ultima_hora_y_siempre_avanza():
    """Prueba real: un lote grande de filas sin estado dejaba el cursor pegado y las filas nuevas (la confirmación) fuera de la página."""
    lst = _lista_con(3)
    modelo = lst.consultar()[0][0]
    pagina = []
    for i in range(PL.MAX_ELEMENTOS_DELTA):
        f = dict(modelo, CLAVE_TRANSACCION=f"BNB|3000100152|20261001|{i:05d}|X", Modified=f"2026-10-08T12:{i // 60:02d}:{i % 60:02d}Z")
        pagina.append(f)
    r = PL.delta(pagina, [], "2026-10-08T10:00:00")
    ultimo = pagina[-1]["Modified"]
    assert r["cursor_nuevo"] < ultimo and r["cursor_nuevo"] == pagina[-2]["Modified"]       # la última hora se lee de nuevo
    iguales = [dict(f, Modified="2026-10-08T12:00:00Z") for f in pagina]
    r = PL.delta(iguales, [], "2026-10-08T10:00:00")
    assert r["cursor_nuevo"] == "" and any(a.startswith("PAGINA_LLENA_SIN_AVANCE") for a in r["anomalias"])


def test_delta_una_fila_malformada_no_tumba_la_pagina():
    lst = _lista_con(2)
    mala = dict(_con_modificado(lst, "2026-10-08T12:00:00Z")[0], FECHA_HORA_ASIGNACION="no es una fecha")
    buena = _con_modificado(lst, "2026-10-08T12:01:00Z")[1]
    r = PL.delta([mala, buena], [grupo()], "2026-10-08T10:00:00")
    assert r["ok"] and len(r["sucios"][0]["filas"]) == 1 and len(r["anomalias"]) == 1


def test_delta_deja_los_grupos_en_reconstruccion_a_la_conciliacion_completa():
    lst = _lista_con(2)
    r = PL.delta(_con_modificado(lst), [grupo(ESTADO="RECONSTRUIR", VERSION_ESTADO=0)], "2026-10-08T12:00:00")
    assert r["sucios"] == [] and r["en_espera"] == [GID]


def test_delta_sin_cambios_no_hace_nada():
    r = PL.delta([], [grupo()], "2026-10-08T10:00:00")
    assert r == {"ok": True, "elementos": 0, "sucios": [], "sin_estado": [], "en_espera": [], "cursor_nuevo": "", "anomalias": []}


def test_un_grupo_creado_por_extracto_y_nunca_conciliado_con_la_lista_se_concilia_solo():
    """Prueba real: los grupos quedaron sin la foto operativa porque la conciliación posterior al extracto no corrió."""
    r = PL.ciclo("2026-10-08T10:00:00", [lock(completa="2026-10-08"), grupo()])
    assert r["modo"] == "NORMAL" and r["slices"] == [{"periodo": "2026-10", "banco": "BNB"}]
    r = PL.ciclo("2026-10-08T10:00:00", [lock(completa="2026-10-08"), grupo(HASH_OPERATIVO="abc")])
    assert r["slices"] == []
    r = PL.ciclo("2026-10-08T10:00:00", [lock(completa="2026-10-08"), grupo(ESTADO="ERROR", INTENTOS=3)])
    assert r["slices"] == []                                                 # con error agotado se espera revisión, no se insiste


def test_un_grupo_nunca_conciliado_sin_filas_en_la_lista_queda_conciliado_con_la_lista_vacia():
    r = PL.clasificar("2026-10", [], [grupo()], "NORMAL", False)
    assert [(s["grupo_id"], s["filas"], s["hash_lista"]) for s in r["sucios"]] == [(GID, [], E.hash_lista([]))]
    r = PL.clasificar("2026-10", [], [grupo(HASH_OPERATIVO=E.hash_lista([]))], "NORMAL", False)
    assert r["sucios"] == []                                                 # ya constatado: no se repite en cada ciclo
