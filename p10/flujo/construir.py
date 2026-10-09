"""Generador de los flujos de P10-A.2 y de sus ZIP importables.

    python -m p10.flujo.construir

  P10_SINCRONIZAR_HISTORICO   el flujo del sincronizador (programado, 1 ejecución a la vez)
  P10_PROVISIONAR_CONTROL     botón de una sola vez: crea la lista `P10_Control` y su elemento LOCK (idempotente)

Power Automate SOLO orquesta: no normaliza, no compara movimientos ni arma Excel. Cada decisión sale de un POST al servicio
`p10-api` (Railway, sin estado) y cada archivo se lee/escribe en OneDrive. Un solo escritor lógico: el bloqueo con vigencia de `P10_Control`.

Límites de Power Automate respetados (y comprobados por tests): ≤ 500 acciones, anidamiento ≤ 8, nombres únicos, `secureData` solo en
acciones de conector/HTTP. Reglas de diseño que el árbol cumple:
  * el estado se escribe DESPUÉS del XLSX y el control DESPUÉS del estado (el control es la marca de confirmación);
  * un fallo técnico de un elemento (extracto, grupo, mes) no detiene a los demás: se anota y la ejecución termina en Failed;
  * el bloqueo se libera siempre;
  * un ciclo sin novedades gasta pocas acciones (el consumo diario de Power Automate es un límite real): nada se compone ni se
    inicializa que no haga falta, y los meses/grupos sin cambios no se leen.
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path

from p0.flujo import construir as P0
from p10.control_lista import CAMPOS_CONTROL, LISTA_CONTROL
from p9 import contrato as C9
from p9.wdl import FALLOS, TODOS, agregar, ambito, asignar, compose, contar_acciones, definicion, secuencia, si, variable

CARPETA_SALIDA = Path(__file__).resolve().parent
RAIZ = CARPETA_SALIDA.parents[1]
NOMBRE_SYNC = "P10_SINCRONIZAR_HISTORICO"
NOMBRE_PROV = "P10_PROVISIONAR_CONTROL"
ZIP_SYNC = "P10_SINCRONIZAR_HISTORICO_V1.zip"
ZIP_PROV = "P10_PROVISIONAR_CONTROL_V1.zip"

SEDE = P0.SEDE
MARCADOR_DOMINIO = "<PEGAR_DOMINIO_P10_RAILWAY>"
URL_API = "https://p10-api-production.up.railway.app"     # servicio p10-api desplegado en Railway (CONTROL-DEPOSITOS)
BASE = "/CONTROL_DEPOSITOS"
RUTA_TOKEN = f"{BASE}/P10_CONFIG/P10_API_TOKEN.txt"
PREFIJO_SERVIDOR = "/personal/gtorricot_univalle_edu/Documents"      # ruta del servidor de la biblioteca de OneDrive del sitio de P9
CARPETA_PROCESADOS = f"{BASE}/P0_EXTRACTOS/PROCESADOS"
MES_INICIO = "2026-09"                                               # primer mes que el ciclo completo mira en PROCESADOS
INTERVALO_MINUTOS = 15
HORAS_ACTIVAS = list(range(6, 23))                                   # 06:00–22:45 hora de Bolivia; el primer ciclo del día es el completo
MINUTOS_ZONA = "SA Western Standard Time"
AHORA = f"convertTimeZone(utcNow(),'UTC','{MINUTOS_ZONA}','yyyy-MM-ddTHH:mm:ss')"
SEGURO_TODO, SEGURO_ENTRADA, SEGURO_SALIDA = P0.SEGURO_TODO, P0.SEGURO_ENTRADA, P0.SEGURO_SALIDA
CON_FALLO = P0.CON_FALLO
API_SP = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
CONTROL = "body('Leer_control')?['d']?['results']"                   # filas de P10_Control leídas al inicio del ciclo


def L(texto):
    """Literal de texto WDL."""
    return "'" + str(texto).replace("'", "''") + "'"


# ---------------------------------------------------------------------------------------------- bloques básicos
def cada(fuente, acciones):
    return {"type": "Foreach", "foreach": fuente, "actions": acciones, "runtimeConfiguration": {"concurrency": {"repetitions": 1}}}


def con_ra(accion, **ra):
    """runAfter explícito: con_ra(accion, Otra=['Failed'])."""
    accion["runAfter"] = ra
    return accion


def sp(metodo, uri, cabeceras, cuerpo=None, seguro=None):
    """«Send an HTTP request to SharePoint» (conector estándar) contra el sitio donde vive Depositos_Activos. Sin reintentos."""
    parametros = {"dataset": C9.SITIO_SHAREPOINT, "parameters/method": metodo, "parameters/uri": uri, "parameters/headers": cabeceras}
    if cuerpo is not None:
        parametros["parameters/body"] = cuerpo
    a = {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": API_SP, "connectionName": "shared_sharepointonline", "operationId": "HttpRequest"},
        "parameters": parametros, "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "none"}}}
    if seguro:
        a["runtimeConfiguration"] = seguro
    return a


def _uri(base, sufijo):
    partes = [L(base)]
    for t in sufijo:
        partes.append(t[1] if isinstance(t, tuple) else L(t))
    return "@concat(" + ",".join(partes) + ")"


def uri_control(sufijo):
    """`_api/web/lists/getbytitle('P10_Control')<sufijo>`; sufijo: lista de trozos (str literal | ('x', expresión))."""
    return _uri(f"_api/web/lists/getbytitle('{LISTA_CONTROL}')", sufijo)


def lista_depositos(sufijo):
    return _uri(f"_api/web/lists(guid'{C9.LISTA_DEPOSITOS_ACTIVOS_ID}')", sufijo)


JSON_V = {"Accept": "application/json;odata=verbose"}
JSON_SIN = {"Accept": "application/json;odata=nometadata"}
JSON_ESCRIBIR = {"Accept": "application/json;odata=nometadata", "Content-Type": "application/json;odata=nometadata"}
MERGE = {**JSON_ESCRIBIR, "X-HTTP-Method": "MERGE", "IF-MATCH": "*"}


def api(ruta, cuerpo, reintentos=True, timeout="PT10M", seguro=SEGURO_TODO):
    """POST al servicio p10-api. El token sale del archivo P10_API_TOKEN.txt (acción `Leer_token`, salida segura)."""
    return {"type": "Http", "inputs": {
        "method": "POST", "uri": f"@concat(outputs('P')?['url_api'],{L('/p10/' + ruta)})",
        "headers": {"Content-Type": "application/json", "Authorization": "@concat('Bearer ',trim(base64ToString(body('Leer_token')?['$content'])))"},
        "body": cuerpo, "limit": {"timeout": timeout},
        "retryPolicy": {"type": "fixed", "count": 2, "interval": "PT30S"} if reintentos else {"type": "none"}},
        "runtimeConfiguration": seguro}


def fallar(motivo):
    """Provoca el fallo de la acción (expresión inválida a propósito) para que su Scope/Foreach lo vea como fallo técnico."""
    return compose(f"@int({L('FALLO_TECNICO_' + motivo)})")


def anotar(detalle_expr, **runafter):
    """Anota un fallo técnico (breve y sin datos bancarios). El número de fallos del ciclo es `length(varDetalles)`."""
    a = agregar("varDetalles", detalle_expr)
    if runafter:
        a["runAfter"] = runafter
    return a


od = P0.od


# ---------------------------------------------------------------------------------------------- lectura/escritura de archivos
def lectura_tolerante(pre, nombre, ruta, solo_404):
    """Lee un archivo de OneDrive; si no existe -> null. `solo_404`: cualquier otro error es un fallo técnico (no se confunde con «falta»)."""
    leer = pre + nombre + "_Leer"
    acciones = {pre + nombre + "_Probar": ambito(secuencia(**{leer: od("GetFileContentByPath", {"path": ruta, "inferContentType": False},
                                                                       seguro=SEGURO_SALIDA)}))}
    valor = compose(f"@if(equals(actions('{leer}')?['status'],'Succeeded'),body('{leer}')?['$content'],null)")
    valor["runAfter"] = {pre + nombre + "_Probar": TODOS}
    acciones[pre + nombre] = valor
    if solo_404:
        acciones[pre + nombre + "_Error"] = con_ra(si(
            f"@and(not(equals(actions('{leer}')?['status'],'Succeeded')),not(equals(outputs('{leer}')?['statusCode'],404)))",
            secuencia(**{pre + nombre + "_Fallo": fallar("LECTURA_" + nombre.upper())})), **{pre + nombre: ["Succeeded"]})
    return acciones


def escritura(pre, carpeta, nombre, ruta, b64):
    """Crea el archivo o, si existe, reemplaza su contenido (OneDrive «Update file» por id)."""
    meta = pre + "Meta"
    cuerpo = f"@base64ToBinary({b64})"
    return {
        pre + "Probar": ambito(secuencia(**{meta: od("GetFileMetadataByPath", {"path": ruta})})),
        pre + "Escribir": {"type": "If", "runAfter": {pre + "Probar": TODOS},
                           "expression": f"@equals(actions('{meta}')?['status'],'Succeeded')",
                           "actions": secuencia(**{pre + "Actualizar": od("UpdateFile", {"id": f"@body('{meta}')?['Id']", "body": cuerpo},
                                                                         seguro=SEGURO_ENTRADA)}),
                           "else": {"actions": secuencia(**{pre + "Crear": od("CreateFile", {"folderPath": carpeta, "name": nombre, "body": cuerpo},
                                                                              seguro=SEGURO_ENTRADA)})}}}


def upsert(pre, existe, item_id, cuerpo):
    """Escribe un elemento de P10_Control: MERGE por Id si existe, POST si no. Un único escritor (bloqueo lógico)."""
    return si(f"@{existe}", secuencia(**{pre + "Actualizar": sp(
        "POST", uri_control(["/items(", ("x", f"string({item_id})"), ")"]), MERGE, f"@string({cuerpo})")}), secuencia(**{pre + "Crear": sp(
        "POST", uri_control(["/items"]), JSON_ESCRIBIR, f"@string({cuerpo})")}))


# ---------------------------------------------------------------------------------------------- bloque de grupo (único para extractos y meses)
def bloque_grupo(pre, valor_varG, leer_xlsx, encolar_conciliacion=False):
    """
    Sincroniza UN grupo (BANCO+CUENTA+MONEDA+MES). Entrada: `varG` = {grupo_id, rutas, parciales, filas, verificar_xlsx, finalizar}.
    Orden de escritura: XLSX -> estado -> control. Un fallo técnico se anota, marca varGrupoOk=false y no toca el control.
    `leer_xlsx`: solo la conciliación verifica el XLSX existente (los caminos de extractos y de delta no lo leen).
    `encolar_conciliacion`: si el estado del grupo cambió, su BANCO+MES se concilia con la lista completa más adelante en el mismo ciclo.
    """
    def G(campo):
        return f"variables('varG')?['{campo}']"

    def R(campo):
        return f"variables('varG')?['rutas']?['{campo}']"

    def n(x):
        return pre + x

    resp = n("Sync")
    ok = f"and(equals(outputs('{resp}')?['statusCode'],200),equals(body('{resp}')?['ok'],true))"
    filtro = "concat('CLAVE_CONTROL eq ''',concat('GRUPO|'," + G("grupo_id") + "),'''')"
    acciones = {
        n("Control_GET"): sp("GET", uri_control(["/items?$top=1&$filter=", ("x", f"uriComponent({filtro})")]), JSON_V),
        n("Control"): compose(f"@first(body('{n('Control_GET')}')?['d']?['results'])"),
        **lectura_tolerante(pre, "Estado", "@" + R("ruta_estado"), True),
        **(lectura_tolerante(pre, "Xlsx", "@" + R("ruta_xlsx"), False) if leer_xlsx else {}),
        resp: api("sincronizar", {
            "sede": "@outputs('P')?['sede']", "grupo_id": "@" + G("grupo_id"), "ahora_local": "@" + AHORA,
            "estado_base64": f"@outputs('{n('Estado')}')", "parciales_base64": "@" + G("parciales"), "filas": "@" + G("filas"),
            "control_grupo": f"@outputs('{n('Control')}')", "verificar_xlsx": "@" + G("verificar_xlsx"),
            "xlsx_actual_base64": f"@outputs('{n('Xlsx')}')" if leer_xlsx else None,
            "finalizar": "@" + G("finalizar"), "parcial_lista": "@" + G("parcial_lista")}),
        n("Escribir_XLSX"): si(f"@and({ok},not(empty(body('{resp}')?['xlsx_b64'])))", secuencia(**escritura(
            n("X_"), "@" + R("carpeta_xlsx"), "@" + R("nombre_xlsx"), "@" + R("ruta_xlsx"), f"body('{resp}')?['xlsx_b64']"))),
        n("Escribir_ESTADO"): si(f"@and({ok},not(empty(body('{resp}')?['estado_b64'])))", secuencia(**escritura(
            n("E_"), "@" + R("carpeta_estado"), "@" + R("nombre_estado"), "@" + R("ruta_estado"), f"body('{resp}')?['estado_b64']"))),
        n("Guardar_CONTROL"): si(f"@and(equals(outputs('{resp}')?['statusCode'],200),coalesce(body('{resp}')?['escribir_control'],true))",
                                 secuencia(**{n("Control_Upsert"): upsert(
            n("Ctl_"), f"not(empty(outputs('{n('Control')}')))", f"outputs('{n('Control')}')?['Id']", f"body('{resp}')?['control']")})),
        **({n("Encolar_conciliacion"): si(f"@and({ok},equals(body('{resp}')?['cambio_estado'],true))", secuencia(**{n("Encolar"): agregar(
            "varSlices", {"periodo": "@split(" + G("grupo_id") + ",'|')[3]", "banco": "@split(" + G("grupo_id") + ",'|')[0]"})}))}
           if encolar_conciliacion else {}),
        n("Revisar_resultado"): si(f"@or(not({ok}),not(equals(body('{resp}')?['xlsx_valido'],true)))", secuencia(**{
            n("Fijar_no_ok"): asignar("varGrupoOk", False),
            n("Anotar"): anotar("@concat('GRUPO '," + G("grupo_id") + f",': ',coalesce(body('{resp}')?['codigo_error'],'XLSX_NO_VALIDO'))")})),
    }
    acciones = secuencia(**acciones)          # se encadenan con Succeeded: un fallo técnico salta al CATCH
    acciones[n("Control_GET")]["runAfter"] = {}
    catch = ambito(secuencia(**{
        n("Fijar_no_ok_catch"): asignar("varGrupoOk", False),
        n("Anotar_catch"): anotar("@concat('GRUPO '," + G("grupo_id") + ",': fallo técnico')")}), {n("TRY"): FALLOS})
    fijar = asignar("varG", valor_varG)
    fijar["runAfter"] = {}
    return {n("Fijar_varG"): fijar, n("TRY"): con_ra(ambito(acciones), **{n("Fijar_varG"): ["Succeeded"]}), n("CATCH"): catch}


# ---------------------------------------------------------------------------------------------- disparador
def disparador():
    return {"Cada_15_minutos": {
        "type": "Recurrence",
        "recurrence": {"frequency": "Day", "interval": 1, "timeZone": MINUTOS_ZONA,
                       "schedule": {"hours": [str(h) for h in HORAS_ACTIVAS], "minutes": list(range(0, 60, INTERVALO_MINUTOS))}},
        "runtimeConfiguration": {"concurrency": {"runs": 1, "maximumWaitingRuns": 1}}}}


# ---------------------------------------------------------------------------------------------- FASE A: extractos nuevos
def fase_extractos():
    """Pasos de la fase A en orden (sin runAfter entre ellos: los encadena `construir_sync`)."""
    F = "string(coalesce(item()?['Files'],createArray()))"
    uri = ("@concat('_api/web/GetFolderByServerRelativeUrl(''',outputs('P')?['prefijo_servidor'],'" + CARPETA_PROCESADOS +
           "/',substring(items('Cada_mes_listar'),0,4),'/',outputs('P')?['meses']?[substring(items('Cada_mes_listar'),5,2)],"
           "''')/Folders?$expand=Files&$select=Name,Files/Name,Files/ServerRelativeUrl,Files/Length,Files/TimeCreated')")
    listar = secuencia(
        Listar_dias=sp("GET", uri, JSON_SIN),
        Aplanar_1={"type": "Select", "inputs": {"from": "@body('Listar_dias')?['value']",
                                                "select": f"@substring({F},1,sub(length({F}),2))"}},
        Aplanar_2={"type": "Query", "inputs": {"from": "@body('Aplanar_1')", "where": "@greater(length(item()),0)"}},
        Unir=compose("@union(variables('varArchivos'),json(concat('[',join(body('Aplanar_2'),','),']')))"),
        Fijar_varArchivos=asignar("varArchivos", "@outputs('Unir')"))
    # 404 = el mes aún no tiene carpeta en PROCESADOS (normal); cualquier otro fallo se anota
    listar["Si_listado_fallo"] = {"type": "If", "runAfter": {"Listar_dias": FALLOS},
                                  "expression": "@not(equals(outputs('Listar_dias')?['statusCode'],404))",
                                  "actions": {"Anotar_listado": anotar("@concat('Listado de PROCESADOS ',items('Cada_mes_listar'))")},
                                  "else": {"actions": {}}}
    por_extracto = secuencia(
        E_Leer=od("GetFileContentByPath", {"path": "@items('Cada_extracto')?['ruta']", "inferContentType": False}, seguro=SEGURO_SALIDA),
        E_Reiniciar=asignar("varGrupoOk", True),
        E_Procesar=api("extracto", {
            "sede": "@outputs('P')?['sede']", "nombre_archivo": "@items('Cada_extracto')?['nombre']",
            "ruta": "@items('Cada_extracto')?['ruta']", "ahora_local": "@" + AHORA,
            "intentos": "@items('Cada_extracto')?['intentos']", "contenido_base64": "@body('E_Leer')?['$content']"}),
        Cada_grupo_E=cada(
            "@if(and(equals(outputs('E_Procesar')?['statusCode'],200),equals(body('E_Procesar')?['ok'],true)),"
            "body('E_Procesar')?['grupos'],createArray())",
            bloque_grupo("GE_", {"grupo_id": "@items('Cada_grupo_E')?['grupo_id']", "rutas": "@items('Cada_grupo_E')?['rutas']",
                                 "parciales": "@createArray(items('Cada_grupo_E')?['parcial_b64'])", "filas": None,
                                 "verificar_xlsx": False, "finalizar": False, "parcial_lista": False}, False, True)),
        E_Anotar=si(
            "@and(equals(outputs('E_Procesar')?['statusCode'],200),or(not(equals(body('E_Procesar')?['ok'],true)),variables('varGrupoOk')))",
            secuencia(E_Ledger=upsert("E_Led_", "greater(coalesce(items('Cada_extracto')?['item_id'],0),0)",
                                      "items('Cada_extracto')?['item_id']", "body('E_Procesar')?['control']"))))
    por_extracto["E_Falla_lectura"] = anotar("@concat('EXTRACTO ',items('Cada_extracto')?['nombre'],': no se pudo leer')", E_Leer=FALLOS)
    por_extracto["E_Falla_proceso"] = anotar("@concat('EXTRACTO ',items('Cada_extracto')?['nombre'],': el servicio no respondió')",
                                             E_Procesar=FALLOS)
    return dict(
        Cada_mes_listar=cada("@body('Ciclo_API')?['meses_listar']", listar),
        Plan=api("plan", {"ahora_local": "@" + AHORA, "modo": "@body('Ciclo_API')?['modo']", "archivos": "@variables('varArchivos')",
                          "control": "@" + CONTROL, "prefijo_servidor": "@outputs('P')?['prefijo_servidor']",
                          "limite": "@body('Ciclo_API')?['limite_extractos']"}),
        Cada_extracto=cada("@if(equals(body('Plan')?['ok'],true),body('Plan')?['extractos'],createArray())", por_extracto))


# ---------------------------------------------------------------------------------------------- FASE B: Depositos_Activos
def rango_mes(periodo):
    """Ventana del mes con un día de holgura a cada lado (la fecha de movimiento es «solo fecha»; el grupo lo decide la CLAVE)."""
    base = f"concat({periodo},'-01T00:00:00Z')"
    ini = f"concat(formatDateTime(addDays({base},-1),'yyyy-MM-dd'),'T00:00:00Z')"
    fin = f"concat(formatDateTime(addDays(startOfMonth(addDays({base},32)),1),'yyyy-MM-dd'),'T00:00:00Z')"
    return ini, fin


def filtro_banco_mes(banco, periodo):
    ini, fin = rango_mes(periodo)
    return (f"uriComponent(concat('BANCO eq ''',replace({banco},'''',''''''),''' and FECHA_MOVIMIENTO ge datetime''',{ini},"
            f"''' and FECHA_MOVIMIENTO lt datetime''',{fin},''''))")


def fase_lista(campos_select):
    """
    B1 (todos los ciclos): lectura INCREMENTAL de Depositos_Activos: solo las filas con Modified >= cursor (un GET; vacío casi siempre).
    B2: conciliación de BANCO+MES con la lista completa (noche, grupos con error o en reconstrucción, y tras cada cambio de extracto).
    """
    sel = f"/items?$select={campos_select}&$top=5000&$filter="
    ctl_d = "body('D_Control_GET')?['d']?['results']"
    fijar_d = {"grupo_id": "@items('Cada_sucio_D')?['grupo_id']", "rutas": "@items('Cada_sucio_D')?['rutas']", "parciales": "@createArray()",
               "filas": "@items('Cada_sucio_D')?['filas']", "verificar_xlsx": False, "finalizar": False, "parcial_lista": True}
    dentro = secuencia(
        D_Control_GET=sp("GET", uri_control(["/items?$top=5000"]), JSON_V),
        D_Clasificar=api("delta", {"ahora_local": "@" + AHORA, "items": "@body('D_GET')?['value']", "control": "@" + ctl_d,
                                   "cursor_desde": "@body('Ciclo_API')?['cursor_desde']"}),
        D_Reiniciar=asignar("varGrupoOk", True),
        Cada_sucio_D=cada("@if(equals(body('D_Clasificar')?['ok'],true),body('D_Clasificar')?['sucios'],createArray())",
                          bloque_grupo("GD_", fijar_d, False)),
        D_Cursor=si("@and(variables('varGrupoOk'),not(empty(body('D_Clasificar')?['cursor_nuevo'])))", secuencia(Fijar_cursor=sp(
            "POST", uri_control(["/items(", ("x", "string(body('Ciclo_API')?['lock']?['item_id'])"), ")"]), MERGE,
            "@concat('{\"CURSOR_LISTA\":\"',body('D_Clasificar')?['cursor_nuevo'],'\"}')"))))
    leer_d = sp("GET", lista_depositos([sel.replace(f"/items?$select={campos_select}&$top=5000&$filter=",
                                                    f"/items?$select={campos_select}&$orderby=Modified&$top=5000&$filter="),
                                        ("x", "uriComponent(concat('Modified gt datetime''',body('Ciclo_API')?['cursor_desde'],''''))")]),
                JSON_SIN, seguro=SEGURO_SALIDA)
    delta_acc = secuencia(
        D_GET=leer_d,
        D_Hay_cambios=si("@greater(length(body('D_GET')?['value']),0)", dentro))
    delta_acc["D_Falla_lectura"] = anotar("@concat('Lectura incremental de Depositos_Activos: no se pudo leer')", D_GET=FALLOS)

    s = "items('Cada_slice')"
    ctl_s = "body('S_Control_GET')?['d']?['results']"
    fijar_s = {"grupo_id": "@items('Cada_sucio_S')?['grupo_id']", "rutas": "@items('Cada_sucio_S')?['rutas']", "parciales": "@createArray()",
               "filas": "@items('Cada_sucio_S')?['filas']", "verificar_xlsx": "@items('Cada_sucio_S')?['verificar_xlsx']",
               "finalizar": "@items('Cada_sucio_S')?['finalizar']", "parcial_lista": False}
    por_slice = secuencia(
        S_Control_GET=sp("GET", uri_control(["/items?$top=5000"]), JSON_V),
        S_Items=sp("GET", lista_depositos([f"/items?$select={campos_select}&$orderby=Id&$top=5000&$filter=",
                                           ("x", filtro_banco_mes(s + "?['banco']", s + "?['periodo']"))]), JSON_SIN, seguro=SEGURO_SALIDA),
        S_Clasificar=api("clasificar", {
            "periodo": f"@{s}?['periodo']", "banco": f"@{s}?['banco']", "items": "@body('S_Items')?['value']", "control": "@" + ctl_s,
            "modo": "@body('Ciclo_API')?['modo']", "hay_mas": "@not(empty(body('S_Items')?['odata.nextLink']))",
            "verificar": "@body('Ciclo_API')?['grupos_a_verificar']"}),
        S_Reiniciar=asignar("varGrupoOk", True),
        Cada_sucio_S=cada("@if(equals(body('S_Clasificar')?['ok'],true),body('S_Clasificar')?['sucios'],createArray())",
                          bloque_grupo("GM_", fijar_s, True)))
    por_slice["S_Falla_lectura"] = anotar(f"@concat('Conciliación {{',{s}?['banco'],' ',{s}?['periodo'],'}}: no se pudo leer')",
                                          S_Control_GET=FALLOS, S_Items=FALLOS)
    por_slice["S_Falla_servicio"] = anotar(f"@concat('Conciliación {{',{s}?['banco'],' ',{s}?['periodo'],'}}: el servicio no respondió')",
                                           S_Clasificar=FALLOS)
    por_slice["S_Rechazo"] = con_ra(si("@not(equals(body('S_Clasificar')?['ok'],true))", {"Anotar_rechazo": anotar(
        f"@concat('Conciliación {{',{s}?['banco'],' ',{s}?['periodo'],'}}: ',coalesce(body('S_Clasificar')?['codigo_error'],'rechazada'))")}),
        S_Clasificar=["Succeeded"])
    return dict(**delta_acc, Cada_slice=con_ra(cada("@union(body('Ciclo_API')?['slices'],variables('varSlices'))", por_slice),
                                              D_Hay_cambios=TODOS))


# ---------------------------------------------------------------------------------------------- flujo principal
def construir_sync(campos_select):
    main = secuencia(**fase_extractos(), **fase_lista(campos_select))
    item_lock = "string(body('Ciclo_API')?['lock']?['item_id'])"
    termina = lambda estado, **extra: {"type": "Terminate", "inputs": {"runStatus": estado, **extra}}  # noqa: E731
    acciones = secuencia(
        P=compose({"sede": SEDE, "url_api": URL_API, "prefijo_servidor": PREFIJO_SERVIDOR, "mes_inicio": MES_INICIO, "meses": P0.MESES}),
        Inicializar_varDetalles=variable("varDetalles", "array", []),
        Inicializar_varArchivos=variable("varArchivos", "array", []),
        Inicializar_varSlices=variable("varSlices", "array", []),
        Inicializar_varGrupoOk=variable("varGrupoOk", "boolean", True),
        Inicializar_varG=variable("varG", "object", {}),
        Leer_token=od("GetFileContentByPath", {"path": RUTA_TOKEN, "inferContentType": False}, seguro=SEGURO_SALIDA),
        Leer_control=sp("GET", uri_control(["/items?$top=5000"]), JSON_V),
        Ciclo_API=api("ciclo", {"ahora_local": "@" + AHORA, "control": "@" + CONTROL, "mes_inicio": "@outputs('P')?['mes_inicio']",
                                "control_incompleto": "@not(empty(body('Leer_control')?['d']?['__next']))"}),
        Ciclo_no_continua=si(
            "@not(and(equals(body('Ciclo_API')?['ok'],true),body('Ciclo_API')?['lock']?['libre']))",
            secuencia(Motivo=si("@equals(body('Ciclo_API')?['ok'],true)",
                                secuencia(Terminar_ocupado=termina("Succeeded")),      # otra ejecución vigente: este ciclo no hace nada
                                secuencia(Terminar_ciclo_invalido=termina("Failed", runError={
                                    "code": "@coalesce(body('Ciclo_API')?['codigo_error'],'CICLO_INVALIDO')",
                                    "message": "@coalesce(body('Ciclo_API')?['mensaje'],'El servicio p10-api no devolvió un ciclo válido.')"}))))))
    acciones["Adquirir_lock"] = con_ra(ambito(secuencia(Tomar_lock=sp(
        "POST", uri_control(["/items(", ("x", item_lock), ")"]),
        {**JSON_ESCRIBIR, "X-HTTP-Method": "MERGE", "IF-MATCH": "@body('Ciclo_API')?['lock']?['etag']"},
        "@concat('{\"LOCK_HASTA\":\"',body('Ciclo_API')?['lock']?['hasta_nuevo'],'\",\"LOCK_ID\":\"',workflow()?['run']?['name'],'\"}')"))),
        Ciclo_no_continua=["Succeeded"])
    acciones["Lock_perdido"] = con_ra(termina("Succeeded"), Adquirir_lock=FALLOS)     # otra ejecución tomó el bloqueo primero
    acciones["MAIN"] = con_ra(ambito(main), Adquirir_lock=["Succeeded"])
    acciones["CATCH_MAIN"] = con_ra(ambito({"Anotar_general": anotar(
        "@concat('Fallo general del ciclo: ',take(coalesce(actions('MAIN')?['error']?['message'],'ver historial'),200))")}), MAIN=FALLOS)
    marcar = ("if(and(equals(body('Ciclo_API')?['modo'],'COMPLETO'),equals(actions('MAIN')?['status'],'Succeeded'),equals(length(variables('varDetalles')),0)),"
              "concat('{\"LOCK_HASTA\":\"\",\"LOCK_ID\":\"\",\"ULTIMA_COMPLETA\":\"',body('Ciclo_API')?['hoy'],'\"}'),"
              "'{\"LOCK_HASTA\":\"\",\"LOCK_ID\":\"\"}')")
    acciones["Liberar_lock"] = con_ra(sp("POST", uri_control(["/items(", ("x", item_lock), ")"]), MERGE, "@" + marcar), MAIN=TODOS, CATCH_MAIN=TODOS)
    acciones["Cierre"] = con_ra(si("@greater(length(variables('varDetalles')),0)", secuencia(Terminar_con_errores=termina("Failed", runError={
        "code": "P10_CICLO_CON_ERRORES",
        "message": "@concat(string(length(variables('varDetalles'))),' fallo(s): ',take(join(variables('varDetalles'),'; '),600))"}))),
        Liberar_lock=TODOS)
    return acciones


def construir_definicion_sync():
    from p10.sharepoint import CAMPOS_SELECT
    return definicion(disparador(), construir_sync(CAMPOS_SELECT))


# ---------------------------------------------------------------------------------------------- provisión de la lista P10_Control
def campo_xml(nombre, tipo, medida):
    attrs = f'Type="{tipo}" DisplayName="{nombre}" Name="{nombre}" StaticName="{nombre}"'
    if tipo == "Text":
        attrs += f' MaxLength="{medida}"'
    elif tipo == "Number":
        attrs += f' Decimals="{medida}"'
    else:
        attrs += ' NumLines="6" RichText="FALSE" AppendOnly="FALSE"'
    return f"<Field {attrs} />"


def construir_definicion_prov():
    lista = f"_api/web/lists/getbytitle('{LISTA_CONTROL}')"
    campos = []
    for nombre, tipo, medida, indexada, unica in CAMPOS_CONTROL:
        campos.append({"nombre": nombre, "indexada": indexada, "unica": unica, "crear": {
            "parameters": {"__metadata": {"type": "SP.XmlSchemaFieldCreationInformation"}, "SchemaXml": campo_xml(nombre, tipo, medida),
                           "Options": 9}}})

    def h(metodo, uri, cuerpo=None, merge=False, verbose=True):
        cab = {"Accept": "application/json;odata=nometadata"}
        if cuerpo is not None:
            cab["Content-Type"] = "application/json;odata=verbose" if verbose else "application/json;odata=nometadata"
        if merge:
            cab["X-HTTP-Method"] = "MERGE"
        return sp(metodo, uri, cab, cuerpo)

    le = lista.replace("'", "''")                      # la ruta va dentro de un literal WDL entre comillas simples
    campo_uri = "@concat('" + le + "/fields/getbyinternalnameortitle(''',items('Cada_campo')?['nombre'],''')')"
    por_campo = secuencia(
        Buscar_campo=h("GET", "@concat('" + le + "/fields?$select=InternalName&$filter=InternalName eq ''',items('Cada_campo')?['nombre'],'''')"),
        Crear_si_falta=si("@equals(length(body('Buscar_campo')?['value']),0)", secuencia(Crear_campo=h(
            "POST", lista + "/fields/createfieldasxml", "@string(items('Cada_campo')?['crear'])"))),
        Indexar=si("@items('Cada_campo')?['indexada']", secuencia(Indexar_campo=h(
            "POST", campo_uri, '{"__metadata":{"type":"SP.Field"},"Indexed":true}', merge=True))),
        Unicidad=si("@items('Cada_campo')?['unica']", secuencia(Exigir_unicidad=h(
            "POST", campo_uri, '{"__metadata":{"type":"SP.Field"},"EnforceUniqueValues":true}', merge=True))))
    acciones = secuencia(
        PARAM_SITIO_SHAREPOINT=compose(C9.SITIO_SHAREPOINT),
        Campos_del_contrato=compose(campos),
        Buscar_lista=h("GET", f"_api/web/lists?$select=Id,Title&$filter=Title eq '{LISTA_CONTROL}'"),
        Crear_lista_si_falta=si("@equals(length(body('Buscar_lista')?['value']),0)", secuencia(Crear_lista=h(
            "POST", "_api/web/lists", json.dumps({"__metadata": {"type": "SP.List"}, "Title": LISTA_CONTROL, "BaseTemplate": 100,
                                                  "ContentTypesEnabled": False})))),
        Liberar_Title=h("POST", f"{lista}/fields/getbyinternalnameortitle('Title')",
                        '{"__metadata":{"type":"SP.FieldText"},"Required":false}', merge=True),
        Cada_campo=cada("@outputs('Campos_del_contrato')", por_campo),
        Buscar_LOCK=h("GET", f"{lista}/items?$select=Id&$filter=CLAVE_CONTROL eq 'LOCK'"),
        Crear_LOCK_si_falta=si("@equals(length(body('Buscar_LOCK')?['value']),0)", secuencia(Crear_LOCK=h(
            "POST", f"{lista}/items", json.dumps({"CLAVE_CONTROL": "LOCK", "TIPO": "LOCK", "LOCK_HASTA": "", "LOCK_ID": "", "ULTIMA_COMPLETA": ""}),
            verbose=False))),
        Campos_finales=h("GET", f"{lista}/fields?$select=InternalName,Indexed,EnforceUniqueValues&$filter=Hidden eq false&$top=500"),
        Faltantes={"type": "Query", "inputs": {
            "from": "@outputs('Campos_del_contrato')",
            "where": "@not(contains(string(body('Campos_finales')?['value']),concat('\"InternalName\":\"',item()?['nombre'],'\"')))"}},
        Resultado=compose({"PROVISION_P10_CONTROL": "@if(equals(length(body('Faltantes')),0),'OK','FAIL')",
                           "campos_faltantes": "@body('Faltantes')", "lista": LISTA_CONTROL}),
        Finalizar=si("@equals(length(body('Faltantes')),0)", secuencia(Terminar_OK={"type": "Terminate", "inputs": {"runStatus": "Succeeded"}}),
                     secuencia(Terminar_FAIL={"type": "Terminate", "inputs": {"runStatus": "Failed", "runError": {
                         "code": "PROVISION_P10_CONTROL_FAIL", "message": "Faltan columnas en P10_Control; ver el elemento Resultado."}}})))
    trigger = {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": {}}},
                          "runtimeConfiguration": {"concurrency": {"runs": 1}}}}
    return definicion(trigger, acciones, version="1.0.0.0")


# ---------------------------------------------------------------------------------------------- paquete ZIP
FECHA_ZIP = (2026, 10, 9, 0, 0, 0)
CONEXIONES = {
    "shared_sharepointonline": ("/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "sharepointonline", "SharePoint",
                                "<CONEXION_SHAREPOINT>"),
    "shared_onedriveforbusiness": (P0.API_OD, "onedriveforbusiness", "OneDrive for Business", "<CONEXION_ONEDRIVEFORBUSINESS>"),
}


def _uuid(nombre, parte):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p10:{nombre}:{parte}"))


def conexiones_usadas(definition):
    texto = json.dumps(definition)
    return [c for c in CONEXIONES if f'"connectionName": "{c}"' in texto]


def archivos_paquete(nombre, descripcion, definition):
    usadas = conexiones_usadas(definition)
    flujo, interno = _uuid(nombre, "resource"), _uuid(nombre, "definition")
    recursos, apis_map, conex_map, refs, depende = {}, {}, {}, {}, []
    for clave in usadas:
        api_id, api_nombre, visible, marcador = CONEXIONES[clave]
        a, c = _uuid(nombre, clave + ":api"), _uuid(nombre, clave + ":connection")
        recursos[a] = {"id": api_id, "name": clave, "type": "Microsoft.PowerApps/apis", "suggestedCreationType": "Existing",
                       "details": {"displayName": visible}, "configurableBy": "System", "hierarchy": "Child", "dependsOn": []}
        recursos[c] = {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing", "creationType": "Existing",
                       "details": {"displayName": marcador}, "configurableBy": "User", "hierarchy": "Child", "dependsOn": [a]}
        apis_map[clave], conex_map[clave] = a, c
        depende += [a, c]
        refs[clave] = {"connectionName": marcador, "source": "Embedded", "id": api_id, "tier": "NotSpecified", "apiName": api_nombre,
                       "isProcessSimpleApiReferenceConversionAlreadyDone": False}
    recursos[flujo] = {"type": "Microsoft.Flow/flows", "suggestedCreationType": "New", "creationType": "New, Update",
                       "details": {"displayName": nombre}, "configurableBy": "User", "hierarchy": "Root", "dependsOn": depende}
    envoltura = {"name": interno, "id": f"/providers/Microsoft.Flow/flows/{interno}", "type": "Microsoft.Flow/flows",
                 "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows", "displayName": nombre, "definition": definition,
                                "connectionReferences": refs, "flowFailureAlertSubscribed": False, "isManaged": False}}
    base = f"Microsoft.Flow/flows/{flujo}"
    return {
        "manifest.json": {"schema": "1.0", "details": {"displayName": nombre, "description": descripcion, "createdTime": "2026-10-09T00:00:00Z",
                                                       "packageTelemetryId": _uuid(nombre, "telemetry"), "creator": "N/A", "sourceEnvironment": ""},
                          "resources": recursos},
        "Microsoft.Flow/flows/manifest.json": {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [flujo]}},
        f"{base}/apisMap.json": apis_map, f"{base}/connectionsMap.json": conex_map, f"{base}/definition.json": envoltura}


def zip_bytes(nombre, descripcion, definition):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta, contenido in archivos_paquete(nombre, descripcion, definition).items():
            info = zipfile.ZipInfo(ruta, date_time=FECHA_ZIP)
            info.create_system, info.compress_type, info.external_attr = 3, zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, json.dumps(contenido, ensure_ascii=False, separators=(",", ":")))
    return buffer.getvalue()


DESCRIPCIONES = {
    NOMBRE_SYNC: ("Sincronizador del histórico mensual de extractos (P10-A.2): cada 15 min incorpora extractos nuevos de PROCESADOS y los cambios de "
                  "Depositos_Activos, y mantiene un XLSX por banco+cuenta+moneda+mes en P10_HISTORICO."),
    NOMBRE_PROV: "Crea (una sola vez, idempotente) la lista P10_Control y su elemento LOCK en el sitio de SharePoint de Depositos_Activos.",
}


def generar():
    salidas = []
    for nombre, zip_nombre, d in ((NOMBRE_SYNC, ZIP_SYNC, construir_definicion_sync()), (NOMBRE_PROV, ZIP_PROV, construir_definicion_prov())):
        (CARPETA_SALIDA / f"{nombre}_definition.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        destino = RAIZ / zip_nombre
        destino.write_bytes(zip_bytes(nombre, DESCRIPCIONES[nombre], d))
        salidas.append((destino, contar_acciones(d["actions"])))
    return salidas


if __name__ == "__main__":
    for ruta, n in generar():
        print(ruta, f"({n} acciones)", hashlib.sha256(ruta.read_bytes()).hexdigest())
