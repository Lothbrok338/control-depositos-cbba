"""Ensayo local de los flujos P9: intérprete WDL (de P8, solo lectura) + SharePoint REST simulado con ETag.

NO es el runtime Microsoft: no certifica importación, conectores ni el comportamiento real de If-Match en el tenant.
Sí modela las reglas de SharePoint que P9 necesita: ETag por versión, MERGE con If-Match (412 si no coincide),
valores de columna de opción restringidos a las opciones definidas y MERGE atómico (candado) entre hilos.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

from p8.ensayo_wdl import EnsayoWDL, FalloConector, Terminado  # solo lectura del intérprete; P8 no se modifica
from p9 import contrato as C

RAIZ = Path(__file__).resolve().parents[1]
META_TIPO = {"Text": "SP.FieldText", "Note": "SP.FieldMultiLineText", "Number": "SP.FieldNumber",
             "DateTime": "SP.FieldDateTime", "Choice": "SP.FieldChoice"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
COLUMNAS_TEXTO = ("ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "USUARIO_ASIGNACION")
COLUMNAS_ESCRIBIBLES = set(C.CAMPOS_ESCRITOS) | set(C.COLUMNAS_MOTOR_26)


class SharePointP9:
    """Lista Depositos_Activos con elementos (ID, versión → ETag) y la definición de ESTADO_ASIGNACION."""
    nombre = "PRUEBA_LOCAL_P9"

    def __init__(self, filas=(), opciones=("DISPONIBLE",), indexados=None):
        """`indexados`: None = estado real del piloto tras P8 (índices de P8; faltan los 3 nuevos de P9);
        un conjunto de InternalName = exactamente esos campos indexados; "P9" = los 7 de P9 más CLAVE_TRANSACCION."""
        self.items = {}
        for i, fila in enumerate(filas, 1):
            self.agregar(i, fila)
        self.opciones = list(opciones)
        self.llamadas = []
        self.fallos = {}
        self.candado = threading.Lock()
        self.barrera = None  # threading.Barrier: los hilos esperan tras leer, antes de actualizar
        self.al_actualizar = None  # callback(id, etag_recibido) previo a la comprobación atómica
        self.campo_extra = {}  # sobrescribe propiedades del campo (pruebas de verificación)
        self.sin_etag = False  # simula una respuesta sin ETag
        self.fallos_indice = {}  # {InternalName: (estado, http)}: falla el MERGE de ese índice
        self.paginar = set()  # nombres de acción cuya respuesta de campos trae odata.nextLink
        self.campos = self._campos_desde_esquema(indexados)
        self.campo_id = self.campos["ESTADO_ASIGNACION"]["Id"]

    # -------------------------------------------------------------- campos
    @staticmethod
    def _campos_desde_esquema(indexados):
        esquema = json.loads((RAIZ / "p8/esquema_listas_p8.json").read_text(encoding="utf-8"))["Depositos_Activos"]["columnas"]
        tipos = {"Texto de una linea": "Text", "Varias lineas de texto sin formato": "Note", "Numero, 2 decimales": "Number",
                 "Fecha y hora, solo fecha": "DateTime", "Fecha y hora, incluir hora": "DateTime", "Opcion": "Choice"}
        if indexados == "P9":
            indexados = {c["nombre_tecnico"] for c in esquema if c["indexada"]} | {n for n, _ in C.INDICES}
        elif indexados is None:
            indexados = {c["nombre_tecnico"] for c in esquema if c["indexada"]}
        campos = {}
        for c in esquema:
            n = c["nombre_tecnico"]
            campos[n] = {"Id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "campo-" + n)), "InternalName": n,
                         "TypeAsString": tipos[c["tipo"]], "Indexed": n in indexados, "Hidden": False}
        return campos

    def indexados(self):
        return {n for n, c in self.campos.items() if c["Indexed"]}

    # -------------------------------------------------------------- elementos
    def agregar(self, id_, fila):
        campos = {k: v for k, v in fila.items()}
        campos.setdefault("ESTADO_ASIGNACION", "DISPONIBLE")
        for k in ("ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "USUARIO_ASIGNACION",
                  "FECHA_HORA_ASIGNACION", "OBSERVACION"):
            campos.setdefault(k, None)
        self.items[id_] = {"campos": campos, "version": 1}

    def etag(self, id_):
        return f'"{self.items[id_]["version"]}"'

    # -------------------------------------------------------------- campo
    def _schema(self):
        campo = ET.Element("Field", {"Name": "ESTADO_ASIGNACION", "Type": "Choice", "Required": "TRUE",
                                     "Format": "DropDown", "FillInChoice": "FALSE", "Hidden": "FALSE"})
        elegidas = ET.SubElement(campo, "CHOICES")
        for o in self.opciones:
            ET.SubElement(elegidas, "CHOICE").text = o
        ET.SubElement(campo, "Default").text = "DISPONIBLE"
        return ET.tostring(campo, encoding="unicode")

    def campo(self):
        c = {"Id": self.campo_id, "InternalName": "ESTADO_ASIGNACION", "TypeAsString": "Choice", "Required": True,
             "Indexed": self.campos["ESTADO_ASIGNACION"]["Indexed"], "DefaultValue": "DISPONIBLE", "Hidden": False, "ReadOnlyField": False,
             "SchemaXml": self._schema()}
        c.update(self.campo_extra)
        return c

    # -------------------------------------------------------------- REST
    def ejecutar(self, nombre, parametros):
        metodo, uri = parametros["parameters/method"], parametros["parameters/uri"]
        cabeceras = {k.lower(): v for k, v in parametros["parameters/headers"].items()}
        cuerpo = json.loads(parametros["parameters/body"]) if "parameters/body" in parametros else None
        with self.candado:
            self.llamadas.append({"accion": nombre, "metodo": metodo, "uri": uri, "cabeceras": cabeceras, "cuerpo": cuerpo})
        if nombre in self.fallos:
            raise FalloConector(*self.fallos[nombre])
        base = f"_api/web/lists(guid'{C.LISTA_DEPOSITOS_ACTIVOS_ID}')"
        if not uri.startswith(base):
            raise FalloConector("Failed", 404)
        resto = uri[len(base):]
        m = re.fullmatch(r"/items\((\d+)\)(\?\$select=(.*))?", resto)
        if m:
            return self._item(nombre, metodo, int(m[1]), m[3], cabeceras, cuerpo)
        if metodo == "GET" and resto.startswith("/fields?$filter=InternalName eq '"):
            nombre_campo = re.search(r"eq '([^']+)'", resto)[1]
            valor = [self.campo()] if nombre_campo == "ESTADO_ASIGNACION" else []
            return {"statusCode": 200, "body": {"value": copy.deepcopy(valor)}}
        if metodo == "GET" and resto == "/fields?$select=Id,InternalName,TypeAsString,Indexed,Hidden&$top=5000":
            cuerpo_resp = {"value": copy.deepcopy(list(self.campos.values()))}
            if nombre in self.paginar:
                cuerpo_resp["odata.nextLink"] = "PAGINA_PARCIAL"
            return {"statusCode": 200, "body": cuerpo_resp}
        m = re.fullmatch(r"/fields\(guid'([^']+)'\)", resto)
        if m and metodo == "POST":
            return self._merge_campo(m[1], cabeceras, cuerpo)
        raise ValueError("Endpoint inesperado: " + uri)

    def _item(self, nombre, metodo, id_, seleccion, cabeceras, cuerpo):
        if metodo == "GET":
            assert cabeceras["accept"] == "application/json;odata=verbose"
            with self.candado:
                item = self.items.get(id_)
                if item is None:
                    raise FalloConector("Failed", 404)
                etag = None if self.sin_etag else self.etag(id_)
                columnas = seleccion.split(",")
                datos = {c: (id_ if c == "Id" else item["campos"].get(c)) for c in columnas}
                metadata = {"uri": f"{id_}", **({"etag": etag} if etag else {})}
                respuesta = {"statusCode": 200, "headers": {"ETag": etag} if etag else {},
                             "body": {"d": {"__metadata": metadata, **copy.deepcopy(datos)}}}
            if self.barrera is not None:
                self.barrera.wait(timeout=15)
            return respuesta
        assert metodo == "POST" and cabeceras.get("x-http-method") == "MERGE"
        assert "if-match" in cabeceras, "SharePoint exige condición explícita: P9 siempre envía If-Match"
        if self.al_actualizar:
            self.al_actualizar(id_, cabeceras["if-match"])
        with self.candado:  # comprobación y escritura atómicas, como en SharePoint
            item = self.items.get(id_)
            if item is None:
                raise FalloConector("Failed", 404)
            if cabeceras["if-match"] not in ("*", self.etag(id_)):
                raise FalloConector("Failed", 412)
            self._validar_cuerpo(cuerpo)
            item["campos"].update(cuerpo)
            item["version"] += 1
        return {"statusCode": 204, "body": {}}

    def _validar_cuerpo(self, cuerpo):
        if not isinstance(cuerpo, dict):
            raise FalloConector("Failed", 400)
        for k, v in cuerpo.items():
            if k not in COLUMNAS_ESCRIBIBLES:
                raise FalloConector("Failed", 400)
            if k == "ESTADO_ASIGNACION" and v not in self.opciones:
                raise FalloConector("Failed", 400)  # la columna no admite relleno: solo las opciones definidas
            if k in COLUMNAS_TEXTO and (not isinstance(v, str) or len(v) > C.MAX_TEXTO):
                raise FalloConector("Failed", 400)
            if k == "FECHA_HORA_ASIGNACION" and not (isinstance(v, str) and ISO.match(v)):
                raise FalloConector("Failed", 400)

    def _merge_campo(self, guid, cabeceras, cuerpo):
        if "Choices" not in cuerpo:
            return self._merge_indice(guid, cabeceras, cuerpo)
        if guid != self.campo_id:
            raise FalloConector("Failed", 404)
        assert cabeceras.get("x-http-method") == "MERGE" and cabeceras["if-match"] == "*"
        assert cuerpo["__metadata"]["type"] == "SP.FieldChoice"
        assert cuerpo["Choices"]["__metadata"]["type"] == "Collection(Edm.String)"
        self.opciones = list(cuerpo["Choices"]["results"])
        return {"statusCode": 204, "body": {}}


    def _merge_indice(self, guid, cabeceras, cuerpo):
        assert cabeceras.get("x-http-method") == "MERGE" and cabeceras["if-match"] == "*"
        assert set(cuerpo) == {"__metadata", "Indexed"}, "el provisionador solo puede cambiar Indexed"
        assert cuerpo["Indexed"] is True, "nunca se elimina un índice"
        campo = next((c for c in self.campos.values() if c["Id"] == guid), None)
        if campo is None:
            raise FalloConector("Failed", 404)
        if campo["InternalName"] in self.fallos_indice:
            raise FalloConector(*self.fallos_indice[campo["InternalName"]])
        if cuerpo["__metadata"]["type"] != META_TIPO[campo["TypeAsString"]]:
            raise FalloConector("Failed", 400)  # SharePoint rechaza un tipo de metadatos que no es el de la columna
        campo["Indexed"] = True
        return {"statusCode": 204, "body": {}}


class EnsayoP9(EnsayoWDL):
    """EnsayoWDL con las funciones WDL que usan los flujos P9 y la acción Response."""

    def __init__(self, definicion, sp, entradas=None, ahora="2026-10-01T15:30:00.0000000Z"):
        # scope_estricto=False: un fallo con sucesor CATCH ejecutado (runAfter Failed) es un fallo MANEJADO, como en Power Automate
        super().__init__(definicion, sp, scope_estricto=False)
        self.trigger = {"body": dict(entradas or {})}
        self.ahora = ahora
        self.respuesta = None

    def _nodo(self, n):
        if n[0] == "funcion" and n[1] in ("trim", "toLower", "first", "xml", "xpath", "utcNow", "greaterOrEquals"):
            args = [self._nodo(a) for a in n[2]]
            if n[1] == "trim":
                return args[0].strip()
            if n[1] == "toLower":
                return args[0].lower()
            if n[1] == "first":
                return args[0][0] if args[0] else None
            if n[1] == "utcNow":
                return self.ahora
            if n[1] == "greaterOrEquals":
                return args[0] >= args[1]
            if n[1] == "xml":
                try:
                    return ET.fromstring(args[0])
                except ET.ParseError as e:
                    raise ValueError("XML inválido") from e
            raiz, ruta = args
            if ruta == "/Field/CHOICES/CHOICE/text()":
                textos = [e.text or "" for e in raiz.findall("./CHOICES/CHOICE")]
                return textos[0] if len(textos) == 1 else textos  # WDL real: texto o lista según el nº de nodos
            m = re.fullmatch(r"string\(/Field/@([A-Za-z]+)\)", ruta)
            if not m:
                raise NotImplementedError(ruta)
            return raiz.attrib.get(m[1], "")
        return super()._nodo(n)

    def _accion(self, nombre, accion):
        if accion["type"] == "Response":
            entradas = self.evaluar(accion["inputs"])
            assert entradas["statusCode"] == 200
            self.respuesta = entradas["body"]
            self.salidas[nombre] = {"statusCode": 200}
            return "Succeeded"
        return super()._accion(nombre, accion)

    def ejecutar(self):
        try:
            self.estado_final = self._bloque(self.definicion["actions"])
        except Terminado as t:
            self.estado_final = t.estado
        return self


def entradas_asignar(id_, clave, estudiante="Ana Perez", codigo="E-1001", solicitado="Mesa de ayuda", sede="COCHABAMBA",
                     observacion="", usuario="operador@univalle.edu"):
    """Cuerpo del trigger tal como lo envía Power Apps (claves internas de C.ENTRADAS)."""
    valores = [id_, clave, estudiante, codigo, solicitado, sede, observacion, usuario]
    return {c[0]: v for c, v in zip(C.ENTRADAS, valores)}


def asignar(definicion, sp, entradas, **kw):
    return EnsayoP9(definicion, sp, entradas, **kw).ejecutar()
