# -*- coding: utf-8 -*-
"""
p10/snapshot_simulado.py · P10-A.1 · SIMULACIÓN controlada de Depositos_Activos.

Es la ÚNICA simulación de la fase A.1: los campos operativos que normalmente vendrían de la lista
(`ESTADO_ASIGNACION`, `ESTUDIANTE`, `SOLICITADO_POR`, `SEDE_ASIGNACION`, `USUARIO_ASIGNACION`,
`FECHA_HORA_ASIGNACION`, `OBSERVACION`, ...). Los movimientos, claves, importes y saldos NO se simulan:
salen del motor P0 sobre los extractos reales.

Todo lo simulado es reconocible a simple vista (`ESTUDIANTE SIMULADO 0037`, `usuario.simulado.2@example.invalid`,
observaciones que empiezan con `SIMULADO`) y es determinista: depende solo de la CLAVE y de la semilla.

Reglas del modelo real de P9 que se respetan:
  * solo se confirman CRÉDITOS (la app solo lista créditos);
  * el estado vigente es DISPONIBLE | ASIGNADO (la app muestra ASIGNADO como CONFIRMADO);
  * la reversión usa el payload real de P9 (`p9.reversion.contrato.payload_reversion`): vuelve a DISPONIBLE,
    limpia los 7 campos y deja `ULTIMA_REVERSION_ID`.

Uso:  python -m p10.snapshot_simulado <LISTS.csv> <snapshot.json> [porcentaje_confirmados]
"""
import datetime as dt
import hashlib
import sys
import uuid

import historico as H

from . import contrato as C
from .snapshot import Snapshot, cargar_snapshot
from p9.reversion.contrato import payload_reversion

SEMILLA = "P10-A1"
PORCENTAJE_CONFIRMADOS = 12          # % de los CRÉDITOS que nacen confirmados en el snapshot base

# Mayoría vacías (como en la operación real); las demás ejercitan acentos, "=" inicial, salto de línea y ceros.
OBSERVACIONES_SIMULADAS = (
    None, None, None, None, None, None,
    "SIMULADO · pago de matrícula – cuota 2/6 (señal)",
    "=SIMULADO igual al inicio: no debe ser fórmula",
    "SIMULADO · línea 1\nSIMULADO · línea 2",
    "SIMULADO 0004521 código con ceros a la izquierda",
)


def _h(sal, clave):
    return int(hashlib.sha256(f"{sal}|{clave}".encode("utf-8")).hexdigest()[:8], 16)


def _fila_vacia(clave):
    f = {c: None for c in C.CAMPOS_SNAPSHOT}
    f[C.CAMPO_CLAVE] = clave
    f[C.CAMPO_ESTADO] = C.ESTADO_DISPONIBLE
    return f


def _confirmacion(clave, fila_p0, fecha_corte, semilla):
    """Campos operativos de un depósito ASIGNADO (simulados), con fecha posterior al movimiento y ≤ corte."""
    h = _h(semilla + ":confirmacion", clave)
    f = H._fecha(fila_p0["FECHA MOVIMIENTO"])
    hora = H._hora(fila_p0["HORA MOVIMIENTO"]) or dt.time(0)
    movimiento = dt.datetime(f.year, f.month, f.day, hora.hour, hora.minute, hora.second)
    # horario de oficina (08:00-17:59), 0 a 2 días después, y nunca antes del propio movimiento ni después del corte
    cuando = (dt.datetime(f.year, f.month, f.day) + dt.timedelta(days=h % 3, hours=8 + (h // 3) % 10,
                                                                  minutes=(h // 30) % 60))
    cuando = max(cuando, movimiento + dt.timedelta(minutes=10))
    if cuando > fecha_corte:
        cuando = max(movimiento, fecha_corte - dt.timedelta(minutes=1 + h % 50))
    return {
        C.CAMPO_ESTADO: C.ESTADO_ASIGNADO,
        "ESTUDIANTE": f"ESTUDIANTE SIMULADO {1000 + h % 9000:04d}",
        "CODIGO_ESTUDIANTE": f"{h % 7000:07d}" if h % 3 == 0 else None,
        "SOLICITADO_POR": f"SOLICITANTE SIMULADO {'ABC'[h % 3]}",
        "SEDE_ASIGNACION": "COCHABAMBA",
        "USUARIO_ASIGNACION": f"usuario.simulado.{1 + h % 4}@example.invalid",
        "FECHA_HORA_ASIGNACION": cuando.isoformat(),
        "OBSERVACION": OBSERVACIONES_SIMULADAS[(h // 7) % len(OBSERVACIONES_SIMULADAS)],
    }


def _uid_reversion(clave, etiqueta):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"p10-a1-{etiqueta}|{clave}"))


def _corte_por_defecto(filas_p0):
    ultimo = max(H._fecha(r["FECHA MOVIMIENTO"]) for r in filas_p0)
    return dt.datetime(ultimo.year, ultimo.month, ultimo.day, 8, 0) + dt.timedelta(days=1)


def snapshot_simulado(filas_p0, semilla=SEMILLA, porcentaje=PORCENTAJE_CONFIRMADOS, fecha_corte=None):
    """
    Snapshot base (T0): todos los movimientos de P0 en la lista; ~`porcentaje` % de los créditos CONFIRMADOS y, para
    ejercitar ULTIMA_REVERSION_ID como lo deja P9 (el marcador NO se borra nunca): ~2 % de los créditos fueron
    revertidos y vuelven a estar DISPONIBLES, y 1 de cada 8 confirmados lo fue de nuevo después de una reversión previa.
    """
    corte = fecha_corte or _corte_por_defecto(filas_p0)
    filas = []
    for r in sorted(filas_p0, key=lambda x: x[C.COLUMNA_CLAVE]):
        clave = r[C.COLUMNA_CLAVE]
        fila = _fila_vacia(clave)
        if r["TIPO MOVIMIENTO"].strip() == "CRÉDITO":
            sel = _h(semilla + ":seleccion", clave) % 100
            if sel < porcentaje:
                fila.update(_confirmacion(clave, r, corte, semilla))
                if _h(semilla + ":reconfirmado", clave) % 8 == 0:
                    fila["ULTIMA_REVERSION_ID"] = _uid_reversion(clave, "reversion-previa")
            elif sel < porcentaje + 2:
                fila.update(payload_reversion(_uid_reversion(clave, "reversion-previa")))
        filas.append(fila)
    return cargar_snapshot({"version": C.VERSION_SNAPSHOT, "origen": "SIMULADO",
                            "fecha_corte": corte.isoformat(), "filas": filas})


def _copiar(snapshot):
    d = snapshot.a_dict()
    return d, {f[C.CAMPO_CLAVE]: f for f in d["filas"]}


def elegir_a_confirmar(snapshot, filas_p0, cuenta, cantidad, semilla=SEMILLA):
    """Créditos DISPONIBLES de `cuenta` (CUENTA BANCARIA) con menor huella: candidatos deterministas a confirmar."""
    cand = [r[C.COLUMNA_CLAVE] for r in filas_p0
            if r["CUENTA BANCARIA"].strip() == cuenta and r["TIPO MOVIMIENTO"].strip() == "CRÉDITO"
            and snapshot.get(r[C.COLUMNA_CLAVE]) and snapshot.get(r[C.COLUMNA_CLAVE])[C.CAMPO_ESTADO] ==
            C.ESTADO_DISPONIBLE]
    return sorted(cand, key=lambda k: _h(semilla + ":t1", k))[:cantidad]


def elegir_a_revertir(snapshot, cuenta, filas_p0, cantidad, semilla=SEMILLA):
    """Depósitos ASIGNADOS de `cuenta` con menor huella: candidatos deterministas a revertir."""
    de_cuenta = {r[C.COLUMNA_CLAVE] for r in filas_p0 if r["CUENTA BANCARIA"].strip() == cuenta}
    cand = [k for k in de_cuenta if snapshot.get(k) and snapshot.get(k)[C.CAMPO_ESTADO] == C.ESTADO_ASIGNADO]
    return sorted(cand, key=lambda k: _h(semilla + ":t2", k))[:cantidad]


def confirmar(snapshot, filas_p0, claves, semilla=SEMILLA, avance=dt.timedelta(days=1, hours=2)):
    """Nuevo snapshot en el que `claves` pasan de DISPONIBLE a ASIGNADO (la app lo muestra CONFIRMADO)."""
    d, por_clave = _copiar(snapshot)
    corte = snapshot.fecha_corte + avance
    p0 = {r[C.COLUMNA_CLAVE]: r for r in filas_p0}
    for clave in claves:
        fila = por_clave[clave]
        if fila[C.CAMPO_ESTADO] != C.ESTADO_DISPONIBLE:
            raise ValueError(f"{clave} no está DISPONIBLE")
        fila.update(_confirmacion(clave, p0[clave], corte, semilla + ":t1"))
    d["fecha_corte"] = corte.isoformat()
    return cargar_snapshot(d)


def revertir(snapshot, claves, avance=dt.timedelta(hours=3)):
    """Nuevo snapshot en el que `claves` vuelven a DISPONIBLE con el payload REAL de reversión de P9."""
    d, por_clave = _copiar(snapshot)
    for clave in claves:
        fila = por_clave[clave]
        if fila[C.CAMPO_ESTADO] != C.ESTADO_ASIGNADO:
            raise ValueError(f"{clave} no está ASIGNADO")
        fila.update(payload_reversion(str(uuid.uuid5(uuid.NAMESPACE_URL, f"p10-a1-reversion|{clave}"))))
    d["fecha_corte"] = (snapshot.fecha_corte + avance).isoformat()
    return cargar_snapshot(d)


def main(argv):
    if len(argv) not in (3, 4):
        print("Uso: python -m p10.snapshot_simulado <LISTS.csv> <snapshot.json> [porcentaje_confirmados]")
        return 2
    import json
    filas = H.leer_normalizado(argv[1])
    snap = snapshot_simulado(filas, porcentaje=int(argv[3]) if len(argv) == 4 else PORCENTAJE_CONFIRMADOS)
    with open(argv[2], "w", encoding="utf-8", newline="\n") as f:
        json.dump(snap.a_dict(), f, ensure_ascii=False, indent=1)
        f.write("\n")
    n_asig = sum(1 for v in snap.filas.values() if v[C.CAMPO_ESTADO] == C.ESTADO_ASIGNADO)
    print(f"Snapshot SIMULADO: {len(snap)} filas · {n_asig} ASIGNADO · corte {snap.fecha_corte} · {snap.sha256[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
