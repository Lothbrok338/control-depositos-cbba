"""Carreras y fallos parciales sobre los JSON WDL generados, sin tenant ni red."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from p8.ensayo_wdl import FalloConector
from reversion_helpers import (D, R, UID, UID2, T0, LIMITE, OPERADOR, assert_cerrada,
    diagnostico, entradas, ejecutar, escrituras_deposito, eventos, fila, servidor, solicitar)

pytestmark = pytest.mark.p9


def evidencia(row, **changes):
    proof = {"run_id":row.get("RUN_ID"), "estado_run":"Failed",
        "url_ejecucion":"https://make.powerautomate.com/environments/ensayo/flows/ensayo/runs/" + str(row.get("RUN_ID")),
        "fecha_fin_run":T0, "fecha_verificacion":T0, "verificado_por_id":OPERADOR["id"],
        "motivo_recuperacion":"Verificación manual en historial de ejecución",
        "evidencia_operaciones":"Acción crítica y respuesta examinadas en el portal",
        "merge_estado":"INCIERTO", "approval_estado":"CREADA_IDENTIFICADA",
        "aprobacion_id":row.get("APROBACION_ID") or "approval-local-1", "solicitud_uid":row["SOLICITUD_UID"]}
    proof.update(changes)
    return proof


def recuperar(sp, *, uid=UID, modo="RECONCILIAR", proof=None, **kwargs):
    row = fila(sp, uid)
    return ejecutar("recuperar", sp, {"text":uid, "text_1":modo,
                     "text_2":json.dumps(proof if proof is not None else evidencia(row))}, **kwargs)


def incertidumbre(*, persistir=True, http=504):
    sp, _, _ = solicitar()
    sp.fallos["RES_E_MERGE_DEPOSITO"] = (http,persistir)
    run = ejecutar("resolver",sp,fila(sp),run_id="dueño-original")
    assert fila(sp)["FASE_PROCESO"] == "RECUPERACION_REQUERIDA", diagnostico(run)
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")
    return sp, run


@pytest.mark.parametrize("cuando,expira", [("2026-10-10T11:59:59Z",False),(LIMITE,True),("2026-10-10T12:00:01Z",True)])
def test_expiracion_justo_antes_en_y_despues_del_limite(cuando,expira):
    sp, _, _ = solicitar()
    run = ejecutar("expirar",sp,ahora=cuando)
    assert run.estado_final == "Succeeded", diagnostico(run)
    if expira:
        assert_cerrada(fila(sp),"NO_EJECUTADO","PENDIENTE","EXPIRADA")
        assert fila(sp)["APROBADOR_UPN"] is None
    else:
        assert fila(sp)["FASE_PROCESO"] == "RECIBIDA"
    assert not escrituras_deposito(sp) and sp.etag(D,17) == '"1"'


def test_trigger_nunca_arranca_expira_y_libera_futura_solicitud():
    sp, _, _ = solicitar()
    ejecutar("expirar",sp,ahora=LIMITE)
    _, run, _ = solicitar(sp,uid=UID2)
    assert run.respuesta["resultado"] == "ENVIADA"
    assert fila(sp,UID2)["CLAVE_BLOQUEO"].startswith("ACTIVA|")


def test_expirador_recorrre_todas_paginas_y_reinicia_variables_por_fila():
    sp, _, _ = solicitar()
    template = fila(sp)
    for i in range(2,8):
        row = {k:v for k,v in template.items() if k not in ("__metadata","@odata.etag")}
        row.update(ID=i, Id=i, SOLICITUD_UID=f"d94fcfa4-5cf2-4a3e-b6e4-{i:012}",
                   DEPOSITO_ID=17+i, CLAVE_BLOQUEO=f"ACTIVA|{sp.listas[D]['id']}|{17+i}")
        sp.agregar(R,row)
    sp.page_size=2
    run=ejecutar("expirar",sp,ahora=LIMITE)
    assert run.estado_final=="Succeeded",diagnostico(run)
    assert len([name for name,_ in sp.llamadas if name=="EXP_LEER_PAGINA"]) == 4
    for row in sp.listas[R]["items"].values():
        assert_cerrada(row,"NO_EJECUTADO","PENDIENTE","EXPIRADA")


def test_aprobacion_justo_antes_limite_gana_y_no_expira_ejecucion():
    sp, _, _ = solicitar()
    def before_merge(*_):
        ejecutar("expirar",sp,ahora=LIMITE)
        assert fila(sp)["ESTADO_SOLICITUD"] == "APROBADO"
    sp.antes["RES_E_MERGE_DEPOSITO"]=before_merge
    run=ejecutar("resolver",sp,fila(sp),ahora="2026-10-10T11:59:59Z")
    assert_cerrada(fila(sp),"REVERTIDO")
    assert len(escrituras_deposito(sp))==1,diagnostico(run)


@pytest.mark.parametrize("cuando",[LIMITE,"2026-10-10T12:00:01Z"])
def test_respuesta_en_limite_o_tardia_no_reabre(cuando):
    sp, _, _ = solicitar()
    def after(run):
        ejecutar("expirar",sp,ahora=cuando)
        run.ahora=cuando
    run=ejecutar("resolver",sp,fila(sp),hook=after)
    assert_cerrada(fila(sp),"NO_EJECUTADO","PENDIENTE","EXPIRADA")
    assert not escrituras_deposito(sp),diagnostico(run)
    assert any(e["accion"]=="RESPUESTA_DESCARTADA" for e in eventos(fila(sp)))


def test_expirador_gana_cas_con_decision_ya_leida():
    sp, _, _=solicitar()
    fired=[]
    def race(*_):
        if not fired:
            fired.append(True)
            ejecutar("expirar",sp,ahora=LIMITE)
    sp.antes["RES_R_ACEPTAR_APPROVE_MERGE"]=race
    run=ejecutar("resolver",sp,fila(sp),ahora="2026-10-10T11:59:59Z")
    assert_cerrada(fila(sp),"NO_EJECUTADO","PENDIENTE","EXPIRADA")
    assert not escrituras_deposito(sp),diagnostico(run)


def test_aprobacion_gana_cas_con_expiracion_ya_leida():
    sp, _, _=solicitar()
    fired=[]
    def race(*_):
        if not fired:
            fired.append(True)
            ejecutar("resolver",sp,fila(sp),ahora="2026-10-10T11:59:59Z")
    sp.antes["EXP_CERRAR_MERGE"]=race
    run=ejecutar("expirar",sp,ahora=LIMITE)
    assert_cerrada(fila(sp),"REVERTIDO")
    assert len(escrituras_deposito(sp))==1,diagnostico(run)


def test_approval_incierta_no_se_recrea_con_trigger_repetido():
    sp, _, _=solicitar()
    first=ejecutar("resolver",sp,fila(sp),aprobacion=FalloConector("TimedOut",504))
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA",diagnostico(first)
    again=ejecutar("resolver",sp,fila(sp))
    assert len(first.approvals_creadas)==1 and not again.approvals_creadas
    assert not escrituras_deposito(sp)
    ejecutar("expirar",sp,ahora=LIMITE)
    assert_cerrada(fila(sp),"NO_EJECUTADO","PENDIENTE","EXPIRADA")


@pytest.mark.parametrize("persistir",[False,True])
def test_merge_incierto_no_se_reintenta_y_expirador_conserva_reserva(persistir):
    sp,run=incertidumbre(persistir=persistir)
    count=len(escrituras_deposito(sp))
    ejecutar("expirar",sp,ahora="2026-10-11T12:00:00Z")
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA"
    assert fila(sp)["ESTADO_SOLICITUD"]=="APROBADO"
    assert len(escrituras_deposito(sp))==count
    assert (sp.fila(D,17)["ULTIMA_REVERSION_ID"]==UID) == persistir,diagnostico(run)


def test_marcador_propio_reconcilia_sin_segunda_limpieza():
    sp,_=incertidumbre()
    before=copy.deepcopy(sp.fila(D,17))
    run=recuperar(sp)
    assert_cerrada(fila(sp),"REVERTIDO")
    assert sp.fila(D,17)==before,diagnostico(run)
    assert len(escrituras_deposito(sp))==1


def test_reversion_a_reconfirmacion_y_recuperacion_a_conserva_confirmacion_posterior():
    sp,_=incertidumbre()
    sp.editar(D,17,ESTADO_ASIGNACION="ASIGNADO", ESTUDIANTE="Confirmación B",
              CODIGO_ESTUDIANTE="B-01",USUARIO_ASIGNACION="otro@univalle.edu")
    before=copy.deepcopy(sp.fila(D,17))
    run=recuperar(sp)
    assert_cerrada(fila(sp),"REVERTIDO")
    assert sp.fila(D,17)==before,diagnostico(run)
    assert len(escrituras_deposito(sp))==1


def test_recuperacion_a_cerrada_no_toca_marcador_b_ni_reserva_b():
    sp,_,_=solicitar()
    ejecutar("resolver",sp,fila(sp))
    sp.editar(D,17,ESTADO_ASIGNACION="ASIGNADO",ESTUDIANTE="B")
    solicitar(sp,uid=UID2)
    ejecutar("resolver",sp,fila(sp,UID2))
    dep=copy.deepcopy(sp.fila(D,17)); req=copy.deepcopy(fila(sp,UID2))
    run=recuperar(sp,proof={})
    assert run.estado_final=="Succeeded",diagnostico(run)
    assert sp.fila(D,17)==dep and fila(sp,UID2)==req
    assert sp.fila(D,17)["ULTIMA_REVERSION_ID"]==UID2


def test_sin_marcador_evidencia_incierta_mantiene_bloqueo():
    sp,_=incertidumbre(persistir=False)
    before=len(escrituras_deposito(sp))
    run=recuperar(sp)
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA",diagnostico(run)
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")
    assert len(escrituras_deposito(sp))==before


def test_reintento_demostrado_sin_efecto_usa_etag_original():
    sp,_=incertidumbre(persistir=False)
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO"))
    assert_cerrada(fila(sp),"REVERTIDO")
    writes=escrituras_deposito(sp)
    assert writes[-1][1]["parameters/headers"]["IF-MATCH"]=='"1"',diagnostico(run)


def test_recuperacion_no_refresca_etag_para_forzar_reversion_antigua():
    sp,_=incertidumbre(persistir=False)
    sp.editar(D,17,ESTUDIANTE="Edición posterior")
    before=len(escrituras_deposito(sp))
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO"))
    assert_cerrada(fila(sp),"CONFLICTO")
    assert len(escrituras_deposito(sp))==before,diagnostico(run)


@pytest.mark.parametrize("merge_estado,resultado",[("INCIERTO",None),("NO_ENVIADO","DEPOSITO_NO_ENCONTRADO")])
def test_404_recuperacion_no_demuestra_resultado_de_intento_incierto(merge_estado,resultado):
    sp,_=incertidumbre(persistir=False)
    sp.listas[D]["items"].pop(17)
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado=merge_estado))
    if resultado:
        assert_cerrada(fila(sp),resultado)
    else:
        assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA",diagnostico(run)
        assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")


@pytest.mark.parametrize("changes",[{"estado_run":"Running"},{"run_id":"otro"},
    {"verificado_por_id":"intruso"},{"url_ejecucion":"https://evil.invalid/run"},
    {"fecha_verificacion":"2026-10-04T12:00:00Z"},{"evidencia_operaciones":""}])
def test_no_transfiere_propiedad_sin_prueba_terminal_valida(changes):
    sp,_=incertidumbre()
    before=copy.deepcopy(fila(sp))
    run=recuperar(sp,proof=evidencia(fila(sp),**changes))
    assert run.estado_final=="Failed",diagnostico(run)
    assert fila(sp)==before


def test_recuperador_no_autorizado_falla_antes_de_escribir():
    sp,_=incertidumbre()
    before=copy.deepcopy(fila(sp))
    run=recuperar(sp,usuario={"id":"otro","userPrincipalName":"operador@univalle.edu"})
    assert run.estado_final=="Failed" and fila(sp)==before,diagnostico(run)


def test_dos_recuperadores_compiten_por_misma_version():
    sp,_=incertidumbre()
    proof=evidencia(fila(sp))
    barrier=threading.Barrier(2)
    seen=set(); lock=threading.Lock()
    def race(*_):
        tid=threading.get_ident()
        with lock:
            first=tid not in seen; seen.add(tid)
        if first:barrier.wait(timeout=10)
    sp.antes["REC_RECLAMAR_MERGE"]=race
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs=list(pool.map(lambda _:recuperar(sp,proof=proof),range(2)))
    assert_cerrada(fila(sp),"REVERTIDO")
    claims=[e for e in eventos(fila(sp)) if e["accion"]=="RECUPERACION_MANUAL_VERIFICADA"]
    assert len(claims)==1,[diagnostico(r) for r in runs]
    assert len(escrituras_deposito(sp))==1


def test_cierre_historial_respuesta_perdida_se_acredita_por_evento():
    sp,_,_=solicitar()
    sp.fallos["RES_E_EXITO_MERGE"]=(504,True)
    run=ejecutar("resolver",sp,fila(sp))
    assert_cerrada(fila(sp),"REVERTIDO")
    assert len(escrituras_deposito(sp))==1,diagnostico(run)


def test_retomar_solicitud_sin_worker_no_extiende_limite():
    sp,_,_=solicitar()
    from p9.reversion.flujos import construir_resolver
    # Copia documental del punto único de configuración, como exige el protocolo
    # manual para una solicitud que nunca llegó a tener trabajador/configuración.
    config={"aprobadores":construir_resolver()["actions"]["PARAM_APROBADORES"]["inputs"],
            "modalidad":"FirstToRespond", "reasignacion":False, "plazo_horas":168}
    proof={"approval_estado":"NO_CREADA", "merge_estado":"NO_ENVIADO", "config_aprobacion":config,
           "fuente_config_url":"https://make.powerautomate.com/environments/ensayo/flows/resolver",
           "fecha_verificacion_config":T0}
    run=recuperar(sp,modo="INICIAR_APROBACION",proof=proof)
    assert_cerrada(fila(sp),"REVERTIDO")
    assert datetime.fromisoformat(fila(sp)["FECHA_LIMITE"].replace("Z", "+00:00")) == datetime.fromisoformat(LIMITE.replace("Z", "+00:00")), diagnostico(run)
    assert len(run.approvals_creadas)==1


@pytest.mark.parametrize("http",[403,429,500,503,504])
def test_fallo_lectura_tras_aprobar_conserva_decision_y_no_es404(http):
    sp,_,_=solicitar()
    sp.fallos["RES_E_DEPOSITO"]=(http,False)
    run=ejecutar("resolver",sp,fila(sp))
    assert fila(sp)["ESTADO_SOLICITUD"]=="APROBADO",diagnostico(run)
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA"
    assert fila(sp)["RESULTADO_TECNICO"]=="ERROR"
    assert not escrituras_deposito(sp)


def test_etag_ausente_en_lectura_critica_error_sin_escritura():
    sp,_,_=solicitar()
    sp.sin_etag_acciones.add("RES_E_DEPOSITO")
    run=ejecutar("resolver",sp,fila(sp))
    assert_cerrada(fila(sp),"ERROR")
    assert not escrituras_deposito(sp),diagnostico(run)


def test_propietario_cambia_antes_de_envio_worker_se_detiene():
    sp,_,_=solicitar()
    sp.antes["RES_E_PRE_MERGE"]=lambda *_:sp.editar(R,1,RUN_ID="otro-dueño")
    run=ejecutar("resolver",sp,fila(sp))
    assert not escrituras_deposito(sp),diagnostico(run)
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")


def test_fallo_cierre_historial_conserva_marcador_y_recupera_solo_historial():
    sp,_,_=solicitar()
    sp.fallos["RES_E_EXITO_MERGE"]=(503,False)
    first=ejecutar("resolver",sp,fila(sp),run_id="fallo-cierre")
    assert sp.fila(D,17)["ULTIMA_REVERSION_ID"]==UID,diagnostico(first)
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")
    before=copy.deepcopy(sp.fila(D,17))
    run=recuperar(sp)
    assert_cerrada(fila(sp),"REVERTIDO")
    assert sp.fila(D,17)==before,diagnostico(run)
    assert len(escrituras_deposito(sp))==1


def test_aprobador_fuera_configuracion_no_autoriza():
    sp,_,_=solicitar()
    answer={"outcome":"Approve","name":"fake","responses":[{
        "responder":{"id":"intruso","userPrincipalName":"intruso@example.com"},
        "responseDate":T0,"comments":"aprobar"}]}
    run=ejecutar("resolver",sp,fila(sp),aprobacion=answer)
    assert fila(sp)["ESTADO_SOLICITUD"]=="PENDIENTE",diagnostico(run)
    assert not escrituras_deposito(sp)
    assert any(e["accion"]=="RESPUESTA_DESCARTADA" for e in eventos(fila(sp)))


def test_recuperacion_espera_misma_aprobacion_sin_crear_otra():
    sp,_,_=solicitar()
    ejecutar("resolver",sp,fila(sp),run_id="run-approval-fallo",aprobacion=FalloConector("Failed",503))
    proof=evidencia(fila(sp),merge_estado="NO_ENVIADO")
    run=recuperar(sp,modo="ESPERAR_APROBACION",proof=proof,ahora="2026-10-05T12:00:00Z")
    assert_cerrada(fila(sp),"REVERTIDO")
    assert not run.approvals_creadas,diagnostico(run)
    assert datetime.fromisoformat(fila(sp)["FECHA_LIMITE"].replace("Z", "+00:00")) == datetime.fromisoformat(LIMITE.replace("Z", "+00:00"))


def test_solicitud_ya_cerrada_sigue_cerrada_aunque_consulta_final_falle():
    sp,_,data=solicitar()
    ejecutar("resolver",sp,fila(sp))
    before=copy.deepcopy(fila(sp)); dep=copy.deepcopy(sp.fila(D,17))
    sp.fallos["BUSCAR_UID"]=(503,False)
    run=ejecutar("solicitar",sp,data)
    assert run.respuesta["resultado"]=="ERROR"
    assert fila(sp)==before and sp.fila(D,17)==dep
    assert_cerrada(fila(sp),"REVERTIDO")


def test_412_recuperacion_relee_marcador_y_conserva_reconfirmacion():
    sp,_=incertidumbre(persistir=False)
    expected={}
    def commit_y_reconfirmacion(*_):
        # El GET previo no veía el efecto. Antes del envío se acredita la
        # reversión y hay una confirmación posterior: el If-Match viejo da412.
        sp.editar(D,17,ULTIMA_REVERSION_ID=UID,ESTADO_ASIGNACION="ASIGNADO",
                  ESTUDIANTE="Confirmación posterior al efecto acreditado",CODIGO_ESTUDIANTE="POST-412")
        expected.update(copy.deepcopy(sp.fila(D,17)))
    sp.antes["REC_A_E_MERGE_DEPOSITO"]=commit_y_reconfirmacion
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO"))
    assert_cerrada(fila(sp),"REVERTIDO")
    assert sp.fila(D,17)==expected,diagnostico(run)
    assert not fila(sp)["ERROR_TECNICO"]
    assert len(escrituras_deposito(sp))==2  # intento incierto y412; nunca tercerMERGE
    calls=[name for name,_ in sp.llamadas]
    merge=calls.index("REC_A_E_MERGE_DEPOSITO")
    subsequent=[p for _,p in sp.llamadas[merge+1:] if sp.listas[D]["id"] in p["parameters/uri"]]
    assert subsequent and subsequent[0]["parameters/method"]=="GET"


def test_412_recuperacion_sin_marcador_propio_no_repite_merge():
    sp,_=incertidumbre(persistir=False)
    sp.antes["REC_A_E_MERGE_DEPOSITO"]=lambda *_:sp.editar(D,17,ESTUDIANTE="Cambio competidor")
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO"))
    assert_cerrada(fila(sp),"CONFLICTO")
    assert sp.fila(D,17)["ESTUDIANTE"]=="Cambio competidor",diagnostico(run)
    assert len(escrituras_deposito(sp))==2


def test_reconcililar_nunca_reenvia_aunque_prueba_diga_no_enviado():
    sp,_=incertidumbre(persistir=False)
    count=len(escrituras_deposito(sp))
    run=recuperar(sp,modo="RECONCILIAR",proof=evidencia(fila(sp),merge_estado="NO_ENVIADO"))
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA",diagnostico(run)
    assert len(escrituras_deposito(sp))==count


def test_cerrar_error_permanente_no_ejecuta_reversion_aprobada():
    sp,_=incertidumbre(persistir=False)
    count=len(escrituras_deposito(sp))
    proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO",error_permanente="Permiso denegado confirmado; sin operación pendiente")
    run=recuperar(sp,modo="CERRAR_ERROR",proof=proof)
    assert_cerrada(fila(sp),"ERROR")
    assert len(escrituras_deposito(sp))==count,diagnostico(run)


def test_412_recuperacion_relectura_fallida_no_cierra_conflicto():
    sp,_=incertidumbre(persistir=False)
    sp.antes["REC_A_E_MERGE_DEPOSITO"]=lambda *_:sp.editar(D,17,ESTUDIANTE="Cambio competidor")
    sp.fallos["REC_A_E_RELEER_TRAS_412"]=(503,False)
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO"))
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA",diagnostico(run)
    assert fila(sp)["RESULTADO_TECNICO"]=="ERROR"
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")
    assert len(escrituras_deposito(sp))==2


def test_marcador_incompatible_con_historial_activo_exige_revision():
    sp,_=incertidumbre(persistir=False)
    sp.editar(D,17,ULTIMA_REVERSION_ID=UID2,ESTUDIANTE="Otra reversión no conciliada")
    before=copy.deepcopy(sp.fila(D,17))
    run=recuperar(sp,modo="CONTINUAR",proof=evidencia(fila(sp),merge_estado="FALLO_SIN_EFECTO"))
    assert fila(sp)["FASE_PROCESO"]=="RECUPERACION_REQUERIDA",diagnostico(run)
    assert fila(sp)["CLAVE_BLOQUEO"].startswith("ACTIVA|")
    assert sp.fila(D,17)==before
