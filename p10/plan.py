# -*- coding: utf-8 -*-
"""
p10/plan.py · P10-A.2 · decisiones de cada ciclo (funciones puras, sin red ni archivos).

El flujo de Power Automate solo recorre listas y llama al servicio; QUÉ hacer en cada ciclo se decide aquí, donde se prueba.

    ciclo      ¿puedo trabajar (lock)? ¿modo NORMAL o COMPLETO? ¿qué meses miro? ¿qué grupos verifico?
    plan       qué extractos de PROCESADOS hay que incorporar (nuevos, reintentos, a reconstruir)
    clasificar de las filas de Depositos_Activos de un mes, qué grupos cambiaron respecto de lo último aplicado

La verificación de archivos (estado/XLSX perdidos o alterados) NO se decide aquí: la hace `sincronizacion.sincronizar_grupo` al comparar
el contenido real con los sellos guardados; aquí solo se elige QUÉ grupos verificar en cada ciclo.

Datos de control = elementos de la lista `P10_Control` (nombres internos de columna). Fechas = texto ISO en hora de Bolivia.
"""
import hashlib
import re
from datetime import datetime, timedelta

from . import sharepoint as SP
from .estado import hash_lista

MAX_INTENTOS = 3                 # un extracto/grupo con error se reintenta hasta 3 veces; luego espera revisión (ERROR_FINAL)
HORA_COMPLETA = 2                # la reconciliación completa corre en el primer ciclo a partir de las 02:00 (hora Bolivia)
LEASE_MINUTOS = 60               # vigencia del bloqueo lógico; un bloqueo vencido se considera abandonado (la plataforma ya serializa las ejecuciones)
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


def clave_extracto(ruta):
    """Clave del registro de un extracto: su ruta en OneDrive; si no cabe en una columna de 255, la huella SHA-256 de la ruta."""
    clave = "EXTRACTO|" + ruta
    return clave if len(clave) <= 240 else "EXTRACTO|#" + hashlib.sha256(ruta.encode("utf-8")).hexdigest()


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
        # Verificación de archivos: cada noche los grupos de la ventana; los domingos, todos los meses conocidos.
        verificar = escanear if ahora.weekday() == 6 else ventana
        a_verificar = [g["CLAVE_CONTROL"][len("GRUPO|"):] for g in grupos
                       if g.get("PERIODO") in verificar and g.get("ESTADO") != "RECONSTRUIR" and _num(g.get("VERSION_ESTADO")) > 0]
    else:
        escanear, listar, a_verificar = ventana, [actual, mes_desplazado(actual, -1)], []
    huellas = {i["PERIODO"]: i.get("HUELLA") or "" for i in _por_tipo(control, "MES") if i.get("PERIODO")}
    # meses con trabajo pendiente aunque la lista no haya cambiado: grupos con error por reintentar o en reconstrucción
    pendientes = sorted({g["PERIODO"] for g in grupos if g.get("PERIODO") in escanear and (
        g.get("ESTADO") == "RECONSTRUIR" or (g.get("ESTADO") == "ERROR" and _num(g.get("INTENTOS")) < MAX_INTENTOS))})
    return {
        "ok": True, "modo": "COMPLETO" if completo else "NORMAL", "hoy": hoy, "periodo_actual": actual,
        "lock": {"libre": libre, "item_id": lock.get("Id"), "etag": (lock.get("__metadata") or {}).get("etag"),
                 "ocupado_hasta": hasta or "", "lock_id_actual": lock.get("LOCK_ID") or "",
                 "hasta_nuevo": (ahora + timedelta(minutes=LEASE_MINUTOS)).isoformat(timespec="seconds")},
        "meses_listar": listar, "meses_escanear": escanear, "meses_pendientes": pendientes, "huellas": huellas,
        "grupos_a_verificar": a_verificar,
        "limite_extractos": MAX_EXTRACTOS_COMPLETO if completo else MAX_EXTRACTOS_NORMAL,
    }


# ------------------------------------------------------------------ plan de extractos
def _grupos_de(item):
    return {g for g in str(item.get("GRUPOS") or "").split(";") if g}


def extractos_pendientes_de_reconstruccion(gid, grupo, control):
    """Extractos que alimentaron `gid` y aún no se reincorporaron desde que el grupo quedó marcado RECONSTRUIR."""
    desde = grupo.get("RECONSTRUIR_DESDE") or ""
    return [e for e in _por_tipo(control, "EXTRACTO")
            if gid in _grupos_de(e) and (e.get("ESTADO") != "PROCESADO" or (e.get("ULTIMA_SYNC") or "") <= desde)]


def plan(ahora_local, modo, archivos, control, prefijo_servidor, limite):
    """
    `archivos`: lo que lista el flujo en PROCESADOS [{ServerRelativeUrl, Name, Length, TimeCreated}].
    Devuelve los extractos a incorporar, en orden cronológico (los acumulativos más nuevos van al final).
    Los extractos de grupos en reconstrucción no cuentan para el límite: la marca solo se quita cuando todos se reincorporaron.
    """
    ledger = {i["CLAVE_CONTROL"]: i for i in _por_tipo(control, "EXTRACTO")}
    marcados = {i["CLAVE_CONTROL"][len("GRUPO|"):]: i for i in _por_tipo(control, "GRUPO") if i.get("ESTADO") == "RECONSTRUIR"}
    cola, finales = [], 0
    for a in sorted(archivos, key=lambda x: (str(x.get("TimeCreated") or ""), str(x.get("Name") or ""))):
        nombre = str(a.get("Name") or "")
        if not nombre.lower().endswith(EXTENSIONES) or nombre.startswith("~$"):
            continue
        ruta = _ruta_onedrive(str(a.get("ServerRelativeUrl") or ""), prefijo_servidor)
        clave = clave_extracto(ruta)
        it = ledger.get(clave)
        razon = None
        if it is None:
            razon = "NUEVO"
        elif it.get("ESTADO") == "PROCESADO":
            if _num(a.get("Length")) and _num(it.get("BYTES")) and _num(a.get("Length")) != _num(it.get("BYTES")):
                razon = "MODIFICADO"
            elif any(gid in marcados and extractos_pendientes_de_reconstruccion(gid, marcados[gid], control) and
                     (it.get("ULTIMA_SYNC") or "") <= (marcados[gid].get("RECONSTRUIR_DESDE") or "") for gid in _grupos_de(it)):
                razon = "RECONSTRUIR"
        elif it.get("ESTADO") == "ERROR_FINAL" or _num(it.get("INTENTOS")) >= MAX_INTENTOS:
            finales += 1
        else:
            razon = "REINTENTO"
        if razon:
            m = _RX_PERIODO_RUTA.search(ruta)
            cola.append({"ruta": ruta, "nombre": nombre, "bytes": _num(a.get("Length")), "razon": razon, "clave_control": clave,
                         "item_id": (it or {}).get("Id"), "intentos": _num((it or {}).get("INTENTOS")),
                         "periodo": f"{m.group(1)}-{m.group(2)}" if m else ahora_local[:7]})
    obligatorios = [e for e in cola if e["razon"] == "RECONSTRUIR"]
    resto = [e for e in cola if e["razon"] != "RECONSTRUIR"]
    elegidos = obligatorios + resto[:max(0, limite - len(obligatorios))]
    elegidos.sort(key=lambda e: cola.index(e))
    return {"ok": True, "extractos": elegidos, "pendientes": len(cola) - len(elegidos), "error_final": finales}


# ------------------------------------------------------------------ clasificar un mes de la lista
def clasificar(periodo, items, control, modo, hay_mas, verificar=()):
    """
    Agrupa las filas de Depositos_Activos del mes y decide qué grupos hay que sincronizar:
      * la lista cambió respecto de lo último aplicado, o el grupo quedó con error por reintentar;
      * `verificar` (ciclo COMPLETO): se sincroniza aunque nada haya cambiado, comparando los archivos reales con sus sellos;
      * grupo en reconstrucción cuyos extractos ya se reincorporaron todos: se sincroniza para quitarle la marca (`finalizar`).
    """
    if hay_mas:
        return {"ok": False, "codigo_error": "MES_EXCEDE_LIMITE",
                "mensaje": "La consulta del mes devolvió más de 5000 elementos; hay que dividirla por BANCO."}
    grupos, anomalias = SP.agrupar(items)
    ctrl = {i["CLAVE_CONTROL"][len("GRUPO|"):]: i for i in _por_tipo(control, "GRUPO")}
    pedidos = set(verificar)
    sucios, sin_estado, en_espera, fuera = [], [], [], 0

    def sucio(gid, filas, h, c, forzado, finalizar):
        sucios.append({"grupo_id": gid, "filas": filas, "hash_lista": h, "verificar_xlsx": forzado, "finalizar": finalizar,
                       "intentos": _num(c.get("INTENTOS"))})

    def procesar(gid, filas):
        h = hash_lista(filas) if filas is not None else ""
        c = ctrl.get(gid)
        if c is None or (_num(c.get("VERSION_ESTADO")) == 0 and c.get("ESTADO") != "RECONSTRUIR"):
            if filas is not None:
                sin_estado.append(gid)               # la lista ya tiene movimientos cuyo extracto P10 aún no incorporó
            return
        if c.get("ESTADO") == "RECONSTRUIR":
            if extractos_pendientes_de_reconstruccion(gid, c, control):
                en_espera.append(gid)
            else:
                sucio(gid, filas, h, c, False, True)
            return
        forzado = gid in pedidos
        if filas is None:                            # grupo sin filas en la lista: solo se sincroniza para verificarlo
            if forzado:
                sucio(gid, None, "", c, True, False)
            return
        if h == (c.get("HASH_OPERATIVO") or "") and c.get("ESTADO") == "OK" and not forzado:
            return
        agotado = (c.get("ESTADO") == "ERROR" and (c.get("HASH_INTENTO") or "") == h
                   and _num(c.get("INTENTOS")) >= MAX_INTENTOS and modo != "COMPLETO")
        if agotado:
            en_espera.append(gid)
            return
        sucio(gid, filas, h, c, forzado, False)

    for gid, filas in sorted(grupos.items()):
        if not gid.endswith("|" + periodo):
            fuera += len(filas)                       # vecinos del borde de mes traídos por la ventana de la consulta
            continue
        procesar(gid, filas)
    for gid in sorted(ctrl):
        if gid.endswith("|" + periodo) and gid not in grupos and (gid in pedidos or ctrl[gid].get("ESTADO") == "RECONSTRUIR"):
            procesar(gid, None)
    return {"ok": True, "periodo": periodo, "elementos": len(items), "grupos_en_lista": len(grupos), "sucios": sucios,
            "sin_estado": sin_estado, "en_espera": en_espera, "fuera_de_periodo": fuera, "anomalias": anomalias[:20]}
