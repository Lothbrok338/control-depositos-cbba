# -*- coding: utf-8 -*-
"""
p10/snapshot.py · P10-A.1 · lectura y validación del snapshot operativo (equivalente a Depositos_Activos).

El snapshot es la "foto" de los campos operativos de la lista, con los NOMBRES INTERNOS REALES de P8/P9
(`ESTADO_ASIGNACION`, `USUARIO_ASIGNACION`, `FECHA_HORA_ASIGNACION`, ...), indexada por `CLAVE_TRANSACCION`.
Hoy lo produce `snapshot_simulado.py`; mañana será la lectura de la lista en el tenant, con este mismo formato:

    {"version": "P10-SNAPSHOT-1", "origen": "SIMULADO" | "DEPOSITOS_ACTIVOS",
     "fecha_corte": "2026-08-21T08:00:00",
     "filas": [{"CLAVE_TRANSACCION": "...", "ESTADO_ASIGNACION": "ASIGNADO", "ESTUDIANTE": "...", ...}]}

Reglas (fallan con SnapshotError; ninguna se "corrige" en silencio):
  * `CLAVE_TRANSACCION` obligatoria y única (se compara exacta, sin trim ni cambio de mayúsculas);
  * `ESTADO_ASIGNACION` debe ser uno de los estados vigentes de P9 (DISPONIBLE | ASIGNADO);
  * `FECHA_HORA_ASIGNACION` debe ser ISO sin zona horaria. Una fecha con zona (Z / +hh:mm) se rechaza:
    la conversión de zona horaria de SharePoint está PENDIENTE de definir en P10-A.2 y no se adivina.
Lo dudoso pero no estructural (un ASIGNADO incompleto, un DISPONIBLE con datos residuales) se informa en
`advertencias` y no impide generar el archivo.
"""
import datetime as dt
import hashlib
import json
import os

from .contrato import (CAMPO_CLAVE, CAMPO_ESTADO, CAMPOS_SNAPSHOT, ESTADOS, ESTADO_ASIGNADO,
                       ESTADO_DISPONIBLE, OBLIGATORIOS_ASIGNADO, VERSION_SNAPSHOT)
from p9.reversion.contrato import CAMPOS_LIMPIAR

MAX_ADVERTENCIAS = 50


class SnapshotError(ValueError):
    """El snapshot no es utilizable; el mensaje dice qué fila y por qué."""


def _texto(v):
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def _fecha_hora(v, clave):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, dt.datetime):
        d = v
    elif isinstance(v, dt.date):
        d = dt.datetime(v.year, v.month, v.day)
    else:
        try:
            d = dt.datetime.fromisoformat(str(v).strip())
        except ValueError:
            raise SnapshotError(f"{clave}: FECHA_HORA_ASIGNACION no es ISO: {v!r}")
    if d.tzinfo is not None:
        raise SnapshotError(
            f"{clave}: FECHA_HORA_ASIGNACION trae zona horaria ({v!r}); la conversión de zona "
            "queda pendiente de definir en P10-A.2")
    return d.replace(microsecond=0)


class Snapshot:
    """Filas ya validadas y tipadas: {CLAVE_TRANSACCION: {campo: valor}} (texto '' = vacío; fecha = datetime|None)."""

    def __init__(self, filas, origen="DESCONOCIDO", fecha_corte=None, version=VERSION_SNAPSHOT,
                 advertencias=None):
        self.filas = filas
        self.origen = origen
        self.fecha_corte = fecha_corte
        self.version = version
        self.advertencias = list(advertencias or [])
        self._sha256 = None

    def __len__(self):
        return len(self.filas)

    def get(self, clave):
        return self.filas.get(clave)

    @property
    def sha256(self):
        """Huella del CONTENIDO (no del formato del archivo): igual snapshot lógico -> igual huella."""
        if self._sha256 is not None:
            return self._sha256
        canon = [dict(f, **{CAMPO_CLAVE: k, "FECHA_HORA_ASIGNACION": (
            f["FECHA_HORA_ASIGNACION"].isoformat() if f["FECHA_HORA_ASIGNACION"] else None)})
            for k, f in sorted(self.filas.items())]
        txt = json.dumps({"origen": self.origen, "fecha_corte": self.fecha_corte.isoformat()
                          if self.fecha_corte else None, "filas": canon},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._sha256 = hashlib.sha256(txt.encode("utf-8")).hexdigest()
        return self._sha256

    def a_dict(self):
        """Forma serializable (la que lee `cargar_snapshot`), filas ordenadas por clave."""
        filas = []
        for clave in sorted(self.filas):
            f = self.filas[clave]
            fila = {CAMPO_CLAVE: clave}
            for campo in CAMPOS_SNAPSHOT[1:]:
                v = f[campo]
                fila[campo] = v.isoformat() if isinstance(v, dt.datetime) else (v if v != "" else None)
            filas.append(fila)
        return {"version": self.version, "origen": self.origen,
                "fecha_corte": self.fecha_corte.isoformat() if self.fecha_corte else None,
                "filas": filas}


def cargar_snapshot(fuente):
    """Ruta a un JSON, dict con la forma de arriba, o lista de filas -> Snapshot validado."""
    if isinstance(fuente, Snapshot):
        return fuente
    if isinstance(fuente, (str, os.PathLike)):
        with open(fuente, encoding="utf-8") as f:
            fuente = json.load(f)
    if isinstance(fuente, list):
        fuente = {"filas": fuente}
    if not isinstance(fuente, dict) or not isinstance(fuente.get("filas"), list):
        raise SnapshotError("el snapshot debe ser {'filas': [...]} o una lista de filas")
    version = fuente.get("version", VERSION_SNAPSHOT)
    if version != VERSION_SNAPSHOT:
        raise SnapshotError(f"versión de snapshot no soportada: {version!r} (se esperaba {VERSION_SNAPSHOT})")
    corte = fuente.get("fecha_corte")
    fecha_corte = _fecha_hora(corte, "fecha_corte") if corte else None

    filas, advertencias, repetidas = {}, [], []

    def avisar(msg):
        if len(advertencias) < MAX_ADVERTENCIAS:
            advertencias.append(msg)

    for i, crudo in enumerate(fuente["filas"], start=1):
        if not isinstance(crudo, dict):
            raise SnapshotError(f"fila {i}: no es un objeto")
        clave = crudo.get(CAMPO_CLAVE)
        if not isinstance(clave, str) or not clave:
            raise SnapshotError(f"fila {i}: falta {CAMPO_CLAVE}")
        if clave in filas:
            repetidas.append(clave)
            continue
        estado = crudo.get(CAMPO_ESTADO)
        if estado not in ESTADOS:
            raise SnapshotError(f"{clave}: {CAMPO_ESTADO}={estado!r} no es un estado vigente {ESTADOS}")
        fila = {c: _texto(crudo.get(c)) for c in CAMPOS_SNAPSHOT[1:]}
        fila[CAMPO_ESTADO] = estado
        fila["FECHA_HORA_ASIGNACION"] = _fecha_hora(crudo.get("FECHA_HORA_ASIGNACION"), clave)
        if estado == ESTADO_ASIGNADO:
            faltan = [c for c in OBLIGATORIOS_ASIGNADO if not fila[c]]
            if faltan:
                avisar(f"{clave}: ASIGNADO sin {', '.join(faltan)}")
        else:
            restos = [c for c in CAMPOS_LIMPIAR if fila[c]]
            if restos:
                avisar(f"{clave}: DISPONIBLE con datos residuales en {', '.join(restos)}")
        filas[clave] = fila
    if repetidas:
        raise SnapshotError(f"CLAVE_TRANSACCION repetida en el snapshot ({len(repetidas)}): {repetidas[:3]}")
    return Snapshot(filas, origen=str(fuente.get("origen", "DESCONOCIDO")), fecha_corte=fecha_corte,
                    version=version, advertencias=advertencias)
