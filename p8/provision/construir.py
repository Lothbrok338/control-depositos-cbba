"""Compila exclusivamente esquema_listas_p8.json a un flujo manual SharePoint.

Ejecutar: python -m p8.provision.construir
No modifica el esquema, el generador de carga, sus ZIP ni ningún archivo P6/P7.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = Path(__file__).resolve().parent
FUENTE = RAIZ / "p8/esquema_listas_p8.json"
PLANTILLA = RAIZ / "P8_CARGA_DEPOSITOS_ACTIVOS.zip"
NOMBRE = "P8_PROVISIONAR_LISTAS_V3_HASH_SHA256"
SALIDA = RAIZ / f"{NOMBRE}.zip"
TODOS = ["Succeeded", "Failed", "Skipped", "TimedOut"]
FALLOS = ["Failed", "TimedOut"]
API = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
SELECT_CAMPOS = "InternalName,Title,TypeAsString,Required,Indexed,EnforceUniqueValues,DefaultValue,SchemaXml,Hidden,ReadOnlyField,FromBaseType"
TIPOS = {
    "Texto de una linea": ("Text", "SP.FieldText"),
    "Varias lineas de texto sin formato": ("Note", "SP.FieldMultiLineText"),
    "Fecha y hora, solo fecha": ("DateTime", "SP.FieldDateTime"),
    "Fecha y hora, incluir hora": ("DateTime", "SP.FieldDateTime"),
    "Numero, 2 decimales": ("Number", "SP.FieldNumber"),
    "Numero, 0 decimales": ("Number", "SP.FieldNumber"),
    "Opcion": ("Choice", "SP.FieldChoice"),
}


def compilar(esquema):
    listas = []
    for nombre, lista in esquema.items():
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]+", nombre)
        assert lista["total_columnas_sin_title"] == len(lista["columnas"])
        assert lista["title_obligatorio"] is False
        campos = []
        for c in lista["columnas"]:
            n = c["nombre_tecnico"]
            assert re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", n), n
            tipo, metadata = TIPOS[c["tipo"]]
            assert not c["valores_unicos"] or c["indexada"], n
            # Primero crear sin unicidad; después configurar índice y finalmente
            # unicidad vía REST. Solo se actualizan los campos creados aquí.
            attrs = dict(Name=n, StaticName=n, DisplayName=n, Type=tipo,
                         Required=str(c["obligatoria"]).upper(), Hidden="FALSE")
            # Crear siempre con el nombre técnico también como título inicial.
            # Si existe un título lógico distinto, se asigna después por GUID:
            # así SHA256 nunca participa en la generación del InternalName.
            esperado = {"InternalName": n, "TypeAsString": tipo,
                        "Required": c["obligatoria"], "Indexed": c["indexada"],
                        "EnforceUniqueValues": c["valores_unicos"],
                        "Hidden": False, "ReadOnlyField": False,
                        "DefaultValue": c.get("predeterminado", "")}
            if "nombre_visible" in c:
                assert isinstance(c["nombre_visible"], str) and 0 < len(c["nombre_visible"]) <= 255
                esperado["Title"] = c["nombre_visible"]
            if tipo == "Text":
                attrs["MaxLength"] = "255"
            elif tipo == "Note":
                attrs.update(RichText="FALSE", AppendOnly="FALSE")
                esperado.update(RichText=False, AppendOnly=False)
            elif tipo == "DateTime":
                attrs["Format"] = "DateOnly" if "solo fecha" in c["tipo"] else "DateTime"
                esperado["Format"] = attrs["Format"]
            elif tipo == "Number":
                attrs.update(Decimals="2" if "2 decimales" in c["tipo"] else "0", Percentage="FALSE")
                esperado.update(Decimals=attrs["Decimals"], Percentage=False)
            elif tipo == "Choice":
                attrs.update(FillInChoice=str(c["permitir_relleno"]).upper(), Format="DropDown")
                esperado.update(Choices=c["valores"], FillInChoice=c["permitir_relleno"])
                assert c["valores"] and len(c["valores"]) == len(set(c["valores"]))
                assert "predeterminado" not in c or c["predeterminado"] in c["valores"]
            xml = ET.Element("Field", attrs)
            if tipo == "Choice":
                choices = ET.SubElement(xml, "CHOICES")
                for valor in c["valores"]:
                    ET.SubElement(choices, "CHOICE").text = valor
            if "predeterminado" in c:
                ET.SubElement(xml, "Default").text = c["predeterminado"]
            campos.append({
                "Nombre": n,
                **({"NombreVisible": c["nombre_visible"]} if "nombre_visible" in c else {}),
                "Crear": {"parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"},
                          "SchemaXml": ET.tostring(xml, encoding="unicode"), "Options": 9}},
                "Configurar": {"__metadata": {"type": metadata}, "Required": c["obligatoria"],
                               "Indexed": c["indexada"], "DefaultValue": c.get("predeterminado", ""),
                               **({"Title": c["nombre_visible"]} if "nombre_visible" in c else {})},
                "Unicidad": {"__metadata": {"type": metadata}, "EnforceUniqueValues": True},
                "ExigeUnicidad": c["valores_unicos"],
                "Propiedades": [{"propiedad": k, "esperado": v} for k, v in esperado.items()],
            })
        assert len({c["Nombre"] for c in campos}) == len(campos)
        listas.append({"Nombre": nombre, "Cantidad": lista["total_columnas_sin_title"],
                       "Nombres": [c["Nombre"] for c in campos], "Campos": campos,
                       "Ruta": f"_api/web/lists/getbytitle('{nombre}')",
                       "Buscar": f"_api/web/lists?$select=Title,BaseTemplate,ContentTypesEnabled,Hidden&$filter=Title eq '{nombre}'&$top=2",
                       "Crear": {"__metadata": {"type": "SP.List"}, "Title": nombre,
                                 "BaseTemplate": 100, "ContentTypesEnabled": False},
                       "TitleRequired": lista["title_obligatorio"]})
    return listas


def secuencia(**acciones):
    anterior = None
    for nombre, accion in acciones.items():
        accion.setdefault("runAfter", {anterior: ["Succeeded"]} if anterior else {})
        anterior = nombre
    return acciones


def scope(acciones, despues=None):
    return {"type": "Scope", "actions": acciones, **({"runAfter": despues} if despues is not None else {})}


def si(condicion, acciones, no=None):
    return {"type": "If", "expression": condicion, "actions": acciones, "else": {"actions": no or {}}}


def cada(fuente, acciones):
    return {"type": "Foreach", "foreach": fuente, "actions": acciones,
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}}}


def compose(valor):
    return {"type": "Compose", "inputs": valor}


def query(fuente, filtro):
    return {"type": "Query", "inputs": {"from": fuente, "where": filtro}}


def diferencia(lista, campo, propiedad, esperado, actual):
    return {"type": "AppendToArrayVariable", "inputs": {"name": "Diferencias", "value": {
        "lista": lista, "campo": campo, "propiedad": propiedad,
        "esperado": esperado, "actual": actual}}}


def http(metodo, uri, cuerpo=None, merge=False):
    headers = {"Accept": "application/json;odata=nometadata"}
    if cuerpo is not None:
        headers["Content-Type"] = "application/json;odata=verbose"
    if merge:
        headers.update({"X-HTTP-Method": "MERGE", "IF-MATCH": "*"})
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API, "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": {"dataset": "@outputs('Sitio_SharePoint')", "parameters/method": metodo,
                       "parameters/uri": uri, "parameters/headers": headers,
                       **({"parameters/body": cuerpo} if cuerpo is not None else {})},
        "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "none"}}}


def ruta(bucle, sufijo):
    return "@concat(items('%s')?['Ruta'],'%s')" % (bucle, sufijo.replace("'", "''"))


def campo_nuevo_ruta():
    # Configurar exclusivamente el GUID devuelto por nuestro POST; una carrera
    # de nombres nunca permite modificar una columna preexistente.
    return "@concat(items('Provisionar_listas')?['Ruta'],'/fields(guid''',body('Crear_columna')?['Id'],''')')"


def observado():
    campo = "first(body('Campo_por_nombre_exacto'))"
    xml = f"xml({campo}?['SchemaXml'])"
    # SchemaXml es leído, nunca comparado como texto crudo; SharePoint puede
    # reordenar atributos. Atributos booleanos XML ausentes tienen valor false.
    result = {p: f"@{campo}?['{p}']" for p in ["InternalName", "Title", "TypeAsString", "Required", "Indexed", "EnforceUniqueValues", "Hidden", "ReadOnlyField"]}
    result["DefaultValue"] = f"@coalesce({campo}?['DefaultValue'],'')"
    result["Choices"] = f"@xpath({xml},'/Field/CHOICES/CHOICE/text()')"
    for p in ["RichText", "AppendOnly", "FillInChoice", "Percentage"]:
        result[p] = f"@equals(toLower(xpath({xml},'string(/Field/@{p})')),'true')"
    for p in ["Format", "Decimals"]:
        result[p] = f"@xpath({xml},'string(/Field/@{p})')"
    return result


def construir_definicion(plan, sha):
    lp = "@items('Provisionar_listas')?['Nombre']"
    lv = "@items('Verificar_listas')?['Nombre']"
    cp = "@items('Provisionar_columnas')?['Nombre']"
    cv = "@items('Verificar_columnas')?['Nombre']"
    crear_campo = si("@empty(body('Colision_nombre_o_titulo'))", secuencia(
        Crear_columna=http("POST", ruta("Provisionar_listas", "/fields/createfieldasxml"), "@string(items('Provisionar_columnas')?['Crear'])"),
        Configurar_columna_nueva=http("POST", campo_nuevo_ruta(), "@string(items('Provisionar_columnas')?['Configurar'])", merge=True),
        Activar_unicidad_si_corresponde=si("@items('Provisionar_columnas')?['ExigeUnicidad']", secuencia(
            Exigir_unicidad=http("POST", campo_nuevo_ruta(), "@string(items('Provisionar_columnas')?['Unicidad'])", merge=True))),
    ))
    error_campo = diferencia(lp, cp, "REST_CREACION", "Columna creada y configurada", {
        "crear": "@actions('Crear_columna')?['status']", "http_crear": "@outputs('Crear_columna')?['statusCode']",
        "configurar": "@actions('Configurar_columna_nueva')?['status']", "http_configurar": "@outputs('Configurar_columna_nueva')?['statusCode']",
        "unicidad": "@actions('Exigir_unicidad')?['status']", "http_unicidad": "@outputs('Exigir_unicidad')?['statusCode']"})
    error_campo["runAfter"] = {"Crear_solo_si_ausente": FALLOS}
    columnas = cada("@items('Provisionar_listas')?['Campos']", secuencia(
        Colision_nombre_o_titulo=query("@body('Campos_antes')?['value']", "@or(equals(toLower(item()?['InternalName']),toLower(items('Provisionar_columnas')?['Nombre'])),equals(toLower(item()?['Title']),toLower(items('Provisionar_columnas')?['Nombre'])),equals(toLower(item()?['Title']),toLower(coalesce(items('Provisionar_columnas')?['NombreVisible'],items('Provisionar_columnas')?['Nombre']))))"),
        Crear_solo_si_ausente=crear_campo, Error_creacion_columna=error_campo))
    preparar = secuencia(
        Buscar_lista=http("GET", "@items('Provisionar_listas')?['Buscar']"),
        Crear_lista_si_ausente=si("@equals(length(body('Buscar_lista')?['value']),0)", secuencia(
            Crear_lista=http("POST", "_api/web/lists", "@string(items('Provisionar_listas')?['Crear'])"))),
        Leer_lista_pre=http("GET", ruta("Provisionar_listas", "?$select=Title,BaseTemplate,ContentTypesEnabled,Hidden")),
        Lista_apta=si("@and(equals(body('Leer_lista_pre')?['Title'],items('Provisionar_listas')?['Nombre']),equals(body('Leer_lista_pre')?['BaseTemplate'],100),equals(body('Leer_lista_pre')?['ContentTypesEnabled'],false),equals(body('Leer_lista_pre')?['Hidden'],false))", secuencia(
            Campos_antes=http("GET", ruta("Provisionar_listas", f"/fields?$select={SELECT_CAMPOS}&$top=5000")),
            Sin_paginacion_pre=si("@and(empty(body('Campos_antes')?['odata.nextLink']),empty(body('Campos_antes')?['@odata.nextLink']),empty(body('Campos_antes')?['__next']))", secuencia(
                Leer_Title=http("GET", ruta("Provisionar_listas", "/fields/getbyinternalnameortitle('Title')?$select=InternalName,Required")),
                Liberar_Title_si_necesario=si("@not(equals(body('Leer_Title')?['Required'],items('Provisionar_listas')?['TitleRequired']))", secuencia(
                    Configurar_Title=http("POST", ruta("Provisionar_listas", "/fields/getbyinternalnameortitle('Title')"), "@string(setProperty(json('{\"__metadata\":{\"type\":\"SP.FieldText\"}}'),'Required',items('Provisionar_listas')?['TitleRequired']))", merge=True))),
                Provisionar_columnas=columnas,
            ), secuencia(Paginacion_pre_no_admitida=diferencia(lp, "", "PAGINACION", "Inventario completo antes de escribir", "SharePoint devolvió una página parcial; no se crean columnas"))),
        ), secuencia(Lista_incompatible=diferencia(lp, "", "CONFIGURACION_LISTA", {"BaseTemplate": 100, "ContentTypesEnabled": False, "Hidden": False}, "@body('Leer_lista_pre')"))),
    )
    error_lista = diferencia(lp, "", "REST_PROVISION", "Provisión sin fallos de conector", {
        "buscar": "@outputs('Buscar_lista')?['statusCode']", "crear": "@outputs('Crear_lista')?['statusCode']",
        "leer": "@outputs('Leer_lista_pre')?['statusCode']", "campos": "@outputs('Campos_antes')?['statusCode']",
        "title": "@outputs('Configurar_Title')?['statusCode']", "mensaje": "Consultar las acciones de esta lista y diferencias de columna"})
    error_lista["runAfter"] = {"TRY_PROVISION_LISTA": FALLOS}
    provision = cada("@outputs('Contrato_compilado')", secuencia(
        TRY_PROVISION_LISTA=scope(preparar), CATCH_PROVISION_LISTA=error_lista))

    propiedades = cada("@items('Verificar_columnas')?['Propiedades']", secuencia(
        Comparar_propiedad=si("@not(equals(outputs('Propiedades_observadas')?[items('Verificar_propiedades')?['propiedad']],items('Verificar_propiedades')?['esperado']))", secuencia(
            Diferencia_propiedad=diferencia(lv, cv, "@items('Verificar_propiedades')?['propiedad']", "@items('Verificar_propiedades')?['esperado']", "@outputs('Propiedades_observadas')?[items('Verificar_propiedades')?['propiedad']]")))))
    comprobar_una_columna = secuencia(
        Campo_por_nombre_exacto=query("@body('Campos_finales')?['value']", "@equals(item()?['InternalName'],items('Verificar_columnas')?['Nombre'])"),
        Campo_unico=si("@equals(length(body('Campo_por_nombre_exacto')),1)", secuencia(
            Propiedades_observadas=compose(observado()), Verificar_propiedades=propiedades,
        ), secuencia(Diferencia_InternalName=diferencia(lv, cv, "InternalName", cv, "Ausente o no único con ese nombre interno exacto"))))
    error_verificar_columna = diferencia(lv, cv, "LECTURA_PROPIEDADES", "Propiedades y SchemaXml verificables", "No se pudo evaluar la configuración; revisar Propiedades_observadas")
    error_verificar_columna["runAfter"] = {"TRY_VERIFICAR_COLUMNA": FALLOS}
    comprobar_columna = cada("@items('Verificar_listas')?['Campos']", secuencia(
        TRY_VERIFICAR_COLUMNA=scope(comprobar_una_columna),
        CATCH_VERIFICAR_COLUMNA=error_verificar_columna))
    comprobacion = secuencia(
        Leer_lista_final=http("GET", ruta("Verificar_listas", "?$select=Title,BaseTemplate,ContentTypesEnabled,Hidden")),
        Verificar_metadatos_lista=si("@not(and(equals(body('Leer_lista_final')?['Title'],items('Verificar_listas')?['Nombre']),equals(body('Leer_lista_final')?['BaseTemplate'],100),equals(body('Leer_lista_final')?['ContentTypesEnabled'],false),equals(body('Leer_lista_final')?['Hidden'],false)))", secuencia(
            Diferencia_lista=diferencia(lv, "", "CONFIGURACION_LISTA", {"Title": lv, "BaseTemplate": 100, "ContentTypesEnabled": False, "Hidden": False}, "@body('Leer_lista_final')"))),
        Campos_finales=http("GET", ruta("Verificar_listas", f"/fields?$select={SELECT_CAMPOS}&$top=5000")),
        Verificar_paginacion=si("@or(not(empty(body('Campos_finales')?['odata.nextLink'])),not(empty(body('Campos_finales')?['@odata.nextLink'])),not(empty(body('Campos_finales')?['__next'])))", secuencia(
            Diferencia_paginacion=diferencia(lv, "", "PAGINACION", "Inventario completo", "La respuesta tiene más páginas; no se puede certificar"))),
        Tecnicas_presentes=query("@body('Campos_finales')?['value']", "@contains(items('Verificar_listas')?['Nombres'],item()?['InternalName'])"),
        Comparar_cantidad=si("@not(equals(length(body('Tecnicas_presentes')),items('Verificar_listas')?['Cantidad']))", secuencia(
            Diferencia_cantidad=diferencia(lv, "", "CANTIDAD_COLUMNAS_TECNICAS", "@items('Verificar_listas')?['Cantidad']", "@length(body('Tecnicas_presentes'))"))),
        Columnas_extra=query("@body('Campos_finales')?['value']", "@and(equals(item()?['FromBaseType'],false),equals(item()?['Hidden'],false),equals(item()?['ReadOnlyField'],false),not(equals(item()?['InternalName'],'Title')),not(contains(items('Verificar_listas')?['Nombres'],item()?['InternalName'])))"),
        Reportar_extras=cada("@body('Columnas_extra')", secuencia(
            Diferencia_extra=diferencia(lv, "@items('Reportar_extras')?['InternalName']", "COLUMNA_ADICIONAL", "Ninguna columna de usuario fuera del contrato", "@items('Reportar_extras')?['Title']"))),
        Title_final=http("GET", ruta("Verificar_listas", "/fields/getbyinternalnameortitle('Title')?$select=InternalName,Required")),
        Comparar_Title=si("@not(equals(body('Title_final')?['Required'],items('Verificar_listas')?['TitleRequired']))", secuencia(
            Diferencia_Title=diferencia(lv, "Title", "Required", "@items('Verificar_listas')?['TitleRequired']", "@body('Title_final')?['Required']"))),
        Verificar_columnas=comprobar_columna,
        Registrar_verificacion={"type": "AppendToArrayVariable", "runAfter": {"Verificar_columnas": TODOS}, "inputs": {"name": "ListasVerificadas", "value": {"lista": lv, "esperadas": "@items('Verificar_listas')?['Cantidad']", "presentes": "@length(body('Tecnicas_presentes'))", "verificacion_columnas": "@actions('Verificar_columnas')?['status']"}}},
    )
    error_verificar = diferencia(lv, "", "REST_VERIFICACION", "Lectura y comprobación final completa", {
        "lista": "@outputs('Leer_lista_final')?['statusCode']", "campos": "@outputs('Campos_finales')?['statusCode']",
        "title": "@outputs('Title_final')?['statusCode']", "mensaje": "Error de lectura o evaluación; no se certifica esta lista"})
    error_verificar["runAfter"] = {"TRY_VERIFICAR_LISTA": FALLOS}
    verificar = cada("@outputs('Contrato_compilado')", secuencia(
        TRY_VERIFICAR_LISTA=scope(comprobacion), CATCH_VERIFICAR_LISTA=error_verificar))
    verificar["runAfter"] = {"Provisionar_listas": TODOS}
    estado = "@if(and(equals(length(variables('Diferencias')),0),equals(length(variables('ListasVerificadas')),length(outputs('Contrato_compilado'))),equals(actions('Verificar_listas')?['status'],'Succeeded')),'OK','FAIL')"
    resumen = compose({"PROVISION_P8": "@outputs('Estado_final')", "resultado": "@concat('PROVISION_P8 = ',outputs('Estado_final'))",
                       "fuente": "p8/esquema_listas_p8.json", "sha256_contrato": sha,
                       "listas": "@variables('ListasVerificadas')", "diferencias": "@variables('Diferencias')",
                       "ejecucion": "@workflow()?['run']?['name']"})
    acciones = secuencia(
        Sitio_SharePoint=compose("@trim(triggerBody()?['text'])"),
        Contrato_compilado=compose(plan),
        Inicializar_diferencias={"type": "InitializeVariable", "inputs": {"variables": [{"name": "Diferencias", "type": "array", "value": []}]}},
        Inicializar_listas_verificadas={"type": "InitializeVariable", "inputs": {"variables": [{"name": "ListasVerificadas", "type": "array", "value": []}]}},
        Provisionar_listas=provision, Verificar_listas=verificar,
        Estado_final={**compose(estado), "runAfter": {"Verificar_listas": TODOS}},
        RESUMEN_FINAL=resumen,
        Finalizar=si("@equals(outputs('Estado_final'),'OK')", secuencia(
            Terminar_OK={"type": "Terminate", "inputs": {"runStatus": "Succeeded"}}), secuencia(
            Terminar_FAIL={"type": "Terminate", "inputs": {"runStatus": "Failed", "runError": {"code": "PROVISION_P8_FAIL", "message": "PROVISION_P8 = FAIL. Revisar RESUMEN_FINAL: diferencias por lista, columna y propiedad."}}})),
    )
    return {"$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#", "contentVersion": "1.0.0.0",
            "parameters": {"$authentication": {"defaultValue": {}, "type": "SecureObject"}, "$connections": {"defaultValue": {}, "type": "Object"}},
            "triggers": {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": {"text": {"title": "Sitio SharePoint", "description": "URL completa del sitio donde se crearán las dos listas P8", "type": "string", "x-ms-content-hint": "TEXT", "x-ms-dynamically-added": True}}, "required": ["text"]}}, "runtimeConfiguration": {"concurrency": {"runs": 1}}}},
            "actions": acciones, "outputs": {}}


def empaquetar(definicion):
    # Se deriva el sobre del ZIP existente, cuya estructura proviene de una
    # exportación real. No se genera un contenedor de importación inventado.
    with zipfile.ZipFile(PLANTILLA) as z:
        archivos = {n: json.loads(z.read(n)) for n in z.namelist()}
    manifest = archivos["manifest.json"]
    definition_path = next(n for n in archivos if n.endswith("/definition.json"))
    ids = list(manifest["resources"]) + [archivos[definition_path]["name"], manifest["details"]["packageTelemetryId"]]
    replacements = {old: str(uuid.uuid5(uuid.NAMESPACE_URL, "control-depositos-cbba:provision-p8:v3-hash-sha256:" + old)) for old in ids}
    def sustituir(valor):
        if isinstance(valor, dict):
            return {sustituir(k): sustituir(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [sustituir(v) for v in valor]
        if isinstance(valor, str):
            for antes, despues in replacements.items():
                valor = valor.replace(antes, despues)
        return valor
    nuevos = {sustituir(n): sustituir(v) for n, v in archivos.items()}
    manifest = nuevos["manifest.json"]
    manifest["details"].update(displayName=NOMBRE, description="Provisión y verificación idempotente del contrato de listas P8; ejecución manual independiente.")
    for resource in manifest["resources"].values():
        if resource["type"] == "Microsoft.Flow/flows":
            resource["details"]["displayName"] = NOMBRE
            resource["suggestedCreationType"] = "New"
    envelope = nuevos[sustituir(definition_path)]
    envelope["properties"]["displayName"] = NOMBRE
    envelope["properties"]["definition"] = definicion
    return nuevos


def generar():
    fuente = FUENTE.read_bytes()
    esquema = json.loads(fuente)
    plan = compilar(esquema)
    sha = hashlib.sha256(fuente).hexdigest()
    definicion = construir_definicion(plan, sha)
    for nombre, contenido in [("plan_provision.json", {"fuente": str(FUENTE.relative_to(RAIZ)), "sha256": sha, "listas": plan}),
                              ("flujo_provision_definition.json", definicion)]:
        (CARPETA / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(SALIDA, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in empaquetar(definicion).items():
            info = zipfile.ZipInfo(nombre, date_time=(2026, 9, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, json.dumps(contenido, ensure_ascii=False, separators=(",", ":")))
    return SALIDA


if __name__ == "__main__":
    print(generar())
