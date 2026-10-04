"""Ejecuta el JSON WDL de reversión contra conectores locales simulados.

No ejecuta red. Las pruebas no certifican Power Apps Studio, importación ni tenant.
La escritura SharePoint y sus restricciones únicas son atómicas bajo un candado.
Los fallos pueden ocurrir antes o después del efecto remoto para probar reconciliación.
"""
from __future__ import annotations

import copy
import base64
import datetime as dt
import json
import re
import threading
import uuid
from urllib.parse import parse_qs, quote, unquote, urlsplit

from p8.ensayo_wdl import FalloConector, Terminado, cadena
from p9.ensayo import EnsayoP9

UTC = dt.timezone.utc


def instante(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def formato_fecha(value, formato):
    if formato != "o":
        raise NotImplementedError(formato)
    fecha = instante(value)
    if fecha.tzinfo is None:
        raise ValueError("Fecha sin zona horaria")
    # ISO round-trip: siete decimales y offset, como el formato 'o' de WDL.
    fraccion = re.search(r"[T ]\d{2}:\d{2}:\d{2}(?:\.(\d+))?", value)
    decimales = ((fraccion.group(1) if fraccion else None) or "").ljust(7, "0")[:7]
    texto = fecha.isoformat(timespec="seconds")
    return texto[:-6] + "." + decimales + texto[-6:].replace("+00:00", "Z")


def union_wdl(*values):
    if all(isinstance(value, list) for value in values):
        result = []
        for value in values:
            for item in value:
                if item not in result:
                    result.append(item)
        return result
    return dict(pair for value in values for pair in value.items())


class ErrorREST(FalloConector):
    def __init__(self, http, codigo="ERROR", estado="Failed"):
        super().__init__(estado, http)
        self.codigo = codigo


def filtro_odata(expression, row):
    """Subconjunto OData usado por los filtros indexados: eq/ne/lt/le/gt/ge, and/or."""
    if not expression:
        return True
    tokens = re.findall(r"datetime'(?:''|[^'])*'|'(?:''|[^'])*'|[()]|[^\s()]+", expression)
    pos = 0

    def atom():
        nonlocal pos
        if tokens[pos] == "(":
            pos += 1
            result = union()
            assert tokens[pos] == ")"
            pos += 1
            return result
        name, op, literal = tokens[pos:pos + 3]
        pos += 3
        es_fecha = literal.startswith("datetime'")
        if es_fecha:
            literal = literal[8:]
        if literal.startswith("'"):
            wanted = literal[1:-1].replace("''", "'")
        elif literal == "null":
            wanted = None
        elif literal in ("true", "false"):
            wanted = literal == "true"
        else:
            wanted = int(literal)
        actual = row.get(name)
        if es_fecha:
            actual, wanted = instante(actual), instante(wanted)
        if isinstance(actual, str) and isinstance(wanted, str) and op in ("eq", "ne"):
            actual, wanted = actual.casefold(), wanted.casefold()
        return {"eq": lambda: actual == wanted, "ne": lambda: actual != wanted,
                "le": lambda: actual <= wanted, "lt": lambda: actual < wanted,
                "ge": lambda: actual >= wanted, "gt": lambda: actual > wanted}[op]()

    def intersection():
        nonlocal pos
        result = atom()
        while pos < len(tokens) and tokens[pos] == "and":
            pos += 1
            other = atom()
            result = result and other
        return result

    def union():
        nonlocal pos
        result = intersection()
        while pos < len(tokens) and tokens[pos] == "or":
            pos += 1
            other = intersection()
            result = result or other
        return result

    result = union()
    assert pos == len(tokens), expression
    return result


class SharePointReversion:
    nombre = "ENSAYO_LOCAL_REVERSION"

    def __init__(self, depositos=(), solicitudes=()):
        self.candado = threading.RLock()
        self.listas = {name: {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "ensayo-reversion:" + name)),
                             "items": {}, "versiones": {}}
                       for name in ("Depositos_Activos", "Depositos_Reversiones")}
        self.llamadas = []
        self.fallos = {}  # acción -> (http, persistir_primero); se consume una sola vez
        self.antes = {}  # acción -> callback para carreras reproducibles
        self.despues = {}
        self.sin_etag = False
        self.sin_etag_acciones = set()
        self.page_size = 100
        for name, rows in (("Depositos_Activos", depositos), ("Depositos_Reversiones", solicitudes)):
            for row in rows:
                self.agregar(name, row)

    def agregar(self, lista, row):
        with self.candado:
            data = self.listas[lista]
            id_ = int(row.get("ID", row.get("Id", max(data["items"], default=0) + 1)))
            data["items"][id_] = {**copy.deepcopy(row), "ID": id_, "Id": id_}
            data["versiones"][id_] = 1
            return id_

    def etag(self, lista, id_):
        return '"' + str(self.listas[lista]["versiones"][id_]) + '"'

    def fila(self, lista, id_):
        with self.candado:
            row = copy.deepcopy(self.listas[lista]["items"][id_])
            if not self.sin_etag:
                row["__metadata"] = {"etag": self.etag(lista, id_)}
                row["@odata.etag"] = self.etag(lista, id_)
            return row

    def editar(self, lista, id_, **changes):
        with self.candado:
            self.listas[lista]["items"][id_].update(changes)
            self.listas[lista]["versiones"][id_] += 1

    def por_uid(self, uid):
        rows = self.listas["Depositos_Reversiones"]["items"]
        return next((self.fila("Depositos_Reversiones", i) for i, r in rows.items()
                     if r.get("SOLICITUD_UID") == uid), None)

    def ejecutar(self, accion, parametros):
        hook = self.antes.get(accion)
        if hook:
            hook(self, parametros)
        fail = self.fallos.pop(accion, None)
        with self.candado:
            self.llamadas.append((accion, copy.deepcopy(parametros)))
        if fail and not fail[1]:
            raise ErrorREST(fail[0])
        with self.candado:
            result = self._rest(parametros)
            if accion in self.sin_etag_acciones:
                result.get("headers", {}).pop("ETag", None)
                row = result.get("body", {}).get("d", {})
                row.pop("__metadata", None)
                row.pop("@odata.etag", None)
        if accion in self.despues:
            self.despues[accion](self, parametros)
        if fail:
            raise ErrorREST(fail[0], "RESPUESTA_PERDIDA", "TimedOut")
        return result

    def _rest(self, p):
        uri = unquote(p["parameters/uri"])
        method = p["parameters/method"].upper()
        headers = {k.lower(): v for k, v in p.get("parameters/headers", {}).items()}
        body = p.get("parameters/body", {})
        if isinstance(body, str):
            body = json.loads(body)
        pattern = r"(?:_api/)?web/lists/(?:GetByTitle|getbytitle)\('([^']+)'\)(.*)"
        match = re.fullmatch(pattern, uri)
        if match:
            name, tail = match.groups()
        else:
            match = re.fullmatch(r"(?:_api/)?web/lists\(guid'([^']+)'\)(.*)", uri)
            if not match:
                raise ValueError("Endpoint no simulado: " + uri)
            name = next((n for n, l in self.listas.items() if l["id"] == match[1]), None)
            tail = match[2]
        if name not in self.listas:
            raise ErrorREST(404)
        data = self.listas[name]
        verbose = "verbose" in headers.get("accept", "")

        def response(payload, status=200, etag=None):
            return {"statusCode": status, "headers": {"ETag": etag} if etag else {},
                    "body": {"d": payload} if verbose else payload}

        if not tail or tail.startswith("?"):
            return response({"Id": data["id"], "Title": name,
                             "ListItemEntityTypeFullName": "SP.Data." + name + "ListItem"})
        match = re.fullmatch(r"/items\((\d+)\)(?:\?.*)?", tail, re.I)
        if match:
            id_ = int(match[1])
            if id_ not in data["items"]:
                raise ErrorREST(404)
            if method == "GET":
                return response(self.fila(name, id_), etag=None if self.sin_etag else self.etag(name, id_))
            assert method in ("POST", "PATCH") and headers.get("x-http-method", "MERGE") == "MERGE"
            assert headers.get("if-match") not in (None, "", "*"), "MERGE sin ETag concreto"
            if headers["if-match"] != self.etag(name, id_):
                raise ErrorREST(412)
            merged = {**data["items"][id_], **body}
            self._unicos(name, merged, exclude=id_)
            self.editar(name, id_, **{k: v for k, v in body.items() if k != "__metadata"})
            return {"statusCode": 204, "body": {}}
        if not tail.lower().startswith("/items"):
            raise ValueError("Endpoint no simulado: " + uri)
        if method == "POST":
            self._unicos(name, body)
            id_ = self.agregar(name, body)
            return response(self.fila(name, id_), 201, self.etag(name, id_))
        assert method == "GET"
        query = parse_qs(urlsplit(tail).query)
        where = query.get("$filter", [""])[0]
        all_rows = [self.fila(name, i) for i in sorted(data["items"])
                    if filtro_odata(where, data["items"][i])]
        # SharePoint pagina por una clave estable, no por el desplazamiento de
        # un conjunto que el propio expirador va reduciendo al cerrar filas.
        after_id = int(query.get("$skiptoken", ["0"])[0])
        all_rows = [row for row in all_rows if row["ID"] > after_id]
        top = min(int(query.get("$top", [str(self.page_size)])[0]), self.page_size)
        rows = all_rows[:top]
        payload = {"results" if verbose else "value": rows}
        if top < len(all_rows):
            prefix = uri.split("&$skiptoken=")[0]
            payload["__next" if verbose else "@odata.nextLink"] = prefix + "&$skiptoken=" + str(rows[-1]["ID"])
        return response(payload)

    def _unicos(self, name, candidate, exclude=None):
        keys = ("CLAVE_TRANSACCION",) if name == "Depositos_Activos" else ("SOLICITUD_UID", "CLAVE_BLOQUEO")
        for k in keys:
            if not candidate.get(k):
                raise ErrorREST(400, "CAMPO_UNICO_OBLIGATORIO")
            for id_, row in self.listas[name]["items"].items():
                if id_ != exclude and str(row.get(k, "")).casefold() == str(candidate[k]).casefold():
                    raise ErrorREST(400, "-2130575169, Microsoft.SharePoint.SPException")


class EnsayoReversion(EnsayoP9):
    """Interpreta las definiciones entregadas; no sustituye WDL por una segunda lógica de negocio."""
    def __init__(self, definicion, sp, entradas=None, *, usuario=None,
                 ahora="2026-10-03T12:00:00Z", run_id="run-local-1", aprobacion=None):
        super().__init__(definicion, sp, entradas, ahora)
        self.usuario = usuario or {"id": "operador-1", "userPrincipalName": "operador@univalle.edu", "displayName": "Operador"}
        self.run_id = run_id
        self.aprobacion = aprobacion or {"outcome": "Approve", "name": "approval-local-1", "responses": [{
            "responder": {"id": "aprobador-1", "userPrincipalName": "gtorricot@univalle.edu", "email": "gtorricot@univalle.edu"},
            "approverResponse": "Approve", "responseDate": ahora, "comments": "Conforme"}]}
        self.approvals_creadas = []
        self.al_aprobar = None
        self.parametros = {k: v.get("defaultValue") for k, v in definicion.get("parameters", {}).items()}

    def _resultado_ambito(self, nombre):
        from p9.reversion.wdl import walk
        ambito = dict(walk(self.definicion["actions"])).get(nombre, {})
        return [{"name": key, "status": self.estados.get(key),
                 **({"outputs": self.salidas[key]} if key in self.salidas else {})}
                for key in ambito.get("actions", {})]

    def _nodo(self, n):
        if n[0] == "funcion":
            name = n[1]
            funcs = {
                "workflow": lambda: {"run": {"name": self.run_id}, "name": "flow-local"},
                "parameters": lambda k: self.parametros.get(k, {}),
                "ticks": lambda v: int((instante(v) - dt.datetime(1, 1, 1, tzinfo=UTC)).total_seconds() * 10_000_000),
                "addHours": lambda v, h: iso(instante(v) + dt.timedelta(hours=h)),
                "addDays": lambda v, d: iso(instante(v) + dt.timedelta(days=d)),
                "addSeconds": lambda v, s: iso(instante(v) + dt.timedelta(seconds=s)),
                "formatDateTime": formato_fecha,
                "int": int, "div": lambda a, b: a // b, "mul": lambda a, b: a * b,
                "guid": lambda: str(uuid.uuid4()), "createArray": lambda *xs: list(xs),
                "array": lambda v: v if isinstance(v, list) else [v],
                "toUpper": lambda s: s.upper(), "last": lambda xs: xs[-1],
                "split": lambda s, d: s.split(d), "uriComponent": lambda s: quote(s, safe=''),
                "encodeUriComponent": lambda s: quote(s, safe=''),
                "base64": lambda s: base64.b64encode(s.encode()).decode(),
                "substring": lambda s, start, length=None: s[start:] if length is None else s[start:start + length],
                "decodeUriComponent": unquote, "removeProperty": lambda o, k: {a: b for a, b in o.items() if a != k},
                "union": union_wdl,
                "result": self._resultado_ambito,
            }
            if name in funcs:
                return funcs[name](*[self._nodo(arg) for arg in n[2]])
        return super()._nodo(n)

    def _accion(self, nombre, accion):
        tipo = accion["type"]
        if tipo in ("OpenApiConnection", "OpenApiConnectionWebhook"):
            raw_inputs = copy.deepcopy(accion["inputs"])
            # Reproduce el parámetro string del conector: un objeto crudo se
            # serializa antes de evaluar, dejando sus expresiones como literales.
            if raw_inputs["host"]["operationId"] == "HttpRequest":
                params = raw_inputs["parameters"]
                if isinstance(params.get("parameters/body"), (dict, list)):
                    params["parameters/body"] = json.dumps(params["parameters/body"], ensure_ascii=False)
            inputs = self.evaluar(raw_inputs)
            op = inputs["host"]["operationId"]
            if op == "HttpRequest":
                try:
                    self.salidas[nombre] = self.sp.ejecutar(nombre, inputs["parameters"])
                except ErrorREST as err:
                    self.salidas[nombre] = {"statusCode": err.http, "body": {"error": {"code": err.codigo, "message": err.codigo}}}
                    return err.estado
            elif op in ("MyProfile_V2", "GetMyProfileV2", "GetMyProfile"):
                self.salidas[nombre] = {"statusCode": 200, "body": copy.deepcopy(self.usuario)}
            elif op in ("StartAndWaitForAnApproval", "WaitForAnApproval"):
                if op == "StartAndWaitForAnApproval":
                    self.approvals_creadas.append(copy.deepcopy(inputs["parameters"]))
                if self.al_aprobar:
                    self.al_aprobar(self)
                if isinstance(self.aprobacion, Exception):
                    raise self.aprobacion
                self.salidas[nombre] = {"statusCode": 200, "body": copy.deepcopy(self.aprobacion)}
            else:
                raise NotImplementedError("Conector no simulado: " + op)
            return "Succeeded"
        if tipo == "Until":
            for _ in range(accion.get("limit", {}).get("count", 100)):
                self._bloque(accion["actions"])
                if self.evaluar(accion["expression"]):
                    return "Succeeded"
            return "TimedOut"
        if tipo == "Wait":
            inputs = self.evaluar(accion["inputs"])
            timestamp = inputs.get("until", {}).get("timestamp")
            if timestamp:
                self.ahora = max(self.ahora, timestamp)
            self.salidas[nombre] = {}
            return "Succeeded"
        return super()._accion(nombre, accion)
