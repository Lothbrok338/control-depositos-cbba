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
FORMATO_UTC = "%Y-%m-%dT%H:%M:%SZ"
ASENTAR_MIN = 5                  # una fila modificada hace menos de 5 min se aplica, pero el cursor no la deja atrás hasta que «asiente»
MAX_SLICES = 60                  # pares BANCO+MES que se concilian con la lista completa en un ciclo


def a_utc(ahora_local):
    """Hora de Bolivia (UTC-4, sin horario de verano) -> texto UTC como lo entrega SharePoint."""
    return (_ahora(ahora_local) + timedelta(hours=4)).strftime(FORMATO_UTC)


def ciclo(ahora_local, control, mes_inicio="2026-09", forzar_completo=False):
    """Primera decisión del ciclo: bloqueo, modo, qué listar en PROCESADOS, desde dónde leer la lista y qué conciliar por completo."""
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
    cursor = str(lock.get("CURSOR_LISTA") or "")
    try:
        desde = datetime.strptime(cursor, FORMATO_UTC)
    except ValueError:                               # sin cursor (primera vez): el día anterior; el ciclo completo concilia el resto
        desde = ahora + timedelta(hours=4) - timedelta(days=1)
    conciliar = set()
    if completo:
        listar = meses_entre(max(mes_inicio, mes_desplazado(actual, -(MAX_MESES_LISTAR - 1))), actual)
        # Cada noche se concilian con la lista completa los grupos de la ventana; los domingos, todos los meses conocidos.
        todos = sorted({*ventana, *(g["PERIODO"] for g in grupos if g.get("PERIODO"))}, reverse=True)[:MAX_MESES_ESCANEAR]
        verificar = todos if ahora.weekday() == 6 else ventana
        a_verificar = [g["CLAVE_CONTROL"][len("GRUPO|"):] for g in grupos
                       if g.get("PERIODO") in verificar and g.get("ESTADO") != "RECONSTRUIR" and _num(g.get("VERSION_ESTADO")) > 0]
        conciliar |= {(g["PERIODO"], g.get("BANCO") or "") for g in grupos if g.get("PERIODO") in verificar}
    else:
        listar, a_verificar = [actual, mes_desplazado(actual, -1)], []
    # grupos con trabajo pendiente aunque la lista no haya cambiado: error por reintentar, reconstrucción por finalizar
    conciliar |= {(g["PERIODO"], g.get("BANCO") or "") for g in grupos if g.get("PERIODO") and (
        g.get("ESTADO") == "RECONSTRUIR" or (g.get("ESTADO") == "ERROR" and _num(g.get("INTENTOS")) < MAX_INTENTOS))}
    slices = [{"periodo": p, "banco": b} for p, b in sorted(conciliar, reverse=True) if b][:MAX_SLICES]
    return {
        "ok": True, "modo": "COMPLETO" if completo else "NORMAL", "hoy": hoy, "periodo_actual": actual,
        "lock": {"libre": libre, "item_id": lock.get("Id"), "etag": (lock.get("__metadata") or {}).get("etag"),
                 "ocupado_hasta": hasta or "", "lock_id_actual": lock.get("LOCK_ID") or "",
                 "hasta_nuevo": (ahora + timedelta(minutes=LEASE_MINUTOS)).isoformat(timespec="seconds")},
        "meses_listar": listar, "cursor_desde": desde.strftime(FORMATO_UTC), "slices": slices,
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


# ------------------------------------------------------------------ lectura incremental de la lista (delta por Modified)
def delta(items, control, ahora_local, cursor_desde=""):
    """
    Lo que cambió en Depositos_Activos desde el cursor (`Modified > cursor`): normalmente nada o unas pocas filas.
    Se aplican a su grupo como información parcial (las filas ausentes NO se tocan). Devuelve además el cursor nuevo:
      * solo avanza sobre filas «asentadas» (modificadas hace más de ASENTAR_MIN minutos): las más recientes se leen otra vez
        en el ciclo siguiente por si SharePoint aún no mostraba otra fila de la misma hora;
      * no pasa de largo las filas cuyo grupo aún no tiene estado (su extracto todavía no se incorporó), hasta 24 h:
        pasado ese plazo manda la conciliación completa de la noche.
    """
    ctrl = {i["CLAVE_CONTROL"][len("GRUPO|"):]: i for i in _por_tipo(control, "GRUPO")}
    por_gid, modificados, anomalias, vistas = {}, {}, [], set()
    for it in items:
        try:
            gid, fila = SP.fila_lista(it)
        except SP.FilaInvalida as e:
            anomalias.append(str(e)[:200])
            continue
        if fila["CLAVE_TRANSACCION"] in vistas:
            anomalias.append(f"CLAVE repetida en la lista: {fila['CLAVE_TRANSACCION'][:80]}")
            continue
        vistas.add(fila["CLAVE_TRANSACCION"])
        por_gid.setdefault(gid, []).append(fila)
        modificados.setdefault(gid, []).append(str(it.get("Modified") or ""))
    sucios, sin_estado, en_espera, retenidas = [], [], [], []
    for gid in sorted(por_gid):
        c = ctrl.get(gid)
        if c is None or (_num(c.get("VERSION_ESTADO")) == 0 and c.get("ESTADO") != "RECONSTRUIR"):
            sin_estado.append(gid)
            retenidas += modificados[gid]
        elif c.get("ESTADO") == "RECONSTRUIR":
            en_espera.append(gid)                      # la conciliación completa del grupo lo atiende
        else:
            sucios.append({"grupo_id": gid, "filas": por_gid[gid], "parcial_lista": True, "verificar_xlsx": False,
                           "finalizar": False, "intentos": _num(c.get("INTENTOS"))})
    asentado = (_ahora(ahora_local) + timedelta(hours=4, minutes=-ASENTAR_MIN)).strftime(FORMATO_UTC)
    todas = [str(i.get("Modified")) for i in items if i.get("Modified") and str(i.get("Modified")) <= asentado]
    cursor_nuevo = max(todas) if todas else ""
    retenidas = [m for m in retenidas if m]
    if retenidas and min(retenidas) > (_ahora(ahora_local) + timedelta(hours=4, days=-1)).strftime(FORMATO_UTC):
        un_segundo_antes = (datetime.strptime(min(retenidas), FORMATO_UTC) - timedelta(seconds=1)).strftime(FORMATO_UTC)
        cursor_nuevo = min(cursor_nuevo, un_segundo_antes) if cursor_nuevo else un_segundo_antes
    if cursor_nuevo and cursor_nuevo <= cursor_desde:                         # nunca retrocede ni repite el mismo valor
        cursor_nuevo = ""
    return {"ok": True, "elementos": len(items), "sucios": sucios, "sin_estado": sin_estado, "en_espera": en_espera,
            "cursor_nuevo": cursor_nuevo, "anomalias": anomalias[:20]}


# ------------------------------------------------------------------ conciliar un BANCO+MES con la lista completa
def clasificar(periodo, items, control, modo, hay_mas, verificar=(), banco=None):
    """
    Agrupa las filas de Depositos_Activos de un BANCO en un mes (`banco=None`: todo el mes) y decide qué grupos sincronizar:
      * la lista difiere de lo último conciliado, o el grupo quedó con error por reintentar;
      * `verificar` (ciclo COMPLETO): se sincroniza aunque nada haya cambiado, comparando los archivos reales con sus sellos;
      * grupo en reconstrucción cuyos extractos ya se reincorporaron todos: se sincroniza para quitarle la marca (`finalizar`).
    """
    if hay_mas:
        return {"ok": False, "codigo_error": "REBANADA_EXCEDE_LIMITE",
                "mensaje": "La consulta de BANCO+MES devolvió 5000 elementos o más; no se puede conciliar con certeza."}
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
        if (gid.endswith("|" + periodo) and gid not in grupos and (banco is None or ctrl[gid].get("BANCO") == banco)
                and (gid in pedidos or ctrl[gid].get("ESTADO") == "RECONSTRUIR")):
            procesar(gid, None)
    return {"ok": True, "periodo": periodo, "elementos": len(items), "grupos_en_lista": len(grupos), "sucios": sucios,
            "sin_estado": sin_estado, "en_espera": en_espera, "fuera_de_periodo": fuera, "anomalias": anomalias[:20]}
