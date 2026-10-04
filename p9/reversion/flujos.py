"""Flujos WDL ejecutables del protocolo V2.

La verificación de una ejecución anterior terminada es manual, por un operador
autenticado autorizado. Se conserva su evidencia; no se finge consultar una API
de estado que el conector estándar no expone. Toda escritura usa CAS real.
"""
from __future__ import annotations

from p9.reversion import contrato as C
from p9.reversion.wdl import (TODOS, FALLOS, api, compose, concat, cond, definition,
                             expr, http, init, item_uri, quote, scope, seq, setvar, uri)

SALIDAS = ("resultado", "codigo", "mensaje", "solicitud_id", "solicitud_uid", "snapshot_json", "etag",
           "estado_solicitud", "fase_proceso", "resultado_tecnico", "fecha_limite")
LISTA_D = "outputs('GUID_DEPOSITOS')"
LISTA_R = "outputs('GUID_REVERSIONES')"
RUN = "workflow()?['run']?['name']"
SNAPSHOT_VISIBLE = ("BANCO", "CUENTA_BANCARIA", "FECHA_MOVIMIENTO", "IMPORTE", "MONEDA", "CODIGO_ASIGNACION") + C.CAMPOS_LIMPIAR
ASIGNACION = ("CODIGO_ASIGNACION",) + C.CAMPOS_LIMPIAR
TERMINALES = "createArray('FINALIZADA','EXPIRADA')"


def R(action, field=None):
    base = f"body('{action}')?['d']"
    return base if field is None else f"{base}?['{field}']"


def Q(field):
    return f"outputs('Entrada')?['{field}']"


def equal(a, b):
    """Comparación exacta de textos, también ante motores equals case-insensitive."""
    return f"equals(base64(string({a})),base64(string({b})))"


def etag(action):
    return f"coalesce({R(action)}?['__metadata']?['etag'],outputs('{action}')?['headers']?['ETag'],'')"


def response(result, code, message, row=None, **extra):
    body = dict.fromkeys(SALIDAS, "")
    body.update(resultado=result, codigo=code, mensaje=message)
    if row:
        for out, column in (("solicitud_id", "ID"), ("solicitud_uid", "SOLICITUD_UID"),
                            ("estado_solicitud", "ESTADO_SOLICITUD"), ("fase_proceso", "FASE_PROCESO"),
                            ("resultado_tecnico", "RESULTADO_TECNICO"), ("fecha_limite", "FECHA_LIMITE")):
            body[out] = f"@string(coalesce({row}?['{column}'],''))"
        body["solicitud_id"] = f"@string(coalesce({row}?['ID'],{row}?['Id'],''))"
        body["snapshot_json"] = f"@coalesce({row}?['SNAPSHOT_JSON'],'')"
        body["etag"] = f"@coalesce({row}?['ETAG_SOLICITUD'],'')"
    body.update(extra)
    return setvar("varRespuesta", body)


def stop(code="DETENIDO", message="No se cumplen las precondiciones para continuar.", failed=False):
    out = {"type": "Terminate", "inputs": {"runStatus": "Failed" if failed else "Succeeded"}}
    if failed:
        out["inputs"]["runError"] = {"code": code, "message": message}
    return out


def read(url):
    action = http("GET", url)
    # Dos reintentos de lectura, tres intentos totales. El runtime aplica Retry-After.
    action["inputs"]["retryPolicy"] = {"type": "exponential", "count": 2, "interval": "PT5S", "minimumInterval": "PT5S", "maximumInterval": "PT30S"}
    return action


def matching(lista, field, value):
    return concat(quote("_api/web/lists(guid'"), lista,
                  quote("')/items?$filter=" + field + " eq '"),
                  f"encodeUriComponent(replace(string({value}),'''',''''''))", quote("'&$top=2"))


def pending(row):
    return f"and(equals({row}?['ESTADO_SOLICITUD'],'PENDIENTE'),contains(createArray('RECIBIDA','ESPERANDO_APROBACION','RECUPERACION_REQUERIDA'),{row}?['FASE_PROCESO']),empty({row}?['FECHA_EJECUCION_REVERSION']),empty({row}?['ETAG_EJECUCION']))"


def owned(row, phase=None):
    terms = [f"equals({row}?['RUN_ID'],{RUN})", f"not(contains({TERMINALES},{row}?['FASE_PROCESO']))"]
    if phase:
        terms.append(f"equals({row}?['FASE_PROCESO'],'{phase}')")
    return "and(" + ",".join(terms) + ")"


class Build:
    def __init__(self):
        self.variables = {}

    def variable(self, name, typ, value):
        self.variables[name] = init(name, typ, value)
        return name

    def cas(self, prefix, ident, predicate, changes, event, evidence=None, reset=False):
        """CAS auditado hasta tres lecturas/escrituras, sin retry automático.

        $R en predicado/valores representa la lectura actual de la solicitud.
        El ID de evento es estable entre reintentos y prueba un commit incierto.
        Un fallo no-412 nunca vuelve a enviar la escritura automáticamente.
        """
        applied = self.variable("ok_" + prefix, "boolean", False)
        finished = self.variable("fin_" + prefix, "boolean", False)
        count = self.variable("n_" + prefix, "integer", 0)
        get = prefix + "_GET"
        row = R(get)
        log = f"json(if(empty({row}?['BITACORA_TECNICA_JSON']),'[]',{row}?['BITACORA_TECNICA_JSON']))"
        event_name = prefix + "_EVENTO"
        newlog = f"string(union({log},createArray(outputs('{event_name}'))))"
        change = {key: (value.replace("$R", row) if isinstance(value, str) else value) for key, value in changes.items()}
        change["BITACORA_TECNICA_JSON"] = "@" + newlog
        put = prefix + "_MERGE"
        after = prefix + "_VERIFICAR"
        verify = read(item_uri(LISTA_R, ident))
        verify["runAfter"] = {put: TODOS}
        committed = f"contains(coalesce({R(after,'BITACORA_TECNICA_JSON')},''),outputs('{event_name}')?['id'])"
        attempt = seq(**{
            put: http("POST", item_uri(LISTA_R, ident), change, "@" + etag(get)),
            after: verify,
            prefix + "_APLICADO": setvar(applied, "@" + committed),
            prefix + "_FIN": setvar(finished, f"@or(variables('{applied}'),not(equals(outputs('{put}')?['statusCode'],412)))")})
        existing = f"contains(coalesce({row}?['BITACORA_TECNICA_JSON'],''),outputs('{event_name}')?['id'])"
        loop = seq(**{
            prefix + "_CONTAR": {"type": "IncrementVariable", "inputs": {"name": count, "value": 1}},
            get: read(item_uri(LISTA_R, ident)),
            prefix + "_YA_APLICADO": cond("@" + existing,
                seq(**{prefix + "_YA_OK": setvar(applied, True), prefix + "_YA_FIN": setvar(finished, True)})),
            prefix + "_PRECONDICIONES": cond(
                f"@and(not(variables('{finished}')),not(empty(" + etag(get) + "))," + predicate.replace("$R", row) + f",lessOrEquals(length({newlog}),60000))",
                attempt, seq(**{prefix + "_NO_CONTINUAR": setvar(finished, True)}))})
        reset_nodes = seq(**{prefix + "_RESET_OK": setvar(applied, False), prefix + "_RESET_FIN": setvar(finished, False), prefix + "_RESET_N": setvar(count, 0)}) if reset else {}
        return scope(seq(**reset_nodes, **{
            event_name: compose({"id": "@guid()", "fecha": "@utcNow()", "run": "@" + RUN,
                "etapa": prefix, "accion": event, "resultado": "REGISTRADO", "evidencia": evidence or {}}),
            prefix + "_CAS": {"type": "Until", "expression": f"@or(variables('{finished}'),greaterOrEquals(variables('{count}'),3))",
                "limit": {"count": 3, "timeout": "PT5M"}, "actions": loop}}))

    def wrap(self, trigger, main, *, identity=False, resolver=False, response_to_app=False):
        self.variable("varRespuesta", "object", dict.fromkeys(SALIDAS, ""))
        self.variable("varEtapa", "string", "INICIO")
        a = {"PARAM_SITIO_SHAREPOINT": compose("<CONFIGURAR_SITIO_SHAREPOINT>")}
        if resolver:
            a["PARAM_APROBADORES"] = compose(";".join(C.APROBADORES))
        if identity:
            a["PARAM_RESPONSABLES_RECUPERACION"] = compose([])
        for name, node in self.variables.items():
            a["INIT_" + name] = node
        setup = seq(
            Sitio_configurado=cond("@or(empty(outputs('PARAM_SITIO_SHAREPOINT')),startsWith(outputs('PARAM_SITIO_SHAREPOINT'),'<'))",
                seq(Falta_sitio=stop("CONFIGURACION_REQUERIDA", "Configurar el sitio antes de ejecutar.", True))),
            GET_LISTA_DEPOSITOS=read("_api/web/lists/GetByTitle('Depositos_Activos')?$select=Id,Title"),
            GUID_DEPOSITOS=compose("@toLower(body('GET_LISTA_DEPOSITOS')?['d']?['Id'])"),
            GET_LISTA_REVERSIONES=read("_api/web/lists/GetByTitle('Depositos_Reversiones')?$select=Id,Title"),
            GUID_REVERSIONES=compose("@toLower(body('GET_LISTA_REVERSIONES')?['d']?['Id'])"))
        if resolver:
            setup["Verificar_GUID_trigger"] = cond("@not(equals(outputs('GUID_REVERSIONES'),toLower(parameters('LISTA_REVERSIONES_ID'))))",
                seq(GUID_inconsistente=stop("CONFIGURACION_INCONSISTENTE", "El GUID del trigger no corresponde a Depositos_Reversiones.", True)))
        if identity:
            identity_nodes = seq(IDENTIDAD=api("shared_office365users", "MyProfile_V2", {"$select": "id,userPrincipalName,displayName"}),
                Identidad_completa=cond("@or(empty(body('IDENTIDAD')?['id']),empty(body('IDENTIDAD')?['userPrincipalName']))",
                    seq(Sin_identidad=stop("IDENTIDAD_NO_VERIFICADA", "La conexión del invocador no devolvió ID y UPN.", True))))
            identity_nodes["IDENTIDAD"]["runAfter"] = {next(reversed(setup)): ["Succeeded"]}
            setup.update(identity_nodes)
        main[next(iter(main))]["runAfter"] = {next(reversed(setup)): ["Succeeded"]}
        a["TRY"] = scope(seq(**setup, **main))
        if response_to_app:
            catch = seq(Error_no_controlado=response("ERROR", "ERROR_NO_CONTROLADO", "No se pudo confirmar la operación. Reintenta con el mismo UID y los mismos datos."))
            a["CATCH"] = scope(catch, {"TRY": FALLOS})
            a["Responder_a_PowerApps"] = {"type": "Response", "kind": "PowerApp", "runAfter": {"TRY": TODOS, "CATCH": TODOS},
                "inputs": {"statusCode": 200, "body": {key: f"@string(coalesce(variables('varRespuesta')?['{key}'],''))" for key in SALIDAS},
                    "schema": {"type": "object", "properties": {key: {"title": key, "type": "string", "x-ms-dynamically-added": True} for key in SALIDAS}}}}
        doc = definition(trigger, seq(**a))
        if resolver:
            doc["parameters"]["LISTA_REVERSIONES_ID"] = {"type": "String", "defaultValue": ""}
        return doc


def solicitud_trigger():
    specs = (("text", "OPERACION", "string"), ("number", "ID depósito", "number"),
             ("text_1", "CLAVE_TRANSACCION", "string"), ("text_2", "ETag esperado", "string"),
             ("text_3", "Motivo", "string"), ("text_4", "SOLICITUD_UID", "string"))
    props = {key: {"title": title, "type": typ, "x-ms-dynamically-added": True,
                   "x-ms-content-hint": "NUMBER" if typ == "number" else "TEXT"} for key, title, typ in specs}
    return {"manual": {"type": "Request", "kind": "PowerAppV2", "inputs": {"schema": {"type": "object", "properties": props, "required": list(props)}}}}


def uid_valid(value):
    clean = f"replace({value},'-','')"
    stripped = clean
    for char in "0123456789abcdef":
        stripped = f"replace({stripped},'{char}','')"
    return (f"and(equals(length({value}),36),equals(length({clean}),32),empty({stripped}),"
            f"not(equals({clean},'00000000000000000000000000000000')),"
            f"equals(substring(concat({value},'____________________________________'),8,1),'-'),"
            f"equals(substring(concat({value},'____________________________________'),13,1),'-'),"
            f"equals(substring(concat({value},'____________________________________'),18,1),'-'),"
            f"equals(substring(concat({value},'____________________________________'),23,1),'-'))")


def validar_uid_existente(prefix, row):
    same = "and(" + ",".join((f"equals({row}?['DEPOSITO_ID'],{Q('id')})",
        equal(f"{row}?['CLAVE_TRANSACCION']", Q('clave')), equal(f"{row}?['ETAG_SOLICITUD']", Q('etag')),
        equal(f"{row}?['MOTIVO_REVERSION']", Q('motivo')), f"equals({row}?['SOLICITANTE_ID'],body('IDENTIDAD')?['id'])",
        f"equals({row}?['LISTA_DEPOSITO_ID'],{LISTA_D})")) + ")"
    return cond("@" + same,
        seq(**{prefix + "_MISMA": response("EXISTENTE", "EXISTENTE", "Se recuperó la solicitud del mismo envío.", row)}),
        seq(**{prefix + "_AJENA": response("ERROR", "UID_REUTILIZADO", "El UID ya está asociado a otra identidad o contenido.")}))


def construir_solicitar():
    b = Build()
    b.variable("varSeguir", "boolean", True)
    entrada = {"operacion": "@toUpper(trim(coalesce(triggerBody()?['text'],'')))", "id": "@coalesce(triggerBody()?['number'],0)",
        "clave": "@coalesce(triggerBody()?['text_1'],'')", "etag": "@coalesce(triggerBody()?['text_2'],'')",
        "motivo": "@trim(coalesce(triggerBody()?['text_3'],''))", "uid": "@toLower(trim(coalesce(triggerBody()?['text_4'],'')))"}
    invalid = (f"or(not(contains(createArray('CONSULTAR','ENVIAR'),{Q('operacion')})),less({Q('id')},1),"
        f"not(equals(float({Q('id')}),float(int({Q('id')})))),empty({Q('clave')}),greater(length({Q('clave')}),255),"
        f"and(equals({Q('operacion')},'ENVIAR'),or(empty({Q('etag')}),empty({Q('motivo')}),greater(length({Q('motivo')}),4000),not({uid_valid(Q('uid'))}))))")
    main = seq(Entrada=compose(entrada), Entrada_invalida=cond("@" + invalid,
        seq(Respuesta_invalida=response("ERROR", "ENTRADA_INVALIDA", "Revisa operación, ID, clave, versión, UID y motivo (máximo 4000 caracteres)."), Parar_entrada=setvar("varSeguir", False))))
    uid_rows = "body('BUSCAR_UID')?['d']?['results']"
    replay = seq(BUSCAR_UID=read(matching(LISTA_R, "SOLICITUD_UID", Q('uid'))),
        UID_existente=cond(f"@greater(length({uid_rows}),0)", seq(
            Validar_repeticion=validar_uid_existente("REPLAY", f"first({uid_rows})"), Parar_replay=setvar("varSeguir", False))))
    main["Reintento_UID_antes_de_ETag"] = cond(f"@and(variables('varSeguir'),equals({Q('operacion')},'ENVIAR'))", replay)
    get = "LEER_DEPOSITO"
    row = R(get)
    snap = {key: f"@{row}?['{key}']" for key in C.CAMPOS_SNAPSHOT}
    snap.update(ID=f"@{row}?['Id']", ULTIMA_REVERSION_ID=f"@{row}?['ULTIMA_REVERSION_ID']", VERSION_SNAPSHOT=1,
        SITIO_SHAREPOINT="@outputs('PARAM_SITIO_SHAREPOINT')", LISTA_DEPOSITO_ID="@outputs('GUID_DEPOSITOS')", ETAG="@" + etag(get))
    bad_dep = (f"if(not(equals({row}?['Id'],{Q('id')})),'ID_INCONSISTENTE',if(empty({etag(get)}),'SIN_ETAG',"
        f"if(not({equal(row + "?['CLAVE_TRANSACCION']", Q('clave'))}),'CLAVE_NO_COINCIDE',"
        f"if(not(equals({row}?['ESTADO_ASIGNACION'],'ASIGNADO')),'YA_NO_ASIGNADO',"
        f"if(and(equals({Q('operacion')},'ENVIAR'),not({equal(etag(get), Q('etag'))})),'CONFLICTO','')))))")
    dep_read = read(item_uri(LISTA_D, Q('id')))
    validate = seq(**{get: dep_read,
        "Snapshot": compose(snap), "Validacion_deposito": compose("@" + bad_dep),
        "Deposito_no_apto": cond("@not(empty(outputs('Validacion_deposito')))", seq(
            Respuesta_deposito=response("@if(equals(outputs('Validacion_deposito'),'CONFLICTO'),'CONFLICTO','ERROR')", "@outputs('Validacion_deposito')", "El depósito no cumple el estado o versión de la solicitud."),
            Parar_deposito=setvar("varSeguir", False)))})
    main["Consultar_deposito"] = cond("@variables('varSeguir')", validate)
    main["Snapshot_cabe_integro"] = cond("@and(variables('varSeguir'),greater(length(string(outputs('Snapshot'))),60000))", seq(
        Snapshot_demasiado_largo=response("ERROR", "SNAPSHOT_EXCEDE_CAPACIDAD", "El snapshot íntegro supera la capacidad admitida. Requiere gestión operativa; no se recortó."),
        Parar_snapshot=setvar("varSeguir", False)))
    active = "body('BUSCAR_ACTIVA')?['d']?['results']"
    main["Comprobar_reserva"] = cond("@variables('varSeguir')", seq(
        CLAVE_ACTIVA=compose(f"@concat('ACTIVA|',{LISTA_D},'|',string(int({Q('id')})))"),
        BUSCAR_ACTIVA=read(matching(LISTA_R, "CLAVE_BLOQUEO", "outputs('CLAVE_ACTIVA')")),
        Ya_activa=cond(f"@greater(length({active}),0)", seq(
            Respuesta_activa=response("PENDIENTE_EXISTENTE", "PENDIENTE_EXISTENTE",
                f"@if(and({pending('first('+active+')')},lessOrEquals(ticks(first({active})?['FECHA_LIMITE']),ticks(utcNow()))),'VENCIDA — CIERRE PENDIENTE','Ya existe una solicitud activa para el depósito.')",
                f"first({active})"), Parar_activa=setvar("varSeguir", False)))))
    main["Devolver_consulta"] = cond(f"@and(variables('varSeguir'),equals({Q('operacion')},'CONSULTAR'))", seq(
        Consulta_lista=response("LISTO", "LISTO", "Depósito confirmado consultado.", snapshot_json="@string(outputs('Snapshot'))", etag="@" + etag(get)),
        Parar_consulta=setvar("varSeguir", False)))
    create = {key: f"@outputs('Snapshot')?['{key}']" for key in SNAPSHOT_VISIBLE}
    # Normalizar solo el POST del historial; el snapshot original sigue íntegro.
    for key in SNAPSHOT_VISIBLE:
        value = f"outputs('Snapshot')?['{key}']"
        if key not in C.REQUERIDOS_HISTORIAL:
            create[key] = f"@if(equals({value},''),null,{value})"
    create["FECHA_MOVIMIENTO"] = "@formatDateTime(outputs('Snapshot')?['FECHA_MOVIMIENTO'],'o')"
    create["FECHA_HORA_ASIGNACION"] = "@if(empty(outputs('Snapshot')?['FECHA_HORA_ASIGNACION']),null,formatDateTime(outputs('Snapshot')?['FECHA_HORA_ASIGNACION'],'o'))"
    create["IMPORTE"] = "@float(outputs('Snapshot')?['IMPORTE'])"
    create.update(SOLICITUD_UID="@" + Q('uid'), DEPOSITO_ID="@int(" + Q('id') + ")", LISTA_DEPOSITO_ID="@" + LISTA_D,
        CLAVE_TRANSACCION="@" + Q('clave'), CLAVE_BLOQUEO="@outputs('CLAVE_ACTIVA')", ETAG_SOLICITUD="@" + etag(get),
        SNAPSHOT_JSON="@string(outputs('Snapshot'))", MOTIVO_REVERSION="@" + Q('motivo'),
        SOLICITANTE_ID="@body('IDENTIDAD')?['id']", SOLICITANTE_UPN="@toLower(body('IDENTIDAD')?['userPrincipalName'])",
        FECHA_SOLICITUD="@formatDateTime(outputs('AHORA_SOLICITUD'),'o')", FECHA_LIMITE="@formatDateTime(addHours(outputs('AHORA_SOLICITUD'),168),'o')",
        ESTADO_SOLICITUD="PENDIENTE", FASE_PROCESO="RECIBIDA", RESULTADO_TECNICO=None,
        BITACORA_TECNICA_JSON="@string(createArray(outputs('EVENTO_RECIBIDA')))" )
    after_create = read(matching(LISTA_R, "SOLICITUD_UID", Q('uid')))
    after_create["runAfter"] = {"CREAR_SOLICITUD": TODOS}
    created = "body('VERIFICAR_CREACION_UID')?['d']?['results']"
    other = "body('VERIFICAR_CREACION_ACTIVA')?['d']?['results']"
    main["Crear_solicitud_completa"] = cond("@variables('varSeguir')", seq(
        AHORA_SOLICITUD=compose("@utcNow()"), EVENTO_RECIBIDA=compose({"id": "@guid()", "fecha": "@outputs('AHORA_SOLICITUD')", "run": "@" + RUN,
            "etapa": "RECIBIDA", "accion": "CREAR_SOLICITUD", "resultado": "PENDIENTE", "evidencia": {"solicitante": "@body('IDENTIDAD')?['id']"}}),
        CREAR_SOLICITUD=http("POST", uri(LISTA_R, "/items"), create), VERIFICAR_CREACION_UID=after_create,
        Creacion_acreditada=cond(f"@equals(length({created}),1)", seq(
            Verificar_UID_creado=validar_uid_existente("CREADO", f"first({created})"),
            Mensaje_creacion=cond("@and(equals(variables('varRespuesta')?['resultado'],'EXISTENTE'),equals(actions('CREAR_SOLICITUD')?['status'],'Succeeded'))", seq(
                Enviada=response("ENVIADA", "ENVIADA", "SOLICITUD DE REVERSIÓN ENVIADA", f"first({created})")))),
            seq(VERIFICAR_CREACION_ACTIVA=read(matching(LISTA_R, "CLAVE_BLOQUEO", "outputs('CLAVE_ACTIVA')")),
                Duplicado_confirmado=cond(f"@and(equals(length({other}),1),contains(string(outputs('CREAR_SOLICITUD')?['body']),'-2130575169'))", seq(
                    Otra_solicitud=response("PENDIENTE_EXISTENTE", "PENDIENTE_EXISTENTE", "Otra solicitud obtuvo la reserva única.", f"first({other})")), seq(
                    Creacion_incierta=response("ERROR", "CREACION_NO_CONFIRMADA", "No se confirmó la creación. Conserva el UID y reintenta el mismo envío.")))))))
    doc = b.wrap(solicitud_trigger(), main, identity=True, response_to_app=True)
    # El CATCH distingue un 404 real al leer; otros fallos no se convierten en inexistencia.
    doc["actions"]["CATCH"]["actions"] = seq(Error_lectura_o_proceso=response("ERROR",
        "@if(equals(outputs('LEER_DEPOSITO')?['statusCode'],404),'DEPOSITO_NO_ENCONTRADO','ERROR_NO_CONTROLADO')",
        "No se pudo confirmar la operación. Conserva el UID y los datos para reintentar."))
    return aplanar(doc)


def cerrar(b, prefix, ident, resultado, evidence=None):
    error = "" if resultado == "REVERTIDO" else resultado
    if resultado.startswith("@"):
        value = resultado[1:]
        error = f"@if(equals({value},'REVERTIDO'),'',{value})"
    return b.cas(prefix, ident, owned("$R"), {
        "FASE_PROCESO": "FINALIZADA", "RESULTADO_TECNICO": resultado,
        "FECHA_CIERRE": "@utcNow()", "CLAVE_BLOQUEO": "@concat('CERRADA|',$R?['SOLICITUD_UID'])",
        "ERROR_TECNICO": error},
        "CERRAR_RESULTADO", evidence or {"resultado": resultado})


def recuperar_error(b, prefix, ident, message, evidence=None):
    return b.cas(prefix, ident, owned("$R"), {
        "FASE_PROCESO": "RECUPERACION_REQUERIDA", "RESULTADO_TECNICO": "ERROR", "ERROR_TECNICO": message},
        "REQUIERE_RECUPERACION", evidence or {"detalle": message})


def expirar(b, prefix, ident, reset=False):
    predicate = f"and({pending('$R')},lessOrEquals(ticks($R?['FECHA_LIMITE']),ticks(utcNow())))"
    return b.cas(prefix, ident, predicate, {
        "ESTADO_SOLICITUD": "PENDIENTE", "FASE_PROCESO": "EXPIRADA", "RESULTADO_TECNICO": "NO_EJECUTADO",
        "CLAVE_BLOQUEO": "@concat('CERRADA|',$R?['SOLICITUD_UID'])", "FECHA_CIERRE": "@utcNow()",
        "APROBADOR_ID": None, "APROBADOR_UPN": None, "FECHA_DECISION": None, "ERROR_TECNICO": None},
        "PLAZO_VENCIDO", {"tarjeta": "Puede quedar pendiente de cancelación manual; respuesta tardía no autoriza reversión."}, reset=reset)


def ejecutar_reversion(b, prefix, ident, recuperacion=False):
    """Mismo protocolo autoritativo en resolver y recuperación, ETag original."""
    req_name, dep_name = prefix + "_SOLICITUD", prefix + "_DEPOSITO"
    request, deposit = R(req_name), R(dep_name)
    snap = f"json({request}?['SNAPSHOT_JSON'])"
    own = f"and({owned(request,'EJECUTANDO_REVERSION')},equals({request}?['ESTADO_SOLICITUD'],'APROBADO'),equals({request}?['LISTA_DEPOSITO_ID'],{LISTA_D}))"
    field_checks = []
    for field in ASIGNACION:
        left, right = f"{deposit}?['{field}']", f"{snap}?['{field}']"
        if field == "FECHA_HORA_ASIGNACION":
            field_checks.append(f"equals(if(empty({left}),0,ticks({left})),if(empty({right}),0,ticks({right})))")
        else:
            field_checks.append(equal(f"coalesce({left},'')", f"coalesce({right},'')"))
    same_snapshot = "and(" + ",".join(field_checks) + ")"
    validation = (f"if(not(equals({deposit}?['Id'],{request}?['DEPOSITO_ID'])),'ERROR',"
        f"if(empty({etag(dep_name)}),'ERROR',if(not({equal(etag(dep_name),request + "?['ETAG_SOLICITUD']")}),'CONFLICTO',"
        f"if(not({equal(deposit + "?['CLAVE_TRANSACCION']",request + "?['CLAVE_TRANSACCION']")}),'CLAVE_NO_COINCIDE',"
        f"if(not(equals({deposit}?['ESTADO_ASIGNACION'],'ASIGNADO')),'YA_NO_ASIGNADO',if(not({same_snapshot}),'CONFLICTO',''))))))")
    allow = "true"
    incompatible_marker = "false"
    if recuperacion:
        # No basta un booleano: el operador debe clasificar y documentar el intento
        # original como nunca enviado o error inequívoco sin efecto/HTTP pendiente.
        allow = "and(not(equals(outputs('REC_OPERACION'),'RECONCILIAR')),contains(createArray('NO_ENVIADO','FALLO_SIN_EFECTO'),outputs('EVIDENCIA')?['merge_estado']))"
        incompatible_marker = f"and(not(empty({deposit}?['ULTIMA_REVERSION_ID'])),not(equals({deposit}?['ULTIMA_REVERSION_ID'],{request}?['SOLICITUD_UID'])),not(equals({deposit}?['ULTIMA_REVERSION_ID'],{snap}?['ULTIMA_REVERSION_ID'])))"
    pre = prefix + "_PRE_MERGE"
    pre_row = R(pre)
    payload = {"ESTADO_ASIGNACION": "DISPONIBLE", **{f: None for f in C.CAMPOS_LIMPIAR},
               "ULTIMA_REVERSION_ID": "@" + request + "?['SOLICITUD_UID']"}
    merge = prefix + "_MERGE_DEPOSITO"
    attempt = prefix + "_INTENTO"
    merge_node = http("POST", item_uri(LISTA_D, request + "?['DEPOSITO_ID']"), payload, "@" + request + "?['ETAG_SOLICITUD']")
    close_success, close_412, mark_unknown = prefix + "_EXITO", prefix + "_CONFLICTO_412", prefix + "_INCIERTO"
    conflict_path = {}
    conflict_result = "CONFLICTO"
    conflict_evidence = {"status": 412, "merge": merge}
    conflict_closure = None
    if recuperacion:
        reread = prefix + "_RELEER_TRAS_412"
        conflict_path[reread] = read(item_uri(LISTA_D, request + "?['DEPOSITO_ID']"))
        conflict_result = f"@if(equals({R(reread,'ULTIMA_REVERSION_ID')},{request}?['SOLICITUD_UID']),'REVERTIDO','CONFLICTO')"
        conflict_evidence.update(marcador_tras_412="@" + R(reread, "ULTIMA_REVERSION_ID"),
                                 etag_tras_412="@" + etag(reread), prueba="RELECTURA_MARCADOR_TRAS_412")
        marker412 = R(reread, "ULTIMA_REVERSION_ID")
        incompatible412 = f"and(not(empty({marker412})),not(equals({marker412},{request}?['SOLICITUD_UID'])),not(equals({marker412},{snap}?['ULTIMA_REVERSION_ID'])))"
        outcome = conflict_result[1:]
        conflict_closure = b.cas(close_412, ident, owned('$R'), {
            "FASE_PROCESO": f"@if({incompatible412},'RECUPERACION_REQUERIDA','FINALIZADA')",
            "RESULTADO_TECNICO": f"@if({incompatible412},'ERROR',{outcome})",
            "FECHA_CIERRE": f"@if({incompatible412},null,utcNow())",
            "CLAVE_BLOQUEO": f"@if({incompatible412},$R?['CLAVE_BLOQUEO'],concat('CERRADA|',$R?['SOLICITUD_UID']))",
            "ERROR_TECNICO": f"@if({incompatible412},'MARCADOR_INCOMPATIBLE_CON_HISTORIAL_ACTIVO',if(equals({outcome},'REVERTIDO'),'','CONFLICTO'))"},
            "RECONCILIAR_412", conflict_evidence)
    conflict_path[close_412] = conflict_closure if conflict_closure is not None else cerrar(b, close_412, ident, conflict_result, conflict_evidence)
    conflict_path[prefix + "_FIN_412"] = stop()
    classify = cond(f"@equals(actions('{merge}')?['status'],'Succeeded')", seq(**{
        close_success: cerrar(b, close_success, ident, "REVERTIDO", {"status": f"@outputs('{merge}')?['statusCode']", "merge": merge}),
        prefix + "_AUDITORIA_NO_CERRADA": cond(f"@not(variables('ok_{close_success}'))", seq(**{
            prefix + "_ERROR_CIERRE": recuperar_error(b, prefix + "_ERROR_CIERRE", ident, "MERGE_ACREDITADO_CIERRE_PENDIENTE",
                {"merge": merge, "status": f"@outputs('{merge}')?['statusCode']", "aplicado": True})})),
        prefix + "_FIN_EXITO": stop()}), seq(**{
        prefix + "_ES_412": cond(f"@equals(outputs('{merge}')?['statusCode'],412)", seq(**conflict_path), seq(**{
            mark_unknown: recuperar_error(b, mark_unknown, ident, "MERGE_RESPUESTA_INCIERTA",
                {"status": f"@outputs('{merge}')?['statusCode']", "merge": merge, "respuesta": f"@outputs('{merge}')?['body']"}),
            prefix + "_FIN_INCIERTO": stop()}))}))
    classify["runAfter"] = {merge: TODOS}
    send = seq(**{
        attempt: b.cas(attempt, ident,
            f"and({owned('$R','EJECUTANDO_REVERSION')},equals($R?['ESTADO_SOLICITUD'],'APROBADO'),{equal('$R'+"?['ETAG_SOLICITUD']",request+"?['ETAG_SOLICITUD']")})",
            {"ETAG_EJECUCION": "@" + request + "?['ETAG_SOLICITUD']",
             "FECHA_EJECUCION_REVERSION": "@if(empty($R?['FECHA_EJECUCION_REVERSION']),utcNow(),$R?['FECHA_EJECUCION_REVERSION'])"},
            "INTENTO_MERGE_DEPOSITO", {"etag": "@" + request + "?['ETAG_SOLICITUD']", "deposito": "@" + request + "?['DEPOSITO_ID']"}),
        prefix + "_INTENTO_PERSISTIDO": cond(f"@not(variables('ok_{attempt}'))", seq(**{prefix + "_PARAR_SIN_INTENTO": stop()})),
        pre: read(item_uri(LISTA_R, ident)),
        prefix + "_PROPIEDAD_ANTES_ENVIO": cond(f"@not(and({owned(pre_row,'EJECUTANDO_REVERSION')},equals({pre_row}?['ESTADO_SOLICITUD'],'APROBADO'),{equal(pre_row+"?['ETAG_EJECUCION']",request+"?['ETAG_SOLICITUD']")}))",
            seq(**{prefix + "_PARAR_CAMBIO_DUENO": stop()})),
        merge: merge_node, prefix + "_CLASIFICAR_MERGE": classify})
    validate_success = seq(**{
        prefix + "_MARCADOR_PROPIO": cond(f"@equals({deposit}?['ULTIMA_REVERSION_ID'],{request}?['SOLICITUD_UID'])", seq(**{
            prefix + "_RECONCILIAR": cerrar(b, prefix + "_RECONCILIAR", ident, "REVERTIDO", {"prueba": "MARCADOR_PROPIO", "deposito_actual": "@" + deposit}),
            prefix + "_FIN_MARCADOR": stop()})),
        prefix + "_EVIDENCIA_SUFICIENTE": cond(f"@or(not({allow}),{incompatible_marker})", seq(**{
            prefix + "_SIN_PRUEBA": recuperar_error(b, prefix + "_SIN_PRUEBA", ident,
                f"@if({incompatible_marker},'MARCADOR_INCOMPATIBLE_CON_HISTORIAL_ACTIVO','INTENTO_ANTERIOR_NO_RECONCILIADO')"),
            prefix + "_FIN_SIN_PRUEBA": stop()})),
        prefix + "_VALIDACION": compose("@" + validation),
        prefix + "_NO_APTO": cond(f"@not(empty(outputs('{prefix}_VALIDACION')))", seq(**{
            prefix + "_CERRAR_NO_APTO": cerrar(b, prefix + "_CERRAR_NO_APTO", ident, f"@outputs('{prefix}_VALIDACION')",
                {"etag_actual": "@" + etag(dep_name), "clave_actual": "@" + deposit + "?['CLAVE_TRANSACCION']", "estado_actual": "@" + deposit + "?['ESTADO_ASIGNACION']"}),
            prefix + "_FIN_NO_APTO": stop()})),
        **send})
    if recuperacion:
        # Una prueba de efecto real tiene prioridad sobre la intención de cerrar
        # ERROR. Este bloque corre después de MARCADOR_PROPIO y antes de cualquier
        # posible nuevo intento.
        nodes = {}
        for name, node in validate_success.items():
            nodes[name] = node
            if name == prefix + "_MARCADOR_PROPIO":
                nodes[prefix + "_CERRAR_ERROR_MANUAL"] = cond(f"@and(equals(outputs('REC_OPERACION'),'CERRAR_ERROR'),not({incompatible_marker}))", seq(**{
                    prefix + "_CIERRE_ERROR": cerrar(b, prefix + "_CIERRE_ERROR", ident, "ERROR", {"evidencia_manual": "@outputs('EVIDENCIA')"}),
                    prefix + "_FIN_ERROR_MANUAL": stop()}))
        # Reconectar solo los dos enlaces afectados. CLASIFICAR_MERGE conserva
        # TODOS: debe procesar 412 y respuestas inciertas aunque falle el MERGE.
        inserted = prefix + "_CERRAR_ERROR_MANUAL"
        nodes[inserted]["runAfter"] = {prefix + "_MARCADOR_PROPIO": ["Succeeded"]}
        nodes[prefix + "_EVIDENCIA_SUFICIENTE"]["runAfter"] = {inserted: ["Succeeded"]}
        validate_success = nodes
    read_failure = seq(**{prefix + "_LECTURA_404": cond(f"@and(equals(outputs('{dep_name}')?['statusCode'],404),{allow})", seq(**{
        prefix + "_NO_ENCONTRADO": cerrar(b, prefix + "_NO_ENCONTRADO", ident, "DEPOSITO_NO_ENCONTRADO")}), seq(**{
        prefix + "_ERROR_LECTURA": recuperar_error(b, prefix + "_ERROR_LECTURA", ident, "ERROR_LECTURA_DEPOSITO",
            {"status": f"@outputs('{dep_name}')?['statusCode']"})})), prefix + "_FIN_ERROR_LECTURA": stop()})
    after_read = cond(f"@equals(actions('{dep_name}')?['status'],'Succeeded')", validate_success, read_failure)
    after_read["runAfter"] = {dep_name: TODOS}
    return scope(seq(**{
        req_name: read(item_uri(LISTA_R, ident)),
        prefix + "_AUTORIZADA": cond("@not(" + own + ")", seq(**{prefix + "_PARAR_NO_AUTORIZADA": stop()})),
        dep_name: read(item_uri(LISTA_D, request + "?['DEPOSITO_ID']")),
        prefix + "_TRATAR_LECTURA": after_read}))


def detalles_aprobacion(row):
    fields = (("Banco", "BANCO"), ("Cuenta", "CUENTA_BANCARIA"), ("Fecha movimiento", "FECHA_MOVIMIENTO"),
        ("Importe", "IMPORTE"), ("Moneda", "MONEDA"), ("Código de asignación", "CODIGO_ASIGNACION"),
        ("Estudiante", "ESTUDIANTE"), ("Solicitado por", "SOLICITADO_POR"), ("Sede", "SEDE_ASIGNACION"),
        ("Confirmado por", "USUARIO_ASIGNACION"), ("Fecha confirmación", "FECHA_HORA_ASIGNACION"),
        ("Solicitante de reversión", "SOLICITANTE_UPN"), ("Motivo", "MOTIVO_REVERSION"),
        ("UID", "SOLICITUD_UID"), ("ID depósito", "DEPOSITO_ID"), ("Clave", "CLAVE_TRANSACCION"), ("Límite UTC", "FECHA_LIMITE"))
    parts = []
    for title, field in fields:
        parts += [quote(title + ": "), f"string(coalesce({row}?['{field}'],''))", quote("\n\n")]
    return concat(*parts)


def aceptar_respuesta(b, prefix, ident, output):
    before = prefix + "_ANTES_RESPUESTA"
    row = R(before)
    evidence = output
    answer = f"first({output}?['responses'])"
    identity = f"{answer}?['responder']"
    upn = f"toLower(coalesce({identity}?['userPrincipalName'],{identity}?['email'],''))"
    config = f"json({row}?['CONFIG_APROBACION_JSON'])"
    valid = (f"and({owned(row,'ESPERANDO_APROBACION')},equals({row}?['ESTADO_SOLICITUD'],'PENDIENTE'),"
        f"less(ticks(utcNow()),ticks({row}?['FECHA_LIMITE'])),"
        f"lessOrEquals(ticks({answer}?['responseDate']),ticks({row}?['FECHA_LIMITE'])),"
        f"greaterOrEquals(ticks({answer}?['responseDate']),ticks({row}?['FECHA_SOLICITUD'])),"
        f"not(empty({identity}?['id'])),contains(split(toLower({config}?['aprobadores']),';'),{upn}),"
        f"contains(createArray('Approve','Reject'),{output}?['outcome']))")
    values = {"APROBACION_ID": f"@coalesce({output}?['name'],{output}?['approvalId'],'')",
        "APROBADOR_ID": "@" + identity + "?['id']", "APROBADOR_UPN": "@" + upn,
        "FECHA_DECISION": "@" + answer + "?['responseDate']",
        "COMENTARIO_APROBADOR": f"@coalesce({answer}?['comments'],'')",
        "RESPUESTA_APROBACION_JSON": "@string(" + evidence + ")"}
    approve = prefix + "_ACEPTAR_APPROVE"
    reject = prefix + "_ACEPTAR_REJECT"
    predicate = f"and({owned('$R','ESPERANDO_APROBACION')},equals($R?['ESTADO_SOLICITUD'],'PENDIENTE'),less(ticks(utcNow()),ticks($R?['FECHA_LIMITE'])))"
    discarded = prefix + "_DESCARTADA"
    return scope(seq(**{
        before: read(item_uri(LISTA_R, ident)),
        prefix + "_RESPUESTA_VALIDA": cond("@not(" + valid + ")", seq(**{
            discarded: b.cas(discarded, ident, "true", {}, "RESPUESTA_DESCARTADA", {"respuesta": "@" + evidence}),
            prefix + "_EXPIRAR_TARDIA": expirar(b, prefix + "_EXPIRAR_TARDIA", ident),
            prefix + "_FIN_DESCARTADA": stop()})),
        prefix + "_DECISION": cond(f"@equals({output}?['outcome'],'Approve')", seq(**{
            approve: b.cas(approve, ident, predicate, {**values, "ESTADO_SOLICITUD": "APROBADO", "FASE_PROCESO": "EJECUTANDO_REVERSION"}, "DECISION_APROBADA", {"respuesta": "@" + evidence}),
            prefix + "_APROBACION_NO_GANO": cond(f"@not(variables('ok_{approve}'))", seq(**{prefix + "_FIN_CAS_PERDIDO": stop()}))}), seq(**{
            reject: b.cas(reject, ident, predicate, {**values, "ESTADO_SOLICITUD": "RECHAZADO", "FASE_PROCESO": "FINALIZADA",
                "RESULTADO_TECNICO": "NO_EJECUTADO", "FECHA_CIERRE": "@utcNow()", "CLAVE_BLOQUEO": "@concat('CERRADA|',$R?['SOLICITUD_UID'])"}, "DECISION_RECHAZADA", {"respuesta": "@" + evidence}),
            prefix + "_FIN_RECHAZADA": stop()}))}))


def esperar_aprobacion(b, prefix, ident, existing=False, recovery=False, only_pending=False):
    get = prefix + "_LEER"
    row = R(get)
    action = prefix + "_APPROVAL"
    cfg = f"json({row}?['CONFIG_APROBACION_JSON'])"
    if existing is True:
        approval = api("shared_approvals", "WaitForAnApproval", {"approvalName": f"@{row}?['APROBACION_ID']"}, webhook=True)
    else:
        approval = api("shared_approvals", "StartAndWaitForAnApproval", {
            "approvalType": "Basic", "WebhookApprovalCreationInput/title": f"@concat('SOLICITUD DE REVERSIÓN DE DEPÓSITO · ',{row}?['SOLICITUD_UID'])",
            "WebhookApprovalCreationInput/assignedTo": "@" + cfg + "?['aprobadores']",
            "WebhookApprovalCreationInput/details": detalles_aprobacion(row),
            "WebhookApprovalCreationInput/enableNotifications": True,
            "WebhookApprovalCreationInput/enableReassignment": False}, webhook=True)
    approval["limit"] = {"timeout": "P7D"}  # rama paralela exige FECHA_LIMITE absoluta
    approval_nodes = {action: approval}
    approval_output = f"body('{action}')"
    if existing == "dynamic":
        wait = api("shared_approvals", "WaitForAnApproval", {"approvalName": f"@{row}?['APROBACION_ID']"}, webhook=True)
        wait["limit"] = {"timeout": "P7D"}
        approval_nodes = {prefix + "_ELEGIR_APPROVAL": cond("@equals(outputs('REC_OPERACION'),'ESPERAR_APROBACION')",
            seq(**{prefix + "_WAIT_EXISTENTE": wait}), seq(**{action: approval})),
            prefix + "_SALIDA_APPROVAL": compose(f"@if(equals(outputs('REC_OPERACION'),'ESPERAR_APROBACION'),body('{prefix}_WAIT_EXISTENTE'),body('{action}'))")}
        approval_output = f"outputs('{prefix}_SALIDA_APPROVAL')"
    approval_nodes[prefix + "_RESPONDER"] = aceptar_respuesta(b, prefix + "_R", ident, approval_output)
    approval_path = seq(**approval_nodes)
    if only_pending:
        approval_path = {prefix + "_SOLO_PENDIENTE": cond(f"@equals({row}?['ESTADO_SOLICITUD'],'PENDIENTE')", approval_path)}
    approval_path[prefix + "_EJECUTAR"] = ejecutar_reversion(b, prefix + "_E", ident, recuperacion=recovery)
    approval_path = seq(**approval_path)
    # No copiar result(PROCESO): incluye filas completas con su bitácora y
    # snapshots, que duplicarían evidencia y podrían impedir guardar el fallo.
    error_evidence = {
        "proceso": prefix + "_PROCESO",
        "estado_proceso": f"@actions('{prefix}_PROCESO')?['status']",
        "aprobacion": {"accion": action, "estado": f"@actions('{action}')?['status']",
            "codigo": f"@actions('{action}')?['code']"},
        "merge_deposito": {"accion": prefix + "_E_MERGE_DEPOSITO",
            "estado": f"@actions('{prefix}_E_MERGE_DEPOSITO')?['status']",
            "http": f"@outputs('{prefix}_E_MERGE_DEPOSITO')?['statusCode']"}}
    if existing == "dynamic":
        wait_action = prefix + "_WAIT_EXISTENTE"
        error_evidence["espera_existente"] = {"accion": wait_action,
            "estado": f"@actions('{wait_action}')?['status']",
            "codigo": f"@actions('{wait_action}')?['code']"}
    catch = scope(seq(**{
        prefix + "_EXPIRAR_ERROR": expirar(b, prefix + "_EXPIRAR_ERROR", ident),
        prefix + "_REGISTRAR_FALLO": recuperar_error(b, prefix + "_REGISTRAR_FALLO", ident, "ERROR_APPROVAL_O_PROCESO",
            error_evidence),
        prefix + "_FIN_FALLO": stop()}), {prefix + "_PROCESO": FALLOS})
    timer_expire = prefix + "_RELOJ_EXPIRAR"
    timer = scope(seq(**{
        prefix + "_HASTA_LIMITE": {"type": "Wait", "inputs": {"until": {"timestamp": "@" + row + "?['FECHA_LIMITE']"}}},
        timer_expire: expirar(b, timer_expire, ident),
        prefix + "_RELOJ_GANO": cond(f"@variables('ok_{timer_expire}')", seq(**{prefix + "_FIN_PLAZO": stop()}))}))
    # Ambas ramas arrancan desde la misma relectura. Ninguna comparte variables CAS.
    apt = f"and({owned(row,'ESPERANDO_APROBACION')},less(ticks(utcNow()),ticks({row}?['FECHA_LIMITE'])))"
    if only_pending:
        apt = f"or({apt},and({owned(row,'EJECUTANDO_REVERSION')},equals({row}?['ESTADO_SOLICITUD'],'APROBADO')))"
    main = seq(**{get: read(item_uri(LISTA_R, ident)),
        prefix + "_PREVIA": cond(f"@not({apt})",
            seq(**{prefix + "_EXPIRAR_PREVIA": expirar(b, prefix + "_EXPIRAR_PREVIA", ident), prefix + "_FIN_PREVIA": stop()})),
        prefix + "_PROCESO": scope(approval_path), prefix + "_CATCH": catch})
    timer["runAfter"] = {prefix + "_PREVIA": ["Succeeded"]}
    main[prefix + "_RELOJ"] = timer
    return scope(main)


def construir_resolver():
    b = Build()
    trigger = {"Cuando_se_crea_solicitud": {"type": "OpenApiConnection", "recurrence": {"frequency": "Minute", "interval": 1},
        "splitOn": "@triggerOutputs()?['body/value']", "inputs": {
            "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "connectionName": "shared_sharepointonline", "operationId": "GetOnNewItems"},
            "parameters": {"dataset": "<CONFIGURAR_SITIO_SHAREPOINT>", "table": "@parameters('LISTA_REVERSIONES_ID')"},
            "authentication": "@parameters('$authentication')"}}}
    ident = "int(triggerBody()?['ID'])"
    pred = f"and(equals($R?['FASE_PROCESO'],'RECIBIDA'),equals($R?['ESTADO_SOLICITUD'],'PENDIENTE'),empty($R?['RUN_ID']),less(ticks(utcNow()),ticks($R?['FECHA_LIMITE'])),equals($R?['LISTA_DEPOSITO_ID'],{LISTA_D}))"
    main = seq(
        Reclamar=b.cas("RECLAMAR", ident, pred, {"RUN_ID": "@" + RUN, "FASE_PROCESO": "ESPERANDO_APROBACION",
            "CONFIG_APROBACION_JSON": "@string(setProperty(outputs('CONFIG_APROBACION'),'fecha_limite',$R?['FECHA_LIMITE']))"}, "INTENTO_APPROVAL", {"tipo": "StartAndWaitForAnApproval", "accion": "RES_APPROVAL"}),
        Solo_ganador=cond("@not(variables('ok_RECLAMAR'))", seq(Expirar_no_reclamada=expirar(b, "RES_SIN_DUENO_EXP", ident), Fin_no_propietario=stop())),
        Ciclo_aprobacion=esperar_aprobacion(b, "RES", ident))
    # Configuración efectiva persistida ANTES de comenzar el webhook.
    config = compose({"aprobadores": "@outputs('PARAM_APROBADORES')", "modalidad": "FirstToRespond", "reasignacion": False,
                      "plazo_horas": 168, "fecha_limite": "@triggerBody()?['FECHA_LIMITE']"})
    main = seq(CONFIG_APROBACION=config, **main)
    return aplanar(b.wrap(trigger, main, resolver=True))


def construir_expirar():
    b = Build()
    b.variable("varSiguiente", "string", "")
    b.variable("varErrorPagina", "boolean", False)
    cutoff = "outputs('CORTE_EXPIRACION')"
    first_url = concat(quote("_api/web/lists(guid'"), LISTA_R,
        quote("')/items?$filter=FECHA_LIMITE le datetime'"), cutoff,
        quote("' and ESTADO_SOLICITUD eq 'PENDIENTE' and (FASE_PROCESO eq 'RECIBIDA' or FASE_PROCESO eq 'ESPERANDO_APROBACION' or FASE_PROCESO eq 'RECUPERACION_REQUERIDA')&$orderby=ID asc&$top=100"))
    ident = "int(coalesce(items('EXP_PAGINA')?['ID'],items('EXP_PAGINA')?['Id']))"
    next_page = "coalesce(body('EXP_LEER_PAGINA')?['d']?['__next'],'')"
    loop = seq(EXP_LEER_PAGINA=read("@variables('varSiguiente')"),
        EXP_PAGINA={"type": "Foreach", "foreach": "@body('EXP_LEER_PAGINA')?['d']?['results']",
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "actions": seq(EXP_CERRAR=expirar(b, "EXP_CERRAR", ident, reset=True))},
        EXP_NEXT_SEGURO=cond(f"@or(empty({next_page}),startsWith({next_page},concat(outputs('PARAM_SITIO_SHAREPOINT'),'/_api/')),startsWith({next_page},'_api/'))",
            seq(EXP_ASIGNAR_NEXT=setvar("varSiguiente", f"@replace({next_page},concat(outputs('PARAM_SITIO_SHAREPOINT'),'/'),'')")),
            seq(EXP_ERROR_NEXT=setvar("varErrorPagina", True), EXP_PARAR_PAGINAS=setvar("varSiguiente", ""))))
    main = seq(CORTE_EXPIRACION=compose("@utcNow()"), EXP_PRIMERA_PAGINA=setvar("varSiguiente", first_url),
        EXP_PAGINAR={"type": "Until", "expression": "@empty(variables('varSiguiente'))", "limit": {"count": 5000, "timeout": "PT1H"}, "actions": loop},
        EXP_PAGINACION_COMPLETA=cond("@or(variables('varErrorPagina'),not(empty(variables('varSiguiente'))))",
            seq(EXP_FALLO_PAGINACION=stop("PAGINACION_INCOMPLETA", "Se requiere revisar la paginación; no se siguió una URL externa ni se omitieron páginas silenciosamente.", True))))
    trigger = {"Cada_cinco_minutos": {"type": "Recurrence", "recurrence": {"frequency": "Minute", "interval": 5},
        "runtimeConfiguration": {"concurrency": {"runs": 1}}}}
    return aplanar(b.wrap(trigger, main))


def recuperar_trigger():
    specs = (("text", "SOLICITUD_UID"), ("text_1", "OPERACION"), ("text_2", "EVIDENCIA_JSON"))
    props = {key: {"title": title, "type": "string", "x-ms-dynamically-added": True,
        "x-ms-content-hint": "TEXT", "description": "Recuperación manual restringida; ver DESPLIEGUE_P9_REVERSION.md."} for key, title in specs}
    return {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": props, "required": list(props)}}}}


def construir_recuperar():
    b = Build()
    uid = "outputs('REC_UID')"
    row = R("REC_LEER_SOLICITUD")
    ident = "outputs('REC_ID')"
    evidence = "outputs('EVIDENCIA')"
    mode = "outputs('REC_OPERACION')"
    # No se consulta una API de ejecuciones: operador autenticado verifica el portal
    # y entrega referencias verificables. Roles/run-only se restringen en despliegue.
    manual_proof = (f"and(equals({evidence}?['run_id'],{row}?['RUN_ID']),not(empty({row}?['RUN_ID'])),"
        f"contains(createArray('Succeeded','Failed','Cancelled','TimedOut'),{evidence}?['estado_run']),"
        f"startsWith({evidence}?['url_ejecucion'],'https://make.powerautomate.com/'),"
        f"contains({evidence}?['url_ejecucion'],{row}?['RUN_ID']),"
        f"not(empty({evidence}?['fecha_fin_run'])),not(empty({evidence}?['fecha_verificacion'])),"
        f"lessOrEquals(ticks({evidence}?['fecha_fin_run']),ticks({evidence}?['fecha_verificacion'])),"
        f"lessOrEquals(ticks({evidence}?['fecha_verificacion']),ticks(utcNow())),"
        f"equals({evidence}?['verificado_por_id'],body('IDENTIDAD')?['id']),"
        f"not(empty({evidence}?['motivo_recuperacion'])),not(empty({evidence}?['evidencia_operaciones'])))")
    # Si el trigger nunca reclamó dueño, ausencia de RUN_ID + RECIBIDA es prueba de
    # que ningún trabajador autorizado pudo enviar Approval ni MERGE.
    unclaimed = f"and(empty({row}?['RUN_ID']),equals({row}?['FASE_PROCESO'],'RECIBIDA'),empty({row}?['CONFIG_APROBACION_JSON']),empty({row}?['FECHA_EJECUCION_REVERSION']))"
    main = seq(REC_UID=compose("@toLower(trim(triggerBody()?['text']))"),
        REC_OPERACION=compose("@toUpper(trim(triggerBody()?['text_1']))"), EVIDENCIA=compose("@json(triggerBody()?['text_2'])"),
        REC_OPERADOR_AUTORIZADO=cond("@not(contains(outputs('PARAM_RESPONSABLES_RECUPERACION'),body('IDENTIDAD')?['id']))",
            seq(REC_DENEGADA=stop("RESPONSABLE_NO_AUTORIZADO", "El ID autenticado no está en la lista de responsables configurada.", True))),
        REC_VALIDAR_ENTRADA=cond(f"@not(and({uid_valid(uid)},contains(createArray('RECONCILIAR','CONTINUAR','ESPERAR_APROBACION','INICIAR_APROBACION','CERRAR_ERROR'),{mode})))",
            seq(REC_ENTRADA_INVALIDA=stop("RECUPERACION_INVALIDA", "Revisa UID, operación y evidencia.", True))),
        REC_BUSCAR=read(matching(LISTA_R, "SOLICITUD_UID", uid)),
        REC_EXISTE_UNICA=cond("@not(equals(length(body('REC_BUSCAR')?['d']?['results']),1))",
            seq(REC_NO_EXISTE=stop("SOLICITUD_NO_ENCONTRADA", "El UID debe identificar exactamente una solicitud.", True))),
        REC_ID=compose("@int(coalesce(first(body('REC_BUSCAR')?['d']?['results'])?['ID'],first(body('REC_BUSCAR')?['d']?['results'])?['Id']))"),
        REC_LEER_SOLICITUD=read(item_uri(LISTA_R, ident)),
        REC_YA_TERMINAL=cond(f"@contains({TERMINALES},{row}?['FASE_PROCESO'])", seq(
            REC_RESULTADO_GUARDADO=compose("@" + row), REC_FIN_YA_CERRADA=stop())),
        REC_ORIGEN_CORRECTO=cond(f"@not(and(equals({row}?['LISTA_DEPOSITO_ID'],{LISTA_D}),equals({row}?['SOLICITUD_UID'],{uid})))",
            seq(REC_ORIGEN_AJENO=stop("ORIGEN_INCONSISTENTE", "El historial no corresponde a la lista y UID configurados.", True))),
        REC_PRUEBA_TERMINACION=cond(f"@not(if({unclaimed},true,{manual_proof}))",
            seq(REC_PRUEBA_REQUERIDA=stop("EVIDENCIA_TERMINACION_REQUERIDA", "No se transfiere RUN_ID sin verificación documentada del propietario anterior.", True))))
    claim_pred = f"and(not(contains({TERMINALES},$R?['FASE_PROCESO'])),{equal('$R'+"?['RUN_ID']",row+"?['RUN_ID']")},equals($R?['SOLICITUD_UID'],{uid}))"
    main["REC_RECLAMAR"] = b.cas("REC_RECLAMAR", ident, claim_pred,
        {"RUN_ID": "@" + RUN, "FASE_PROCESO": "RECUPERACION_REQUERIDA"}, "RECUPERACION_MANUAL_VERIFICADA",
        {"operador_id": "@body('IDENTIDAD')?['id']", "operador_upn": "@body('IDENTIDAD')?['userPrincipalName']",
         "propietario_anterior": "@" + row + "?['RUN_ID']", "evidencia_manual": "@" + evidence,
         "limite_verificacion": "La terminalidad fue verificada por el operador en el portal; no por una API del flujo."})
    main["REC_SOLO_GANADOR"] = cond("@not(variables('ok_REC_RECLAMAR'))", seq(REC_FIN_OTRO_DUENO=stop()))
    main["REC_EXPIRAR_SIN_DECISION"] = expirar(b, "REC_EXPIRAR", ident)
    main["REC_FIN_EXPIRADA"] = cond("@variables('ok_REC_EXPIRAR')", seq(REC_TERMINADA_PLAZO=stop()))
    main["REC_ESTADO_ACTUAL"] = read(item_uri(LISTA_R, ident))
    current = R("REC_ESTADO_ACTUAL")
    main["REC_MODO_APROBADA_VALIDO"] = cond(f"@and(equals({current}?['ESTADO_SOLICITUD'],'APROBADO'),not(contains(createArray('RECONCILIAR','CONTINUAR','CERRAR_ERROR'),{mode})))",
        seq(REC_MODO_INCOMPATIBLE=stop("OPERACION_INCOMPATIBLE_CON_ETAPA", "La solicitud ya tiene aprobación aceptada; no corresponde iniciar o esperar otra Approval.", True)))
    proof_safe_error = f"and(contains(createArray('NO_ENVIADO','FALLO_SIN_EFECTO'),{evidence}?['merge_estado']),not(empty({evidence}?['error_permanente'])),or(equals({current}?['ESTADO_SOLICITUD'],'APROBADO'),equals({evidence}?['approval_estado'],'NO_CREADA')))"
    main["REC_PRUEBA_ERROR"] = cond(f"@and(equals({mode},'CERRAR_ERROR'),not({proof_safe_error}))", seq(
        REC_ERROR_NO_ACREDITADO=stop("AUSENCIA_DE_EFECTO_NO_ACREDITADA", "El cierre requiere error permanente y ausencia de efectos pendientes demostrada.", True)))
    main["REC_ERROR_PERMANENTE"] = cond(f"@and(equals({mode},'CERRAR_ERROR'),equals({current}?['ESTADO_SOLICITUD'],'PENDIENTE'))", seq(
        REC_ERROR_TERMINAL=cerrar(b, "REC_ERROR_TERMINAL", ident, "ERROR", {"evidencia_manual": "@" + evidence}), REC_FIN_ERROR_TERMINAL=stop()))
    main["REC_APROBADA"] = cond(f"@equals({current}?['ESTADO_SOLICITUD'],'APROBADO')", seq(
        REC_AUTORIZAR_EJECUCION=b.cas("REC_AUTORIZAR", ident,
            f"and({owned('$R','RECUPERACION_REQUERIDA')},equals($R?['ESTADO_SOLICITUD'],'APROBADO'))",
            {"FASE_PROCESO": "EJECUTANDO_REVERSION"}, "RETOMAR_DECISION_PERSISTIDA", {"evidencia_manual": "@" + evidence})))
    # Las recuperaciones sin decisión no deben recrear una aprobación ambigua.
    predecision = seq(REC_SIN_DECISION=cond(f"@not(equals({current}?['ESTADO_SOLICITUD'],'PENDIENTE'))",
        seq(REC_ESTADO_NO_ADMITIDO=stop("ESTADO_NO_RECUPERABLE", "La decisión no admite este camino.", True)))
    )
    predecision["REC_OPERACION_PREDECISION"] = cond(f"@not(contains(createArray('INICIAR_APROBACION','ESPERAR_APROBACION','CERRAR_ERROR'),{mode}))",
        seq(REC_NO_HAY_MERGE=stop("ETAPA_REQUIERE_EVIDENCIA", "La solicitud está sin decisión; usa la recuperación de la aprobación con evidencia.", True)))
    start_ok = f"and(equals({mode},'INICIAR_APROBACION'),equals({evidence}?['approval_estado'],'NO_CREADA'),equals({evidence}?['merge_estado'],'NO_ENVIADO'))"
    wait_ok = f"and(equals({mode},'ESPERAR_APROBACION'),equals({evidence}?['approval_estado'],'CREADA_IDENTIFICADA'),not(empty({evidence}?['aprobacion_id'])),equals({evidence}?['solicitud_uid'],{uid}))"
    predecision["REC_PROBAR_ETAPA_APPROVAL"] = cond(f"@not(or({start_ok},{wait_ok}))", seq(
        REC_APROBACION_AMBIGUA=stop("APROBACION_NO_ACREDITADA", "No se crea otra Approval sin prueba de que nunca existió, ni se espera una ajena.", True)))
    # Continuará en el mismo bloque de aprobación común (una sola copia del motor).
    cfg = "outputs('EVIDENCIA')?['config_aprobacion']"
    people = f"split(toLower(coalesce({cfg}?['aprobadores'],'')),';')"
    config_valid = (f"and(equals({cfg}?['modalidad'],'FirstToRespond'),equals({cfg}?['reasignacion'],false),"
        f"equals({cfg}?['plazo_horas'],168),equals(length({people}),2),equals(length(union({people},{people})),2),"
        f"contains(first({people}),'@'),contains(last({people}),'@'),"
        "startsWith(coalesce(outputs('EVIDENCIA')?['fuente_config_url'],''),'https://make.powerautomate.com/'),"
        "not(empty(outputs('EVIDENCIA')?['fecha_verificacion_config'])),"
        "lessOrEquals(ticks(outputs('EVIDENCIA')?['fecha_verificacion_config']),ticks(utcNow())))")
    predecision["REC_CONFIG_VERIFICADA"] = cond(f"@not(if(empty({current}?['CONFIG_APROBACION_JSON']),{config_valid},true))",
        seq(REC_CONFIG_NO_ACREDITADA=stop("CONFIGURACION_APPROVAL_NO_ACREDITADA", "Sin configuración persistida se requiere copia verificada del parámetro único del resolver.", True)))
    predecision["REC_CONFIG_INICIAL"] = compose(f"@if(empty({current}?['CONFIG_APROBACION_JSON']),setProperty({cfg},'fecha_limite',{current}?['FECHA_LIMITE']),json({current}?['CONFIG_APROBACION_JSON']))")
    predecision["REC_PREPARAR_APPROVAL"] = b.cas("REC_PREPARAR", ident,
        f"and({owned('$R','RECUPERACION_REQUERIDA')},equals($R?['ESTADO_SOLICITUD'],'PENDIENTE'),less(ticks(utcNow()),ticks($R?['FECHA_LIMITE'])))",
        {"FASE_PROCESO": "ESPERANDO_APROBACION",
         "CONFIG_APROBACION_JSON": "@if(empty($R?['CONFIG_APROBACION_JSON']),string(outputs('REC_CONFIG_INICIAL')),$R?['CONFIG_APROBACION_JSON'])",
         "APROBACION_ID": f"@if(equals({mode},'ESPERAR_APROBACION'),{evidence}?['aprobacion_id'],$R?['APROBACION_ID'])"},
        "RECUPERAR_APPROVAL", {"operacion": "@" + mode, "evidencia_manual": "@" + evidence})
    predecision["REC_APPROVAL_GANADA"] = cond("@not(variables('ok_REC_PREPARAR'))", seq(REC_FIN_CAS_APPROVAL=stop()))
    main["REC_PREPARAR_SIN_DECISION"] = cond(f"@equals({current}?['ESTADO_SOLICITUD'],'PENDIENTE')", seq(**predecision))
    main["REC_CICLO_APPROVAL"] = esperar_aprobacion(b, "REC_A", ident, existing="dynamic", recovery=True, only_pending=True)
    return aplanar(b.wrap(recuperar_trigger(), main, identity=True))


def aplanar(doc):
    """Quita ámbitos auxiliares, manteniendo fronteras TRY/CATCH reales.

    Evita superar los ocho niveles de Power Automate; conserva dependencias de
    cada rama paralela y nunca extrae acciones de If/Until/Foreach.
    """
    replacements = {}

    def flatten(actions):
        out = {}
        for name, node in actions.items():
            for key in ("actions",):
                if key in node:
                    node[key] = flatten(node[key])
            if "else" in node:
                node["else"]["actions"] = flatten(node["else"].get("actions", {}))
            if node["type"] == "Scope" and name not in ("TRY", "CATCH") and not name.endswith(("_PROCESO", "_CATCH")):
                children = node["actions"]
                if children:
                    for child in children.values():
                        if not child.get("runAfter"):
                            child["runAfter"] = node.get("runAfter", {})
                    replacements[name] = next(reversed(children))
                    out.update(children)
                else:
                    out[name] = compose(None)
                    out[name]["runAfter"] = node.get("runAfter", {})
            else:
                out[name] = node
        return out

    doc["actions"] = flatten(doc["actions"])

    def target(name):
        while name in replacements:
            name = replacements[name]
        return name

    from p9.reversion.wdl import walk
    for _, node in walk(doc["actions"]):
        if "runAfter" in node:
            node["runAfter"] = {target(name): status for name, status in node["runAfter"].items()}
    return doc
