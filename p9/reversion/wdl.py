"""Primitivas WDL propias de reversión; no modifican constructores P9."""
from __future__ import annotations

import json

TODOS = ["Succeeded", "Failed", "Skipped", "TimedOut"]
FALLOS = ["Failed", "TimedOut"]


def seq(**acciones):
    anterior = None
    for nombre, accion in acciones.items():
        if not accion.get("runAfter"):
            accion["runAfter"] = {anterior: ["Succeeded"]} if anterior else {}
        anterior = nombre
    return acciones


def compose(value):
    return {"type": "Compose", "inputs": value}


def setvar(name, value):
    return {"type": "SetVariable", "inputs": {"name": name, "value": value}}


def init(name, tipo, value):
    return {"type": "InitializeVariable", "inputs": {"variables": [{"name": name, "type": tipo, "value": value}]}}


def scope(actions, after=None):
    node = {"type": "Scope", "actions": actions}
    if after is not None:
        node["runAfter"] = after
    return node


def cond(expression, yes, no=None):
    return {"type": "If", "expression": expression, "actions": yes, "else": {"actions": no or {}}}


def expr(value):
    return value if value.startswith("@") else "@" + value


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def concat(*parts):
    return "@concat(" + ",".join(parts) + ")"


def uri(lista, suffix=""):
    """lista es expresión con GUID descubierto, nunca identificador inventado."""
    return concat(quote("_api/web/lists(guid'"), lista, quote("')" + suffix))


def item_uri(lista, ident):
    return concat(quote("_api/web/lists(guid'"), lista, quote("')/items("), f"string({ident})", quote(")"))


def serializar_cuerpo(body):
    """Evalúa propiedades WDL antes de convertir el objeto al body string REST.

    El conector HttpRequest declara body como string. Un dict con expresiones
    puede ser convertido en texto por el conector sin evaluar sus propiedades.
    setProperty conserva los tipos; string serializa/escapa una sola vez al final.
    """
    if not isinstance(body, dict):
        raise TypeError("El cuerpo REST debe construirse desde un objeto")
    constantes, dinamicos = {}, {}
    for key, value in body.items():
        if isinstance(value, str) and value.startswith("@"):
            dinamicos[key] = value[1:]
        else:
            constantes[key] = value
    base = json.dumps(constantes, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    expresion = "json(" + quote(base) + ")"
    for key, value in dinamicos.items():
        expresion = f"setProperty({expresion},{quote(key)},{value})"
    return "@string(" + expresion + ")"


def http(method, url, body=None, etag=None):
    headers = {"Accept": "application/json;odata=verbose"}
    params = {"dataset": "@outputs('PARAM_SITIO_SHAREPOINT')", "parameters/method": method,
              "parameters/uri": url, "parameters/headers": headers}
    if body is not None:
        headers["Content-Type"] = "application/json;odata=nometadata"
        params["parameters/body"] = serializar_cuerpo(body)
    if etag is not None:
        assert etag != "*"
        headers.update({"X-HTTP-Method": "MERGE", "IF-MATCH": etag})
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                 "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": params, "authentication": "@parameters('$authentication')",
        "retryPolicy": {"type": "none"}}}


def api(conn, operation, params, webhook=False):
    return {"type": "OpenApiConnectionWebhook" if webhook else "OpenApiConnection", "inputs": {
        "host": {"apiId": f"/providers/Microsoft.PowerApps/apis/{conn}",
                 "connectionName": conn, "operationId": operation},
        "parameters": params, "authentication": "@parameters('$authentication')",
        "retryPolicy": {"type": "none"}}}


def definition(triggers, actions):
    return {"$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
            "contentVersion": "2.0.0.0", "parameters": {
                "$authentication": {"defaultValue": {}, "type": "SecureObject"},
                "$connections": {"defaultValue": {}, "type": "Object"}},
            "triggers": triggers, "actions": actions, "outputs": {}}


def walk(actions):
    for name, action in actions.items():
        yield name, action
        yield from walk(action.get("actions", {}))
        yield from walk(action.get("else", {}).get("actions", {}))
        for case in action.get("cases", {}).values():
            yield from walk(case.get("actions", {}))
        yield from walk(action.get("default", {}).get("actions", {}))
