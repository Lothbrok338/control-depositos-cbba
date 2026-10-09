# -*- coding: utf-8 -*-
"""
p10/ensayo_wdl.py · P10-A.2 · intérprete local del subconjunto de WDL (Power Automate) que usan los flujos de P10.

NO es el runtime de Microsoft ni certifica la importación ni los conectores. Sirve para ejecutar el JSON REAL de los flujos contra un tenant
simulado (`tenant_simulado.py`) y comprobar su lógica: orden de ejecución (runAfter), Scope/If/Foreach, estado de cada acción, variables,
Terminate y, sobre todo, las expresiones. Es ESTRICTO a propósito:
  * solo acepta funciones de WDL que existen de verdad (lista cerrada); una función inventada o mal escrita falla la acción;
  * leer la salida de una acción que no se ejecutó falla la acción (en Power Automate puede o no fallar: el flujo no debe depender de ello);
  * un Scope falla si alguna acción hija falló y ninguna otra acción hermana, ejecutada, la «recoge» con su runAfter.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

ZONA_BOLIVIA = timezone(timedelta(hours=-4))


class FalloAccion(Exception):
    def __init__(self, codigo="ActionFailed", mensaje="", http=None, estado="Failed"):
        super().__init__(mensaje or codigo)
        self.codigo, self.mensaje, self.http, self.estado = codigo, mensaje, http, estado


class Terminado(Exception):
    def __init__(self, estado, codigo=None, mensaje=None):
        self.estado, self.codigo, self.mensaje = estado, codigo, mensaje


class ErrorExpresion(Exception):
    pass


# ------------------------------------------------------------------ tiempo
def _a_utc(texto):
    t = str(texto).strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(t)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _iso(d):
    d = d.astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond:06d}0Z"


def _formatear(d, formato):
    tabla = {"yyyy": "%Y", "MM": "%m", "dd": "%d", "HH": "%H", "mm": "%M", "ss": "%S"}
    salida, i = [], 0
    while i < len(formato):
        for tok in ("yyyy", "MM", "dd", "HH", "mm", "ss"):
            if formato.startswith(tok, i):
                salida.append(d.strftime(tabla[tok]))
                i += len(tok)
                break
        else:
            salida.append(formato[i])
            i += 1
    return "".join(salida)


ZONAS = {"UTC": timezone.utc, "SA Western Standard Time": ZONA_BOLIVIA}


# ------------------------------------------------------------------ valores
def cadena(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return str(v)


def vacio(v):
    return v is None or v == "" or v == [] or v == {}


def _igual(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return a == b


def _comparar(a, b, op):
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        raise ErrorExpresion(f"comparación entre tipos distintos: {type(a).__name__} / {type(b).__name__}")
    return op(a, b)


# ------------------------------------------------------------------ analizador
_TOKEN = re.compile(r"\s*('(?:''|[^'])*'|-?\d+(?:\.\d+)?|[A-Za-z_][\w]*|\?\[|[(),\[\]])")


def tokenizar(texto):
    pos, tokens = 0, []
    while pos < len(texto):
        m = _TOKEN.match(texto, pos)
        if not m:
            if texto[pos:].strip() == "":
                break
            raise ErrorExpresion(f"carácter inesperado en {texto[pos:pos + 20]!r}")
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


class Analizador:
    def __init__(self, texto):
        self.t, self.i = tokenizar(texto), 0

    def tomar(self, esperado=None):
        if self.i >= len(self.t):
            raise ErrorExpresion("expresión incompleta")
        v = self.t[self.i]
        self.i += 1
        if esperado and v != esperado:
            raise ErrorExpresion(f"se esperaba {esperado!r} y llegó {v!r}")
        return v

    def expresion(self):
        tok = self.tomar()
        if tok.startswith("'"):
            nodo = ("lit", tok[1:-1].replace("''", "'"))
        elif re.fullmatch(r"-?\d+", tok):
            nodo = ("lit", int(tok))
        elif re.fullmatch(r"-?\d+\.\d+", tok):
            nodo = ("lit", float(tok))
        elif tok in ("true", "false", "null"):
            nodo = ("lit", {"true": True, "false": False, "null": None}[tok])
        elif re.fullmatch(r"[A-Za-z_]\w*", tok):
            self.tomar("(")
            args = []
            if self.t[self.i] != ")":
                while True:
                    args.append(self.expresion())
                    if self.t[self.i] != ",":
                        break
                    self.tomar(",")
            self.tomar(")")
            nodo = ("fn", tok, args)
        else:
            raise ErrorExpresion(f"token inesperado {tok!r}")
        while self.i < len(self.t) and self.t[self.i] in ("[", "?["):
            seguro = self.tomar() == "?["
            clave = self.expresion()
            self.tomar("]")
            nodo = ("idx", nodo, clave, seguro)
        return nodo

    def completo(self):
        n = self.expresion()
        if self.i != len(self.t):
            raise ErrorExpresion("sobran tokens al final de la expresión")
        return n


FUNCIONES_PERMITIDAS = {
    "variables", "outputs", "body", "actions", "items", "item", "workflow", "triggerBody", "triggerOutputs", "parameters", "result",
    "utcNow", "convertTimeZone", "formatDateTime", "addDays", "addMinutes", "startOfMonth", "ticks",
    "concat", "substring", "replace", "toLower", "toUpper", "trim", "startsWith", "endsWith", "contains", "indexOf", "lastIndexOf",
    "length", "empty", "equals", "not", "and", "or", "if", "greater", "greaterOrEquals", "less", "lessOrEquals", "coalesce",
    "first", "last", "take", "skip", "join", "union", "createArray", "string", "int", "float", "json", "base64", "base64ToString",
    "base64ToBinary", "uriComponent", "add", "sub", "mul", "div", "range", "min", "max", "split"}


# ------------------------------------------------------------------ intérprete
class Ejecucion:
    def __init__(self, definicion, entorno, nombre_ejecucion="run-0001", disparador="manual"):
        self.defn, self.env = definicion, entorno
        self.nombre_ejecucion = nombre_ejecucion
        self.variables, self.tipos = {}, {}
        self.salidas, self.estados, self.errores, self.tipo_accion = {}, {}, {}, {}
        self.iteraciones, self.item_actual = {}, None
        self.estado_final, self.error_final = None, None
        self.orden = []                       # nombres de acciones en el orden en que corrieron
        self.nombres = {}
        self._indexar(definicion["actions"])

    def _indexar(self, acciones):
        for n, a in acciones.items():
            if n in self.nombres:
                raise AssertionError(f"nombre de acción repetido: {n}")
            self.nombres[n] = a
            self._indexar(a.get("actions", {}))
            self._indexar(a.get("else", {}).get("actions", {}))

    # ---- evaluación
    def evaluar(self, v):
        if isinstance(v, dict):
            return {k: self.evaluar(x) for k, x in v.items()}
        if isinstance(v, list):
            return [self.evaluar(x) for x in v]
        if isinstance(v, str) and v.startswith("@") and not v.startswith("@@"):
            return self._nodo(Analizador(v[1:]).completo())
        return v

    def _nodo(self, n):
        if n[0] == "lit":
            return n[1]
        if n[0] == "idx":
            base, clave = self._nodo(n[1]), self._nodo(n[2])
            if base is None:
                if n[3]:
                    return None
                raise ErrorExpresion("acceso a propiedad de null")
            if isinstance(base, dict):
                if clave in base:
                    return base[clave]
                if n[3]:
                    return None
                raise ErrorExpresion(f"propiedad inexistente {clave!r}")
            if isinstance(base, list) and isinstance(clave, int):
                if 0 <= clave < len(base):
                    return base[clave]
                raise ErrorExpresion("índice fuera de rango")
            raise ErrorExpresion("acceso inválido")
        _, nombre, args = n
        if nombre not in FUNCIONES_PERMITIDAS:
            raise ErrorExpresion(f"función inexistente en WDL: {nombre}")
        if nombre == "if":
            return self._nodo(args[1] if self._nodo(args[0]) is True else args[2])
        if nombre == "and":
            return all(self._nodo(a) is True for a in args)
        if nombre == "or":
            return any(self._nodo(a) is True for a in args)
        if nombre == "coalesce":
            for a in args:
                v = self._nodo(a)
                if v is not None:
                    return v
            return None
        return self._fn(nombre, [self._nodo(a) for a in args])

    def _salida(self, nombre):
        if nombre not in self.salidas:
            raise ErrorExpresion(f"la acción {nombre!r} no produjo salida (no se ejecutó o falló)")
        return self.salidas[nombre]

    def _fn(self, f, a):
        if f == "variables":
            if a[0] not in self.variables:
                raise ErrorExpresion(f"variable no inicializada {a[0]}")
            return self.variables[a[0]]
        if f == "outputs":
            s = self._salida(a[0])
            return s["__valor"] if isinstance(s, dict) and "__valor" in s else s
        if f == "body":
            s = self._salida(a[0])
            if isinstance(s, dict) and "__valor" in s:
                return s["__valor"]
            return s.get("body") if isinstance(s, dict) else s
        if f == "actions":
            if a[0] not in self.nombres:
                raise ErrorExpresion(f"acción inexistente {a[0]}")
            r = {"status": self.estados.get(a[0], "Skipped")}
            if a[0] in self.salidas:
                r["outputs"] = self.salidas[a[0]]
            if a[0] in self.errores:
                r["error"] = self.errores[a[0]]
            return r
        if f == "items":
            if a[0] not in self.iteraciones:
                raise ErrorExpresion(f"items() fuera del bucle {a[0]}")
            return self.iteraciones[a[0]]
        if f == "item":
            return self.item_actual
        if f == "workflow":
            return {"run": {"name": self.nombre_ejecucion}, "name": "flujo-local"}
        if f == "parameters":
            return {}
        if f in ("triggerBody", "triggerOutputs"):
            return {}
        if f == "utcNow":
            return _iso(self.env.ahora_utc())
        if f == "convertTimeZone":
            d = _a_utc(a[0]).astimezone(ZONAS[a[2]])
            return _formatear(d, a[3]) if len(a) > 3 else _iso(d)
        if f == "formatDateTime":
            return _formatear(_a_utc(a[0]), a[1])
        if f == "addDays":
            return _iso(_a_utc(a[0]) + timedelta(days=a[1]))
        if f == "addMinutes":
            return _iso(_a_utc(a[0]) + timedelta(minutes=a[1]))
        if f == "startOfMonth":
            d = _a_utc(a[0])
            return _iso(d.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        if f == "ticks":
            d = _a_utc(a[0])
            return int((d - datetime(1, 1, 1, tzinfo=timezone.utc)) / timedelta(microseconds=1)) * 10
        if f == "concat":
            return "".join(cadena(x) for x in a)
        if f == "substring":
            s, ini = cadena(a[0]), a[1]
            n = a[2] if len(a) > 2 else len(s) - ini
            if ini < 0 or n < 0 or ini + n > len(s):
                raise ErrorExpresion("substring fuera de rango")
            return s[ini:ini + n]
        if f == "replace":
            return cadena(a[0]).replace(a[1], a[2])
        if f == "toLower":
            return cadena(a[0]).lower()
        if f == "toUpper":
            return cadena(a[0]).upper()
        if f == "trim":
            return cadena(a[0]).strip()
        if f == "startsWith":
            return cadena(a[0]).lower().startswith(cadena(a[1]).lower())
        if f == "endsWith":
            return cadena(a[0]).lower().endswith(cadena(a[1]).lower())
        if f == "contains":
            if isinstance(a[0], dict):
                return a[1] in a[0]
            if isinstance(a[0], list):
                return any(_igual(x, a[1]) for x in a[0])
            return cadena(a[1]) in cadena(a[0])
        if f == "indexOf":
            return cadena(a[0]).lower().find(cadena(a[1]).lower())
        if f == "lastIndexOf":
            return cadena(a[0]).lower().rfind(cadena(a[1]).lower())
        if f == "split":
            return cadena(a[0]).split(a[1])
        if f == "length":
            if a[0] is None or isinstance(a[0], (int, float, bool)):
                raise ErrorExpresion("length() de un valor sin longitud")
            return len(a[0])
        if f == "empty":
            return vacio(a[0])
        if f == "equals":
            return _igual(a[0], a[1])
        if f == "not":
            if not isinstance(a[0], bool):
                raise ErrorExpresion("not() espera un booleano")
            return not a[0]
        if f == "greater":
            return _comparar(a[0], a[1], lambda x, y: x > y)
        if f == "greaterOrEquals":
            return _comparar(a[0], a[1], lambda x, y: x >= y)
        if f == "less":
            return _comparar(a[0], a[1], lambda x, y: x < y)
        if f == "lessOrEquals":
            return _comparar(a[0], a[1], lambda x, y: x <= y)
        if f == "first":
            if isinstance(a[0], str):
                return a[0][:1]
            return a[0][0] if a[0] else None
        if f == "last":
            return a[0][-1] if a[0] else None
        if f == "take":
            return a[0][:a[1]]
        if f == "skip":
            return a[0][a[1]:]
        if f == "join":
            return a[1].join(cadena(x) for x in a[0])
        if f == "union":
            if all(isinstance(x, list) for x in a):
                out = []
                for x in a:
                    for y in x:
                        if y not in out:
                            out.append(y)
                return out
            out = {}
            for x in a:
                out.update(x)
            return out
        if f == "createArray":
            return list(a)
        if f == "string":
            return cadena(a[0])
        if f == "int":
            try:
                return int(a[0])
            except (TypeError, ValueError):
                raise ErrorExpresion(f"int() no puede convertir {a[0]!r}")
        if f == "float":
            return float(a[0])
        if f == "json":
            return json.loads(a[0]) if isinstance(a[0], str) else a[0]
        if f == "base64":
            return base64.b64encode(cadena(a[0]).encode()).decode()
        if f == "base64ToString":
            return base64.b64decode(a[0], validate=True).decode("utf-8")
        if f == "base64ToBinary":
            base64.b64decode(a[0], validate=True)
            return {"$content-type": "application/octet-stream", "$content": a[0]}
        if f == "uriComponent":
            return urllib.parse.quote(cadena(a[0]), safe="")
        if f == "add":
            return a[0] + a[1]
        if f == "sub":
            return a[0] - a[1]
        if f == "mul":
            return a[0] * a[1]
        if f == "div":
            if a[1] == 0:
                raise ErrorExpresion("división por cero")
            return a[0] // a[1] if isinstance(a[0], int) and isinstance(a[1], int) else a[0] / a[1]
        if f == "range":
            return list(range(a[0], a[0] + a[1]))
        if f in ("min", "max"):
            xs = a[0] if len(a) == 1 and isinstance(a[0], list) else a
            return (min if f == "min" else max)(xs)
        if f == "result":
            if a[0] not in self.nombres:
                raise ErrorExpresion(f"acción inexistente {a[0]}")
            hijas = self.nombres[a[0]].get("actions", {})
            return [{"name": h, "status": self.estados.get(h, "Skipped"), **({"error": self.errores[h]} if h in self.errores else {})}
                    for h in hijas]
        raise ErrorExpresion(f"función sin implementar {f}")

    # ---- ejecución
    def ejecutar(self):
        try:
            self._bloque(self.defn["actions"])
            self.estado_final = "Succeeded" if not self._hay_fallo_no_recogido(self.defn["actions"]) else "Failed"
        except Terminado as t:
            self.estado_final, self.error_final = t.estado, (t.codigo, t.mensaje)
        return self

    def _hay_fallo_no_recogido(self, acciones):
        return self._fallo(acciones)

    def _fallo(self, acciones):
        """True si alguna acción hermana falló y ninguna otra ejecutada la recoge (semántica de «última acción» de los Scope)."""
        for n, a in acciones.items():
            if self.estados.get(n) in ("Failed", "TimedOut"):
                recogida = any(n in b.get("runAfter", {}) and self.estados.get(m) not in (None, "Skipped") and
                               self.estados.get(n) in b["runAfter"][n] for m, b in acciones.items() if m != n)
                if not recogida:
                    return True
        return False

    def _bloque(self, acciones):
        pendientes = dict(acciones)
        locales = {}
        while pendientes:
            avance = False
            for n, a in list(pendientes.items()):
                ra = a.get("runAfter", {})
                if not all(d in locales for d in ra):
                    continue
                avance = True
                if not all(locales[d] in estados for d, estados in ra.items()):
                    self._omitir({n: a})
                    est = "Skipped"
                else:
                    est = self._correr(n, a)
                self.estados[n] = locales[n] = est
                pendientes.pop(n)
            if not avance:
                raise AssertionError(f"runAfter inválido o cíclico: {list(pendientes)}")
        return "Failed" if self._fallo(acciones) else "Succeeded"

    def _omitir(self, acciones):
        for n, a in acciones.items():
            self.estados[n] = "Skipped"
            self.salidas.pop(n, None)
            self._omitir(a.get("actions", {}))
            self._omitir(a.get("else", {}).get("actions", {}))

    def _correr(self, n, a):
        self.orden.append(n)
        t = a["type"]
        self.tipo_accion[n] = t
        try:
            if t == "Scope":
                return self._bloque(a["actions"])
            if t == "If":
                cond = self.evaluar(a["expression"])
                if not isinstance(cond, bool):
                    raise ErrorExpresion("la condición de If no es booleana")
                elegido, otro = (a["actions"], a.get("else", {}).get("actions", {})) if cond else (a.get("else", {}).get("actions", {}), a["actions"])
                self._omitir(otro)
                return self._bloque(elegido)
            if t == "Foreach":
                coleccion = self.evaluar(a["foreach"])
                if not isinstance(coleccion, list):
                    raise ErrorExpresion("Foreach sobre un valor que no es lista")
                estados = []
                for v in coleccion:
                    self.iteraciones[n] = v
                    self._omitir(a["actions"])
                    estados.append(self._bloque(a["actions"]))
                self.iteraciones.pop(n, None)
                return "Failed" if "Failed" in estados else "Succeeded"
            if t in ("Select", "Query"):
                entrada, previo, salida = self.evaluar(a["inputs"]["from"]), self.item_actual, []
                for it in entrada:
                    self.item_actual = it
                    if t == "Select":
                        salida.append(self.evaluar(a["inputs"]["select"]))
                    elif self.evaluar(a["inputs"]["where"]) is True:
                        salida.append(it)
                self.item_actual = previo
                self.salidas[n] = {"body": salida}
                return "Succeeded"
            ent = self.evaluar(a.get("inputs", {}))
            if t == "Compose":
                self.salidas[n] = {"__valor": ent}
            elif t == "InitializeVariable":
                for v in ent["variables"]:
                    self.variables[v["name"]], self.tipos[v["name"]] = v["value"], v["type"]
            elif t == "SetVariable":
                self._asignable(ent["name"], ent["value"])
                self.variables[ent["name"]] = ent["value"]
            elif t == "IncrementVariable":
                self.variables[ent["name"]] += ent["value"]
            elif t == "AppendToArrayVariable":
                self.variables[ent["name"]].append(ent["value"])
            elif t in ("Http", "OpenApiConnection"):
                self.salidas[n] = self.env.ejecutar(n, t, ent, a)
            elif t == "Terminate":
                err = ent.get("runError", {})
                raise Terminado(ent["runStatus"], err.get("code"), err.get("message"))
            else:
                raise AssertionError(f"tipo de acción sin implementar: {t}")
            return "Succeeded"
        except FalloAccion as e:
            self.errores[n] = {"code": e.codigo, "message": e.mensaje}
            self.salidas[n] = {"statusCode": e.http, "body": None} if e.http else self.salidas.get(n, {})
            return e.estado
        except (ErrorExpresion, KeyError, TypeError, ValueError, IndexError, AttributeError, json.JSONDecodeError) as e:
            self.errores[n] = {"code": "ExpressionEvaluationFailed", "message": f"{type(e).__name__}: {str(e)[:200]}"}
            return "Failed"

    def _asignable(self, nombre, valor):
        tipo = self.tipos.get(nombre)
        esperado = {"integer": int, "string": str, "boolean": bool, "array": list, "object": dict}.get(tipo)
        if esperado and (not isinstance(valor, esperado) or (esperado is int and isinstance(valor, bool))):
            raise ErrorExpresion(f"la variable {nombre} es {tipo} y se le asignó {type(valor).__name__}")
