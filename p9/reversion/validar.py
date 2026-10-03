"""Validación estática de los artefactos nuevos; no certifica el runtime M365.

Analiza exclusivamente definiciones/paquetes recibidos, nunca referencia/ ni
fixtures. Los UUID de recursos de importación son válidos en el sobre ZIP;
ningún GUID literal del tenant está permitido dentro del WDL generado.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from uuid import UUID

from . import contrato as C

GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
CONEXIONES = {"shared_sharepointonline": "Embedded", "shared_office365users": "Invoker", "shared_approvals": "Embedded"}
FUNCIONES = set("actions add addDays addHours addMinutes and array base64 body coalesce concat contains createArray div empty encodeUriComponent endsWith equals first float formatDateTime greater greaterOrEquals guid if int item items json last length less lessOrEquals max min mod mul not or outputs parameters replace result setProperty skip split startsWith string sub substring take ticks toLower toUpper triggerBody triggerOutputs trim union uriComponent utcNow variables workflow xml xpath".lower().split())
TOKEN = re.compile(r"\s*(?P<t>'(?:''|[^'])*'|-?\d+(?:\.\d+)?|[A-Za-z_$][\w$]*|\?\[|[(),\[\]])")


class Expresion:
    """Parser pequeño con consumo completo; no omite caracteres desconocidos."""
    def __init__(self, texto):
        self.tokens, self.i = [], 0
        pos = 0
        while pos < len(texto):
            if not texto[pos:].strip():
                break
            match = TOKEN.match(texto, pos)
            if not match:
                raise ValueError(f"Token WDL inválido cerca de {texto[pos:pos+30]!r}")
            self.tokens.append(match.group("t"))
            pos = match.end()

    def tomar(self, esperado=None):
        if self.i >= len(self.tokens):
            raise ValueError("Expresión WDL incompleta")
        token = self.tokens[self.i]
        self.i += 1
        if esperado is not None and token != esperado:
            raise ValueError(f"Se esperaba {esperado!r}, se encontró {token!r}")
        return token

    def nodo(self):
        token = self.tomar()
        if token.startswith("'"):
            out = ("literal", token[1:-1].replace("''", "'"))
        elif token in ("true", "false", "null") or re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            out = ("literal", token)
        else:
            if token.lower() not in FUNCIONES:
                raise ValueError(f"Función WDL desconocida: {token}")
            self.tomar("(")
            args = []
            if self.i >= len(self.tokens):
                raise ValueError("Función sin cierre")
            if self.tokens[self.i] != ")":
                args.append(self.nodo())
                while self.i < len(self.tokens) and self.tokens[self.i] == ",":
                    self.tomar(",")
                    args.append(self.nodo())
            self.tomar(")")
            out = ("funcion", token.lower(), args)
        while self.i < len(self.tokens) and self.tokens[self.i] in ("[", "?["):
            self.tomar()
            key = self.nodo()
            self.tomar("]")
            out = ("acceso", out, key)
        return out

    def analizar(self):
        out = self.nodo()
        if self.i != len(self.tokens):
            raise ValueError("Contenido después del final de la expresión")
        return out


def cadenas(valor):
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for dato in valor.values():
            yield from cadenas(dato)
    elif isinstance(valor, list):
        for dato in valor:
            yield from cadenas(dato)


def expresiones(valor):
    for texto in cadenas(valor):
        if texto.startswith("@@"):
            continue
        if texto.startswith("@{") and texto.endswith("}"):
            yield texto[2:-1]
        elif texto.startswith("@"):
            yield texto[1:]
        elif "@{" in texto:
            # Los builders actuales no interpolan expresiones dentro de texto.
            # No se admite omitir su análisis si en el futuro se introduce una.
            raise ValueError("Interpolación embebida no analizada; usar una expresión concat completa")


def funciones(ast):
    if ast[0] == "funcion":
        yield ast[1], ast[2]
        for arg in ast[2]:
            yield from funciones(arg)
    elif ast[0] == "acceso":
        yield from funciones(ast[1])
        yield from funciones(ast[2])


def _fallar(errores):
    if errores:
        raise ValueError("Artefacto de reversión inválido:\n- " + "\n- ".join(errores))


def validar_definicion(definicion, nombre=None):
    errores, nodos, bloques, variables, profundidades = [], {}, {}, {}, []

    def registrar(acciones, ruta=(), ancestros_bucle=()):
        bloques[ruta] = acciones
        for accion, nodo in acciones.items():
            path = ruta + (accion,)
            profundidad = len([p for p in path if p not in ("actions", "else", "default") and not p.startswith("case:")])
            profundidades.append(profundidad)
            if accion in nodos:
                errores.append(f"Nombre de acción repetido: {accion}")
            nodos[accion] = (path, nodo, ancestros_bucle)
            if profundidad > 8:
                errores.append(f"Profundidad > 8: {accion} ({profundidad})")
            desconocidas = set(nodo.get("runAfter", {})) - set(acciones)
            if desconocidas:
                errores.append(f"runAfter inexistente/fuera de bloque en {accion}: {sorted(desconocidas)}")
            if accion in nodo.get("runAfter", {}):
                errores.append(f"runAfter circular en {accion}")
            if nodo.get("type") == "Terminate" and ancestros_bucle:
                errores.append(f"Terminate dentro de bucle: {accion}")
            if nodo.get("type") == "InitializeVariable":
                if ruta:
                    errores.append(f"InitializeVariable fuera del nivel raíz: {accion}")
                for var in nodo.get("inputs", {}).get("variables", []):
                    if var["name"] in variables:
                        errores.append(f"Variable inicializada más de una vez: {var['name']}")
                    variables[var["name"]] = accion
            bucles = ancestros_bucle + ((accion,) if nodo.get("type") in ("Until", "Foreach") else ())
            registrar(nodo.get("actions", {}), path + ("actions",), bucles)
            registrar(nodo.get("else", {}).get("actions", {}), path + ("else",), bucles)
            for clave, caso in nodo.get("cases", {}).items():
                registrar(caso.get("actions", {}), path + ("case:" + clave,), bucles)
            registrar(nodo.get("default", {}).get("actions", {}), path + ("default",), bucles)

    registrar(definicion.get("actions", {}))
    if len(nodos) > 500:
        errores.append(f"Más de 500 acciones: {len(nodos)}")
    if len(variables) > 250:
        errores.append(f"Más de 250 variables: {len(variables)}")

    def depende(acciones, desde, hasta, vistos=None):
        if desde == hasta:
            return True
        vistos = set() if vistos is None else vistos
        if desde not in acciones or desde in vistos:
            return False
        return any(depende(acciones, dep, hasta, vistos | {desde}) for dep in acciones[desde].get("runAfter", {}))

    def referencia_ordenada(origen, destino):
        if origen == destino:
            return False
        ruta_a, ruta_b = nodos[origen][0], nodos[destino][0]
        i = 0
        while i < min(len(ruta_a), len(ruta_b)) and ruta_a[i] == ruta_b[i]:
            i += 1
        comun = ruta_a[:i]
        # No se puede leer una acción que todavía ejecuta a su padre/hijo.
        if i >= min(len(ruta_a), len(ruta_b)) or comun not in bloques:
            return False
        return depende(bloques[comun], ruta_a[i], ruta_b[i])

    # Detectar ciclos indirectos incluso cuando ninguna expresión los referencia.
    for bloque in bloques.values():
        for accion, nodo in bloque.items():
            if any(depende(bloque, dep, accion) for dep in nodo.get("runAfter", {})):
                errores.append(f"Ciclo de runAfter: {accion}")

    for accion, (_, nodo, bucles) in nodos.items():
        propio = {k: v for k, v in nodo.items() if k not in ("actions", "else", "cases", "default", "runAfter")}
        try:
            for texto in expresiones(propio):
                if len(texto) > 8192:
                    errores.append(f"Expresión de más de 8192 caracteres en {accion}")
                for funcion, args in funciones(Expresion(texto).analizar()):
                    if funcion not in ("outputs", "body", "actions", "result", "variables", "parameters", "items"):
                        continue
                    if len(args) != 1 or args[0][0] != "literal":
                        errores.append(f"Referencia dinámica/no literal en {accion}: {funcion}")
                        continue
                    objetivo = args[0][1]
                    if funcion in ("outputs", "body", "actions", "result"):
                        if objetivo not in nodos:
                            errores.append(f"Referencia inexistente en {accion}: {objetivo}")
                        elif not referencia_ordenada(accion, objetivo):
                            errores.append(f"Referencia futura/paralela sin dependencia en {accion}: {objetivo}")
                    elif funcion == "variables":
                        if objetivo not in variables:
                            errores.append(f"Variable no inicializada en {accion}: {objetivo}")
                        elif not referencia_ordenada(accion, variables[objetivo]):
                            errores.append(f"Variable usada antes de inicializar en {accion}: {objetivo}")
                        if nodo.get("type") == "SetVariable" and objetivo == nodo.get("inputs", {}).get("name"):
                            errores.append(f"SetVariable usa su propia variable en {accion}: {objetivo}")
                    elif funcion == "parameters" and objetivo not in definicion.get("parameters", {}):
                        errores.append(f"Parámetro inexistente en {accion}: {objetivo}")
                    elif funcion == "items" and objetivo not in bucles:
                        errores.append(f"items fuera de su bucle en {accion}: {objetivo}")
        except ValueError as error:
            errores.append(f"Expresión inválida en {accion}: {error}")
        if nodo.get("type") in ("SetVariable", "IncrementVariable", "DecrementVariable", "AppendToArrayVariable", "AppendToStringVariable"):
            variable = nodo.get("inputs", {}).get("name")
            if variable not in variables:
                errores.append(f"Escritura de variable no inicializada en {accion}: {variable}")

    conexiones = set()
    for accion, nodo in [(n, v[1]) for n, v in nodos.items()] + list(definicion.get("triggers", {}).items()):
        if accion in definicion.get("triggers", {}):
            try:
                for texto in expresiones(nodo):
                    for funcion, args in funciones(Expresion(texto).analizar()):
                        if funcion == "parameters" and (len(args) != 1 or args[0][0] != "literal" or args[0][1] not in definicion.get("parameters", {})):
                            errores.append(f"Parámetro inexistente/dinámico en trigger {accion}")
                        if funcion in ("body", "outputs", "actions", "variables", "result", "items"):
                            errores.append(f"Trigger referencia estado de acciones en {accion}: {funcion}")
            except ValueError as error:
                errores.append(f"Expresión inválida en trigger {accion}: {error}")
        if nodo.get("type", "").startswith("OpenApiConnection"):
            host = nodo.get("inputs", {}).get("host", {})
            conexion = host.get("connectionName")
            conexiones.add(conexion)
            if conexion not in CONEXIONES or host.get("apiId") != "/providers/Microsoft.PowerApps/apis/" + str(conexion):
                errores.append(f"Conexión antigua/no autorizada o API incorrecta en {accion}")
            if conexion == "shared_office365users" and host.get("operationId") != "MyProfile_V2":
                errores.append(f"Identidad debe obtenerse con MyProfile_V2 en {accion}")
            if conexion == "shared_sharepointonline":
                if host.get("operationId") not in ("HttpRequest", "GetOnNewItems"):
                    errores.append(f"Escritura/operación SharePoint fuera del contrato en {accion}")
                params = nodo.get("inputs", {}).get("parameters", {})
                headers = {k.lower(): v for k, v in params.get("parameters/headers", {}).items()}
                url = params.get("parameters/uri", "")
                method = str(params.get("parameters/method", "GET")).upper()
                merge = str(headers.get("x-http-method", "")).upper() == "MERGE" or method in ("PATCH", "MERGE")
                if "*" in str(headers.get("if-match", "")):
                    errores.append(f"If-Match comodín en {accion}")
                if merge and "/fields" not in url.lower():
                    if not isinstance(headers.get("if-match"), str) or not headers["if-match"].startswith("@"):
                        errores.append(f"MERGE sin ETag concreto dinámico en {accion}")
                if method != "GET" and nodo.get("inputs", {}).get("retryPolicy") != {"type": "none"}:
                    errores.append(f"Escritura con reintento automático en {accion}")
                body = params.get("parameters/body")
                deposito = merge and ("GUID_DEPOSITOS" in url or accion.endswith("MERGE_DEPOSITO"))
                if method != "GET" and "GUID_DEPOSITOS" in url and not merge:
                    errores.append(f"Escritura de depósito sin MERGE protegido en {accion}")
                if isinstance(body, dict) and "ULTIMA_REVERSION_ID" in body and not deposito:
                    errores.append(f"Marcador escrito fuera del MERGE autoritativo en {accion}")
                if deposito:
                    if "ETAG_SOLICITUD" not in str(headers.get("if-match", "")):
                        errores.append(f"MERGE depósito no conserva el ETag original en {accion}")
                    if not isinstance(body, dict) or set(body) != set(C.CAMPOS_ESCRITOS):
                        errores.append(f"MERGE depósito no tiene los nueve campos exactos en {accion}")
                    elif body.get("ESTADO_ASIGNACION") != "DISPONIBLE" or any(body[c] is not None for c in C.CAMPOS_LIMPIAR):
                        errores.append(f"Limpieza/estado incorrectos en {accion}")
                    if not isinstance(body, dict) or "SOLICITUD_UID" not in str(body.get("ULTIMA_REVERSION_ID")):
                        errores.append(f"Marcador de reversión no vinculado al UID en {accion}")
                if re.search(r"\$top\s*=\s*1(?:[&'\"\s)]|$)", url, re.I) and re.search(r"CODIGO_ASIGNACION|asignacion", url, re.I):
                    errores.append(f"Búsqueda top=1 por código de asignación en {accion}")
    serialized = json.dumps(definicion, ensure_ascii=False)
    if GUID.search(serialized):
        errores.append("GUID literal de tenant dentro de la definición")
    if re.search(r"\bCOCHABAMBA\b", serialized, re.I):
        errores.append("Sede COCHABAMBA hardcodeada")
    for titulo in re.findall(r"getbytitle\('([^']+)'\)", serialized, re.I):
        if titulo not in (C.LISTA_DEPOSITOS, C.LISTA_REVERSIONES):
            errores.append(f"Referencia a lista antigua/no autorizada: {titulo}")
    _fallar(errores)
    return {"flujo": nombre, "acciones": len(nodos), "profundidad": max(profundidades, default=0),
            "variables": len(variables), "conexiones": sorted(conexiones), "resultado": "OK"}


def validar_paquete(archivos_o_zip, nombre=None):
    if isinstance(archivos_o_zip, (str, Path)):
        with zipfile.ZipFile(archivos_o_zip) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP corrupto")
            archivos = {n: json.loads(archive.read(n)) for n in archive.namelist()}
    else:
        archivos = archivos_o_zip
    errores = []
    if len(archivos) != 5:
        errores.append("Paquete debe contener cinco JSON")
    definition_paths = [p for p in archivos if p.endswith("/definition.json")]
    if len(definition_paths) != 1:
        raise ValueError("Se requiere exactamente un definition.json")
    path = definition_paths[0]
    base = path.rsplit("/", 1)[0]
    wrapper = archivos[path]
    props = wrapper["properties"]
    resumen = validar_definicion(props["definition"], nombre or props.get("displayName"))
    manifest = archivos.get("manifest.json", {})
    resources = manifest.get("resources", {})
    flows = {k: v for k, v in resources.items() if v.get("type") == "Microsoft.Flow/flows"}
    if len(flows) != 1:
        errores.append("Manifest requiere un recurso de flujo")
    for identificador in resources:
        try:
            UUID(identificador)
        except ValueError:
            errores.append("ID de recurso ZIP inválido")
    flow = next(iter(flows), "")
    if flow != base.rsplit("/", 1)[-1] or archivos.get("Microsoft.Flow/flows/manifest.json", {}).get("flowAssets", {}).get("assetPaths") != [flow]:
        errores.append("Rutas de recurso/flowAssets inconsistentes")
    refs = props.get("connectionReferences", {})
    apis = archivos.get(base + "/apisMap.json", {})
    conns = archivos.get(base + "/connectionsMap.json", {})
    if set(refs) != set(resumen["conexiones"]) or set(apis) != set(refs) or set(conns) != set(refs):
        errores.append("Mapas y conexiones usadas no coinciden")
    if set(resources) != {flow} | set(apis.values()) | set(conns.values()):
        errores.append("Recursos adicionales/no mapeados en el paquete")
    try:
        UUID(wrapper["name"])
    except (ValueError, KeyError):
        errores.append("ID interno de flujo inválido")
    if wrapper.get("id") != "/providers/Microsoft.Flow/flows/" + str(wrapper.get("name")):
        errores.append("ID y nombre interno del flujo inconsistentes")
    for key, ref in refs.items():
        if key not in CONEXIONES or ref.get("source") != CONEXIONES.get(key):
            errores.append(f"Origen de conexión incorrecto para {key}; Users debe ser Invoker")
        if ref.get("id") != "/providers/Microsoft.PowerApps/apis/" + key or ref.get("connectionName") != f"<CONEXION_{key.upper()}>":
            errores.append(f"Conexión real/antigua o API no mapeada para {key}")
        if resources.get(apis.get(key), {}).get("id") != ref.get("id"):
            errores.append(f"Recurso de API incorrecto para {key}")
        conn = resources.get(conns.get(key), {})
        if conn.get("type") != "Microsoft.PowerApps/apis/connections" or conn.get("dependsOn") != [apis.get(key)]:
            errores.append(f"Dependencia de conexión incorrecta para {key}")
    if flows and set(flows[flow].get("dependsOn", [])) != set(apis.values()) | set(conns.values()):
        errores.append("Dependencias del flujo incompletas")
    if nombre and (props.get("displayName") != nombre or manifest.get("details", {}).get("displayName") != nombre):
        errores.append("Nombre del paquete no coincide")
    _fallar(errores)
    return {**resumen, "archivos_zip": len(archivos)}
