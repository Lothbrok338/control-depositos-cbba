"""Ensayo local del JSON WDL generado, con SharePoint simulado.

Interpreta solo el subconjunto de WDL usado por P8, incluidos runAfter, Scope,
If y Foreach. No es el runtime Microsoft ni certifica importación/conectores.
Por defecto propaga el fallo de cualquier hijo al Scope: prueba el caso más
conservador del manejo de errores. No ejecuta red ni escribe archivos.
"""
from __future__ import annotations

import base64
import copy
import json
import re


def cadena(valor):
    if isinstance(valor, str):
        return valor
    if valor is None:
        return ""
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


class Expresion:
    def __init__(self, texto):
        self.tokens = re.findall(r"'(?:''|[^'])*'|-?\d+(?:\.\d+)?|[A-Za-z_$][\w$]*|\?\[|[(),\[\]]", texto)
        self.i = 0

    def tomar(self, esperado=None):
        valor = self.tokens[self.i]
        self.i += 1
        if esperado is not None and valor != esperado:
            raise ValueError((esperado, valor))
        return valor

    def analizar(self):
        t = self.tomar()
        if t.startswith("'"):
            nodo = ("literal", t[1:-1].replace("''", "'"))
        elif t in ("true", "false", "null"):
            nodo = ("literal", {"true": True, "false": False, "null": None}[t])
        elif re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            nodo = ("literal", float(t) if "." in t else int(t))
        else:
            self.tomar("(")
            args = []
            if self.tokens[self.i] != ")":
                while True:
                    args.append(self.analizar())
                    if self.tokens[self.i] != ",":
                        break
                    self.tomar(",")
            self.tomar(")")
            nodo = ("funcion", t, args)
        while self.i < len(self.tokens) and self.tokens[self.i] in ("[", "?["):
            seguro = self.tomar() == "?["
            clave = self.analizar()
            self.tomar("]")
            nodo = ("acceso", nodo, clave, seguro)
        return nodo


class FalloConector(Exception):
    def __init__(self, estado="Failed", http=500):
        self.estado, self.http = estado, http


class Terminado(Exception):
    def __init__(self, estado):
        self.estado = estado


def validar_esquema(valor, esquema):
    tipos = {"object": dict, "array": list, "string": str, "integer": int}
    if not isinstance(valor, tipos[esquema["type"]]):
        raise ValueError("Tipo incorrecto")
    if isinstance(valor, dict):
        for campo in esquema.get("required", []):
            if campo not in valor:
                raise ValueError(f"Propiedad obligatoria ausente: {campo}")
        for campo, contenido in valor.items():
            if campo in esquema.get("properties", {}):
                validar_esquema(contenido, esquema["properties"][campo])
    elif isinstance(valor, list):
        for contenido in valor:
            validar_esquema(contenido, esquema["items"])


class SharePointSimulado:
    def __init__(self, contenido, existentes=None, fallos=None, nombre="DEPOSITOS_ACTIVOS__piloto.json", directo=False,
                 alteraciones=None):
        self.contenido = contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False)
        self.activos = copy.deepcopy(existentes or {})
        self.fallos = fallos or {}
        # {(accion, clave): {campo: valor}}: altera solo el registro DEVUELTO por SharePoint
        # (preconsulta, respuesta del POST o reconsulta), no el almacenado.
        self.alteraciones = alteraciones or {}
        self.nombre = nombre
        self.directo = directo
        self.bitacoras = []
        self.llamadas = []
        self.creaciones = []
        self.coincidencias_preconsulta = 0

    def _registro(self, nombre, clave, fila):
        """Registro tal como lo devuelve SharePoint: la fecha solo-fecha llega como fecha-hora ISO."""
        r = copy.deepcopy(fila)
        if isinstance(r.get("FECHA_MOVIMIENTO"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["FECHA_MOVIMIENTO"]):
            r["FECHA_MOVIMIENTO"] += "T00:00:00Z"
        r.update(self.alteraciones.get((nombre, clave), {}))
        return r

    def ejecutar(self, nombre, parametros):
        self.llamadas.append((nombre, copy.deepcopy(parametros)))
        if nombre == "Obtener_contenido_del_archivo":
            if nombre in self.fallos:
                raise FalloConector(*self.fallos[nombre])
            if self.directo:
                return {"body": json.loads(self.contenido)}
            return {"body": {"$content-type": "application/octet-stream", "$content": base64.b64encode(self.contenido.encode()).decode()}}
        if nombre == "Registrar_bitacora_del_lote":
            if nombre in self.fallos:
                raise FalloConector(*self.fallos[nombre])
            self.bitacoras.append({k[5:]: v for k, v in parametros.items() if k.startswith("item/")})
            return {"body": {"ID": len(self.bitacoras)}, "statusCode": 201}
        if nombre in ("Obtener_clave_preexistente", "Reconsultar_CLAVE_TRANSACCION"):
            match = re.fullmatch(r"CLAVE_TRANSACCION eq '((?:[^']|'')*)'", parametros["$filter"])
            if not match:
                raise ValueError("Filtro OData inválido")
            clave = match[1].replace("''", "'")
            fallo = self.fallos.get((nombre, clave))
            if fallo:
                raise FalloConector(*fallo)
            encontrados = [m for k, m in self.activos.items() if k.casefold() == clave.casefold()]
            if nombre == "Obtener_clave_preexistente":
                self.coincidencias_preconsulta += len(encontrados[:1])
            return {"body": {"value": [self._registro(nombre, clave, m) for m in encontrados[:1]]}, "statusCode": 200}
        if nombre == "Crear_movimiento":
            self.creaciones.append(copy.deepcopy(parametros))
            clave = parametros["item/CLAVE_TRANSACCION"]
            fallo = self.fallos.get((nombre, clave))
            fila = {k[5:]: v for k, v in parametros.items() if k.startswith("item/")}
            if fallo:
                # Timeout con commit remoto o carrera de unicidad.
                if len(fallo) == 3 and fallo[2] == "persistir":
                    self.activos[clave] = fila
                raise FalloConector(*fallo[:2])
            if any(k.casefold() == clave.casefold() for k in self.activos):
                raise FalloConector("Failed", 409)
            self.activos[clave] = fila
            return {"body": {"ID": len(self.activos), **self._registro(nombre, clave, fila)}, "statusCode": 201}
        raise NotImplementedError(nombre)


class EnsayoWDL:
    def __init__(self, definicion, sp, scope_estricto=True):
        self.definicion, self.sp = definicion, sp
        self.variables, self.salidas, self.estados, self.iteraciones = {}, {}, {}, {}
        self.item = None
        self.eventos = []
        self.scope_estricto = scope_estricto
        self.trigger = {"body": {"{FilenameWithExtension}": sp.nombre, "{Identifier}": "identificador-de-prueba", "{IsFolder}": False}}
        self.estado_final = None

    def evaluar(self, valor):
        if isinstance(valor, dict):
            return {k: self.evaluar(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [self.evaluar(v) for v in valor]
        if not isinstance(valor, str) or not valor.startswith("@"):
            return valor
        parser = Expresion(valor[1:])
        nodo = parser.analizar()
        if parser.i != len(parser.tokens):
            raise ValueError(f"Expresión no consumida: {valor}")
        return self._nodo(nodo)

    def _nodo(self, n):
        if n[0] == "literal":
            return n[1]
        if n[0] == "acceso":
            base, clave = self._nodo(n[1]), self._nodo(n[2])
            if base is None and n[3]:
                return None
            if isinstance(base, dict):
                return base.get(clave)
            return base[clave]
        nombre, argumentos = n[1], n[2]
        if nombre == "if":
            return self._nodo(argumentos[1] if self._nodo(argumentos[0]) else argumentos[2])
        args = [self._nodo(a) for a in argumentos]
        funciones = {
            "variables": lambda k: self.variables[k], "outputs": lambda k: self.salidas.get(k),
            "body": lambda k: self.salidas.get(k, {}).get("body"),
            "actions": lambda k: {"status": self.estados.get(k)},
            "triggerBody": lambda: self.trigger["body"], "triggerOutputs": lambda: self.trigger,
            "workflow": lambda: {"run": {"name": "EJECUCION_LOCAL_NO_TENANT"}},
            "parameters": lambda k: {},
            "items": lambda k: self.iteraciones[k], "item": lambda: self.item,
            "utcNow": lambda: "2026-09-30T12:00:00Z", "string": cadena,
            "json": json.loads, "float": float,
            "base64ToString": lambda s: base64.b64decode(s, validate=True).decode("utf-8"),
            "equals": lambda a, b: a == b, "and": lambda *a: all(a), "or": lambda *a: any(a),
            "not": lambda a: not a, "empty": lambda a: a is None or a == "" or a == [] or a == {},
            "coalesce": lambda *a: next((v for v in a if v is not None), None),
            "length": len, "range": lambda inicio, cantidad: list(range(inicio, inicio + cantidad)),
            "add": lambda a, b: a + b, "sub": lambda a, b: a - b, "max": max,
            "greater": lambda a, b: a > b, "less": lambda a, b: a < b,
            "lessOrEquals": lambda a, b: a <= b,
            "contains": lambda a, b: b in a, "startsWith": lambda a, b: a.startswith(b),
            "endsWith": lambda a, b: a.endswith(b), "take": lambda a, b: a[:b],
            "join": lambda a, b: b.join(a), "concat": lambda *a: "".join(map(cadena, a)),
            "replace": lambda a, b, c: a.replace(b, c), "setProperty": lambda d, k, v: {**d, k: v},
        }
        if nombre not in funciones:
            raise NotImplementedError(nombre)
        return funciones[nombre](*args)

    def _marcar_omitidas(self, acciones):
        for nombre, accion in acciones.items():
            self.estados[nombre] = "Skipped"
            self.salidas.pop(nombre, None)
            self._marcar_omitidas(accion.get("actions", {}))
            self._marcar_omitidas(accion.get("else", {}).get("actions", {}))

    def _bloque(self, acciones):
        pendientes = dict(acciones)
        locales = {}
        while pendientes:
            progreso = False
            for nombre, accion in list(pendientes.items()):
                deps = accion.get("runAfter", {})
                if not all(d in locales for d in deps):
                    continue
                progreso = True
                if not all(locales[d] in estados for d, estados in deps.items()):
                    self._marcar_omitidas({nombre: accion})
                    estado = "Skipped"
                else:
                    self.eventos.append(nombre)
                    try:
                        estado = self._accion(nombre, accion)
                    except FalloConector as e:
                        estado = e.estado
                        self.salidas[nombre] = {"statusCode": e.http}
                    except (ValueError, TypeError, KeyError, IndexError, UnicodeDecodeError) as e:
                        estado = "Failed"
                        self.salidas[nombre] = {"error": {"code": type(e).__name__}}
                self.estados[nombre] = locales[nombre] = estado
                pendientes.pop(nombre)
            if not progreso:
                raise AssertionError(f"runAfter inválido/cíclico: {list(pendientes)}")
        if any(s in ("Failed", "TimedOut") for s in locales.values()):
            if self.scope_estricto:
                return "Failed"
            # Fallo manejado si tiene un sucesor ejecutado que lo acepta.
            for nombre, estado in locales.items():
                if estado in ("Failed", "TimedOut") and not any(
                    nombre in a.get("runAfter", {}) and locales[k] == "Succeeded"
                    for k, a in acciones.items()
                ):
                    return "Failed"
        return "Succeeded"

    def _accion_base(self, nombre, accion):
        tipo = accion["type"]
        if tipo == "Scope":
            return self._bloque(accion["actions"])
        if tipo == "If":
            si = self.evaluar(accion["expression"])
            elegido = accion["actions"] if si else accion["else"]["actions"]
            omitido = accion["else"]["actions"] if si else accion["actions"]
            self._marcar_omitidas(omitido)
            return self._bloque(elegido)
        if tipo == "Foreach":
            estados = []
            for valor in self.evaluar(accion["foreach"]):
                self.iteraciones[nombre] = valor
                estados.append(self._bloque(accion["actions"]))
            return "Failed" if "Failed" in estados else "Succeeded"
        inputs = self.evaluar(accion.get("inputs", {}))
        if tipo == "Compose":
            self.salidas[nombre] = inputs
        elif tipo == "InitializeVariable":
            for variable in inputs["variables"]:
                self.variables[variable["name"]] = variable["value"]
        elif tipo == "SetVariable":
            self.variables[inputs["name"]] = inputs["value"]
        elif tipo == "IncrementVariable":
            self.variables[inputs["name"]] += inputs["value"]
        elif tipo == "AppendToArrayVariable":
            self.variables[inputs["name"]].append(inputs["value"])
        elif tipo == "ParseJson":
            validar_esquema(inputs["content"], inputs["schema"])
            self.salidas[nombre] = {"body": inputs["content"]}
        elif tipo == "OpenApiConnection":
            self.salidas[nombre] = self.sp.ejecutar(nombre, inputs["parameters"])
        elif tipo == "Terminate":
            raise Terminado(inputs["runStatus"])
        else:
            raise NotImplementedError(tipo)
        return "Succeeded"

    def ejecutar(self):
        trigger = self.definicion["triggers"]["Cuando_se_crea_un_archivo"]
        if not self.evaluar(trigger["conditions"][0]["expression"]):
            self.estado_final = "NoDisparado"
            return self
        try:
            self.estado_final = self._bloque(self.definicion["actions"])
        except Terminado as t:
            self.estado_final = t.estado
        return self

    def _accion(self, nombre, accion):
        # Query/Select necesitan evaluar item() por elemento, no anticipadamente.
        if accion["type"] in ("Query", "Select"):
            anteriores = self.item
            fuente = self.evaluar(accion["inputs"]["from"])
            salida = []
            for item in fuente:
                self.item = item
                if accion["type"] == "Query":
                    if self.evaluar(accion["inputs"]["where"]):
                        salida.append(item)
                else:
                    salida.append(self.evaluar(accion["inputs"]["select"]))
            self.item = anteriores
            self.salidas[nombre] = {"body": salida}
            return "Succeeded"
        return self._accion_base(nombre, accion)
