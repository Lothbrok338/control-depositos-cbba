# -*- coding: utf-8 -*-
"""
p10/tenant_simulado.py · P10-A.2 · tenant simulado para ejecutar los flujos REALES de P10 con el intérprete local.

Simula, con el comportamiento observable que P10 usa:
  * OneDrive for Business (leer/crear/actualizar archivo por ruta, metadatos, carpetas implícitas) con reloj propio;
  * SharePoint REST: la lista `P10_Control` (columnas tipadas y validadas, índice único, ETag/If-Match, 412), `Depositos_Activos`
    (`lista_simulada.ListaSimulada`, con las escrituras de P9) y el listado de carpetas de PROCESADOS;
  * el servicio p10-api REAL (FastAPI TestClient): el motor de P0 y el generador de A.1 corren de verdad;
  * inyección de fallos técnicos (HTTP 5xx, caída del servicio, caída del ciclo a mitad de camino).
No es SharePoint ni OneDrive: no certifica límites de la plataforma. Sirve para probar la lógica de extremo a extremo.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from . import control_lista as CL
from .ensayo_wdl import FalloAccion, Terminado
from .lista_simulada import ListaSimulada

RX_FILTRO = re.compile(r"^(\w+) eq (?:'((?:[^']|'')*)'|(true|false))$")
RX_FECHAS = re.compile(r"FECHA_MOVIMIENTO ge datetime'([^']+)' and FECHA_MOVIMIENTO lt datetime'([^']+)'")


class SPLista:
    """Lista de SharePoint con columnas tipadas (lo mínimo para validar lo que P10 escribe)."""

    def __init__(self, titulo, entidad=None):
        self.titulo, self.campos, self.items, self._sig = titulo, {"Title": {"tipo": "Text", "max": 255, "requerido": True}}, [], 1
        self.indexados, self.unicos = set(), set()

    def validar(self, valores):
        for k, v in valores.items():
            if k == "__metadata":
                continue
            if k not in self.campos:
                raise FalloAccion("BadRequest", f"columna inexistente en {self.titulo}: {k}", 400)
            c = self.campos[k]
            if v is None:
                continue
            if c["tipo"] == "Number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
                raise FalloAccion("BadRequest", f"{k} es Number y recibió {type(v).__name__}", 400)
            if c["tipo"] in ("Text", "Note") and not isinstance(v, str):
                raise FalloAccion("BadRequest", f"{k} es texto y recibió {type(v).__name__}", 400)
            if c["tipo"] == "Text" and len(v) > c.get("max", 255):
                raise FalloAccion("BadRequest", f"{k} excede {c.get('max', 255)} caracteres", 400)

    def crear(self, valores):
        self.validar(valores)
        for u in self.unicos:
            if valores.get(u) not in (None, "") and any(i.get(u) == valores[u] for i in self.items):
                raise FalloAccion("DuplicateValue", f"valor duplicado en {u}", 400)
        it = {"Id": self._sig, "__etag": 1, **{k: v for k, v in valores.items() if k != "__metadata"}}
        self._sig += 1
        self.items.append(it)
        return it

    def actualizar(self, id_, valores, if_match):
        it = next((i for i in self.items if i["Id"] == id_), None)
        if it is None:
            raise FalloAccion("ItemNotFound", "elemento inexistente", 404)
        if if_match not in (None, "*") and if_match != f'"{it["__etag"]}"':
            raise FalloAccion("PreconditionFailed", "ETag distinto", 412)
        self.validar(valores)
        for u in self.unicos:
            if u in valores and valores[u] not in (None, "") and any(o is not it and o.get(u) == valores[u] for o in self.items):
                raise FalloAccion("DuplicateValue", f"valor duplicado en {u}", 400)
        it.update({k: v for k, v in valores.items() if k != "__metadata"})
        it["__etag"] += 1
        return it

    def como_rest(self, it, verbose):
        out = {k: copy.deepcopy(v) for k, v in it.items() if not k.startswith("__")}
        for c in self.campos:
            out.setdefault(c, None)
        if verbose:
            out["__metadata"] = {"etag": f'"{it["__etag"]}"'}
        return out


class TenantSimulado:
    def __init__(self, app, token="t" * 24, inicio_utc="2026-10-08T14:00:00", sitio="/personal/gtorricot_univalle_edu"):
        self.reloj = datetime.fromisoformat(inicio_utc).replace(tzinfo=timezone.utc)
        self.sitio, self.prefijo = sitio, sitio + "/Documents"
        self.archivos = {}                  # ruta OneDrive -> {"id","contenido","creado"}
        self._id_archivo = 1
        self.listas = {}                    # título -> SPLista
        self.depositos = ListaSimulada(self._local().isoformat())
        self.guid_depositos = None
        self.cliente = TestClient(app)
        self.token = token
        self.fallos = []                    # [{"op","contiene","veces","http"}]
        self.caida = None                   # {"op","contiene","despues_de"}: la ejecución muere sin liberar nada
        self.registro = []                  # (operación, detalle) de cada llamada
        self.api_llamadas = []
        self.archivar_token()

    # ---- reloj
    def _local(self):
        return (self.reloj + timedelta(hours=-4)).replace(tzinfo=None)

    def ahora_utc(self):
        return self.reloj

    def avanzar(self, **kw):
        self.reloj += timedelta(**kw)
        self.depositos.reloj = self._local()

    def poner_hora_local(self, iso_local):
        self.reloj = datetime.fromisoformat(iso_local).replace(tzinfo=timezone.utc) + timedelta(hours=4)
        self.depositos.reloj = self._local()

    # ---- OneDrive
    def archivar_token(self):
        self.escribir_archivo("/CONTROL_DEPOSITOS/P10_CONFIG/P10_API_TOKEN.txt", self.token.encode())

    def escribir_archivo(self, ruta, contenido):
        if ruta in self.archivos:
            self.archivos[ruta]["contenido"] = contenido
        else:
            self.archivos[ruta] = {"id": f"id{self._id_archivo}", "contenido": contenido, "creado": self.reloj}
            self._id_archivo += 1

    def soltar_en_procesados(self, nombre, contenido, anio, mes_carpeta, dia):
        ruta = f"/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS/{anio}/{mes_carpeta}/{dia}/{nombre}"
        self.escribir_archivo(ruta, contenido)
        return ruta

    def _por_id(self, id_):
        return next((r for r, a in self.archivos.items() if a["id"] == id_), None)

    # ---- fallos
    def fallar(self, op, contiene="", veces=1, http=500):
        self.fallos.append({"op": op, "contiene": contiene, "veces": veces, "http": http})

    def _revisar_fallos(self, op, detalle):
        for f in self.fallos:
            if f["veces"] > 0 and f["op"] == op and f["contiene"] in detalle:
                f["veces"] -= 1
                raise FalloAccion("InjectedFailure", f"fallo inyectado en {op}", f["http"])
        if self.caida and self.caida["op"] == op and self.caida["contiene"] in detalle:
            if self.caida.get("despues_de", 0) <= 0:
                self.caida = None
                raise Terminado("Cancelled", "CAIDA", "la ejecución murió")
            self.caida["despues_de"] -= 1

    # ---- despacho de acciones
    def ejecutar(self, nombre, tipo, ent, accion):
        if tipo == "Http":
            return self._http(ent)
        op = accion["inputs"]["host"]["operationId"]
        p = ent["parameters"]
        if op == "HttpRequest":
            return self._sharepoint(p)
        return self._onedrive(op, p)

    # ---- servicio p10-api real
    def _http(self, ent):
        uri = ent["uri"]
        if "<PEGAR" in uri:
            raise FalloAccion("InvalidUri", "falta pegar el dominio de Railway", 0)
        ruta = urllib.parse.urlparse(uri).path
        self._revisar_fallos("api", ruta)
        self.api_llamadas.append(ruta)
        r = self.cliente.post(ruta, json=ent["body"], headers=ent["headers"])
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = None
        if r.status_code >= 400:
            raise FalloAccion("HttpError", f"HTTP {r.status_code}", r.status_code)
        return {"statusCode": r.status_code, "headers": dict(r.headers), "body": cuerpo}

    # ---- OneDrive
    def _onedrive(self, op, p):
        if op == "UpdateFile":
            detalle = self._por_id(p["id"]) or str(p["id"])
        elif op == "CreateFile":
            detalle = p["folderPath"].rstrip("/") + "/" + p["name"]
        else:
            detalle = p["path"]
        self._revisar_fallos(op, detalle)
        self.registro.append((op, detalle))
        if op == "GetFileContentByPath":
            a = self.archivos.get(p["path"])
            if a is None:
                raise FalloAccion("ItemNotFound", "no existe", 404)
            return {"statusCode": 200, "body": {"$content-type": "application/octet-stream", "$content": base64.b64encode(a["contenido"]).decode()}}
        if op == "GetFileMetadataByPath":
            a = self.archivos.get(p["path"])
            if a is None:
                raise FalloAccion("ItemNotFound", "no existe", 404)
            return {"statusCode": 200, "body": {"Id": a["id"], "Size": len(a["contenido"]), "Name": p["path"].rsplit("/", 1)[-1]}}
        if op == "CreateFile":
            ruta = p["folderPath"].rstrip("/") + "/" + p["name"]
            if ruta in self.archivos:
                raise FalloAccion("Conflict", "el archivo ya existe", 409)
            self.escribir_archivo(ruta, base64.b64decode(p["body"]["$content"]))
            return {"statusCode": 201, "body": {"Id": self.archivos[ruta]["id"], "Name": p["name"]}}
        if op == "UpdateFile":
            ruta = self._por_id(p["id"])
            if ruta is None:
                raise FalloAccion("ItemNotFound", "no existe", 404)
            self.archivos[ruta]["contenido"] = base64.b64decode(p["body"]["$content"])
            return {"statusCode": 200, "body": {"Id": p["id"]}}
        raise NotImplementedError(op)

    # ---- SharePoint REST
    def _sharepoint(self, p):
        metodo, uri, cab = p["parameters/method"], p["parameters/uri"], p.get("parameters/headers", {})
        cuerpo = p.get("parameters/body")
        u = urllib.parse.urlparse(uri)
        ruta, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        self._revisar_fallos("HttpRequest", ruta + "?" + u.query)
        self.registro.append(("HttpRequest:" + metodo, ruta))
        verbose = "odata=verbose" in cab.get("Accept", "")
        efectivo = cab.get("X-HTTP-Method") or metodo
        if isinstance(cuerpo, str):
            try:
                cuerpo = json.loads(cuerpo)
            except ValueError:
                raise FalloAccion("BadRequest", "cuerpo no es JSON", 400)
        m = re.fullmatch(r"_api/web/lists/getbytitle\('([^']+)'\)(/.*)?", ruta)
        if m:
            return self._lista_titulo(m.group(1), m.group(2) or "", efectivo, q, cab, cuerpo, verbose)
        m = re.fullmatch(r"_api/web/lists\(guid'([^']+)'\)/items", ruta)
        if m:
            return self._depositos(q, verbose)
        m = re.fullmatch(r"_api/web/GetFolderByServerRelativeUrl\('([^']*)'\)/Folders", ruta)
        if m:
            return self._carpetas(m.group(1))
        if ruta == "_api/web/lists":
            return self._listas(efectivo, q, cuerpo)
        raise FalloAccion("NotFound", f"endpoint no simulado: {ruta}", 404)

    @staticmethod
    def _respuesta(items, verbose, mas=False, status=200):
        if verbose:
            d = {"results": items}
            if mas:
                d["__next"] = "https://siguiente"
            return {"statusCode": status, "body": {"d": d}}
        out = {"value": items}
        if mas:
            out["odata.nextLink"] = "https://siguiente"
        return {"statusCode": status, "body": out}

    @staticmethod
    def _filtro_eq(texto):
        m = RX_FILTRO.match(texto or "")
        if not m:
            return None
        return m.group(1), (m.group(2).replace("''", "'") if m.group(2) is not None else (m.group(3) == "true"))

    def _listas(self, metodo, q, cuerpo):
        if metodo == "GET":
            f = self._filtro_eq(q.get("$filter"))
            sel = [{"Id": "guid-" + t, "Title": t} for t in self.listas if not f or t == f[1]]
            return self._respuesta(sel, False)
        if metodo == "POST":
            t = cuerpo["Title"]
            if t in self.listas:
                raise FalloAccion("Conflict", "la lista ya existe", 409)
            self.listas[t] = SPLista(t)
            return {"statusCode": 201, "body": {"Id": "guid-" + t}}
        raise FalloAccion("NotFound", "método no simulado", 404)

    def _lista_titulo(self, titulo, resto, metodo, q, cab, cuerpo, verbose):
        lista = self.listas.get(titulo)
        if lista is None:
            raise FalloAccion("ListNotFound", f"no existe la lista {titulo}", 404)
        m = re.fullmatch(r"/items(?:\((\d+)\))?", resto)
        if m:
            if m.group(1) is None and metodo == "GET":
                f = self._filtro_eq(q.get("$filter"))
                its = [i for i in lista.items if not f or i.get(f[0]) == f[1]]
                top = int(q.get("$top", 100))
                return self._respuesta([lista.como_rest(i, verbose) for i in its[:top]], verbose, mas=len(its) > top)
            if m.group(1) is None and metodo == "POST":
                it = lista.crear(cuerpo)
                return {"statusCode": 201, "body": lista.como_rest(it, False)}
            if m.group(1) and metodo == "MERGE":
                lista.actualizar(int(m.group(1)), cuerpo, cab.get("IF-MATCH"))
                return {"statusCode": 204, "body": None}
        if resto == "/fields" and metodo == "GET":
            f = self._filtro_eq(q.get("$filter"))
            campos = [{"InternalName": k, "Indexed": k in lista.indexados, "EnforceUniqueValues": k in lista.unicos} for k in lista.campos]
            if f and f[0] == "InternalName":
                campos = [c for c in campos if c["InternalName"] == f[1]]
            return self._respuesta(campos, False)
        if resto == "/fields/createfieldasxml" and metodo == "POST":
            xml = cuerpo["parameters"]["SchemaXml"]
            nombre = re.search(r' Name="([^"]+)"', xml).group(1)
            tipo = re.search(r'Type="([^"]+)"', xml).group(1)
            mx = re.search(r'MaxLength="(\d+)"', xml)
            if nombre in lista.campos:
                raise FalloAccion("Conflict", "la columna ya existe", 409)
            lista.campos[nombre] = {"tipo": tipo, "max": int(mx.group(1)) if mx else None}
            return {"statusCode": 200, "body": {"InternalName": nombre}}
        m = re.fullmatch(r"/fields/getbyinternalnameortitle\('([^']+)'\)", resto)
        if m and metodo == "MERGE":
            n = m.group(1)
            if n not in lista.campos:
                raise FalloAccion("NotFound", "columna inexistente", 404)
            if cuerpo.get("Indexed"):
                lista.indexados.add(n)
            if cuerpo.get("EnforceUniqueValues"):
                if n not in lista.indexados:
                    raise FalloAccion("BadRequest", "la unicidad exige columna indexada", 400)
                lista.unicos.add(n)
            if cuerpo.get("Required") is False:
                lista.campos[n]["requerido"] = False
            return {"statusCode": 204, "body": None}
        raise FalloAccion("NotFound", f"endpoint de lista no simulado: {resto}", 404)

    def _depositos(self, q, verbose):
        f = q.get("$filter", "")
        m = RX_FECHAS.fullmatch(f)
        if not m:
            raise FalloAccion("BadRequest", "filtro no soportado", 400)
        orden_modificado = q.get("$orderby", "").startswith("Modified")
        top = int(q.get("$top", 100))
        sel = [i for i in self.depositos.items.values() if m.group(1) <= i["FECHA_MOVIMIENTO"] < m.group(2)]
        sel.sort(key=(lambda i: (i["Modified"], i["Id"])) if orden_modificado else (lambda i: i["Id"]), reverse=orden_modificado)
        campos = set(q["$select"].split(",")) if "$select" in q else None
        out = [self.depositos.elemento(i, campos) for i in sel[:top]]
        for o in out:
            o.pop("__metadata", None)
        return self._respuesta(out, verbose, mas=len(sel) > top)

    def _carpetas(self, ruta_servidor):
        base = ruta_servidor[len(self.prefijo):].rstrip("/") + "/"
        dias = {}
        for ruta, a in self.archivos.items():
            if ruta.startswith(base):
                resto = ruta[len(base):]
                if "/" in resto:
                    dia, nombre = resto.split("/", 1)
                    dias.setdefault(dia, []).append({
                        "Name": nombre, "ServerRelativeUrl": self.prefijo + ruta, "Length": str(len(a["contenido"])),
                        "TimeCreated": a["creado"].strftime("%Y-%m-%dT%H:%M:%SZ")})
        if not dias:
            raise FalloAccion("FolderNotFound", "la carpeta no existe", 404)
        return self._respuesta([{"Name": d, "Files": fs} for d, fs in sorted(dias.items())], False)
