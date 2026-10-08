# -*- coding: utf-8 -*-
"""
p10/plan.py · P10-A.2 · decisiones de cada ciclo (funciones puras, sin red ni archivos).

El flujo de Power Automate solo recorre listas y llama al servicio; QUÉ hacer en cada ciclo se decide aquí, donde se prueba.

    ciclo      ¿puedo trabajar (lock)? ¿modo NORMAL o COMPLETO? ¿qué meses miro?
    verificar  (solo COMPLETO) archivos de estado/XLSX que faltan o fueron alterados -> reconstruir / forzar
    plan       qué extractos de PROCESADOS hay que incorporar (nuevos, reintentos, a reconstruir)
    clasificar de las filas de Depositos_Activos de un mes, qué grupos cambiaron respecto de lo último aplicado

Datos de control = elementos de la lista `P10_Control` (nombres internos de columna). Fechas = texto ISO en hora de Bolivia.
"""
import re
from datetime import datetime, timedelta

from . import sharepoint as SP
from .estado import hash_lista

MAX_INTENTOS = 3                 # un extracto/grupo con error se reintenta hasta 3 veces; luego espera revisión (ERROR_FINAL)
HORA_COMPLETA = 2                # la reconciliación completa corre en el primer ciclo a partir de las 02:00 (hora Bolivia)
LEASE_MINUTOS = 40               # vigencia del bloqueo lógico; un bloqueo vencido se considera abandonado
VENTANA_MESES = 3                # mes actual + 2 anteriores: lo que la app de Power Apps permite tocar (ventana de 2 meses)
MAX_MESES_LISTAR = 12
MAX_MESES_ESCANEAR = 14
MAX_EXTRACTOS_NORMAL = 10
MAX_EXTRACTOS_COMPLETO = 60
EXTENSIONES = (".xls", ".xlsx")
_RX_PERIODO_RUTA = re.compile(r"/PROCESADOS/(\d{4})/(\d{2})_[A-Z]+/", re.IGNORECASE)


def _ahora(texto):
    return datetime.fromisoformat(texto)


def mes_desplazado(periodo, n):
    """'2026-10' + n meses -> 'AAAA-MM'."""
    anio, mes = (int(x) for x in periodo.split("-"))
    i = anio * 12 + (mes - 1) + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def meses_entre(inicio, fin):
    out, p = [], inicio
    while p <= fin:
        out.append(p)
        p = mes_desplazado(p, 1)
    return out


def _num(v, defecto=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return defecto


def _por_tipo(control, tipo):
    return [i for i in control if i.get("TIPO") == tipo]


def _ruta_onedrive(ruta_servidor, prefijo):
    """'/personal/x/Documents/CONTROL_DEPOSITOS/...' -> '/CONTROL_DEPOSITOS/...' (la ruta que usa el conector de OneDrive)."""
    if prefijo and ruta_servidor.startswith(prefijo):
        ruta_servidor = ruta_servidor[len(prefijo):]
    return ruta_servidor if ruta_servidor.startswith("/") else "/" + ruta_servidor


# ------------------------------------------------------------------ ciclo
def ciclo(ahora_local, control, mes_inicio="2026-10", forzar_completo=False):
    """Primera decisión del ciclo: bloqueo, modo y meses a mirar."""
    ahora = _ahora(ahora_local)
    hoy, actual = ahora.strftime("%Y-%m-%d"), ahora.strftime("%Y-%m")
    lock = next((i for i in control if i.get("CLAVE_CONTROL") == "LOCK"), None)
    if lock is None:
        return {"ok": False, "codigo_error": "LOCK_NO_EXISTE",
                "mensaje": "Falta el elemento LOCK de la lista P10_Control (ver la guía de provisión)."}
    hasta = lock.get("LOCK_HASTA")
    libre = not hasta or _ahora(hasta) <= ahora
    completo = forzar_completo or (ahora.hour >= HORA_COMPLETA and lock.get("ULTIMA_COMPLETA") != hoy)
    ventana = [mes_desplazado(actual, -k) for k in range(VENTANA_MESES)]
    grupos = _por_tipo(control, "GRUPO")
    if completo:
        escanear = sorted({*ventana, *(g["PERIODO"] for g in grupos if g.get("PERIODO"))}, reverse=True)[:MAX_MESES_ESCANEAR]
        listar = meses_entre(max(mes_inicio, mes_desplazado(actual, -(MAX_MESES_LISTAR - 1))), actual)
    else:
        escanear, listar = ventana, [actual, mes_desplazado(actual, -1)]
    huellas = {i["PERIODO"]: i.get("HUELLA") or "" for i in _por_tipo(control, "MES") if i.get("PERIODO")}
    return {
        "ok": True, "modo": "COMPLETO" if completo else "NORMAL", "hoy": hoy, "periodo_actual": actual,
        "lock": {"libre": libre, "item_id": lock.get("Id"), "etag": (lock.get("__metadata") or {}).get("etag"),
                 "ocupado_hasta": hasta or "", "lock_id_actual": lock.get("LOCK_ID") or "",
                 "hasta_nuevo": (ahora + timedelta(minutes=LEASE_MINUTOS)).isoformat(timespec="seconds")},
        "meses_listar": listar, "meses_escanear": escanear, "huellas": huellas,
        "grupos_a_verificar": [g["CLAVE_CONTROL"][len("GRUPO|"):] for g in grupos if g.get("PERIODO") in escanear
                               and _num(g.get("VERSION_ESTADO")) > 0] if completo else [],
        "limite_extractos": MAX_EXTRACTOS_COMPLETO if completo else MAX_EXTRACTOS_NORMAL,
    }


# ------------------------------------------------------------------ verificar (COMPLETO)
def verificar(control, verificaciones):
    """
    `verificaciones`: [{grupo_id, estado_existe, estado_bytes, xlsx_existe, xlsx_bytes}] leídas por el flujo en OneDrive.
    Estado ausente  -> RECONSTRUIR (se reprocesan los extractos del grupo).
    XLSX ausente o con otro tamaño que el último escrito -> forzar su regeneración desde el estado.
    """
    por_gid = {i["CLAVE_CONTROL"][len("GRUPO|"):]: i for i in _por_tipo(control, "GRUPO")}
    reconstruir, forzar, correctos = [], [], 0
    for v in verificaciones:
        c = por_gid.get(v["grupo_id"])
        if c is None or c.get("ESTADO") == "RECONSTRUIR":
            continue
        if not v.get("estado_existe"):
            reconstruir.append({"grupo_id": v["grupo_id"], "motivo": "ESTADO_AUSENTE", "item_id": c.get("Id")})
        elif _num(c.get("ESTADO_BYTES")) and _num(v.get("estado_bytes")) != _num(c.get("ESTADO_BYTES")):
            reconstruir.append({"grupo_id": v["grupo_id"], "motivo": "ESTADO_ALTERADO", "item_id": c.get("Id")})
        elif not v.get("xlsx_existe"):
            forzar.append({"grupo_id": v["grupo_id"], "motivo": "XLSX_AUSENTE"})
        elif _num(c.get("XLSX_BYTES")) and _num(v.get("xlsx_bytes")) != _num(c.get("XLSX_BYTES")):
            forzar.append({"grupo_id": v["grupo_id"], "motivo": "XLSX_ALTERADO"})
        else:
            correctos += 1
    return {"ok": True, "reconstruir": reconstruir, "forzar": forzar, "correctos": correctos}


# ------------------------------------------------------------------ plan de extractos
def plan(ahora_local, modo, archivos, control, prefijo_servidor, limite):
    """
    `archivos`: lo que lista el flujo en PROCESADOS [{ServerRelativeUrl, Name, Length, TimeCreated}].
    Devuelve los extractos a incorporar, en orden cronológico (los acumulativos más nuevos van al final).
    """
    ledger = {i["CLAVE_CONTROL"]: i for i in _por_tipo(control, "EXTRACTO")}
    reconstruir = {i["CLAVE_CONTROL"][len("GRUPO|"):] for i in _por_tipo(control, "GRUPO") if i.get("ESTADO") == "RECONSTRUIR"}
    cola, finales = [], 0
    for a in sorted(archivos, key=lambda x: (str(x.get("TimeCreated") or ""), str(x.get("Name") or ""))):
        nombre = str(a.get("Name") or "")
        if not nombre.lower().endswith(EXTENSIONES) or nombre.startswith("~$"):
            continue
        ruta = _ruta_onedrive(str(a.get("ServerRelativeUrl") or ""), prefijo_servidor)
        clave = "EXTRACTO|" + ruta
        it = ledger.get(clave)
        razon = None
        if it is None:
            razon = "NUEVO"
        elif it.get("ESTADO") == "PROCESADO":
            if _num(a.get("Length")) and _num(it.get("BYTES")) and _num(a.get("Length")) != _num(it.get("BYTES")):
                razon = "MODIFICADO"
            elif reconstruir & {g for g in str(it.get("GRUPOS") or "").split(";") if g}:
                razon = "RECONSTRUIR"
        elif it.get("ESTADO") == "ERROR_FINAL" or _num(it.get("INTENTOS")) >= MAX_INTENTOS:
            finales += 1
        else:
            razon = "REINTENTO"
        if razon:
            m = _RX_PERIODO_RUTA.search(ruta)
            cola.append({"ruta": ruta, "nombre": nombre, "bytes": _num(a.get("Length")), "razon": razon,
                         "clave_control": clave, "intentos": _num((it or {}).get("INTENTOS")),
                         "periodo": f"{m.group(1)}-{m.group(2)}" if m else ahora_local[:7]})
    return {"ok": True, "extractos": cola[:limite], "pendientes": max(0, len(cola) - limite), "error_final": finales}


# ------------------------------------------------------------------ clasificar un mes de la lista
def clasificar(periodo, items, control, modo, hay_mas, forzar=()):
    """
    Agrupa las filas de Depositos_Activos del mes y decide qué grupos hay que regenerar.
    `forzar`: [{grupo_id}] de `verificar` (XLSX ausente/alterado): se regeneran aunque la lista no haya cambiado.
    """
    if hay_mas:
        return {"ok": False, "codigo_error": "MES_EXCEDE_LIMITE",
                "mensaje": "La consulta del mes devolvió más de 5000 elementos; hay que dividirla por BANCO."}
    grupos, anomalias = SP.agrupar(items)
    ctrl = {i["CLAVE_CONTROL"][len("GRUPO|"):]: i for i in _por_tipo(control, "GRUPO")}
    pedidos = {f["grupo_id"] for f in forzar}
    sucios, sin_estado, en_espera, fuera = [], [], [], 0
    for gid, filas in sorted(grupos.items()):
        if not gid.endswith("|" + periodo):
            fuera += len(filas)                       # vecinos del borde de mes traídos por la ventana de la consulta
            continue
        h = hash_lista(filas)
        c = ctrl.get(gid)
        if c is None or _num(c.get("VERSION_ESTADO")) == 0:
            sin_estado.append(gid)                    # la lista ya tiene movimientos cuyo extracto P10 aún no incorporó
            continue
        if c.get("ESTADO") == "RECONSTRUIR":
            en_espera.append(gid)
            continue
        forzado = gid in pedidos
        if h == (c.get("HASH_OPERATIVO") or "") and not forzado:
            continue
        agotado = (c.get("ESTADO") == "ERROR" and (c.get("HASH_INTENTO") or "") == h
                   and _num(c.get("INTENTOS")) >= MAX_INTENTOS and modo != "COMPLETO")
        if agotado:
            en_espera.append(gid)
            continue
        sucios.append({"grupo_id": gid, "filas": filas, "hash_lista": h, "forzar_xlsx": forzado,
                       "intentos": _num(c.get("INTENTOS"))})
    for gid in sorted(pedidos - {s["grupo_id"] for s in sucios}):   # forzados sin filas en la lista del mes
        if gid.endswith("|" + periodo) and gid in ctrl and gid not in grupos:
            sucios.append({"grupo_id": gid, "filas": None, "hash_lista": "", "forzar_xlsx": True,
                           "intentos": _num(ctrl[gid].get("INTENTOS"))})
    return {"ok": True, "periodo": periodo, "elementos": len(items), "grupos_en_lista": len(grupos), "sucios": sucios,
            "sin_estado": sin_estado, "en_espera": en_espera, "fuera_de_periodo": fuera, "anomalias": anomalias[:20]}
