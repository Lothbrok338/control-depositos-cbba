"""Generador del flujo PROTOTIPO `P9_MASIVA_PROTO_CONFIRMAR` (confirmación masiva, hasta 1999 filas con UN clic) y de su ZIP importable.

    python -m proto_masiva.flows.construir_confirmar

Confirma SOLO las filas que Power Apps envía (las que la prevalidación dejó en VALIDO), UNA DETRÁS DE OTRA, con la MISMA semántica por fila que la
confirmación individual `P9_ASIGNAR_DEPOSITO` V4.2 (fuente de verdad: p9/asignar/flujo_asignar_powerapps_v4_2_definition.json):

  por fila:  releer el depósito por ID (GET, `$select`) → comprobar que NADA relevante cambió desde la prevalidación → tomar el ETag
             FRESCO de esa lectura → `POST` + `X-HTTP-Method: MERGE` + `IF-MATCH: <ETag>` (nunca `*`), sin reintentos, con los
             MISMOS 8 campos que V4.2 → 412 = CONFLICTO.   (Esta lógica NO cambió respecto de la V1 validada en el tenant.)

ARQUITECTURA (escala hasta 1999 con un solo clic, sin timeout de Power Apps):
  1. PREPARAR   valida la entrada, cuenta las filas y crea el estado temporal `confirmacion_<execution_uid>.json` (PROCESANDO) en Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP.
  2. RESPONDER  «Responder a Power Apps» con ACEPTADO + execution_uid: Power Apps recibe la respuesta en segundos (límite entrante de 120 s).
  3. PROCESAR   DESPUÉS de responder el flujo SIGUE ejecutándose (documentado por Microsoft: las acciones posteriores a la respuesta continúan más
                allá de ese límite; la duración máxima de una ejecución es de 30 días) y recorre las filas válidas, secuencial (concurrencia 1).
                Cada 25 filas actualiza el estado (solo contadores). Al terminar escribe TERMINADO con SOLO las filas no confirmadas.
  Power Apps consulta el avance con el flujo `P9_MASIVA_PROTO_ESTADO` (construir_estado.py). Si Power Apps se cierra, el backend continúa.

Sin rollback global: lo confirmado queda confirmado. Un error en una fila NO detiene a las demás. Sin listas ni historial de lotes: el estado es un
archivo JSON temporal por ejecución (no es historial; no se limpia automáticamente).

LÍMITE DE 131.072 CARACTERES: Microsoft limita `string()`, `concat()` y `base64()` a 131.072 caracteres. Por eso el estado NUNCA serializa la lista
de filas confirmadas: solo se guardan las no confirmadas, con un máximo de `MAX_DETALLE` entradas (el resto se cuenta, no se detalla).
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
CARPETA_ESTADO = BASE.CARPETA_TEMP              # "/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP": la MISMA carpeta técnica que usa la prevalidación (una sola constante)
PREFIJO_ESTADO = "confirmacion_"                # confirmacion_<execution_uid>.json

MAX_FILAS_ARCHIVO = 1999       # límite de negocio del archivo (la prevalidación rechaza 2000 o más)
MAX_FILAS_POR_LLAMADA = 1999   # antes 50 (síncrono). Ahora el flujo responde antes de procesar, así que el tope es el del archivo
INTERVALO_PROGRESO = 25        # filas entre actualizaciones del estado (no cada fila: cada actualización es una llamada a SharePoint)
MAX_DETALLE = 300              # entradas máximas de filas no confirmadas dentro del estado (límite de 131.072 caracteres de string())
LIMITE_STRING = 131072         # límite documentado de string()/concat()/base64() en Power Automate

ENTRADAS = (("text", "detalle_json", "Filas VALIDO de la prevalidación, como arreglo JSON (JSON(..., JSONFormat.Compact))"),
            ("text_1", "usuario_email", "Correo del usuario que confirma (User().Email), como en la confirmación individual"))
RESULTADOS_FILA = ("CONFIRMADO", "NO_ENCONTRADO", "NO_DISPONIBLE", "CONFLICTO", "CONFLICTO_DATOS", "ERROR_FILA")
# Respuesta TEMPRANA a Power Apps (5 textos)
SALIDAS = ("resultado", "codigo", "mensaje", "execution_uid", "filas_recibidas")
RESULTADOS_ACEPTACION = ("ACEPTADO", "ERROR")
CODIGO_ACEPTADO = "PROCESAMIENTO_INICIADO"
CODIGOS_ERROR = ("ENTRADA_INVALIDA", "SIN_FILAS", "LOTE_EXCEDE_LIMITE", "ERROR_ESTADO")
# Estado final del archivo (lo devuelve P9_MASIVA_PROTO_ESTADO)
ESTADOS = ("PROCESANDO", "TERMINADO", "ERROR")
RESULTADOS_GLOBALES = ("OK", "PARCIAL", "ERROR")   # lo deriva Power Apps del estado final (OK = todas; PARCIAL = alguna no; ERROR = interrumpido)
CODIGO_OK, CODIGO_PARCIAL, CODIGO_NINGUNA = "CONFIRMACION_OK", "CONFIRMACION_PARCIAL", "NINGUNA_CONFIRMADA"
CODIGO_INTERRUMPIDA = "ERROR_NO_CONTROLADO"
CODIGOS_ESTADO = (CODIGO_ACEPTADO, CODIGO_OK, CODIGO_PARCIAL, CODIGO_NINGUNA, CODIGO_INTERRUMPIDA)
CODIGOS = (CODIGO_ACEPTADO,) + CODIGOS_ERROR + (CODIGO_OK, CODIGO_PARCIAL, CODIGO_NINGUNA, CODIGO_INTERRUMPIDA)
CAMPOS_ESTADO = ("execution_uid", "estado", "codigo", "filas_totales", "filas_procesadas", "filas_confirmadas", "filas_no_confirmadas", "porcentaje",
                 "mensaje", "detalle_json", "detalle_truncado", "actualizado_utc", "tiempos_ms")
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


# Power Automate rechaza al importar (InvalidRetryPolicy) un intervalo fijo menor de 5 s: el rango permitido es PT5S..P1D.
INTERVALO_REINTENTO_LECTURA = "PT5S"


def leer_deposito():
    """Lectura FRESCA por ID (como V4.2: Accept odata=verbose → el ETag viene en d.__metadata.etag). Solo lectura: se permiten 2 reintentos
    (intervalo fijo de 5 s, el mínimo que admite Power Automate) ante errores transitorios (429/5xx); es la ÚNICA diferencia con V4.2, que no
    reintenta ni siquiera la lectura. El MERGE NO se reintenta nunca."""
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": {"dataset": "@outputs('PARAM_SITIO')", "parameters/method": "GET", "parameters/uri": uri_item(),
                       "parameters/headers": {"Accept": "application/json;odata=verbose"}},
        "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "fixed", "count": 2, "interval": INTERVALO_REINTENTO_LECTURA}}}


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
    """Anota una fila NO confirmada (solo las no confirmadas se guardan: las confirmadas se cuentan)."""
    return {"type": "AppendToArrayVariable", "inputs": {"name": "varFallidas", "value": valor}}


def incrementar(variable_):
    return {"type": "IncrementVariable", "inputs": {"name": variable_, "value": 1}}


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
    return secuencia(Agregar_error_fila=agregar(detalle("@" + resultado, "@" + mensaje, "@" + estado)),
                     Sumar_error_fila=incrementar("varNoConfirmadas"))


def fila_scope():
    confirmar = secuencia(
        Cuerpo_actualizacion=cuerpo_actualizacion(),
        Actualizar_deposito=actualizar_deposito(),
        Sumar_confirmada=incrementar("varConfirmadas"))
    no_confirmar = secuencia(
        Agregar_no_confirmado=agregar(detalle("@outputs('Revalidacion')?['codigo']", mensaje_no_confirmada(), "@outputs('Revalidacion')?['estado']")),
        Sumar_no_confirmada=incrementar("varNoConfirmadas"))
    return secuencia(
        Leer_deposito=leer_deposito(),
        Cambio=compose("@" + cambio()),
        **revalidacion(),
        Puede_confirmar=si("@equals(outputs('Revalidacion')?['codigo'],'OK')", confirmar, no_confirmar))


# ---------------------------------------------------------------------------------------------- estado temporal (archivo JSON por ejecución)
UID, TOTAL, PROC, CONF, NOCONF = ("variables('varUid')", "variables('varTotal')", "variables('varProcesadas')", "variables('varConfirmadas')",
                                  "variables('varNoConfirmadas')")
MS = "div(sub(ticks(utcNow()),variables('varT0')),10000)"
RETRY_ESTADO = {"type": "fixed", "count": 2, "interval": "PT5S"}   # escribir el estado es idempotente: se puede reintentar (el MERGE NO)


def tiempos():
    return f"@concat('total=',string({MS}),';filas=',string({TOTAL}),';ms_por_fila=',string(div({MS},max(1,{TOTAL}))))"


def estado_json(estado, codigo, mensaje, detalle=None, truncado=False):
    """Contenido del archivo de estado. Solo contadores y, al terminar, las filas NO confirmadas (como máximo MAX_DETALLE)."""
    cuerpo = {
        "execution_uid": "@" + UID, "estado": estado, "codigo": codigo, "filas_totales": "@" + TOTAL, "filas_procesadas": "@" + PROC,
        "filas_confirmadas": "@" + CONF, "filas_no_confirmadas": "@" + NOCONF,
        "porcentaje": f"@div(mul(100,{PROC}),max(1,{TOTAL}))", "mensaje": mensaje,
        "detalle_json": [] if detalle is None else detalle, "detalle_truncado": truncado, "actualizado_utc": "@utcNow()", "tiempos_ms": tiempos()}
    assert tuple(cuerpo) == CAMPOS_ESTADO
    return compose(cuerpo)


def _sp_estado(operacion, parametros, **extra):
    return BASE._sp(operacion, {"dataset": "@outputs('PARAM_SITIO')", **parametros}, **extra)


def escribir_estado(origen):
    return _sp_estado("UpdateFile", {"id": "@variables('varEstadoId')", "body": f"@string(outputs('{origen}'))"}, retryPolicy=RETRY_ESTADO)


# ---------------------------------------------------------------------------------------------- bucle por fila
def bucle():
    progreso = si(f"@equals(mod({PROC},outputs('PARAM_INTERVALO_PROGRESO')),0)", secuencia(
        Estado_progreso=estado_json("PROCESANDO", CODIGO_ACEPTADO,
                                    f"@concat(string({PROC}),' de ',string({TOTAL}),' procesados.')"),
        Escribir_progreso=escribir_estado("Estado_progreso")))
    return {"type": "Foreach", "foreach": "@body('Filas_a_procesar')", "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "actions": {
                "TRY_FILA": {**ambito(fila_scope()), "runAfter": {}},
                "CATCH_FILA": ambito(captura_error_fila(), {"TRY_FILA": FALLOS}),
                "Contar_procesada": {**incrementar("varProcesadas"), "runAfter": {"TRY_FILA": TODOS, "CATCH_FILA": TODOS}},
                "Progreso": {**progreso, "runAfter": {"Contar_procesada": ["Succeeded"]}}}}


# ---------------------------------------------------------------------------------------------- flujo completo
def error_global(codigo, mensaje, nombre):
    return secuencia(**{f"{nombre}_codigo": asignar("varErrorCodigo", codigo), f"{nombre}_mensaje": asignar("varErrorMensaje", mensaje)})


def preparar():
    """ANTES de responder: valida, cuenta, crea el estado. Trabajo mínimo (rápido): el procesamiento pesado va DESPUÉS de la respuesta."""
    con_estado = secuencia(
        Etapa_estado=asignar("varEtapa", "ESTADO"),
        Generar_uid=compose("@guid()"),
        Guardar_uid=asignar("varUid", "@string(outputs('Generar_uid'))"),
        Nombre_estado=compose(f"@concat({lit(PREFIJO_ESTADO)},variables('varUid'),'.json')"),
        Estado_inicial=estado_json("PROCESANDO", CODIGO_ACEPTADO, "Confirmación iniciada. Procesando los depósitos válidos."),
        Crear_estado=_sp_estado("CreateFile", {"folderPath": "@outputs('PARAM_CARPETA')", "name": "@outputs('Nombre_estado')",
                                               "body": "@string(outputs('Estado_inicial'))"}, retryPolicy={"type": "none"}),
        Guardar_id_estado=asignar("varEstadoId", "@string(body('Crear_estado')?['Id'])"))
    limite = "min(outputs('PARAM_MAX_FILAS_POR_LLAMADA'),outputs('PARAM_MAX_FILAS_ARCHIVO'))"
    return secuencia(Entrada_valida=si(
        "@empty(outputs('Validar_entrada'))",
        secuencia(
            Filas=compose("@json(outputs('Entrada')?['texto'])"),
            Total=compose("@length(outputs('Filas'))"),
            Guardar_total=asignar("varTotal", "@outputs('Total')"),
            Validar_lote=compose(f"@if(equals(outputs('Total'),0),'SIN_FILAS',if(greater(outputs('Total'),{limite}),'LOTE_EXCEDE_LIMITE',''))"),
            Lote_valido=si("@empty(outputs('Validar_lote'))", con_estado, secuencia(
                Error_de_lote=si(
                    "@equals(outputs('Validar_lote'),'SIN_FILAS')",
                    error_global("SIN_FILAS", "No hay filas VALIDO para confirmar. No se confirmó ningún depósito.", "Sin_filas"),
                    error_global("LOTE_EXCEDE_LIMITE",
                                 f"@concat('Se enviaron ',string(outputs('Total')),' filas y el máximo por confirmación es ',string({limite}),"
                                 "'. No se confirmó ningún depósito.')", "Lote_excede"))))),
        error_global("ENTRADA_INVALIDA", "Faltan detalle_json o usuario_email, o detalle_json no es un arreglo JSON. "
                                         "No se confirmó ningún depósito.", "Entrada_invalida")))


def captura_preparar():
    return secuencia(Clasificar_fallo=si(
        "@equals(variables('varEtapa'),'ESTADO')",
        error_global("ERROR_ESTADO", "No se pudo crear el registro de progreso en P9_MASIVA_TEMP. No se confirmó ningún depósito: "
                                     "vuelva a intentar.", "Fallo_estado"),
        error_global("ENTRADA_INVALIDA", "detalle_json no es un arreglo JSON válido. No se confirmó ningún depósito.", "Fallo_entrada")))


def responder():
    """UNA sola respuesta por ejecución, ANTES del procesamiento. ACEPTADO (+execution_uid) o ERROR (nada se confirmó)."""
    esquema = {"type": "object", "properties": {k: {"title": k, "type": "string", "x-ms-dynamically-added": True} for k in SALIDAS}}
    aceptado = {"resultado": "ACEPTADO", "codigo": CODIGO_ACEPTADO,
                "mensaje": f"@concat('Confirmación iniciada: ',string({TOTAL}),' depósitos en proceso.')",
                "execution_uid": "@" + UID, "filas_recibidas": f"@string({TOTAL})"}
    error = {"resultado": "ERROR", "codigo": "@variables('varErrorCodigo')", "mensaje": "@variables('varErrorMensaje')",
             "execution_uid": "", "filas_recibidas": f"@string({TOTAL})"}
    assert tuple(aceptado) == tuple(error) == SALIDAS

    def respuesta(cuerpo):
        return {"type": "Response", "kind": "PowerApp", "inputs": {"statusCode": 200, "body": cuerpo, "schema": esquema}}
    return si("@empty(variables('varErrorCodigo'))", {"Responder_aceptado": {**respuesta(aceptado), "runAfter": {}}},
              {"Responder_error": {**respuesta(error), "runAfter": {}}})


def preparar_procesamiento():
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
        Cargar_invalidas=asignar("varFallidas", "@body('Resultados_invalidas')"),
        Contar_invalidas_no_confirmadas=asignar("varNoConfirmadas", "@length(body('Resultados_invalidas'))"),
        Contar_invalidas_procesadas=asignar("varProcesadas", "@length(body('Resultados_invalidas'))"),
        Etapa_confirmar=asignar("varEtapa", "CONFIRMAR"))


def captura_procesamiento():
    return secuencia(
        Fallo_global_codigo=asignar("varErrorCodigo", CODIGO_INTERRUMPIDA),
        Fallo_global_mensaje=asignar("varErrorMensaje", "El proceso se interrumpió antes de terminar: algunos depósitos pueden haberse confirmado. "
                                                         "Vuelva a PREVALIDAR para ver el estado real de cada uno antes de reintentar."))


def finalizar():
    """Escribe el estado FINAL (TERMINADO o ERROR) con SOLO las filas no confirmadas (máximo MAX_DETALLE). Si string() no cupiera, respaldo mínimo."""
    hay_error = "not(empty(variables('varErrorCodigo')))"
    resumen = (f"concat(string({CONF}),' de ',string({TOTAL}),' depósitos confirmados',"
               f"if(equals({NOCONF},0),'.',concat('; ',string({NOCONF}),' requieren revisión.')))")
    codigo = (f"if({hay_error},variables('varErrorCodigo'),if(equals({NOCONF},0),'{CODIGO_OK}',if(equals({CONF},0),'{CODIGO_NINGUNA}','{CODIGO_PARCIAL}')))")
    final = estado_json("__ESTADO__", "@" + codigo, "@" + f"if({hay_error},variables('varErrorMensaje'),{resumen})",
                        detalle="@take(variables('varFallidas'),outputs('PARAM_MAX_DETALLE'))",
                        truncado="@greater(length(variables('varFallidas')),outputs('PARAM_MAX_DETALLE'))")
    final["inputs"]["estado"] = f"@if({hay_error},'ERROR','TERMINADO')"
    final["inputs"]["porcentaje"] = f"@if({hay_error},div(mul(100,{PROC}),max(1,{TOTAL})),100)"
    minimo = estado_json("__ESTADO__", "@" + codigo,
                         "@" + f"concat({resumen},' El detalle de las filas no confirmadas no se pudo guardar: vuelva a PREVALIDAR para verlas.')",
                         detalle=[], truncado=True)
    minimo["inputs"]["estado"] = final["inputs"]["estado"]
    minimo["inputs"]["porcentaje"] = final["inputs"]["porcentaje"]
    return secuencia(
        Estado_final=final,
        ESCRIBIR_FINAL=ambito(secuencia(Escribir_final=escribir_estado("Estado_final"))),
        ESCRIBIR_FINAL_RESPALDO=ambito(secuencia(Estado_final_minimo=minimo, Escribir_final_minimo=escribir_estado("Estado_final_minimo")),
                                       {"ESCRIBIR_FINAL": FALLOS}))


def procesar():
    return {
        "PROCESAR_PREPARACION": {**ambito(preparar_procesamiento()), "runAfter": {}},
        "PROCESAR_PREPARACION_CATCH": ambito(captura_procesamiento(), {"PROCESAR_PREPARACION": FALLOS}),
        "Para_cada_fila": {**bucle(), "runAfter": {"PROCESAR_PREPARACION": ["Succeeded"]}},
        "FINALIZAR": ambito(finalizar(), {"Para_cada_fila": TODOS, "PROCESAR_PREPARACION_CATCH": TODOS})}


def construir_definicion(max_por_llamada=MAX_FILAS_POR_LLAMADA, intervalo_progreso=INTERVALO_PROGRESO, max_detalle=MAX_DETALLE):
    acciones = secuencia(
        PARAM_SITIO=compose(SITIO),
        PARAM_LISTA_DEPOSITOS_ACTIVOS=compose(LISTA_ID),
        PARAM_CARPETA=compose(CARPETA_ESTADO),
        PARAM_MAX_FILAS_POR_LLAMADA=compose(max_por_llamada),
        PARAM_MAX_FILAS_ARCHIVO=compose(MAX_FILAS_ARCHIVO),
        PARAM_INTERVALO_PROGRESO=compose(intervalo_progreso),
        PARAM_MAX_DETALLE=compose(max_detalle),
        Entrada=compose({"texto": "@trim(coalesce(triggerBody()?['text'],''))", "usuario": "@trim(coalesce(triggerBody()?['text_1'],''))"}),
        Inicializar_varT0=variable("varT0", "integer", "@ticks(utcNow())"),
        Inicializar_varEtapa=variable("varEtapa", "string", "ENTRADA"),
        Inicializar_varFallidas=variable("varFallidas", "array", []),
        Inicializar_varTotal=variable("varTotal", "integer", 0),
        Inicializar_varProcesadas=variable("varProcesadas", "integer", 0),
        Inicializar_varConfirmadas=variable("varConfirmadas", "integer", 0),
        Inicializar_varNoConfirmadas=variable("varNoConfirmadas", "integer", 0),
        Inicializar_varUid=variable("varUid", "string", ""),
        Inicializar_varEstadoId=variable("varEstadoId", "string", ""),
        Inicializar_varErrorCodigo=variable("varErrorCodigo", "string", ""),
        Inicializar_varErrorMensaje=variable("varErrorMensaje", "string", ""),
        Validar_entrada=compose("@if(or(empty(outputs('Entrada')?['texto']),empty(outputs('Entrada')?['usuario']),"
                                "greater(length(outputs('Entrada')?['usuario']),255),not(startsWith(outputs('Entrada')?['texto'],'['))),"
                                "'ENTRADA_INVALIDA','')"),
        PREPARAR=ambito(preparar()))
    acciones["PREPARAR_CATCH"] = ambito(captura_preparar(), {"PREPARAR": FALLOS})
    acciones["RESPONDER"] = {**responder(), "runAfter": {"PREPARAR": TODOS, "PREPARAR_CATCH": TODOS}}
    # DESPUÉS de la respuesta el flujo SIGUE: solo si se aceptó (si hubo error de entrada, nada que procesar)
    acciones["PROCESAR"] = {**si("@empty(variables('varErrorCodigo'))", procesar()), "runAfter": {"RESPONDER": TODOS}}
    return definicion(disparador(), acciones)


# ---------------------------------------------------------------------------------------------- paquete ZIP
CONEXIONES = {"shared_sharepointonline": ("SharePoint", "sharepointonline")}
DESCRIPCION = ("PROTOTIPO: confirma, una por una y releyendo cada depósito (ETag fresco, If-Match), hasta 1999 filas VALIDO enviadas por Power Apps. "
               "Responde ACEPTADO enseguida y sigue procesando; el avance se consulta con P9_MASIVA_PROTO_ESTADO. "
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
