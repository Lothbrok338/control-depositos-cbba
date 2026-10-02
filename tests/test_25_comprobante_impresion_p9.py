"""Regresión estática del comprobante P9. No ejecuta Power Fx ni certifica Studio."""
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.p9
RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "p9/powerapps"
NOMBRE = "P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt"
BASE = APP / "_base_validada_tenant_2m" / NOMBRE
FRONT = APP / NOMBRE
RECIBO = APP / "COMPROBANTE_PDF.pa.yaml"
REFERENCIA = APP / "_referencia_comprobante/COMPROBANTE_PDF_ORIGINAL.pa.yaml"


def nodos(items):
    for item in items:
        (nombre, control), = item.items()
        yield nombre, control
        yield from nodos(control.get("Children", []))


def cargar(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


BASE_DOC, FRONT_DOC, RECIBO_DOC = cargar(BASE), cargar(FRONT), cargar(RECIBO)
PANTALLA = RECIBO_DOC["Screens"]["COMPROBANTE PDF"]
B = dict(nodos(BASE_DOC))
F = dict(nodos(FRONT_DOC))
R = dict(nodos(PANTALLA["Children"]))
ABRIR = F["btnAbrirComprobanteP9"]["Properties"]["OnSelect"]


def propiedades(nombre):
    return R[nombre]["Properties"]


def test_base_exacta_del_commit_validado_conservada():
    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == "eb68f73700d259bfb4db43d787e4a2ff050ee8c08754b7b5138468f003e050c8"


def test_p9_solo_agrega_boton_y_reubica_ver_sin_modificar_otra_propiedad():
    """Comparación completa, incluidos filtros, modal, Run y orden de controles."""
    actual = copy.deepcopy(FRONT_DOC)
    controles = dict(nodos(actual))
    gal = controles["galDepositosP9"]
    gal["Children"] = [c for c in gal["Children"] if "btnAbrirComprobanteP9" not in c]
    props = controles["btnAsignarP9"]["Properties"]
    assert props["Height"] == '=If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO", 28, 32)'
    assert props["Y"] == '=If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO", 6, 22)'
    props["Height"], props["Y"] = "=32", "=22"
    assert actual == BASE_DOC


def test_formula_confirmacion_conservada_literalmente():
    assert F["btnConfirmarDepositoP9"] == B["btnConfirmarDepositoP9"]
    assert F["btnAsignarP9"]["Properties"]["OnSelect"] == B["btnAsignarP9"]["Properties"]["OnSelect"]
    assert set(F) - set(B) == {"btnAbrirComprobanteP9"}


def test_boton_solo_para_asignado_y_no_selecciona_ni_resetea_galeria():
    p = F["btnAbrirComprobanteP9"]["Properties"]
    assert p["Visible"] == '=ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO"'
    assert p["Text"] == '="PDF"'
    assert "varP9ComprobanteCargando" in p["DisplayMode"]
    assert "DisplayMode.Disabled" in p["DisplayMode"]
    assert "Set(varP9ComprobanteID, ThisItem.ID)" in ABRIR
    assert "Set(varP9Comprobante, ThisItem)" not in ABRIR
    for prohibido in ("varDepositoSeleccionado", "Select(Parent)", "Reset(", "UpdateContext("):
        assert prohibido not in ABRIR


def test_actualizacion_y_lectura_con_manejo_de_errores_independientes():
    # Refresh es el primer argumento de IfError, NO una cadena Refresh(); LookUp().
    assert re.search(r"IfError\(\s*Refresh\(Depositos_Activos\),", ABRIR)
    assert ABRIR.count("IfError(") == 2
    assert ABRIR.index("Set(varP9Comprobante, Blank())") < ABRIR.index("Refresh(")
    assert ABRIR.index("Refresh(") < ABRIR.index("LookUp(")
    assert "LookUp(Depositos_Activos, ID = varP9ComprobanteID)" in ABRIR
    assert 'IsBlank(registroP9.ID) || registroP9.ESTADO_ASIGNACION.Value <> "ASIGNADO"' in ABRIR
    assert ABRIR.index('registroP9.ESTADO_ASIGNACION.Value <> "ASIGNADO"') < ABRIR.index("Set(varP9Comprobante, registroP9)") < ABRIR.index("Navigate(")
    assert ABRIR.count("Navigate(") == 1
    assert ABRIR.count("Set(varP9Comprobante, Blank())") == 3
    assert ABRIR.count("Set(varP9ComprobanteID, Blank())") == 3
    assert ABRIR.endswith("Set(varP9ComprobanteCargando, false)")


def test_acceso_directo_y_salida_limpian_el_comprobante():
    onvisible = PANTALLA["Properties"]["OnVisible"]
    for fragmento in ("IsBlank(varP9ComprobanteID)", "IsBlank(varP9Comprobante.ID)", "varP9Comprobante.ID <> varP9ComprobanteID", 'varP9Comprobante.ESTADO_ASIGNACION.Value <> "ASIGNADO"', "Set(varP9Comprobante, Blank())", "NotificationType.Warning", "Back()"):
        assert fragmento in onvisible
    assert PANTALLA["Properties"]["OnHidden"] == "=Set(varP9Comprobante, Blank());\nSet(varP9ComprobanteID, Blank())"
    assert 'varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO"' in propiedades("cntComprobantePDF")["Visible"]
    assert "varP9Comprobante.ID = varP9ComprobanteID" in propiedades("cntComprobantePDF")["Visible"]


def test_campos_reales_y_tipos_de_sharepoint():
    esquema = json.loads((RAIZ / "p8/esquema_listas_p8.json").read_text(encoding="utf-8"))
    tipos = {c["nombre_tecnico"]: c["tipo"] for c in esquema["Depositos_Activos"]["columnas"]}
    txt = RECIBO.read_text(encoding="utf-8")
    esperados = {"BANCO", "CUENTA_BANCARIA", "MONEDA", "FECHA_MOVIMIENTO", "HORA_MOVIMIENTO", "IMPORTE", "CODIGO_ASIGNACION", "DESCRIPCION", "ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "OBSERVACION", "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "ESTADO_ASIGNACION"}
    usados = set(re.findall(r"varP9Comprobante\.([A-Z_]+)", txt))
    assert usados == esperados | {"ID"}
    assert esperados <= set(tipos)
    assert set(re.findall(r"varP9Comprobante\.(\w+)\.Value", txt)) == {"ESTADO_ASIGNACION"}
    assert ".DisplayName" not in txt
    for campo in ("BANCO", "MONEDA", "HORA_MOVIMIENTO", "SEDE_ASIGNACION", "USUARIO_ASIGNACION"):
        assert tipos[campo] == "Texto de una linea"


def test_datos_persistidos_sin_experimentales_ni_escrituras():
    txt = RECIBO.read_text(encoding="utf-8") + ABRIR
    for patron in (r"\bPDF\s*\(", r"\bUser\s*\(", r"\bNow\s*\(", r"\bToday\s*\(", r"\bDownload\s*\(", r"\bPatch\s*\(", r"\bSubmitForm\s*\(", r"\bRemove\s*\(", r"\bCollect\s*\(", r"\bClearCollect\s*\(", r"\.Run\s*\("):
        assert not re.search(patron, txt), patron
    for prohibido in ("CODIGO_ESTUDIANTE", "varDepositoSeleccionado", "PdfViewer", "Office365Outlook"):
        assert prohibido not in txt


def test_formato_importe_cero_blank_fechas_y_observacion():
    importe = propiedades("lblImporteValorPDF")["Text"]
    assert "IsBlank(varP9Comprobante.IMPORTE)" in importe
    assert 'Text(varP9Comprobante.IMPORTE, "#,##0.00", "es-ES")' in importe
    assert '="20"' != propiedades("lblImporteValorPDF")["Size"] == "=20"
    assert '"Sin observación"' in propiedades("lblObsValorPDF")["Text"]
    assert "TrimEnds(" in propiedades("lblObsValorPDF")["Text"]
    fecha = propiedades("lblFechaConfirmValorPDF")["Text"]
    assert 'Text(varP9Comprobante.FECHA_HORA_ASIGNACION, "dd/mm/yyyy hh:mm:ss", "es-ES")' in fecha
    assert "IsBlank(varP9Comprobante.FECHA_HORA_ASIGNACION)" in fecha
    assert "USUARIO_ASIGNACION" in propiedades("lblConfirmadoValorPDF")["Text"]


def test_print_back_a4_y_controles_fuera_del_area_imprimible():
    assert PANTALLA["Properties"]["Width"] == "=794"
    assert PANTALLA["Properties"]["Height"] == "=1123"
    assert propiedades("btnImprimirPDF")["OnSelect"] == "=Print()"
    assert propiedades("btnVolverPDF")["OnSelect"] == "=Back()"
    inner = dict(nodos(R["cntComprobantePDF"]["Children"]))
    assert not any(c["Control"].startswith(("Gallery@", "Classic/Button@")) for c in inner.values())
    for name in ("btnImprimirPDF", "btnVolverPDF", "lblLimiteImpresionPDF"):
        assert name not in inner
        assert "Not('COMPROBANTE PDF'.Printing)" in propiedades(name)["Visible"]


def test_textos_crecen_y_no_se_permite_imprimir_contenido_fuera_de_pagina():
    for name in ("lblCodigoValorPDF", "lblBancoValorPDF", "lblCuentaValorPDF", "lblMonedaValorPDF", "lblDescripcionValorPDF", "lblObsValorPDF", "lblEstudianteValorPDF", "lblSolicitadoValorPDF", "lblSedeValorPDF", "lblConfirmadoValorPDF", "lblFechaConfirmValorPDF"):
        assert propiedades(name)["AutoHeight"] == "=true"
        assert propiedades(name)["Wrap"] == "=true"
    assert propiedades("cntComprobantePDF")["Height"] == "=lblFirmaPDF.Y + lblFirmaPDF.Height + 16"
    mode = propiedades("btnImprimirPDF")["DisplayMode"]
    assert "cntComprobantePDF.Y + cntComprobantePDF.Height <= Parent.Height - 24" in mode
    assert "DisplayMode.Disabled" in mode
    assert "cntComprobantePDF.Y + cntComprobantePDF.Height > Parent.Height - 24" in propiedades("lblLimiteImpresionPDF")["Visible"]


def test_nombres_y_estilo_de_referencia_conservados():
    originales = dict(nodos(cargar(REFERENCIA)["Screens"]["COMPROBANTE PDF"]["Children"]))
    assert set(originales) <= set(R)
    for name, original in originales.items():
        assert R[name]["Control"] == original["Control"]
        for prop in ("Color", "Fill", "BorderColor", "RadiusTopLeft", "RadiusBottomRight"):
            if prop in original.get("Properties", {}):
                assert propiedades(name)[prop] == original["Properties"][prop]
    for name in ("lblCuentaContableTituloPDF", "lblCuentaContableValorPDF"):
        assert propiedades(name)["Visible"] == "=false"
        assert propiedades(name)["Text"] == '=""'


def test_nombres_unicos_y_referencias_a_controles_existentes():
    todos = list(nodos(FRONT_DOC)) + list(nodos(PANTALLA["Children"]))
    nombres = [n for n, _ in todos]
    assert len(nombres) == len(set(nombres))
    txt = FRONT.read_text(encoding="utf-8") + RECIBO.read_text(encoding="utf-8")
    refs = set(re.findall(r"\b((?:lbl|btn|cnt|rect|gal|row|cmb|txt|dp|head|sep|overlay)\w*)\.", txt))
    assert refs <= set(nombres), refs - set(nombres)


def test_botones_caben_en_fila_sin_tocar_otros_campos():
    assert F["galDepositosP9"]["Properties"]["TemplateSize"] == "=76"
    nuevo = F["btnAbrirComprobanteP9"]["Properties"]
    assert (nuevo["X"], nuevo["Width"], nuevo["Y"], nuevo["Height"]) == ("=Parent.TemplateWidth - 125", "=110", "=40", "=28")
    assert 6 + 28 < 40 and 40 + 28 < 75


def test_formulas_delimitadores_balanceados_sin_validar_semantica_power_fx():
    textos = [ABRIR] + list(PANTALLA["Properties"].values())
    textos += [v for _, c in nodos(PANTALLA["Children"]) for v in c.get("Properties", {}).values()]
    for text in textos:
        if not isinstance(text, str):
            continue
        limpio = re.sub(r'"(?:""|[^"])*"|\'(?:\'\'|[^\'])*\'', "", text)
        stack = []
        for char in limpio:
            if char in "([{":
                stack.append(char)
            elif char in ")]}":
                assert stack and stack.pop() == {")": "(", "]": "[", "}": "{"}[char], text
        assert not stack, text
