"""Helpers mínimos para escribir WDL de P9 (copia propia; no reutiliza el provisionador de P8)."""
from p9 import contrato as C

TODOS = ["Succeeded", "Failed", "Skipped", "TimedOut"]
FALLOS = ["Failed", "TimedOut"]
API = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"


def secuencia(**acciones):
    anterior = None
    for nombre, accion in acciones.items():
        accion.setdefault("runAfter", {anterior: ["Succeeded"]} if anterior else {})
        anterior = nombre
    return acciones


def compose(valor):
    return {"type": "Compose", "inputs": valor}


def variable(nombre, tipo, valor):
    return {"type": "InitializeVariable", "inputs": {"variables": [{"name": nombre, "type": tipo, "value": valor}]}}


def asignar(nombre, valor):
    return {"type": "SetVariable", "inputs": {"name": nombre, "value": valor}}


def agregar(nombre, valor):
    return {"type": "AppendToArrayVariable", "inputs": {"name": nombre, "value": valor}}


def ambito(acciones, despues=None):
    a = {"type": "Scope", "actions": acciones}
    if despues is not None:
        a["runAfter"] = despues
    return a


def si(expresion, acciones, no=None):
    return {"type": "If", "expression": expresion, "actions": acciones, "else": {"actions": no or {}}}


def http_sharepoint(metodo, uri, cabeceras, cuerpo=None):
    """«Enviar una solicitud HTTP a SharePoint» (conector estándar). Sin reintentos: un MERGE no se repite solo."""
    parametros = {"dataset": "@outputs('PARAM_SITIO_SHAREPOINT')", "parameters/method": metodo,
                  "parameters/uri": uri, "parameters/headers": cabeceras}
    if cuerpo is not None:
        parametros["parameters/body"] = cuerpo
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API, "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": parametros, "authentication": "@parameters('$authentication')",
        "retryPolicy": {"type": "none"}}}


def parametros_sitio():
    return {"PARAM_SITIO_SHAREPOINT": compose(C.SITIO_SHAREPOINT),
            "PARAM_LISTA_DEPOSITOS_ACTIVOS": compose(C.LISTA_DEPOSITOS_ACTIVOS_ID)}


def lista_uri(sufijo):
    """Expresión WDL: `_api/web/lists(guid'<GUID>')<sufijo>`; `sufijo` es una lista de trozos (str literales o ('x', expr))."""
    partes = ["'_api/web/lists(guid'''", "outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS')", "''')'"]
    for trozo in sufijo:
        partes.append(trozo[1] if isinstance(trozo, tuple) else "'" + trozo.replace("'", "''") + "'")
    return "@concat(" + ",".join(partes) + ")"


def definicion(triggers, acciones, version="1.0.0.0"):
    return {"$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
            "contentVersion": version,
            "parameters": {"$authentication": {"defaultValue": {}, "type": "SecureObject"},
                           "$connections": {"defaultValue": {}, "type": "Object"}},
            "triggers": triggers, "actions": acciones, "outputs": {}}


def contar_acciones(acciones):
    """Cuenta recursiva de acciones (Scope/If/Foreach incluidos), tal como las cuenta Power Automate."""
    n = 0
    for accion in acciones.values():
        n += 1 + contar_acciones(accion.get("actions", {})) + contar_acciones(accion.get("else", {}).get("actions", {}))
    return n


def recorrer(acciones):
    for nombre, accion in acciones.items():
        yield nombre, accion
        yield from recorrer(accion.get("actions", {}))
        yield from recorrer(accion.get("else", {}).get("actions", {}))
