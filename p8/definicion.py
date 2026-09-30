"""Definición WDL P8. Solo conectores estándar SharePoint y acciones integradas."""

TODOS = ["Succeeded", "Failed", "TimedOut", "Skipped"]
MAX_ERRORES = 8
MAX_MENSAJE = 8000
API = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"


def secuencia(**acciones):
    anterior = None
    for nombre, accion in acciones.items():
        accion.setdefault("runAfter", {anterior: ["Succeeded"]} if anterior else {})
        anterior = nombre
    return acciones


def asignar(nombre, valor):
    return {"type": "SetVariable", "inputs": {"name": nombre, "value": valor}}


def incrementar(nombre):
    return {"type": "IncrementVariable", "inputs": {"name": nombre, "value": 1}}


def redactar(valor):
    return {"type": "Compose", "inputs": valor}


def ambito(acciones, despues=None):
    a = {"type": "Scope", "actions": acciones}
    if despues is not None:
        a["runAfter"] = despues
    return a


def condicion(expresion, si, no=None):
    return {"type": "If", "expression": expresion, "actions": si, "else": {"actions": no or {}}}


def sp(operacion, parametros):
    return {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {"apiId": API, "connectionName": "shared_sharepointonline", "operationId": operacion},
            "parameters": parametros,
            "authentication": "@parameters('$authentication')",
            # No reintentar POST silenciosamente: la reconsulta decide si ya se creó.
            "retryPolicy": {"type": "none"},
        },
    }


def lista(nombre):
    return {"dataset": "@outputs('PARAM_SITIO_SHAREPOINT')", "table": f"@outputs('PARAM_LISTA_{nombre}')"}


def consulta(clave):
    return sp("GetItems", {
        **lista("DEPOSITOS_ACTIVOS"),
        "$filter": f"@concat('CLAVE_TRANSACCION eq ''',replace({clave},'''',''''''),'''')",
        "$top": 1,
    })


def diagnostico_fila(sufijo, motivo, codigo, clave=None, fila=None):
    """No copia cuerpos, cabeceras, mensajes arbitrarios ni result()."""
    entrada = {
        "fila": fila or "@variables('varFilaActual')",
        "CLAVE_TRANSACCION": clave or "@take(outputs('Movimiento_actual')?['CLAVE_TRANSACCION'],255)",
        "motivo": motivo,
        "codigo": codigo,
    }
    # Acotar cada representación serializada, incluso con comillas/control chars.
    # 8 entradas de <=800 caracteres + cabecera quedan por debajo de 8000.
    return condicion(
        f"@less(length(variables('varDetalle')),{MAX_ERRORES})",
        secuencia(**{
            f"Detalle_{sufijo}": redactar(entrada),
            f"Detalle_acotado_{sufijo}": redactar(
                f"@if(lessOrEquals(length(string(outputs('Detalle_{sufijo}'))),800),"
                f"outputs('Detalle_{sufijo}'),setProperty(outputs('Detalle_{sufijo}'),"
                f"'CLAVE_TRANSACCION',take(outputs('Detalle_{sufijo}')?['CLAVE_TRANSACCION'],64)))"
            ),
            f"Anotar_{sufijo}": {"type": "AppendToArrayVariable", "inputs": {
                "name": "varDetalle", "value": f"@outputs('Detalle_acotado_{sufijo}')"}},
        }),
    )


def crear_y_clasificar(columnas):
    parametros = lista("DEPOSITOS_ACTIVOS")
    for _, tecnico, tipo, _ in columnas:
        valor = f"outputs('Movimiento_actual')?['{tecnico}']"
        if tipo == "numero":
            valor = f"if(empty({valor}),null,float({valor}))" if tecnico in {"DEBITO", "CREDITO"} else f"float({valor})"
        parametros[f"item/{tecnico}"] = "@" + valor
    parametros["item/ESTADO_ASIGNACION/Value"] = "DISPONIBLE"
    catch = secuencia(
        Reconsultar_CLAVE_TRANSACCION=consulta("outputs('Movimiento_actual')?['CLAVE_TRANSACCION']"),
        Clasificar_reconsulta=condicion(
            "@greater(length(body('Reconsultar_CLAVE_TRANSACCION')?['value']),0)",
            {"Resultado_YA_EXISTE": asignar("varResultadoFila", "YA_EXISTE")},
            secuencia(
                Resultado_ERROR=asignar("varResultadoFila", "ERROR"),
                Registrar_clave_ausente=diagnostico_fila(
                    "clave_ausente", "Crear elemento fallo o expiro; reconsulta sin coincidencias.",
                    "@concat('CREAR_',actions('Crear_movimiento')?['status'],'_HTTP_',"
                    "string(coalesce(outputs('Crear_movimiento')?['statusCode'],0)))"),
            ),
        ),
    )
    fallo_reconsulta = ambito(secuencia(
        Resultado_ERROR_reconsulta=asignar("varResultadoFila", "ERROR"),
        Anotar_fallo_reconsulta=diagnostico_fila(
            "reconsulta", "Fallo o timeout de reconsulta; existencia no confirmada. Reprocesar es seguro.",
            "@concat('CREAR_',actions('Crear_movimiento')?['status'],'_HTTP_',"
            "string(coalesce(outputs('Crear_movimiento')?['statusCode'],0)),"
            "'; RECONSULTA_',actions('Reconsultar_CLAVE_TRANSACCION')?['status'],'_HTTP_',"
            "string(coalesce(outputs('Reconsultar_CLAVE_TRANSACCION')?['statusCode'],0)))"),
    ), {"Reconsultar_CLAVE_TRANSACCION": ["Failed", "TimedOut"]})
    catch["CATCH_RECONSULTA"] = fallo_reconsulta
    # El cierre de fila se ejecuta aun si el Scope contiene una acción fallida manejada.
    resultado = {
        "TRY_CREAR_MOVIMIENTO": ambito({"Crear_movimiento": sp("PostItem", parametros)}, {}),
        "Crear_OK": asignar("varResultadoFila", "NUEVO"),
        "CATCH_CREAR_MOVIMIENTO": ambito(catch, {"TRY_CREAR_MOVIMIENTO": ["Failed", "TimedOut"]}),
    }
    resultado["Crear_OK"]["runAfter"] = {"TRY_CREAR_MOVIMIENTO": ["Succeeded"]}
    return resultado


def procesar(columnas):
    fila = secuencia(
        Movimiento_actual=redactar("@body('Analizar_JSON')?['movimientos'][items('Aplicar_a_cada_movimiento')]"),
        Guardar_numero_fila=asignar("varFilaActual", "@body('Filas_movimientos')[items('Aplicar_a_cada_movimiento')]"),
        Reiniciar_resultado_fila=asignar("varResultadoFila", "PENDIENTE"),
        Clave_preexistente=condicion(
            "@contains(variables('varClavesExistentes'),outputs('Movimiento_actual')?['CLAVE_TRANSACCION'])",
            {"Preexistente": asignar("varResultadoFila", "YA_EXISTE")},
            crear_y_clasificar(columnas),
        ),
        Cerrar_fila=condicion(
            "@equals(variables('varResultadoFila'),'NUEVO')",
            {"Contar_NUEVO": incrementar("varCantidadNueva")},
            {"Resultado_alternativo": condicion(
                "@equals(variables('varResultadoFila'),'YA_EXISTE')",
                {"Contar_YA_EXISTE": incrementar("varCantidadYaExiste")},
                {"Contar_ERROR": incrementar("varCantidadError")},
            )},
        ),
        Contar_fila_clasificada=incrementar("varClasificados"),
    )
    fila["Cerrar_fila"]["runAfter"] = {"Clave_preexistente": TODOS}
    acciones = secuencia(
        Etapa_preconsulta=asignar("varEtapa", "PRECONSULTA"),
        Preconsultar_claves={
            "type": "Foreach", "foreach": "@body('Analizar_JSON')?['movimientos']",
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "actions": secuencia(
                Obtener_clave_preexistente=consulta("items('Preconsultar_claves')?['CLAVE_TRANSACCION']"),
                Existe_en_preconsulta=condicion(
                    "@greater(length(body('Obtener_clave_preexistente')?['value']),0)",
                    {"Guardar_clave_existente": {"type": "AppendToArrayVariable", "inputs": {
                        "name": "varClavesExistentes", "value": "@items('Preconsultar_claves')?['CLAVE_TRANSACCION']"}}},
                ),
            ),
        },
        Claves_en_preconsulta=redactar("@length(variables('varClavesExistentes'))"),
        Etapa_procesamiento=asignar("varEtapa", "MOVIMIENTOS"),
        Aplicar_a_cada_movimiento={
            "type": "Foreach", "foreach": "@range(0,length(body('Analizar_JSON')?['movimientos']))",
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}}, "actions": fila,
        },
        Comprobar_fin_procesamiento=condicion(
            "@equals(variables('varClasificados'),length(body('Analizar_JSON')?['movimientos']))",
            secuencia(
                Procesamiento_completo=asignar("varProcesamientoCompleto", True),
                Sin_fallo_estructural=asignar("varFalloEstructural", False),
            ),
        ),
    )
    acciones["Comprobar_fin_procesamiento"]["runAfter"] = {"Aplicar_a_cada_movimiento": TODOS}
    return acciones


def construir_definicion(esquema_p7, columnas, esquema_listas):
    # El nombre lógico SHA256 pertenece a la bitácora P8. El JSON P7 y sus
    # 26 columnas permanecen intactos; la escritura usa el InternalName del
    # mismo contrato que consume el provisionador.
    campos_hash = [c["nombre_tecnico"] for c in esquema_listas["Depositos_Cargas"]["columnas"]
                   if c.get("nombre_logico", c["nombre_tecnico"]) == "SHA256"]
    assert len(campos_hash) == 1, "Debe existir un único campo lógico SHA256 en Depositos_Cargas"
    campo_hash = campos_hash[0]
    nombres = [c[1] for c in columnas]
    vars_iniciales = {
        "varCantidadRecibida": ("integer", 0), "varCantidadValida": ("integer", 0),
        "varCantidadNueva": ("integer", 0), "varCantidadYaExiste": ("integer", 0),
        "varCantidadError": ("integer", 0), "varClasificados": ("integer", 0),
        "varFilaActual": ("integer", 0), "varDetalle": ("array", []),
        "varClavesExistentes": ("array", []), "varResultadoFila": ("string", "PENDIENTE"),
        "varFalloEstructural": ("boolean", True), "varProcesamientoCompleto": ("boolean", False),
        "varLoteId": ("string", "DESCONOCIDO"), "varArchivoFuente": ("string", "DESCONOCIDO"),
        "varSha256": ("string", "DESCONOCIDO"), "varEtapa": ("string", "LECTURA"),
        "varArchivoJson": ("string", "@take(coalesce(triggerBody()?['{FilenameWithExtension}'],'DESCONOCIDO'),255)"),
    }
    acciones = secuencia(
        CONFIGURACION=ambito(secuencia(
            PARAM_SITIO_SHAREPOINT=redactar("<SITIO_SHAREPOINT>"),
            PARAM_LISTA_DEPOSITOS_ACTIVOS=redactar("Depositos_Activos"),
            PARAM_LISTA_DEPOSITOS_CARGAS=redactar("Depositos_Cargas"),
        )),
        **{f"Inicializar_{nombre}": {"type": "InitializeVariable", "inputs": {"variables": [
            {"name": nombre, "type": tipo, "value": valor}
        ]}} for nombre, (tipo, valor) in vars_iniciales.items()},
    )
    preparacion = secuencia(
        Guardar_lote=asignar("varLoteId", "@body('Analizar_JSON')?['lote_id']"),
        Guardar_fuente=asignar("varArchivoFuente", "@body('Analizar_JSON')?['archivo_fuente']"),
        Guardar_hash=asignar("varSha256", "@body('Analizar_JSON')?['sha256_archivo_fuente']"),
        Guardar_validos=asignar("varCantidadValida", "@sub(variables('varCantidadRecibida'),length(body('Omitidos_ERROR')))"),
        Contar_omitidos_error=asignar("varCantidadError", "@length(body('Omitidos_ERROR'))"),
        Contar_omitidos_existentes=asignar("varCantidadYaExiste", "@length(body('Omitidos_YA_EXISTE'))"),
        Detallar_omitidos={"type": "Foreach", "foreach": f"@take(body('Omitidos_ERROR'),{MAX_ERRORES})",
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}}, "actions": {
                "Registrar_detalle_omitido": diagnostico_fila("omitido", "Fila rechazada por adaptador P7; ver omitidos del JSON.",
                    "P7_OMITIDO_ERROR", "@take(items('Detallar_omitidos')?['valores']?['CLAVE_TRANSACCION'],255)",
                    "@items('Detallar_omitidos')?['fila']")}},
        **procesar(columnas),
    )
    # secuencia() respeta runAfter preestablecidos; unir la primera acción del subgrafo.
    preparacion["Etapa_preconsulta"]["runAfter"] = {"Detallar_omitidos": ["Succeeded"]}
    filtros = {
        "Omitidos_ERROR": "@equals(item()?['estado'],'ERROR')",
        "Omitidos_YA_EXISTE": "@equals(item()?['estado'],'YA_EXISTE')",
        "Omitidos_invalidos": "@not(or(equals(item()?['estado'],'ERROR'),equals(item()?['estado'],'YA_EXISTE')))",
    }
    contrato = (
        "@and(equals(body('Analizar_JSON')?['esquema'],'P7_DEPOSITOS_ACTIVOS_V1'),"
        f"equals(join(body('Analizar_JSON')?['columnas'],'|'),'{ '|'.join(nombres) }'),"
        "equals(length(body('Analizar_JSON')?['columnas']),26),empty(body('Omitidos_invalidos')),"
        "equals(length(body('Filas_movimientos')),length(body('Analizar_JSON')?['movimientos'])),"
        "greater(length(body('Analizar_JSON')?['lote_id']),0),lessOrEquals(length(body('Analizar_JSON')?['lote_id']),255),"
        "greater(length(body('Analizar_JSON')?['archivo_fuente']),0),lessOrEquals(length(body('Analizar_JSON')?['archivo_fuente']),255),"
        "equals(length(body('Analizar_JSON')?['sha256_archivo_fuente']),64))"
    )
    acciones["TRY"] = ambito(secuencia(
        Obtener_contenido_del_archivo=sp("GetFileContent", {
            "dataset": "@outputs('PARAM_SITIO_SHAREPOINT')", "id": "@triggerBody()?['{Identifier}']",
            "inferContentType": False,
        }),
        Etapa_parse=asignar("varEtapa", "PARSE_JSON"),
        Analizar_JSON={"type": "ParseJson", "inputs": {
            "content": "@json(base64ToString(body('Obtener_contenido_del_archivo')?['$content']))",
            "schema": esquema_p7,
        }},
        Etapa_contrato=asignar("varEtapa", "CONTRATO"),
        Guardar_recibidos=asignar("varCantidadRecibida", "@add(length(body('Analizar_JSON')?['movimientos']),length(body('Analizar_JSON')?['omitidos']))"),
        **{nombre: {"type": "Query", "inputs": {"from": "@body('Analizar_JSON')?['omitidos']", "where": expr}} for nombre, expr in filtros.items()},
        Filas_omitidas={"type": "Select", "inputs": {"from": "@body('Analizar_JSON')?['omitidos']", "select": "@item()?['fila']"}},
        Filas_movimientos={"type": "Query", "inputs": {"from": "@range(1,variables('varCantidadRecibida'))", "where": "@not(contains(body('Filas_omitidas'),item()))"}},
        Contrato_P7_valido=condicion(contrato, preparacion),
    ), {"Inicializar_varArchivoJson": ["Succeeded"]})
    acciones["CATCH"] = ambito({
        "Marcar_fallo_estructural": condicion("@not(variables('varProcesamientoCompleto'))", {
            "Fallo_estructural": asignar("varFalloEstructural", True)
        }),
    }, {"TRY": ["Failed", "TimedOut"]})
    cierre = secuencia(
        Reconciliar_fallo_estructural=condicion("@variables('varFalloEstructural')", {
            "Errores_sin_procesar": asignar("varCantidadError", "@max(0,sub(sub(variables('varCantidadRecibida'),variables('varCantidadNueva')),variables('varCantidadYaExiste')))")
        }),
        Invariante=redactar("@equals(variables('varCantidadRecibida'),add(add(variables('varCantidadNueva'),variables('varCantidadYaExiste')),variables('varCantidadError')))"),
        Estado_final=redactar("@if(not(outputs('Invariante')),'COMPLETADO_CON_ERRORES',if(variables('varFalloEstructural'),'FALLIDO',if(greater(variables('varCantidadError'),0),'COMPLETADO_CON_ERRORES','COMPLETADO')))"),
        Diagnostico=redactar({
            "etapa": "@variables('varEtapa')", "archivo": "@variables('varArchivoJson')",
            "mensaje": "@if(variables('varFalloEstructural'),'Fallo estructural: revisar la etapa indicada en el historial. Las filas sin resultado confirmado se cuentan como ERROR.',if(outputs('Invariante'),'Errores de filas manejados; ver detalle.','Conteos inconsistentes.'))",
            "ejecucion": "@take(workflow()?['run']?['name'],128)",
            "errores": "@variables('varDetalle')",
            "cantidad_error": "@variables('varCantidadError')",
            "detalle_omitido": "@max(0,sub(variables('varCantidadError'),length(variables('varDetalle'))))",
        }),
        Mensaje_acotado=redactar(
            f"@if(equals(outputs('Estado_final'),'COMPLETADO'),'',if(lessOrEquals(length(string(outputs('Diagnostico'))),{MAX_MENSAJE}),"
            "string(outputs('Diagnostico')),string(setProperty(setProperty(outputs('Diagnostico'),'errores',json('[]')),"
            "'mensaje','Detalle excedio el limite de 8000 caracteres; revisar historial mediante ejecucion.'))))"
        ),
        Registrar_bitacora_del_lote=sp("PostItem", {
            **lista("DEPOSITOS_CARGAS"),
            "item/LOTE_ID": "@variables('varLoteId')", "item/FECHA_HORA_PROCESO": "@utcNow()",
            "item/ARCHIVO_FUENTE": "@variables('varArchivoFuente')", f"item/{campo_hash}": "@variables('varSha256')",
            **{f"item/{columna}": f"@variables('{variable}')" for columna, variable in [
                ("CANTIDAD_RECIBIDA", "varCantidadRecibida"), ("CANTIDAD_VALIDA", "varCantidadValida"),
                ("CANTIDAD_NUEVA", "varCantidadNueva"), ("CANTIDAD_YA_EXISTE", "varCantidadYaExiste"),
                ("CANTIDAD_ERROR", "varCantidadError")
            ]},
            "item/ESTADO_LOTE/Value": "@outputs('Estado_final')", "item/MENSAJE_ERROR": "@outputs('Mensaje_acotado')",
            "item/ARCHIVO_JSON": "@variables('varArchivoJson')", "item/ID_EJECUCION_FLUJO": "@workflow()?['run']?['name']",
        }),
    )
    acciones["FINALLY"] = ambito(cierre, {"CATCH": TODOS})
    # Terminate solo después de un POST confirmado. Un fallo de bitácora deja la ejecución fallida.
    acciones["Finalizar_ejecucion"] = condicion(
        "@equals(outputs('Estado_final'),'FALLIDO')",
        {"Terminar_FALLIDO": {"type": "Terminate", "inputs": {"runStatus": "Failed", "runError": {"code": "P8_ESTRUCTURAL", "message": "Bitacora FALLIDO registrada; revisar Depositos_Cargas."}}}},
        {"Terminar_procesado": {"type": "Terminate", "inputs": {"runStatus": "Succeeded"}}},
    )
    acciones["Finalizar_ejecucion"]["runAfter"] = {"FINALLY": ["Succeeded"]}
    return {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.1.0.0",
        "parameters": {"$authentication": {"defaultValue": {}, "type": "SecureObject"}, "$connections": {"defaultValue": {}, "type": "Object"}},
        "triggers": {"Cuando_se_crea_un_archivo": {
            "type": "OpenApiConnection", "recurrence": {"interval": 1, "frequency": "Minute"},
            "splitOn": "@triggerOutputs()?['body/value']",
            "inputs": sp("GetOnNewFileItems", {"dataset": "<SITIO_SHAREPOINT>", "table": "<BIBLIOTECA_DOCUMENTOS>", "folderPath": "<CARPETA_ENTRADA_M365>"})["inputs"],
            "conditions": [{"expression": "@and(equals(triggerBody()?['{IsFolder}'],false),startsWith(coalesce(triggerBody()?['{FilenameWithExtension}'],''),'DEPOSITOS_ACTIVOS__'),endsWith(coalesce(triggerBody()?['{FilenameWithExtension}'],''),'.json'))"}],
            "runtimeConfiguration": {"concurrency": {"runs": 1}},
        }},
        "actions": acciones, "outputs": {},
    }
