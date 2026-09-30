"""P7 · Adaptador Microsoft 365: LISTS.csv -> artefacto de intercambio para Power Automate.

Capa NUEVA y SEPARADA del motor P6. No importa el motor, no modifica LISTS.csv ni ninguna salida del motor:
solo LEE un LISTS.csv ya generado y ESCRIBE dos archivos nuevos en una carpeta distinta:

    DEPOSITOS_ACTIVOS__<lote_id>.json   artefacto (lo lee el flujo "P7 - CARGA DEPOSITOS ACTIVOS")
    MANIFIESTO_P7__<lote_id>.json       manifiesto del lote (huella del archivo, conteos, rangos)

Uso:
    python adaptador_m365.py <LISTS.csv> <carpeta_salida> [--claves-existentes claves.txt] [--ahora AAAA-MM-DDTHH:MM:SSZ]
    python adaptador_m365.py --esquema <ruta>.json        # esquema para la accion "Analizar JSON" de Power Automate

Solo biblioteca estandar (csv, json, hashlib, ...): sin pandas, sin openpyxl.

Contrato (ver DISENO_LISTA_DEPOSITOS_ACTIVOS.md): el CSV debe traer EXACTAMENTE las 26 COLUMNAS_LISTS del motor, en
su orden. Cada valor se conserva como TEXTO EXACTO del CSV (ni recorte, ni conversion numerica, ni de fechas). La
CLAVE TRANSACCIÓN que produjo `crear_clave` (P6, congelada) es la identidad del movimiento y no se recalcula.
"""
import argparse
import ast
import csv
import datetime
import hashlib
import io
import json
import math
import os
import re
import sys

VERSION_ADAPTADOR = "P7.1"
ESQUEMA_ARTEFACTO = "P7_DEPOSITOS_ACTIVOS_V1"
ESQUEMA_MANIFIESTO = "P7_MANIFIESTO_V1"

# Estados de la carga (contrato con el flujo de Power Automate).
NUEVO = "NUEVO"
YA_EXISTE = "YA_EXISTE"
ERROR = "ERROR"

MOTIVO_EN_LISTA = "EN_LISTA"
MOTIVO_REPETIDA_EN_LOTE = "REPETIDA_EN_LOTE"

# Tipos de columna en Microsoft Lists (los usa la validacion y el esquema; el detalle esta en el documento de diseno).
T_TEXTO = "texto"            # una linea, maximo 255 caracteres
T_TEXTO_LARGO = "texto_largo"  # varias lineas (texto sin formato)
T_NUMERO = "numero"
T_FECHA = "fecha"            # solo fecha (AAAA-MM-DD)
MAX_TEXTO_LINEA = 255

# (nombre en COLUMNAS_LISTS, nombre tecnico en Microsoft Lists, tipo, obligatorio)
# Fuente de verdad de los NOMBRES de origen: motor_control_depositos_cbba.COLUMNAS_LISTS (una prueba exige que
# esta tabla coincida con esa lista, 26 columnas y mismo orden). El nombre tecnico es solo ASCII: es el nombre
# INTERNO de la columna en Microsoft Lists (los acentos y espacios generan nombres internos ilegibles).
# Las 7 columnas de "seguimiento" del motor (ESTADO, ESTUDIANTE, ...) llevan prefijo MOTOR_ porque los campos
# operativos de Power Apps (ESTUDIANTE, SOLICITADO_POR, OBSERVACION, ...) usan los mismos nombres base.
COLUMNAS_M365 = (
    ("CLAVE TRANSACCIÓN", "CLAVE_TRANSACCION", T_TEXTO, True),
    ("CÓDIGO DE ASIGNACIÓN", "CODIGO_ASIGNACION", T_TEXTO, False),
    ("BANCO", "BANCO", T_TEXTO, True),
    ("CUENTA BANCARIA", "CUENTA_BANCARIA", T_TEXTO, True),
    ("MONEDA", "MONEDA", T_TEXTO, True),
    ("FECHA MOVIMIENTO", "FECHA_MOVIMIENTO", T_FECHA, True),
    ("HORA MOVIMIENTO", "HORA_MOVIMIENTO", T_TEXTO, False),
    ("IMPORTE", "IMPORTE", T_NUMERO, True),
    ("DÉBITO", "DEBITO", T_NUMERO, False),
    ("CRÉDITO", "CREDITO", T_NUMERO, False),
    ("TIPO MOVIMIENTO", "TIPO_MOVIMIENTO", T_TEXTO, True),
    ("SALDO", "SALDO", T_NUMERO, True),
    ("DESCRIPCIÓN", "DESCRIPCION", T_TEXTO_LARGO, False),
    ("DEPOSITANTE / ORIGINANTE", "DEPOSITANTE_ORIGINANTE", T_TEXTO_LARGO, False),
    ("INFORMACIÓN ADICIONAL", "INFORMACION_ADICIONAL", T_TEXTO_LARGO, False),
    ("ESTADO", "MOTOR_ESTADO", T_TEXTO, False),
    ("ESTUDIANTE", "MOTOR_ESTUDIANTE", T_TEXTO, False),
    ("SOLICITADO POR", "MOTOR_SOLICITADO_POR", T_TEXTO, False),
    ("SEDE SOLICITANTE", "MOTOR_SEDE_SOLICITANTE", T_TEXTO, False),
    ("CONFIRMADO POR", "MOTOR_CONFIRMADO_POR", T_TEXTO, False),
    ("FECHA CONFIRMACIÓN", "MOTOR_FECHA_CONFIRMACION", T_TEXTO, False),
    ("OBSERVACIÓN", "MOTOR_OBSERVACION", T_TEXTO_LARGO, False),
    ("TEXTO DE BÚSQUEDA", "TEXTO_BUSQUEDA", T_TEXTO_LARGO, False),
    ("ARCHIVO ORIGEN", "ARCHIVO_ORIGEN", T_TEXTO, True),
    ("LOTE DE CARGA", "LOTE_CARGA", T_TEXTO, True),
    ("FECHA DE CARGA", "FECHA_CARGA", T_TEXTO, True),
)

COLUMNAS_CSV = tuple(c[0] for c in COLUMNAS_M365)
COLUMNAS_TECNICAS = tuple(c[1] for c in COLUMNAS_M365)
_TECNICO = {c[0]: c[1] for c in COLUMNAS_M365}
_TIPO = {c[1]: c[2] for c in COLUMNAS_M365}
OBLIGATORIAS = tuple(c[1] for c in COLUMNAS_M365 if c[3])
CLAVE = "CLAVE_TRANSACCION"

# Campos OPERATIVOS de Depositos_Activos (Power Apps). NO son parte de COLUMNAS_LISTS y el adaptador NO los emite:
# los completa el flujo (ESTADO_ASIGNACION = DISPONIBLE) o, despues, Power Apps.
CAMPOS_OPERATIVOS = (
    "ESTADO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION",
    "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "OBSERVACION",
)
ESTADO_ASIGNACION_INICIAL = "DISPONIBLE"

_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ContratoError(ValueError):
    """El contrato de 26 columnas de P6 no se cumple (adaptador, motor o LISTS.csv): no se genera ningun artefacto."""


# ------------------------------------------------------------------ contrato de columnas (fail-fast)

# Contrato ESPERADO por P7: las 26 columnas de COLUMNAS_LISTS de P6, en su orden. Es un literal independiente de la
# tabla COLUMNAS_M365: si alguien edita el mapeo (o el motor cambia sus columnas), el adaptador se detiene.
COLUMNAS_LISTS_P6 = (
    "CLAVE TRANSACCIÓN", "CÓDIGO DE ASIGNACIÓN", "BANCO", "CUENTA BANCARIA", "MONEDA",
    "FECHA MOVIMIENTO", "HORA MOVIMIENTO", "IMPORTE", "DÉBITO", "CRÉDITO",
    "TIPO MOVIMIENTO", "SALDO", "DESCRIPCIÓN", "DEPOSITANTE / ORIGINANTE",
    "INFORMACIÓN ADICIONAL", "ESTADO", "ESTUDIANTE", "SOLICITADO POR",
    "SEDE SOLICITANTE", "CONFIRMADO POR", "FECHA CONFIRMACIÓN", "OBSERVACIÓN",
    "TEXTO DE BÚSQUEDA", "ARCHIVO ORIGEN", "LOTE DE CARGA", "FECHA DE CARGA",
)
MOTOR_P6 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor_control_depositos_cbba.py")

CONTRATO_VERIFICADO_CONTRA_MOTOR = "VERIFICADO_CONTRA_MOTOR"
CONTRATO_MOTOR_NO_DISPONIBLE = "MOTOR_NO_DISPONIBLE"


def _describir_diferencia(esperado, recibido):
    esperado, recibido = list(esperado), list(recibido)
    faltan = [c for c in esperado if c not in recibido]
    sobran = [c for c in recibido if c not in esperado]
    partes = []
    if faltan:
        partes.append(f"faltan {faltan}")
    if sobran:
        partes.append(f"sobran {sobran}")
    if len(recibido) != len(set(recibido)):
        partes.append("hay columnas repetidas")
    if not faltan and not sobran and len(recibido) == len(set(recibido)):
        partes.append("mismas columnas en distinto orden")
    return f"{len(recibido)} columnas recibidas, se esperaban {len(esperado)}: " + "; ".join(partes)


def columnas_lists_del_motor(ruta_motor):
    """COLUMNAS_LISTS leida del CODIGO FUENTE del motor (ast.literal_eval): no lo importa ni lo ejecuta, y no
    requiere pandas. Devuelve la tupla de columnas."""
    try:
        with open(ruta_motor, encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename=ruta_motor)
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        raise ContratoError(f"No se pudo leer COLUMNAS_LISTS del motor ({ruta_motor}): {e}")
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COLUMNAS_LISTS"
                                                 for t in nodo.targets):
            try:
                valor = ast.literal_eval(nodo.value)
            except ValueError as e:
                raise ContratoError(f"COLUMNAS_LISTS del motor no es una lista literal: {e}")
            return tuple(valor)
    raise ContratoError(f"El motor ({ruta_motor}) no define COLUMNAS_LISTS")


def verificar_contrato(ruta_motor=None):
    """Fail-fast: el contrato que espera P7 debe ser EXACTAMENTE el de P6 (26 columnas, mismo nombre y orden).
    1) COLUMNAS_LISTS_P6 y la tabla COLUMNAS_M365 (nombres de origen, nombres tecnicos) deben ser coherentes.
    2) Si el motor esta junto al adaptador (o se indica `ruta_motor`), su COLUMNAS_LISTS debe ser identica.
    Lanza ContratoError ante cualquier desviacion; devuelve CONTRATO_VERIFICADO_CONTRA_MOTOR o, si el motor no esta
    disponible (adaptador desplegado solo), CONTRATO_MOTOR_NO_DISPONIBLE. No modifica P6."""
    esperado = tuple(COLUMNAS_LISTS_P6)
    if len(esperado) != 26 or len(set(esperado)) != 26:
        raise ContratoError(f"Contrato esperado invalido: {len(esperado)} columnas ({len(set(esperado))} distintas), "
                            "se requieren 26 distintas")
    origen = tuple(c[0] for c in COLUMNAS_M365)
    if origen != esperado:
        raise ContratoError("La tabla de columnas del adaptador (COLUMNAS_M365) no coincide con las 26 columnas "
                            "de P6: " + _describir_diferencia(esperado, origen))
    tecnicos = [c[1] for c in COLUMNAS_M365]
    if len(set(tecnicos)) != len(tecnicos):
        raise ContratoError("Nombres tecnicos repetidos en COLUMNAS_M365")
    choque = sorted(set(tecnicos) & set(CAMPOS_OPERATIVOS))
    if choque:
        raise ContratoError(f"Nombres tecnicos que chocan con campos operativos (usar prefijo MOTOR_): {choque}")
    ruta = MOTOR_P6 if ruta_motor is None else ruta_motor
    if not os.path.isfile(ruta):
        return CONTRATO_MOTOR_NO_DISPONIBLE
    del_motor = columnas_lists_del_motor(ruta)
    if del_motor != esperado:
        raise ContratoError("COLUMNAS_LISTS del motor no coincide con el contrato P6 esperado por P7: "
                            + _describir_diferencia(esperado, del_motor))
    return CONTRATO_VERIFICADO_CONTRA_MOTOR


# ------------------------------------------------------------------ lectura y validacion

def _sha256_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


def leer_lists_csv(ruta):
    """Lee LISTS.csv (UTF-8 con o sin BOM). Devuelve (movimientos, sha256, bytes_totales).
    Cada movimiento es un dict {nombre_tecnico: texto exacto} en el orden de COLUMNAS_LISTS."""
    with open(ruta, "rb") as f:
        datos = f.read()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ContratoError(f"LISTS.csv no esta en UTF-8: {e}")
    lector = csv.reader(io.StringIO(texto, newline=""))
    try:
        encabezado = next(lector)
    except StopIteration:
        raise ContratoError("LISTS.csv esta vacio (sin encabezado)")
    if tuple(encabezado) != COLUMNAS_CSV:
        raise ContratoError(
            "El encabezado de LISTS.csv no coincide con COLUMNAS_LISTS (26 columnas, mismo orden): "
            + _describir_diferencia(COLUMNAS_CSV, encabezado)
        )
    movimientos = []
    for n, fila in enumerate(lector, start=1):
        if len(fila) != len(COLUMNAS_CSV):
            raise ContratoError(f"Fila de datos {n}: {len(fila)} campos, se esperaban {len(COLUMNAS_CSV)}")
        movimientos.append({_TECNICO[c]: v for c, v in zip(COLUMNAS_CSV, fila)})
    return movimientos, _sha256_bytes(datos), len(datos)


def _numero_valido(txt):
    try:
        return math.isfinite(float(txt))
    except ValueError:
        return False


def _fecha_valida(txt):
    if not _FECHA_ISO.match(txt):
        return False
    try:
        datetime.date.fromisoformat(txt)
    except ValueError:
        return False
    return True


def _num2(txt):
    return f"{float(txt):.2f}"


def validar_movimiento(mov):
    """Lista de errores de un movimiento (vacia = valido). Solo comprueba coherencia estructural con el contrato;
    no recalcula ni corrige la clave."""
    errores = []
    for col in OBLIGATORIAS:
        if mov[col] == "":
            errores.append(f"OBLIGATORIO_VACIO:{col}")
    for col, tipo in _TIPO.items():
        v = mov[col]
        if v == "":
            continue
        if tipo == T_NUMERO and not _numero_valido(v):
            errores.append(f"NUMERO_INVALIDO:{col}")
        elif tipo == T_FECHA and not _fecha_valida(v):
            errores.append(f"FECHA_INVALIDA:{col}")
        elif tipo == T_TEXTO and len(v) > MAX_TEXTO_LINEA:
            errores.append(f"LONGITUD_EXCEDIDA:{col}")
    if mov[CLAVE] and not any(e.endswith(f":{CLAVE}") for e in errores):
        errores.extend(_errores_clave(mov))
    return errores


def _errores_clave(mov):
    """La CLAVE debe seguir siendo la de crear_clave (P6): BANCO|CUENTA|AAAAMMDD|HHMMSS|CODIGO|TIPO|IMPORTE|SALDO
    y coincidir con las demas columnas de la misma fila (detecta ediciones manuales del CSV)."""
    partes = mov[CLAVE].split("|")
    if len(partes) != 8:
        return ["CLAVE_FORMATO"]
    esperado = [
        mov["BANCO"],
        mov["CUENTA_BANCARIA"],
        mov["FECHA_MOVIMIENTO"].replace("-", ""),
        re.sub(r"[^0-9]", "", mov["HORA_MOVIMIENTO"]),
        mov["CODIGO_ASIGNACION"],
        mov["TIPO_MOVIMIENTO"],
        _num2(mov["IMPORTE"]) if _numero_valido(mov["IMPORTE"]) else None,
        _num2(mov["SALDO"]) if _numero_valido(mov["SALDO"]) else "",
    ]
    if any(e is None for e in esperado):
        return []  # ya reportado como NUMERO_INVALIDO
    return [] if partes == esperado else ["CLAVE_INCOHERENTE"]


# ------------------------------------------------------------------ duplicados y clasificacion

def separar_lote(movimientos):
    """Separa el lote en (a_cargar, omitidos).
    a_cargar: movimientos validos con CLAVE unica dentro del archivo (se conserva la primera aparicion), en orden.
    omitidos: dicts {fila, estado, motivo, errores, valores}: ERROR (no valido) o YA_EXISTE/REPETIDA_EN_LOTE."""
    a_cargar, omitidos, vistas = [], [], set()
    for n, mov in enumerate(movimientos, start=1):
        errores = validar_movimiento(mov)
        if errores:
            omitidos.append({"fila": n, "estado": ERROR, "motivo": ";".join(errores), "errores": errores,
                             "valores": mov})
        elif mov[CLAVE] in vistas:
            omitidos.append({"fila": n, "estado": YA_EXISTE, "motivo": MOTIVO_REPETIDA_EN_LOTE, "errores": [],
                             "valores": mov})
        else:
            vistas.add(mov[CLAVE])
            a_cargar.append(mov)
    return a_cargar, omitidos


def clasificar(a_cargar, omitidos, claves_existentes=()):
    """Resultado esperado de la carga, igual al que aplica el flujo. Devuelve una lista de
    {clave, estado, motivo, fila} en el orden original del archivo (fila = numero de fila de datos, base 1):
      ERROR                    fila no valida (nunca se envia a la lista)
      YA_EXISTE                la CLAVE ya esta en Depositos_Activos, o se repite dentro del mismo archivo
      NUEVO                    CLAVE valida y no existente: se crea con ESTADO_ASIGNACION = DISPONIBLE
    """
    existentes = set(claves_existentes)
    filas_omitidas = {o["fila"] for o in omitidos}
    por_fila = {o["fila"]: o for o in omitidos}
    resultado, iterador = [], iter(a_cargar)
    total = len(a_cargar) + len(omitidos)
    for n in range(1, total + 1):
        if n in filas_omitidas:
            o = por_fila[n]
            resultado.append({"fila": n, "clave": o["valores"][CLAVE], "estado": o["estado"], "motivo": o["motivo"]})
            continue
        mov = next(iterador)
        if mov[CLAVE] in existentes:
            resultado.append({"fila": n, "clave": mov[CLAVE], "estado": YA_EXISTE, "motivo": MOTIVO_EN_LISTA})
        else:
            resultado.append({"fila": n, "clave": mov[CLAVE], "estado": NUEVO, "motivo": ""})
    return resultado


# ------------------------------------------------------------------ construccion de artefacto y manifiesto

def identificador_lote(sha256_hex):
    """Determinista: mismo LISTS.csv (byte a byte) => mismo lote. No depende de la fecha ni del equipo."""
    return "P7-" + sha256_hex[:12]


def _ahora_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def construir_manifiesto(nombre_fuente, sha256_hex, bytes_fuente, movimientos, a_cargar, omitidos, generado_en,
                         nombre_artefacto=None, sha256_artefacto=None):
    validos = [m for m in movimientos if not validar_movimiento(m)]
    fechas = sorted(m["FECHA_MOVIMIENTO"] for m in validos)
    cuentas = {}
    for m in validos:
        k = (m["BANCO"], m["CUENTA_BANCARIA"], m["MONEDA"])
        cuentas[k] = cuentas.get(k, 0) + 1
    repetidas = sum(1 for o in omitidos if o["motivo"] == MOTIVO_REPETIDA_EN_LOTE)
    con_error = sum(1 for o in omitidos if o["estado"] == ERROR)
    manifiesto = {
        "esquema": ESQUEMA_MANIFIESTO,
        "version_adaptador": VERSION_ADAPTADOR,
        "lote_id": identificador_lote(sha256_hex),
        "generado_en": generado_en,
        "archivo_fuente": nombre_fuente,
        "sha256_archivo_fuente": sha256_hex,
        "bytes_archivo_fuente": bytes_fuente,
        "cantidad_recibida": len(movimientos),
        "cantidad_valida": len(validos),
        "cantidad_a_cargar": len(a_cargar),
        "cantidad_repetida_en_lote": repetidas,
        "cantidad_error": con_error,
        "rango_fechas": {"desde": fechas[0], "hasta": fechas[-1]} if fechas else None,
        "bancos": sorted({k[0] for k in cuentas}),
        "cuentas": [
            {"banco": b, "cuenta": c, "moneda": mo, "movimientos": n}
            for (b, c, mo), n in sorted(cuentas.items())
        ],
        "lotes_motor": sorted({m["LOTE_CARGA"] for m in validos}),
        "archivos_origen": sorted({m["ARCHIVO_ORIGEN"] for m in validos}),
    }
    if nombre_artefacto is not None:
        manifiesto["artefacto"] = {"archivo": nombre_artefacto, "sha256": sha256_artefacto}
    return manifiesto


def serializar_artefacto(lote_id, nombre_fuente, sha256_hex, a_cargar, omitidos):
    """JSON UTF-8 sin BOM, una fila por linea (legible en diff), orden de claves fijo => bytes deterministas."""
    d = lambda x: json.dumps(x, ensure_ascii=False)  # noqa: E731
    partes = [
        "{",
        f'"esquema": {d(ESQUEMA_ARTEFACTO)},',
        f'"lote_id": {d(lote_id)},',
        f'"archivo_fuente": {d(nombre_fuente)},',
        f'"sha256_archivo_fuente": {d(sha256_hex)},',
        f'"columnas": {d(list(COLUMNAS_TECNICAS))},',
        '"movimientos": [',
        ",\n".join(d(m) for m in a_cargar),
        "],",
        '"omitidos": [',
        ",\n".join(d(o) for o in omitidos),
        "]",
        "}",
        "",
    ]
    return "\n".join(partes).encode("utf-8")


def esquema_parse_json():
    """Esquema para la accion 'Analizar JSON' de Power Automate (todos los valores son texto, como en el CSV)."""
    fila = {
        "type": "object",
        "properties": {c: {"type": "string"} for c in COLUMNAS_TECNICAS},
        "required": list(COLUMNAS_TECNICAS),
    }
    omitido = {
        "type": "object",
        "properties": {
            "fila": {"type": "integer"},
            "estado": {"type": "string"},
            "motivo": {"type": "string"},
            "errores": {"type": "array", "items": {"type": "string"}},
            "valores": fila,
        },
        "required": ["fila", "estado", "motivo", "errores", "valores"],
    }
    return {
        "type": "object",
        "properties": {
            "esquema": {"type": "string"},
            "lote_id": {"type": "string"},
            "archivo_fuente": {"type": "string"},
            "sha256_archivo_fuente": {"type": "string"},
            "columnas": {"type": "array", "items": {"type": "string"}},
            "movimientos": {"type": "array", "items": fila},
            "omitidos": {"type": "array", "items": omitido},
        },
        "required": ["esquema", "lote_id", "archivo_fuente", "sha256_archivo_fuente", "columnas", "movimientos",
                     "omitidos"],
    }


def serializar_esquema():
    return (json.dumps(esquema_parse_json(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def adaptar(ruta_lists_csv, carpeta_salida, ahora=None, claves_existentes=None, ruta_motor=None):
    """Lee LISTS.csv y escribe el artefacto y el manifiesto en `carpeta_salida`.
    `carpeta_salida` no puede ser la carpeta de LISTS.csv (no se toca la salida del motor).
    Devuelve dict con rutas, manifiesto y (si se dieron `claves_existentes`) la clasificacion esperada."""
    contrato = verificar_contrato(ruta_motor)  # fail-fast: antes de leer o escribir cualquier cosa
    ruta_lists_csv = os.path.abspath(ruta_lists_csv)
    carpeta_salida = os.path.abspath(carpeta_salida)
    if os.path.dirname(ruta_lists_csv) == carpeta_salida:
        raise ContratoError("La carpeta de salida del adaptador debe ser distinta de la carpeta de LISTS.csv")
    movimientos, sha, tam = leer_lists_csv(ruta_lists_csv)  # falla ANTES de escribir nada
    a_cargar, omitidos = separar_lote(movimientos)
    lote_id = identificador_lote(sha)
    nombre_fuente = os.path.basename(ruta_lists_csv)

    artefacto = serializar_artefacto(lote_id, nombre_fuente, sha, a_cargar, omitidos)
    nombre_artefacto = f"DEPOSITOS_ACTIVOS__{lote_id}.json"
    manifiesto = construir_manifiesto(
        nombre_fuente, sha, tam, movimientos, a_cargar, omitidos, ahora or _ahora_utc(),
        nombre_artefacto, _sha256_bytes(artefacto),
    )
    os.makedirs(carpeta_salida, exist_ok=True)
    rutas = {
        "artefacto": os.path.join(carpeta_salida, nombre_artefacto),
        "manifiesto": os.path.join(carpeta_salida, f"MANIFIESTO_P7__{lote_id}.json"),
    }
    with open(rutas["artefacto"], "wb") as f:
        f.write(artefacto)
    with open(rutas["manifiesto"], "wb") as f:
        f.write((json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    res = {"lote_id": lote_id, "rutas": rutas, "manifiesto": manifiesto, "contrato": contrato}
    if claves_existentes is not None:
        clasif = clasificar(a_cargar, omitidos, claves_existentes)
        rutas["clasificacion"] = os.path.join(carpeta_salida, f"CLASIFICACION_P7__{lote_id}.csv")
        with open(rutas["clasificacion"], "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["FILA", "CLAVE TRANSACCIÓN", "ESTADO", "MOTIVO"])
            for c in clasif:
                w.writerow([c["fila"], c["clave"], c["estado"], c["motivo"]])
        res["clasificacion"] = clasif
    return res


def leer_claves_existentes(ruta):
    """Un CLAVE TRANSACCIÓN por linea (UTF-8), p. ej. exportada de Depositos_Activos."""
    with open(ruta, encoding="utf-8-sig") as f:
        return {linea.rstrip("\r\n") for linea in f if linea.strip()}


def main(argv=None):
    p = argparse.ArgumentParser(description="P7: LISTS.csv -> artefacto JSON para Power Automate")
    p.add_argument("lists_csv", nargs="?")
    p.add_argument("carpeta_salida", nargs="?")
    p.add_argument("--claves-existentes", help="archivo con una CLAVE TRANSACCIÓN por linea (exportada de la lista)")
    p.add_argument("--ahora", help="fecha/hora UTC del manifiesto AAAA-MM-DDTHH:MM:SSZ (por defecto, la actual)")
    p.add_argument("--esquema", help="escribe el esquema JSON para 'Analizar JSON' y termina")
    a = p.parse_args(argv)
    if a.esquema:
        try:
            verificar_contrato()
        except ContratoError as e:
            print(f"ERROR de contrato: {e}", file=sys.stderr)
            return 2
        with open(a.esquema, "wb") as f:
            f.write(serializar_esquema())
        print(f"Esquema escrito: {a.esquema}")
        return 0
    if not a.lists_csv or not a.carpeta_salida:
        p.error("faltan lists_csv y carpeta_salida")
    try:
        existentes = leer_claves_existentes(a.claves_existentes) if a.claves_existentes else None
        r = adaptar(a.lists_csv, a.carpeta_salida, ahora=a.ahora, claves_existentes=existentes)
    except ContratoError as e:
        print(f"ERROR de contrato: {e}", file=sys.stderr)
        return 2
    m = r["manifiesto"]
    print(f"Contrato de 26 columnas: {r['contrato']}")
    print(f"Lote {m['lote_id']}: recibidas={m['cantidad_recibida']} validas={m['cantidad_valida']} "
          f"a_cargar={m['cantidad_a_cargar']} repetidas_en_lote={m['cantidad_repetida_en_lote']} "
          f"error={m['cantidad_error']}")
    for k, v in r["rutas"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
