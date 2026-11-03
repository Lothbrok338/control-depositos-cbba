"""Construye el flujo P9_ASIGNAR_DEPOSITO (trigger Power Apps V2) y su ZIP.

Ejecutar: python -m p9.asignar.construir
Solo conectores estándar: Power Apps (V2) / Respuesta a PowerApps (integrados) y «Enviar una solicitud HTTP a SharePoint».
Dos llamadas SharePoint por asignación: GET del elemento (con su ETag) y MERGE condicionado con If-Match = ETag.
"""
from __future__ import annotations

import json
from pathlib import Path

from p9 import contrato as C
from p9.paquete import RAIZ, escribir_zip
from p9.wdl import (TODOS, FALLOS, agregar, ambito, asignar, compose, contar_acciones, definicion, http_sharepoint,
                    lista_uri, parametros_sitio, secuencia, si, variable)

CARPETA = Path(__file__).resolve().parent
DEFINICION_SALIDA = CARPETA / "flujo_asignar_definition.json"
ZIP_SALIDA = RAIZ / C.ZIP_ASIGNAR
SELECCION_LECTURA = "Id,CLAVE_TRANSACCION,ESTADO_ASIGNACION,USUARIO_ASIGNACION,FECHA_HORA_ASIGNACION"


def E(clave):
    """Referencia WDL a un campo normalizado de la acción Entrada."""
    return f"outputs('Entrada')?['{clave}']"


def D(campo):
    return f"outputs('Deposito')?['{campo}']"


def respuesta(resultado, codigo, mensaje, estado_actual="", asignado_por="", fecha=""):
    return {"resultado": resultado, "codigo": codigo, "mensaje": mensaje, "estado_actual": estado_actual,
            "asignado_por": asignado_por, "fecha_hora_asignacion": fecha}


def trigger():
    propiedades = {}
    for clave, _, tipo, _, titulo in C.ENTRADAS:
        propiedades[clave] = {"title": titulo, "type": tipo, "x-ms-dynamically-added": True,
                              "description": f"Valor de {titulo} enviado por la app",
                              "x-ms-content-hint": "NUMBER" if tipo == "number" else "TEXT"}
    return {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {
        "type": "object", "properties": propiedades, "required": [c[0] for c in C.ENTRADAS if c[3]]}}}}


def entrada():
    valores = {}
    for clave, nombre, tipo, _, _ in C.ENTRADAS:
        origen = f"triggerBody()?['{clave}']"
        if tipo == "number":
            valores[nombre] = f"@coalesce({origen},0)"
        elif nombre == "clave":
            valores[nombre] = f"@coalesce({origen},'')"  # la clave NO se recorta: debe coincidir exactamente
        else:
            valores[nombre] = f"@trim(coalesce({origen},''))"
    return valores


def validacion():
    vacio = ",".join(f"empty({E(k)})" for k in C.OBLIGATORIOS_TEXTO)
    largo = ",".join(f"greater(length({E(k)}),{C.MAX_TEXTO})" for k in C.OBLIGATORIOS_TEXTO)
    id_malo = f"or(less({E('id')},1),contains(string({E('id')}),'.'))"
    return f"@if(or({vacio}),'CAMPOS_OBLIGATORIOS',if(or({largo}),'CAMPO_EXCEDE_255',if({id_malo},'ID_INVALIDO','')))"


def rama_asignar():
    cuerpo = {campo: f"@{E(nombre)}" for campo, nombre in [
        ("ESTUDIANTE", "estudiante"), ("CODIGO_ESTUDIANTE", "codigo_estudiante"), ("SOLICITADO_POR", "solicitado_por"),
        ("SEDE_ASIGNACION", "sede_asignacion"), ("OBSERVACION", "observacion"), ("USUARIO_ASIGNACION", "usuario")]}
    cuerpo = {"ESTADO_ASIGNACION": C.ESTADO_ASIGNADO, **cuerpo, "FECHA_HORA_ASIGNACION": "@outputs('Ahora')"}
    assert tuple(cuerpo) == tuple(sorted(cuerpo, key=C.CAMPOS_ESCRITOS.index)) and set(cuerpo) == set(C.CAMPOS_ESCRITOS)
    return secuencia(
        Ahora=compose("@utcNow()"),
        Cuerpo_actualizacion=compose(cuerpo),
        Etapa_actualizar=asignar("varEtapa", "ACTUALIZAR"),
        Actualizar_deposito=http_sharepoint(
            "POST", lista_uri(["/items(", ("x", f"string({E('id')})"), ")"]),
            {"Accept": "application/json;odata=nometadata", "Content-Type": "application/json;odata=nometadata",
             "X-HTTP-Method": "MERGE", "IF-MATCH": "@outputs('ETag')"},
            "@string(outputs('Cuerpo_actualizacion'))"),
        Resultado_ASIGNADO=asignar("varRespuesta", respuesta(
            "ASIGNADO", "ASIGNADO", "Depósito asignado correctamente.", C.ESTADO_ASIGNADO, "@" + E("usuario"),
            "@outputs('Ahora')")),
    )


def cuerpo_principal():
    leer = http_sharepoint(
        "GET", lista_uri(["/items(", ("x", f"string({E('id')})"), f")?$select={SELECCION_LECTURA}"]),
        {"Accept": "application/json;odata=verbose"})
    disponible = si(f"@equals({D('ESTADO_ASIGNACION')},'{C.ESTADO_DISPONIBLE}')", secuencia(
        Con_ETag=si("@not(empty(outputs('ETag')))", rama_asignar(), secuencia(
            Resultado_ERROR_SIN_ETAG=asignar("varRespuesta", respuesta(
                "ERROR", "SIN_ETAG", "SharePoint no devolvió el ETag del depósito; no se aplicó ningún cambio.")))),
    ), secuencia(
        Resultado_NO_DISPONIBLE=asignar("varRespuesta", respuesta(
            "NO_DISPONIBLE", "NO_DISPONIBLE", "El depósito ya no está disponible. No se aplicó ningún cambio.",
            f"@coalesce({D('ESTADO_ASIGNACION')},'')", f"@coalesce({D('USUARIO_ASIGNACION')},'')",
            f"@coalesce({D('FECHA_HORA_ASIGNACION')},'')"))))
    coincide = si(f"@equals({D('CLAVE_TRANSACCION')},{E('clave')})", secuencia(Estado_disponible=disponible),
                  secuencia(Resultado_CLAVE_NO_COINCIDE=asignar("varRespuesta", respuesta(
                      "ERROR", "CLAVE_NO_COINCIDE",
                      "La CLAVE_TRANSACCION enviada no coincide con la del depósito (ID de SharePoint). No se aplicó ningún cambio."))))
    valida = secuencia(
        Etapa_leer=asignar("varEtapa", "LEER"),
        Leer_deposito=leer,
        Deposito=compose("@body('Leer_deposito')?['d']"),
        ETag=compose("@coalesce(outputs('Deposito')?['__metadata']?['etag'],outputs('Leer_deposito')?['headers']?['ETag'],'')"),
        Clave_coincide=coincide,
    )
    invalida = secuencia(Resultado_ENTRADA_INVALIDA=asignar("varRespuesta", respuesta(
        "ERROR", "@outputs('Validar_entrada')", "Faltan datos obligatorios o exceden 255 caracteres. No se aplicó ningún cambio.")))
    return secuencia(Entrada_valida=si("@empty(outputs('Validar_entrada'))", valida, invalida))


def captura_fallos():
    """CATCH: clasifica el fallo SOLO con acciones que sabemos que corrieron (varEtapa)."""
    def err(codigo, mensaje, nombre):
        return secuencia(**{nombre: asignar("varRespuesta", respuesta("ERROR", codigo, mensaje))})
    conflicto = secuencia(Resultado_CONFLICTO=asignar("varRespuesta", respuesta(
        "CONFLICTO", "CONFLICTO", "Otro usuario modificó el depósito mientras se asignaba. No se aplicó tu asignación.",
        "", "")))
    actualizar = si("@equals(outputs('Actualizar_deposito')?['statusCode'],412)", conflicto, err(
        "ACTUALIZACION_NO_CONFIRMADA",
        "No se pudo confirmar la asignación. Actualice la lista y verifique el depósito antes de reintentar.",
        "Resultado_ACTUALIZACION_NO_CONFIRMADA"))
    leer = si("@equals(outputs('Leer_deposito')?['statusCode'],404)", err(
        "DEPOSITO_NO_ENCONTRADO", "No existe un depósito con ese ID en SharePoint. No se aplicó ningún cambio.",
        "Resultado_DEPOSITO_NO_ENCONTRADO"), err(
        "ERROR_LECTURA", "No se pudo leer el depósito en SharePoint. No se aplicó ningún cambio.",
        "Resultado_ERROR_LECTURA"))
    otro = err("ERROR_NO_CONTROLADO", "Error inesperado antes de tocar SharePoint. No se aplicó ningún cambio.",
               "Resultado_ERROR_NO_CONTROLADO")
    return secuencia(Clasificar_fallo=si(
        "@equals(variables('varEtapa'),'ACTUALIZAR')", secuencia(Fallo_en_actualizar=actualizar),
        secuencia(Fallo_antes_de_actualizar=si("@equals(variables('varEtapa'),'LEER')", secuencia(Fallo_en_leer=leer), otro))))


def construir_definicion():
    acciones = secuencia(
        **parametros_sitio(),
        Entrada=compose(entrada()),
        Inicializar_varEtapa=variable("varEtapa", "string", "ENTRADA"),
        Inicializar_varRespuesta=variable("varRespuesta", "object", respuesta(
            "ERROR", "ERROR_NO_CONTROLADO", "La asignación no se completó. No se aplicó ningún cambio.")),
        Validar_entrada=compose(validacion()),
        TRY=ambito(cuerpo_principal()),
    )
    acciones["CATCH"] = ambito(captura_fallos(), {"TRY": FALLOS})
    cuerpo = {k: f"@variables('varRespuesta')?['{k}']" for k in C.SALIDAS}
    esquema = {"type": "object", "properties": {k: {"title": k, "type": "string"} for k in C.SALIDAS}}
    acciones["Responder_a_PowerApps"] = {
        "type": "Response", "kind": "PowerApp", "runAfter": {"TRY": TODOS, "CATCH": TODOS},
        "inputs": {"statusCode": 200, "body": cuerpo, "schema": esquema}}
    return definicion(trigger(), acciones)


def generar():
    d = construir_definicion()
    DEFINICION_SALIDA.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    escribir_zip(ZIP_SALIDA, C.NOMBRE_FLUJO_ASIGNAR,
                 "Asigna un depósito DISPONIBLE -> ASIGNADO con control optimista If-Match/ETag; trigger Power Apps (V2).", d)
    return ZIP_SALIDA, contar_acciones(d["actions"])


if __name__ == "__main__":
    ruta, n = generar()
    print(ruta, f"({n} acciones)")
