"""P0 · API HTTP sin estado para Railway.

    GET  /health               -> {"status": "ok", ...}   (sin autenticación; para el healthcheck de Railway)
    POST /procesar-extracto    -> procesa UN extracto en memoria/temporal y devuelve el JSON de P7 (ver P0_AUTOMATIZACION_EXTRACTOS.md)

Autenticación: cabecera `Authorization: Bearer <P0_API_TOKEN>` (variable de entorno; sin ella el servicio rechaza todo).
No persiste nada: ni base de datos, ni volumen, ni archivos de los extractos o de los JSON.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from p0 import nucleo

MAX_BYTES_DEFECTO = 30 * 1024 * 1024
HTTP_ERROR = {"SEDE_DESCONOCIDA": 400, "SOLICITUD_INVALIDA": 400, "CONTENIDO_INVALIDO": 400, "NO_AUTORIZADO": 401,
              "ARCHIVO_DEMASIADO_GRANDE": 413, "API_NO_CONFIGURADA": 503}

if not logging.getLogger("p0").handlers:  # logs técnicos a stdout (Railway los recoge); nunca contenido bancario
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("p0").addHandler(_h)
    logging.getLogger("p0").setLevel(logging.INFO)

app = FastAPI(title="P0 extractos", docs_url=None, redoc_url=None, openapi_url=None)


def _max_bytes():
    try:
        return int(os.environ.get("P0_MAX_BYTES", MAX_BYTES_DEFECTO))
    except ValueError:
        return MAX_BYTES_DEFECTO


def _error(codigo, mensaje, etapa="API", status=None, extra=None):
    cuerpo = {"ok": False, "resultado": "ERROR", "version": nucleo.VERSION, "etapa": etapa,
              "codigo_error": codigo, "mensaje": mensaje}
    cuerpo.update(extra or {})
    return JSONResponse(cuerpo, status_code=status or HTTP_ERROR.get(codigo, 500))


def _autorizado(request):
    esperado = os.environ.get("P0_API_TOKEN", "")
    if len(esperado) < 16:  # sin secreto configurado (o demasiado corto) no se procesa nada
        return _error("API_NO_CONFIGURADA", "El servicio no tiene P0_API_TOKEN configurado.")
    cabecera = request.headers.get("authorization", "")
    esquema, _, token = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not hmac.compare_digest(token.strip().encode(), esperado.encode()):
        return _error("NO_AUTORIZADO", "Token ausente o inválido.")
    return None


async def _leer_solicitud(request):
    """-> (sede, nombre_archivo, bytes). Acepta JSON (contenido_base64) o multipart (campos `sede` y `archivo`)."""
    limite = _max_bytes()
    largo = request.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > limite * 2:  # base64 pesa ~4/3 + sobre
        raise nucleo.ErrorP0("API", "ARCHIVO_DEMASIADO_GRANDE", f"El archivo supera el máximo de {limite} bytes.")
    tipo = request.headers.get("content-type", "").lower()
    if tipo.startswith("multipart/form-data"):
        form = await request.form()
        try:
            sede, archivo = form.get("sede"), form.get("archivo")
            if not sede or archivo is None or not hasattr(archivo, "read"):
                raise nucleo.ErrorP0("API", "SOLICITUD_INVALIDA", "Faltan los campos multipart `sede` y `archivo`.")
            nombre = form.get("nombre_archivo") or getattr(archivo, "filename", "") or "extracto"
            datos = await archivo.read()
        finally:
            await form.close()
    elif tipo.startswith("application/json"):
        try:
            cuerpo = json.loads(await request.body())
            sede, nombre, b64 = cuerpo["sede"], cuerpo["nombre_archivo"], cuerpo["contenido_base64"]
            if not (isinstance(sede, str) and sede and isinstance(nombre, str) and nombre and isinstance(b64, str)):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise nucleo.ErrorP0("API", "SOLICITUD_INVALIDA",
                                 "Se espera JSON con `sede`, `nombre_archivo` y `contenido_base64` (texto).")
        try:
            datos = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise nucleo.ErrorP0("API", "CONTENIDO_INVALIDO", "`contenido_base64` no es Base64 válido.")
    else:
        raise nucleo.ErrorP0("API", "SOLICITUD_INVALIDA", "Content-Type debe ser application/json o multipart/form-data.")
    if len(datos) > limite:
        raise nucleo.ErrorP0("API", "ARCHIVO_DEMASIADO_GRANDE", f"El archivo supera el máximo de {limite} bytes.")
    return sede, nombre, datos


@app.get("/health")
def health():
    return {"status": "ok", "servicio": "p0-extractos", "version": nucleo.VERSION}


@app.post("/procesar-extracto")
async def procesar_extracto(request: Request):
    rechazo = _autorizado(request)
    if rechazo is not None:
        return rechazo
    try:
        sede, nombre, datos = await _leer_solicitud(request)
    except nucleo.ErrorP0 as e:
        return _error(e.codigo, e.mensaje)
    try:
        resultado = await run_in_threadpool(nucleo.procesar_extracto, datos, nombre, sede)
    except nucleo.SedeDesconocida as e:
        return _error("SEDE_DESCONOCIDA", str(e))
    except nucleo.ConfigError:
        return _error("CONFIGURACION_INVALIDA", "Configuración de la sede inválida.", status=500)
    # Archivo rechazado por reglas de negocio -> 200 con ok:false (Power Automate lo ramifica con una condición).
    # Fallo interno inesperado -> 500.
    status = 500 if resultado.get("codigo_error") == "ERROR_INESPERADO" else 200
    return JSONResponse(resultado, status_code=status)
