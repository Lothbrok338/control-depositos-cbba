"""Genera el provisionador manual V2; nunca accede al tenant desde Python.

Columnas existentes se verifican sin corregirlas automáticamente. Los cambios
de metadatos de Field no llevan If-Match: Microsoft limita ETags a listas e
items. Solo se configura el GUID devuelto al crear una columna, salvo Title
de una lista recién creada. No hay escritura de elementos de negocio.
"""
from __future__ import annotations

import hashlib
import json
from xml.etree import ElementTree as ET

from p9.wdl import agregar, ambito, compose, definicion, secuencia, si, variable
from . import contrato as C

TODOS = ["Succeeded", "Failed", "Skipped", "TimedOut"]
FALLOS = ["Failed", "TimedOut"]
SELECT_CAMPOS = "Id,InternalName,Title,TypeAsString,Required,Indexed,EnforceUniqueValues,DefaultValue,SchemaXml,Hidden,ReadOnlyField,FromBaseType"
SELECT_LISTA = "Id,Title,BaseTemplate,ContentTypesEnabled,Hidden,EnableVersioning"
METADATA = {"Text": "SP.FieldText", "Note": "SP.FieldMultiLineText", "DateTime": "SP.FieldDateTime",
            "Number": "SP.FieldNumber", "Choice": "SP.FieldChoice"}


def compilar(esquema=None):
    esquema = C.cargar_esquema() if esquema is None else esquema
    C.validar_esquema(esquema)
    plan = []
    for lista in (C.LISTA_DEPOSITOS, C.LISTA_REVERSIONES):
        contrato = esquema[lista]
        campos = []
        for c in contrato["columnas"]:
            nombre, tipo = c["nombre_tecnico"], c["tipo"]
            attrs = {"Name": nombre, "StaticName": nombre, "DisplayName": nombre, "Type": tipo,
                     "Required": str(c["obligatoria"]).upper(), "Hidden": "FALSE"}
            esperado = {"InternalName": nombre, "Title": c["nombre_visible"], "TypeAsString": tipo,
                        "Required": c["obligatoria"], "Indexed": c["indexada"],
                        "EnforceUniqueValues": c["valores_unicos"], "Hidden": False, "ReadOnlyField": False,
                        "DefaultValue": c.get("predeterminado", "")}
            if tipo == "Text":
                attrs["MaxLength"] = str(c["max_length"])
                esperado["MaxLength"] = attrs["MaxLength"]
            elif tipo == "Note":
                attrs.update(RichText="FALSE", AppendOnly="FALSE")
                esperado.update(RichText=False, AppendOnly=False)
            elif tipo == "DateTime":
                attrs["Format"] = c["format"]
                esperado["Format"] = c["format"]
            elif tipo == "Number":
                attrs.update(Decimals=str(c["decimals"]), Percentage="FALSE")
                esperado.update(Decimals=str(c["decimals"]), Percentage=False)
                if "min" in c:
                    attrs["Min"] = str(c["min"])
                    esperado["Min"] = str(c["min"])
            elif tipo == "Choice":
                attrs.update(FillInChoice="FALSE", Format="Dropdown")
                esperado.update(Choices=c["valores"], FillInChoice=False)
            xml = ET.Element("Field", attrs)
            if tipo == "Choice":
                opciones = ET.SubElement(xml, "CHOICES")
                for valor in c["valores"]:
                    ET.SubElement(opciones, "CHOICE").text = valor
            if "predeterminado" in c:
                ET.SubElement(xml, "Default").text = c["predeterminado"]
            campos.append({
                "Nombre": nombre, "NombreVisible": c["nombre_visible"],
                "Crear": {"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                                          "SchemaXml": ET.tostring(xml, encoding="unicode"), "Options": 9}},
                "Configurar": {"__metadata": {"type": METADATA[tipo]}, "Title": c["nombre_visible"],
                               "Required": c["obligatoria"], "Indexed": c["indexada"],
                               "DefaultValue": c.get("predeterminado", "")},
                "Unicidad": {"__metadata": {"type": METADATA[tipo]}, "EnforceUniqueValues": True},
                "ExigeUnicidad": c["valores_unicos"],
                "Propiedades": [{"propiedad": k, "esperado": v} for k, v in esperado.items()],
            })
        plan.append({
            "Nombre": lista, "PermitirCrear": contrato["crear_si_ausente"], "Campos": campos,
            "Nombres": [c["Nombre"] for c in campos], "Cantidad": len(campos),
            "ExigirVersionado": contrato.get("versionado", False),
            "VerificarTitle": lista == C.LISTA_REVERSIONES,
            "Ruta": f"_api/web/lists/getbytitle('{lista}')",
            "Buscar": f"_api/web/lists?$select={SELECT_LISTA}&$filter=Title eq '{lista}'&$top=2",
            "Crear": {"__metadata": {"type": "SP.List"}, "Title": lista, "BaseTemplate": 100,
                      "ContentTypesEnabled": False, "EnableVersioning": True},
        })
    return plan


def http(metodo, uri, cuerpo=None, campo=False):
    headers = {"Accept": "application/json;odata=nometadata"}
    if cuerpo is not None:
        headers["Content-Type"] = "application/json;odata=verbose"
    if campo:
        headers["X-HTTP-Method"] = "MERGE"
    parametros = {"dataset": "@outputs('PARAM_SITIO_SHAREPOINT')", "parameters/method": metodo,
                  "parameters/uri": uri, "parameters/headers": headers}
    if cuerpo is not None:
        parametros["parameters/body"] = cuerpo
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                 "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": parametros, "authentication": "@parameters('$authentication')",
        "retryPolicy": {"type": "none"}}}


def cada(fuente, acciones):
    return {"type": "Foreach", "foreach": fuente, "actions": acciones,
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}}}


def ruta(bucle, sufijo):
    return "@concat(items('%s')?['Ruta'],'%s')" % (bucle, sufijo.replace("'", "''"))


def query(fuente, filtro):
    return {"type": "Query", "inputs": {"from": fuente, "where": filtro}}


def diferencia(lista, campo, propiedad, esperado, actual):
    return agregar("Diferencias", {"lista": lista, "campo": campo, "propiedad": propiedad,
                                    "esperado": esperado, "actual": actual})


def observado():
    campo = "first(body('Campo_por_nombre_exacto'))"
    xml = f"xml({campo}?['SchemaXml'])"
    props = {k: f"@{campo}?['{k}']" for k in (
        "InternalName", "Title", "TypeAsString", "Required", "Indexed", "EnforceUniqueValues", "Hidden", "ReadOnlyField")}
    props["DefaultValue"] = f"@coalesce({campo}?['DefaultValue'],'')"
    props["Choices"] = f"@xpath({xml},'/Field/CHOICES/CHOICE/text()')"
    for p in ("RichText", "AppendOnly", "FillInChoice", "Percentage"):
        props[p] = f"@equals(toLower(xpath({xml},'string(/Field/@{p})')),'true')"
    for p in ("Format", "Decimals", "MaxLength", "Min"):
        props[p] = f"@xpath({xml},'string(/Field/@{p})')"
    return props


def construir_definicion():
    plan = compilar()
    lp, lv = "@items('Provisionar_listas')?['Nombre']", "@items('Verificar_listas')?['Nombre']"
    cp, cv = "@items('Provisionar_columnas')?['Nombre']", "@items('Verificar_columnas')?['Nombre']"
    ruta_nueva = "@concat(items('Provisionar_listas')?['Ruta'],'/fields(guid''',body('Crear_columna')?['Id'],''')')"
    crear = secuencia(
        Crear_columna=http("POST", ruta("Provisionar_listas", "/fields/createfieldasxml"), "@string(items('Provisionar_columnas')?['Crear'])"),
        Configurar_columna_nueva=http("POST", ruta_nueva, "@string(items('Provisionar_columnas')?['Configurar'])", campo=True),
        Activar_unicidad_si_corresponde=si("@items('Provisionar_columnas')?['ExigeUnicidad']", secuencia(
            Exigir_unicidad=http("POST", ruta_nueva, "@string(items('Provisionar_columnas')?['Unicidad'])", campo=True))))
    err_col = diferencia(lp, cp, "REST_CREACION", "Creación y configuración comprobables", {
        "crear": "@actions('Crear_columna')?['status']", "configurar": "@actions('Configurar_columna_nueva')?['status']",
        "unicidad": "@actions('Exigir_unicidad')?['status']"})
    err_col["runAfter"] = {"Crear_solo_si_ausente": FALLOS}
    columnas = cada("@items('Provisionar_listas')?['Campos']", secuencia(
        Colision_nombre_o_titulo=query("@body('Campos_antes')?['value']", "@or(equals(toLower(item()?['InternalName']),toLower(items('Provisionar_columnas')?['Nombre'])),equals(toLower(item()?['Title']),toLower(items('Provisionar_columnas')?['Nombre'])),equals(toLower(item()?['Title']),toLower(items('Provisionar_columnas')?['NombreVisible'])))"),
        Crear_solo_si_ausente=si("@empty(body('Colision_nombre_o_titulo'))", crear),
        CATCH_CREAR_COLUMNA=err_col))
    preparar = secuencia(
        Buscar_lista=http("GET", "@items('Provisionar_listas')?['Buscar']"),
        Crear_lista_si_ausente=si("@and(equals(length(body('Buscar_lista')?['value']),0),items('Provisionar_listas')?['PermitirCrear'])", secuencia(
            Crear_lista=http("POST", "_api/web/lists", "@string(items('Provisionar_listas')?['Crear'])"),
            Liberar_Title_nueva=http("POST", ruta("Provisionar_listas", "/fields/getbyinternalnameortitle('Title')"),
                                    json.dumps({"__metadata": {"type": "SP.FieldText"}, "Required": False}), campo=True))),
        Leer_lista_pre=http("GET", ruta("Provisionar_listas", f"?$select={SELECT_LISTA}")),
        Lista_apta=si("@and(lessOrEquals(length(body('Buscar_lista')?['value']),1),equals(body('Leer_lista_pre')?['Title'],items('Provisionar_listas')?['Nombre']),equals(body('Leer_lista_pre')?['BaseTemplate'],100),equals(body('Leer_lista_pre')?['ContentTypesEnabled'],false),equals(body('Leer_lista_pre')?['Hidden'],false),not(empty(body('Leer_lista_pre')?['Id'])))", secuencia(
            Campos_antes=http("GET", ruta("Provisionar_listas", f"/fields?$select={SELECT_CAMPOS}&$top=5000")),
            Sin_paginacion_pre=si("@and(empty(body('Campos_antes')?['odata.nextLink']),empty(body('Campos_antes')?['@odata.nextLink']),empty(body('Campos_antes')?['__next']))", secuencia(
                Provisionar_columnas=columnas), secuencia(
                Paginacion_pre=diferencia(lp, "", "PAGINACION_PRE", "Inventario completo", "No se crean columnas desde una página parcial"))),
        ), secuencia(Lista_incompatible=diferencia(lp, "", "CONFIGURACION_LISTA", "Lista genérica y GUID verificables", "@body('Leer_lista_pre')"))))
    err_lista = diferencia(lp, "", "REST_PROVISION", "Lecturas/escrituras válidas", "@result('TRY_PROVISION_LISTA')")
    err_lista["runAfter"] = {"TRY_PROVISION_LISTA": FALLOS}
    provision = cada("@outputs('Contrato_compilado')", secuencia(
        TRY_PROVISION_LISTA=ambito(preparar), CATCH_PROVISION_LISTA=err_lista))

    propiedades = cada("@items('Verificar_columnas')?['Propiedades']", secuencia(
        Comparar_propiedad=si("@not(equals(outputs('Propiedades_observadas')?[items('Verificar_propiedades')?['propiedad']],items('Verificar_propiedades')?['esperado']))", secuencia(
            Diferencia_propiedad=diferencia(lv, cv, "@items('Verificar_propiedades')?['propiedad']", "@items('Verificar_propiedades')?['esperado']", "@outputs('Propiedades_observadas')?[items('Verificar_propiedades')?['propiedad']]")))))
    comprobacion_campo = secuencia(
        Campo_por_nombre_exacto=query("@body('Campos_finales')?['value']", "@equals(item()?['InternalName'],items('Verificar_columnas')?['Nombre'])"),
        Campo_unico=si("@equals(length(body('Campo_por_nombre_exacto')),1)", secuencia(
            Propiedades_observadas=compose(observado()), Verificar_propiedades=propiedades), secuencia(
            Diferencia_nombre=diferencia(lv, cv, "InternalName", cv, "Ausente o distinto"))))
    error_verificar_columna = diferencia(lv, cv, "LECTURA_PROPIEDADES", "SchemaXml válido", "@result('TRY_VERIFICAR_COLUMNA')")
    error_verificar_columna["runAfter"] = {"TRY_VERIFICAR_COLUMNA": FALLOS}
    verificar_campos = cada("@items('Verificar_listas')?['Campos']", secuencia(
        TRY_VERIFICAR_COLUMNA=ambito(comprobacion_campo), CATCH_VERIFICAR_COLUMNA=error_verificar_columna))
    comprobacion = secuencia(
        Leer_lista_final=http("GET", ruta("Verificar_listas", f"?$select={SELECT_LISTA}")),
        Verificar_meta=si("@not(and(equals(body('Leer_lista_final')?['Title'],items('Verificar_listas')?['Nombre']),equals(body('Leer_lista_final')?['BaseTemplate'],100),equals(body('Leer_lista_final')?['ContentTypesEnabled'],false),equals(body('Leer_lista_final')?['Hidden'],false),not(empty(body('Leer_lista_final')?['Id'])),or(not(items('Verificar_listas')?['ExigirVersionado']),equals(body('Leer_lista_final')?['EnableVersioning'],true))))", secuencia(
            Diferencia_lista=diferencia(lv, "", "CONFIGURACION_LISTA", "GUID, tipo y versionado aprobados", "@body('Leer_lista_final')"))),
        Campos_finales=http("GET", ruta("Verificar_listas", f"/fields?$select={SELECT_CAMPOS}&$top=5000")),
        Verificar_pagina=si("@or(not(empty(body('Campos_finales')?['odata.nextLink'])),not(empty(body('Campos_finales')?['@odata.nextLink'])),not(empty(body('Campos_finales')?['__next'])))", secuencia(
            Diferencia_pagina=diferencia(lv, "", "PAGINACION_FINAL", "Inventario completo", "Página parcial; no se certifica"))),
        Verificar_Title=si("@items('Verificar_listas')?['VerificarTitle']", secuencia(
            Title_final=http("GET", ruta("Verificar_listas", "/fields/getbyinternalnameortitle('Title')?$select=InternalName,Required")),
            Comparar_Title=si("@not(equals(body('Title_final')?['Required'],false))", secuencia(
                Diferencia_Title=diferencia(lv, "Title", "Required", False, "@body('Title_final')?['Required']"))),
            Columnas_extra=query("@body('Campos_finales')?['value']", "@and(equals(item()?['FromBaseType'],false),equals(item()?['Hidden'],false),equals(item()?['ReadOnlyField'],false),not(equals(item()?['InternalName'],'Title')),not(contains(items('Verificar_listas')?['Nombres'],item()?['InternalName'])))"),
            Reportar_extras=cada("@body('Columnas_extra')", secuencia(
                Diferencia_extra=diferencia(lv, "@items('Reportar_extras')?['InternalName']", "COLUMNA_ADICIONAL", "Esquema V2", "@items('Reportar_extras')?['Title']"))))),
        Verificar_columnas=verificar_campos,
        Registrar_lista=agregar("ListasVerificadas", {"lista": lv, "id": "@toLower(coalesce(body('Leer_lista_final')?['Id'],''))", "columnas_contrato": "@items('Verificar_listas')?['Cantidad']"}))
    err_verificacion = diferencia(lv, "", "REST_VERIFICACION", "Verificación íntegra", "@result('TRY_VERIFICAR_LISTA')")
    err_verificacion["runAfter"] = {"TRY_VERIFICAR_LISTA": FALLOS}
    verificar = cada("@outputs('Contrato_compilado')", secuencia(
        TRY_VERIFICAR_LISTA=ambito(comprobacion), CATCH_VERIFICAR_LISTA=err_verificacion))
    verificar["runAfter"] = {"Provisionar_listas": TODOS}
    acciones = secuencia(
        PARAM_SITIO_SHAREPOINT=compose("@trim(triggerBody()?['text'])"),
        Contrato_compilado=compose(plan),
        Inicializar_diferencias=variable("Diferencias", "array", []),
        Inicializar_listas=variable("ListasVerificadas", "array", []),
        Provisionar_listas=provision,
        Verificar_listas=verificar,
        Estado_final={**compose("@if(and(equals(length(variables('Diferencias')),0),equals(length(variables('ListasVerificadas')),2),equals(actions('Verificar_listas')?['status'],'Succeeded')),'OK','FAIL')"), "runAfter": {"Verificar_listas": TODOS}},
        RESUMEN_FINAL=compose({"PROVISION_P9_REVERSION": "@outputs('Estado_final')", "sitio": "@outputs('PARAM_SITIO_SHAREPOINT')",
                               "listas": "@variables('ListasVerificadas')", "diferencias": "@variables('Diferencias')",
                               "sha256_esquema": hashlib.sha256(C.ESQUEMA.read_bytes()).hexdigest(),
                               "ejecucion": "@workflow()?['run']?['name']"}),
        Finalizar=si("@equals(outputs('Estado_final'),'OK')", secuencia(
            Terminar_OK={"type": "Terminate", "inputs": {"runStatus": "Succeeded"}}), secuencia(
            Terminar_FAIL={"type": "Terminate", "inputs": {"runStatus": "Failed", "runError": {
                "code": "PROVISION_P9_REVERSION_FAIL", "message": "No certificado. Revisar RESUMEN_FINAL; no habilitar flujos."}}})))
    trigger = {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {
        "type": "object", "properties": {"text": {"title": "Sitio SharePoint", "type": "string",
        "description": "URL real del sitio. Depositos_Activos debe existir; los GUID se resuelven en el tenant.",
        "x-ms-content-hint": "TEXT", "x-ms-dynamically-added": True}}, "required": ["text"]}},
        "runtimeConfiguration": {"concurrency": {"runs": 1}}}}
    return definicion(trigger, acciones, version="2.0.0.0")


def generar():
    ruta = C.CARPETA / "flujo_provisionar_definition.json"
    ruta.write_text(json.dumps(construir_definicion(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ruta


if __name__ == "__main__":
    print(generar())
