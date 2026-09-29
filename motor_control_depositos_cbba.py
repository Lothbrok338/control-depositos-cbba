"""
============================================================
CONTROL DE DEPÓSITOS CBBA — MOTOR DE NORMALIZACIÓN
============================================================

Reconstrucción como script único de:
  - CELDA_1_CONTROL_DEPOSITOS_CORREGIDA.txt
    (configuración + detección + normalización + validación)
  - CELDA_2_CONTROL_DEPOSITOS_CORREGIDA.txt
    (subida de archivos -> reemplazada por descubrimiento automático)
  - CELDA_3_CONTROL_DEPOSITOS_CORREGIDA.txt
    (orquestación + auditoría + exportación)

REGLA FUNDAMENTAL: ninguna regla de negocio fue modificada respecto
de las 3 celdas originales (detección de bancos/cuentas, hojas
válidas, encabezados esperados, normalizadores por banco, cálculo
de CÓDIGO DE ASIGNACIÓN y CLAVE TRANSACCIÓN, reglas de débito/
crédito, extracción del originante, construcción de INFORMACIÓN
ADICIONAL, validaciones estructurales, validación de saldos con
tolerancia 0.01, control fijo del año 2026, criterios que bloquean
la exportación, estados válidos OK/SIN MOVIMIENTOS, y el lector
robusto xlrd -> calamine ante AssertionError).

Este módulo es intencionalmente independiente de Google Drive, de
Google Colab y de Claude/Cowork. Solo conoce:
  - una carpeta local de entrada (extractos .xls/.xlsx ya
    descargados, con su nombre original intacto);
  - una ruta local de salida (NORMALIZADO.xlsx).

Descargar los extractos desde Drive y volver a subir NORMALIZADO.xlsx
es responsabilidad de la orquestación externa (Cowork), NO de este
motor. Este archivo no importa ni referencia ningún conector de
Google Drive.

Cambios de infraestructura respecto de las 3 celdas (ninguno es una
regla de negocio):
  1. Se elimina `from google.colab import files`, `files.upload()` y
     `files.download()`. En su lugar: `descubrir_archivos()` lista
     los .xls/.xlsx de una carpeta local, y `ejecutar_motor()` recibe
     una ruta local de salida en vez de disparar una descarga.
  2. Se elimina `display(df)` (específico de notebooks). Se reemplaza
     por `print(df.to_string(index=False))`, que muestra exactamente
     la misma información.
  3. Se elimina la línea `!pip -q install ...` (sintaxis de notebook,
     inválida en un .py). En su lugar, `verificar_dependencias()`
     comprueba en tiempo de ejecución que pandas, numpy, xlrd,
     openpyxl y python-calamine estén disponibles, y falla con un
     mensaje claro (incluyendo el comando pip) si falta alguna.
  4. ARCHIVO ORIGEN: las celdas originales usaban directamente el
     nombre devuelto por `files.upload()` (que en Colab ya era solo
     el nombre de archivo, sin ruta). Ahora que el archivo puede
     leerse desde una ruta temporal completa, se separan dos
     conceptos:
       - `archivo`: la ruta real desde la que se lee el Excel
         (necesaria para pd.read_excel).
       - `nombre_origen`: el nombre original del archivo, que es lo
         único que se guarda en la columna ARCHIVO ORIGEN y lo único
         que se usa en las comparaciones internas
         (`df_final["ARCHIVO ORIGEN"] == nombre_origen`).
     Todas las funciones normalizar_* y finalizar_dataframe aceptan
     ahora un parámetro opcional `nombre_origen` (por defecto None,
     en cuyo caso se comporta exactamente como antes y usa `archivo`
     tal cual). Esto es un cambio de encaje de datos, no de lógica
     de negocio.
  5. El nombre de salida deja de llevar timestamp
     ("CONTROL_DEPOSITOS_CBBA_PRUEBA_<timestamp>.xlsx") y pasa a ser
     la ruta fija que indique el llamador (por requisito de esta
     etapa: NORMALIZADO.xlsx). El contenido y las 4 hojas
     (LISTS, VALIDACION, RESUMEN, DIAGNOSTICO) no cambian.
  6. Salida adicional LISTS.csv: además de NORMALIZADO.xlsx (que no
     se reemplaza ni se altera), se genera un archivo plano
     LISTS.csv en la misma carpeta de salida, con el mismo
     `df_final` ya validado, restringido a las columnas y al orden
     exacto de `COLUMNAS_LISTS`, codificado en UTF-8 con BOM
     (utf-8-sig). Es puramente una exportación adicional: no
     modifica ningún dato, cálculo ni validación del motor.

Uso como script:
    python motor_control_depositos_cbba.py <carpeta_entrada> <ruta_salida>

Uso como módulo:
    from motor_control_depositos_cbba import ejecutar_motor
    resultado = ejecutar_motor("/tmp/entrada", "/tmp/salida/NORMALIZADO.xlsx")
============================================================
"""

import importlib
import os
import re
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.table import Table


# ============================================================
# 0. VERIFICACIÓN DE DEPENDENCIAS
# ============================================================

DEPENDENCIAS_REQUERIDAS = {
    "pandas": "pandas",
    "numpy": "numpy",
    "xlrd": "xlrd",
    "openpyxl": "openpyxl",
    "python_calamine": "python-calamine",
}


def verificar_dependencias():
    """
    Comprueba que las librerías necesarias para el motor estén
    disponibles en el intérprete actual. No instala nada: solo
    informa qué falta, para que la orquestación decida cómo
    resolverlo antes de ejecutar el motor.

    Lanza RuntimeError si falta alguna dependencia.
    """

    faltantes = []

    for modulo, paquete_pip in DEPENDENCIAS_REQUERIDAS.items():

        try:
            importlib.import_module(modulo)
        except ImportError:
            faltantes.append(paquete_pip)

    if faltantes:
        raise RuntimeError(
            "❌ Faltan dependencias para ejecutar el motor: "
            f"{', '.join(faltantes)}. "
            "Instálalas antes de continuar con: "
            f"pip install {' '.join(faltantes)}"
        )

    return True


# ============================================================
# COLUMNAS FINALES
# ============================================================

COLUMNAS_LISTS = [
    "CLAVE TRANSACCIÓN",
    "CÓDIGO DE ASIGNACIÓN",
    "BANCO",
    "CUENTA BANCARIA",
    "MONEDA",
    "FECHA MOVIMIENTO",
    "HORA MOVIMIENTO",
    "IMPORTE",
    "DÉBITO",
    "CRÉDITO",
    "TIPO MOVIMIENTO",
    "SALDO",
    "DESCRIPCIÓN",
    "DEPOSITANTE / ORIGINANTE",
    "INFORMACIÓN ADICIONAL",
    "ESTADO",
    "ESTUDIANTE",
    "SOLICITADO POR",
    "SEDE SOLICITANTE",
    "CONFIRMADO POR",
    "FECHA CONFIRMACIÓN",
    "OBSERVACIÓN",
    "TEXTO DE BÚSQUEDA",
    "ARCHIVO ORIGEN",
    "LOTE DE CARGA",
    "FECHA DE CARGA"
]


# ============================================================
# HOJA CORRECTA POR FORMATO
# ============================================================

HOJAS_VALIDAS = {
    "ECO_AHORRO": "Extracto",
    "ECO_CTA_CTE": "Extracto",
    "BMSC": "Excel",
    "UNION_ME": "ExtractoMovimientosFechas",
    "UNION_MN": "ExtractoMovimientosFechas",
    "BCP_ME": "HistoricalAccountExcel",
    "BCP_MN": "HistoricalAccountExcel",
    "BISA_ME": "Extracto de Movimientos",
    "BISA_MN": "Extracto de Movimientos",
    "BNB_AHORRO": "Hoja",
    "BNB_ME": "Hoja 1",
    "BNB_MN": "Hoja 1",
    "BNB_CLINICA": "Hoja 1"
}


# ============================================================
# ENCABEZADOS ESPERADOS
# ============================================================

ENCABEZADOS_ESPERADOS = {

    "UNION_MN": [
        "FECHA MOVIMIENTO",
        "DESCRIPCION",
        "NRO DOCUMENTO",
        "MONTO",
        "SALDO"
    ],

    "UNION_ME": [
        "FECHA MOVIMIENTO",
        "DESCRIPCION",
        "NRO DOCUMENTO",
        "MONTO",
        "SALDO"
    ],

    "BMSC": [
        "FECHA",
        "HORA",
        "COD. BCA.",
        "DEBITO",
        "CREDITO",
        "SALDO"
    ],

    "ECO_CTA_CTE": [
        "FECHA",
        "HORA",
        "NRO TRN./CHEQUE",
        "TRANSACCION",
        "MONTO",
        "SALDO"
    ],

    "ECO_AHORRO": [
        "FECHA",
        "HORA",
        "NRO TRN./CHEQUE",
        "TRANSACCION",
        "MONTO",
        "SALDO"
    ],

    "BNB_CLINICA": [
        "FECHA",
        "HORA",
        "DESCRIPCION",
        "CODIGO DE TRANSACCION",
        "DEBITOS",
        "CREDITOS",
        "SALDO"
    ],

    "BNB_MN": [
        "FECHA",
        "HORA",
        "DESCRIPCION",
        "CODIGO DE TRANSACCION",
        "DEBITOS",
        "CREDITOS",
        "SALDO"
    ],

    "BNB_ME": [
        "FECHA",
        "HORA",
        "DESCRIPCION",
        "CODIGO DE TRANSACCION",
        "DEBITOS",
        "CREDITOS",
        "SALDO"
    ],

    "BNB_AHORRO": [
        "FECHA",
        "HORA",
        "DESCRIPCION",
        "CODIGO DE TRANSACCION",
        "DEBITOS",
        "CREDITOS",
        "SALDO"
    ],

    "BISA_MN": [
        "FECHA",
        "HORA",
        "DESCRIPCION",
        "IMPORTE",
        "SALDO",
        "NRO. REF."
    ],

    "BISA_ME": [
        "FECHA",
        "HORA",
        "DESCRIPCION",
        "IMPORTE",
        "SALDO",
        "NRO. REF."
    ],

    "BCP_MN": [
        "FECHA",
        "HORA",
        "GLOSA",
        "IMPORTE",
        "SALDO",
        "NRO. OPERACION"
    ],

    "BCP_ME": [
        "FECHA",
        "HORA",
        "GLOSA",
        "IMPORTE",
        "SALDO",
        "NRO. OPERACION"
    ]
}


# ============================================================
# FUNCIONES DE TEXTO
# ============================================================

def normalizar_texto(valor):

    if pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto


def buscar_columna(df, *posibles):

    mapa = {
        normalizar_texto(c): c
        for c in df.columns
    }

    for posible in posibles:

        clave = normalizar_texto(posible)

        if clave in mapa:
            return mapa[clave]

    for posible in posibles:

        clave = normalizar_texto(posible)

        for normalizada, original in mapa.items():

            if (
                clave in normalizada
                or normalizada in clave
            ):
                return original

    raise KeyError(
        f"No encontré {posibles}. "
        f"Columnas disponibles: {list(df.columns)}"
    )


def buscar_columna_opcional(df, *posibles):

    try:
        return buscar_columna(
            df,
            *posibles
        )

    except:
        return None


# ============================================================
# CONVERSIÓN DE NÚMEROS
# ============================================================

def numero(valor):

    if pd.isna(valor) or valor == "":
        return np.nan

    if isinstance(
        valor,
        (int, float, np.integer, np.floating)
    ):
        return float(valor)

    texto = str(valor).strip()

    texto = (
        texto
        .replace("Bs", "")
        .replace("BS", "")
        .replace("USD", "")
        .replace("EUR", "")
        .replace("$", "")
        .replace(" ", "")
    )

    if "," in texto and "." in texto:

        if texto.rfind(",") > texto.rfind("."):

            texto = (
                texto
                .replace(".", "")
                .replace(",", ".")
            )

        else:

            texto = texto.replace(",", "")

    elif "," in texto:

        texto = texto.replace(",", ".")

    try:
        return float(texto)

    except:
        return np.nan


# ============================================================
# CÓDIGOS COMO TEXTO
# ============================================================

def codigo_texto(valor):

    if pd.isna(valor):
        return ""

    if isinstance(valor, (int, np.integer)):
        return str(valor)

    if isinstance(valor, (float, np.floating)):

        if float(valor).is_integer():
            return str(int(valor))

        return str(valor)

    texto = str(valor).strip()

    if re.match(
        r"^-?\d+\.0$",
        texto
    ):
        return texto[:-2]

    return texto


# ============================================================
# FECHA Y HORA
# ============================================================

def normalizar_fecha(valor):

    if pd.isna(valor) or valor == "":
        return pd.NaT

    # Fechas ya reconocidas por pandas / Excel
    if isinstance(valor, (pd.Timestamp, datetime)):
        return pd.Timestamp(valor).date()

    texto = normalizar_texto(valor)

    # Meses en español usados por algunos extractos
    meses_es = {
        "ENE": "01",
        "FEB": "02",
        "MAR": "03",
        "ABR": "04",
        "MAY": "05",
        "JUN": "06",
        "JUL": "07",
        "AGO": "08",
        "SEP": "09",
        "SET": "09",
        "OCT": "10",
        "NOV": "11",
        "DIC": "12"
    }

    for mes, numero_mes in meses_es.items():
        texto = re.sub(
            rf"\b{mes}\b",
            numero_mes,
            texto
        )

    fecha = pd.to_datetime(
        texto,
        dayfirst=True,
        errors="coerce"
    )

    if pd.isna(fecha):
        return pd.NaT

    return fecha.date()

def normalizar_hora(valor):

    if pd.isna(valor):
        return ""

    if hasattr(valor, "strftime"):

        try:
            return valor.strftime("%H:%M:%S")
        except:
            pass

    texto = str(valor).strip()

    if texto == "":
        return ""

    try:

        hora = pd.to_datetime(
            texto,
            errors="coerce"
        )

        if not pd.isna(hora):
            return hora.strftime("%H:%M:%S")

    except:
        pass

    return texto


# ============================================================
# LEER TODAS LAS HOJAS
# ============================================================

def leer_excel_robusto(archivo, **kwargs):
    """
    Intenta leer con el motor normal de pandas.
    Si xlrd lanza AssertionError en ciertos .xls antiguos,
    reintenta automáticamente con Calamine.
    """
    try:
        return pd.read_excel(
            archivo,
            **kwargs
        )

    except AssertionError:
        print(
            f"⚠️ xlrd no pudo leer '{archivo}'. "
            "Reintentando con Calamine..."
        )

        return pd.read_excel(
            archivo,
            engine="calamine",
            **kwargs
        )


def leer_todas_hojas(archivo):

    return leer_excel_robusto(
        archivo,
        sheet_name=None,
        header=None
    )

def texto_de_archivo(hojas):

    partes = []

    for nombre, df in hojas.items():

        partes.append(str(nombre))

        muestra = (
            df.head(40)
            .fillna("")
            .astype(str)
        )

        partes.extend(
            muestra.values.flatten()
        )

    return normalizar_texto(
        " ".join(partes)
    )


# ============================================================
# DETECTOR ROBUSTO
#
# IMPORTANTE:
# Primero identifica la estructura del banco.
# Recién después usa la cuenta.
#
# Esto evita confundir números de cuenta que aparezcan
# dentro de glosas, adicionales u originantes.
# ============================================================

def detectar_formato(archivo):

    hojas = leer_todas_hojas(
        archivo
    )

    texto = texto_de_archivo(
        hojas
    )

    # ========================================================
    # 1. BISA
    # ========================================================

    if (
        "INFO. COMPLEMENTARIA" in texto
        or "NRO. REF." in texto
        or "BANCO BISA" in texto
    ):

        if "0696870039" in texto:
            return "BISA_MN"

        if "0696872023" in texto:
            return "BISA_ME"

        if "MONEDA: BS" in texto:
            return "BISA_MN"

        if "MONEDA: USD" in texto:
            return "BISA_ME"


    # ========================================================
    # 2. BNB
    # ========================================================

    if (
        "CODIGO DE TRANSACCION" in texto
        and "ADICIONALES" in texto
    ):

        if "3000100152" in texto:
            return "BNB_MN"

        if "3400041236" in texto:
            return "BNB_ME"

        if "3501936692" in texto:
            return "BNB_AHORRO"

        if "3000100705" in texto:
            return "BNB_CLINICA"


    # ========================================================
    # 3. BCP
    # ========================================================

    if (
        "EXTRACTOS BANCARIOS" in texto
        and "NRO. OPERACION" in texto
    ):

        if "301-5005684-3-97" in texto:
            return "BCP_MN"

        if "301-5005425-2-71" in texto:
            return "BCP_ME"


    # ========================================================
    # 4. BANCO UNIÓN
    # ========================================================

    if (
        "FECHA MOVIMIENTO" in texto
        and "NRO DOCUMENTO" in texto
    ):

        if "10000003224552" in texto:
            return "UNION_MN"

        if "20000003224544" in texto:
            return "UNION_ME"


    # ========================================================
    # 5. BANCO ECONÓMICO
    # ========================================================

    if (
        "NRO TRN./CHEQUE" in texto
        and "TRANSACCION" in texto
    ):

        if "3041210569" in texto:
            return "ECO_CTA_CTE"

        if "3051446946" in texto:
            return "ECO_AHORRO"


    # ========================================================
    # 6. BMSC
    # ========================================================

    if (
        "COD. BCA." in texto
        or "NOMBRE/DENOMINACION DEPOSITANTE" in texto
        or "BANCO MERCANTIL SANTA CRUZ" in texto
    ):

        return "BMSC"


    return "NO_RECONOCIDO"


# ============================================================
# DETECTAR FILA DE ENCABEZADO
# ============================================================

def encontrar_fila_encabezado(
    df_raw,
    formato
):

    esperados = (
        ENCABEZADOS_ESPERADOS[
            formato
        ]
    )

    mejor_fila = None
    mejor_puntaje = -1

    for idx, fila in df_raw.iterrows():

        texto = normalizar_texto(
            " | ".join(
                fila.fillna("")
                .astype(str)
                .tolist()
            )
        )

        puntaje = sum(
            1
            for encabezado in esperados
            if normalizar_texto(encabezado)
            in texto
        )

        if puntaje > mejor_puntaje:

            mejor_fila = idx
            mejor_puntaje = puntaje

    return (
        mejor_fila,
        mejor_puntaje,
        len(esperados)
    )


# ============================================================
# LEER TABLA DE MOVIMIENTOS
# ============================================================

def leer_tabla_movimientos(
    archivo,
    formato
):

    hoja = HOJAS_VALIDAS[
        formato
    ]

    raw = leer_excel_robusto(
        archivo,
        sheet_name=hoja,
        header=None
    )

    fila_header, _, _ = (
        encontrar_fila_encabezado(
            raw,
            formato
        )
    )

    df = leer_excel_robusto(
        archivo,
        sheet_name=hoja,
        header=fila_header
    )

    df = df.dropna(
        axis=1,
        how="all"
    )

    df.columns = [
        re.sub(
            r"\s+",
            " ",
            str(c)
        ).strip()
        for c in df.columns
    ]

    return df

# ============================================================
# EXTRAER NOMBRE BNB
# ============================================================

def extraer_nombre_bnb(texto):

    if pd.isna(texto):
        return ""

    s = str(texto)

    patrones = [
        r"Nombre Originante\s*:\s*([^;]+)",
        r"Nombre\\?\s*:\s*([^;]+)",
        r"Nombre\s*:\s*([^;]+)"
    ]

    for patron in patrones:

        m = re.search(
            patron,
            s,
            flags=re.IGNORECASE
        )

        if m:
            return m.group(1).strip()

    return ""


# ============================================================
# CLAVE DEFINITIVA
# ============================================================

def valor_clave_numero(valor):

    if pd.isna(valor):
        return ""

    return f"{float(valor):.2f}"


def crear_clave(row):

    fecha = pd.to_datetime(
        row["FECHA MOVIMIENTO"],
        errors="coerce"
    )

    fecha_txt = (
        ""
        if pd.isna(fecha)
        else fecha.strftime("%Y%m%d")
    )

    hora = re.sub(
        r"[^0-9]",
        "",
        str(
            row["HORA MOVIMIENTO"]
        )
    )

    return (
        f"{row['BANCO']}|"
        f"{row['CUENTA BANCARIA']}|"
        f"{fecha_txt}|"
        f"{hora}|"
        f"{codigo_texto(row['CÓDIGO DE ASIGNACIÓN'])}|"
        f"{row['TIPO MOVIMIENTO']}|"
        f"{valor_clave_numero(row['IMPORTE'])}|"
        f"{valor_clave_numero(row['SALDO'])}"
    )


# ============================================================
# FINALIZAR TABLA
# ============================================================

def finalizar_dataframe(
    df,
    archivo,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df["ESTADO"] = "DISPONIBLE"
    df["ESTUDIANTE"] = ""
    df["SOLICITADO POR"] = ""
    df["SEDE SOLICITANTE"] = "COCHABAMBA"
    df["CONFIRMADO POR"] = ""
    df["FECHA CONFIRMACIÓN"] = pd.NaT
    df["OBSERVACIÓN"] = ""

    # ARCHIVO ORIGEN guarda el nombre original del archivo, nunca
    # una ruta temporal. Si no se indica nombre_origen explícito,
    # se mantiene el comportamiento original (usar "archivo" tal
    # cual, como en las celdas de Colab, donde ya era solo un
    # nombre de archivo sin ruta).
    df["ARCHIVO ORIGEN"] = (
        nombre_origen
        if nombre_origen is not None
        else archivo
    )

    df["LOTE DE CARGA"] = lote
    df["FECHA DE CARGA"] = fecha_carga

    df["TEXTO DE BÚSQUEDA"] = (
        df["DESCRIPCIÓN"]
        .fillna("")
        .astype(str)
        + " | "
        + df["DEPOSITANTE / ORIGINANTE"]
        .fillna("")
        .astype(str)
        + " | "
        + df["INFORMACIÓN ADICIONAL"]
        .fillna("")
        .astype(str)
        + " | "
        + df["CÓDIGO DE ASIGNACIÓN"]
        .fillna("")
        .astype(str)
    )

    df["CLAVE TRANSACCIÓN"] = (
        df.apply(
            crear_clave,
            axis=1
        )
    )

    for columna in COLUMNAS_LISTS:

        if columna not in df.columns:
            df[columna] = ""

    return df[
        COLUMNAS_LISTS
    ]


# ============================================================
# NORMALIZADOR BNB
# ============================================================

def normalizar_bnb(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df = leer_tabla_movimientos(
        archivo,
        formato
    )

    cf = buscar_columna(df, "Fecha")
    ch = buscar_columna(df, "Hora")

    cd = buscar_columna(
        df,
        "Descripción",
        "Descripcion"
    )

    cc = buscar_columna(
        df,
        "Código de transacción",
        "Codigo de transaccion"
    )

    cs = buscar_columna(
        df,
        "Saldo"
    )

    ca = buscar_columna(
        df,
        "Adicionales"
    )

    cdeb = buscar_columna_opcional(
        df,
        "Débitos",
        "Debitos",
        "Débito",
        "Debito"
    )

    ccre = buscar_columna_opcional(
        df,
        "Créditos",
        "Creditos",
        "Crédito",
        "Credito"
    )

    fechas = pd.to_datetime(
        df[cf],
        dayfirst=True,
        errors="coerce"
    )

    df = df[
        fechas.notna()
    ].copy()

    cuentas = {
        "BNB_MN": "3000100152",
        "BNB_ME": "3400041236",
        "BNB_AHORRO": "3501936692",
        "BNB_CLINICA": "3000100705"
    }

    salida = pd.DataFrame(
        index=df.index
    )

    salida["BANCO"] = "BNB"
    salida["CUENTA BANCARIA"] = cuentas[formato]

    salida["MONEDA"] = (
        "USD"
        if formato == "BNB_ME"
        else "BOB"
    )

    salida["FECHA MOVIMIENTO"] = (
        df[cf].apply(
            normalizar_fecha
        )
    )

    salida["HORA MOVIMIENTO"] = (
        df[ch].apply(
            normalizar_hora
        )
    )

    salida["DÉBITO"] = (
        df[cdeb].apply(numero)
        if cdeb is not None
        else np.nan
    )

    salida["CRÉDITO"] = (
        df[ccre].apply(numero)
        if ccre is not None
        else np.nan
    )

    salida["IMPORTE"] = (
        salida["CRÉDITO"]
        .fillna(
            salida["DÉBITO"]
        )
        .abs()
    )

    salida["TIPO MOVIMIENTO"] = (
        np.select(
            [
                salida["CRÉDITO"].notna(),
                salida["DÉBITO"].notna()
            ],
            [
                "CRÉDITO",
                "DÉBITO"
            ],
            default=""
        )
    )

    salida["SALDO"] = (
        df[cs].apply(numero)
    )

    salida["DESCRIPCIÓN"] = (
        df[cd]
        .fillna("")
        .astype(str)
    )

    salida["DEPOSITANTE / ORIGINANTE"] = (
        df[ca].apply(
            extraer_nombre_bnb
        )
    )

    salida["INFORMACIÓN ADICIONAL"] = (
        df[ca]
        .fillna("")
        .astype(str)
    )

    salida["CÓDIGO DE ASIGNACIÓN"] = (
        df[cc].apply(
            codigo_texto
        )
    )

    return finalizar_dataframe(
        salida,
        archivo,
        lote,
        fecha_carga,
        nombre_origen=nombre_origen
    )


# ============================================================
# NORMALIZADOR BCP
# ============================================================

def normalizar_bcp(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df = leer_tabla_movimientos(
        archivo,
        formato
    )

    cf = buscar_columna(df, "Fecha")
    ch = buscar_columna(df, "Hora")
    cg = buscar_columna(df, "Glosa")
    ci = buscar_columna(df, "Importe")
    cs = buscar_columna(df, "Saldo")

    co = buscar_columna(
        df,
        "Nro. Operación",
        "Nro Operación",
        "Nro. Operacion",
        "Nro Operacion"
    )

    glosa = (
        df[cg]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    df = df[
        ~glosa.str.contains(
            "SALDO INICIAL",
            na=False
        )
        &
        ~glosa.str.contains(
            "SALDO AL CIERRE",
            na=False
        )
    ].copy()

    fechas = pd.to_datetime(
        df[cf],
        dayfirst=True,
        errors="coerce"
    )

    df = df[
        fechas.notna()
    ].copy()

    salida = pd.DataFrame(
        index=df.index
    )

    if formato == "BCP_MN":

        cuenta = "301-5005684-3-97"
        moneda = "BOB"

    else:

        cuenta = "301-5005425-2-71"
        moneda = "USD"

    salida["BANCO"] = "BCP"
    salida["CUENTA BANCARIA"] = cuenta
    salida["MONEDA"] = moneda

    salida["FECHA MOVIMIENTO"] = (
        df[cf].apply(
            normalizar_fecha
        )
    )

    salida["HORA MOVIMIENTO"] = (
        df[ch].apply(
            normalizar_hora
        )
    )

    monto = (
        df[ci].apply(numero)
    )

    salida["IMPORTE"] = monto.abs()

    salida["CRÉDITO"] = (
        monto.where(
            monto > 0
        )
    )

    salida["DÉBITO"] = (
        (-monto).where(
            monto < 0
        )
    )

    salida["TIPO MOVIMIENTO"] = (
        np.select(
            [
                monto > 0,
                monto < 0
            ],
            [
                "CRÉDITO",
                "DÉBITO"
            ],
            default=""
        )
    )

    salida["SALDO"] = (
        df[cs].apply(numero)
    )

    salida["DESCRIPCIÓN"] = (
        df[cg]
        .fillna("")
        .astype(str)
    )

    salida["DEPOSITANTE / ORIGINANTE"] = ""

    info_cols = []

    for nombre in [
        "Tipo",
        "Suc. Age.",
        "Usuario"
    ]:

        col = buscar_columna_opcional(
            df,
            nombre
        )

        if col is not None:
            info_cols.append(col)

    if info_cols:

        salida["INFORMACIÓN ADICIONAL"] = (
            df[info_cols]
            .fillna("")
            .astype(str)
            .agg(
                " | ".join,
                axis=1
            )
        )

    else:

        salida["INFORMACIÓN ADICIONAL"] = ""

    salida["CÓDIGO DE ASIGNACIÓN"] = (
        df[co].apply(
            codigo_texto
        )
    )

    return finalizar_dataframe(
        salida,
        archivo,
        lote,
        fecha_carga,
        nombre_origen=nombre_origen
    )


# ============================================================
# NORMALIZADOR BANCO UNIÓN
# ============================================================

def normalizar_union(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df = leer_tabla_movimientos(
        archivo,
        formato
    )

    cf = buscar_columna(
        df,
        "Fecha Movimiento"
    )

    cd = buscar_columna(
        df,
        "Descripción",
        "Descripcion"
    )

    cc = buscar_columna(
        df,
        "Nro Documento",
        "Nro. Documento"
    )

    cm = buscar_columna(
        df,
        "Monto"
    )

    cs = buscar_columna(
        df,
        "Saldo"
    )

    cag = buscar_columna_opcional(
        df,
        "AG",
        "Agencia"
    )

    fechas = pd.to_datetime(
        df[cf],
        dayfirst=True,
        errors="coerce"
    )

    df = df[
        fechas.notna()
    ].copy()

    if formato == "UNION_MN":

        cuenta = "10000003224552"
        moneda = "BOB"

    else:

        cuenta = "20000003224544"
        moneda = "USD"

    salida = pd.DataFrame(
        index=df.index
    )

    salida["BANCO"] = "BANCO UNIÓN"
    salida["CUENTA BANCARIA"] = cuenta
    salida["MONEDA"] = moneda

    salida["FECHA MOVIMIENTO"] = (
        df[cf].apply(
            normalizar_fecha
        )
    )

    salida["HORA MOVIMIENTO"] = ""

    monto = (
        df[cm].apply(numero)
    )

    salida["IMPORTE"] = monto.abs()
    salida["CRÉDITO"] = monto.where(monto > 0)
    salida["DÉBITO"] = (-monto).where(monto < 0)

    salida["TIPO MOVIMIENTO"] = (
        np.select(
            [
                monto > 0,
                monto < 0
            ],
            [
                "CRÉDITO",
                "DÉBITO"
            ],
            default=""
        )
    )

    salida["SALDO"] = (
        df[cs].apply(numero)
    )

    salida["DESCRIPCIÓN"] = (
        df[cd]
        .fillna("")
        .astype(str)
    )

    salida["DEPOSITANTE / ORIGINANTE"] = ""

    salida["INFORMACIÓN ADICIONAL"] = (
        (
            "AG: "
            + df[cag]
            .fillna("")
            .astype(str)
        )
        if cag is not None
        else ""
    )

    salida["CÓDIGO DE ASIGNACIÓN"] = (
        df[cc].apply(
            codigo_texto
        )
    )

    return finalizar_dataframe(
        salida,
        archivo,
        lote,
        fecha_carga,
        nombre_origen=nombre_origen
    )


# ============================================================
# NORMALIZADOR BANCO ECONÓMICO
# ============================================================

def normalizar_economico(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df = leer_tabla_movimientos(
        archivo,
        formato
    )

    cf = buscar_columna(
        df,
        "Fecha"
    )

    ch = buscar_columna_opcional(
        df,
        "Hora"
    )

    cc = buscar_columna(
        df,
        "Nro Trn./Cheque",
        "Nro Trn / Cheque"
    )

    ct = buscar_columna(
        df,
        "Transacción",
        "Transaccion"
    )

    cn = buscar_columna_opcional(
        df,
        "Nota"
    )

    cm = buscar_columna(
        df,
        "Monto"
    )

    cs = buscar_columna(
        df,
        "Saldo"
    )

    # Banco Económico puede entregar fechas como 24/Ago/2026.
    fechas = df[cf].apply(
        normalizar_fecha
    )

    df = df[
        fechas.notna()
    ].copy()

    cuenta = (
        "3041210569"
        if formato == "ECO_CTA_CTE"
        else "3051446946"
    )

    salida = pd.DataFrame(
        index=df.index
    )

    salida["BANCO"] = "BANCO ECONÓMICO"
    salida["CUENTA BANCARIA"] = cuenta
    salida["MONEDA"] = "BOB"

    salida["FECHA MOVIMIENTO"] = (
        df[cf].apply(
            normalizar_fecha
        )
    )

    salida["HORA MOVIMIENTO"] = (
        df[ch].apply(
            normalizar_hora
        )
        if ch is not None
        else ""
    )

    monto = (
        df[cm].apply(numero)
    )

    salida["IMPORTE"] = monto.abs()
    salida["CRÉDITO"] = monto.where(monto > 0)
    salida["DÉBITO"] = (-monto).where(monto < 0)

    salida["TIPO MOVIMIENTO"] = (
        np.select(
            [
                monto > 0,
                monto < 0
            ],
            [
                "CRÉDITO",
                "DÉBITO"
            ],
            default=""
        )
    )

    salida["SALDO"] = (
        df[cs].apply(numero)
    )

    salida["DESCRIPCIÓN"] = (
        df[ct]
        .fillna("")
        .astype(str)
    )

    salida["DEPOSITANTE / ORIGINANTE"] = ""

    salida["INFORMACIÓN ADICIONAL"] = (
        df[cn]
        .fillna("")
        .astype(str)
        if cn is not None
        else ""
    )

    salida["CÓDIGO DE ASIGNACIÓN"] = (
        df[cc].apply(
            codigo_texto
        )
    )

    return finalizar_dataframe(
        salida,
        archivo,
        lote,
        fecha_carga,
        nombre_origen=nombre_origen
    )

# ============================================================
# NORMALIZADOR BISA
# ============================================================

def normalizar_bisa(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df = leer_tabla_movimientos(
        archivo,
        formato
    )

    cf = buscar_columna_opcional(
        df,
        "Fecha"
    )

    # Extracto válido sin movimientos
    if cf is None:

        return pd.DataFrame(
            columns=COLUMNAS_LISTS
        )

    ch = buscar_columna_opcional(
        df,
        "Hora"
    )

    cd = buscar_columna(
        df,
        "Descripción",
        "Descripcion"
    )

    ci = buscar_columna(
        df,
        "Importe"
    )

    cs = buscar_columna(
        df,
        "Saldo"
    )

    cinfo = buscar_columna_opcional(
        df,
        "Info. Complementaria",
        "Info Complementaria"
    )

    cref = buscar_columna(
        df,
        "Nro. Ref.",
        "Nro Ref."
    )

    csuc = buscar_columna_opcional(
        df,
        "Sucursal"
    )

    ccan = buscar_columna_opcional(
        df,
        "Canal"
    )

    fechas = pd.to_datetime(
        df[cf],
        dayfirst=True,
        errors="coerce"
    )

    df = df[
        fechas.notna()
    ].copy()

    if formato == "BISA_MN":

        cuenta = "0696870039"
        moneda = "BOB"

    else:

        cuenta = "0696872023"
        moneda = "USD"

    salida = pd.DataFrame(
        index=df.index
    )

    salida["BANCO"] = "BISA"
    salida["CUENTA BANCARIA"] = cuenta
    salida["MONEDA"] = moneda

    salida["FECHA MOVIMIENTO"] = (
        df[cf].apply(
            normalizar_fecha
        )
    )

    salida["HORA MOVIMIENTO"] = (
        df[ch].apply(
            normalizar_hora
        )
        if ch is not None
        else ""
    )

    monto = (
        df[ci].apply(numero)
    )

    salida["IMPORTE"] = monto.abs()
    salida["CRÉDITO"] = monto.where(monto > 0)
    salida["DÉBITO"] = (-monto).where(monto < 0)

    salida["TIPO MOVIMIENTO"] = (
        np.select(
            [
                monto > 0,
                monto < 0
            ],
            [
                "CRÉDITO",
                "DÉBITO"
            ],
            default=""
        )
    )

    salida["SALDO"] = (
        df[cs].apply(numero)
    )

    salida["DESCRIPCIÓN"] = (
        df[cd]
        .fillna("")
        .astype(str)
    )

    salida["DEPOSITANTE / ORIGINANTE"] = ""

    partes = []

    if cinfo is not None:

        partes.append(
            df[cinfo]
            .fillna("")
            .astype(str)
        )

    if csuc is not None:

        partes.append(
            "Sucursal: "
            + df[csuc]
            .fillna("")
            .astype(str)
        )

    if ccan is not None:

        partes.append(
            "Canal: "
            + df[ccan]
            .fillna("")
            .astype(str)
        )

    if partes:

        info = partes[0]

        for parte in partes[1:]:

            info = (
                info
                + " | "
                + parte
            )

        salida["INFORMACIÓN ADICIONAL"] = info

    else:

        salida["INFORMACIÓN ADICIONAL"] = ""

    salida["CÓDIGO DE ASIGNACIÓN"] = (
        df[cref].apply(
            codigo_texto
        )
    )

    return finalizar_dataframe(
        salida,
        archivo,
        lote,
        fecha_carga,
        nombre_origen=nombre_origen
    )


# ============================================================
# NORMALIZADOR BMSC
# ============================================================

def normalizar_bmsc(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    df = leer_tabla_movimientos(
        archivo,
        formato
    )

    cf = buscar_columna(
        df,
        "Fecha"
    )

    ch = buscar_columna_opcional(
        df,
        "Hora"
    )

    cc = buscar_columna(
        df,
        "Cod. Bca.",
        "Cod Bca."
    )

    cdeb = buscar_columna_opcional(
        df,
        "Débito",
        "Debito",
        "Débitos",
        "Debitos"
    )

    ccre = buscar_columna_opcional(
        df,
        "Crédito",
        "Credito",
        "Créditos",
        "Creditos"
    )

    cs = buscar_columna(
        df,
        "Saldo"
    )

    cd = buscar_columna(
        df,
        "Descripción",
        "Descripcion"
    )

    cn = buscar_columna_opcional(
        df,
        "Nombre/Denominación Depositante",
        "Nombre/Denominacion Depositante"
    )

    cdoc = buscar_columna_opcional(
        df,
        "Doc.Depositante",
        "Doc. Depositante"
    )

    cglosa = buscar_columna_opcional(
        df,
        "Glosa"
    )

    corig = buscar_columna_opcional(
        df,
        "Originador"
    )

    cach = buscar_columna_opcional(
        df,
        "Originador ACH"
    )

    fechas = pd.to_datetime(
        df[cf],
        dayfirst=True,
        errors="coerce"
    )

    df = df[
        fechas.notna()
    ].copy()

    salida = pd.DataFrame(
        index=df.index
    )

    salida["BANCO"] = "BMSC"
    salida["CUENTA BANCARIA"] = "1000872489"
    salida["MONEDA"] = "BOB"

    salida["FECHA MOVIMIENTO"] = (
        df[cf].apply(
            normalizar_fecha
        )
    )

    salida["HORA MOVIMIENTO"] = (
        df[ch].apply(
            normalizar_hora
        )
        if ch is not None
        else ""
    )

    salida["DÉBITO"] = (
        df[cdeb].apply(numero)
        if cdeb is not None
        else np.nan
    )

    salida["CRÉDITO"] = (
        df[ccre].apply(numero)
        if ccre is not None
        else np.nan
    )

    salida["IMPORTE"] = (
        salida["CRÉDITO"]
        .fillna(
            salida["DÉBITO"]
        )
        .abs()
    )

    salida["TIPO MOVIMIENTO"] = (
        np.select(
            [
                salida["CRÉDITO"].notna(),
                salida["DÉBITO"].notna()
            ],
            [
                "CRÉDITO",
                "DÉBITO"
            ],
            default=""
        )
    )

    salida["SALDO"] = (
        df[cs].apply(numero)
    )

    salida["DESCRIPCIÓN"] = (
        df[cd]
        .fillna("")
        .astype(str)
    )

    salida["DEPOSITANTE / ORIGINANTE"] = (
        df[cn]
        .fillna("")
        .astype(str)
        if cn is not None
        else ""
    )

    partes = []

    for etiqueta, col in [
        ("DOC", cdoc),
        ("GLOSA", cglosa),
        ("ORIGINADOR", corig),
        ("ORIGINADOR ACH", cach)
    ]:

        if col is not None:

            partes.append(
                etiqueta
                + ": "
                + df[col]
                .fillna("")
                .astype(str)
            )

    if partes:

        info = partes[0]

        for parte in partes[1:]:

            info = (
                info
                + " | "
                + parte
            )

        salida["INFORMACIÓN ADICIONAL"] = info

    else:

        salida["INFORMACIÓN ADICIONAL"] = ""

    salida["CÓDIGO DE ASIGNACIÓN"] = (
        df[cc].apply(
            codigo_texto
        )
    )

    return finalizar_dataframe(
        salida,
        archivo,
        lote,
        fecha_carga,
        nombre_origen=nombre_origen
    )


# ============================================================
# ENRUTADOR
# ============================================================

def normalizar_archivo(
    archivo,
    formato,
    lote,
    fecha_carga,
    nombre_origen=None
):

    if formato.startswith("BNB_"):

        return normalizar_bnb(
            archivo,
            formato,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

    if formato.startswith("BCP_"):

        return normalizar_bcp(
            archivo,
            formato,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

    if formato.startswith("UNION_"):

        return normalizar_union(
            archivo,
            formato,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

    if formato.startswith("ECO_"):

        return normalizar_economico(
            archivo,
            formato,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

    if formato.startswith("BISA_"):

        return normalizar_bisa(
            archivo,
            formato,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

    if formato == "BMSC":

        return normalizar_bmsc(
            archivo,
            formato,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

    raise ValueError(
        f"Formato no soportado: {formato}"
    )


# ============================================================
# VALIDACIÓN MATEMÁTICA
# ============================================================

def ecuacion_saldo(
    saldo_inicial,
    creditos,
    debitos,
    saldo_final
):

    calculado = (
        saldo_inicial
        + creditos
        - debitos
    )

    diferencia = (
        saldo_final
        - calculado
    )

    return (
        round(calculado, 2),
        round(diferencia, 2),
        "OK"
        if abs(diferencia) <= 0.01
        else "REVISAR"
    )


def validar_archivo(
    archivo,
    formato,
    datos
):

    datos = datos.copy()

    # BNB suele venir de más reciente a más antiguo.
    # Para reconstruir correctamente saldo inicial/final,
    # ordenar cronológicamente solo durante la validación.
    if (
        formato.startswith("BNB_")
        and len(datos) > 0
    ):

        datos["_ORDEN_FECHA"] = pd.to_datetime(
            datos["FECHA MOVIMIENTO"],
            errors="coerce"
        )

        horas_orden = (
            datos["HORA MOVIMIENTO"]
            .fillna("")
            .astype(str)
            .replace(
                "",
                "00:00:00"
            )
        )

        datos["_ORDEN_HORA"] = pd.to_timedelta(
            horas_orden,
            errors="coerce"
        ).fillna(
            pd.Timedelta(0)
        )

        datos = (
            datos
            .sort_values(
                [
                    "_ORDEN_FECHA",
                    "_ORDEN_HORA"
                ],
                na_position="last"
            )
            .drop(
                columns=[
                    "_ORDEN_FECHA",
                    "_ORDEN_HORA"
                ]
            )
            .reset_index(
                drop=True
            )
        )

    creditos = (
        datos["CRÉDITO"]
        .sum(skipna=True)
    )

    debitos = (
        datos["DÉBITO"]
        .sum(skipna=True)
    )

    # ========================================================
    # BANCO ECONÓMICO
    # ========================================================

    if formato.startswith("ECO_"):

        raw = leer_excel_robusto(
            archivo,
            sheet_name="Extracto",
            header=None
        )

        def buscar_valor_por_etiqueta(
            df_raw,
            etiqueta
        ):
            objetivo = normalizar_texto(
                etiqueta
            )

            for _, fila in df_raw.iterrows():

                valores = fila.tolist()

                for posicion, valor in enumerate(
                    valores
                ):

                    texto = normalizar_texto(
                        valor
                    )

                    if objetivo in texto:

                        for candidato in valores[
                            posicion + 1:
                        ]:

                            valor_numero = numero(
                                candidato
                            )

                            if pd.notna(
                                valor_numero
                            ):
                                return valor_numero

            return np.nan

        inicial = buscar_valor_por_etiqueta(
            raw,
            "SALDO INICIAL"
        )

        final = buscar_valor_por_etiqueta(
            raw,
            "SALDO FINAL"
        )

    # ========================================================
    # BISA
    # ========================================================

    elif formato.startswith("BISA_"):

        raw = leer_excel_robusto(
            archivo,
            sheet_name="Extracto de Movimientos",
            header=None
        )

        inicial = numero(
            raw.iloc[7, 6]
        )

        final = (
            numero(
                datos.iloc[-1]["SALDO"]
            )
            if len(datos) > 0
            else inicial
        )

    # ========================================================
    # BCP
    # ========================================================

    elif formato.startswith("BCP_"):

        df = leer_tabla_movimientos(
            archivo,
            formato
        )

        cg = buscar_columna(
            df,
            "Glosa"
        )

        cs = buscar_columna(
            df,
            "Saldo"
        )

        glosa = (
            df[cg]
            .fillna("")
            .astype(str)
            .str.upper()
        )

        si = df[
            glosa.str.contains(
                "SALDO INICIAL",
                na=False
            )
        ]

        sf = df[
            glosa.str.contains(
                "SALDO AL CIERRE",
                na=False
            )
        ]

        inicial = (
            numero(
                si.iloc[0][cs]
            )
            if len(si) > 0
            else np.nan
        )

        final = (
            numero(
                sf.iloc[-1][cs]
            )
            if len(sf) > 0
            else (
                numero(
                    datos.iloc[-1]["SALDO"]
                )
                if len(datos) > 0
                else np.nan
            )
        )

    # ========================================================
    # BNB / BANCO UNIÓN / BMSC
    # RECONSTRUIR DESDE PRIMER MOVIMIENTO
    # ========================================================

    else:

        if len(datos) == 0:

            return {
                "SALDO INICIAL": np.nan,
                "CRÉDITOS": 0,
                "DÉBITOS": 0,
                "SALDO CALCULADO": np.nan,
                "SALDO FINAL": np.nan,
                "DIFERENCIA": np.nan,
                "ESTADO": "SIN MOVIMIENTOS"
            }

        primera = datos.iloc[0]

        primer_saldo = numero(
            primera["SALDO"]
        )

        primer_credito = (
            numero(
                primera["CRÉDITO"]
            )
            if pd.notna(
                primera["CRÉDITO"]
            )
            else 0
        )

        primer_debito = (
            numero(
                primera["DÉBITO"]
            )
            if pd.notna(
                primera["DÉBITO"]
            )
            else 0
        )

        inicial = (
            primer_saldo
            - primer_credito
            + primer_debito
        )

        final = numero(
            datos.iloc[-1]["SALDO"]
        )

    calculado, diferencia, estado = (
        ecuacion_saldo(
            inicial,
            creditos,
            debitos,
            final
        )
    )

    return {
        "SALDO INICIAL": inicial,
        "CRÉDITOS": creditos,
        "DÉBITOS": debitos,
        "SALDO CALCULADO": calculado,
        "SALDO FINAL": final,
        "DIFERENCIA": diferencia,
        "ESTADO": estado
    }


# ============================================================
# DESCUBRIMIENTO DE ARCHIVOS
# (reemplaza CELDA_2 / files.upload())
# ============================================================

EXTENSIONES_VALIDAS = (".xls", ".xlsx")
MARCA_EXCLUSION = "NORMALIZADO"

# Archivos generados por el propio sistema: nunca son extractos de
# entrada (D-20). Se comparan sobre el nombre en mayúsculas y solo
# para .xlsx: ORIGEN*.xlsx y EXTRACTO_HISTORICO_*.xlsx.
PREFIJOS_SALIDA_SISTEMA = (
    "ORIGEN",
    "EXTRACTO_HISTORICO_"
)


def descubrir_archivos(carpeta_entrada):
    """
    Lista los extractos a procesar dentro de una carpeta local.

    Reglas de descubrimiento (requisito de esta etapa, no son
    reglas de negocio del motor de normalización):
      - solo se consideran archivos con extensión .xls o .xlsx,
        sin distinguir mayúsculas/minúsculas;
      - se ignora cualquier archivo cuyo nombre contenga
        "NORMALIZADO" (sin distinguir mayúsculas/minúsculas), para
        no reprocesar una salida de una corrida anterior si quedó
        en la misma carpeta;
      - se ignora cualquier otro archivo que no sea .xls/.xlsx.

    Devuelve un diccionario {nombre_original: ruta_completa}, de
    forma que el resto del motor pueda leer cada archivo desde su
    ruta real, mientras que solo el nombre original se registra en
    ARCHIVO ORIGEN y se usa en las comparaciones internas.

    No modifica, renombra ni elimina ningún archivo.
    """

    if not os.path.isdir(carpeta_entrada):
        raise FileNotFoundError(
            f"❌ La carpeta de entrada no existe: {carpeta_entrada}"
        )

    archivos = {}

    for nombre in sorted(os.listdir(carpeta_entrada)):

        ruta = os.path.join(carpeta_entrada, nombre)

        if not os.path.isfile(ruta):
            continue

        _, extension = os.path.splitext(nombre)

        if extension.lower() not in EXTENSIONES_VALIDAS:
            continue

        if MARCA_EXCLUSION in nombre.upper():
            continue

        if (
            extension.lower() == ".xlsx"
            and nombre.upper().startswith(
                PREFIJOS_SALIDA_SISTEMA
            )
        ):
            continue

        archivos[nombre] = ruta

    return archivos


# ============================================================
# ORQUESTACIÓN DEL MOTOR
# (reconstruye CELDA_3, sin Google Colab ni Google Drive)
# ============================================================

def ejecutar_motor(carpeta_entrada, ruta_salida):
    """
    Punto de entrada único del motor.

    Parámetros
    ----------
    carpeta_entrada : str
        Carpeta local donde ya están descargados los extractos
        bancarios originales (.xls / .xlsx), con su nombre de
        archivo original intacto. El motor NO descarga nada de
        Google Drive: eso es responsabilidad de quien llama a
        esta función.
    ruta_salida : str
        Ruta local completa (incluyendo nombre de archivo) donde
        se debe escribir el resultado. Por requisito de esta
        etapa, el llamador debe pasar una ruta que termine en
        "NORMALIZADO.xlsx".

    Devuelve
    --------
    dict con las tablas generadas (para inspección/registro por
    parte de quien llama) y las rutas de los archivos finales:
        {
            "df_final": DataFrame,
            "df_validacion": DataFrame,
            "resumen": DataFrame,
            "df_resultado_archivos": DataFrame,
            "df_deteccion_final": DataFrame,
            "ruta_salida": str,
            "ruta_lists_csv": str,
        }

    Además de NORMALIZADO.xlsx, se genera en la misma carpeta un
    archivo LISTS.csv (mismo df_final ya validado, columnas y
    orden de COLUMNAS_LISTS, UTF-8 con BOM). No reemplaza ni
    modifica NORMALIZADO.xlsx.

    Lanza ValueError (o RuntimeError si faltan dependencias) con
    el mismo criterio que las celdas originales si cualquier
    validación crítica falla. En ese caso NO se genera ningún
    archivo de salida ni se toca ninguno de los extractos
    originales.
    """

    verificar_dependencias()

    print("============================================================")
    print("CONTROL DE DEPÓSITOS CBBA")
    print("PROCESAMIENTO AUTOMÁTICO")
    print("============================================================")

    # ========================================================
    # 0. DESCUBRIR ARCHIVOS (reemplaza CELDA_2)
    # ========================================================

    mapa_archivos = descubrir_archivos(carpeta_entrada)

    if not mapa_archivos:

        raise ValueError(
            "❌ PROCESO DETENIDO: no se encontraron archivos "
            f".xls/.xlsx para procesar en {carpeta_entrada}."
        )

    print(
        f"\n📂 {len(mapa_archivos)} archivo(s) encontrado(s) en "
        f"'{carpeta_entrada}':"
    )

    for nombre in mapa_archivos:
        print(" •", nombre)

    # ========================================================
    # CONFIGURAR LOTE
    # ========================================================

    fecha_carga = pd.Timestamp.now()

    lote = fecha_carga.strftime(
        "%Y%m%d_%H%M%S"
    )

    # ========================================================
    # 1. DETECTAR FORMATOS
    # ========================================================

    detecciones = []

    print(
        "\n🔎 DETECTANDO BANCOS Y CUENTAS...\n"
    )

    for nombre, ruta in mapa_archivos.items():

        try:

            formato = detectar_formato(
                ruta
            )

            detecciones.append({
                "ARCHIVO": nombre,
                "FORMATO": formato,
                "ESTADO": (
                    "OK"
                    if formato != "NO_RECONOCIDO"
                    else "ERROR"
                )
            })

            if formato == "NO_RECONOCIDO":

                print(
                    f"❌ {nombre} → "
                    "NO RECONOCIDO"
                )

            else:

                print(
                    f"✅ {nombre} → "
                    f"{formato}"
                )

        except Exception as e:

            detecciones.append({
                "ARCHIVO": nombre,
                "FORMATO": "ERROR",
                "ESTADO": str(e)
            })

            print(
                f"❌ {nombre}: "
                f"{type(e).__name__} | {repr(e)}"
            )

    df_deteccion_final = pd.DataFrame(
        detecciones
    )

    # ========================================================
    # BLOQUEAR SI HAY ARCHIVO NO RECONOCIDO
    # ========================================================

    errores_deteccion = (
        df_deteccion_final[
            "FORMATO"
        ]
        .isin(
            [
                "NO_RECONOCIDO",
                "ERROR"
            ]
        )
        .sum()
    )

    if errores_deteccion > 0:

        raise ValueError(
            "❌ PROCESO DETENIDO: "
            "hay archivos no reconocidos."
        )

    # ========================================================
    # CONTROL DE FORMATOS REPETIDOS
    # ========================================================

    formatos_repetidos = (
        df_deteccion_final[
            "FORMATO"
        ]
        .duplicated(
            keep=False
        )
    )

    if formatos_repetidos.any():

        print(
            "\n⚠️ FORMATOS REPETIDOS:"
        )

        print(
            df_deteccion_final[
                formatos_repetidos
            ].to_string(index=False)
        )

        raise ValueError(
            "❌ No cargues dos archivos de la misma "
            "cuenta en la misma ejecución."
        )

    print(
        f"\n✅ {len(df_deteccion_final)} "
        "formatos reconocidos."
    )

    # ========================================================
    # 2. NORMALIZAR
    # ========================================================

    print(
        "\n🔄 NORMALIZANDO MOVIMIENTOS...\n"
    )

    tablas = []

    resultados_archivos = []

    for _, fila in df_deteccion_final.iterrows():

        nombre = fila["ARCHIVO"]
        formato = fila["FORMATO"]
        ruta = mapa_archivos[nombre]

        try:

            resultado = normalizar_archivo(
                ruta,
                formato,
                lote,
                fecha_carga,
                nombre_origen=nombre
            )

            tablas.append(
                resultado
            )

            resultados_archivos.append({
                "ARCHIVO": nombre,
                "FORMATO": formato,
                "MOVIMIENTOS": len(resultado),
                "NORMALIZACIÓN": "OK"
            })

            print(
                f"✅ {formato}: "
                f"{len(resultado):,} movimientos"
            )

        except Exception as e:

            resultados_archivos.append({
                "ARCHIVO": nombre,
                "FORMATO": formato,
                "MOVIMIENTOS": 0,
                "NORMALIZACIÓN": "ERROR"
            })

            print(
                f"❌ {formato}: {e}"
            )

    df_resultado_archivos = pd.DataFrame(
        resultados_archivos
    )

    errores_normalizacion = (
        df_resultado_archivos[
            "NORMALIZACIÓN"
        ]
        .eq("ERROR")
        .sum()
    )

    if errores_normalizacion > 0:

        print(
            "\n❌ ARCHIVOS CON ERROR:"
        )

        print(
            df_resultado_archivos[
                df_resultado_archivos[
                    "NORMALIZACIÓN"
                ] == "ERROR"
            ].to_string(index=False)
        )

        raise ValueError(
            "❌ PROCESO DETENIDO: "
            "falló la normalización de al menos un archivo."
        )

    # ========================================================
    # 3. UNIR TODO
    # ========================================================

    df_final = pd.concat(
        tablas,
        ignore_index=True
    )

    print(
        f"\n✅ Movimientos normalizados: "
        f"{len(df_final):,}"
    )

    # ========================================================
    # 4. GARANTIZAR TIPOS DE FECHA
    # ========================================================

    df_final[
        "FECHA MOVIMIENTO"
    ] = pd.to_datetime(
        df_final[
            "FECHA MOVIMIENTO"
        ],
        errors="coerce"
    )

    df_final[
        "FECHA CONFIRMACIÓN"
    ] = pd.to_datetime(
        df_final[
            "FECHA CONFIRMACIÓN"
        ],
        errors="coerce"
    )

    df_final[
        "FECHA DE CARGA"
    ] = pd.to_datetime(
        df_final[
            "FECHA DE CARGA"
        ],
        errors="coerce"
    )

    # ========================================================
    # 5. AUDITORÍA ESTRUCTURAL
    # ========================================================

    print(
        "\n🔍 AUDITORÍA ESTRUCTURAL..."
    )

    duplicados = (
        df_final[
            "CLAVE TRANSACCIÓN"
        ]
        .duplicated()
        .sum()
    )

    codigos_vacios = (
        df_final[
            "CÓDIGO DE ASIGNACIÓN"
        ]
        .fillna("")
        .eq("")
        .sum()
    )

    sin_importe = (
        df_final[
            "IMPORTE"
        ]
        .isna()
        .sum()
    )

    importe_cero = (
        df_final[
            "IMPORTE"
        ]
        .fillna(0)
        .eq(0)
        .sum()
    )

    sin_tipo = (
        df_final[
            "TIPO MOVIMIENTO"
        ]
        .fillna("")
        .eq("")
        .sum()
    )

    doble_movimiento = (
        (
            df_final["DÉBITO"].notna()
            &
            df_final["CRÉDITO"].notna()
        )
        .sum()
    )

    fechas_invalidas = (
        df_final[
            "FECHA MOVIMIENTO"
        ]
        .isna()
        .sum()
    )

    print(
        f"   Claves duplicadas: {duplicados}"
    )

    print(
        f"   Códigos vacíos: {codigos_vacios}"
    )

    print(
        f"   Sin importe: {sin_importe}"
    )

    print(
        f"   Importe cero: {importe_cero}"
    )

    print(
        f"   Sin tipo: {sin_tipo}"
    )

    print(
        f"   Débito + crédito simultáneo: "
        f"{doble_movimiento}"
    )

    print(
        f"   Fechas inválidas: "
        f"{fechas_invalidas}"
    )

    errores_estructurales = (
        duplicados
        + codigos_vacios
        + sin_importe
        + importe_cero
        + sin_tipo
        + doble_movimiento
        + fechas_invalidas
    )

    if errores_estructurales > 0:

        raise ValueError(
            "❌ PROCESO DETENIDO: "
            "la auditoría estructural encontró problemas."
        )

    print(
        "\n✅ AUDITORÍA ESTRUCTURAL SUPERADA"
    )

    # ========================================================
    # 6. CONTROL DEL AÑO
    # ========================================================

    anios_detectados = (
        df_final[
            "FECHA MOVIMIENTO"
        ]
        .dt.year
        .dropna()
        .unique()
        .tolist()
    )

    print(
        f"\n📅 Años detectados: "
        f"{sorted(anios_detectados)}"
    )

    if any(
        anio != 2026
        for anio in anios_detectados
    ):

        raise ValueError(
            "❌ EXPORTACIÓN BLOQUEADA: "
            "se detectaron movimientos fuera del año 2026."
        )

    print(
        "✅ Todos los movimientos corresponden a 2026"
    )

    # ========================================================
    # 7. VALIDAR SALDOS
    # ========================================================

    print(
        "\n💰 VALIDANDO SALDOS BANCARIOS...\n"
    )

    validaciones = []

    for _, fila in df_deteccion_final.iterrows():

        nombre = fila["ARCHIVO"]
        formato = fila["FORMATO"]
        ruta = mapa_archivos[nombre]

        datos_archivo = df_final[
            df_final[
                "ARCHIVO ORIGEN"
            ] == nombre
        ].copy()

        resultado = validar_archivo(
            ruta,
            formato,
            datos_archivo
        )

        validaciones.append({
            "ARCHIVO": nombre,
            "FORMATO": formato,
            "MOVIMIENTOS": len(datos_archivo),
            **resultado
        })

        icono = (
            "✅"
            if resultado["ESTADO"] == "OK"
            else "ℹ️"
            if resultado["ESTADO"] == "SIN MOVIMIENTOS"
            else "❌"
        )

        print(
            f"{icono} {formato}: "
            f"{resultado['ESTADO']}"
        )

    df_validacion = pd.DataFrame(
        validaciones
    )

    # ========================================================
    # BISA SIN MOVIMIENTOS ES VÁLIDO
    # ========================================================

    estados_invalidos = (
        ~df_validacion[
            "ESTADO"
        ]
        .isin(
            [
                "OK",
                "SIN MOVIMIENTOS"
            ]
        )
    )

    if estados_invalidos.any():

        print(
            "\n❌ HAY CUENTAS QUE NO CUADRAN:"
        )

        print(
            df_validacion[
                estados_invalidos
            ].to_string(index=False)
        )

        raise ValueError(
            "❌ EXPORTACIÓN BLOQUEADA."
        )

    print(
        "\n✅ INTEGRIDAD FINANCIERA SUPERADA"
    )

    # ========================================================
    # 8. RESUMEN
    # ========================================================

    resumen = (

        df_final
        .groupby(
            [
                "BANCO",
                "CUENTA BANCARIA",
                "MONEDA"
            ],
            dropna=False
        )
        .agg(

            MOVIMIENTOS=(
                "IMPORTE",
                "size"
            ),

            TOTAL_DEBITOS=(
                "DÉBITO",
                "sum"
            ),

            TOTAL_CREDITOS=(
                "CRÉDITO",
                "sum"
            ),

            PRIMERA_FECHA=(
                "FECHA MOVIMIENTO",
                "min"
            ),

            ULTIMA_FECHA=(
                "FECHA MOVIMIENTO",
                "max"
            )

        )
        .reset_index()
    )

    # ========================================================
    # 9. ORDENAR BASE FINAL
    # ========================================================

    df_final = (

        df_final
        .sort_values(
            [
                "FECHA MOVIMIENTO",
                "HORA MOVIMIENTO",
                "BANCO",
                "CUENTA BANCARIA"
            ],
            na_position="last"
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # 10. RUTA DE SALIDA
    #
    # A diferencia de la celda original (que generaba un nombre
    # con timestamp, p. ej. CONTROL_DEPOSITOS_CBBA_PRUEBA_<ts>.xlsx,
    # y luego lo descargaba con files.download()), este motor
    # escribe siempre en la ruta fija indicada por el llamador
    # (NORMALIZADO.xlsx), y es la orquestación quien decide dónde
    # queda ese archivo y qué hacer con él después (subirlo a
    # Drive). El contenido y las hojas generadas no cambian.
    # ========================================================

    carpeta_salida = os.path.dirname(
        os.path.abspath(ruta_salida)
    )

    if carpeta_salida:
        os.makedirs(carpeta_salida, exist_ok=True)

    # ========================================================
    # 10-B. GENERAR LISTS.csv (SALIDA ADICIONAL)
    #
    # Requisito de esta etapa: además de NORMALIZADO.xlsx (que no
    # se toca ni se reemplaza), generar un archivo plano LISTS.csv
    # en la misma carpeta de salida, a partir del mismo df_final ya
    # validado (auditoría estructural, control de año y validación
    # de saldos ya superados en los pasos anteriores), restringido
    # a las columnas y al orden exacto de COLUMNAS_LISTS, con
    # codificación UTF-8 con BOM. Esto es una exportación adicional
    # de infraestructura: no modifica ningún dato, cálculo ni
    # validación del motor.
    # ========================================================

    ruta_lists_csv = os.path.join(
        carpeta_salida,
        "LISTS.csv"
    )

    df_final[COLUMNAS_LISTS].to_csv(
        ruta_lists_csv,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # 11. GENERAR EXCEL
    # ========================================================

    with pd.ExcelWriter(
        ruta_salida,
        engine="openpyxl"
    ) as writer:

        df_final.to_excel(
            writer,
            sheet_name="LISTS",
            index=False
        )

        df_validacion.to_excel(
            writer,
            sheet_name="VALIDACION",
            index=False
        )

        resumen.to_excel(
            writer,
            sheet_name="RESUMEN",
            index=False
        )

        df_resultado_archivos.to_excel(
            writer,
            sheet_name="DIAGNOSTICO",
            index=False
        )

    # ========================================================
    # 12. APLICAR FORMATO EXCEL COMPATIBLE CON LISTS
    # ========================================================

    wb = load_workbook(
        ruta_salida
    )

    ws = wb["LISTS"]

    # ========================================================
    # IDENTIFICAR COLUMNAS POR ENCABEZADO
    # ========================================================

    columnas_excel = {}

    for celda in ws[1]:

        columnas_excel[
            celda.value
        ] = celda.column

    # ========================================================
    # FORMATO FECHA MOVIMIENTO
    # ========================================================

    if "FECHA MOVIMIENTO" in columnas_excel:

        col = columnas_excel[
            "FECHA MOVIMIENTO"
        ]

        for fila in range(
            2,
            ws.max_row + 1
        ):

            celda = ws.cell(
                row=fila,
                column=col
            )

            if celda.value is not None:

                celda.number_format = (
                    "mm/dd/yy"
                )

    # ========================================================
    # FORMATO FECHA CONFIRMACIÓN
    # ========================================================

    if "FECHA CONFIRMACIÓN" in columnas_excel:

        col = columnas_excel[
            "FECHA CONFIRMACIÓN"
        ]

        for fila in range(
            2,
            ws.max_row + 1
        ):

            celda = ws.cell(
                row=fila,
                column=col
            )

            if celda.value is not None:

                celda.number_format = (
                    "mm/dd/yy hh:mm AM/PM"
                )

    # ========================================================
    # FORMATO FECHA DE CARGA
    # ========================================================

    if "FECHA DE CARGA" in columnas_excel:

        col = columnas_excel[
            "FECHA DE CARGA"
        ]

        for fila in range(
            2,
            ws.max_row + 1
        ):

            celda = ws.cell(
                row=fila,
                column=col
            )

            if celda.value is not None:

                celda.number_format = (
                    "mm/dd/yy hh:mm AM/PM"
                )

    # ========================================================
    # FORMATO DE NÚMEROS
    # ========================================================

    for nombre_columna in [
        "IMPORTE",
        "DÉBITO",
        "CRÉDITO",
        "SALDO"
    ]:

        if nombre_columna in columnas_excel:

            col = columnas_excel[
                nombre_columna
            ]

            for fila in range(
                2,
                ws.max_row + 1
            ):

                celda = ws.cell(
                    row=fila,
                    column=col
                )

                if celda.value is not None:

                    celda.number_format = (
                        "0.00"
                    )

    # ========================================================
    # CUENTA Y CÓDIGO COMO TEXTO VISUAL
    # ========================================================

    for nombre_columna in [
        "CUENTA BANCARIA",
        "CÓDIGO DE ASIGNACIÓN",
        "CLAVE TRANSACCIÓN"
    ]:

        if nombre_columna in columnas_excel:

            col = columnas_excel[
                nombre_columna
            ]

            for fila in range(
                2,
                ws.max_row + 1
            ):

                celda = ws.cell(
                    row=fila,
                    column=col
                )

                if celda.value is not None:

                    celda.number_format = "@"

                    celda.value = str(
                        celda.value
                    )

    # ========================================================
    # AJUSTAR FORMATO DE LAS FECHAS DEL RESUMEN
    # ========================================================

    ws_resumen = wb["RESUMEN"]

    encabezados_resumen = {}

    for celda in ws_resumen[1]:

        encabezados_resumen[
            celda.value
        ] = celda.column

    for nombre_columna in [
        "PRIMERA_FECHA",
        "ULTIMA_FECHA"
    ]:

        if nombre_columna in encabezados_resumen:

            col = encabezados_resumen[
                nombre_columna
            ]

            for fila in range(
                2,
                ws_resumen.max_row + 1
            ):

                celda = ws_resumen.cell(
                    row=fila,
                    column=col
                )

                if celda.value is not None:

                    celda.number_format = (
                        "mm/dd/yy"
                    )

    # ========================================================
    # CREAR TABLA EXCEL PARA POWER AUTOMATE / MICROSOFT LISTS
    # ========================================================

    ws_lists = wb["LISTS"]

    # La tabla se crea únicamente como estructura de Excel para que
    # Power Automate pueda enumerar las filas. No modifica valores,
    # cálculos, reglas de negocio ni el orden de COLUMNAS_LISTS.
    if (
        ws_lists.max_row >= 2
        and ws_lists.max_column >= 1
    ):

        nombres_tablas = {
            tabla.name
            for tabla in ws_lists.tables.values()
        }

        if "tblLISTS" not in nombres_tablas:

            ultima_celda = ws_lists.cell(
                row=ws_lists.max_row,
                column=ws_lists.max_column
            ).coordinate

            tabla_lists = Table(
                displayName="tblLISTS",
                ref=f"A1:{ultima_celda}"
            )

            ws_lists.add_table(
                tabla_lists
            )

    # ========================================================
    # GUARDAR CAMBIOS
    # ========================================================

    wb.save(
        ruta_salida
    )

    # ========================================================
    # 13. RESULTADO FINAL
    # ========================================================

    print(
        "\n============================================================"
    )

    print(
        "🎯 PROCESO COMPLETADO CORRECTAMENTE"
    )

    print(
        "============================================================"
    )

    print(
        f"Archivos procesados: "
        f"{len(df_deteccion_final)}"
    )

    print(
        f"Movimientos: "
        f"{len(df_final):,}"
    )

    print(
        f"Claves duplicadas: "
        f"{duplicados}"
    )

    print(
        f"Códigos vacíos: "
        f"{codigos_vacios}"
    )

    print(
        f"Errores estructurales: "
        f"{errores_estructurales}"
    )

    print(
        "Integridad bancaria: ✅"
    )

    print(
        "\n📅 FORMATO PARA MICROSOFT LISTS:"
    )

    print(
        "FECHA MOVIMIENTO   → MM/DD/YY"
    )

    print(
        "FECHA CONFIRMACIÓN → MM/DD/YY HH:MM AM/PM"
    )

    print(
        "FECHA DE CARGA     → MM/DD/YY HH:MM AM/PM"
    )

    print(
        f"\n📄 Archivo generado:"
    )

    print(
        ruta_salida
    )

    print(
        f"\n📄 Archivo adicional generado (LISTS.csv, UTF-8 con BOM):"
    )

    print(
        ruta_lists_csv
    )

    print(
        "\n🚫 MICROSOFT LISTS NO FUE MODIFICADO"
    )

    print(
        "============================================================"
    )

    # ========================================================
    # 14. MOSTRAR RESUMEN
    # (reemplaza display() por salida textual equivalente)
    # ========================================================

    print(
        "\nRESUMEN POR CUENTA:"
    )

    print(
        resumen.to_string(index=False)
    )

    print(
        "\nVALIDACIÓN:"
    )

    print(
        df_validacion.to_string(index=False)
    )

    # NOTA: aquí terminaba CELDA_3 con files.download(nombre_archivo).
    # Ese paso se elimina deliberadamente: subir NORMALIZADO.xlsx a
    # Google Drive es responsabilidad de la orquestación externa
    # (Cowork), no de este motor.

    # ========================================================
    # 15. CAPTURA ÍNTEGRA DE ORIGEN (P1, pasiva)
    #
    # Genera ORIGEN.xlsx (DATOS_ORIGINALES, METADATOS_EXTRACTO,
    # METADATOS_EXTRA, MAPA_ORIGEN) en la carpeta de salida, leyendo
    # los extractos originales por su cuenta. No modifica df_final,
    # NORMALIZADO.xlsx ni LISTS.csv, y un fallo aquí NUNCA detiene
    # el proceso (solo queda registrado en "origen_estado").
    # ========================================================
    ruta_origen = os.path.join(
        carpeta_salida or ".",
        "ORIGEN.xlsx"
    )

    try:
        import importlib.util as _iu

        _ruta_mod = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "captura_origen.py"
        )
        _spec = _iu.spec_from_file_location(
            "captura_origen",
            _ruta_mod
        )
        _cap = _iu.module_from_spec(_spec)
        _spec.loader.exec_module(_cap)

        origen_estado = _cap.generar_origen_seguro(
            mapa_archivos,
            df_deteccion_final,
            tablas,
            df_validacion,
            lote,
            fecha_carga,
            ruta_origen,
            {
                "hojas_validas": HOJAS_VALIDAS,
                "encabezados_esperados": ENCABEZADOS_ESPERADOS,
                "encontrar_fila_encabezado": encontrar_fila_encabezado,
            }
        )

    except Exception as e:

        origen_estado = {
            "estado": "ERROR",
            "error": f"{type(e).__name__}: {e}",
            "ruta_origen": None
        }

    if origen_estado.get("estado") == "OK":

        print(
            f"\n📄 Archivo técnico de origen (ORIGEN.xlsx): "
            f"{ruta_origen}"
        )

    else:

        print(
            "\n⚠️ ORIGEN.xlsx no se generó "
            "(no afecta NORMALIZADO.xlsx ni LISTS.csv): "
            f"{origen_estado.get('error')}"
        )

    return {
        "df_final": df_final,
        "df_validacion": df_validacion,
        "resumen": resumen,
        "df_resultado_archivos": df_resultado_archivos,
        "df_deteccion_final": df_deteccion_final,
        "ruta_salida": ruta_salida,
        "ruta_lists_csv": ruta_lists_csv,
        "origen_estado": origen_estado
    }


# ============================================================
# EJECUCIÓN COMO SCRIPT
# ============================================================

if __name__ == "__main__":

    import sys

    if len(sys.argv) != 3:

        print(
            "Uso: python motor_control_depositos_cbba.py "
            "<carpeta_entrada> <ruta_salida_NORMALIZADO.xlsx>"
        )

        sys.exit(1)

    carpeta_entrada_cli = sys.argv[1]
    ruta_salida_cli = sys.argv[2]

    ejecutar_motor(
        carpeta_entrada_cli,
        ruta_salida_cli
    )
