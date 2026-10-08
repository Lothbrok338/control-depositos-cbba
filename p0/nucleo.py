"""P0 · núcleo sin estado: UN extracto bancario (bytes) -> JSON de P7 listo para P8.

    bytes del .xls/.xlsx
      -> detección P4 (banco/cuenta/moneda)              motor_control_depositos_cbba.detector_registro
      -> motor_control_depositos_cbba.ejecutar_motor      (un solo archivo)            -> LISTS.csv
      -> adaptador_m365.adaptar (P7)                                                   -> DEPOSITOS_ACTIVOS__P7-<hash>.json
      -> resultado (diccionario) con el texto del JSON

No guarda nada: el archivo se escribe en un directorio temporal que se elimina siempre al terminar (éxito o error) y
el resultado solo vive en la respuesta. No contiene lógica de negocio: encadena el motor y P7 existentes. No hace
logging de contenido bancario: solo `registrar_tecnico` (nombre de archivo, hash, etapa, banco, filas, resultado,
código de error y duración).
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEDES_JSON = Path(__file__).resolve().parent / "sedes.json"
REGISTRO_BASE = RAIZ / "registro_bancos.json"
VARIABLE_REGISTRO = "CBBA_REGISTRO_BANCOS"  # la leen la detección y la normalización del motor (P4/P5)
VERSION = "P0-API-1"

EXTENSIONES = (".xls", ".xlsx")
MESES = ("01_ENERO", "02_FEBRERO", "03_MARZO", "04_ABRIL", "05_MAYO", "06_JUNIO", "07_JULIO", "08_AGOSTO",
         "09_SEPTIEMBRE", "10_OCTUBRE", "11_NOVIEMBRE", "12_DICIEMBRE")  # independiente del idioma del equipo

log = logging.getLogger("p0")
# El motor cambia el registro por variable de entorno y redirige stdout: una corrida a la vez por proceso.
_CANDADO = threading.Lock()


class SedeDesconocida(ValueError):
    pass


class ConfigError(ValueError):
    pass


class ErrorP0(Exception):
    """Fallo de UN archivo en una etapa -> respuesta estructurada (codigo_error, etapa, mensaje)."""

    def __init__(self, etapa, codigo, mensaje):
        super().__init__(mensaje)
        self.etapa, self.codigo, self.mensaje = etapa, codigo, mensaje


# ------------------------------------------------------------------ configuración por sede
def _leer_sedes(sedes_json=None):
    sedes_json = sedes_json or SEDES_JSON
    try:
        return json.loads(Path(sedes_json).read_text(encoding="utf-8"))["sedes"]
    except (OSError, ValueError, KeyError) as e:
        raise ConfigError(f"no se pudo leer {Path(sedes_json).name}: {e}") from e


def config_sede(sede, sedes_json=None):
    sedes = _leer_sedes(sedes_json)
    if sede not in sedes:
        raise SedeDesconocida(f"sede '{sede}' no definida (sedes disponibles: {sorted(sedes)})")
    return sedes[sede]


def registro_para_sede(cfg_sede, trabajo, base=REGISTRO_BASE, sede="SEDE"):
    """Registro de bancos efectivo de la sede: formatos comunes + las cuentas de la sede.
    Sin filtro ni cuentas adicionales devuelve el registro base tal cual (no se escribe nada)."""
    cuentas, extra = cfg_sede.get("cuentas", "TODAS"), cfg_sede.get("cuentas_adicionales")
    if cuentas == "TODAS" and not extra:
        return Path(base)
    reg = json.loads(Path(base).read_text(encoding="utf-8"))
    por_id = {c["id"]: c for c in reg["CUENTAS"]}
    if cuentas == "TODAS":
        elegidas = list(reg["CUENTAS"])
    else:
        desconocidas = [i for i in cuentas if i not in por_id]
        if desconocidas:
            raise ConfigError(f"sede {sede}: cuentas inexistentes en registro_bancos.json: {desconocidas}")
        elegidas = [por_id[i] for i in cuentas]
    if extra:
        ruta = Path(extra)
        if not ruta.is_absolute():
            ruta = Path(__file__).resolve().parent / ruta
        try:
            adicionales = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"sede {sede}: no se pudo leer cuentas_adicionales ({ruta.name}): {e}") from e
        elegidas += adicionales["CUENTAS"] if isinstance(adicionales, dict) else adicionales
    ids = [c["id"] for c in elegidas]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"sede {sede}: ids de cuenta repetidos en el registro efectivo")
    reg["CUENTAS"] = elegidas
    destino = Path(trabajo) / f"registro_bancos_{sede}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def ahora_local(cfg_sede=None):
    """Hora local de la sede (por defecto America/La_Paz, UTC-4 sin horario de verano)."""
    nombre = (cfg_sede or {}).get("zona_horaria", "America/La_Paz")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(nombre))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def periodo(fecha):
    """AAAA y MM_MES de la fecha (carpeta PROCESADOS/ERROR que usará Power Automate)."""
    return {"anio": fecha.year, "mes": MESES[fecha.month - 1], "carpeta": f"{fecha.year:04d}/{MESES[fecha.month - 1]}"}


# ------------------------------------------------------------------ etapas (reutilizan el código existente)
_MODULOS = {}


def _modulo(nombre, archivo):
    if nombre not in _MODULOS:
        spec = importlib.util.spec_from_file_location(nombre, RAIZ / archivo)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _MODULOS[nombre] = m
    return _MODULOS[nombre]


@contextlib.contextmanager
def _registro_activo(ruta):
    previo = os.environ.get(VARIABLE_REGISTRO)
    os.environ[VARIABLE_REGISTRO] = str(ruta)
    try:
        yield
    finally:
        if previo is None:
            os.environ.pop(VARIABLE_REGISTRO, None)
        else:
            os.environ[VARIABLE_REGISTRO] = previo


def etapa_detectar(archivo, registro):
    """Detección P4 sobre ese archivo -> objeto con .ok/.estado/.motivo (o excepción si no se puede leer)."""
    motor = _modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    with _registro_activo(registro):
        return motor.detector_registro().detectar(str(archivo))


def etapa_motor(carpeta_entrada, ruta_salida, registro):
    """ejecutar_motor sobre una carpeta con UN extracto. Devuelve (resultado, texto de consola; no se registra)."""
    motor = _modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    consola = io.StringIO()
    with _registro_activo(registro), contextlib.redirect_stdout(consola):
        try:
            res = motor.ejecutar_motor(str(carpeta_entrada), str(ruta_salida))
        except Exception as e:
            e.consola = consola.getvalue()
            raise
    return res, consola.getvalue()


def etapa_p7(lists_csv, carpeta_m365):
    """adaptador_m365.adaptar (P7) sin cambios: LISTS.csv -> DEPOSITOS_ACTIVOS__<lote>.json."""
    return _modulo("adaptador_m365", "adaptador_m365.py").adaptar(str(lists_csv), str(carpeta_m365))


@dataclass
class Etapas:
    detectar: object = etapa_detectar
    motor: object = etapa_motor
    p7: object = etapa_p7


ETAPAS = Etapas()


# ------------------------------------------------------------------ utilidades
def sha256_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


def nombre_seguro(nombre):
    """Solo el nombre (sin rutas), sin caracteres de control; nunca vacío."""
    n = re.split(r"[\\/]", str(nombre or ""))[-1]
    n = re.sub(r"[\x00-\x1f\x7f]", "", n).strip().strip(".")[:150]
    return n or "extracto"


def enmascarar(texto, secretos=()):
    """Oculta números de cuenta: los conocidos (los leídos de la cabecera) y cualquier número de 9+ dígitos."""
    t = str(texto)
    for s in secretos:
        if s and len(str(s)) >= 4:
            s = str(s)
            t = t.replace(s, "****" + re.sub(r"\D", "", s)[-4:])
    return re.sub(r"\b\d{9,}\b", lambda m: "****" + m.group()[-4:], t)


def _limpiar(texto):
    t = re.sub(r"^\s*[❌✅⚠️ℹ️\s]+", "", str(texto).strip())
    return re.sub(r"^(PROCESO DETENIDO|EXPORTACIÓN BLOQUEADA):\s*", "", t).strip()


def traducir_error_motor(exc, consola=""):
    """ValueError del motor -> (código, mensaje). El motor no cambia: se interpretan sus mensajes. Los mensajes no
    incluyen tablas de saldos ni filas del extracto."""
    msg = str(exc)
    if "rango válido" in msg:
        return "ANIO_FUERA_DE_RANGO", _limpiar(msg)
    if "hay archivos no reconocidos" in msg:
        return "ARCHIVO_NO_RECONOCIDO", _limpiar(msg.replace("hay archivos no reconocidos.\n", "No reconocido: "))
    if "no se encontraron archivos" in msg:
        return ("ARCHIVO_EXCLUIDO_POR_NOMBRE",
                "El motor ignora este archivo por su nombre (contiene 'NORMALIZADO' o empieza como una salida del "
                "sistema). Renombra el extracto original.")
    if "auditoría estructural" in msg:
        bloque = consola.split("AUDITORÍA ESTRUCTURAL...")[-1].split("AUDITORÍA ESTRUCTURAL SUPERADA")[0]
        filas = [l.strip() for l in bloque.splitlines() if re.match(r"\s+\S.*:\s*[1-9]\d*\s*$", l)]
        return "AUDITORIA_ESTRUCTURAL", "La auditoría estructural del extracto falló: " + " | ".join(filas)
    if "EXPORTACIÓN BLOQUEADA" in msg:
        return "SALDOS_NO_CUADRAN", "Los saldos del extracto no cuadran con sus movimientos (saldo inicial + créditos - débitos <> saldo final)."
    if "falló la normalización" in msg:
        return "NORMALIZACION_FALLIDA", _limpiar(msg)
    return "FALLO_MOTOR", _limpiar(msg)


def registrar_tecnico(nombre, sha, etapa, banco, filas, resultado, codigo, ms):
    """ÚNICO punto de logging de P0. Solo datos técnicos: nunca movimientos, cuentas completas ni JSON."""
    log.info("archivo=%s sha=%s etapa=%s banco=%s filas=%s resultado=%s codigo=%s ms=%d",
             nombre, (sha or "")[:12], etapa, banco or "-", "-" if filas is None else filas, resultado, codigo or "-", ms)


# ------------------------------------------------------------------ procesar UN extracto
def procesar_extracto(contenido, nombre, sede, etapas=None):
    """bytes + nombre + sede -> dict (ok True/False). Lanza SedeDesconocida si la sede no existe. No lee ni escribe
    nada fuera de un directorio temporal propio, que se elimina siempre."""
    etapas = etapas or ETAPAS
    t0 = time.perf_counter()
    cfg = config_sede(sede)
    nombre = nombre_seguro(nombre)
    sha = sha256_bytes(contenido)
    ahora = ahora_local(cfg)
    out = {"ok": False, "version": VERSION, "sede": sede,
           "archivo": {"nombre": nombre, "sha256": sha, "bytes": len(contenido)},
           "deteccion": None, "periodo": periodo(ahora), "procesado_en": ahora.isoformat(timespec="seconds")}
    etapa, banco, filas, secretos = "ARCHIVO", None, None, []
    try:
        if os.path.splitext(nombre)[1].lower() not in EXTENSIONES:
            raise ErrorP0("ARCHIVO", "EXTENSION_NO_SOPORTADA", "Solo se procesan extractos .xls/.xlsx.")
        if not contenido:
            raise ErrorP0("ARCHIVO", "ARCHIVO_VACIO", "El archivo está vacío (0 bytes).")
        with _CANDADO, tempfile.TemporaryDirectory(prefix="p0_") as tmp:
            tmp = Path(tmp)
            ent = tmp / "entrada"
            ent.mkdir()
            (ent / nombre).write_bytes(contenido)  # mismo nombre: ARCHIVO ORIGEN conserva el nombre original
            registro = registro_para_sede(cfg, tmp, sede=sede)

            etapa = "DETECCION"
            try:
                det = etapas.detectar(ent / nombre, registro)
            except Exception as e:
                raise ErrorP0("DETECCION", "ARCHIVO_ILEGIBLE",
                              "No se pudo leer el archivo como Excel (¿corrupto o no es un extracto real?): "
                              + enmascarar(_limpiar(e))[:200])
            secretos = [getattr(det, "cuenta_leida", None)]
            banco = getattr(det, "banco", None)
            if det.ok:
                out["deteccion"] = {"banco": det.banco, "cuenta_id": det.cuenta_id, "moneda": det.moneda,
                                    "formato": det.formato_id}
            else:
                raise ErrorP0("DETECCION", det.estado, f"{det.estado}: {det.motivo}")

            etapa = "MOTOR"
            try:
                res, consola = etapas.motor(ent, tmp / "motor" / "NORMALIZADO.xlsx", registro)
            except ValueError as e:
                codigo, msg = traducir_error_motor(e, getattr(e, "consola", ""))
                raise ErrorP0("MOTOR", codigo, msg)
            filas = int(len(res["df_final"]))
            out["movimientos"] = filas

            if filas == 0:  # extracto válido sin movimientos: nada que cargar
                out.update(ok=True, resultado="PROCESADO", publicar_json=False, json=None,
                           advertencia="Extracto sin movimientos: no se genera JSON.")
            else:
                etapa = "P7"
                try:
                    p7 = etapas.p7(res["ruta_lists_csv"], tmp / "m365")
                except ValueError as e:
                    raise ErrorP0("P7", "P7_CONTRATO", _limpiar(e)[:300])
                m = p7["manifiesto"]
                ruta_json = Path(p7["rutas"]["artefacto"])
                if m["cantidad_error"] > 0:
                    art = json.loads(ruta_json.read_text(encoding="utf-8"))
                    det_err = [f"fila {o['fila']}: {o['motivo']}" for o in art["omitidos"] if o["estado"] == "ERROR"]
                    raise ErrorP0("P7", "P7_FILAS_INVALIDAS",
                                  f"P7 marcó {m['cantidad_error']} fila(s) inválida(s); no se entrega JSON para no "
                                  f"cargar un extracto incompleto. {'; '.join(det_err[:5])}")
                datos = ruta_json.read_bytes()
                out.update(ok=True, resultado="PROCESADO", publicar_json=True,
                           json={"nombre": ruta_json.name, "lote_id": p7["lote_id"], "sha256": sha256_bytes(datos),
                                 "bytes": len(datos), "texto": datos.decode("utf-8")})
    except ErrorP0 as e:
        out.update(ok=False, resultado="ERROR", etapa=e.etapa, codigo_error=e.codigo,
                   mensaje=enmascarar(e.mensaje, secretos)[:400])
    except Exception as e:  # defensa: nunca se registra el mensaje (puede traer valores del extracto)
        out.update(ok=False, resultado="ERROR", etapa=etapa, codigo_error="ERROR_INESPERADO",
                   mensaje=f"Error interno inesperado ({type(e).__name__}).")
    ms = int((time.perf_counter() - t0) * 1000)
    out["duracion_ms"] = ms
    registrar_tecnico(nombre, sha, out.get("etapa", etapa) if not out["ok"] else "COMPLETO", banco, filas,
                      out["resultado"], out.get("codigo_error"), ms)
    return out
