# -*- coding: utf-8 -*-
"""
p10/sharepoint.py · P10-A.2 · adaptador de los elementos REALES de `Depositos_Activos` (REST de SharePoint) a filas de P10.

* SharePoint entrega las fechas con hora en UTC («2026-10-08T14:29:00Z»); Power Apps las muestra en hora de Bolivia. Aquí se
  convierten a hora local (America/La_Paz, UTC-4 sin horario de verano) como texto ISO sin zona: es lo que A.1 acepta y lo que ve el usuario.
* El mes de un movimiento sale de su CLAVE TRANSACCIÓN (segmento AAAAMMDD), nunca de `FECHA_MOVIMIENTO`: esa columna es «solo fecha» y su
  conversión de zona puede correrse un día en el borde del mes. Es LEER la clave, no calcularla: la fórmula sigue en P0 (`crear_clave`).
  Si la clave no trae una fecha válida se recurre a `FECHA_MOVIMIENTO`.
"""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import contrato as C
from .estado import CAMPOS_LISTA, grupo_id

ZONA_LOCAL = ZoneInfo("America/La_Paz")
CAMPOS_SELECT = ("Id,Modified,CLAVE_TRANSACCION,BANCO,CUENTA_BANCARIA,MONEDA,FECHA_MOVIMIENTO,"
                 + ",".join(CAMPOS_LISTA))
_RX_FECHA_CLAVE = re.compile(r"^\d{8}$")


class FilaInvalida(ValueError):
    pass


def utc_a_local(texto):
    """'2026-10-08T14:29:00Z' -> '2026-10-08T10:29:00' (hora de Bolivia, sin zona). Vacío -> None."""
    if texto in (None, ""):
        return None
    t = str(texto).strip()
    d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    if d.tzinfo is None:                      # sin zona: SharePoint siempre entrega UTC
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(ZONA_LOCAL).replace(microsecond=0, tzinfo=None).isoformat()


def _texto(v):
    return "" if v is None else (v if isinstance(v, str) else str(v))


def periodo_de_clave(clave, fecha_movimiento=None):
    partes = str(clave).split("|")
    if len(partes) >= 3 and _RX_FECHA_CLAVE.match(partes[2]):
        return f"{partes[2][:4]}-{partes[2][4:6]}"
    if fecha_movimiento:
        return str(fecha_movimiento)[:7]
    raise FilaInvalida(f"la CLAVE no trae fecha de movimiento: {clave!r}")


def fila_lista(item):
    """Elemento REST -> (grupo_id, fila normalizada con los 12 campos de la foto operativa + la clave)."""
    clave = item.get("CLAVE_TRANSACCION")
    if not isinstance(clave, str) or not clave:
        raise FilaInvalida("elemento sin CLAVE_TRANSACCION")
    banco, cuenta, moneda = (_texto(item.get(k)).strip() for k in ("BANCO", "CUENTA_BANCARIA", "MONEDA"))
    if not (banco and cuenta and moneda):
        raise FilaInvalida(f"elemento sin BANCO/CUENTA/MONEDA: {clave}")
    fila = {"CLAVE_TRANSACCION": clave}
    for campo in CAMPOS_LISTA:
        fila[campo] = _texto(item.get(campo))
    fila["FECHA_HORA_ASIGNACION"] = utc_a_local(item.get("FECHA_HORA_ASIGNACION"))
    for campo in ("ULTIMA_REVERSION_ID", "OBSERVACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR",
                  "SEDE_ASIGNACION", "USUARIO_ASIGNACION"):
        fila[campo] = fila[campo] or None      # vacío = null, igual que deja una reversión (payload_reversion)
    periodo = periodo_de_clave(clave, _texto(item.get("FECHA_MOVIMIENTO")))
    return grupo_id(banco, cuenta, moneda, periodo), fila


def agrupar(items):
    """Lista de elementos REST -> ({grupo_id: [filas]}, [anomalías]). Un elemento inválido no detiene al resto."""
    grupos, anomalias, vistas = {}, [], set()
    for it in items:
        try:
            gid, fila = fila_lista(it)
        except FilaInvalida as e:
            anomalias.append(str(e)[:200])
            continue
        if fila["CLAVE_TRANSACCION"] in vistas:
            anomalias.append(f"CLAVE repetida en la lista: {fila['CLAVE_TRANSACCION'][:80]}")
            continue
        vistas.add(fila["CLAVE_TRANSACCION"])
        grupos.setdefault(gid, []).append(fila)
    return grupos, anomalias
