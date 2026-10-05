"""Tenant SIMULADO para el flujo P9_MASIVA_PROTO_PREVALIDAR.

NO es Power Automate, SharePoint ni Excel Online: es un intérprete WDL local (el de P8, solo lectura) más
conectores falsos. Prueba la LÓGICA del flujo y el CONTRATO de sus llamadas; no certifica nombres de operaciones,
tiempos ni códigos HTTP reales del conector Excel (supuestos marcados [SUPUESTO]).
"""
from __future__ import annotations

import base64
import io
import json
import re
import uuid
from datetime import datetime

from openpyxl import load_workbook

from p8.ensayo_wdl import EnsayoWDL, FalloConector
from proto_masiva.flows import construir as F

AHORA = "2026-10-05T12:00:00Z"
URI_LOTE = re.compile(r"^_api/web/lists/GetByTitle\('P9_MASIVA_PROTO_LOTES'\)/items\((\d+)\)$")
ESTADOS_ESCRIBIBLES = {"PROCESANDO", "COMPLETADO", "ERROR"}


class TenantSimulado:
    def __init__(self, esquema):
        self.columnas = {c["nombre_tecnico"] for c in esquema["columnas"]}
        self.nombre = "TENANT_SIMULADO"
        self.lotes, self.adjuntos, self.biblioteca = {}, {}, {}
        self.llamadas, self.escrituras = [], []
        self.fallos = {}        # {"adjuntos"|"contenido"|"crear"|"excel"|"merge_final": (estado, http[, mensaje])}
        self.bloqueados = set()  # nombres de archivo que Excel ve como bloqueados (423)
        self._n = 0

    # ---- preparación
    def crear_lote(self, adjunto=None, nombre="ejemplo.xlsx", **campos):
        self._n += 1
        item = {"ID": self._n, "LOTE_UID": f"UID-{self._n}", "ESTADO": "PENDIENTE", "ARCHIVO_NOMBRE": nombre,
                "MENSAJE": "En cola", "CODIGO_RESULTADO": "", "TABLA_ENCONTRADA": "", "FILAS_LEIDAS": 0, **campos}
        self.lotes[self._n] = item
        if adjunto is not None:
            self.adjuntos[self._n] = [(nombre, adjunto)]
        return item

    # ---- conectores
    def operacion(self, operacion, parametros, nombre_accion):
        self.llamadas.append((operacion, nombre_accion))
        fallo = self.fallos.get({"Obtener_adjuntos": "adjuntos", "Obtener_contenido_adjunto": "contenido",
                                 "Crear_archivo": "crear", "Leer_tabla_Excel": "excel"}.get(nombre_accion, ""))
        if fallo:
            raise FalloConector(fallo[0], fallo[1])
        if operacion == "HttpRequest":
            return self._http(parametros, nombre_accion)
        if operacion == "GetAttachments":
            assert parametros["table"] == F.LISTA
            return {"statusCode": 200, "body": [{"Id": f"adj-{i}", "DisplayName": n}
                                                 for i, (n, _) in enumerate(self.adjuntos.get(parametros["id"], []))]}
        if operacion == "GetAttachmentContent":
            assert parametros["table"] == F.LISTA
            _, datos = self.adjuntos[parametros["id"]][int(parametros["attachmentId"].split("-")[1])]
            return {"statusCode": 200, "body": {"$content-type": "application/octet-stream",
                                                "$content": base64.b64encode(datos).decode()}}
        if operacion == "CreateFile":
            assert parametros["folderPath"] == F.CARPETA_TEMP
            clave = (parametros["folderPath"], parametros["name"])
            if any((c, n) == clave for c, n, _ in self.biblioteca.values()):
                raise FalloConector("Failed", 409)
            assert parametros["body"]["$content-type"]
            ident = f"file-{uuid.uuid4().hex[:8]}"
            self.biblioteca[ident] = (parametros["folderPath"], parametros["name"], base64.b64decode(parametros["body"]["$content"]))
            return {"statusCode": 201, "body": {"Id": ident, "Name": parametros["name"]}}
        if operacion == "GetItems":
            return self._excel(parametros)
        raise AssertionError(f"operación no prevista en el prototipo: {operacion}")

    def _http(self, p, nombre):
        uri, metodo, cab = p["parameters/uri"], p["parameters/method"], p["parameters/headers"]
        assert "Depositos_Activos" not in uri and "Depositos_Reversiones" not in uri, "el prototipo no puede tocar producción"
        m = URI_LOTE.match(uri)
        assert m, f"URI no permitida: {uri}"
        assert metodo == "POST" and cab["X-HTTP-Method"] == "MERGE" and cab["IF-MATCH"] == "*"
        cuerpo = json.loads(p["parameters/body"])
        assert set(cuerpo) <= self.columnas, f"columnas fuera del esquema: {set(cuerpo) - self.columnas}"
        if "ESTADO" in cuerpo:
            assert cuerpo["ESTADO"] in ESTADOS_ESCRIBIBLES, "el flujo nunca debe reescribir PENDIENTE (bucle de disparo)"
        if "FILAS_LEIDAS" in cuerpo:
            assert isinstance(cuerpo["FILAS_LEIDAS"], int) and not isinstance(cuerpo["FILAS_LEIDAS"], bool)
        if "FECHA_ESTADO" in cuerpo:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cuerpo["FECHA_ESTADO"])
        for v in cuerpo.values():
            assert not (isinstance(v, str) and v.startswith("@")), "expresión sin evaluar en el cuerpo"
        if nombre == "Escribir_resultado" and "merge_final" in self.fallos:
            raise FalloConector(*self.fallos["merge_final"][:2])
        self.escrituras.append((nombre, int(m[1]), cuerpo))
        self.lotes[int(m[1])].update(cuerpo)
        return {"statusCode": 204, "body": {}}

    def _excel(self, p):
        """Imita el conector Excel Online (Business) «Enumerar filas presentes en una tabla».
        [SUPUESTO] tabla inexistente -> 404; archivo bloqueado -> 423; celdas vacías -> ""; claves = encabezados."""
        carpeta, nombre, datos = self.biblioteca[p["file"]]
        assert p["table"] == F.TABLA
        if nombre in self.bloqueados:
            raise FalloConector("Failed", 423)
        try:
            libro = load_workbook(io.BytesIO(datos))
        except Exception as e:
            raise FalloConector("Failed", 400) from e
        for hoja in libro.worksheets:
            for tabla in hoja.tables.values():
                if tabla.displayName == p["table"]:
                    celdas = list(hoja[tabla.ref])
                    cabeceras = [str(c.value) for c in celdas[0]]
                    filas = [{h: ("" if c.value is None else c.value) for h, c in zip(cabeceras, fila)} for fila in celdas[1:]]
                    return {"statusCode": 200, "body": {"value": [{**f, "@odata.etag": "", "ItemInternalId": str(uuid.uuid4())}
                                                                    for f in filas]}}
        raise FalloConector("Failed", 404)


class EnsayoMasivo(EnsayoWDL):
    def __init__(self, definicion, tenant, item):
        super().__init__(definicion, tenant, scope_estricto=False)
        self.trigger = {"body": dict(item)}

    def _nodo(self, n):
        if n[0] == "funcion" and n[1] in ("toLower", "first", "createArray", "formatDateTime", "utcNow", "take", "string"):
            args = [self._nodo(a) for a in n[2]]
            if n[1] == "toLower":
                return args[0].lower()
            if n[1] == "first":
                return args[0][0] if args[0] else None
            if n[1] == "createArray":
                return list(args)
            if n[1] == "utcNow":
                return AHORA
            if n[1] == "take":
                return args[0][:args[1]]
            if n[1] == "formatDateTime":
                return datetime.strptime(args[0], "%Y-%m-%dT%H:%M:%SZ").strftime(
                    args[1].replace("yyyy", "%Y").replace("MM", "%m").replace("dd", "%d").replace("HH", "%H")
                    .replace("mm", "%M").replace("ss", "%S"))
        return super()._nodo(n)

    def _accion(self, nombre, accion):
        if accion["type"] == "OpenApiConnection":
            entradas = self.evaluar(accion["inputs"])
            self.salidas[nombre] = self.sp.operacion(entradas["host"]["operationId"], entradas["parameters"], nombre)
            return "Succeeded"
        return super()._accion(nombre, accion)

    def dispara(self):
        trigger = next(iter(self.definicion["triggers"].values()))
        return all(self.evaluar(c["expression"]) for c in trigger.get("conditions", []))

    def ejecutar(self):
        if not self.dispara():
            self.estado_final = "NoDisparado"
            return self
        self.estado_final = self._bloque(self.definicion["actions"])
        return self


def configurar(definicion, ubicacion="me", biblioteca="b!BIBLIOTECA-FICTICIA"):
    """Sustituye los marcadores <CONFIGURAR_...> como haría el usuario en el diseñador."""
    texto = json.dumps(definicion).replace(F.PLACEHOLDER_UBICACION, ubicacion).replace(F.PLACEHOLDER_BIBLIOTECA, biblioteca)
    return json.loads(texto)


def procesar(tenant, lote_id, definicion=None):
    definicion = definicion or configurar(F.construir_definicion())
    return EnsayoMasivo(definicion, tenant, tenant.lotes[lote_id]).ejecutar()
