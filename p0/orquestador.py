"""P0 · Orquestador de entrada de extractos bancarios.

    ENTRADA/<extracto>.xls|xlsx
      -> motor_control_depositos_cbba.ejecutar_motor   (UN archivo por corrida)   -> LISTS.csv
      -> adaptador_m365.adaptar (P7)                                              -> DEPOSITOS_ACTIVOS__P7-<hash>.json
      -> copia del JSON a la carpeta que escucha P8 V5                            -> P8 carga Depositos_Activos
      -> el extracto pasa a PROCESADOS/   (o a ERROR/ + <archivo>.error.json si algo falla)

No contiene logica de negocio: solo encadena el motor y P7 existentes, procesa archivo por archivo (un archivo malo no
detiene a los demas) y mueve los originales. La idempotencia sigue en P8 (CLAVE_TRANSACCION); aqui no se duplica.

Uso:  python -m p0 --sede CBBA --documentos <carpeta local 'Documents' de OneDrive> [--una-vez]
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEDES_JSON = Path(__file__).resolve().parent / "sedes.json"
REGISTRO_BASE = RAIZ / "registro_bancos.json"
VARIABLE_REGISTRO = "CBBA_REGISTRO_BANCOS"  # la leen la deteccion y la normalizacion del motor (P4/P5)

EXTENSIONES = (".xls", ".xlsx")
# Archivos transitorios o del sistema: se dejan donde estan (no son extractos ni errores).
IGNORAR_PREFIJOS = ("~$", ".")
IGNORAR_SUFIJOS = (".tmp", ".crdownload", ".part", ".partial", ".download", ".lnk", ".p0tmp")
IGNORAR_NOMBRES = {"desktop.ini", "thumbs.db"}

ESTADO_PROCESADO = "PROCESADO"
ESTADO_ERROR = "ERROR"
LOCK_VENCE_S = 2 * 3600

log = logging.getLogger("p0")


class ConfigError(ValueError):
    """Configuracion invalida (carpeta o registro): se detiene todo antes de tocar ningun extracto."""


class ErrorP0(Exception):
    """Fallo de UN archivo en una etapa; el orquestador lo convierte en ERROR y sigue con los demas."""

    def __init__(self, etapa, codigo, mensaje, detalle=None):
        super().__init__(mensaje)
        self.etapa, self.codigo, self.mensaje, self.detalle = etapa, codigo, mensaje, detalle


# ------------------------------------------------------------------ configuracion por sede
@dataclass
class Config:
    sede: str
    entrada: Path
    procesados: Path
    error: Path
    destino_p8: Path
    registro: Path
    trabajo: Path
    estable_s: float = 30.0
    intervalo_s: float = 60.0


def _resolver(base, valor):
    p = Path(valor)
    if p.is_absolute():
        return p
    if base is None:
        raise ConfigError(f"la ruta '{valor}' es relativa: indica --documentos (carpeta local 'Documents' de OneDrive)")
    return Path(base) / p


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
        ruta = _resolver(Path(__file__).resolve().parent, extra)
        try:
            adicionales = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"sede {sede}: no se pudo leer cuentas_adicionales ({ruta}): {e}") from e
        elegidas += adicionales["CUENTAS"] if isinstance(adicionales, dict) else adicionales
    ids = [c["id"] for c in elegidas]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"sede {sede}: ids de cuenta repetidos en el registro efectivo")
    reg["CUENTAS"] = elegidas
    destino = Path(trabajo) / f"registro_bancos_{sede}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def cargar_config(sede, documentos=None, raiz=None, destino_p8=None, trabajo=None, sedes_json=SEDES_JSON,
                  registro_base=REGISTRO_BASE, estable_s=30.0, intervalo_s=60.0):
    documentos = documentos or os.environ.get("CBBA_DOCUMENTOS")
    try:
        sedes = json.loads(Path(sedes_json).read_text(encoding="utf-8"))["sedes"]
    except (OSError, ValueError, KeyError) as e:
        raise ConfigError(f"no se pudo leer {sedes_json}: {e}") from e
    if sede not in sedes:
        raise ConfigError(f"sede '{sede}' no definida en {Path(sedes_json).name} (hay: {sorted(sedes)})")
    s = sedes[sede]
    raiz = _resolver(documentos, raiz or s["carpeta_p0"])
    trabajo = Path(trabajo) if trabajo else Path(tempfile.gettempdir()) / "cbba_p0" / sede
    cfg = Config(
        sede=sede, entrada=raiz / "ENTRADA", procesados=raiz / "PROCESADOS", error=raiz / "ERROR",
        destino_p8=_resolver(documentos, destino_p8 or s["destino_p8"]),
        registro=registro_para_sede(s, trabajo, registro_base, sede), trabajo=trabajo,
        estable_s=estable_s, intervalo_s=intervalo_s)
    return cfg


def validar_config(cfg):
    """Antes de procesar: las carpetas existen (la de P8 NO se crea: una carpeta nueva no la escucha el flujo)."""
    if not cfg.destino_p8.is_dir():
        raise ConfigError(f"la carpeta de P8 no existe: {cfg.destino_p8}. Debe ser la carpeta local sincronizada "
                          "que corresponde a la carpeta de SharePoint que escucha el flujo P8.")
    if not Path(cfg.registro).is_file():
        raise ConfigError(f"no se encuentra el registro de bancos: {cfg.registro}")
    for c in (cfg.entrada, cfg.procesados, cfg.error, cfg.trabajo):
        c.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ etapas (reutilizan el codigo existente)
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
    """Deteccion P4 sobre ese archivo -> objeto con .ok/.estado/.motivo (o excepcion si no se puede leer)."""
    motor = _modulo("motor_control_depositos_cbba", "motor_control_depositos_cbba.py")
    with _registro_activo(registro):
        return motor.detector_registro().detectar(str(archivo))


def etapa_motor(carpeta_entrada, ruta_salida, registro):
    """ejecutar_motor sobre una carpeta con UN extracto. Devuelve (resultado, texto de consola)."""
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


def etapa_publicar(ruta_json, destino, ahora):
    """Copia el JSON con su nombre final a la carpeta que escucha P8 y comprueba que llego completo.
    No se usa archivo temporal + renombrar: un archivo renombrado ya 'visto' por SharePoint podria no disparar
    'Cuando se crea un archivo'."""
    ruta_json, destino = Path(ruta_json), Path(destino)
    if not destino.is_dir():
        raise ErrorP0("PUBLICACION", "DESTINO_P8_NO_EXISTE", f"la carpeta de P8 no existe: {destino}")
    final = destino / ruta_json.name
    if final.exists():  # mismo LISTS.csv byte a byte ya publicado antes: nombre nuevo conservando prefijo y .json
        final = destino / f"{ruta_json.stem}__{ahora:%Y%m%d_%H%M%S}.json"
    try:
        shutil.copyfile(ruta_json, final)
        if _sha256(final) != _sha256(ruta_json):
            final.unlink(missing_ok=True)
            raise ErrorP0("PUBLICACION", "COPIA_INCOMPLETA", "el JSON copiado no coincide con el original")
    except OSError as e:
        raise ErrorP0("PUBLICACION", "PUBLICACION_FALLIDA", f"no se pudo copiar el JSON a {destino}: {e}") from e
    return final


@dataclass
class Etapas:
    detectar: object = etapa_detectar
    motor: object = etapa_motor
    p7: object = etapa_p7
    publicar: object = etapa_publicar


# ------------------------------------------------------------------ utilidades
def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _limpiar(texto):
    t = re.sub(r"^\s*[❌✅⚠️ℹ️\s]+", "", str(texto).strip())
    return re.sub(r"^(PROCESO DETENIDO|EXPORTACIÓN BLOQUEADA):\s*", "", t).strip()


def _seguro(nombre):
    return re.sub(r"[^\w.-]+", "_", nombre)[:60]


def traducir_error_motor(exc, consola=""):
    """ValueError del motor -> (codigo, mensaje legible). El motor no cambia: se interpretan sus mensajes."""
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
        tabla = consola.split("HAY CUENTAS QUE NO CUADRAN:")[-1].strip() if "NO CUADRAN" in consola else ""
        return "SALDOS_NO_CUADRAN", "Los saldos del extracto no cuadran con sus movimientos. " + tabla[:600]
    if "falló la normalización" in msg:
        return "NORMALIZACION_FALLIDA", _limpiar(msg)
    return "FALLO_MOTOR", _limpiar(msg)


@dataclass
class Resultado:
    archivo: str
    estado: str = ""
    etapa: str = ""
    codigo: str = ""
    mensaje: str = ""
    movimientos: int = 0
    lote_id: str = ""
    json_publicado: str = ""
    sha256_extracto: str = ""
    destino: str = ""
    advertencia: str = ""
    inicio: str = ""
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ orquestador
class Orquestador:
    def __init__(self, cfg, etapas=None, reloj=datetime.now, esperar=time.sleep):
        self.cfg, self.etapas, self.reloj, self.esperar = cfg, etapas or Etapas(), reloj, esperar
        self.atascados = set()  # originales que no se pudieron mover: no se vuelven a publicar en cada ciclo

    # --- descubrimiento
    def pendientes(self):
        """Archivos de ENTRADA listos para procesar (estables, no transitorios), mas antiguos primero."""
        ahora, salida = time.time(), []
        for p in self.cfg.entrada.iterdir():
            n = p.name.lower()
            if not p.is_file() or n.startswith(IGNORAR_PREFIJOS) or n.endswith(IGNORAR_SUFIJOS) \
                    or n in IGNORAR_NOMBRES:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if (p.name, st.st_size, st.st_mtime) in self.atascados:
                continue
            if ahora - st.st_mtime < self.cfg.estable_s:  # puede seguir copiandose/sincronizandose
                log.info("espera (archivo reciente): %s", p.name)
                continue
            salida.append((st.st_mtime, p.name, p))
        return [p for _, _, p in sorted(salida)]

    # --- un archivo
    def procesar_archivo(self, ruta):
        ruta, ahora = Path(ruta), self.reloj()
        r = Resultado(archivo=ruta.name, inicio=ahora.isoformat(timespec="seconds"))
        trabajo = self.cfg.trabajo / "corridas" / f"{ahora:%Y%m%d_%H%M%S}_{_seguro(ruta.stem)}"
        etapa = "ARCHIVO"
        try:
            if ruta.suffix.lower() not in EXTENSIONES:
                raise ErrorP0("ARCHIVO", "EXTENSION_NO_SOPORTADA",
                              f"Solo se procesan extractos .xls/.xlsx (llegó '{ruta.suffix or 'sin extensión'}').")
            if ruta.stat().st_size == 0:
                raise ErrorP0("ARCHIVO", "ARCHIVO_VACIO", "El archivo está vacío (0 bytes).")
            r.sha256_extracto = _sha256(ruta)
            ent = trabajo / "entrada"
            ent.mkdir(parents=True, exist_ok=True)
            copia = ent / ruta.name  # mismo nombre: ARCHIVO ORIGEN conserva el nombre original
            shutil.copy2(ruta, copia)

            etapa = "DETECCION"
            try:
                det = self.etapas.detectar(copia, self.cfg.registro)
            except Exception as e:
                raise ErrorP0("DETECCION", "ARCHIVO_ILEGIBLE", f"No se pudo leer el archivo como Excel (¿corrupto o no es un extracto real?): {_limpiar(e)}")
            if not det.ok:
                raise ErrorP0("DETECCION", det.estado, f"{det.estado}: {det.motivo}")

            etapa = "MOTOR"
            try:
                res, consola = self.etapas.motor(ent, trabajo / "motor" / "NORMALIZADO.xlsx", self.cfg.registro)
            except ValueError as e:
                codigo, msg = traducir_error_motor(e, getattr(e, "consola", ""))
                raise ErrorP0("MOTOR", codigo, msg, getattr(e, "consola", "")[-1500:])
            r.movimientos = int(len(res["df_final"]))

            if r.movimientos == 0:  # extracto valido sin movimientos: nada que cargar (no se publica JSON vacio)
                r.advertencia = "Extracto sin movimientos: no se generó JSON."
            else:
                etapa = "P7"
                try:
                    p7 = self.etapas.p7(res["ruta_lists_csv"], trabajo / "m365")
                except ValueError as e:
                    raise ErrorP0("P7", "P7_CONTRATO", _limpiar(e))
                m = p7["manifiesto"]
                r.lote_id = p7["lote_id"]
                if m["cantidad_error"] > 0:
                    art = json.loads(Path(p7["rutas"]["artefacto"]).read_text(encoding="utf-8"))
                    det_err = [f"fila {o['fila']}: {o['motivo']}" for o in art["omitidos"] if o["estado"] == "ERROR"]
                    raise ErrorP0("P7", "P7_FILAS_INVALIDAS",
                                  f"P7 marcó {m['cantidad_error']} fila(s) inválida(s); no se publica para no cargar "
                                  f"un extracto incompleto. {'; '.join(det_err[:5])}")
                etapa = "PUBLICACION"
                final = self.etapas.publicar(p7["rutas"]["artefacto"], self.cfg.destino_p8, ahora)
                r.json_publicado = Path(final).name
        except ErrorP0 as e:
            r.etapa, r.codigo, r.mensaje = e.etapa, e.codigo, e.mensaje
            r.extra["detalle"] = e.detalle
        except Exception as e:  # defensa: un error inesperado tampoco puede detener a los demas archivos
            r.etapa, r.codigo, r.mensaje = etapa, "ERROR_INESPERADO", f"{type(e).__name__}: {e}"
            log.exception("error inesperado en %s", ruta.name)
        finally:
            shutil.rmtree(trabajo, ignore_errors=True)

        if r.codigo:
            r.estado = ESTADO_ERROR
            self._cerrar(ruta, r, self.cfg.error, ".error.json")
        else:
            r.estado = ESTADO_PROCESADO
            self._cerrar(ruta, r, self.cfg.procesados, ".p0.json")
        log.info("%s -> %s%s", r.archivo, r.estado, f" [{r.etapa}/{r.codigo}] {r.mensaje}" if r.codigo else
                 f" ({r.movimientos} mov., JSON {r.json_publicado or 'no aplica'})")
        return r

    def _cerrar(self, ruta, r, carpeta, sufijo):
        """Mueve el original (recien ahora) y deja la evidencia minima junto a el."""
        destino = carpeta / ruta.name
        if destino.exists():
            destino = carpeta / f"{ruta.stem}__{self.reloj():%Y%m%d_%H%M%S}{ruta.suffix}"
        for intento in range(3):
            try:
                shutil.move(str(ruta), str(destino))
                break
            except OSError as e:
                if intento == 2:
                    r.advertencia = (r.advertencia + " " if r.advertencia else "") + \
                        f"No se pudo mover el original a {carpeta.name}: {e}"
                    log.error("no se pudo mover %s a %s: %s", ruta.name, carpeta.name, e)
                    try:
                        st = ruta.stat()
                        self.atascados.add((ruta.name, st.st_size, st.st_mtime))
                    except OSError:
                        pass
                    return
                self.esperar(2)
        r.destino = str(destino)
        evidencia = {"nombre_archivo": r.archivo, "sede": self.cfg.sede, "fecha_hora": r.inicio,
                     "estado": r.estado, "etapa": r.etapa, "codigo_error": r.codigo, "mensaje": r.mensaje,
                     "sha256_extracto": r.sha256_extracto, "movimientos": r.movimientos, "lote_id": r.lote_id,
                     "json_publicado": r.json_publicado, "advertencia": r.advertencia}
        if r.estado == ESTADO_ERROR and r.extra.get("detalle"):
            evidencia["detalle"] = r.extra["detalle"]
        try:
            Path(str(destino) + sufijo).write_text(json.dumps(evidencia, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
        except OSError as e:
            log.error("no se pudo escribir la evidencia de %s: %s", r.archivo, e)

    # --- un ciclo
    def ciclo(self):
        return [self.procesar_archivo(p) for p in self.pendientes()]


@contextlib.contextmanager
def candado(trabajo):
    """Una sola instancia por sede (archivo de bloqueo local, nunca en la carpeta sincronizada)."""
    ruta = Path(trabajo) / "p0.lock"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - ruta.stat().st_mtime < LOCK_VENCE_S:
            raise ConfigError(f"ya hay otra instancia de P0 en ejecución ({ruta}). Si no es así, borra ese archivo.")
        ruta.unlink()
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        yield ruta
    finally:
        ruta.unlink(missing_ok=True)


def _configurar_log(trabajo):
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(Path(trabajo) / "p0.log", encoding="utf-8")):
            h.setFormatter(fmt)
            log.addHandler(h)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m p0", description="P0: ENTRADA de extractos -> motor -> P7 -> carpeta de P8")
    p.add_argument("--sede", default="CBBA")
    p.add_argument("--documentos", help="carpeta local 'Documents' de OneDrive (o variable CBBA_DOCUMENTOS)")
    p.add_argument("--raiz", help="sustituye carpeta_p0 de la sede (ENTRADA/PROCESADOS/ERROR)")
    p.add_argument("--destino-p8", help="sustituye destino_p8 de la sede")
    p.add_argument("--trabajo", help="carpeta local de trabajo/logs (por defecto en la carpeta temporal del sistema)")
    p.add_argument("--una-vez", action="store_true", help="un solo ciclo y termina (pruebas / Programador de tareas)")
    p.add_argument("--intervalo", type=float, default=60.0, help="segundos entre ciclos (por defecto 60)")
    p.add_argument("--estable", type=float, default=30.0,
                   help="segundos sin cambios que debe tener un archivo antes de procesarlo (por defecto 30)")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        cfg = cargar_config(a.sede, a.documentos, a.raiz, a.destino_p8, a.trabajo, estable_s=a.estable,
                            intervalo_s=a.intervalo)
        validar_config(cfg)
        _configurar_log(cfg.trabajo)
        orq = Orquestador(cfg)
        with candado(cfg.trabajo) as lock:
            log.info("P0 %s: ENTRADA=%s | P8=%s", cfg.sede, cfg.entrada, cfg.destino_p8)
            while True:
                try:
                    res = orq.ciclo()
                    if res:
                        log.info("ciclo: %d procesado(s), %d con error",
                                 sum(r.estado == ESTADO_PROCESADO for r in res), sum(r.estado == ESTADO_ERROR for r in res))
                except Exception:
                    log.exception("fallo inesperado del ciclo (se reintenta)")
                if a.una_vez:
                    return 0
                os.utime(lock)  # mantiene vigente el bloqueo
                time.sleep(cfg.intervalo_s)
    except ConfigError as e:
        print(f"ERROR de configuración: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
