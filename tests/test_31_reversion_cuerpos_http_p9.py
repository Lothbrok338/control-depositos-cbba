"""Regresiones del body string de SharePoint; pruebas locales, sin tenant."""
import copy
import datetime as dt
import json

import pytest

from p9.reversion import contrato as C
from p9.reversion.construir import COMPONENTES
from p9.reversion.ensayo import EnsayoReversion
from p9.reversion.flujos import construir_solicitar
from p9.reversion.validar import decodificar_cuerpo, validar_definicion
from p9.reversion.wdl import definition, http, quote, serializar_cuerpo, walk
from reversion_helpers import (
    D, LIMITE, OPERADOR, T0, UID, diagnostico, ejecutar,
    escrituras_deposito, fila, servidor, solicitar,
)

pytestmark = pytest.mark.p9


def cuerpos_http(doc):
    for nombre, accion in walk(doc["actions"]):
        inputs = accion.get("inputs", {})
        if not isinstance(inputs, dict) or inputs.get("host", {}).get("operationId") != "HttpRequest":
            continue
        parametros = inputs["parameters"]
        if "parameters/body" in parametros:
            yield nombre, parametros["parameters/body"]


def fecha_iso(value):
    assert isinstance(value, str) and "T" in value
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert result.tzinfo is not None
    return result


@pytest.mark.parametrize("componente", list(COMPONENTES))
def test_cinco_builders_entregan_body_string_validado(componente):
    nombre, constructor, _ = COMPONENTES[componente]
    doc = constructor()
    cuerpos = list(cuerpos_http(doc))
    assert cuerpos, nombre
    for accion, cuerpo in cuerpos:
        assert isinstance(cuerpo, str), accion
        # Rechaza expresiones anidadas convertidas prematuramente en texto JSON.
        decodificar_cuerpo(cuerpo)
    assert validar_definicion(doc, nombre)["resultado"] == "OK"


@pytest.mark.parametrize("expresion", [
    "@outputs('Snapshot')?['FECHA_MOVIMIENTO']",
    "@body('IDENTIDAD')?['id']",
    "@addHours(outputs('AHORA_SOLICITUD'),168)",
    "@coalesce(outputs('Snapshot')?['CODIGO_ESTUDIANTE'],null)",
])
@pytest.mark.parametrize("transporte", ["objeto", "json_literal", "string_json_literal"])
def test_validador_rechaza_expresiones_literales_en_body(expresion, transporte):
    doc = construir_solicitar()
    payload = {"FECHA_MOVIMIENTO": expresion}
    if transporte == "json_literal":
        payload = json.dumps(payload)
    elif transporte == "string_json_literal":
        payload = "@string(json(" + quote(json.dumps(payload)) + "))"
    accion = dict(walk(doc["actions"]))["CREAR_SOLICITUD"]
    accion["inputs"]["parameters"]["parameters/body"] = payload
    with pytest.raises(ValueError, match="Cuerpo SharePoint inseguro"):
        validar_definicion(doc)


def test_serializacion_evaluada_preserva_tipos_y_escapes_sin_doble_evaluacion():
    run = EnsayoReversion(definition({}, {}), servidor())
    valores = {
        "texto": 'Gabriel O\'Connor: "revisión" \\ archivo\nLínea 2\tñ 🚀',
        "dato_parecido_a_expresion": "@outputs('NO_EJECUTAR')",
        "numero": 1234.56, "cero": 0, "booleano": False, "opcional": None,
    }
    run.salidas["Datos"] = valores
    plantilla = {
        "fijo": 'Texto "fijo" O\'Connor\ncon ñ',
        "falso": False, "nulo": None, "entero": 17, "decimal": 1.25,
        "objeto": {"lista": [None, False, 0, "ñ"]},
        **{key: "@outputs('Datos')?[" + quote(key) + "]" for key in valores},
        "nombre'con_comilla": "@outputs('Datos')?['texto']",
    }
    cuerpo = serializar_cuerpo(plantilla)
    assert decodificar_cuerpo(cuerpo) == plantilla
    transportado = run.evaluar(cuerpo)
    assert isinstance(transportado, str)
    real = json.loads(transportado)
    assert real == {
        **{k: v for k, v in plantilla.items() if not isinstance(v, str) or not v.startswith("@")},
        **valores,
        "nombre'con_comilla": valores["texto"],
    }
    assert type(real["numero"]) is float and type(real["cero"]) is int
    assert real["booleano"] is False and real["opcional"] is None


def test_simulador_reproduce_coercion_del_objeto_antes_de_evaluar_expresiones():
    class Captura:
        nombre = "CAPTURA_HTTP_LOCAL"

        def ejecutar(self, nombre, parametros):
            self.parametros = parametros
            return {"statusCode": 201, "body": {}}

    sp = Captura()
    run = EnsayoReversion(definition({}, {}), sp)
    run.salidas["Fecha"] = T0
    run.salidas["PARAM_SITIO_SHAREPOINT"] = "https://tenant.invalid/sites/pruebas"
    accion = http("POST", "_api/web/lists", {})
    # Reintroducir deliberadamente el defecto: objeto donde el conector espera string.
    accion["inputs"]["parameters"]["parameters/body"] = {"FECHA_SOLICITUD": "@outputs('Fecha')"}
    assert run._accion("CREAR_SOLICITUD", accion) == "Succeeded"
    cuerpo = sp.parametros["parameters/body"]
    assert isinstance(cuerpo, str)
    assert json.loads(cuerpo)["FECHA_SOLICITUD"] == "@outputs('Fecha')"

    accion["inputs"]["parameters"]["parameters/body"] = serializar_cuerpo({"FECHA_SOLICITUD": "@outputs('Fecha')"})
    run._accion("CREAR_SOLICITUD", accion)
    assert json.loads(sp.parametros["parameters/body"])["FECHA_SOLICITUD"] == T0


@pytest.mark.parametrize("importe", [1234.56, "1234.56", 0, "0"])
def test_crear_solicitud_transporta_iso_numeros_null_y_snapshot_original(importe):
    sp = servidor(IMPORTE=importe,
                  FECHA_MOVIMIENTO="2026-10-02T00:00:00.1234567-04:00",
                  FECHA_HORA_ASIGNACION="2026-10-03T11:00:00.7654321-04:00")
    original = copy.deepcopy(sp.fila(D, 17))
    sp, run, entrada = solicitar(sp)
    llamadas = [p for name, p in sp.llamadas if name == "CREAR_SOLICITUD"]
    assert len(llamadas) == 1, diagnostico(run)
    wire = llamadas[0]["parameters/body"]
    assert isinstance(wire, str)
    payload = json.loads(wire)
    assert type(payload["DEPOSITO_ID"]) is int and payload["DEPOSITO_ID"] == 17
    assert type(payload["IMPORTE"]) in (int, float) and payload["IMPORTE"] == float(importe)
    for campo in ("FECHA_MOVIMIENTO", "FECHA_HORA_ASIGNACION"):
        assert fecha_iso(payload[campo]) == fecha_iso(original[campo])
        assert payload[campo] == original[campo]  # Conserva también el séptimo decimal y el offset.
    assert fecha_iso(payload["FECHA_SOLICITUD"]) == fecha_iso(T0)
    assert fecha_iso(payload["FECHA_LIMITE"]) == fecha_iso(LIMITE)
    assert fecha_iso(payload["FECHA_LIMITE"]) - fecha_iso(payload["FECHA_SOLICITUD"]) == dt.timedelta(hours=168)
    assert payload["CODIGO_ESTUDIANTE"] is None
    assert payload["RESULTADO_TECNICO"] is None
    assert payload["ESTADO_SOLICITUD"] == "PENDIENTE" and payload["FASE_PROCESO"] == "RECIBIDA"
    assert payload["ETAG_SOLICITUD"] == entrada["text_2"]
    snapshot = json.loads(payload["SNAPSHOT_JSON"])
    assert all(snapshot[k] == original[k] for k in C.CAMPOS_SNAPSHOT)
    assert payload["CODIGO_ASIGNACION"] == original["CODIGO_ASIGNACION"]
    assert payload["CLAVE_TRANSACCION"] == original["CLAVE_TRANSACCION"]
    assert sp.fila(D, 17) == original and not escrituras_deposito(sp)


@pytest.mark.parametrize("ausente", [None, ""])
def test_opcionales_ausentes_llegan_como_null_sin_vaciar_snapshot(ausente):
    opcionales = set(C.CAMPOS_LIMPIAR) | {"CODIGO_ASIGNACION"}
    sp = servidor(**dict.fromkeys(opcionales, ausente))
    sp, _, _ = solicitar(sp)
    wire = next(p["parameters/body"] for name, p in sp.llamadas if name == "CREAR_SOLICITUD")
    payload = json.loads(wire)
    snapshot = json.loads(payload["SNAPSHOT_JSON"])
    assert all(payload[k] is None for k in opcionales)
    assert all(snapshot[k] == ausente for k in opcionales)


@pytest.mark.parametrize("recuperar", [False, True])
def test_merge_deposito_wire_conserva_null_etag_y_campos_motor(recuperar):
    sp, _, _ = solicitar()
    original = copy.deepcopy(sp.fila(D, 17))
    if recuperar:
        sp.fallos["RES_E_MERGE_DEPOSITO"] = (504, False)
    run = ejecutar("resolver", sp, fila(sp), run_id="worker-original-local")
    if recuperar:
        row = fila(sp)
        assert row["FASE_PROCESO"] == "RECUPERACION_REQUERIDA", diagnostico(run)
        proof = {
            "run_id": row["RUN_ID"], "estado_run": "Failed",
            "url_ejecucion": "https://make.powerautomate.com/environments/ensayo/flows/ensayo/runs/" + row["RUN_ID"],
            "fecha_fin_run": T0, "fecha_verificacion": T0,
            "verificado_por_id": OPERADOR["id"],
            "motivo_recuperacion": "Evidencia local de fallo anterior al efecto",
            "evidencia_operaciones": "MERGE fallido sin efecto, worker terminado",
            "merge_estado": "FALLO_SIN_EFECTO", "approval_estado": "CREADA_IDENTIFICADA",
            "aprobacion_id": row["APROBACION_ID"], "solicitud_uid": UID,
        }
        run = ejecutar("recuperar", sp, {"text": UID, "text_1": "CONTINUAR", "text_2": json.dumps(proof)})
    assert fila(sp)["RESULTADO_TECNICO"] == "REVERTIDO", diagnostico(run)
    name, parametros = escrituras_deposito(sp)[-1]
    assert name.startswith("REC_" if recuperar else "RES_")
    assert isinstance(parametros["parameters/body"], str)
    payload = json.loads(parametros["parameters/body"])
    assert payload == C.payload_reversion(UID)
    assert len(payload) == 9 and all(payload[k] is None for k in C.CAMPOS_LIMPIAR)
    assert not set(payload) & set(C.CAMPOS_MOTOR)
    assert parametros["parameters/headers"]["IF-MATCH"] == original["@odata.etag"]
    assert all(sp.fila(D, 17)[k] == original[k] for k in C.CAMPOS_MOTOR)
