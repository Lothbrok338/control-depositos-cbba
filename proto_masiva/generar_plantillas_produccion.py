"""Genera desde cero las DOS plantillas definitivas de trabajo de la confirmación masiva P9.

    python proto_masiva/generar_plantillas_produccion.py

    xlsx/Plantilla_Confirmacion_Masiva_P9.xlsx   VACÍA, lista para entregar al usuario
    xlsx/Ejemplo_Confirmacion_Masiva_P9.xlsx     misma plantilla con 3 filas FICTICIAS

Bancos y cuentas NO se escriben aquí: salen de `catalogo_p9.extraer()` (Main_Screen del checkpoint 3b407e2).
XLSX estándar: sin macros, sin VBA, sin conexiones externas. Salida determinista (mismo SHA-256 en cada ejecución).
Antes de guardar, `verificar()` comprueba la estructura y aborta si algo no cumple; se vuelve a ejecutar sobre los bytes finales.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.table import Table, TableStyleInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto_masiva import catalogo_p9  # noqa: E402
from proto_masiva.contrato_plantilla import (ARCHIVO_EJEMPLO, ARCHIVO_PLANTILLA, ENCABEZADOS, HOJA_CARGA,  # noqa: E402
                                              HOJA_CATALOGOS, MONEDAS, NOMBRE_TABLA, OBLIGATORIAS)

SALIDA = Path(__file__).resolve().parent / "xlsx"
TITULO = "P9 — CONFIRMACIÓN MASIVA DE DEPÓSITOS"
INSTRUCCION = "Complete una fila por depósito. No modifique los encabezados."
LEYENDA = "Encabezado granate = columna obligatoria · gris = opcional. BANCO, CUENTA_BANCARIA y MONEDA se eligen de la lista."
FILA_TITULO, FILA_INSTRUCCION, FILA_LEYENDA, FILA_ENC, PRIMERA = 1, 2, 3, 5, 6
FILAS_FORMATO = 500          # formatos, listas y reglas preconfigurados hasta esta fila de datos (la tabla crece sola)
ULTIMA = PRIMERA + FILAS_FORMATO - 1
GRANATE, GRIS, AMBAR, ROJO_CLARO = "7B1632", "6B6F73", "FFE9B3", "F8C9C9"
FECHA_FIJA, FECHA_ZIP = datetime(2026, 10, 5), (2026, 10, 5, 0, 0, 0)
Q = f"'{HOJA_CATALOGOS}'"
LETRAS = "ABCDEFGHI"
COL = {nombre: LETRAS[i] for i, nombre in enumerate(ENCABEZADOS)}


# ------------------------------------------------------------------------------------------------ catálogo en la hoja oculta
def rangos(cat):
    nb, nc = len(cat["bancos"]), len(cat["cuentas"])
    return {"bancos": f"{Q}!$A$2:$A${1 + nb}", "banco_de_cuenta": f"{Q}!$E$2:$E${1 + nc}",
            "cuentas": f"{Q}!$F$2:$F${1 + nc}", "moneda_de_cuenta": f"{Q}!$H$2:$H${1 + nc}"}


def formula_cuentas(cat, celda_banco):
    """Lista dependiente SIN macros ni INDIRECT: devuelve solo las cuentas del banco elegido (rango contiguo en el catálogo);
    si BANCO está vacío o no existe, muestra las 13 cuentas."""
    r = rangos(cat)
    pos = f"MATCH({celda_banco},{r['banco_de_cuenta']},0)"
    return (f"IF(ISNUMBER({pos}),OFFSET({Q}!$F$2,{pos}-1,0,COUNTIF({r['banco_de_cuenta']},{celda_banco}),1),{r['cuentas']})")


def hoja_catalogos(wb, cat):
    ws = wb.create_sheet(HOJA_CATALOGOS)
    for col, titulo in zip("ACEFGH", ("BANCO", "MONEDA", "BANCO_DE_LA_CUENTA", "CUENTA", "ETIQUETA", "MONEDA_DE_LA_CUENTA")):
        ws[f"{col}1"] = titulo
        ws[f"{col}1"].font = Font(bold=True)
    for i, b in enumerate(cat["bancos"], 2):
        ws[f"A{i}"] = b
    for i, m in enumerate(MONEDAS, 2):
        ws[f"C{i}"] = m
    for i, c in enumerate(cat["cuentas"], 2):
        ws[f"E{i}"], ws[f"F{i}"], ws[f"G{i}"], ws[f"H{i}"] = c["banco"], c["cuenta"], c["etiqueta"], c["moneda"]
        ws[f"F{i}"].number_format = "@"
    ws["J1"] = (f"Generado por proto_masiva/generar_plantillas_produccion.py desde {cat['fuente']['archivo']} "
                f"@ {cat['fuente']['checkpoint_commit'][:7]}. No editar a mano.")
    for col, ancho in zip("ACEFGHJ", (18, 10, 22, 22, 30, 20, 60)):
        ws.column_dimensions[col].width = ancho
    ws.sheet_state = "hidden"
    return ws


# ------------------------------------------------------------------------------------------------ hoja de carga
def validaciones(ws, cat):
    def lista(col, formula, titulo, mensaje):
        v = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=True, errorStyle="stop",
                           errorTitle=titulo, error=mensaje)
        v.add(f"{col}{PRIMERA}:{col}{ULTIMA}")
        ws.add_data_validation(v)

    lista(COL["BANCO"], rangos(cat)["bancos"], "BANCO", "Elija un banco de la lista.")
    lista(COL["CUENTA_BANCARIA"], formula_cuentas(cat, f"${COL['BANCO']}{PRIMERA}"), "CUENTA_BANCARIA",
          "Elija una cuenta de la lista (se filtra por el BANCO de la fila).")
    lista(COL["MONEDA"], '"' + ",".join(MONEDAS) + '"', "MONEDA", "Use BOB o USD.")
    importe = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True, showErrorMessage=True,
                             errorStyle="stop", errorTitle="IMPORTE", error="El importe debe ser un número mayor que 0.")
    importe.add(f"{COL['IMPORTE']}{PRIMERA}:{COL['IMPORTE']}{ULTIMA}")
    ws.add_data_validation(importe)
    for nombre in ("ESTUDIANTE", "SOLICITADO_POR", "SEDE"):
        texto = DataValidation(type="textLength", operator="between", formula1="1", formula2="255", allow_blank=True,
                               showErrorMessage=True, errorStyle="stop", errorTitle=nombre,
                               error="Obligatorio: texto de hasta 255 caracteres.")
        texto.add(f"{COL[nombre]}{PRIMERA}:{COL[nombre]}{ULTIMA}")
        ws.add_data_validation(texto)


def reglas_visuales(ws, cat):
    """Solo ayudas visuales (no bloquean): obligatorios vacíos en filas en uso, cuenta que no es del banco, moneda distinta a la de la cuenta."""
    r = rangos(cat)
    a, b, e = (COL[n] for n in ("BANCO", "CUENTA_BANCARIA", "MONEDA"))
    obligatorias = f"{COL[OBLIGATORIAS[0]]}{PRIMERA}:{COL[OBLIGATORIAS[-1]]}{ULTIMA}"
    ws.conditional_formatting.add(obligatorias, FormulaRule(
        formula=[f'AND(COUNTA(${LETRAS[0]}{PRIMERA}:${LETRAS[-1]}{PRIMERA})>0,{LETRAS[0]}{PRIMERA}="")'],
        fill=PatternFill("solid", bgColor=AMBAR)))
    ws.conditional_formatting.add(f"{b}{PRIMERA}:{b}{ULTIMA}", FormulaRule(
        formula=[f'AND(${a}{PRIMERA}<>"",${b}{PRIMERA}<>"",COUNTIFS({r["banco_de_cuenta"]},${a}{PRIMERA},{r["cuentas"]},${b}{PRIMERA})=0)'],
        fill=PatternFill("solid", bgColor=ROJO_CLARO)))
    ws.conditional_formatting.add(f"{e}{PRIMERA}:{e}{ULTIMA}", FormulaRule(
        formula=[f'AND(${b}{PRIMERA}<>"",${e}{PRIMERA}<>"",IFERROR(INDEX({r["moneda_de_cuenta"]},MATCH(${b}{PRIMERA},{r["cuentas"]},0))<>${e}{PRIMERA},FALSE))'],
        fill=PatternFill("solid", bgColor=ROJO_CLARO)))


def filas_ejemplo(cat):
    """Tres filas ficticias con bancos/cuentas VÁLIDOS tomados del catálogo (primera cuenta, primera cuenta USD, última cuenta)."""
    cuentas = cat["cuentas"]
    elegidas = [cuentas[0], next(c for c in cuentas if c["moneda"] == "USD"), cuentas[-1]]
    importes = (1000.00, 250.50, 500.00)
    return [(c["banco"], c["cuenta"], f"EJEMPLO-{i:04d}", importes[i - 1], c["moneda"], f"ESTUDIANTE EJEMPLO {i}",
             "SOLICITANTE EJEMPLO", "COCHABAMBA", "FILA DE EJEMPLO: borrar") for i, c in enumerate(elegidas, 1)]


def hoja_carga(wb, cat, con_ejemplos, filas=None):
    ws = wb.active
    ws.title = HOJA_CARGA
    ws.sheet_properties.tabColor = GRANATE
    ultima_col = LETRAS[len(ENCABEZADOS) - 1]
    textos = ((FILA_TITULO, TITULO, Font(bold=True, size=16, color=GRANATE), 28),
              (FILA_INSTRUCCION, ("EJEMPLO con datos FICTICIOS, no usar para confirmar. " if con_ejemplos else "") + INSTRUCCION,
               Font(bold=True, size=11, color="34373A"), 20),
              (FILA_LEYENDA, LEYENDA, Font(size=9, color="62666A"), 16))
    for fila, texto, fuente, alto in textos:
        ws.merge_cells(f"A{fila}:{ultima_col}{fila}")
        ws[f"A{fila}"] = texto
        ws[f"A{fila}"].font = fuente
        ws[f"A{fila}"].alignment = Alignment(vertical="center")
        ws.row_dimensions[fila].height = alto
    for i, nombre in enumerate(ENCABEZADOS):
        c = ws.cell(FILA_ENC, i + 1, nombre)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=GRANATE if nombre in OBLIGATORIAS else GRIS)
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[FILA_ENC].height = 22
    filas = list(filas) if filas is not None else (filas_ejemplo(cat) if con_ejemplos else [])
    for r, fila in enumerate(filas, PRIMERA):
        for c, valor in enumerate(fila, 1):
            ws.cell(r, c, valor)
    for r in range(PRIMERA, ULTIMA + 1):
        ws[f"{COL['CUENTA_BANCARIA']}{r}"].number_format = "@"
        ws[f"{COL['CODIGO_ASIGNACION']}{r}"].number_format = "@"
        ws[f"{COL['IMPORTE']}{r}"].number_format = "#,##0.00"
        ws[f"{COL['MONEDA']}{r}"].alignment = Alignment(horizontal="center")
        ws[f"{COL['OBSERVACION']}{r}"].alignment = Alignment(wrap_text=True, vertical="top")
    n = max(len(filas), 1)  # una tabla de Excel conserva siempre una fila de datos: la «vacía» tiene una fila en blanco
    ref = f"A{FILA_ENC}:{ultima_col}{FILA_ENC + n}"
    tabla = Table(displayName=NOMBRE_TABLA, ref=ref)
    tabla.autoFilter = AutoFilter(ref=ref)
    tabla.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(tabla)
    validaciones(ws, cat)
    reglas_visuales(ws, cat)
    ws.freeze_panes = f"A{PRIMERA}"
    ws.page_setup.orientation, ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = "landscape", 1, 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = f"{FILA_ENC}:{FILA_ENC}"
    for nombre, ancho in zip(ENCABEZADOS, (18, 24, 22, 14, 11, 30, 28, 16, 36)):
        ws.column_dimensions[COL[nombre]].width = ancho
    return ws


# ------------------------------------------------------------------------------------------------ verificación y guardado
def verificar(datos: bytes, cat: dict, con_ejemplos) -> None:
    """Aborta con la lista completa de incumplimientos."""
    fallos = []
    with zipfile.ZipFile(io.BytesIO(datos)) as z:
        nombres, crudo = z.namelist(), b"".join(z.read(n) for n in z.namelist())
        tipos = z.read("[Content_Types].xml").decode("utf-8")
    if any("vba" in n.lower() or n.lower().endswith(".bin") for n in nombres) or "macroEnabled" in tipos:
        fallos.append("contiene macros/VBA")
    if any(n.startswith("xl/externalLinks") for n in nombres) or b"<connections" in crudo:
        fallos.append("contiene conexiones o vínculos externos")
    if b"TIPO_CAMBIO" in crudo:
        fallos.append("aparece TIPO_CAMBIO")
    wb = load_workbook(io.BytesIO(datos))
    if wb.sheetnames != [HOJA_CARGA, HOJA_CATALOGOS] or wb[HOJA_CATALOGOS].sheet_state != "hidden":
        fallos.append(f"hojas inesperadas: {wb.sheetnames} / catálogo {wb[HOJA_CATALOGOS].sheet_state}")
    ws, cats = wb[HOJA_CARGA], wb[HOJA_CATALOGOS]
    if list(ws.tables) != [NOMBRE_TABLA]:
        fallos.append(f"tablas: {list(ws.tables)}")
        raise AssertionError("Plantilla inválida:\n - " + "\n - ".join(fallos))  # el resto de comprobaciones depende de la tabla
    else:
        ref = ws.tables[NOMBRE_TABLA].ref
        inicio, fin = ref.split(":")
        if inicio != f"A{FILA_ENC}" or not fin.startswith(LETRAS[len(ENCABEZADOS) - 1]):
            fallos.append(f"rango de tabla {ref}")
        tabla = ws.tables[NOMBRE_TABLA]
        if tabla.name != NOMBRE_TABLA or tabla.displayName != NOMBRE_TABLA:
            fallos.append(f"nombre de tabla: name={tabla.name!r} displayName={tabla.displayName!r}")
        if tabla.autoFilter is None:
            fallos.append("la tabla no tiene filtros")
        if [c.name for c in tabla.tableColumns] != list(ENCABEZADOS):
            fallos.append("las columnas de la tabla no coinciden con los encabezados")
    encabezados = tuple(c.value for c in ws[FILA_ENC] if c.value is not None)
    if encabezados != ENCABEZADOS:
        fallos.append(f"encabezados {encabezados}")
    for col in ("CUENTA_BANCARIA", "CODIGO_ASIGNACION"):
        if {ws[f"{COL[col]}{r}"].number_format for r in (PRIMERA, PRIMERA + 1, ULTIMA)} != {"@"}:
            fallos.append(f"{col} no es texto")
    if ws[f"{COL['IMPORTE']}{PRIMERA}"].number_format != "#,##0.00":
        fallos.append("IMPORTE sin 2 decimales")
    bancos = [c.value for c in cats["A"][1:] if c.value]
    cuentas = [(cats[f"E{r}"].value, cats[f"F{r}"].value) for r in range(2, cats.max_row + 1) if cats[f"F{r}"].value]
    if bancos != cat["bancos"] or "(Todos)" in bancos:
        fallos.append(f"bancos {bancos}")
    if cuentas != [(c["banco"], c["cuenta"]) for c in cat["cuentas"]]:
        fallos.append(f"cuentas {cuentas}")
    if len({c for _, c in cuentas}) != len(cuentas):
        fallos.append("cuentas duplicadas")
    por_col = {}
    for v in ws.data_validations.dataValidation:
        por_col[str(v.sqref).split(":")[0].rstrip("0123456789")] = v
    esperadas = {COL["BANCO"]: ("list", rangos(cat)["bancos"]), COL["MONEDA"]: ("list", '"' + ",".join(MONEDAS) + '"'),
                 COL["CUENTA_BANCARIA"]: ("list", formula_cuentas(cat, f"${COL['BANCO']}{PRIMERA}")),
                 COL["IMPORTE"]: ("decimal", "0")}
    for col, (tipo, formula) in esperadas.items():
        v = por_col.get(col)
        if v is None or v.type != tipo or v.formula1 != formula or not v.showErrorMessage:
            fallos.append(f"validación de la columna {col} ausente o distinta")
    fin_tabla = int(re.sub(r"\D", "", ws.tables[NOMBRE_TABLA].ref.split(":")[1]))
    datos_tabla = [[c.value for c in ws[r][:len(ENCABEZADOS)]] for r in range(PRIMERA, fin_tabla + 1)]
    con_datos = [f for f in datos_tabla if any(v not in (None, "") for v in f)]
    if isinstance(con_ejemplos, bool):  # True = Ejemplo (3 filas), False = Plantilla de producción (0 filas)
        if con_ejemplos and len(con_datos) != 3:
            fallos.append(f"el ejemplo debe tener 3 filas, tiene {len(con_datos)}")
        if not con_ejemplos and con_datos:
            fallos.append("la plantilla de producción trae filas con datos")
    elif len(con_datos) != con_ejemplos:  # nº exacto de filas (archivos de medición)
        fallos.append(f"se esperaban {con_ejemplos} filas con datos y hay {len(con_datos)}")
    if fallos:
        raise AssertionError("Plantilla inválida:\n - " + "\n - ".join(fallos))


def _zip_determinista(wb) -> bytes:
    crudo = io.BytesIO()
    wb.save(crudo)
    salida = io.BytesIO()
    with zipfile.ZipFile(crudo) as origen, zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in sorted(origen.infolist(), key=lambda i: i.filename):
            datos = origen.read(info.filename)
            if info.filename == "docProps/core.xml":  # openpyxl reescribe «modified» con la hora actual al guardar
                datos = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>2026-10-05T00:00:00Z\g<2>", datos)
            nuevo = zipfile.ZipInfo(info.filename, date_time=FECHA_ZIP)
            nuevo.compress_type, nuevo.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            destino.writestr(nuevo, datos)
    return salida.getvalue()


def construir(con_ejemplos, cat: dict | None = None, filas=None) -> bytes:
    """con_ejemplos: False = vacía, True = 3 ejemplos; con `filas` explícitas, se verifica que el nº de filas coincida."""
    cat = cat or catalogo_p9.extraer()
    wb = Workbook()
    hoja_carga(wb, cat, con_ejemplos, filas)
    hoja_catalogos(wb, cat)
    wb.properties.creator = "P9 CONFIRMACIÓN MASIVA"
    wb.properties.title = TITULO
    wb.properties.created = wb.properties.modified = FECHA_FIJA
    datos = _zip_determinista(wb)
    verificar(datos, cat, con_ejemplos if filas is None else len(filas))
    return datos


def generar() -> dict[str, Path]:
    cat = catalogo_p9.extraer()
    catalogo_p9.escribir_json(cat)
    SALIDA.mkdir(exist_ok=True)
    rutas = {"plantilla": SALIDA / ARCHIVO_PLANTILLA, "ejemplo": SALIDA / ARCHIVO_EJEMPLO}
    rutas["plantilla"].write_bytes(construir(False, cat))
    rutas["ejemplo"].write_bytes(construir(True, cat))
    return rutas


if __name__ == "__main__":
    import hashlib
    for ruta in generar().values():
        print(hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.name)
