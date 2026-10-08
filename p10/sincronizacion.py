# -*- coding: utf-8 -*-
"""
p10/sincronizacion.py · P10-A.2 · núcleo del servicio (sin HTTP, sin estado propio).

Dos operaciones con efectos, ambas deterministas e idempotentes:

  procesar_extracto(bytes del extracto ya archivado en PROCESADOS)
      -> PARCIALES por BANCO+CUENTA+MONEDA+MES.  Usa el MISMO motor que P0 (`p0.nucleo.etapa_detectar` / `etapa_motor`
         -> `ejecutar_motor`): la CLAVE TRANSACCIÓN y las 26 columnas salen del motor, no se recalculan aquí.

  sincronizar_grupo(estado actual + parciales nuevos + filas actuales de Depositos_Activos)
      -> estado nuevo + XLSX regenerado COMPLETO con el generador aprobado de A.1 (`generador`, sin cambios) y validado
         contra sus fuentes antes de entregarlo.

El servicio NO guarda nada: el estado y los XLSX viven en OneDrive y los maneja el flujo (único escritor).
"""
import base64
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path

import historico as H
from openpyxl.utils import column_index_from_string

from p0 import nucleo

from . import contrato as C
from . import estado as E
from . import generador as G
from . import plan as PL
from . import validacion as V
from .snapshot import SnapshotError, cargar_snapshot

VERSION = "P10-API-1"
BASE_DEFECTO = "/CONTROL_DEPOSITOS"
_REGISTROS = {}


class ErrorP10(Exception):
    def __init__(self, codigo, mensaje, etapa="P10"):
        super().__init__(mensaje)
        self.codigo, self.mensaje, self.etapa = codigo, mensaje, etapa


def b64(datos):
    return base64.b64encode(datos).decode("ascii")


def sha256_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


# ------------------------------------------------------------------ rutas
def rutas_grupo(g, base=BASE_DEFECTO):
    """Dónde viven el XLSX (lectura para usuarios) y el estado (solo automatización) de un grupo. Rutas del conector OneDrive."""
    anio, mm = g["periodo"].split("-")
    mes, banco = nucleo.MESES[int(mm) - 1], H._seguro(g["banco"])
    nombre_xlsx = G.nombre_archivo(g["banco"], g["cuenta"], g["moneda"], g["periodo"])
    nombre_estado = (f"ESTADO_P10_{banco}_{H._seguro(g['cuenta'])}_{H._seguro(g['moneda'])}_{g['periodo']}.json.gz")
    carpeta_x, carpeta_e = f"{base}/P10_HISTORICO/{anio}/{mes}/{banco}", f"{base}/P10_ESTADO/{anio}/{mes}/{banco}"
    return {"carpeta_xlsx": carpeta_x, "nombre_xlsx": nombre_xlsx, "ruta_xlsx": f"{carpeta_x}/{nombre_xlsx}",
            "carpeta_estado": carpeta_e, "nombre_estado": nombre_estado, "ruta_estado": f"{carpeta_e}/{nombre_estado}"}


def registro_de_sede(sede):
    """Mismo registro de bancos efectivo que usa P0 para esa sede (cuentas de la sede + formatos comunes)."""
    if sede not in _REGISTROS:
        cfg = nucleo.config_sede(sede)
        with tempfile.TemporaryDirectory(prefix="p10_reg_") as tmp:
            _REGISTROS[sede] = json.loads(Path(nucleo.registro_para_sede(cfg, tmp, sede=sede)).read_text(encoding="utf-8"))
    return _REGISTROS[sede]


# ------------------------------------------------------------------ 1. extracto -> parciales
def _leer_origen_de_extracto(ruta_origen, ruta_lists):
    datos, mapa = H.leer_origen(ruta_origen)
    return datos, mapa, H.leer_normalizado(ruta_lists)


def construir_parciales(datos, mapa, filas, nombre, sha, procesado_en, formato_banco):
    """ORIGEN + LISTS de UN extracto (salida de P0) -> {grupo_id: parcial}."""
    ids = {m["ID_EXTRACTO"] for m in mapa}
    if len(ids) != 1:
        raise ErrorP10("EXTRACTO_MULTIPLE", "el motor devolvió más de un extracto para un solo archivo")
    ide = ids.pop()
    hoja = mapa[0]["HOJA"]
    por_clave = {m[C.COLUMNA_CLAVE]: m for m in mapa}
    enc, zona, celdas = {}, [], defaultdict(dict)
    for r in datos:
        if r["ID_EXTRACTO"] != ide or r["HOJA"] != hoja:
            continue
        col, rol, valor = column_index_from_string(r["COLUMNA_EXCEL"]), r["ROL_FILA"], H._texto(r.get("VALOR_ORIGINAL"))
        if rol == "ENCABEZADO_TABLA":
            enc[str(col)] = valor
        elif rol == "MOVIMIENTO":
            celdas[r["ID_ORIGEN"]][str(col)] = valor
        else:
            zona.append([int(r["FILA_EXCEL"]), col, rol, valor])
    zona.sort()
    por_grupo = defaultdict(list)
    for f in filas:
        banco, cuenta, moneda = (H._texto(f[k]).strip() for k in ("BANCO", "CUENTA BANCARIA", "MONEDA"))
        por_grupo[(banco, cuenta, moneda, E.periodo_de_fecha(f["FECHA MOVIMIENTO"]))].append(f)
    meses = {k[3] for k in por_grupo if k[:3] == next(iter(por_grupo))[:3]}
    multi = len(meses) > 1
    parciales = {}
    for (banco, cuenta, moneda, periodo), fs in sorted(por_grupo.items()):
        gid = E.grupo_id(banco, cuenta, moneda, periodo)
        movs, ultimo = {}, ""
        for f in fs:
            m = por_clave[f[C.COLUMNA_CLAVE]]
            movs[f[C.COLUMNA_CLAVE]] = {"p0": [H._texto(f[c]) for c in C.COLUMNAS_LISTS], "fila": int(m["FILA_EXCEL"]),
                                        "celdas": celdas.get(m["ID_ORIGEN"], {})}
            ultimo = max(ultimo, f"{E.periodo_de_fecha(f['FECHA MOVIMIENTO'])}-{str(f['FECHA MOVIMIENTO'])[8:10]}T"
                                 f"{H._texto(f['HORA MOVIMIENTO']) or '00:00:00'}")
        parciales[gid] = {
            "formato": E.FORMATO_PARCIAL, "grupo": {**E.grupo_desde_id(gid), "id_cuenta": mapa[0]["FORMATO"],
                                                    "formato_banco": formato_banco},
            "hoja": hoja, "encabezado": enc, "zona": zona, "movimientos": movs,
            "extracto": {"nombre": nombre, "sha256": sha, "procesado_en": procesado_en, "ultimo_mov": ultimo,
                         "movimientos_extracto": len(filas), "multi_mes": multi}}
    return parciales


def _periodo_de_ruta(ruta, defecto):
    m = re.search(r"/PROCESADOS/(\d{4})/(\d{2})_", ruta or "", re.IGNORECASE)
    return f"{m.group(1)}-{m.group(2)}" if m else defecto[:7]


def procesar_extracto(contenido, nombre, sede, ruta, ahora_local, intentos_previos=0):
    """
    bytes del extracto + nombre/ruta en PROCESADOS -> {ok, grupos: [{grupo_id, parcial_b64, movimientos}], control (fila del registro)}.
    Un extracto rechazado devuelve ok:false con `control` listo para el registro (ESTADO ERROR / ERROR_FINAL).
    """
    nombre, sha = nucleo.nombre_seguro(nombre), nucleo.sha256_bytes(contenido)
    control = {"CLAVE_CONTROL": PL.clave_extracto(ruta), "TIPO": "EXTRACTO", "PERIODO": _periodo_de_ruta(ruta, ahora_local),
               "BYTES": len(contenido), "SHA256": sha, "ULTIMA_SYNC": ahora_local}
    try:
        if os.path.splitext(nombre)[1].lower() not in nucleo.EXTENSIONES:
            raise ErrorP10("EXTENSION_NO_SOPORTADA", "Solo se incorporan extractos .xls/.xlsx.", "ARCHIVO")
        if not contenido:
            raise ErrorP10("ARCHIVO_VACIO", "El archivo está vacío (0 bytes).", "ARCHIVO")
        cfg = nucleo.config_sede(sede)
        with nucleo._CANDADO, tempfile.TemporaryDirectory(prefix="p10_") as tmp:
            tmp = Path(tmp)
            ent = tmp / "entrada"
            ent.mkdir()
            (ent / nombre).write_bytes(contenido)
            registro = nucleo.registro_para_sede(cfg, tmp, sede=sede)
            try:
                det = nucleo.ETAPAS.detectar(ent / nombre, registro)
            except Exception as e:
                raise ErrorP10("ARCHIVO_ILEGIBLE", nucleo.enmascarar(nucleo._limpiar(e))[:200], "DETECCION")
            if not det.ok:
                raise ErrorP10(det.estado, nucleo.enmascarar(f"{det.estado}: {det.motivo}", [getattr(det, 'cuenta_leida', None)])[:300],
                               "DETECCION")
            try:
                res, _ = nucleo.ETAPAS.motor(ent, tmp / "motor" / "NORMALIZADO.xlsx", registro)
            except ValueError as e:
                cod, msg = nucleo.traducir_error_motor(e, getattr(e, "consola", ""))
                raise ErrorP10(cod, msg, "MOTOR")
            origen = res.get("origen_estado") or {}
            if len(res["df_final"]) and origen.get("estado") != "OK":
                raise ErrorP10("ORIGEN_NO_GENERADO", "El motor no generó ORIGEN.xlsx (captura íntegra del extracto).", "MOTOR")
            if len(res["df_final"]) == 0:
                parciales = {}
            else:
                datos, mapa, filas = _leer_origen_de_extracto(origen["ruta_origen"], res["ruta_lists_csv"])
                parciales = construir_parciales(datos, mapa, filas, nombre, sha, ahora_local, det.formato_id)
        control.update(ESTADO="PROCESADO", MOVIMIENTOS=int(len(res["df_final"])), GRUPOS=";".join(parciales),
                       INTENTOS=intentos_previos, DETALLE="")
        return {"ok": True, "version": VERSION, "extracto": {"nombre": nombre, "sha256": sha, "bytes": len(contenido),
                                                              "movimientos": control["MOVIMIENTOS"]},
                "grupos": [{"grupo_id": gid, "parcial_b64": b64(E.empaquetar(p)), "movimientos": len(p["movimientos"]),
                            "rutas": rutas_grupo(E.grupo_desde_id(gid))} for gid, p in parciales.items()], "control": control}
    except ErrorP10 as e:
        intentos = intentos_previos + 1
        control.update(ESTADO="ERROR_FINAL" if intentos >= 3 else "ERROR", INTENTOS=intentos,
                       DETALLE=f"{e.etapa}/{e.codigo}: {e.mensaje}"[:900], MOVIMIENTOS=0, GRUPOS="")
        return {"ok": False, "version": VERSION, "etapa": e.etapa, "codigo_error": e.codigo, "mensaje": e.mensaje[:400],
                "grupos": [], "control": control}
    except nucleo.SedeDesconocida as e:
        return {"ok": False, "version": VERSION, "etapa": "API", "codigo_error": "SEDE_DESCONOCIDA", "mensaje": str(e)[:300],
                "grupos": [], "control": dict(control, ESTADO="ERROR", DETALLE="SEDE_DESCONOCIDA", INTENTOS=intentos_previos + 1)}
    except Exception as e:  # defensa: el mensaje puede traer valores del extracto, solo se informa el tipo
        intentos = intentos_previos + 1
        detalle = f"Error interno inesperado ({type(e).__name__})."
        control.update(ESTADO="ERROR_FINAL" if intentos >= 3 else "ERROR", INTENTOS=intentos, DETALLE=detalle, MOVIMIENTOS=0, GRUPOS="")
        return {"ok": False, "version": VERSION, "etapa": "P10", "codigo_error": "ERROR_INESPERADO", "mensaje": detalle,
                "grupos": [], "control": control}


# ------------------------------------------------------------------ 2. estado -> XLSX
def _sin_verificacion(registro):
    """Extractos que cruzan meses: los saldos declarados valen para TODO el extracto, no para el mes del archivo."""
    r = json.loads(json.dumps(registro))
    for fmt in r["FORMATOS"].values():
        for item in fmt.get("historico", {}).get("encabezado", []):
            item.pop("verifica", None)
    return r


def construir_xlsx(estado, registro):
    """Estado -> (bytes del XLSX aprobado de A.1, resumen). Lanza ErrorP10 si el libro no pasa la validación."""
    datos, mapa, filas, snap = E.entradas_generador(estado)
    snapshot = cargar_snapshot(snap) if snap else None
    reg = _sin_verificacion(registro) if estado["cabecera"]["multi_mes"] else registro
    libros, _ = G.construir_libros(datos, mapa, filas, reg, snapshot)
    if len(libros) != 1:
        raise ErrorP10("LIBROS_INESPERADOS", f"el estado de un grupo produjo {len(libros)} libros", "XLSX")
    libro = libros[0]
    if not libro.ok:
        raise ErrorP10("XLSX_NO_GENERABLE", "; ".join(libro.errores)[:600] or "sin movimientos", "XLSX")
    esperado = estado["grupo"]
    if (libro.banco, libro.cuenta, libro.moneda, libro.periodo) != (esperado["banco"], esperado["cuenta"], esperado["moneda"],
                                                                    esperado["periodo"]):
        raise ErrorP10("GRUPO_INCONSISTENTE", "las filas del estado no corresponden a su grupo", "XLSX")
    with tempfile.TemporaryDirectory(prefix="p10_x_") as tmp:
        ruta = os.path.join(tmp, libro.nombre_archivo)
        G.escribir_libro(libro, ruta, snapshot)
        errores = V.validar_libro(ruta, libro, filas, snapshot, V.indice_origen(datos, mapa), reg)
        if errores:
            raise ErrorP10("XLSX_NO_VALIDO", " | ".join(errores)[:600], "XLSX")
        contenido = Path(ruta).read_bytes()
    return contenido, {"nombre": libro.nombre_archivo, "estados": libro.estados, "movimientos": len(libro.claves)}


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def sincronizar_grupo(sede, gid, estado_bytes, parciales_bytes, filas, ahora_local, control=None, forzar_xlsx=False,
                      verificar_xlsx=False, xlsx_actual=None, finalizar=False, base=BASE_DEFECTO):
    """
    Aplica parciales y/o la foto actual de la lista a un grupo y regenera su XLSX.
    `filas`: filas normalizadas de la lista para ESTE grupo (de `plan.clasificar`) o None si no se leyó la lista.
    `control`: el elemento de P10_Control del grupo tal como está AHORA (o None si aún no existe). De él salen la versión y el sello
    del último estado confirmado (detección de alteración/retroceso), los intentos y la marca RECONSTRUIR.
    `verificar_xlsx` + `xlsx_actual`: ciclo COMPLETO; el XLSX que hay en OneDrive (bytes o None si falta) se compara con el hash que el
    estado dice haber escrito y, si falta o difiere, se regenera.
    `finalizar`: quita la marca RECONSTRUIR (solo cuando ya no quedan extractos por reincorporar; lo decide `plan.clasificar`).
    Resultado ok:true incluye `estado_b64` solo si el estado cambió y `xlsx_b64` solo si el libro cambió (o se forzó).
    """
    g = E.grupo_desde_id(gid)
    rutas = rutas_grupo(g, base)
    ctl = control or {}
    cv, ch, intentos = _num(ctl.get("VERSION_ESTADO")), str(ctl.get("HASH_ESTADO") or ""), _num(ctl.get("INTENTOS"))
    marcado = ctl.get("ESTADO") == "RECONSTRUIR"
    reconstruyendo = marcado and not finalizar
    ignorar = marcado and cv == 0                  # reconstrucción en curso: el archivo de estado viejo no se usa
    control = {"CLAVE_CONTROL": "GRUPO|" + gid, "TIPO": "GRUPO", "BANCO": g["banco"], "CUENTA": g["cuenta"], "MONEDA": g["moneda"],
               "PERIODO": g["periodo"], "RUTA_XLSX": rutas["ruta_xlsx"], "RUTA_ESTADO": rutas["ruta_estado"],
               "ULTIMA_SYNC": ahora_local}

    def falla(codigo, mensaje, estado_control="ERROR", **extra):
        control.update({"ESTADO": estado_control, "DETALLE": f"{codigo}: {mensaje}"[:900], "INTENTOS": intentos + 1, **extra})
        return {"ok": False, "version": VERSION, "grupo_id": gid, "codigo_error": codigo, "mensaje": mensaje[:400],
                "rutas": rutas, "control": control}

    def a_reconstruir(codigo, mensaje):
        return falla(codigo, mensaje, "RECONSTRUIR", HASH_OPERATIVO="", HASH_ESTADO="", VERSION_ESTADO=0,
                     RECONSTRUIR_DESDE=ahora_local, INTENTOS=0)

    estado = None
    try:
        if estado_bytes and not ignorar:
            estado = E.cargar_estado(estado_bytes, gid)
            if cv > 0 and ch:                       # el control confirma lo último que se escribió; el estado puede ir 1 adelante
                v = estado["version"]               # (cierre interrumpido entre escribir el estado y confirmarlo en el control)
                if v == cv and estado["integridad"] != ch:
                    raise E.ErrorEstado("ESTADO_ALTERADO", "El sello del estado no coincide con el confirmado en el control.")
                if v < cv:
                    raise E.ErrorEstado("ESTADO_RETROCEDIDO", "El estado es más antiguo que el confirmado en el control.")
                if v > cv + 1:
                    raise E.ErrorEstado("ESTADO_ALTERADO", "El estado es más nuevo de lo que el control permite.")
        elif not estado_bytes and cv > 0 and not ignorar:
            raise E.ErrorEstado("ESTADO_AUSENTE", "El control dice que el grupo tenía estado pero no se encontró el archivo.")
    except E.ErrorEstado as e:
        return a_reconstruir(e.codigo, e.mensaje)
    integridad_inicial = estado["integridad"] if estado else None
    xlsx_previo = dict(estado["xlsx"]) if estado and estado.get("xlsx") else None
    info = {"parciales": [], "operativo": None}
    cambio_datos = False
    try:
        for pb in parciales_bytes or []:
            p = E.desempaquetar(pb)
            if p.get("formato") != E.FORMATO_PARCIAL:
                raise E.ErrorEstado("PARCIAL_INVALIDO", "formato de parcial desconocido")
            if estado is None:
                estado = E.estado_vacio(p["grupo"], p["hoja"], p["grupo"]["id_cuenta"], p["grupo"]["formato_banco"])
            r = E.aplicar_parcial(estado, p)
            info["parciales"].append(r)
            cambio_datos |= r["cambio"]
        if estado is None:
            return falla("SIN_DATOS", "El grupo no tiene estado ni extractos que incorporar (sus extractos aún no se procesaron).",
                         "PENDIENTE")
        hash_op = None
        if filas is not None:
            r = E.aplicar_operativo(estado, filas, ahora_local)
            info["operativo"], hash_op = r, r["hash_lista"]
            cambio_datos |= r["cambio"]
    except E.ErrorEstado as e:
        return falla(e.codigo, e.mensaje)
    registro = registro_de_sede(sede)
    resumen = {"parciales": info["parciales"], "operativo": info["operativo"], "movimientos": len(estado["movimientos"])}
    verificado = None
    if verificar_xlsx and estado.get("xlsx"):
        if xlsx_actual is None:
            verificado = "XLSX_AUSENTE"
        elif sha256_bytes(xlsx_actual) != estado["xlsx"]["sha256"]:
            verificado = "XLSX_ALTERADO"
        resumen["xlsx_verificado"] = verificado or "OK"
    forzar = forzar_xlsx or verificado is not None
    xlsx_bytes, xlsx_err = None, None
    if cambio_datos or forzar or estado["xlsx"] is None:
        try:
            xlsx_bytes, r = construir_xlsx(estado, registro)
            resumen.update(estados=r["estados"])
        except (ErrorP10, SnapshotError, E.ErrorEstado) as e:
            xlsx_err = (getattr(e, "codigo", "SNAPSHOT_INVALIDO"), getattr(e, "mensaje", str(e)))
    cambio_xlsx = False
    if xlsx_bytes is not None:
        h = sha256_bytes(xlsx_bytes)
        control["XLSX_BYTES"] = len(xlsx_bytes)
        cambio_xlsx = forzar or estado["xlsx"] is None or estado["xlsx"]["sha256"] != h
        estado["xlsx"] = {"nombre": rutas["nombre_xlsx"], "sha256": h, "bytes": len(xlsx_bytes)}
    elif xlsx_err:
        estado["xlsx"] = None                       # no hay libro válido para este estado: el próximo intento lo regenera
    if cambio_datos or estado["xlsx"] != xlsx_previo:
        estado["version"] += 1                      # cada escritura del estado sube la versión en 1 (lo comprueba el próximo ciclo)
    E.sellar(estado)
    cambio_estado = estado["integridad"] != integridad_inicial
    empaquetado = E.empaquetar(estado)
    control.update(HASH_ESTADO=estado["integridad"], MOVIMIENTOS=len(estado["movimientos"]), VERSION_ESTADO=estado["version"],
                   ESTADO_BYTES=len(empaquetado), HASH_XLSX=(estado["xlsx"] or {}).get("sha256", ""))
    if xlsx_err:
        control.update(ESTADO="RECONSTRUIR" if reconstruyendo else "ERROR", DETALLE=f"{xlsx_err[0]}: {xlsx_err[1]}"[:900],
                       INTENTOS=intentos + 1)
        if hash_op is not None:
            control["HASH_INTENTO"] = hash_op
    else:
        control.update(ESTADO="RECONSTRUIR" if reconstruyendo else "OK", DETALLE="", INTENTOS=0)
        if finalizar:
            control["RECONSTRUIR_DESDE"] = ""
        if reconstruyendo:
            control["HASH_OPERATIVO"] = ""
        elif hash_op is not None:
            control["HASH_OPERATIVO"] = hash_op
    out = {"ok": True, "version": VERSION, "grupo_id": gid, "cambio_estado": cambio_estado, "cambio_xlsx": cambio_xlsx,
           "xlsx_valido": xlsx_err is None, "estado_b64": b64(empaquetado) if cambio_estado else None,
           "xlsx_b64": b64(xlsx_bytes) if (cambio_xlsx and xlsx_bytes is not None) else None,
           "rutas": rutas, "control": control, "resumen": resumen}
    if xlsx_err:
        out["codigo_error"], out["mensaje"] = xlsx_err[0], xlsx_err[1][:400]
    return out
