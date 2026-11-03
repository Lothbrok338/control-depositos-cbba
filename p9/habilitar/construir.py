"""Construye P9_HABILITAR_ESTADO_ASIGNADO: habilita ASIGNADO en la columna ESTADO_ASIGNACION y verifica.

Ejecutar: python -m p9.habilitar.construir
Independiente del provisionador P8 (no lo importa ni lo modifica). Ejecución manual, idempotente:
  * opciones == [DISPONIBLE]              -> agrega ASIGNADO (único escritura: la definición de ESTA columna);
  * opciones == [DISPONIBLE, ASIGNADO]    -> no escribe nada;
  * cualquier otra cosa                   -> no escribe nada y reporta FAIL.
Además verifica los 7 índices de Depositos_Activos (contrato.INDICES): crea SOLO los que falten (Indexed=true sobre la
columna ya existente) y comprueba al final que los 7 existan. Nunca elimina ni desactiva un índice.
No lee ni modifica elementos de la lista. No crea ni borra columnas.
"""
from __future__ import annotations

import json
from pathlib import Path

from p9 import contrato as C
from p9.paquete import RAIZ, escribir_zip
from p9.wdl import (FALLOS, TODOS, agregar, ambito, asignar, compose, contar_acciones, definicion, http_sharepoint,
                    lista_uri, parametros_sitio, secuencia, si, variable)

CARPETA = Path(__file__).resolve().parent
DEFINICION_SALIDA = CARPETA / "flujo_habilitar_definition.json"
ZIP_SALIDA = RAIZ / C.ZIP_HABILITAR
OPCIONES = "|".join(C.ESTADOS)
SELECCION = "Id,InternalName,TypeAsString,Required,Indexed,DefaultValue,Hidden,ReadOnlyField,SchemaXml"


def consulta_campo():
    return lista_uri(["/fields?$filter=InternalName eq '" + C.CAMPO_ESTADO + "'&$select=" + SELECCION])


def normalizar_opciones(campo):
    """Texto `A|B` de las opciones leídas del SchemaXml; vale igual si xpath devuelve un texto o una lista."""
    xp = f"xpath(xml({campo}?['SchemaXml']),'/Field/CHOICES/CHOICE/text()')"
    return f"replace(replace(replace(replace(string({xp}),'[',''),']',''),'\"',''),',','|')"


def fill_in(campo):
    return f"equals(toLower(xpath(xml({campo}?['SchemaXml']),'string(/Field/@FillInChoice)')),'true')"


def diferencias_texto(campo, opciones):
    comprobaciones = [
        ("InternalName", f"equals({campo}?['InternalName'],'{C.CAMPO_ESTADO}')"),
        ("TypeAsString", f"equals({campo}?['TypeAsString'],'Choice')"),
        ("Required", f"equals({campo}?['Required'],true)"),  # Indexed se verifica en el bloque de los 7 índices
        ("Hidden", f"equals({campo}?['Hidden'],false)"), ("ReadOnlyField", f"equals({campo}?['ReadOnlyField'],false)"),
        ("DefaultValue", f"equals(coalesce({campo}?['DefaultValue'],''),'{C.ESTADO_DISPONIBLE}')"),
        ("FillInChoice", f"equals({fill_in(campo)},false)"),
        ("Choices", f"equals({opciones},'{OPCIONES}')"),
    ]
    return "@concat(" + ",".join(f"if({expr},'','{nombre};')" for nombre, expr in comprobaciones) + ")"


SELECCION_INDICES = "Id,InternalName,TypeAsString,Indexed,Hidden"
SIN_PAGINAR = ("@and(empty(body('{a}')?['odata.nextLink']),empty(body('{a}')?['@odata.nextLink']),"
               "empty(body('{a}')?['__next']))")
IT = "items('Aplicar_a_cada_indice')"


def consulta_todos_los_campos():
    return lista_uri([f"/fields?$select={SELECCION_INDICES}&$top=5000"])


def param_indices():
    """Un elemento por índice: nombre y cuerpo REST ya serializado (solo Indexed=true; nunca false)."""
    return [{"nombre": n, "cuerpo": json.dumps({"__metadata": {"type": meta}, "Indexed": True}, separators=(",", ":"))}
            for n, meta in C.INDICES]


def diferencia(propiedades, observado="", esperado=""):
    return {"campo": "INDICES", "propiedades": propiedades, "opciones_observadas": observado, "opciones_esperadas": esperado}


def bloque_crear_indices():
    """Lee los campos UNA vez; por cada índice del contrato: ya indexado -> solo lo anota; sin indexar -> MERGE Indexed=true.
    Un fallo al crear un índice queda registrado como diferencia y el bucle sigue con los demás."""
    uri_merge = ("@concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')',"
                 "'/fields(guid''',first(body('Campo_indice'))?['Id'],''')')")
    crear = secuencia(
        TRY_INDICE=ambito(secuencia(Crear_indice=http_sharepoint(
            "POST", uri_merge,
            {"Accept": "application/json;odata=nometadata", "Content-Type": "application/json;odata=verbose",
             "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}, f"@{IT}?['cuerpo']"))),
        Anotar_indice_creado={**agregar("varIndicesCreados", f"@{IT}?['nombre']"), "runAfter": {"TRY_INDICE": ["Succeeded"]}},
        CATCH_INDICE=ambito(secuencia(Diferencia_indice_no_creado=agregar("varDiferencias", diferencia(
            "INDICE_NO_CREADO", f"@{IT}?['nombre']",
            "@concat('HTTP ',string(coalesce(outputs('Crear_indice')?['statusCode'],0)))"))), {"TRY_INDICE": FALLOS}),
    )
    por_indice = secuencia(
        Campo_indice={"type": "Query", "inputs": {"from": "@body('Leer_campos_antes_indices')?['value']",
                                                  "where": f"@equals(item()?['InternalName'],{IT}?['nombre'])"}},
        Evaluar_indice=si("@equals(length(body('Campo_indice')),1)", secuencia(
            Ya_indexado=si("@equals(first(body('Campo_indice'))?['Indexed'],true)", secuencia(
                Anotar_indice_existente=agregar("varIndicesExistentes", f"@{IT}?['nombre']")), crear)),
            secuencia(Diferencia_campo_indice=agregar("varDiferencias", diferencia(
                "CAMPO_AUSENTE_O_NO_UNICO", f"@{IT}?['nombre']", "una columna con ese InternalName")))),
    )
    return secuencia(
        Etapa_indices=asignar("varEtapa", "INDICES"),
        Leer_campos_antes_indices=http_sharepoint("GET", consulta_todos_los_campos(), {"Accept": "application/json;odata=nometadata"}),
        Sin_paginacion_indices=si(SIN_PAGINAR.format(a="Leer_campos_antes_indices"), secuencia(
            Aplicar_a_cada_indice={"type": "Foreach", "foreach": "@outputs('PARAM_INDICES')",
                                   "runtimeConfiguration": {"concurrency": {"repetitions": 1}}, "actions": por_indice}),
            secuencia(Diferencia_paginacion_indices=agregar("varDiferencias", diferencia(
                "PAGINACION", "respuesta parcial", "inventario completo de campos; no se crea ningun indice")))),
    )


def bloque_verificar_indices():
    return secuencia(
        Etapa_verificar_indices=asignar("varEtapa", "VERIFICAR_INDICES"),
        Leer_campos_despues_indices=http_sharepoint("GET", consulta_todos_los_campos(), {"Accept": "application/json;odata=nometadata"}),
        Verificar_paginacion_indices=si(SIN_PAGINAR.format(a="Leer_campos_despues_indices"), secuencia(
            Indexados_final={"type": "Query", "inputs": {
                "from": "@body('Leer_campos_despues_indices')?['value']",
                "where": "@and(contains(outputs('PARAM_NOMBRES_INDICES'),item()?['InternalName']),equals(item()?['Indexed'],true))"}},
            Nombres_indexados_final={"type": "Select", "inputs": {"from": "@body('Indexados_final')", "select": "@item()?['InternalName']"}},
            Indices_faltantes={"type": "Query", "inputs": {
                "from": "@outputs('PARAM_NOMBRES_INDICES')", "where": "@not(contains(body('Nombres_indexados_final'),item()))"}},
            Guardar_indices_final=asignar("varIndicesFinal", "@length(body('Indexados_final'))"),
            Registrar_indices_faltantes=si("@greater(length(body('Indices_faltantes')),0)", secuencia(
                Diferencia_indices_faltantes=agregar("varDiferencias", diferencia(
                    "INDICE_AUSENTE_O_NO_INDEXADO", "@join(body('Indices_faltantes'),',')", "|".join(n for n, _ in C.INDICES))))),
        ), secuencia(Diferencia_paginacion_final=agregar("varDiferencias", diferencia(
            "PAGINACION", "respuesta parcial", "inventario completo de campos; no se puede certificar")))),
    )


def construir_definicion():
    cuerpo = {"__metadata": {"type": "SP.FieldChoice"},
              "Choices": {"__metadata": {"type": "Collection(Edm.String)"}, "results": list(C.ESTADOS)}}
    antes = "outputs('Campo_antes')"
    despues = "outputs('Campo_despues')"
    habilitar = secuencia(
        Cuerpo_habilitar=compose(cuerpo),
        Etapa_habilitar=asignar("varEtapa", "HABILITAR"),
        Habilitar_ASIGNADO=http_sharepoint(
            "POST", "@concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')',"
                    "'/fields(guid''',outputs('Campo_antes')?['Id'],''')')",
            {"Accept": "application/json;odata=nometadata", "Content-Type": "application/json;odata=verbose",
             "X-HTTP-Method": "MERGE", "IF-MATCH": "*"},
            "@string(outputs('Cuerpo_habilitar'))"),
        Accion_HABILITADO=asignar("varAccion", "HABILITADO"),
    )
    con_campo = secuencia(
        Campo_antes=compose("@first(body('Leer_campo_antes')?['value'])"),
        Opciones_antes=compose("@" + normalizar_opciones(antes)),
        Estado_antes=compose(
            f"@if(equals(outputs('Opciones_antes'),'{OPCIONES}'),'YA_HABILITADO',"
            f"if(and(equals(outputs('Opciones_antes'),'{C.ESTADO_DISPONIBLE}'),equals({antes}?['TypeAsString'],'Choice')),'POR_HABILITAR','INESPERADO'))"),
        Guardar_estado_antes=asignar("varEstadoAntes", "@outputs('Estado_antes')"),
        Habilitar_si_corresponde=si("@equals(outputs('Estado_antes'),'POR_HABILITAR')", habilitar),
        Etapa_leer_despues=asignar("varEtapa", "LEER_DESPUES"),
        Leer_campo_despues=http_sharepoint("GET", consulta_campo(), {"Accept": "application/json;odata=nometadata"}),
        Verificar_campo_unico=si("@equals(length(body('Leer_campo_despues')?['value']),1)", secuencia(
            Campo_despues=compose("@first(body('Leer_campo_despues')?['value'])"),
            Opciones_despues=compose("@" + normalizar_opciones(despues)),
            Guardar_opciones_despues=asignar("varOpcionesDespues", "@outputs('Opciones_despues')"),
            Diferencias_campo=compose(diferencias_texto(despues, "outputs('Opciones_despues')")),
            Registrar_diferencias=si("@not(empty(outputs('Diferencias_campo')))", secuencia(
                Diferencia_campo=agregar("varDiferencias", {
                    "campo": C.CAMPO_ESTADO, "propiedades": "@outputs('Diferencias_campo')",
                    "opciones_observadas": "@outputs('Opciones_despues')", "opciones_esperadas": OPCIONES}))),
        ), secuencia(Diferencia_campo_final=agregar("varDiferencias", {
            "campo": C.CAMPO_ESTADO, "propiedades": "CAMPO_AUSENTE_O_NO_UNICO",
            "opciones_observadas": "", "opciones_esperadas": OPCIONES}))),
    )
    sin_campo = secuencia(Diferencia_campo_antes=agregar("varDiferencias", {
        "campo": C.CAMPO_ESTADO, "propiedades": "CAMPO_AUSENTE_O_NO_UNICO", "opciones_observadas": "",
        "opciones_esperadas": OPCIONES}))
    try_ = secuencia(
        Etapa_leer_antes=asignar("varEtapa", "LEER_ANTES"),
        Leer_campo_antes=http_sharepoint("GET", consulta_campo(), {"Accept": "application/json;odata=nometadata"}),
        Campo_unico=si("@equals(length(body('Leer_campo_antes')?['value']),1)", con_campo, sin_campo),
        **bloque_crear_indices(),
        **bloque_verificar_indices(),
    )
    # secuencia() encadena por orden de declaración; las primeras acciones de cada bloque nuevo se enlazan explícitamente
    try_["Etapa_indices"]["runAfter"] = {"Campo_unico": ["Succeeded"]}
    try_["Etapa_verificar_indices"]["runAfter"] = {"Sin_paginacion_indices": ["Succeeded"]}
    catch = secuencia(Diferencia_REST=agregar("varDiferencias", {
        "campo": C.CAMPO_ESTADO, "propiedades": "@concat('REST_',variables('varEtapa'))",
        "opciones_observadas": "", "opciones_esperadas": OPCIONES}))
    resumen = {
        "P9_HABILITAR_ESTADO_ASIGNADO": "@outputs('Estado_final')", "campo": C.CAMPO_ESTADO,
        "accion": "@variables('varAccion')", "estado_antes": "@variables('varEstadoAntes')",
        "opciones_despues": "@variables('varOpcionesDespues')", "opciones_esperadas": OPCIONES,
        "indices_esperados": [n for n, _ in C.INDICES], "indices_creados": "@variables('varIndicesCreados')",
        "indices_ya_existian": "@variables('varIndicesExistentes')", "indices_verificados_al_final": "@variables('varIndicesFinal')",
        "diferencias": "@variables('varDiferencias')", "ejecucion": "@workflow()?['run']?['name']"}
    acciones = secuencia(
        **parametros_sitio(),
        Inicializar_varEtapa=variable("varEtapa", "string", "INICIO"),
        Inicializar_varAccion=variable("varAccion", "string", "NINGUNA"),
        Inicializar_varEstadoAntes=variable("varEstadoAntes", "string", "NO_EVALUADO"),
        Inicializar_varOpcionesDespues=variable("varOpcionesDespues", "string", "NO_LEIDAS"),
        Inicializar_varDiferencias=variable("varDiferencias", "array", []),
        Inicializar_varIndicesCreados=variable("varIndicesCreados", "array", []),
        Inicializar_varIndicesExistentes=variable("varIndicesExistentes", "array", []),
        Inicializar_varIndicesFinal=variable("varIndicesFinal", "integer", 0),
        PARAM_INDICES=compose(param_indices()),
        PARAM_NOMBRES_INDICES=compose([n for n, _ in C.INDICES]),
        TRY=ambito(try_),
    )
    acciones["CATCH"] = ambito(catch, {"TRY": FALLOS})
    acciones.update({
        "Estado_final": {**compose("@if(equals(length(variables('varDiferencias')),0),'OK','FAIL')"), "runAfter": {"TRY": TODOS, "CATCH": TODOS}},
        "RESUMEN_FINAL": {**compose(resumen), "runAfter": {"Estado_final": ["Succeeded"]}},
        "Finalizar": {**si("@equals(outputs('Estado_final'),'OK')", secuencia(
            Terminar_OK={"type": "Terminate", "inputs": {"runStatus": "Succeeded"}}), secuencia(
            Terminar_FAIL={"type": "Terminate", "inputs": {"runStatus": "Failed", "runError": {
                "code": "P9_HABILITAR_FAIL",
                "message": "P9_HABILITAR_ESTADO_ASIGNADO = FAIL. Revisar RESUMEN_FINAL: diferencias de la columna ESTADO_ASIGNACION."}}})),
            "runAfter": {"RESUMEN_FINAL": ["Succeeded"]}},
    })
    trigger = {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": {}, "required": []}},
                          "runtimeConfiguration": {"concurrency": {"runs": 1}}}}
    return definicion(trigger, acciones)


def generar():
    d = construir_definicion()
    DEFINICION_SALIDA.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    escribir_zip(ZIP_SALIDA, C.NOMBRE_FLUJO_HABILITAR,
                 "Habilita el valor ASIGNADO en ESTADO_ASIGNACION (DISPONIBLE, ASIGNADO) y verifica la columna; manual e idempotente.", d)
    return ZIP_SALIDA, contar_acciones(d["actions"])


if __name__ == "__main__":
    ruta, n = generar()
    print(ruta, f"({n} acciones)")
