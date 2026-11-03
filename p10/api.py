"""P10-A.2 · API HTTP SIN ESTADO para Railway (servicio SEPARADO de `p0-api`).

    GET  /health            sin autenticación (healthcheck de Railway)
    POST /p10/ciclo         bloqueo + modo + meses a mirar               (decisión pura, p10/plan.py)
    POST /p10/plan          extractos de PROCESADOS que hay que incorporar
    POST /p10/delta         filas de Depositos_Activos modificadas desde el cursor -> grupos a actualizar + cursor nuevo
    POST /p10/clasificar    conciliación de un BANCO+MES de Depositos_Activos con lo guardado (nocturna o tras un cambio de extracto)
    POST /p10/extracto      UN extracto de PROCESADOS -> aportes (parciales) por BANCO+CUENTA+MONEDA+MES, con el MOTOR REAL de P0
    POST /p10/sincronizar   UN grupo: estado + parciales + filas de la lista -> estado nuevo + XLSX (generador aprobado de A.1)

Nada se guarda aquí: ni base de datos, ni volumen, ni archivos. El estado canónico vive en OneDrive (`P10_ESTADO`) y el control
en la lista `P10_Control`; este servicio solo calcula. Autenticación: `Authorization: Bearer <P10_API_TOKEN>` (≥16 caracteres;
sin él el servicio rechaza todo). Los logs son técnicos: nunca contenido bancario.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import os
import sys
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import estado as E
from . import plan as PL
from . import sincronizacion as S

MAX_BYTES_DEFECTO = 80 * 1024 * 1024        # cuerpo JSON (incluye Base64 y las filas de un mes de la lista)
HTTP_ERROR = {"SOLICITUD_INVALIDA": 400, "CONTENIDO_INVALIDO": 400, "NO_AUTORIZADO": 401, "SOLICITUD_DEMASIADO_GRANDE": 413,
              "API_NO_CONFIGURADA": 503}

if not logging.getLogger("p10").handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("p10").addHandler(_h)
    logging.getLogger("p10").setLevel(logging.INFO)
_log = logging.getLogger("p10")

app = FastAPI(title="P10 histórico", docs_url=None, redoc_url=None, openapi_url=None)
_SERIE = threading.Lock()                    # un cálculo pesado a la vez (memoria acotada); el flujo ya corre con concurrencia 1


def _max_bytes():
    try:
        return int(os.environ.get("P10_MAX_BYTES", MAX_BYTES_DEFECTO))
    except ValueError:
        return MAX_BYTES_DEFECTO


def _error(codigo, mensaje, status=None, **extra):
    return JSONResponse({"ok": False, "version": S.VERSION, "codigo_error": codigo, "mensaje": mensaje, **extra},
                        status_code=status or HTTP_ERROR.get(codigo, 500))


def _autorizado(request):
    esperado = os.environ.get("P10_API_TOKEN", "")
    if len(esperado) < 16:
        return _error("API_NO_CONFIGURADA", "El servicio no tiene P10_API_TOKEN configurado.")
    esquema, _, token = request.headers.get("authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not hmac.compare_digest(token.strip().encode(), esperado.encode()):
        return _error("NO_AUTORIZADO", "Token ausente o inválido.")
    return None


class _Mala(Exception):
    def __init__(self, mensaje, codigo="SOLICITUD_INVALIDA"):
        super().__init__(mensaje)
        self.codigo = codigo


async def _cuerpo(request):
    largo = request.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > _max_bytes():
        raise _Mala("La solicitud supera el tamaño máximo.", "SOLICITUD_DEMASIADO_GRANDE")
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise _Mala("Content-Type debe ser application/json.")
    crudo = await request.body()
    if len(crudo) > _max_bytes():
        raise _Mala("La solicitud supera el tamaño máximo.", "SOLICITUD_DEMASIADO_GRANDE")
    try:
        cuerpo = json.loads(crudo)
    except ValueError:
        raise _Mala("El cuerpo no es JSON válido.")
    if not isinstance(cuerpo, dict):
        raise _Mala("Se espera un objeto JSON.")
    return cuerpo


def _campo(cuerpo, nombre, tipo, obligatorio=True, defecto=None):
    if nombre not in cuerpo or cuerpo[nombre] is None:
        if obligatorio:
            raise _Mala(f"Falta el campo `{nombre}`.")
        return defecto
    v = cuerpo[nombre]
    if not isinstance(v, tipo) or (tipo is int and isinstance(v, bool)):
        raise _Mala(f"El campo `{nombre}` no tiene el tipo esperado.")
    return v


def _b64(texto, nombre):
    try:
        return base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise _Mala(f"`{nombre}` no es Base64 válido.", "CONTENIDO_INVALIDO")


def _fecha(cuerpo):
    t = _campo(cuerpo, "ahora_local", str)
    if len(t) < 19 or t[10] != "T":
        raise _Mala("`ahora_local` debe ser ISO 'AAAA-MM-DDTHH:MM:SS' en hora de Bolivia.")
    return t[:19]


def _items(cuerpo, nombre, obligatorio=True):
    v = _campo(cuerpo, nombre, list, obligatorio, [])
    if any(not isinstance(i, dict) for i in v):
        raise _Mala(f"Todos los elementos de `{nombre}` deben ser objetos.")
    return v


# ---------------------------------------------------------------- manejadores
def _h_ciclo(c):
    if c.get("control_incompleto") is True:
        return {"ok": False, "codigo_error": "CONTROL_EXCEDE_LIMITE",
                "mensaje": "P10_Control tiene más de 5000 elementos; depurar los registros de extractos antiguos."}
    return PL.ciclo(_fecha(c), _items(c, "control"), _campo(c, "mes_inicio", str, False, "2026-10"),
                    bool(_campo(c, "forzar_completo", bool, False, False)))


def _h_plan(c):
    return PL.plan(_fecha(c), _campo(c, "modo", str), _items(c, "archivos"), _items(c, "control"),
                   _campo(c, "prefijo_servidor", str, False, ""), _campo(c, "limite", int, False, PL.MAX_EXTRACTOS_NORMAL))


def _h_delta(c):
    r = PL.delta(_items(c, "items"), _items(c, "control"), _fecha(c), _campo(c, "cursor_desde", str, False, ""))
    for g in r["sucios"]:
        g["rutas"] = S.rutas_grupo(E.grupo_desde_id(g["grupo_id"]))
    return r


def _h_clasificar(c):
    r = PL.clasificar(_campo(c, "periodo", str), _items(c, "items"), _items(c, "control"), _campo(c, "modo", str, False, "NORMAL"),
                      bool(_campo(c, "hay_mas", bool, False, False)), _campo(c, "verificar", list, False, []), _campo(c, "banco", str, False))
    for g in r.get("sucios", []):                       # el flujo necesita las rutas ANTES de llamar a /sincronizar
        g["rutas"] = S.rutas_grupo(E.grupo_desde_id(g["grupo_id"]))
    return r


def _h_extracto(c):
    contenido = _b64(_campo(c, "contenido_base64", str), "contenido_base64")
    with _SERIE:
        return S.procesar_extracto(contenido, _campo(c, "nombre_archivo", str), _campo(c, "sede", str), _campo(c, "ruta", str),
                                   _fecha(c), _campo(c, "intentos", int, False, 0))


def _h_sincronizar(c):
    estado = _campo(c, "estado_base64", str, False)
    xlsx = _campo(c, "xlsx_actual_base64", str, False)
    parciales = _campo(c, "parciales_base64", list, False, [])
    if any(not isinstance(p, str) for p in parciales):
        raise _Mala("`parciales_base64` debe ser una lista de textos Base64.")
    filas = c.get("filas")
    if filas is not None and (not isinstance(filas, list) or any(not isinstance(f, dict) for f in filas)):
        raise _Mala("`filas` debe ser una lista de objetos o null.")
    control = c.get("control_grupo")
    if control is not None and not isinstance(control, dict):
        raise _Mala("`control_grupo` debe ser un objeto o null.")
    with _SERIE:
        return S.sincronizar_grupo(
            _campo(c, "sede", str), _campo(c, "grupo_id", str), _b64(estado, "estado_base64") if estado else None,
            [_b64(p, "parciales_base64") for p in parciales], filas, _fecha(c), control,
            bool(_campo(c, "forzar_xlsx", bool, False, False)), bool(_campo(c, "verificar_xlsx", bool, False, False)),
            _b64(xlsx, "xlsx_actual_base64") if xlsx else None, bool(_campo(c, "finalizar", bool, False, False)), bool(_campo(c, "parcial_lista", bool, False, False)))


RUTAS = {"ciclo": _h_ciclo, "plan": _h_plan, "delta": _h_delta, "clasificar": _h_clasificar,
         "extracto": _h_extracto, "sincronizar": _h_sincronizar}


@app.get("/health")
def health():
    return {"status": "ok", "servicio": "p10-historico", "version": S.VERSION}


@app.post("/p10/{operacion}")
async def operar(operacion: str, request: Request):
    rechazo = _autorizado(request)
    if rechazo is not None:
        return rechazo
    manejador = RUTAS.get(operacion)
    if manejador is None:
        return _error("OPERACION_DESCONOCIDA", "Operación desconocida.", 404)
    try:
        cuerpo = await _cuerpo(request)
        resultado = await run_in_threadpool(manejador, cuerpo)
    except _Mala as e:
        return _error(e.codigo, str(e))
    except (KeyError, TypeError, ValueError, AttributeError):       # forma inesperada de los datos; sin contenido bancario en el log
        _log.exception("p10 %s: datos con forma inesperada", operacion)
        return _error("SOLICITUD_INVALIDA", "Los datos recibidos no tienen la forma esperada.")
    except Exception:
        _log.exception("p10 %s: error interno", operacion)
        return _error("ERROR_INESPERADO", "Error interno inesperado.", 500)
    _log.info("p10 %s ok=%s", operacion, resultado.get("ok"))
    # Un extracto rechazado (incluido un error inesperado al procesarlo) responde 200 con ok:false y su registro de control listo:
    # el flujo lo anota y sigue. Solo un fallo del propio servicio (excepción no controlada, arriba) responde 5xx.
    return JSONResponse(resultado, status_code=200)
