"""Generador del flujo PROTOTIPO `P9_MASIVA_PROTO_ESTADO` (consulta de progreso de la confirmación masiva) y de su ZIP importable.

    python -m proto_masiva.flows.construir_estado

Existe por una limitación real: Power Apps no puede leer el archivo JSON de `P9_MASIVA_TEMP` (solo ve listas ya conectadas), y el flujo de confirmación ya
respondió y sigue procesando. Este flujo es de SOLO LECTURA: recibe `execution_uid`, lee `confirmacion_<execution_uid>.json` de la carpeta técnica
`Documents/P9_MASIVA_TEMP` (la misma que ya usa la prevalidación) y devuelve su contenido a Power Apps como 9 textos. No escribe nada.

Siempre responde (una sola respuesta, también ante errores): `estado` = PROCESANDO | TERMINADO | ERROR | NO_ENCONTRADO.
Power Apps lo llama con un Timer cada 10-15 s (NO cada segundo).
"""
from __future__ import annotations

import json
from pathlib import Path

from p9.wdl import FALLOS, TODOS, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable
from proto_masiva.flows import construir as BASE
from proto_masiva.flows import construir_confirmar as K

CARPETA_SALIDA = Path(__file__).resolve().parent
NOMBRE_FLUJO = "P9_MASIVA_PROTO_ESTADO"
ENTRADAS = (("text", "execution_uid", "Identificador devuelto por P9_MASIVA_PROTO_CONFIRMAR (execution_uid)"),)
ESTADOS_RESPUESTA = K.ESTADOS + ("NO_ENCONTRADO",)
SALIDAS = ("estado", "filas_totales", "filas_procesadas", "filas_confirmadas", "filas_no_confirmadas", "porcentaje", "mensaje", "detalle_json",
           "tiempos_ms")


def disparador():
    props = {c: {"title": t, "type": "string", "x-ms-dynamically-added": True, "description": d, "x-ms-content-hint": "TEXT"} for c, t, d in ENTRADAS}
    return {"manual": {"type": "Request", "kind": "PowerAppV2", "inputs": {"schema": {
        "type": "object", "properties": props, "required": [c for c, _, _ in ENTRADAS]}}}}


def _estado(campo, defecto):
    return f"coalesce(variables('varEstado')?['{campo}'],{defecto})"


def construir_definicion():
    uid = "outputs('Entrada')?['uid']"
    # un execution_uid es un GUID de 36 caracteres en minúsculas: LISTA BLANCA (solo 0-9, a-f y «-»); cualquier otro carácter (/, \\, ., %, :) se rechaza,
    # así que nadie puede construir una ruta distinta de confirmacion_<guid>.json
    resto = f"toLower({uid})"
    for caracter in "0123456789abcdef-":
        resto = f"replace({resto},{K.lit(caracter)},'')"
    invalido = f"or(not(equals(length({uid}),36)),not(empty({resto})))"
    leer = secuencia(
        Leer_estado=BASE._sp("GetFileContentByPath", {
            "dataset": "@outputs('PARAM_SITIO')",
            "path": f"@concat(outputs('PARAM_CARPETA'),'/',{K.lit(K.PREFIJO_ESTADO)},{uid},'.json')",
            "inferContentType": False}, retryPolicy={"type": "none"}),
        # inferContentType=false → siempre llega como binario en base64 ($content). Si por algún motivo llegara ya como objeto, se usa tal cual.
        Guardar_estado=asignar("varEstado", "@if(empty(body('Leer_estado')?['$content']),body('Leer_estado'),"
                                            "json(base64ToString(body('Leer_estado')?['$content'])))"))
    captura = secuencia(Clasificar=si(
        "@equals(outputs('Leer_estado')?['statusCode'],404)",
        secuencia(No_encontrado_estado=asignar("varFalloEstado", "NO_ENCONTRADO"),
                  No_encontrado_mensaje=asignar("varFalloMensaje", "Todavía no existe el registro de progreso de esta ejecución.")),
        secuencia(Error_estado=asignar("varFalloEstado", "ERROR"),
                  Error_mensaje=asignar("varFalloMensaje", "No se pudo leer el progreso de la confirmación. Puede seguir ejecutándose en segundo plano."))))
    acciones = secuencia(
        PARAM_SITIO=compose(K.SITIO),
        PARAM_CARPETA=compose(K.CARPETA_ESTADO),
        Entrada=compose({"uid": "@trim(coalesce(triggerBody()?['text'],''))"}),
        Inicializar_varEstado=variable("varEstado", "object", {}),
        Inicializar_varFalloEstado=variable("varFalloEstado", "string", "ERROR"),
        Inicializar_varFalloMensaje=variable("varFalloMensaje", "string", "No se pudo leer el progreso de la confirmación."),
        Validar_uid=compose(f"@if({invalido},'UID_INVALIDO','')"),
        TRY=ambito(secuencia(Uid_valido=si("@empty(outputs('Validar_uid'))", leer,
                                           secuencia(Uid_invalido=asignar("varFalloMensaje", "execution_uid inválido."))))))
    acciones["CATCH"] = ambito(captura, {"TRY": FALLOS})
    cuerpo = {
        "estado": "@" + _estado("estado", "variables('varFalloEstado')"),
        "filas_totales": "@string(" + _estado("filas_totales", "0") + ")",
        "filas_procesadas": "@string(" + _estado("filas_procesadas", "0") + ")",
        "filas_confirmadas": "@string(" + _estado("filas_confirmadas", "0") + ")",
        "filas_no_confirmadas": "@string(" + _estado("filas_no_confirmadas", "0") + ")",
        "porcentaje": "@string(" + _estado("porcentaje", "0") + ")",
        "mensaje": "@" + _estado("mensaje", "variables('varFalloMensaje')"),
        "detalle_json": "@string(" + _estado("detalle_json", "createArray()") + ")",
        "tiempos_ms": "@" + _estado("tiempos_ms", "''")}
    assert tuple(cuerpo) == SALIDAS
    esquema = {"type": "object", "properties": {k: {"title": k, "type": "string", "x-ms-dynamically-added": True} for k in SALIDAS}}
    acciones["Responder_a_PowerApps"] = {"type": "Response", "kind": "PowerApp", "runAfter": {"TRY": TODOS, "CATCH": TODOS},
                                         "inputs": {"statusCode": 200, "body": cuerpo, "schema": esquema}}
    return definicion(disparador(), acciones)


CONEXIONES = {"shared_sharepointonline": ("SharePoint", "sharepointonline")}
DESCRIPCION = ("PROTOTIPO: devuelve a Power Apps el avance de una confirmación masiva (P9_MASIVA_PROTO_CONFIRMAR) leyendo "
               "Documents/P9_MASIVA_TEMP/confirmacion_<execution_uid>.json. Solo lectura.")


def zip_bytes(definition):
    return BASE.zip_bytes(definition, nombre=NOMBRE_FLUJO, conexiones_flujo=CONEXIONES, descripcion=DESCRIPCION)


def generar():
    d_ = construir_definicion()
    (CARPETA_SALIDA / f"{NOMBRE_FLUJO}_definition.json").write_text(json.dumps(d_, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destino = CARPETA_SALIDA / f"{NOMBRE_FLUJO}.zip"
    destino.write_bytes(zip_bytes(d_))
    return destino, contar_acciones(d_["actions"])


if __name__ == "__main__":
    ruta, n = generar()
    print(ruta, f"({n} acciones)")
