"""Ejecuta WDL real generado: solicitud, unicidad e idempotencia entre hilos."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from reversion_helpers import (D, R, UID, UID2, T0, LIMITE, assert_cerrada, diagnostico,
                               entradas, ejecutar, escrituras_deposito, fila, servidor, solicitar)
from p9.reversion import contrato as C

pytestmark = pytest.mark.p9


def test_consulta_es_solo_lectura_y_devuelve_etag_snapshot():
    sp = servidor()
    run = ejecutar("solicitar", sp, entradas(sp, operacion="CONSULTAR", motivo="", uid=""))
    assert run.respuesta["resultado"] == "LISTO", diagnostico(run)
    snap = json.loads(run.respuesta["snapshot_json"])
    assert snap["ID"] == 17 and snap["OBSERVACION"] == sp.fila(D, 17)["OBSERVACION"]
    assert run.respuesta["etag"] == sp.etag(D, 17)
    assert not sp.listas[R]["items"] and not escrituras_deposito(sp)


def test_creacion_snapshot_completo_identidad_y_plazo_fijo():
    sp, run, data = solicitar()
    row = fila(sp)
    assert run.respuesta["resultado"] == "ENVIADA"
    solicitud = datetime.fromisoformat(row["FECHA_SOLICITUD"].replace("Z", "+00:00"))
    limite = datetime.fromisoformat(row["FECHA_LIMITE"].replace("Z", "+00:00"))
    assert solicitud == datetime.fromisoformat(T0.replace("Z", "+00:00"))
    assert limite == datetime.fromisoformat(LIMITE.replace("Z", "+00:00"))
    assert limite - solicitud == timedelta(hours=168)
    assert row["SOLICITANTE_ID"] == "operador-1"
    assert row["SOLICITANTE_UPN"] == "operador@univalle.edu"
    assert row["ETAG_SOLICITUD"] == data["text_2"]
    assert row["CLAVE_BLOQUEO"] == C.clave_activa(sp.listas[D]["id"], 17)
    snap = json.loads(row["SNAPSHOT_JSON"])
    assert all(snap[k] == sp.fila(D, 17)[k] for k in C.CAMPOS_SNAPSHOT)
    assert not escrituras_deposito(sp) and not run.approvals_creadas


@pytest.mark.parametrize("patch", [{"text_3": ""}, {"text_3": "   "}, {"text_3": "x"*4001},
    {"text_4": "invalid"}, {"text_4": "00000000-0000-0000-0000-000000000000"},
    {"text_2": ""}, {"number": 0}, {"number": 17.1}, {"text_1": ""}])
def test_entrada_invalida_no_crea_solicitud(patch):
    sp = servidor()
    run = ejecutar("solicitar", sp, entradas(sp, **patch))
    assert run.respuesta["resultado"] == "ERROR", diagnostico(run)
    assert not sp.listas[R]["items"] and not escrituras_deposito(sp)


@pytest.mark.parametrize("changes,patch,codigo", [
    ({"ESTADO_ASIGNACION": "DISPONIBLE"}, {}, "YA_NO_ASIGNADO"),
    ({}, {"text_1": "otra"}, "CLAVE_NO_COINCIDE"),
    ({}, {"number": 99}, "DEPOSITO_NO_ENCONTRADO"),
    ({}, {"text_2": '"99"'}, "CONFLICTO")])
def test_prevalidacion_autoritativa(changes, patch, codigo):
    sp = servidor(**changes)
    run = ejecutar("solicitar", sp, entradas(sp, **patch))
    assert run.respuesta["codigo"] == codigo, diagnostico(run)
    assert not sp.listas[R]["items"] and not escrituras_deposito(sp)


@pytest.mark.parametrize("http", [403,429,500,503,504])
def test_lectura_fallida_no_se_inventa_deposito_inexistente(http):
    sp = servidor()
    sp.fallos["LEER_DEPOSITO"] = (http, False)
    run = ejecutar("solicitar", sp, entradas(sp))
    assert run.respuesta["resultado"] == "ERROR", diagnostico(run)
    assert run.respuesta["codigo"] != "DEPOSITO_NO_ENCONTRADO"
    assert not sp.listas[R]["items"]


def test_sin_etag_falla_cerrado():
    sp = servidor()
    sp.sin_etag = True
    run = ejecutar("solicitar", sp, entradas(sp))
    assert run.respuesta["codigo"] == "SIN_ETAG", diagnostico(run)
    assert not sp.listas[R]["items"]


def test_reintento_mismo_uid_no_relee_version_ni_extiende_plazo():
    sp, first, data = solicitar()
    original = copy.deepcopy(fila(sp))
    sp.editar(D, 17, ESTUDIANTE="Cambio posterior")
    run = ejecutar("solicitar", sp, data, ahora="2026-10-04T12:00:00Z")
    assert run.respuesta["resultado"] == "EXISTENTE", diagnostico(run)
    assert run.respuesta["solicitud_id"] == first.respuesta["solicitud_id"]
    assert fila(sp) == original
    assert "LEER_DEPOSITO" not in run.eventos


@pytest.mark.parametrize("patch,usuario", [({"text_3":"otro motivo"},None),
    ({"text_2":'"9"'},None), ({"text_1":"OTRA"},None), ({"number":18},None),
    ({}, {"id":"intruso", "userPrincipalName":"operador@univalle.edu"})])
def test_uid_reutilizado_rechaza_payload_o_identidad_distintos(patch, usuario):
    sp, _, data = solicitar()
    run = ejecutar("solicitar", sp, {**data, **patch}, usuario=usuario)
    assert run.respuesta["codigo"] == "UID_REUTILIZADO", diagnostico(run)
    assert len(sp.listas[R]["items"]) == 1


def test_correo_libre_no_suplanta_conexion_autenticada():
    sp = servidor()
    run = ejecutar("solicitar", sp, entradas(sp, email="intruso@example.com", solicitante="otro"))
    assert run.respuesta["resultado"] == "ENVIADA", diagnostico(run)
    assert fila(sp)["SOLICITANTE_UPN"] == "operador@univalle.edu"


@pytest.mark.parametrize("same_uid", [False, True])
def test_dos_solicitudes_simultaneas_reserva_unica_atomica(same_uid):
    sp = servidor()
    barrier = threading.Barrier(2)
    sp.antes["CREAR_SOLICITUD"] = lambda *_: barrier.wait(timeout=10)
    values = [entradas(sp,uid=UID), entradas(sp,uid=UID if same_uid else UID2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda data: ejecutar("solicitar",sp,data), values))
    assert len(sp.listas[R]["items"]) == 1
    assert sorted(r.respuesta["resultado"] for r in runs) == ["ENVIADA", "EXISTENTE" if same_uid else "PENDIENTE_EXISTENTE"], [diagnostico(r) for r in runs]
    assert len({r.respuesta["solicitud_id"] for r in runs}) == 1
    assert not escrituras_deposito(sp)


def test_creacion_respuesta_perdida_reconcilia_por_uid():
    sp = servidor()
    sp.fallos["CREAR_SOLICITUD"] = (504, True)
    run = ejecutar("solicitar", sp, entradas(sp))
    assert run.respuesta["resultado"] == "EXISTENTE", diagnostico(run)
    assert len(sp.listas[R]["items"]) == 1


def test_colision_solo_clasifica_duplicado_con_evidencia():
    sp = servidor()
    sp.fallos["CREAR_SOLICITUD"] = (403, False)
    run = ejecutar("solicitar", sp, entradas(sp))
    assert run.respuesta["codigo"] == "CREACION_NO_CONFIRMADA", diagnostico(run)
    assert not sp.listas[R]["items"]


def test_aprobacion_inmediata_reversion_atomica_nueve_campos():
    sp, _, _ = solicitar()
    before = copy.deepcopy(sp.fila(D, 17))
    snapshot = fila(sp)["SNAPSHOT_JSON"]
    run = ejecutar("resolver",sp,fila(sp))
    assert_cerrada(fila(sp), "REVERTIDO")
    merges = escrituras_deposito(sp)
    assert len(merges) == 1, diagnostico(run)
    body = merges[0][1]["parameters/body"]
    assert isinstance(body, str)
    payload = json.loads(body)
    assert payload == C.payload_reversion(UID)
    assert merges[0][1]["parameters/headers"]["IF-MATCH"] == '"1"'
    after = sp.fila(D,17)
    assert all(after[k] == before[k] for k in C.CAMPOS_MOTOR)
    assert all(after[k] is None for k in C.CAMPOS_LIMPIAR)
    assert fila(sp)["SNAPSHOT_JSON"] == snapshot
    assert len(run.approvals_creadas) == 1
    assert fila(sp)["APROBADOR_UPN"] == "gtorricot@univalle.edu"
    limite = json.loads(fila(sp)["CONFIG_APROBACION_JSON"])["fecha_limite"]
    assert datetime.fromisoformat(limite.replace("Z", "+00:00")) == datetime.fromisoformat(LIMITE.replace("Z", "+00:00"))


def test_rechazo_cierra_sin_version_nueva_del_deposito():
    sp, _, _ = solicitar()
    answer = {"outcome":"Reject", "name":"approval-local", "responses":[{
        "responder":{"id":"aprobador-1", "userPrincipalName":"gtorricot@univalle.edu"},
        "responseDate":T0, "approverResponse":"Reject", "comments":"No corresponde"}]}
    run = ejecutar("resolver",sp,fila(sp),aprobacion=answer)
    assert_cerrada(fila(sp),"NO_EJECUTADO","RECHAZADO")
    assert not escrituras_deposito(sp) and sp.etag(D,17) == '"1"'
    assert fila(sp)["COMENTARIO_APROBADOR"] == "No corresponde", diagnostico(run)


@pytest.mark.parametrize("changes", [{"ESTUDIANTE":"Otra persona"}, {"OBSERVACION":"Cambio inocuo"},
                                      {"CLAVE_TRANSACCION":"Otra clave"}, {"ESTADO_ASIGNACION":"DISPONIBLE"}])
def test_etag_distinto_tiene_prioridad_sobre_estado_o_clave(changes):
    sp, _, _ = solicitar()
    run = ejecutar("resolver",sp,fila(sp),hook=lambda _:sp.editar(D,17,**changes))
    assert_cerrada(fila(sp),"CONFLICTO")
    assert not escrituras_deposito(sp), diagnostico(run)
    log=json.loads(fila(sp)["BITACORA_TECNICA_JSON"])
    evidence=next(e["evidencia"] for e in log if e["etapa"]=="RES_E_CERRAR_NO_APTO")
    assert evidence["etag_actual"]=='"2"'
    assert evidence["clave_actual"]==sp.fila(D,17)["CLAVE_TRANSACCION"]
    assert evidence["estado_actual"]==sp.fila(D,17)["ESTADO_ASIGNACION"]


def test_cambio_y_restauracion_de_valores_sigue_siendo_conflicto():
    sp, _, _ = solicitar()
    original = sp.fila(D,17)["ESTUDIANTE"]
    def hook(_):
        sp.editar(D,17,ESTUDIANTE="Cambio temporal")
        sp.editar(D,17,ESTUDIANTE=original)
    ejecutar("resolver",sp,fila(sp),hook=hook)
    assert_cerrada(fila(sp),"CONFLICTO")
    assert not escrituras_deposito(sp)


@pytest.mark.parametrize("changes,result", [({"CLAVE_TRANSACCION":"otra"},"CLAVE_NO_COINCIDE"),
                                          ({"ESTADO_ASIGNACION":"DISPONIBLE"},"YA_NO_ASIGNADO")])
def test_defensa_adicional_si_respuesta_inconsistente_misma_version(changes,result):
    sp, _, _ = solicitar()
    # Simula respuesta inconsistente de conector; una edición real sí cambia ETag.
    def hook(_):
        sp.listas[D]["items"][17].update(changes)
    ejecutar("resolver",sp,fila(sp),hook=hook)
    assert_cerrada(fila(sp),result)
    assert not escrituras_deposito(sp)


def test_deposito_eliminado_tras_solicitud_es404_real():
    sp, _, _ = solicitar()
    ejecutar("resolver",sp,fila(sp),hook=lambda _:sp.listas[D]["items"].pop(17))
    assert_cerrada(fila(sp),"DEPOSITO_NO_ENCONTRADO")
    assert not escrituras_deposito(sp)


def test_cambio_entre_get_y_merge_produce412_sin_sobrescribir():
    sp, _, _ = solicitar()
    sp.antes["RES_E_MERGE_DEPOSITO"] = lambda *_:sp.editar(D,17,ESTUDIANTE="Confirmación competidora")
    run = ejecutar("resolver",sp,fila(sp))
    assert_cerrada(fila(sp),"CONFLICTO")
    assert sp.fila(D,17)["ESTUDIANTE"] == "Confirmación competidora", diagnostico(run)
    assert sp.fila(D,17)["ULTIMA_REVERSION_ID"] is None
    assert len(escrituras_deposito(sp)) == 1


def test_dos_triggers_solo_ganador_crea_approval_y_limpia():
    sp, _, _ = solicitar()
    request = fila(sp)
    barrier = threading.Barrier(2)
    seen = set()
    lock = threading.Lock()
    def race(*_):
        tid = threading.get_ident()
        with lock:
            first = tid not in seen
            seen.add(tid)
        if first:
            barrier.wait(timeout=10)
    sp.antes["RECLAMAR_MERGE"] = race
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _:ejecutar("resolver",sp,request),range(2)))
    assert sum(len(r.approvals_creadas) for r in runs) == 1, [diagnostico(r) for r in runs]
    assert len(escrituras_deposito(sp)) == 1
    assert_cerrada(fila(sp),"REVERTIDO")


def test_nueva_reversion_legitima_despues_de_reconfirmar():
    sp, _, _ = solicitar()
    ejecutar("resolver",sp,fila(sp))
    sp.editar(D,17,ESTADO_ASIGNACION="ASIGNADO", ESTUDIANTE="Nueva confirmación")
    _, run, _ = solicitar(sp,uid=UID2)
    assert run.respuesta["resultado"] == "ENVIADA"
    assert len(sp.listas[R]["items"]) == 2
    assert fila(sp,UID2)["CLAVE_BLOQUEO"].startswith("ACTIVA|")
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("CERRADA|")


def test_snapshot_excede_capacidad_se_rechaza_sin_truncar():
    sp=servidor(OBSERVACION="á"*60000)
    run=ejecutar("solicitar",sp,entradas(sp))
    assert run.respuesta["codigo"]=="SNAPSHOT_EXCEDE_CAPACIDAD",diagnostico(run)
    assert not sp.listas[R]["items"] and not escrituras_deposito(sp)
    assert sp.fila(D,17)["OBSERVACION"]=="á"*60000


def test_auditoria_intento_no_persistida_impide_merge_deposito():
    sp,_,_=solicitar()
    sp.fallos["RES_E_INTENTO_MERGE"]=(403,False)
    run=ejecutar("resolver",sp,fila(sp))
    assert fila(sp)["ESTADO_SOLICITUD"]=="APROBADO",diagnostico(run)
    assert not escrituras_deposito(sp)
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")


# --- CONSULTAR con solicitud activa: contrato que consume la UX "REVERSIÓN PENDIENTE" ---

def consultar(sp, ahora=T0):
    return ejecutar("solicitar", sp, entradas(sp, operacion="CONSULTAR", motivo="", uid=""), ahora=ahora)


def sin_escrituras_tras(sp, desde):
    return [p["parameters/uri"] for _, p in sp.llamadas[desde:] if p["parameters/method"] != "GET"]


@pytest.mark.parametrize("fase,decision,tecnico", [
    ("RECIBIDA", "PENDIENTE", ""),
    ("ESPERANDO_APROBACION", "PENDIENTE", ""),
    ("EJECUTANDO_REVERSION", "APROBADO", ""),
    ("RECUPERACION_REQUERIDA", "APROBADO", "ERROR")])
def test_consultar_con_solicitud_activa_devuelve_estado_real_sin_escribir(fase, decision, tecnico):
    sp, _, data = solicitar()
    ident = fila(sp)["ID"]
    cambios = {"FASE_PROCESO": fase, "ESTADO_SOLICITUD": decision}
    if tecnico:
        cambios["RESULTADO_TECNICO"] = tecnico
    sp.editar(R, ident, **cambios)
    solicitudes, depositos, desde = copy.deepcopy(sp.listas[R]["items"]), copy.deepcopy(sp.listas[D]["items"]), len(sp.llamadas)
    run = consultar(sp)
    r = run.respuesta
    assert (r["resultado"], r["codigo"]) == ("PENDIENTE_EXISTENTE", "PENDIENTE_EXISTENTE"), diagnostico(run)
    assert r["solicitud_id"] == str(ident) and r["solicitud_uid"] == UID
    assert (r["estado_solicitud"], r["fase_proceso"], r["resultado_tecnico"]) == (decision, fase, tecnico)
    assert datetime.fromisoformat(r["fecha_limite"].replace("Z", "+00:00")) == datetime.fromisoformat(LIMITE.replace("Z", "+00:00"))
    assert json.loads(r["snapshot_json"])["ID"] == 17
    assert r["etag"] == data["text_2"]
    assert r["mensaje"] == "Ya existe una solicitud activa para el depósito."
    assert sin_escrituras_tras(sp, desde) == []
    assert sp.listas[R]["items"] == solicitudes and sp.listas[D]["items"] == depositos


def test_consultar_activa_no_depende_del_etag_actual_del_deposito():
    sp, _, data = solicitar()
    sp.editar(D, 17, OBSERVACION="editada mientras la solicitud espera")
    assert sp.etag(D, 17) != data["text_2"]
    run = consultar(sp)
    assert run.respuesta["resultado"] == "PENDIENTE_EXISTENTE", diagnostico(run)
    assert run.respuesta["etag"] == data["text_2"]


@pytest.mark.parametrize("ahora,mensaje", [
    ("2026-10-10T11:59:59Z", "Ya existe una solicitud activa para el depósito."),
    (LIMITE, "VENCIDA — CIERRE PENDIENTE")])
def test_consultar_activa_vencida_sin_cerrar_conserva_bloqueo_y_lo_informa(ahora, mensaje):
    sp, _, _ = solicitar()
    run = consultar(sp, ahora)
    assert run.respuesta["resultado"] == "PENDIENTE_EXISTENTE", diagnostico(run)
    assert run.respuesta["mensaje"] == mensaje
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")


def test_consultar_tras_cierre_vuelve_a_listo_sin_campos_de_solicitud():
    sp, _, _ = solicitar()
    row = fila(sp)
    sp.editar(R, row["ID"], FASE_PROCESO="FINALIZADA", RESULTADO_TECNICO="REVERTIDO",
              CLAVE_BLOQUEO="CERRADA|" + row["SOLICITUD_UID"])
    r = consultar(sp).respuesta
    assert (r["resultado"], r["codigo"]) == ("LISTO", "LISTO")
    for campo in ("solicitud_id", "solicitud_uid", "estado_solicitud", "fase_proceso", "resultado_tecnico", "fecha_limite"):
        assert r[campo] == "", campo
    assert json.loads(r["snapshot_json"])["ID"] == 17 and r["etag"] == sp.etag(D, 17)
