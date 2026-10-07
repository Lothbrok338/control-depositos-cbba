"""Tenant SIMULADO para `P9_MASIVA_PROTO_CONFIRMAR`: una lista Depositos_Activos con ETags REALES.

NO es SharePoint: es un modelo local que reproduce lo que importa para la concurrencia:
  - GET /items(ID)?$select=...   -> devuelve esas columnas + d.__metadata.etag y la cabecera ETag (como V4.2 con odata=verbose);
  - POST + X-HTTP-Method: MERGE + IF-MATCH: aplica el cuerpo SOLO si el ETag coincide (412 si no) y cambia el ETag;
  - `IF-MATCH: *` se RECHAZA (aborta la prueba): la confirmación nunca puede usarlo;
  - inyección de fallos por ID y de «carreras» (otro usuario cambia el depósito entre la lectura y la escritura).
Prueba la LÓGICA del flujo y el CONTRATO de sus llamadas; no certifica el comportamiento real de SharePoint (ver CONFIRMACION_MASIVA.md §9).
"""
from __future__ import annotations

import copy
import json
import re

from p8.ensayo_wdl import FalloConector
from proto_masiva.flows import construir_confirmar as K
import simulador as S

SITIO, LISTA = K.SITIO, K.LISTA_ID
COLUMNAS_ESCRITAS = set(K.CAMPOS_ESCRITOS)


def deposito(id_, banco="BNB", cuenta="3000100152", codigo="COD-0001", importe=100.0, moneda="BOB", estado="DISPONIBLE",
             fecha="2026-10-01", tipo="CRÉDITO", clave=None):
    """Fila de Depositos_Activos con TODAS sus columnas relevantes (también las que la confirmación NO debe tocar)."""
    return {"Id": id_, "CLAVE_TRANSACCION": clave or f"CLAVE-{id_}", "BANCO": banco, "CUENTA_BANCARIA": cuenta, "CODIGO_ASIGNACION": codigo,
            "IMPORTE": importe, "MONEDA": moneda, "ESTADO_ASIGNACION": estado, "FECHA_MOVIMIENTO": fecha, "TIPO_MOVIMIENTO": tipo,
            "USUARIO_ASIGNACION": None, "FECHA_HORA_ASIGNACION": None, "ESTUDIANTE": None, "CODIGO_ESTUDIANTE": None,
            "SOLICITADO_POR": None, "SEDE_ASIGNACION": None, "OBSERVACION": None,
            "DESCRIPCION": f"DESCRIPCION {id_}", "SALDO": 1234.5, "HORA_MOVIMIENTO": "10:00", "LOTE_CARGA": "LOTE-1", "MOTOR_ESTADO": "DISPONIBLE"}


class TenantConfirmacion:
    def __init__(self, depositos=()):
        self.filas = {d["Id"]: copy.deepcopy(d) for d in depositos}
        self.iniciales = copy.deepcopy(self.filas)
        self.etags = {i: 1 for i in self.filas}
        self.llamadas = []          # (método, id, acción) de cada llamada a SharePoint
        self.lecturas = []          # ids leídos, en orden
        self.escrituras = []        # {"id", "headers", "body", "retry", "etag_enviado"} de cada MERGE
        self.fallos_lectura = {}    # id -> (estado, http)
        self.fallos_escritura = {}  # id -> (estado, http)
        self.carreras = {}          # id -> {campo: valor}: otro usuario modifica el depósito justo ANTES de nuestro MERGE
        self.nombre = "TENANT_SIMULADO"

    # --- ETag
    def etag(self, id_):
        return f'"{self.etags[id_]}"'

    # --- operaciones
    def operacion(self, operacion, parametros, nombre_accion, accion):
        assert operacion == "HttpRequest", f"operación no prevista en la confirmación: {operacion}"
        assert parametros["dataset"] == SITIO
        metodo, uri = parametros["parameters/method"], parametros["parameters/uri"]
        m = re.fullmatch(r"_api/web/lists\(guid'" + LISTA + r"'\)/items\((\d+)\)(\?\$select=([A-Za-z_,]+))?", uri)
        assert m, f"URI no prevista: {uri}"
        id_ = int(m[1])
        self.llamadas.append((metodo, id_, nombre_accion))
        if metodo == "GET":
            return self._leer(id_, parametros, m[3], accion)
        assert metodo == "POST", metodo
        return self._escribir(id_, parametros, accion)

    def _leer(self, id_, p, select, accion):
        assert p["parameters/headers"] == {"Accept": "application/json;odata=verbose"} and select
        assert tuple(select.split(",")) == K.COLUMNAS_LECTURA
        self.lecturas.append(id_)
        if id_ in self.fallos_lectura:
            raise FalloConector(*self.fallos_lectura[id_])
        if id_ not in self.filas:
            raise FalloConector("Failed", 404)
        fila = self.filas[id_]
        datos = {c: (fila[c] + "T00:00:00Z" if c == "FECHA_MOVIMIENTO" and len(fila[c]) == 10 else fila[c]) for c in K.COLUMNAS_LECTURA}
        return {"statusCode": 200, "headers": {"ETag": self.etag(id_)}, "body": {"d": {**datos, "__metadata": {"etag": self.etag(id_)}}}}

    def _escribir(self, id_, p, accion):
        h = p["parameters/headers"]
        assert h["X-HTTP-Method"] == "MERGE" and h["Accept"] == h["Content-Type"] == "application/json;odata=nometadata"
        assert h["IF-MATCH"] != "*" and h["IF-MATCH"], f"IF-MATCH inválido: {h['IF-MATCH']!r}"  # NUNCA '*'
        cuerpo = json.loads(p["parameters/body"])
        if id_ in self.carreras:  # otro usuario modifica el depósito entre nuestra lectura y nuestra escritura
            self.filas[id_].update(self.carreras.pop(id_))
            self.etags[id_] += 1
        self.escrituras.append({"id": id_, "headers": dict(h), "body": cuerpo, "retry": accion["inputs"]["retryPolicy"],
                                "etag_enviado": h["IF-MATCH"], "etag_vigente": self.etag(id_) if id_ in self.filas else None})
        if id_ in self.fallos_escritura:
            raise FalloConector(*self.fallos_escritura[id_])
        if id_ not in self.filas:
            raise FalloConector("Failed", 404)
        if h["IF-MATCH"] != self.etag(id_):
            raise FalloConector("Failed", 412)   # precondición: el ETag ya no es el vigente
        assert set(cuerpo) == COLUMNAS_ESCRITAS  # SharePoint solo recibe los 8 campos de V4.2
        self.filas[id_].update(cuerpo)
        self.etags[id_] += 1
        return {"statusCode": 204, "body": {}}

    # --- comprobaciones para las pruebas
    def campos_cambiados(self, id_):
        return {c for c in self.filas[id_] if self.filas[id_][c] != self.iniciales[id_][c]}


class EnsayoConfirmacion(S.EnsayoDirecto):
    """Ejecuta el flujo como lo haría Power Apps: Run(detalle_json, usuario_email). El bucle reinicia el estado de sus acciones en cada
    iteración (como el runtime: cada iteración tiene su propio historial) y es secuencial."""

    def __init__(self, definicion, tenant, detalle_json, usuario, paso_ms=7):
        super().__init__(definicion, tenant, None, None, paso_ms)
        self.trigger = {"body": {"text": detalle_json, "text_1": usuario}}

    def _accion(self, nombre, accion):
        if accion["type"] == "Response":
            entradas = self.evaluar(accion["inputs"])
            assert entradas["statusCode"] == 200 and accion["kind"] == "PowerApp"
            assert set(entradas["body"]) == set(K.SALIDAS) and all(isinstance(v, str) for v in entradas["body"].values())
            self.respuesta = entradas["body"]
            self.salidas[nombre] = {"statusCode": 200}
            return "Succeeded"
        if accion["type"] == "Foreach":
            assert accion["runtimeConfiguration"]["concurrency"]["repetitions"] == 1  # secuencial
            estados, nombres = [], list(_nombres(accion["actions"]))
            for valor in self.evaluar(accion["foreach"]):
                for n in nombres:
                    self.estados.pop(n, None)
                    self.salidas.pop(n, None)
                self.iteraciones[nombre] = valor
                estados.append(self._bloque(accion["actions"]))
            return "Failed" if "Failed" in estados else "Succeeded"
        return super()._accion(nombre, accion)


def _nombres(acciones):
    for n, a in acciones.items():
        yield n
        yield from _nombres(a.get("actions", {}))
        yield from _nombres(a.get("else", {}).get("actions", {}))


def fila_validada(dep, **cambios):
    """La fila tal como la enviaría Power Apps desde colPrevalidacionP9 (resultado VALIDO) para ese depósito."""
    f = {"fila_excel": 5 + dep["Id"], "deposito_id": dep["Id"], "clave_transaccion": dep["CLAVE_TRANSACCION"], "banco": dep["BANCO"],
         "cuenta_bancaria": dep["CUENTA_BANCARIA"], "codigo_asignacion": dep["CODIGO_ASIGNACION"], "importe": dep["IMPORTE"],
         "moneda": dep["MONEDA"], "estudiante": f"ESTUDIANTE {dep['Id']}", "solicitado_por": "SOLICITANTE", "sede": "COCHABAMBA",
         "observacion": ""}
    f.update(cambios)
    return f


USUARIO = "gabriel@univalle.edu"


def confirmar(filas, tenant, usuario=USUARIO, definicion=None, texto=None, paso_ms=7):
    definicion = definicion or K.construir_definicion()
    ensayo = EnsayoConfirmacion(definicion, tenant, json.dumps(filas, ensure_ascii=False) if texto is None else texto, usuario, paso_ms).ejecutar()
    assert ensayo.estado_final == "Succeeded" and ensayo.respuesta is not None, ensayo.estados
    return ensayo.respuesta


def detalle(respuesta):
    return json.loads(respuesta["detalle_json"])
