# -*- coding: utf-8 -*-
"""
p10/lista_simulada.py · P10-A.2 · `Depositos_Activos` EN MEMORIA, solo para pruebas.

Se comporta como la lista real en lo que P10 observa: elementos con `Id`, `Modified` y ETag que cambian en cada escritura,
fechas con hora en UTC («…Z»), fecha de movimiento «solo fecha» como medianoche UTC, columnas con los nombres internos reales
(P8/P9) y las escrituras de P9: asignar (`DISPONIBLE -> ASIGNADO`), revertir (payload REAL de `p9.reversion.contrato`) y
eliminar (lo que hará P10-B). No simula SharePoint más allá de eso.
"""
import copy
import uuid
from datetime import datetime, timedelta, timezone

from p9.reversion.contrato import payload_reversion

from . import contrato as C
from .estado import CAMPOS_LISTA
from .sharepoint import ZONA_LOCAL

CAMPOS_OPERATIVOS = ("ESTADO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION",
                     "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "OBSERVACION", "ULTIMA_REVERSION_ID")


def a_utc_z(local_iso):
    """'2026-10-08T10:29:00' (Bolivia) -> '2026-10-08T14:29:00Z' (como lo entrega SharePoint)."""
    d = datetime.fromisoformat(local_iso).replace(tzinfo=ZONA_LOCAL)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ListaSimulada:
    def __init__(self, reloj_local="2026-10-08T08:00:00"):
        self.reloj = datetime.fromisoformat(reloj_local)
        self.items = {}              # Id -> dict
        self._sig = 1
        self.escrituras = 0

    # -- reloj
    def avanzar(self, **kw):
        self.reloj += timedelta(**kw)
        return self.reloj

    def _modificar(self, it):
        it["Modified"] = a_utc_z(self.reloj.replace(microsecond=0).isoformat())
        it["__etag"] = it.get("__etag", 0) + 1
        self.escrituras += 1

    # -- carga (lo que hace P8 con el JSON de P7)
    def cargar(self, filas_p0, snapshot=None):
        """`filas_p0`: filas de LISTS.csv (26 columnas). `snapshot`: A.1 Snapshot (estado operativo inicial) o None."""
        nuevos = 0
        existentes = {i["CLAVE_TRANSACCION"] for i in self.items.values()}
        for f in sorted(filas_p0, key=lambda r: r[C.COLUMNA_CLAVE]):
            clave = f[C.COLUMNA_CLAVE]
            if clave in existentes:
                continue                       # P8: YA_EXISTE
            it = {"Id": self._sig, "CLAVE_TRANSACCION": clave, "BANCO": f["BANCO"], "CUENTA_BANCARIA": f["CUENTA BANCARIA"],
                  "MONEDA": f["MONEDA"], "FECHA_MOVIMIENTO": f["FECHA MOVIMIENTO"][:10] + "T00:00:00Z",
                  "ESTADO_ASIGNACION": "DISPONIBLE", "LOTE_CARGA": f["LOTE DE CARGA"], "FECHA_CARGA": f["FECHA DE CARGA"],
                  "ARCHIVO_ORIGEN": f["ARCHIVO ORIGEN"], **{c: None for c in CAMPOS_OPERATIVOS[1:]}}
            if snapshot is not None and snapshot.get(clave):
                s = snapshot.get(clave)
                for c in CAMPOS_OPERATIVOS:
                    v = s.get(c)
                    it[c] = (a_utc_z(v.isoformat()) if c == "FECHA_HORA_ASIGNACION" and v else (v if v != "" else None))
            self._sig += 1
            self._modificar(it)
            self.items[it["Id"]] = it
            nuevos += 1
        return nuevos

    # -- escrituras de P9
    def _por_clave(self, clave):
        return next(i for i in self.items.values() if i["CLAVE_TRANSACCION"] == clave)

    def confirmar(self, clave, estudiante="ESTUDIANTE PRUEBA", usuario="usuario@example.invalid", sede="COCHABAMBA",
                  solicitado_por="SOLICITANTE", observacion=None, codigo_estudiante=None):
        it = self._por_clave(clave)
        assert it["ESTADO_ASIGNACION"] == "DISPONIBLE", "P9 solo asigna depósitos DISPONIBLES"
        it.update(ESTADO_ASIGNACION="ASIGNADO", ESTUDIANTE=estudiante, CODIGO_ESTUDIANTE=codigo_estudiante,
                  SOLICITADO_POR=solicitado_por, SEDE_ASIGNACION=sede, USUARIO_ASIGNACION=usuario, OBSERVACION=observacion,
                  FECHA_HORA_ASIGNACION=a_utc_z(self.reloj.replace(microsecond=0).isoformat()))
        self._modificar(it)
        return it["Id"]

    def revertir(self, clave):
        it = self._por_clave(clave)
        assert it["ESTADO_ASIGNACION"] == "ASIGNADO"
        it.update(payload_reversion(str(uuid.uuid5(uuid.NAMESPACE_URL, f"lista-simulada|{clave}|{it['__etag']}"))))
        self._modificar(it)
        return it["Id"]

    def eliminar(self, clave):
        it = self._por_clave(clave)
        del self.items[it["Id"]]
        self.escrituras += 1

    # -- lecturas (lo que devuelve el REST)
    def elemento(self, it, campos=None):
        out = {k: copy.deepcopy(v) for k, v in it.items() if not k.startswith("__")}
        out["__metadata"] = {"etag": f'"{it["__etag"]}"'}
        if campos:
            out = {k: v for k, v in out.items() if k in campos or k == "__metadata"}
        return out

    def consultar(self, desde_utc=None, hasta_utc=None, orden_modified_desc=False, top=5000, campos=None):
        sel = [i for i in self.items.values()
               if (desde_utc is None or i["FECHA_MOVIMIENTO"] >= desde_utc) and (hasta_utc is None or i["FECHA_MOVIMIENTO"] < hasta_utc)]
        sel.sort(key=lambda i: (i["Modified"], i["Id"]), reverse=orden_modified_desc)
        return [self.elemento(i, campos) for i in sel[:top]], len(sel) > top

    @property
    def total(self):
        return len(self.items)
