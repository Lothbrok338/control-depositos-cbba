"""Regresión estática del comprobante P9 con CUENTA CONTABLE, TIPO DE CAMBIO y EQUIVALENTE EN Bs.

Valida el YAML de pegado versionado (`COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`), su coherencia con
`COMPROBANTE_PDF.pa.yaml` y con `FORMULAS_EXACTAS.md`, el orden de pegado (ninguna referencia hacia un control
definido después), la geometría fija de una página Carta (816 × 1056), el mapeo contable y las reglas del tipo de cambio.
No ejecuta Power Fx ni certifica Studio: la validación en el tenant la hizo el usuario a mano.
"""
import hashlib
import math
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.p9
RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "p9/powerapps"
FRONT = APP / "P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt"
PEGAR = APP / "COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml"
RECIBO = APP / "COMPROBANTE_PDF.pa.yaml"
ANTERIOR = APP / "_referencia_comprobante/COMPROBANTE_PDF_38a59cc_SIN_CUENTA_NI_TC.pa.yaml"
LAYOUT_A4 = APP / "_referencia_comprobante/COMPROBANTE_PDF_CONTROLES_205ad0b_A4.yaml"
FORMULAS = APP / "FORMULAS_EXACTAS.md"

SHA_PEGAR = "5135add00c48128824b183e4fd3d84af1d1b60cad14e1f2d0facfb8e8cfb9697"  # layout Carta aprobado visualmente en Studio
SHA_LAYOUT_A4 = "a8eb740c1345d39a615099677b1dbba4faf26072c1f9bdb9a8f23a40effcafcc"  # layout A4 de 205ad0b (validado a mano en el tenant)
SHA_ANTERIOR = "3d4809bf433483e3480f4f9014388ae85395edb65901857ee41b4a749ed3e36f"  # comprobante de 38a59ccb, sin cuenta contable ni TC
PANTALLA_W, PANTALLA_H, MARGEN = 816, 1056, 24  # papel Carta vertical a 96 ppp
LIMITE_INFERIOR = 930  # el contenido imprimible no debe pasar de esta Y (margen para el área no imprimible)

TEXTO = PEGAR.read_text(encoding="utf-8")
RAIZ_YAML = yaml.safe_load(TEXTO)


def preorden(items, padre=None):
    for item in items:
        (nombre, ctrl), = item.items()
        yield nombre, ctrl, padre
        yield from preorden(ctrl.get("Children", []), nombre)


CONTROLES = list(preorden(RAIZ_YAML))
NOMBRES = [n for n, _, _ in CONTROLES]
POS = {n: i for i, n in enumerate(NOMBRES)}
C = {n: c for n, c, _ in CONTROLES}
PADRE = {n: p for n, _, p in CONTROLES}
RECIBO_DOC = yaml.safe_load(RECIBO.read_text(encoding="utf-8"))
PANTALLA = RECIBO_DOC["Screens"]["COMPROBANTE PDF"]
BASE = {n: c for n, c, _ in preorden(yaml.safe_load(ANTERIOR.read_text(encoding="utf-8"))["Screens"]["COMPROBANTE PDF"]["Children"])}
FRONT_DOC = yaml.safe_load(FRONT.read_text(encoding="utf-8"))
F = {n: c for n, c, _ in preorden(FRONT_DOC)}


def sin_cadenas(formula):
    """Quita literales "..." (con "" escapado) para analizar solo código."""
    return re.sub(r'"(?:[^"]|"")*"', '""', formula)


PREFIJO_CONTROL = re.compile(r"\b((?:lbl|btn|txt|rect|cnt|gal|ico|img|cmb|drp|chk|tgl|frm|dtp|scr)[A-Z][A-Za-z0-9_]*)\b")


def referencias(nombre):
    """(control_referenciado, propiedad) por cada referencia a otro control en las fórmulas de `nombre`."""
    refs = []
    for prop, valor in C[nombre]["Properties"].items():
        codigo = re.sub(r"\.'[^']*'", ".X", sin_cadenas(str(valor)))  # Font.'Segoe UI'
        refs += [(m.group(1), prop) for m in PREFIJO_CONTROL.finditer(codigo)]
        refs += [("'" + m.group(1) + "'", prop) for m in re.finditer(r"'([^']+)'", codigo)]
    return refs


def rect(n):
    p = C[n]["Properties"]
    return tuple(int(p[k][1:]) for k in ("X", "Y", "Width", "Height"))


# ------------------------------------------------------------------ procedencia y coherencia entre archivos
def test_huellas_fijadas():
    # Los hashes fijados corresponden al contenido LF de los blobs Git. En
    # Windows el checkout aplica CRLF; normalizar solo para esta comparación
    # conserva la misma prueba de contenido sin reescribir ningún artefacto.
    # huellas_base.json verifica por separado los bytes reales del checkout.
    sha_lf = lambda ruta: hashlib.sha256(ruta.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert sha_lf(PEGAR) == SHA_PEGAR
    assert sha_lf(ANTERIOR) == SHA_ANTERIOR
    assert sha_lf(LAYOUT_A4) == SHA_LAYOUT_A4


def test_recibo_completo_coincide_con_el_yaml_de_pegado():
    assert PANTALLA["Children"] == RAIZ_YAML
    assert list(PANTALLA["Properties"]) == ["Fill", "Height", "LoadingSpinnerColor", "Width", "OnVisible", "OnHidden"]
    assert PANTALLA["Properties"]["Width"] == "=816" and PANTALLA["Properties"]["Height"] == "=1056"
    assert PANTALLA["Properties"]["OnHidden"] == "=Reset(txtTipoCambioPDF);\nSet(varP9Comprobante, Blank());\nSet(varP9ComprobanteID, Blank())"
    onvisible = PANTALLA["Properties"]["OnVisible"]
    assert onvisible.startswith("=Reset(txtTipoCambioPDF);\nIf(")
    assert onvisible.endswith("Back()\n)")
    # el resto de OnVisible es el de la base validada, sin cambios
    assert onvisible.split("\n", 1)[1] == yaml.safe_load(ANTERIOR.read_text(encoding="utf-8"))["Screens"]["COMPROBANTE PDF"]["Properties"]["OnVisible"].lstrip("=")


# ------------------------------------------------------------------ solo controles hijos; nombres únicos
def test_yaml_de_pegado_solo_contiene_controles_hijos():
    assert isinstance(RAIZ_YAML, list) and RAIZ_YAML
    for item in RAIZ_YAML:
        (nombre, ctrl), = item.items()
        assert set(ctrl) <= {"Control", "Variant", "Properties", "Children"}, nombre
    assert [next(iter(i)) for i in RAIZ_YAML] == ["cntComprobantePDF", "btnVolverPDF", "btnImprimirPDF", "lblLimiteImpresionPDF"]
    assert "Screens:" not in TEXTO and "\t" not in TEXTO
    assert not re.search(r"^\s*COMPROBANTE PDF\s*:", TEXTO, re.M)
    assert not re.search(r"^Properties\s*:", TEXTO, re.M)
    for prop in ("OnVisible", "OnHidden", "LoadingSpinnerColor"):
        assert not re.search(rf"^\s*{prop}\s*:", TEXTO, re.M), prop


def test_nombres_unicos_sin_sufijos_y_controles_nuevos():
    assert len(NOMBRES) == len(set(NOMBRES)) == 49
    assert not [n for n in NOMBRES if re.search(r"_\d+$", n)]
    contenedores = {"cntComprobantePDF", "btnVolverPDF", "btnImprimirPDF", "lblLimiteImpresionPDF"}
    nuevos = set(NOMBRES) - set(BASE) - contenedores
    assert nuevos == {"lblTipoCambioTituloPDF", "txtTipoCambioPDF", "lblTipoCambioValorPDF", "lblEquivalenteTituloPDF", "lblEquivalenteValorPDF"}
    assert set(BASE) <= set(NOMBRES)
    for n in BASE:
        assert C[n]["Control"] == BASE[n]["Control"], n
    assert C["txtTipoCambioPDF"]["Control"] == "Classic/TextInput@2.3.2"
    todos = [n for n, _, _ in preorden(FRONT_DOC)] + NOMBRES
    assert len(todos) == len(set(todos)), "nombres repetidos entre P9 y el comprobante"


# ------------------------------------------------------------------ orden topológico de pegado
def test_referencias_existentes_y_ninguna_adelantada():
    for nombre in NOMBRES:
        for ref, prop in referencias(nombre):
            if ref.startswith("'"):
                assert ref == "'COMPROBANTE PDF'", (nombre, prop, ref)
                continue
            assert ref in POS, f"{nombre}.{prop} referencia a un control inexistente: {ref}"
            assert ref != nombre, f"{nombre}.{prop} se referencia a sí mismo"
            assert POS[ref] < POS[nombre], f"{nombre}.{prop} referencia adelantada a {ref}"


def test_unicas_referencias_entre_controles_son_las_del_tipo_de_cambio():
    entre = sorted({(n, r, p) for n in NOMBRES for r, p in referencias(n) if not r.startswith("'")})
    assert entre == [
        ("btnImprimirPDF", "txtTipoCambioPDF", "DisplayMode"),
        ("lblEquivalenteValorPDF", "txtTipoCambioPDF", "Text"),
        ("lblTipoCambioValorPDF", "txtTipoCambioPDF", "Text"),
    ]
    assert POS["cntComprobantePDF"] < POS["btnImprimirPDF"]


def test_la_pantalla_solo_se_usa_para_printing():
    for n in NOMBRES:
        for prop, valor in C[n]["Properties"].items():
            for m in re.finditer(r"'COMPROBANTE PDF'\.(\w+)", sin_cadenas(valor)):
                assert m.group(1) == "Printing", (n, prop)


# ------------------------------------------------------------------ geometría fija, una página Carta (816 × 1056)
def test_geometria_numerica_sin_autoheight():
    for n in NOMBRES:
        p = C[n]["Properties"]
        assert "AutoHeight" not in p, n
        for k in ("X", "Y", "Width", "Height"):
            assert re.fullmatch(r"=\d+", p[k]), (n, k, p[k])
    assert rect("cntComprobantePDF") == (20, 24, 715, 904)


def test_todo_cabe_en_una_pagina_carta_y_sin_solapes():
    x, y, w, h = rect("cntComprobantePDF")
    assert x >= 0 and x + w <= PANTALLA_W and y >= 0 and y + h <= PANTALLA_H - MARGEN
    hijos = [n for n in NOMBRES if PADRE[n] == "cntComprobantePDF"]
    for n in hijos:
        cx, cy, cw, ch = rect(n)
        assert cx >= 0 and cy >= 0 and cx + cw <= w and cy + ch <= h, n
    permitido = {frozenset({"txtTipoCambioPDF", "lblTipoCambioValorPDF"})}  # uno u otro según Printing
    for i, a in enumerate(hijos):
        for b in hijos[i + 1:]:
            ax, ay, aw, ah = rect(a)
            bx, by, bw, bh = rect(b)
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                assert frozenset({a, b}) in permitido, (a, b)


def test_el_contenido_imprimible_termina_antes_de_y_930():
    x, y, w, h = rect("cntComprobantePDF")
    fondo = max(y + rect(n)[1] + rect(n)[3] for n in NOMBRES if PADRE[n] == "cntComprobantePDF")
    assert fondo == 928 and fondo <= LIMITE_INFERIOR, fondo  # lblFirmaPDF; quedan 128 px hasta el borde de 1056
    assert y + h <= LIMITE_INFERIOR


# VOLVER, IMPRIMIR y el aviso van en la banda inferior y no se imprimen (Visible incluye Not(Printing)); posición aprobada en Studio.
EXTERNOS = {"btnVolverPDF": (40, 912, 110, 38), "btnImprimirPDF": (544, 912, 190, 38), "lblLimiteImpresionPDF": (160, 894, 394, 56)}


def test_botones_y_aviso_en_la_banda_inferior_y_ocultos_al_imprimir():
    for n, esperado in EXTERNOS.items():
        assert rect(n) == esperado, n
        cx, cy, cw, ch = esperado
        assert 0 <= cx and cx + cw <= PANTALLA_W and cy + ch <= PANTALLA_H, n
        assert "Not('COMPROBANTE PDF'.Printing)" in C[n]["Properties"]["Visible"], n


def test_el_contenedor_no_incluye_controles_interactivos_salvo_el_tipo_de_cambio():
    interactivos = [n for n in NOMBRES if PADRE[n] == "cntComprobantePDF" and C[n]["Control"].startswith(("Gallery@", "Classic/"))]
    assert interactivos == ["txtTipoCambioPDF"]


# ------------------------------------------------------------------ Print/Back y prohibiciones
def test_print_back_y_prohibiciones():
    assert C["btnImprimirPDF"]["Properties"]["OnSelect"] == "=Print()"
    assert C["btnVolverPDF"]["Properties"]["OnSelect"] == "=Back()"
    assert TEXTO.count("Print()") == 1 and TEXTO.count("Back()") == 1
    codigo = sin_cadenas(TEXTO + yaml.dump(PANTALLA["Properties"]))
    for prohibido in (r"\bPatch\s*\(", r"\bPDF\s*\(", r"\bDownload\s*\(", r"\bUser\s*\(", r"\bNow\s*\(", r"\bToday\s*\(",
                      r"\.Run\s*\(", r"\bLaunch\s*\(", r"\bSubmitForm\s*\(", r"\bRemove\s*\(", r"\bCollect\s*\(",
                      r"\bClearCollect\s*\(", r"\bNavigate\s*\(", r"\bRefresh\s*\(", r"P9_ASIGNAR_DEPOSITO", r"Office365", r"SharePoint"):
        assert not re.search(prohibido, codigo), prohibido


def test_delimitadores_balanceados_y_formulas_con_igual():
    for n in NOMBRES:
        for prop, valor in C[n]["Properties"].items():
            assert valor.startswith("="), (n, prop)
            assert valor.count('"') % 2 == 0, (n, prop)
            codigo = sin_cadenas(valor)
            for a, b in ("()", "{}", "[]"):
                prof = 0
                for ch in codigo:
                    prof += (ch == a) - (ch == b)
                    assert prof >= 0, (n, prop)
                assert prof == 0, (n, prop)


# ------------------------------------------------------------------ base validada conservada
CAMBIOS_PERMITIDOS = {
    "lblCuentaContableTituloPDF": {"Text", "Visible"},
    "lblCuentaContableValorPDF": {"Text", "Visible"},
    "btnImprimirPDF": {"DisplayMode"},
    "lblLimiteImpresionPDF": {"Size", "Align", "Text", "Visible"},
}
GEOMETRIA = {"X", "Y", "Width", "Height", "AutoHeight", "VerticalAlign"}


def test_estilos_y_textos_del_comprobante_validado_sin_cambios():
    for n, b in BASE.items():
        props_b = {k: v for k, v in b["Properties"].items() if k not in GEOMETRIA}
        props_n = {k: v for k, v in C[n]["Properties"].items() if k not in GEOMETRIA}
        dif = {k for k in set(props_b) | set(props_n) if props_b.get(k) != props_n.get(k)}
        assert dif <= CAMBIOS_PERMITIDOS.get(n, set()), (n, dif)
    cnt_b = {k: v for k, v in BASE["cntComprobantePDF"]["Properties"].items() if k not in GEOMETRIA}
    assert {k: v for k, v in C["cntComprobantePDF"]["Properties"].items() if k not in GEOMETRIA} == cnt_b


def test_el_layout_carta_solo_cambia_geometria_respecto_del_layout_a4_validado():
    """Todo lo funcional (fórmulas, textos, estilos, nombres, orden) es el de 205ad0b; solo cambian X/Y/Width/Height."""
    a4 = yaml.safe_load(LAYOUT_A4.read_text(encoding="utf-8"))
    viejo = {n: c for n, c, _ in preorden(a4)}
    assert [n for n, _, _ in preorden(a4)] == NOMBRES
    assert [(n, p) for n, _, p in preorden(a4)] == [(n, PADRE[n]) for n in NOMBRES]
    cambios = {"X": [], "Y": [], "Width": [], "Height": []}
    for n in NOMBRES:
        assert viejo[n]["Control"] == C[n]["Control"] and viejo[n].get("Variant") == C[n].get("Variant"), n
        pv, pn = viejo[n]["Properties"], C[n]["Properties"]
        assert list(pv) == list(pn), n
        for k in pv:
            if k in cambios:
                if pv[k] != pn[k]:
                    cambios[k].append(n)
            else:
                assert pv[k] == pn[k], (n, k)
    # los tamaños no cambian: la protección de texto depende de ellos. Excepciones deliberadas: contenedor y franja superior
    assert sorted(cambios["Width"]) == ["cntComprobantePDF", "rectLineaSuperiorPDF"]
    assert sorted(cambios["Height"]) == ["cntComprobantePDF", "rectLineaSuperiorPDF"]
    assert sorted(cambios["X"]) == ["btnImprimirPDF", "cntComprobantePDF", "rectLineaSuperiorPDF"]
    assert len(cambios["Y"]) == 48


def _cpl(ancho, size, em=0.62, ajuste=0.85):
    return int((ancho - 10) / (size * 4 / 3 * em) * ajuste)


def _lineas(alto, size):
    return int((alto - 10) // (size * 4 / 3 * 1.2))


def test_los_limites_de_la_proteccion_coinciden_con_el_tamano_de_cada_caja():
    """Si alguien cambia el ancho o alto de una caja protegida, el límite de la fórmula deja de ser cierto y esta prueba falla."""
    caps, (cpl_d, lin_d), (cpl_o, lin_o) = capacidades()
    cajas = {  # campo: (control, tamaño de fuente, ancho medio de carácter, factor de corte de palabra)
        "CODIGO_ASIGNACION": ("lblCodigoValorPDF", 26, 0.62, 0.9), "BANCO": ("lblBancoValorPDF", 12, 0.62, 0.8),
        "CUENTA_BANCARIA": ("lblCuentaValorPDF", 12, 0.62, 0.8), "HORA_MOVIMIENTO": ("lblFechaMovValorPDF", 11, 0.62, 0.8),
        "ESTUDIANTE": ("lblEstudianteValorPDF", 10, 0.62, 0.8), "SOLICITADO_POR": ("lblSolicitadoValorPDF", 10, 0.62, 0.8),
        "SEDE_ASIGNACION": ("lblSedeValorPDF", 10, 0.62, 0.8), "USUARIO_ASIGNACION": ("lblConfirmadoValorPDF", 11, 0.62, 0.85),
    }
    for campo, (caja, size, em, aj) in cajas.items():
        w, h = rect(caja)[2:]
        cap = _cpl(w, size, em, aj) * _lineas(h, size) - (len("dd/mm/yyyy · ") if campo == "HORA_MOVIMIENTO" else 0)
        assert cap == caps[campo], (campo, w, h, cap, caps[campo])
    w, h = rect("lblDescripcionValorPDF")[2:]
    assert (_cpl(w, 10, 0.62, 0.85), _lineas(h, 10)) == (cpl_d, lin_d) == (62, 5)
    w, h = rect("lblObsValorPDF")[2:]
    assert (_cpl(w, 10, 0.60, 0.85), _lineas(h, 10)) == (cpl_o, lin_o) == (64, 5)
    w, h = rect("lblFechaConfirmValorPDF")[2:]
    assert 19 <= _cpl(w, 11, 0.62, 0.85) and _lineas(h, 11) >= 1  # 'dd/mm/yyyy hh:mm:ss' (19 caracteres) cabe en una línea


# ------------------------------------------------------------------ cuenta contable
TABLA_USUARIO = {  # BNB MN, BNB CLÍNICA, BISA MN, BCP MN, BUSA MN, BANECO MN, BMS MN, BNB ME, BISA ME, BCP ME, BUSA ME, BANECO AH, BISA EURO AH, BNB AH
    "3000100152": "110103012", "3000100705": "110103022", "696870039": "110103032", "3015005684397": "110103042",
    "13224552": "110103052", "3041210569": "110103062", "4010879042": "110103072", "3400041236": "110104012",
    "696872023": "110104022", "3015005425271": "110104032", "23224544": "110104042", "3051446946": "110103722",
    "0696876517": "110105112", "3501936692": "110103712",
}
VARIANTES_CERO_BISA = {"0696870039": "110103032", "0696872023": "110104022", "696876517": "110105112"}
CONFIRMADAS_USUARIO = {"10000003224552": "110103052", "20000003224544": "110104042", "1000872489": "110103072"}  # Banco Unión MN/ME y BMSC
CUENTA_CONTABLE = C["lblCuentaContableValorPDF"]["Properties"]["Text"]


def mapa_formula():
    assert "varP9Comprobante.CUENTA_BANCARIA" in CUENTA_CONTABLE and "Switch(" in CUENTA_CONTABLE
    assert 'Substitute(Substitute(Substitute(Coalesce(varP9Comprobante.CUENTA_BANCARIA, ""), "-", ""), " ", ""), ".", "")' in CUENTA_CONTABLE
    assert re.search(r'"SIN MAPEO"\s*\)\s*\)\s*$', CUENTA_CONTABLE)
    pares = re.findall(r'"(\d+)",\s*"(\d+)"', CUENTA_CONTABLE)
    assert len(pares) == len(dict(pares)), "cuenta repetida en el Switch"
    return dict(pares)


def cuenta_contable(cuenta):
    return mapa_formula().get(cuenta.replace("-", "").replace(" ", "").replace(".", ""), "SIN MAPEO")


def cuentas_p9():
    return [c for c in re.findall(r'Cuenta: "([^"]*)"', FRONT.read_text(encoding="utf-8")) if c]


def test_mapa_contable_es_el_del_usuario_mas_ceros_de_bisa_y_las_tres_confirmadas():
    assert mapa_formula() == {**TABLA_USUARIO, **VARIANTES_CERO_BISA, **CONFIRMADAS_USUARIO}
    assert C["lblCuentaContableTituloPDF"]["Properties"]["Text"] == '="CUENTA CONTABLE"'
    for n in ("lblCuentaContableTituloPDF", "lblCuentaContableValorPDF"):
        assert "Visible" not in C[n]["Properties"]  # visibles siempre


def test_mapeo_vigente_completo_tiene_los_pares_aprobados():
    """La regresión cubre todas las entradas del comprobante, incluidas sus variantes."""
    esperado = {
        "3000100152": "110103012", "3000100705": "110103022",
        "696870039": "110103032", "0696870039": "110103032",
        "3015005684397": "110103042", "13224552": "110103052",
        "10000003224552": "110103052", "3041210569": "110103062",
        "4010879042": "110103072", "1000872489": "110103072",
        "3400041236": "110104012", "696872023": "110104022",
        "0696872023": "110104022", "3015005425271": "110104032",
        "23224544": "110104042", "20000003224544": "110104042",
        "3051446946": "110103722", "0696876517": "110105112",
        "696876517": "110105112", "3501936692": "110103712",
    }
    assert mapa_formula() == esperado
    assert len(esperado) == 20 and len(set(esperado.values())) == 14


def test_cuentas_ofrecidas_por_p9_tienen_su_cuenta_contable():
    esperado = {
        "3000100152": "110103012", "3400041236": "110104012", "3501936692": "110103712", "3000100705": "110103022",
        "301-5005684-3-97": "110103042", "301-5005425-2-71": "110104032",
        "0696870039": "110103032", "0696872023": "110104022",
        "10000003224552": "110103052", "20000003224544": "110104042",
        "3041210569": "110103062", "3051446946": "110103722",
        "1000872489": "110103072",
    }
    assert sorted(cuentas_p9()) == sorted(esperado)
    assert {c: cuenta_contable(c) for c in cuentas_p9()} == esperado


def test_cuenta_desconocida_dice_sin_mapeo_y_no_bloquea_la_impresion():
    for desconocida in ("999999999", "", "ABC", "1000872488"):
        assert cuenta_contable(desconocida) == "SIN MAPEO"
    assert cuenta_contable(" 3000 1001.52 ") == "110103012"
    mode = C["btnImprimirPDF"]["Properties"]["DisplayMode"]
    assert "SIN MAPEO" not in mode and "CUENTA_BANCARIA" not in mode.replace('varP9Comprobante.CUENTA_BANCARIA, "")) <= ', "")


# ------------------------------------------------------------------ tipo de cambio
def tc_valor(texto):
    """Réplica de la fórmula: Trim + IsMatch(^[0-9]+$ | ^[0-9]+[.,][0-9]+$) + Value(en-US)."""
    t = " ".join(texto.split())
    if re.fullmatch(r"[0-9]+", t) or re.fullmatch(r"[0-9]+[.,][0-9]+", t):
        return float(t.replace(",", "."))
    return None


def es_es(numero, dec=2):
    return f"{numero:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


@pytest.mark.parametrize("entrada, valido", [
    ("6,96", True), ("6.96", True), (" 6,96 ", True), ("7", True), ("6,8650", True),
    ("", False), ("   ", False), ("abc", False), ("0", False), ("0,00", False), ("-6,96", False),
    ("6,96,1", False), ("6.960,00", False), ("6,", False), (",96", False), ("6 96", False), ("1e3", False),
])
def test_tc_valido_solo_numerico_y_mayor_que_cero(entrada, valido):
    v = tc_valor(entrada)
    assert (v is not None and v > 0) is valido


def test_formulas_del_tipo_de_cambio_usan_la_misma_validacion():
    comun = ('IsMatch(tcTexto, "^[0-9]+$") || IsMatch(tcTexto, "^[0-9]+[.,][0-9]+$")', 'Value(Substitute(tcTexto, ",", "."), "en-US")', "Trim(txtTipoCambioPDF.Text)")
    eq = C["lblEquivalenteValorPDF"]["Properties"]["Text"]
    for parte in comun + ("!IsBlank(tcValor) && tcValor > 0", '"Bs " & Text(varP9Comprobante.IMPORTE * tcValor, "#,##0.00", "es-ES")', '"Ingrese TC"', '"TC no válido"'):
        assert parte in eq, parte
    for texto in (C["lblTipoCambioValorPDF"]["Properties"]["Text"], C["btnImprimirPDF"]["Properties"]["DisplayMode"]):
        for parte in comun:
            assert parte in texto, parte
    assert 'Text(tcValor, "0.00####", "es-ES")' in C["lblTipoCambioValorPDF"]["Properties"]["Text"]


def test_ejemplo_usd_500_por_6_96():
    for escrito in ("6,96", "6.96"):
        assert "Bs " + es_es(500 * tc_valor(escrito)) == "Bs 3.480,00"
    assert es_es(tc_valor("6,96")) == "6,96"


def test_visibilidad_por_moneda_e_impresion():
    usd, imp = 'varP9Comprobante.MONEDA = "USD"', "'COMPROBANTE PDF'.Printing"
    vis = lambda n: C[n]["Properties"]["Visible"]
    for n in ("lblTipoCambioTituloPDF", "lblEquivalenteTituloPDF", "lblEquivalenteValorPDF"):
        assert vis(n) == f"={usd}"
    assert vis("txtTipoCambioPDF") == f"={usd} && Not({imp})"  # editable solo mientras se ve
    assert vis("lblTipoCambioValorPDF") == f"={usd} && {imp}"  # al imprimir, texto
    assert C["txtTipoCambioPDF"]["Properties"]["Default"] == '=""'
    assert "DisplayMode" not in C["txtTipoCambioPDF"]["Properties"]
    assert rect("txtTipoCambioPDF")[:2] == rect("lblTipoCambioValorPDF")[:2]


def test_imprimir_exige_tc_solo_en_usd():
    d = C["btnImprimirPDF"]["Properties"]["DisplayMode"]
    assert 'varP9Comprobante.MONEDA <> "USD" ||' in d
    assert d.rstrip().endswith("DisplayMode.Edit,\n    DisplayMode.Disabled\n)")
    assert C["btnImprimirPDF"]["Properties"]["Visible"] == BASE["btnImprimirPDF"]["Properties"]["Visible"]


# ------------------------------------------------------------------ protección de una sola página
def capacidades():
    d = C["btnImprimirPDF"]["Properties"]["DisplayMode"]
    caps = {m.group(1): int(m.group(2)) for m in re.finditer(r'varP9Comprobante\.(\w+), ""\)\) <= (\d+)', d)}
    desc = re.search(r"RoundUp\(Len\(descTexto\) / (\d+), 0\) .*?<= (\d+)", d)
    obs = re.search(r"RoundUp\(Len\(obsTexto\) / (\d+), 0\) .*?<= (\d+)", d)
    return caps, tuple(map(int, desc.groups())), tuple(map(int, obs.groups()))


def lineas_estimadas(texto, cpl):
    return math.ceil(len(texto) / cpl) + texto.count("\n")


def test_aviso_y_boton_comparten_la_misma_proteccion():
    d = C["btnImprimirPDF"]["Properties"]["DisplayMode"]
    v = C["lblLimiteImpresionPDF"]["Properties"]["Visible"]
    assert v.startswith("=Not('COMPROBANTE PDF'.Printing) && !IsBlank(varP9ComprobanteID)")
    assert C["lblLimiteImpresionPDF"]["Properties"]["Text"].startswith('="El contenido supera el espacio de una página A4.')

    def bloque(s):
        i = s.index("descTexto: Coalesce(varP9Comprobante.DESCRIPCION")
        j = s.index("\n", s.index('Len(Substitute(obsTexto, Char(10), "")) <= '))
        return re.sub(r"\s+", " ", s[i:j]).strip()

    assert bloque(d) == bloque(v)
    assert set(capacidades()[0]) == {"CODIGO_ASIGNACION", "BANCO", "CUENTA_BANCARIA", "HORA_MOVIMIENTO", "ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "USUARIO_ASIGNACION"}


def test_la_proteccion_admite_datos_reales_y_bloquea_desbordes():
    caps, (cpl_d, lin_d), (cpl_o, lin_o) = capacidades()
    real = {
        "CODIGO_ASIGNACION": "TT26224V735L", "BANCO": "BANCO ECONÓMICO", "CUENTA_BANCARIA": "301-5005684-3-97",
        "HORA_MOVIMIENTO": "14:43:49", "ESTUDIANTE": "CASTRILLO  DE ALTAMIRANO ROSARIO",
        "SOLICITADO_POR": "MONTERO CORTEZ LUCIANA NICOLE", "SEDE_ASIGNACION": "COCHABAMBA",
        "USUARIO_ASIGNACION": "nombre.apellido.segundo@univalle.edu",
    }
    for k, v in real.items():
        assert len(v) <= caps[k], k
    assert lineas_estimadas("CREDITO TRANSFERENCIA ACH TRANSFERENCIA  MONTERO CORTEZ LUCIANA NICOLE BANCO SOLIDARIO S A", cpl_d) <= lin_d
    assert lineas_estimadas("", cpl_o) <= lin_o
    assert lineas_estimadas("x" * 1000, cpl_d) > lin_d
    assert lineas_estimadas("a\nb\nc\nd\ne\nf", cpl_o) > lin_o


# ------------------------------------------------------------------ FORMULAS_EXACTAS.md coincide con los YAML
def a_regional(formula):
    """Invariante -> regional (es): ',' -> ';' y ';' -> ';;' fuera de cadenas y de identificadores entre comillas simples."""
    out, i, cadena, ident = [], 0, False, False
    while i < len(formula):
        c = formula[i]
        if cadena:
            out.append(c)
            if c == '"':
                if i + 1 < len(formula) and formula[i + 1] == '"':
                    out.append('"')
                    i += 1
                else:
                    cadena = False
        elif ident:
            out.append(c)
            ident = c != "'"
        elif c == '"':
            cadena = True
            out.append(c)
        elif c == "'":
            ident = True
            out.append(c)
        elif c == ";":
            out.append(";;")
        elif c == ",":
            out.append(";")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def secciones_md():
    texto = FORMULAS.read_text(encoding="utf-8")
    res = {}
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", texto, re.M | re.S):
        bloques = re.findall(r"```powerfx\n(.*?)\n```", m.group(2), re.S)
        res[m.group(1).strip()] = bloques
    return res


def valor_yaml(titulo):
    objeto, prop = titulo.rsplit(".", 1)
    if objeto == "'COMPROBANTE PDF'":
        props = PANTALLA["Properties"]
    else:
        props = (C.get(objeto) or F[objeto])["Properties"]
    return props[prop][1:]


def test_formulas_exactas_md_coincide_con_los_yaml_y_las_variantes_regionales():
    secciones = secciones_md()
    assert len(secciones) >= 39
    for titulo, bloques in secciones.items():
        canonica = valor_yaml(titulo)
        regional = a_regional(canonica)
        assert bloques[0] == canonica, titulo
        if regional == canonica:
            assert len(bloques) == 1, titulo
        else:
            assert len(bloques) == 2 and bloques[1] == regional, titulo
    for obligatoria in ("'COMPROBANTE PDF'.OnVisible", "'COMPROBANTE PDF'.OnHidden", "lblCuentaContableValorPDF.Text",
                        "txtTipoCambioPDF.Visible", "lblTipoCambioValorPDF.Text", "lblEquivalenteValorPDF.Text",
                        "btnImprimirPDF.DisplayMode", "lblLimiteImpresionPDF.Visible", "btnAsignarP9.Height", "btnAsignarP9.Y"):
        assert obligatoria in secciones, obligatoria


def test_formulas_regionales_de_pantalla_son_las_validadas_en_el_tenant():
    s = secciones_md()
    assert s["'COMPROBANTE PDF'.OnHidden"][1] == "Reset(txtTipoCambioPDF);;\nSet(varP9Comprobante; Blank());;\nSet(varP9ComprobanteID; Blank())"
    onvisible = s["'COMPROBANTE PDF'.OnVisible"][1]
    assert onvisible.startswith("Reset(txtTipoCambioPDF);;\nIf(")
    assert 'varP9Comprobante.ESTADO_ASIGNACION.Value <> "ASIGNADO";\n    Set(varP9Comprobante; Blank());;' in onvisible
    assert "," not in sin_cadenas(onvisible)
