"""Generador del flujo PROTOTIPO `P9_MASIVA_PROTO_CONFIRMAR` (confirmación masiva) y de su ZIP importable.

    python -m proto_masiva.flows.construir_confirmar

Confirma SOLO las filas que Power Apps envía (las que la prevalidación dejó en VALIDO), UNA DETRÁS DE OTRA, con la MISMA semántica que la
confirmación individual `P9_ASIGNAR_DEPOSITO` V4.2 (fuente de verdad: p9/asignar/flujo_asignar_powerapps_v4_2_definition.json):

  por fila:  releer el depósito por ID (GET, `$select`) → comprobar que NADA relevante cambió desde la prevalidación → tomar el ETag
             FRESCO de esa lectura → `POST` + `X-HTTP-Method: MERGE` + `IF-MATCH: <ETag>` (nunca `*`), sin reintentos, con los
             MISMOS 8 campos que V4.2 → 412 = CONFLICTO.

  La prevalidación NO reserva nada: este flujo no confía en ella ni reutiliza ningún ETag viejo.
  Sin rollback global: lo confirmado queda confirmado. Un error en una fila NO detiene a las demás. Secuencial (concurrencia 1).
  Sin lotes, sin historial, sin listas nuevas, sin sondeo: la respuesta devuelve el resultado de cada fila a Power Apps, que lo guarda
  solo en memoria.

ESCALA: es un flujo SÍNCRONO (la app espera la respuesta). No se afirma que 1999 filas quepan: `PARAM_MAX_FILAS_POR_LLAMADA` limita cada
llamada y se sube solo después de medir en el tenant (ver ../CONFIRMACION_MASIVA.md §7).
"""
from __future__ import annotations

import json
from pathlib import Path

from p9 import contrato as C
from p9.wdl import FALLOS, TODOS, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable
from proto_masiva.contrato_plantilla import MONEDAS
from proto_masiva.flows import construir as BASE
from proto_masiva.flows import prevalidacion as PV
from proto_masiva.flows.prevalidacion import centavos, encadenar_if, it, lit, pasar, sin_digitos

CARPETA_SALIDA = Path(__file__).resolve().parent
NOMBRE_FLUJO = "P9_MASIVA_PROTO_CONFIRMAR"
API_SP = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
SITIO = C.SITIO_SHAREPOINT
LISTA_ID = C.LISTA_DEPOSITOS_ACTIVOS_ID

MAX_FILAS_POR_LLAMADA = 50     # tope por llamada síncrona: se sube SOLO después de medir (1, 3, 10, 50 filas en el tenant)
MAX_FILAS_ARCHIVO = 1999       # límite de negocio del archivo (la prevalidación rechaza 2000 o más)

ENTRADAS = (("text", "detalle_json", "Filas VALIDO de la prevalidación, como arreglo JSON (JSON(..., JSONFormat.Compact))"),
            ("text_1", "usuario_email", "Correo del usuario que confirma (User().Email), como en la confirmación individual"))
RESULTADOS_FILA = ("CONFIRMADO", "NO_ENCONTRADO", "NO_DISPONIBLE", "CONFLICTO", "CONFLICTO_DATOS", "ERROR_FILA")
RESULTADOS_GLOBALES = ("OK", "PARCIAL", "ERROR")
CODIGO_OK, CODIGO_PARCIAL, CODIGO_NINGUNA = "CONFIRMACION_OK", "CONFIRMACION_PARCIAL", "NINGUNA_CONFIRMADA"
CODIGOS_ERROR = ("ENTRADA_INVALIDA", "SIN_FILAS", "LOTE_EXCEDE_LIMITE", "ERROR_NO_CONTROLADO")
CODIGOS = (CODIGO_OK, CODIGO_PARCIAL, CODIGO_NINGUNA) + CODIGOS_ERROR
SALIDAS = ("resultado", "codigo", "mensaje", "filas_recibidas", "filas_confirmadas", "filas_no_confirmadas", "detalle_json", "tiempos_ms")
DETALLE_CAMPOS = ("fila_excel", "deposito_id", "resultado", "mensaje", "estado_final", "banco", "cuenta_bancaria", "codigo_asignacion",
                  "importe", "moneda")
# Campos de cada fila que Power Apps envía en detalle_json (los 12 de colPrevalidacionP9 que hacen falta)
CAMPOS_ENTRADA = ("fila_excel", "deposito_id", "clave_transaccion", "banco", "cuenta_bancaria", "codigo_asignacion", "importe", "moneda",
                  "estudiante", "solicitado_por", "sede", "observacion")
# Columnas que se releen del depósito (nombres internos reales: ver ../PREVALIDACION_REAL.md §2)
COLUMNAS_LECTURA = ("Id", "CLAVE_TRANSACCION", "ESTADO_ASIGNACION", "TIPO_MOVIMIENTO", "FECHA_MOVIMIENTO", "BANCO", "CUENTA_BANCARIA",
                    "CODIGO_ASIGNACION", "IMPORTE", "MONEDA", "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION")
# Los 8 campos EXACTOS que escribe V4.2 (Cuerpo_actualizacion), en su orden
CAMPOS_ESCRITOS = ("ESTADO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "OBSERVACION",
                   "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION")
FILA = "items('Para_cada_fila')"


def fila(campo):
    return f"{FILA}?['{campo}']"


def d(campo):
    return f"body('Leer_deposito')?['d']?['{campo}']"


# ---------------------------------------------------------------------------------------------- disparador
def disparador():
    """Power Apps (V2) con DOS entradas de texto. Todas en `required`, como V4.2, para que Studio pida los argumentos posicionales."""
    props = {clave: {"title": titulo, "type": "string", "x-ms-dynamically-added": True, "description": descripcion,
                     "x-ms-content-hint": "TEXT"} for clave, titulo, descripcion in ENTRADAS}
    return {"manual": {"type": "Request", "kind": "PowerAppV2", "inputs": {"schema": {
        "type": "object", "properties": props, "required": [c for c, _, _ in ENTRADAS]}}}}


# ---------------------------------------------------------------------------------------------- validación de las filas recibidas
def filas_normalizadas():
    def col(nombre):
        return f"trim(string(coalesce(item()?['{nombre}'],'')))"
    sel = {"fila_excel": "@item()?['fila_excel']", "id_txt": "@" + col("deposito_id"), "clave": "@" + col("clave_transaccion"),
           "banco": "@" + col("banco"), "cuenta": "@" + col("cuenta_bancaria"), "codigo": "@" + col("codigo_asignacion"),
           "importe_txt": "@" + col("importe"), "moneda": f"@toUpper({col('moneda')})", "estudiante": "@" + col("estudiante"),
           "solicitado_por": "@" + col("solicitado_por"), "sede": "@" + col("sede"), "observacion": "@" + col("observacion")}
    return {"type": "Select", "inputs": {"from": "@outputs('Filas')", "select": sel}}


CAMPOS_TEXTO = ("fila_excel", "id_txt", "clave", "banco", "cuenta", "codigo", "importe_txt", "moneda", "estudiante", "solicitado_por",
                "sede", "observacion")
CAMPOS_FORMATO = CAMPOS_TEXTO + ("id_ok", "formato_ok")
CAMPOS_VALIDADAS = CAMPOS_FORMATO + ("centavos", "invalida")
OBLIGATORIOS = ("clave", "banco", "cuenta", "codigo", "moneda", "estudiante", "solicitado_por", "sede")


def filas_formato():
    s = it("importe_txt")
    ip = f"indexOf({s},'.')"
    sd = sin_digitos(s)
    ident = it("id_txt")
    formato = (f"@and(not(empty({s})),lessOrEquals(length({s}),15),or(equals({sd},''),and(equals({sd},'.'),greater({ip},0),"
               f"less({ip},sub(length({s}),1)),lessOrEquals(sub(length({s}),add({ip},1)),2))))")
    id_ok = f"@and(not(empty({ident})),lessOrEquals(length({ident}),9),equals({sin_digitos(ident)},''))"
    return {"type": "Select", "inputs": {"from": "@body('Filas_texto')",
                                         "select": {**pasar(CAMPOS_TEXTO), "id_ok": id_ok, "formato_ok": formato}}}


def filas_validadas():
    cent = centavos(it("importe_txt"))
    vacio = "or(" + ",".join(f"empty({it(c)})" for c in OBLIGATORIOS) + ")"
    largo = "or(" + ",".join(f"greater(length({it(c)}),255)" for c in OBLIGATORIOS + ("observacion",)) + ")"
    invalida = encadenar_if([
        (f"or(not({it('id_ok')}),if({it('id_ok')},equals(int({it('id_txt')}),0),false))", "'ID_INVALIDO'"),
        (vacio, "'CAMPOS_OBLIGATORIOS'"),
        (largo, "'CAMPO_EXCEDE_255'"),
        (f"not({it('formato_ok')})", "'IMPORTE_INVALIDO'"),
        (f"equals({cent},0)", "'IMPORTE_INVALIDO'"),
        ("not(or(" + ",".join(f"equals({it('moneda')},{lit(m)})" for m in MONEDAS) + "))", "'MONEDA_INVALIDA'")], "''")
    return {"type": "Select", "inputs": {"from": "@body('Filas_formato')", "select": {
        **pasar(CAMPOS_FORMATO),
        "centavos": f"@if({it('formato_ok')},{cent},0)",
        "invalida": "@" + invalida}}}


def detalle_invalidas():
    """Las filas que no cumplen el formato mínimo NO se procesan: ERROR_FILA, sin tocar SharePoint."""
    r = it
    return {"type": "Select", "inputs": {"from": "@body('Filas_invalidas')", "select": {
        "fila_excel": "@" + r("fila_excel"), "deposito_id": f"@if({r('id_ok')},int({r('id_txt')}),null)", "resultado": "ERROR_FILA",
        "mensaje": f"@concat('Fila inválida en los datos enviados (',{r('invalida')},'). No se aplicó ningún cambio.')", "estado_final": "",
        "banco": "@" + r("banco"), "cuenta_bancaria": "@" + r("cuenta"), "codigo_asignacion": "@" + r("codigo"),
        "importe": f"@if({r('formato_ok')},div(float({r('centavos')}),100.0),null)", "moneda": "@" + r("moneda")}}}


# ---------------------------------------------------------------------------------------------- por fila: releer, comparar, escribir
def uri_item():
    return ("@concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')','/items(',"
            f"{fila('id_txt')},')?$select={','.join(COLUMNAS_LECTURA)}')")


def uri_escritura():
    """Idéntica a la de V4.2 (`Actualizar_deposito`)."""
    return ("@concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')','/items(',"
            f"{fila('id_txt')},')')")


def leer_deposito():
    """Lectura FRESCA por ID (como V4.2: Accept odata=verbose → el ETag viene en d.__metadata.etag). Solo lectura: se permiten 2 reintentos
    ante errores transitorios (429/5xx); es la ÚNICA diferencia con V4.2, que no reintenta ni siquiera la lectura."""
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": {"dataset": "@outputs('PARAM_SITIO')", "parameters/method": "GET", "parameters/uri": uri_item(),
                       "parameters/headers": {"Accept": "application/json;odata=verbose"}},
        "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "fixed", "count": 2, "interval": "PT2S"}}}


def texto_deposito(campo):
    return f"toLower(trim(string(coalesce({d(campo)},''))))"


def cambio():
    """Primer dato relevante que NO coincide con lo prevalidado ('' si todo coincide). Orden: ID → CLAVE → ESTADO → resto."""
    dep_importe = centavos(f"string(coalesce({d('IMPORTE')},0))")
    fecha = f"take(string(coalesce({d('FECHA_MOVIMIENTO')},'')),10)"
    return encadenar_if([
        (f"not(equals(string(coalesce({d('Id')},{d('ID')},0)),{fila('id_txt')}))", "'ID'"),
        (f"not(equals(trim(string(coalesce({d('CLAVE_TRANSACCION')},''))),{fila('clave')}))", "'CLAVE_TRANSACCION'"),
        (f"not(equals(trim(string(coalesce({d('ESTADO_ASIGNACION')},''))),{lit(PV.ESTADO_DISPONIBLE)}))", "'ESTADO_ASIGNACION'"),
        (f"not(equals(trim(string(coalesce({d('TIPO_MOVIMIENTO')},''))),{lit(PV.TIPO_CREDITO)}))", "'TIPO_MOVIMIENTO'"),
        (f"or(less({fecha},outputs('Desde_local')),greater({fecha},outputs('Hoy_local')))", "'FECHA_MOVIMIENTO'"),
        (f"not(equals({texto_deposito('BANCO')},toLower({fila('banco')})))", "'BANCO'"),
        (f"not(equals({texto_deposito('CUENTA_BANCARIA')},toLower({fila('cuenta')})))", "'CUENTA_BANCARIA'"),
        (f"not(equals({texto_deposito('CODIGO_ASIGNACION')},toLower({fila('codigo')})))", "'CODIGO_ASIGNACION'"),
        (f"not(equals({dep_importe},{fila('centavos')}))", "'IMPORTE'"),
        (f"not(equals(toUpper(trim(string(coalesce({d('MONEDA')},'')))),{fila('moneda')}))", "'MONEDA'")], "''")


def revalidacion():
    campo = "outputs('Cambio')"
    estado = f"trim(string(coalesce({d('ESTADO_ASIGNACION')},'')))"
    etag = f"coalesce({d('__metadata')}?['etag'],outputs('Leer_deposito')?['headers']?['ETag'],'')"
    codigo = ("if(empty(" + campo + "),if(empty(outputs('ETag_fresco')),'ERROR_FILA','OK'),"
              f"if(equals({campo},'ESTADO_ASIGNACION'),'NO_DISPONIBLE','CONFLICTO_DATOS'))")
    return {"ETag_fresco": compose("@" + etag),
            "Revalidacion": compose({
                "codigo": "@" + codigo, "campo": "@" + campo, "estado": "@" + estado, "etag": "@outputs('ETag_fresco')"})}


def mensaje_no_confirmada():
    rv = "outputs('Revalidacion')"
    return ("@if(equals(" + rv + "?['codigo'],'NO_DISPONIBLE'),concat('El depósito ya no está DISPONIBLE (estado actual: ',"
            + rv + "?['estado'],'). No se aplicó ningún cambio.'),"
            "if(equals(" + rv + "?['codigo'],'CONFLICTO_DATOS'),concat('El depósito cambió desde la prevalidación (',"
            + rv + "?['campo'],'). No se aplicó ningún cambio.'),"
            "'SharePoint no devolvió el ETag del depósito; no se aplicó ningún cambio.'))")


def detalle(resultado, mensaje, estado_final):
    return {"fila_excel": "@" + fila("fila_excel"), "deposito_id": f"@int({fila('id_txt')})", "resultado": resultado, "mensaje": mensaje,
            "estado_final": estado_final, "banco": "@" + fila("banco"), "cuenta_bancaria": "@" + fila("cuenta"),
            "codigo_asignacion": "@" + fila("codigo"), "importe": f"@div(float({fila('centavos')}),100.0)", "moneda": "@" + fila("moneda")}


def agregar(valor):
    return {"type": "AppendToArrayVariable", "inputs": {"name": "varResultados", "value": valor}}


def actualizar_deposito():
    """MISMA llamada que V4.2: POST + X-HTTP-Method MERGE + IF-MATCH con el ETag FRESCO (nunca '*'), sin reintentos."""
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": {"dataset": "@outputs('PARAM_SITIO')", "parameters/method": "POST", "parameters/uri": uri_escritura(),
                       "parameters/headers": {"Accept": "application/json;odata=nometadata",
                                              "Content-Type": "application/json;odata=nometadata", "X-HTTP-Method": "MERGE",
                                              "IF-MATCH": "@outputs('Revalidacion')?['etag']"},
                       "parameters/body": "@string(outputs('Cuerpo_actualizacion'))"},
        "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "none"}}}


def cuerpo_actualizacion():
    """Los 8 campos de V4.2, con las mismas fuentes: CODIGO_ESTUDIANTE = '' (la app individual también lo envía vacío),
    OBSERVACION = texto recortado ('' si vacío, nunca null), USUARIO_ASIGNACION = el correo recibido, FECHA_HORA_ASIGNACION = utcNow()."""
    return compose({"ESTADO_ASIGNACION": "ASIGNADO", "ESTUDIANTE": "@" + fila("estudiante"), "CODIGO_ESTUDIANTE": "",
                    "SOLICITADO_POR": "@" + fila("solicitado_por"), "SEDE_ASIGNACION": "@" + fila("sede"),
                    "OBSERVACION": "@" + fila("observacion"), "USUARIO_ASIGNACION": "@outputs('Entrada')?['usuario']",
                    "FECHA_HORA_ASIGNACION": "@utcNow()"})


def captura_error_fila():
    """Cualquier fallo de la fila (HTTP no controlado, expresión, tiempo) se convierte en resultado de ESA fila y el bucle continúa."""
    fallo_escritura = "equals(actions('Actualizar_deposito')?['status'],'Failed')"
    fallo_lectura = "equals(actions('Leer_deposito')?['status'],'Failed')"
    http_e, http_l = "outputs('Actualizar_deposito')?['statusCode']", "outputs('Leer_deposito')?['statusCode']"
    resultado = encadenar_if([(f"and({fallo_escritura},equals({http_e},412))", "'CONFLICTO'"), (fallo_escritura, "'ERROR_FILA'"),
                              (f"and({fallo_lectura},equals({http_l},404))", "'NO_ENCONTRADO'")], "'ERROR_FILA'")
    mensaje = encadenar_if([
        (f"and({fallo_escritura},equals({http_e},412))", "'Otro usuario modificó el depósito mientras se confirmaba. No se aplicó tu confirmación.'"),
        (fallo_escritura, f"concat('No se pudo confirmar el depósito (HTTP ',string({http_e}),'). Verifique su estado con PREVALIDAR antes de reintentar.')"),
        (f"and({fallo_lectura},equals({http_l},404))", "'El depósito ya no existe en SharePoint. No se aplicó ningún cambio.'"),
        (fallo_lectura, f"concat('No se pudo leer el depósito (HTTP ',string({http_l}),'). No se aplicó ningún cambio.')")],
        "'Error inesperado al procesar la fila. Verifique el depósito con PREVALIDAR antes de reintentar.'")
    # tras un intento de escritura que falló y NO fue 412 no se sabe si SharePoint la aplicó: estado_final = DESCONOCIDO
    estado = f"if(and({fallo_escritura},not(equals({http_e},412))),'DESCONOCIDO','')"
    return secuencia(Agregar_error_fila=agregar(detalle("@" + resultado, "@" + mensaje, "@" + estado)))


def fila_scope():
    confirmar = secuencia(
        Cuerpo_actualizacion=cuerpo_actualizacion(),
        Actualizar_deposito=actualizar_deposito(),
        Agregar_confirmado=agregar(detalle("CONFIRMADO", "Depósito confirmado correctamente.", "ASIGNADO")))
    no_confirmar = secuencia(Agregar_no_confirmado=agregar(detalle(
        "@outputs('Revalidacion')?['codigo']", mensaje_no_confirmada(), "@outputs('Revalidacion')?['estado']")))
    return secuencia(
        Leer_deposito=leer_deposito(),
        Cambio=compose("@" + cambio()),
        **revalidacion(),
        Puede_confirmar=si("@equals(outputs('Revalidacion')?['codigo'],'OK')", confirmar, no_confirmar))


def bucle():
    return {"type": "Foreach", "foreach": "@body('Filas_a_procesar')", "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "actions": {
                "TRY_FILA": {**ambito(fila_scope()), "runAfter": {}},
                "CATCH_FILA": ambito(captura_error_fila(), {"TRY_FILA": FALLOS})}}


# ---------------------------------------------------------------------------------------------- flujo completo
def error_global(codigo, mensaje, nombre):
    return secuencia(**{f"{nombre}_codigo": asignar("varErrorCodigo", codigo), f"{nombre}_mensaje": asignar("varErrorMensaje", mensaje)})


def ejecutar_lote():
    return secuencia(
        Etapa_preparar=asignar("varEtapa", "PREPARAR"),
        Hoy_local=compose(f"@convertTimeZone(utcNow(),'UTC',{lit(PV.ZONA_HORARIA)},'yyyy-MM-dd')"),
        Desde_local=compose(f"@formatDateTime(addToTime(concat(outputs('Hoy_local'),'T00:00:00Z'),-{PV.MESES_VENTANA},'Month'),'yyyy-MM-dd')"),
        Filas_texto=filas_normalizadas(),
        Filas_formato=filas_formato(),
        Filas_validadas=filas_validadas(),
        Filas_a_procesar={"type": "Query", "inputs": {"from": "@body('Filas_validadas')", "where": "@empty(item()?['invalida'])"}},
        Filas_invalidas={"type": "Query", "inputs": {"from": "@body('Filas_validadas')", "where": "@not(empty(item()?['invalida']))"}},
        Resultados_invalidas=detalle_invalidas(),
        Cargar_invalidas=asignar("varResultados", "@body('Resultados_invalidas')"),
        Etapa_confirmar=asignar("varEtapa", "CONFIRMAR"),
        Para_cada_fila=bucle())


def procesar():
    return secuencia(
        Filas=compose("@json(outputs('Entrada')?['texto'])"),
        Total=compose("@length(outputs('Filas'))"),
        Guardar_recibidas=asignar("varRecibidas", "@string(outputs('Total'))"),
        Validar_lote=compose("@if(equals(outputs('Total'),0),'SIN_FILAS',if(greater(outputs('Total'),min(outputs('PARAM_MAX_FILAS_POR_LLAMADA'),"
                             "outputs('PARAM_MAX_FILAS_ARCHIVO'))),'LOTE_EXCEDE_LIMITE',''))"),
        Lote_valido=si("@empty(outputs('Validar_lote'))", ejecutar_lote(), secuencia(
            Error_de_lote=si(
                "@equals(outputs('Validar_lote'),'SIN_FILAS')",
                error_global("SIN_FILAS", "No hay filas VALIDO para confirmar. No se confirmó ningún depósito.", "Sin_filas"),
                error_global("LOTE_EXCEDE_LIMITE",
                             "@concat('Se enviaron ',string(outputs('Total')),' filas y el máximo por confirmación es ',"
                             "string(min(outputs('PARAM_MAX_FILAS_POR_LLAMADA'),outputs('PARAM_MAX_FILAS_ARCHIVO'))),"
                             "'. No se confirmó ningún depósito: divida la confirmación en partes más pequeñas.')", "Lote_excede")))))


def captura_global():
    return secuencia(Clasificar_fallo=si(
        "@equals(variables('varEtapa'),'ENTRADA')",
        error_global("ENTRADA_INVALIDA", "detalle_json no es un arreglo JSON válido. No se confirmó ningún depósito.", "Fallo_entrada"),
        error_global("ERROR_NO_CONTROLADO",
                     "El proceso se interrumpió antes de terminar: algunos depósitos pueden haberse confirmado. "
                     "Vuelva a PREVALIDAR para ver el estado real de cada uno antes de reintentar.", "Fallo_global")))


def construir_definicion(max_por_llamada=MAX_FILAS_POR_LLAMADA):
    acciones = secuencia(
        PARAM_SITIO=compose(SITIO),
        PARAM_LISTA_DEPOSITOS_ACTIVOS=compose(LISTA_ID),
        PARAM_MAX_FILAS_POR_LLAMADA=compose(max_por_llamada),
        PARAM_MAX_FILAS_ARCHIVO=compose(MAX_FILAS_ARCHIVO),
        Entrada=compose({"texto": "@trim(coalesce(triggerBody()?['text'],''))", "usuario": "@trim(coalesce(triggerBody()?['text_1'],''))"}),
        Inicializar_varT0=variable("varT0", "integer", "@ticks(utcNow())"),
        Inicializar_varEtapa=variable("varEtapa", "string", "ENTRADA"),
        Inicializar_varResultados=variable("varResultados", "array", []),
        Inicializar_varRecibidas=variable("varRecibidas", "string", "0"),
        Inicializar_varErrorCodigo=variable("varErrorCodigo", "string", ""),
        Inicializar_varErrorMensaje=variable("varErrorMensaje", "string", ""),
        Validar_entrada=compose("@if(or(empty(outputs('Entrada')?['texto']),empty(outputs('Entrada')?['usuario']),"
                                "greater(length(outputs('Entrada')?['usuario']),255),not(startsWith(outputs('Entrada')?['texto'],'['))),"
                                "'ENTRADA_INVALIDA','')"),
        TRY=ambito(secuencia(Entrada_valida=si(
            "@empty(outputs('Validar_entrada'))", procesar(),
            error_global("ENTRADA_INVALIDA", "Faltan detalle_json o usuario_email, o detalle_json no es un arreglo JSON. "
                                             "No se confirmó ningún depósito.", "Entrada_invalida")))))
    acciones["CATCH"] = ambito(captura_global(), {"TRY": FALLOS})
    # Resumen: SIEMPRE se calcula (éxito, error o interrupción), a partir de lo realmente anotado fila a fila
    acciones["Confirmadas"] = {"type": "Query", "inputs": {"from": "@variables('varResultados')", "where": "@equals(item()?['resultado'],'CONFIRMADO')"},
                               "runAfter": {"TRY": TODOS, "CATCH": TODOS}}
    acciones["Cuenta_confirmadas"] = {**compose("@length(body('Confirmadas'))"), "runAfter": {"Confirmadas": ["Succeeded"]}}
    acciones["Cuenta_recibidas"] = {**compose("@int(variables('varRecibidas'))"), "runAfter": {"Cuenta_confirmadas": ["Succeeded"]}}
    acciones["Tiempos"] = {**compose(
        "@concat('total=',string(div(sub(ticks(utcNow()),variables('varT0')),10000)),';filas=',variables('varRecibidas'),"
        "';ms_por_fila=',string(div(div(sub(ticks(utcNow()),variables('varT0')),10000),max(1,outputs('Cuenta_recibidas')))))"),
        "runAfter": {"Cuenta_recibidas": ["Succeeded"]}}
    conf, recib = "outputs('Cuenta_confirmadas')", "outputs('Cuenta_recibidas')"
    hay_error = "not(empty(variables('varErrorCodigo')))"
    todas = f"equals({conf},{recib})"
    cuerpo = {
        "resultado": f"@if({hay_error},'ERROR',if({todas},'OK','PARCIAL'))",
        "codigo": f"@if({hay_error},variables('varErrorCodigo'),if({todas},'{CODIGO_OK}',if(equals({conf},0),'{CODIGO_NINGUNA}','{CODIGO_PARCIAL}')))",
        "mensaje": (f"@if({hay_error},variables('varErrorMensaje'),concat(string({conf}),' de ',string({recib}),' depósitos confirmados',"
                    f"if({todas},'.',concat('; ',string(sub({recib},{conf})),' requieren revisión.'))))"),
        "filas_recibidas": "@variables('varRecibidas')", "filas_confirmadas": f"@string({conf})",
        "filas_no_confirmadas": f"@string(sub({recib},{conf}))", "detalle_json": "@string(variables('varResultados'))",
        "tiempos_ms": "@outputs('Tiempos')"}
    assert tuple(cuerpo) == SALIDAS
    esquema = {"type": "object", "properties": {k: {"title": k, "type": "string", "x-ms-dynamically-added": True} for k in SALIDAS}}
    acciones["Responder_a_PowerApps"] = {"type": "Response", "kind": "PowerApp", "runAfter": {"Tiempos": TODOS},
                                         "inputs": {"statusCode": 200, "body": cuerpo, "schema": esquema}}
    return definicion(disparador(), acciones)


# ---------------------------------------------------------------------------------------------- paquete ZIP
CONEXIONES = {"shared_sharepointonline": ("SharePoint", "sharepointonline")}
DESCRIPCION = ("PROTOTIPO: confirma, una por una y releyendo cada depósito (ETag fresco, If-Match), las filas VALIDO enviadas por Power Apps. "
               "Misma escritura que P9_ASIGNAR_DEPOSITO V4.2. Sin lotes persistentes ni rollback global.")


def generar():
    d_ = construir_definicion()
    (CARPETA_SALIDA / f"{NOMBRE_FLUJO}_definition.json").write_text(json.dumps(d_, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destino = CARPETA_SALIDA / f"{NOMBRE_FLUJO}.zip"
    destino.write_bytes(zip_bytes(d_))
    return destino, contar_acciones(d_["actions"])


def zip_bytes(definition):
    return BASE.zip_bytes(definition, nombre=NOMBRE_FLUJO, conexiones_flujo=CONEXIONES, descripcion=DESCRIPCION)


if __name__ == "__main__":
    ruta, n = generar()
    print(ruta, f"({n} acciones)")
