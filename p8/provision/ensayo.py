"""Ejecuta el WDL generado con REST simulado; no certifica Microsoft 365."""
from __future__ import annotations

import copy
import json
import re
import uuid
from xml.etree import ElementTree as ET

from p8.ensayo_wdl import EnsayoWDL, FalloConector, Terminado


class EnsayoProvision(EnsayoWDL):
    def __init__(self, definicion, sp):
        super().__init__(definicion, sp)
        self.trigger = {"body": {"text": "https://example.invalid/sites/piloto"}}

    def _nodo(self, n):
        if n[0] == "funcion" and n[1] in ("trim", "toLower", "first", "xml", "xpath"):
            args = [self._nodo(a) for a in n[2]]
            if n[1] == "trim":
                return args[0].strip()
            if n[1] == "toLower":
                return args[0].lower()
            if n[1] == "first":
                return args[0][0]
            if n[1] == "xml":
                try:
                    return ET.fromstring(args[0])
                except ET.ParseError as e:
                    raise ValueError("SchemaXml inválido") from e
            root, path = args
            if path == "/Field/CHOICES/CHOICE/text()":
                return [e.text or "" for e in root.findall("./CHOICES/CHOICE")]
            match = re.fullmatch(r"string\(/Field/@([A-Za-z]+)\)", path)
            if not match:
                raise NotImplementedError(path)
            return root.attrib.get(match[1], "")
        return super()._nodo(n)

    def ejecutar(self):
        try:
            self.estado_final = self._bloque(self.definicion["actions"])
        except Terminado as t:
            self.estado_final = t.estado
        return self


class SharePointREST:
    """Modelo de REST de listas/campos, con conservación de elementos existentes."""
    nombre = "PRUEBA_LOCAL"

    def __init__(self):
        self.listas = {}
        self.llamadas = []
        self.fallos = {}
        self.al_verificar = None
        # Inyectar respuestas reales o incompatibles en pruebas de verificación.
        self.al_crear = None
        self.paginar = set()

    def _campo_xml(self, schema, base=False):
        e = ET.fromstring(schema)
        identificador = uuid.UUID(e.get("ID")) if e.get("ID") else uuid.uuid5(uuid.NAMESPACE_DNS, schema)
        return {"Id": str(identificador), "InternalName": e.get("Name"),
                "Title": e.get("DisplayName", e.get("Name")), "TypeAsString": e.get("Type"),
                "Required": e.get("Required", "FALSE").upper() == "TRUE",
                "Indexed": e.get("Indexed", "FALSE").upper() == "TRUE", "EnforceUniqueValues": False,
                "DefaultValue": e.findtext("Default"), "Hidden": e.get("Hidden", "FALSE").upper() == "TRUE",
                "ReadOnlyField": False, "FromBaseType": base, "SchemaXml": schema}

    def nueva_lista(self, nombre):
        self.listas[nombre] = {
            "meta": {"Title": nombre, "BaseTemplate": 100, "ContentTypesEnabled": False, "Hidden": False},
            "fields": {"Title": self._campo_xml('<Field Name="Title" Type="Text" Required="TRUE" />', base=True)},
            "items": [],
        }
        return self.listas[nombre]

    def ejecutar(self, nombre, parametros):
        assert parametros["parameters/headers"]["Accept"] == "application/json;odata=nometadata"
        metodo, uri = parametros["parameters/method"], parametros["parameters/uri"]
        assert metodo in ("GET", "POST")
        self.llamadas.append({"accion": nombre, "metodo": metodo, "uri": uri,
                              "body": json.loads(parametros["parameters/body"]) if "parameters/body" in parametros else None})
        actual = self.llamadas[-1]
        if nombre in self.fallos:
            raise FalloConector(*self.fallos[nombre])
        if metodo == "GET" and uri.startswith("_api/web/lists?"):
            titulo = re.search(r"Title eq '([^']+)'", uri)[1]
            return {"statusCode": 200, "body": {"value": [copy.deepcopy(l["meta"]) for n, l in self.listas.items() if n == titulo]}}
        if metodo == "POST" and uri == "_api/web/lists":
            p = actual["body"]
            assert p["BaseTemplate"] == 100 and p["ContentTypesEnabled"] is False
            if p["Title"] in self.listas:
                raise FalloConector("Failed", 409)
            lista = self.nueva_lista(p["Title"])
            return {"statusCode": 201, "body": copy.deepcopy(lista["meta"])}
        m = re.fullmatch(r"_api/web/lists/getbytitle\('([^']+)'\)(.*)", uri)
        if not m:
            raise ValueError("Endpoint inesperado " + uri)
        titulo, ruta = m.groups()
        if titulo not in self.listas:
            raise FalloConector("Failed", 404)
        lista = self.listas[titulo]
        if nombre == "Leer_lista_final" and self.al_verificar:
            self.al_verificar(titulo, lista)
        if metodo == "GET" and ruta.startswith("?$select="):
            return {"statusCode": 200, "body": copy.deepcopy(lista["meta"])}
        if metodo == "GET" and ruta.startswith("/fields?$select="):
            body = {"value": copy.deepcopy(list(lista["fields"].values()))}
            if nombre in self.paginar:
                body["odata.nextLink"] = "NO_SE_DEBE_CERTIFICAR_UNA_PAGINA_PARCIAL"
            return {"statusCode": 200, "body": body}
        if metodo == "POST" and ruta == "/fields/createfieldasxml":
            data = actual["body"]["parameters"]
            assert data["Options"] == 9
            assert data["__metadata"]["type"] == "SP.XmlSchemaFieldCreationInformation"
            campo = self._campo_xml(data["SchemaXml"])
            if self.al_crear:
                self.al_crear(titulo, campo)
            if campo["InternalName"] in lista["fields"]:
                raise FalloConector("Failed", 409)
            lista["fields"][campo["InternalName"]] = campo
            return {"statusCode": 200, "body": copy.deepcopy(campo)}
        if ruta.startswith("/fields/getbyinternalnameortitle('Title')"):
            campo = lista["fields"]["Title"]
        else:
            guid = re.fullmatch(r"/fields\(guid'([^']+)'\)", ruta)
            if not guid:
                raise ValueError("Endpoint campo inesperado " + ruta)
            encontrados = [c for c in lista["fields"].values() if c["Id"] == guid[1]]
            if len(encontrados) != 1:
                raise FalloConector("Failed", 404)
            campo = encontrados[0]
        if metodo == "GET":
            return {"statusCode": 200, "body": copy.deepcopy(campo)}
        assert parametros["parameters/headers"]["X-HTTP-Method"] == "MERGE"
        p = actual["body"]
        if p.get("EnforceUniqueValues") and not campo["Indexed"]:
            raise FalloConector("Failed", 400)
        schema = ET.fromstring(campo["SchemaXml"])
        for k, v in p.items():
            if k == "__metadata":
                continue
            campo[k] = v
            if k == "Title":
                schema.set("DisplayName", v)
            if isinstance(v, bool):
                schema.set(k, str(v).upper())
        campo["SchemaXml"] = ET.tostring(schema, encoding="unicode")
        return {"statusCode": 204, "body": {}}


def ejecutar(definicion, servidor=None):
    servidor = servidor or SharePointREST()
    return EnsayoProvision(definicion, servidor).ejecutar(), servidor
