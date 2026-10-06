"""Acciones WDL de la PREVALIDACIÓN REAL contra `Depositos_Activos` (solo lectura) para `P9_MASIVA_PROTO_PREVALIDAR`.

Se insertan en `construir.py` después de leer `tblConfirmacionMasiva` y de comprobar que hay filas con datos. NO escriben nada:
la única operación contra `Depositos_Activos` es UN GET (`Enviar una solicitud HTTP a SharePoint`, el mismo patrón ya validado en
P9_ASIGNAR_DEPOSITO V4.2 para leer el depósito). No hay `Apply to each` ni una llamada a SharePoint por fila: el universo
elegible (CRÉDITO + últimos 2 meses) se trae UNA vez y las filas se resuelven con `Select` / `Filter array` / `split`.

Reglas (ver ../PREVALIDACION_REAL.md):
  clave base = BANCO + CUENTA_BANCARIA + CODIGO_ASIGNACION + IMPORTE   (MONEDA NO entra en la clave; se compara después)
  texto  -> trim; BANCO/CODIGO/CUENTA se comparan en minúsculas; NUNCA se convierten a número (se conservan los ceros iniciales)
  IMPORTE -> texto con punto decimal, máx. 2 decimales, > 0; se compara como ENTERO de centavos (nunca como texto ni con redondeo libre)

Índice de depósitos en memoria (una sola cadena): `§<clave>¶<id>¦<CLAVE_TRANSACCION>¦<estado>¦<moneda>¦<fecha>¤` por depósito. El número
de coincidencias de una fila es el número de apariciones de `§<clave>¶` (length(split(...)) - 1). Los separadores § ¦ ¶ ¤ no existen en
los datos reales (se eligieron por eso).
"""
from __future__ import annotations

from p9 import contrato as C
from p9.wdl import asignar, compose, si, secuencia
from proto_masiva.contrato_plantilla import ENCABEZADOS, MONEDAS, OBLIGATORIAS

# ---------------------------------------------------------------------------------------------- contrato (única fuente)
LISTA_DEPOSITOS_ID = C.LISTA_DEPOSITOS_ACTIVOS_ID          # lista real Depositos_Activos (la misma que lee V4.2)
TIPO_CREDITO = "CRÉDITO"                                    # valor real de TIPO_MOVIMIENTO (con tilde): lo usa la galería de P9
ESTADO_DISPONIBLE = "DISPONIBLE"                            # único estado confirmable (valores de la opción: DISPONIBLE, ASIGNADO)
MESES_VENTANA = 2                                           # DateAdd(Today(), -2, TimeUnit.Months): igual que galDepositosP9_1
ZONA_HORARIA = "SA Western Standard Time"                   # Bolivia (UTC-4, sin horario de verano): «Today()» de la app
TOPE_DEPOSITOS = 5000                                       # $top de la lectura; si SharePoint indica más (__next) se avisa, no se cuenta de menos
FILA_ENCABEZADO_PLANTILLA = 5                               # el encabezado de la plantilla oficial está en la fila 5 -> fila_excel = fila_tabla + 5
# columnas REALES de Depositos_Activos que lee la prevalidación (nombre interno = nombre técnico; ver ../PREVALIDACION_REAL.md §2)
COLUMNAS_DEPOSITO = ("Id", "CLAVE_TRANSACCION", "BANCO", "CUENTA_BANCARIA", "CODIGO_ASIGNACION", "IMPORTE", "MONEDA",
                     "ESTADO_ASIGNACION", "FECHA_MOVIMIENTO")

RESULTADOS_FILA = ("VALIDO", "FILA_INCOMPLETA", "IMPORTE_INVALIDO", "MONEDA_INVALIDA", "DUPLICADO_ARCHIVO", "NO_ENCONTRADO",
                   "ASIGNACION_AMBIGUA", "MONEDA_NO_COINCIDE", "NO_DISPONIBLE")
CODIGO_OK, CODIGO_OBSERVADO = "PREVALIDACION_OK", "PREVALIDACION_CON_ERRORES"
CODIGO_SHAREPOINT, CODIGO_UNIVERSO = "ERROR_SHAREPOINT", "DEPOSITOS_DEMASIADOS"
SALIDAS_NUEVAS = ("filas_totales", "filas_validas", "filas_con_error", "depositos_consultados", "detalle_json")
DETALLE_CAMPOS = ("fila_excel", "fila_tabla", "resultado", "mensaje", "deposito_id", "clave_transaccion", "estado_actual",
                  "fecha_movimiento", "moneda_deposito", "coincidencias", "banco", "cuenta_bancaria", "codigo_asignacion",
                  "importe", "importe_original", "moneda", "estudiante", "solicitado_por", "sede", "observacion")

REG, SEP, PAY, FIN = "§", "¦", "¶", "¤"
# nombre de columna de la plantilla -> campo interno de la fila
CAMPO = {"BANCO": "banco", "CUENTA_BANCARIA": "cuenta", "CODIGO_ASIGNACION": "codigo", "IMPORTE": "importe_txt", "MONEDA": "moneda",
         "ESTUDIANTE": "estudiante", "SOLICITADO_POR": "solicitado_por", "SEDE": "sede", "OBSERVACION": "observacion"}
assert tuple(CAMPO) == ENCABEZADOS


# ---------------------------------------------------------------------------------------------- helpers de expresión
def lit(texto):
    return "'" + texto.replace("'", "''") + "'"


def it(campo):
    return f"item()?['{campo}']"


def encadenar_if(casos, por_defecto):
    """`if(c1,v1,if(c2,v2,...,por_defecto))` generado: evita contar paréntesis a mano. `casos` = [(condición, valor)]."""
    expr = por_defecto
    for condicion, valor in reversed(casos):
        expr = f"if({condicion},{valor},{expr})"
    return expr


def pasar(campos):
    return {c: "@" + it(c) for c in campos}


def sin_digitos(expr):
    for d in "0123456789":
        expr = f"replace({expr},{lit(d)},'')"
    return expr


def centavos(texto):
    """Entero de centavos de un importe ya validado (≤ 2 decimales): exacto, sin comparar texto ni redondear a ojo."""
    return f"int(formatNumber(mul(float({texto}),100),'0'))"


CAMPOS_TEXTO = ("fila_tabla", "banco", "cuenta", "codigo", "importe_txt", "moneda", "estudiante", "solicitado_por", "sede", "observacion")
CAMPOS_FORMATO = CAMPOS_TEXTO + ("faltan", "en_blanco", "formato_ok")
CAMPOS_CALCULO = CAMPOS_FORMATO + ("centavos", "importe_ok", "moneda_ok", "incompleta")
CAMPOS_CLAVE = CAMPOS_CALCULO + ("clave_ok", "clave")
CAMPOS_MATCH = CAMPOS_CLAVE + ("n_dup", "n_dep", "dep")
CAMPOS_RESULTADO = CAMPOS_MATCH + ("resultado", "conoce", "dep_id", "dep_clave", "dep_estado", "dep_moneda", "dep_fecha")


def _select(origen, expresiones):
    return {"type": "Select", "inputs": {"from": origen, "select": expresiones}}


# ---------------------------------------------------------------------------------------------- 1 · filas del Excel
def filas_con_posicion():
    """Una entrada por fila de la tabla (incluidas las totalmente en blanco, para no desalinear fila_excel)."""
    return _select("@range(0,length(outputs('Filas_brutas')))",
                   {"n": "@add(item(),1)", "f": "@outputs('Filas_brutas')?[item()]"})


def filas_texto():
    def col(nombre):
        return f"trim(string(coalesce(item()?['f']?['{nombre}'],'')))"
    sel = {"fila_tabla": "@" + it("n")}
    for nombre, campo in CAMPO.items():
        sel[campo] = f"@toUpper({col(nombre)})" if campo == "moneda" else "@" + col(nombre)
    return _select("@body('Filas_con_posicion')", sel)


def filas_formato():
    s = it("importe_txt")
    ip = f"indexOf({s},'.')"
    sd = sin_digitos(s)
    faltan = "@concat(" + ",".join(f"if(empty({it(CAMPO[h])}),{lit(h + ', ')},'')" for h in OBLIGATORIAS) + ")"
    en_blanco = "@and(" + ",".join(f"empty({it(CAMPO[h])})" for h in ENCABEZADOS) + ")"
    formato = (f"@and(not(empty({s})),lessOrEquals(length({s}),15),or(equals({sd},''),and(equals({sd},'.'),greater({ip},0),"
               f"less({ip},sub(length({s}),1)),lessOrEquals(sub(length({s}),add({ip},1)),2))))")
    return _select("@body('Filas_texto')", {**pasar(CAMPOS_TEXTO), "faltan": faltan, "en_blanco": en_blanco, "formato_ok": formato})


def filas_calculo():
    moneda_ok = "@or(" + ",".join(f"equals({it('moneda')},{lit(m)})" for m in MONEDAS) + ")"
    return _select("@body('Filas_formato')", {
        **pasar(CAMPOS_FORMATO),
        "centavos": f"@if({it('formato_ok')},{centavos(it('importe_txt'))},0)",
        "importe_ok": f"@if({it('formato_ok')},greater({centavos(it('importe_txt'))},0),false)",
        "moneda_ok": moneda_ok,
        "incompleta": f"@not(empty({it('faltan')}))"})


def _clave_ok():
    return (f"and(not(empty({it('banco')})),not(empty({it('cuenta')})),not(empty({it('codigo')})),{it('importe_ok')})")


def clave_texto(banco, cuenta, codigo, cents):
    return f"concat(toLower({banco}),{lit(SEP)},toLower({cuenta}),{lit(SEP)},toLower({codigo}),{lit(SEP)},string({cents}))"


def filas_clave():
    return _select("@body('Filas_calculo')", {
        **pasar(CAMPOS_CALCULO),
        "clave_ok": "@" + _clave_ok(),
        "clave": f"@if({_clave_ok()},{clave_texto(it('banco'), it('cuenta'), it('codigo'), it('centavos'))},'')"})


def marcas_clave():
    return _select("@body('Filas_a_validar')", f"@if({it('clave_ok')},concat({lit(REG)},{it('clave')},{lit(PAY)}),'')")


# ---------------------------------------------------------------------------------------------- 2 · depósitos
def uri_depositos():
    """GET de UNA sola lectura: CRÉDITO + ventana de la galería (FECHA_MOVIMIENTO desde hoy-2 meses hasta hoy). Solo lectura.

    `_api/web/lists(guid'<GUID>')/items?$select=<columnas>&$filter=TIPO_MOVIMIENTO eq 'CRÉDITO' and FECHA_MOVIMIENTO ge datetime'<desde>T00:00:00Z'
    and FECHA_MOVIMIENTO le datetime'<hoy>T00:00:00Z'&$top=<tope>`
    """
    trozos = [
        lit("_api/web/lists(guid'"), "outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS')",
        lit("')/items?$select=" + ",".join(COLUMNAS_DEPOSITO) + f"&$filter=TIPO_MOVIMIENTO eq '{TIPO_CREDITO}' "
            "and FECHA_MOVIMIENTO ge datetime'"),
        "outputs('Desde_local')", lit("T00:00:00Z' and FECHA_MOVIMIENTO le datetime'"),
        "outputs('Hoy_local')", lit("T00:00:00Z'&$top="), "string(outputs('PARAM_TOPE_DEPOSITOS'))"]
    return "@concat(" + ",".join(trozos) + ")"


def leer_depositos():
    return {"type": "OpenApiConnection", "inputs": {
        "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "connectionName": "shared_sharepointonline",
                 "operationId": "HttpRequest"},
        "parameters": {"dataset": "@outputs('PARAM_SITIO')", "parameters/method": "GET", "parameters/uri": uri_depositos(),
                       "parameters/headers": {"Accept": "application/json;odata=verbose"}},
        "authentication": "@parameters('$authentication')", "retryPolicy": {"type": "none"}}}


def depositos_normalizados():
    def txt(campo):
        return f"trim(string(coalesce({it(campo)},'')))"
    cents = centavos(f"string(coalesce({it('IMPORTE')},0))")
    entrada = ("@concat(" + ",".join([
        lit(REG), clave_texto(txt("BANCO"), txt("CUENTA_BANCARIA"), txt("CODIGO_ASIGNACION"), cents), lit(PAY),
        f"string({it('Id')})", lit(SEP), txt("CLAVE_TRANSACCION"), lit(SEP), txt("ESTADO_ASIGNACION"), lit(SEP),
        f"toUpper({txt('MONEDA')})", lit(SEP), f"take({txt('FECHA_MOVIMIENTO')},10)", lit(FIN)]) + ")")
    return _select("@outputs('Depositos')", entrada)


# ---------------------------------------------------------------------------------------------- 3 · resolución por fila
def filas_coincidencia():
    clave = f"concat({lit(REG)},{it('clave')},{lit(PAY)})"

    def apariciones(texto):
        return f"if({it('clave_ok')},sub(length(split({texto},{clave})),1),0)"
    return _select("@body('Filas_a_validar')", {
        **pasar(CAMPOS_CLAVE),
        "n_dup": "@" + apariciones("outputs('Texto_claves')"),
        "n_dep": "@" + apariciones("outputs('Indice_depositos')"),
        "dep": f"@if({it('clave_ok')},if(equals(sub(length(split(outputs('Indice_depositos'),{clave})),1),1),"
               f"first(split(last(split(outputs('Indice_depositos'),{clave})),{lit(FIN)})),''),'')"})


def detalle_resultado():
    r = it
    sep = lit(SEP)
    cadena = encadenar_if([
        (r("incompleta"), "'FILA_INCOMPLETA'"),
        (f"not({r('importe_ok')})", "'IMPORTE_INVALIDO'"),
        (f"not({r('moneda_ok')})", "'MONEDA_INVALIDA'"),
        (f"greater({r('n_dup')},1)", "'DUPLICADO_ARCHIVO'"),
        (f"equals({r('n_dep')},0)", "'NO_ENCONTRADO'"),
        (f"greater({r('n_dep')},1)", "'ASIGNACION_AMBIGUA'"),
        (f"not(equals(split({r('dep')},{sep})[3],{r('moneda')}))", "'MONEDA_NO_COINCIDE'"),
        (f"not(equals(split({r('dep')},{sep})[2],{lit(ESTADO_DISPONIBLE)}))", "'NO_DISPONIBLE'")], "'VALIDO'")

    def dep(i):
        return f"@if(empty({r('dep')}),'',split({r('dep')},{lit(SEP)})[{i}])"
    return _select("@body('Filas_coincidencia')", {
        **pasar(CAMPOS_MATCH), "resultado": "@" + cadena,
        "conoce": f"@and({r('clave_ok')},{r('moneda_ok')},not({r('incompleta')}),less({r('n_dup')},2),equals({r('n_dep')},1))",
        "dep_id": dep(0), "dep_clave": dep(1), "dep_estado": dep(2), "dep_moneda": dep(3), "dep_fecha": dep(4)})


def detalle():
    r = it

    def res(nombre):
        return f"equals({r('resultado')},{lit(nombre)})"
    mensaje = encadenar_if([
        (res("VALIDO"), f"concat('Depósito disponible encontrado (ID ',{r('dep_id')},').')"),
        (res("FILA_INCOMPLETA"), f"concat('Faltan datos obligatorios: ',take({r('faltan')},sub(length({r('faltan')}),2)),'.')"),
        (res("IMPORTE_INVALIDO"), "'IMPORTE inválido: use un número mayor que 0, con punto decimal y como máximo 2 decimales.'"),
        (res("MONEDA_INVALIDA"), "'MONEDA inválida: use BOB o USD.'"),
        (res("DUPLICADO_ARCHIVO"), f"concat('Hay ',string({r('n_dup')}),' filas del archivo que apuntan al mismo depósito "
                                   "(BANCO + CUENTA + CÓDIGO + IMPORTE).')"),
        (res("NO_ENCONTRADO"), "'No hay un depósito CRÉDITO de los últimos 2 meses con ese BANCO, CUENTA, CÓDIGO e IMPORTE.'"),
        (res("ASIGNACION_AMBIGUA"), f"concat('Hay ',string({r('n_dep')}),' depósitos con esa misma clave: no se puede elegir uno.')"),
        (res("MONEDA_NO_COINCIDE"), f"concat('La moneda del Excel (',{r('moneda')},') no coincide con la del depósito (',{r('dep_moneda')},').')")],
        f"concat('El depósito no está disponible para confirmar. Estado actual: ',{r('dep_estado')},'.')")
    conoce = r("conoce")
    return _select("@body('Filas_resultado')", {
        "fila_excel": f"@add({r('fila_tabla')},{FILA_ENCABEZADO_PLANTILLA})", "fila_tabla": "@" + r("fila_tabla"),
        "resultado": "@" + r("resultado"), "mensaje": "@" + mensaje,
        "deposito_id": f"@if({conoce},int({r('dep_id')}),null)",
        "clave_transaccion": f"@if({conoce},{r('dep_clave')},'')",
        "estado_actual": f"@if({conoce},{r('dep_estado')},'')",
        "fecha_movimiento": f"@if({conoce},{r('dep_fecha')},'')",
        "moneda_deposito": f"@if({conoce},{r('dep_moneda')},'')",
        "coincidencias": "@" + r("n_dep"),
        "banco": "@" + r("banco"), "cuenta_bancaria": "@" + r("cuenta"), "codigo_asignacion": "@" + r("codigo"),
        "importe": f"@if({r('importe_ok')},div(float({r('centavos')}),100),null)", "importe_original": "@" + r("importe_txt"),
        "moneda": "@" + r("moneda"), "estudiante": "@" + r("estudiante"), "solicitado_por": "@" + r("solicitado_por"),
        "sede": "@" + r("sede"), "observacion": "@" + r("observacion")})


# ---------------------------------------------------------------------------------------------- 4 · bloque completo
def _universo_ok():
    return secuencia(
        Depositos_normalizados=depositos_normalizados(),
        Indice_depositos=compose("@join(body('Depositos_normalizados'),'')"),
        Etapa_validacion_filas=asignar("varEtapa", "VALIDACION"),
        Filas_coincidencia=filas_coincidencia(),
        Filas_resultado=detalle_resultado(),
        Detalle_filas=detalle(),
        Filas_validas={"type": "Query", "inputs": {"from": "@body('Detalle_filas')",
                                                    "where": "@equals(item()?['resultado'],'VALIDO')"}},
        Cuenta_validas=compose("@length(body('Filas_validas'))"),
        Cuenta_total=compose("@length(body('Detalle_filas'))"),
        Guardar_totales=asignar("varTotales", "@string(outputs('Cuenta_total'))"),
        Guardar_validas=asignar("varValidas", "@string(outputs('Cuenta_validas'))"),
        Guardar_con_error=asignar("varConError", "@string(sub(outputs('Cuenta_total'),outputs('Cuenta_validas')))"),
        Guardar_universo=asignar("varUniverso", "@string(length(outputs('Depositos')))"),
        Guardar_detalle=asignar("varDetalle", "@string(body('Detalle_filas'))"),
        Resultado_prevalidacion=asignar("varResultado", {
            "estado": "@if(equals(outputs('Cuenta_validas'),outputs('Cuenta_total')),'OK','OBSERVADO')",
            "codigo": f"@if(equals(outputs('Cuenta_validas'),outputs('Cuenta_total')),'{CODIGO_OK}','{CODIGO_OBSERVADO}')",
            "mensaje": "@concat(string(outputs('Cuenta_validas')),' de ',string(outputs('Cuenta_total')),' filas válidas'"
                       ",if(equals(outputs('Cuenta_validas'),outputs('Cuenta_total')),'. ',"
                       "concat('; ',string(sub(outputs('Cuenta_total'),outputs('Cuenta_validas'))),' con observaciones. ')),"
                       "'Prevalidación de solo lectura: no se confirmó ningún depósito.')",
            "tabla": "SI", "filas": "@outputs('Cuenta_total')"}))


def prevalidar_filas(error_universo):
    """Bloque que reemplaza al antiguo `Resultado_OK`: normaliza, lee depósitos (1 GET), resuelve fila por fila y fija el resultado."""
    return secuencia(
        Marca_T5=asignar("varT5", "@ticks(utcNow())"),
        Etapa_filas=asignar("varEtapa", "VALIDACION"),
        Filas_con_posicion=filas_con_posicion(),
        Filas_texto=filas_texto(),
        Filas_formato=filas_formato(),
        Filas_calculo=filas_calculo(),
        Filas_calculadas=filas_clave(),
        Filas_a_validar={"type": "Query", "inputs": {"from": "@body('Filas_calculadas')", "where": "@not(item()?['en_blanco'])"}},
        Marcas_clave=marcas_clave(),
        Texto_claves=compose("@join(body('Marcas_clave'),'')"),
        Hoy_local=compose(f"@convertTimeZone(utcNow(),'UTC',{lit(ZONA_HORARIA)},'yyyy-MM-dd')"),
        Desde_local=compose(f"@formatDateTime(addToTime(concat(outputs('Hoy_local'),'T00:00:00Z'),-{MESES_VENTANA},'Month'),'yyyy-MM-dd')"),
        Etapa_depositos=asignar("varEtapa", "DEPOSITOS"),
        Leer_depositos=leer_depositos(),
        Marca_T6=asignar("varT6", "@ticks(utcNow())"),
        Depositos=compose("@coalesce(body('Leer_depositos')?['d']?['results'],createArray())"),
        Universo_completo=si("@not(empty(body('Leer_depositos')?['d']?['__next']))", error_universo, _universo_ok()))
