"""Tenant SIMULADO para `P9_MASIVA_PROTO_CONFIRMAR` y `P9_MASIVA_PROTO_ESTADO`: una lista Depositos_Activos con ETags REALES y una carpeta de archivos.

NO es SharePoint: es un modelo local que reproduce lo que importa para la concurrencia y para el estado temporal:
  - GET /items(ID)?$select=...   -> devuelve esas columnas + d.__metadata.etag y la cabecera ETag (como V4.2 con odata=verbose);
  - POST + X-HTTP-Method: MERGE + IF-MATCH: aplica el cuerpo SOLO si el ETag coincide (412 si no) y cambia el ETag;
  - `IF-MATCH: *` se RECHAZA (aborta la prueba): la confirmación nunca puede usarlo;
  - CreateFile / UpdateFile / GetFileContentByPath sobre `Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` (con historial de cada versión del archivo de estado);
  - inyección de fallos por ID y de «carreras» (otro usuario cambia el depósito entre la lectura y la escritura), y fallos al escribir el estado;
  - `string()`/`concat()` por encima de 131.072 caracteres FALLAN, como documenta Microsoft para Power Automate;
  - EL ORDEN de los eventos queda registrado (`eventos`): la respuesta a Power Apps llega ANTES de la primera lectura de un depósito.
Prueba la LÓGICA de los flujos y el CONTRATO de sus llamadas; no certifica el comportamiento real de SharePoint (ver ESCALA_1999.md y CONFIRMACION_MASIVA.md §9).
"""
from __future__ import annotations

import base64
import copy
import json
import re

from p8.ensayo_wdl import FalloConector, cadena
from proto_masiva.flows import construir_confirmar as K
from proto_masiva.flows import construir_estado as E
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
        self.llamadas = []          # (método, id, acción) de cada llamada HTTP a la lista de depósitos
        self.lecturas = []          # ids leídos, en orden
        self.escrituras = []        # {"id", "headers", "body", "retry", "etag_enviado"} de cada MERGE
        self.fallos_lectura = {}    # id -> (estado, http)
        self.fallos_escritura = {}  # id -> (estado, http)
        self.carreras = {}          # id -> {campo: valor}: otro usuario modifica el depósito justo ANTES de nuestro MERGE
        self.nombre = "TENANT_SIMULADO"
        # --- archivos (estado temporal)
        self.archivos = {}          # nombre -> {"id", "contenido"}
        self.historial_estado = []  # (nombre, dict) de cada versión escrita, en orden
        self.llamadas_archivo = []  # (operación, nombre_accion)
        self.actualizaciones = 0
        self.fallos_actualizacion = set()   # números de actualización (1 = la primera UpdateFile) que fallan
        self.fallo_crear_estado = None      # (estado, http)
        self.eventos = []           # ("respuesta", nombre) | ("deposito", método, id) | ("archivo", operación)

    # --- ETag
    def etag(self, id_):
        return f'"{self.etags[id_]}"'

    # --- operaciones
    def operacion(self, operacion, parametros, nombre_accion, accion):
        assert parametros["dataset"] == SITIO
        if operacion == "HttpRequest":
            return self._http(parametros, nombre_accion, accion)
        return self._archivo(operacion, parametros, nombre_accion, accion)

    def _http(self, parametros, nombre_accion, accion):
        metodo, uri = parametros["parameters/method"], parametros["parameters/uri"]
        m = re.fullmatch(r"_api/web/lists\(guid'" + LISTA + r"'\)/items\((\d+)\)(\?\$select=([A-Za-z_,]+))?", uri)
        assert m, f"URI no prevista: {uri}"
        id_ = int(m[1])
        self.llamadas.append((metodo, id_, nombre_accion))
        self.eventos.append(("deposito", metodo, id_))
        if metodo == "GET":
            return self._leer(id_, parametros, m[3], accion)
        assert metodo == "POST", metodo
        return self._escribir(id_, parametros, accion)

    def _leer(self, id_, p, select, accion):
        assert p["parameters/headers"] == {"Accept": "application/json;odata=verbose"} and select
        assert tuple(select.split(",")) == K.COLUMNAS_LECTURA
        assert accion["inputs"]["retryPolicy"] == {"type": "fixed", "count": 2, "interval": "PT5S"}
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

    # --- archivos de estado
    def _archivo(self, operacion, p, nombre_accion, accion):
        self.llamadas_archivo.append((operacion, nombre_accion))
        self.eventos.append(("archivo", operacion))
        if operacion == "CreateFile":
            assert p["folderPath"] == K.CARPETA_ESTADO == "/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP"
            nombre = p["name"]
            assert re.fullmatch(K.PREFIJO_ESTADO + r"[0-9a-f-]{36}\.json", nombre), nombre
            assert accion["inputs"]["retryPolicy"] == {"type": "none"}              # crear NO se reintenta (no es idempotente)
            if self.fallo_crear_estado:
                raise FalloConector(*self.fallo_crear_estado)
            assert nombre not in self.archivos
            self.archivos[nombre] = {"id": f"ID-{len(self.archivos) + 1}", "contenido": p["body"]}
            self._historial(nombre, p["body"])
            return {"statusCode": 201, "body": {"Id": self.archivos[nombre]["id"], "Name": nombre}}
        if operacion == "UpdateFile":
            assert accion["inputs"]["retryPolicy"] == K.RETRY_ESTADO
            self.actualizaciones += 1
            if self.actualizaciones in self.fallos_actualizacion:
                raise FalloConector("Failed", 500)
            destino = next((n for n, a in self.archivos.items() if a["id"] == p["id"]), None)
            assert destino, f"UpdateFile sobre un archivo que no existe: {p['id']}"
            self.archivos[destino]["contenido"] = p["body"]
            self._historial(destino, p["body"])
            return {"statusCode": 200, "body": {"Id": p["id"]}}
        if operacion == "GetFileContentByPath":
            assert p["inferContentType"] is False
            ruta = p["path"]
            assert ruta.startswith(K.CARPETA_ESTADO + "/"), ruta
            nombre = ruta[len(K.CARPETA_ESTADO) + 1:]
            if nombre not in self.archivos:
                raise FalloConector("Failed", 404)
            contenido = self.archivos[nombre]["contenido"]
            return {"statusCode": 200, "body": {"$content-type": "application/octet-stream",
                                                "$content": base64.b64encode(contenido.encode("utf-8")).decode()}}
        raise AssertionError(f"operación de archivo no prevista: {operacion}")

    def _historial(self, nombre, contenido):
        assert isinstance(contenido, str) and len(contenido) <= K.LIMITE_STRING        # nunca se escribe más de lo que string() permite
        self.historial_estado.append((nombre, json.loads(contenido)))

    # --- comprobaciones para las pruebas
    def campos_cambiados(self, id_):
        return {c for c in self.filas[id_] if self.filas[id_][c] != self.iniciales[id_][c]}


class EnsayoConfirmacion(S.EnsayoDirecto):
    """Ejecuta el flujo como lo haría Power Apps. El bucle reinicia el estado de sus acciones en cada iteración (como el runtime: cada iteración tiene
    su propio historial) y es secuencial. La respuesta a Power Apps se registra EN EL ORDEN en que ocurre (`tenant.eventos`)."""
    SALIDAS = K.SALIDAS

    def __init__(self, definicion, tenant, trigger_body, paso_ms=7):
        super().__init__(definicion, tenant, None, None, paso_ms)
        self.trigger = {"body": trigger_body}
        self.respuestas = []

    def _nodo(self, n):
        if n[0] == "funcion" and n[1] in ("mod", "string", "concat", "createArray", "guid"):
            args = [self._nodo(a) for a in n[2]]
            if n[1] == "guid":                          # determinista (contador por tenant): los ejemplos versionados son reproducibles
                self.sp.guids = getattr(self.sp, "guids", 0) + 1
                return f"00000000-0000-4000-8000-{self.sp.guids:012d}"
            if n[1] == "mod":
                return args[0] % args[1]
            if n[1] == "createArray":
                return list(args)
            resultado = cadena(args[0]) if n[1] == "string" else "".join(map(cadena, args))
            if len(resultado) > K.LIMITE_STRING:        # límite documentado de Power Automate: la acción que lo usa FALLA
                raise ValueError(f"{n[1]}() supera {K.LIMITE_STRING} caracteres")
            return resultado
        return super()._nodo(n)

    def _accion(self, nombre, accion):
        if accion["type"] == "Response":
            entradas = self.evaluar(accion["inputs"])
            assert entradas["statusCode"] == 200 and accion["kind"] == "PowerApp"
            assert set(entradas["body"]) == set(self.SALIDAS) and all(isinstance(v, str) for v in entradas["body"].values())
            self.respuestas.append(entradas["body"])
            self.respuesta = entradas["body"]
            self.sp.eventos.append(("respuesta", nombre))
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


class EnsayoEstado(EnsayoConfirmacion):
    SALIDAS = E.SALIDAS


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


class Ejecucion:
    """Una ejecución completa de P9_MASIVA_PROTO_CONFIRMAR: la respuesta TEMPRANA a Power Apps + el estado FINAL que quedó en el archivo temporal."""

    def __init__(self, ensayo, tenant, filas):
        self.ensayo, self.tenant, self.filas = ensayo, tenant, filas or []
        assert len(ensayo.respuestas) == 1, ensayo.respuestas           # UNA sola respuesta por ejecución, siempre
        self.aceptacion = ensayo.respuestas[0]
        self.uid = self.aceptacion["execution_uid"]
        self.nombre_archivo = f"{K.PREFIJO_ESTADO}{self.uid}.json" if self.uid else None

    # --- atajos de la respuesta temprana
    def __getitem__(self, clave):
        return self.aceptacion[clave]

    @property
    def aceptada(self):
        return self.aceptacion["resultado"] == "ACEPTADO"

    # --- estado final
    @property
    def estado(self):
        assert self.nombre_archivo, "no hubo estado: la entrada se rechazó antes de crearlo"
        return json.loads(self.tenant.archivos[self.nombre_archivo]["contenido"])

    @property
    def fallidas(self):
        return self.estado["detalle_json"]

    @property
    def versiones(self):
        return [e for n, e in self.tenant.historial_estado if n == self.nombre_archivo]

    def resultados(self):
        """Resultado de CADA fila enviada, en orden: la que figura entre las no confirmadas, o CONFIRMADO (las confirmadas no se listan: se cuentan)."""
        malas = {d["fila_excel"]: d["resultado"] for d in self.fallidas}
        return [malas.get(f["fila_excel"], "CONFIRMADO") for f in self.filas]

    def fila(self, i=0):
        """Detalle de la fila i: el registro de no confirmada o {'resultado': 'CONFIRMADO'} si no está entre las no confirmadas."""
        f = self.filas[i]
        return next((d for d in self.fallidas if d["fila_excel"] == f["fila_excel"]), {"fila_excel": f["fila_excel"], "resultado": "CONFIRMADO"})


def confirmar(filas, tenant, usuario=USUARIO, definicion=None, texto=None, paso_ms=7):
    """Ejecuta P9_MASIVA_PROTO_CONFIRMAR de punta a punta (como Power Apps) y devuelve la `Ejecucion` (respuesta temprana + estado final)."""
    definicion = definicion or K.construir_definicion()
    cuerpo = {"text": json.dumps(filas, ensure_ascii=False) if texto is None else texto, "text_1": usuario}
    ensayo = EnsayoConfirmacion(definicion, tenant, cuerpo, paso_ms).ejecutar()
    assert ensayo.respuesta is not None, ensayo.estados
    return Ejecucion(ensayo, tenant, filas)


def consultar_estado(tenant, uid, definicion=None):
    """Ejecuta P9_MASIVA_PROTO_ESTADO como lo haría Power Apps (Run(execution_uid)). Devuelve las 9 salidas (texto)."""
    ensayo = EnsayoEstado(definicion or E.construir_definicion(), tenant, {"text": uid}).ejecutar()
    assert ensayo.estado_final == "Succeeded" and len(ensayo.respuestas) == 1, ensayo.estados
    return ensayo.respuesta
