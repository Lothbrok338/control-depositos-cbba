"""Fixtures locales; todos los identificadores se limitan al simulador."""
import copy
import json
import uuid

from p9.reversion import contrato as C
from p9.reversion import flujos
from p9.reversion.ensayo import EnsayoReversion, SharePointReversion

D = C.LISTA_DEPOSITOS
R = C.LISTA_REVERSIONES
T0 = "2026-10-03T12:00:00Z"
LIMITE = "2026-10-10T12:00:00Z"
UID = "d94fcfa4-5cf2-4a3e-b6e4-02e7650c9f12"
UID2 = "d94fcfa4-5cf2-4a3e-b6e4-02e7650c9f13"
OPERADOR = {"id": "operador-1", "userPrincipalName": "operador@univalle.edu", "displayName": "Operador"}


def deposito(**changes):
    row = {name: "original:" + name for name in C.CAMPOS_SNAPSHOT}
    row.update(ID=17, CLAVE_TRANSACCION="clave:bank:17", CODIGO_ASIGNACION="ASG-00017",
               IMPORTE=1234.56, DEBITO=0, CREDITO=1234.56, SALDO=9876.50,
               BANCO="BANCO ENSAYO", CUENTA_BANCARIA="0696870039", MONEDA="USD",
               FECHA_MOVIMIENTO="2026-10-02T00:00:00Z", ESTADO_ASIGNACION="ASIGNADO",
               ESTUDIANTE="Estudiante original", CODIGO_ESTUDIANTE=None,
               USUARIO_ASIGNACION="confirmador@univalle.edu",
               FECHA_HORA_ASIGNACION="2026-10-03T11:00:00Z", OBSERVACION="áéí & ' \n" * 450,
               ULTIMA_REVERSION_ID=None)
    row.update(changes)
    return row


def servidor(**changes):
    return SharePointReversion([deposito(**changes)])


def entradas(sp, *, uid=UID, motivo="Confirmación equivocada", operacion="ENVIAR", **changes):
    values = {"text": operacion, "number": 17, "text_1": "clave:bank:17",
              "text_2": sp.etag(D, 17), "text_3": motivo, "text_4": uid}
    values.update(changes)
    return values


def ejecutar(nombre, sp, data=None, *, ahora=T0, run_id=None, usuario=None, aprobacion=None, hook=None):
    doc = copy.deepcopy(getattr(flujos, "construir_" + nombre)())
    doc["actions"]["PARAM_SITIO_SHAREPOINT"]["inputs"] = "https://tenant.invalid/sites/pruebas"
    if "PARAM_RESPONSABLES_RECUPERACION" in doc["actions"]:
        doc["actions"]["PARAM_RESPONSABLES_RECUPERACION"]["inputs"] = [OPERADOR["id"]]
    if "LISTA_REVERSIONES_ID" in doc["parameters"]:
        doc["parameters"]["LISTA_REVERSIONES_ID"]["defaultValue"] = sp.listas[R]["id"]
    run = EnsayoReversion(doc, sp, data, ahora=ahora, run_id=run_id or str(uuid.uuid4()),
                         usuario=usuario or OPERADOR, aprobacion=aprobacion)
    run.al_aprobar = hook
    return run.ejecutar()


def solicitar(sp=None, **kwargs):
    sp = sp or servidor()
    data = entradas(sp, **kwargs)
    run = ejecutar("solicitar", sp, data)
    assert run.respuesta and run.respuesta["resultado"] in ("ENVIADA", "EXISTENTE"), diagnostico(run)
    return sp, run, data


def diagnostico(run):
    return {"final": run.estado_final, "respuesta": run.respuesta,
            "fallos": {k: run.salidas.get(k) for k, v in run.estados.items() if v in ("Failed", "TimedOut")},
            "eventos": run.eventos[-20:]}


def fila(sp, uid=UID):
    return sp.por_uid(uid)


def escrituras_deposito(sp):
    guid = sp.listas[D]["id"]
    return [(name, p) for name, p in sp.llamadas
            if guid in p["parameters/uri"] and p["parameters/method"] != "GET"]


def assert_cerrada(row, resultado, decision="APROBADO", fase="FINALIZADA"):
    assert row["ESTADO_SOLICITUD"] == decision
    assert row["FASE_PROCESO"] == fase
    assert row["RESULTADO_TECNICO"] == resultado
    assert row["CLAVE_BLOQUEO"] == "CERRADA|" + row["SOLICITUD_UID"]
    assert row["FECHA_CIERRE"]


def eventos(row):
    return json.loads(row["BITACORA_TECNICA_JSON"])
