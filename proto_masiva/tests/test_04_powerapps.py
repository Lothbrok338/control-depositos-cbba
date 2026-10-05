"""Pantalla P9_Confirmacion_Masiva, botón de Main_Screen y fórmulas manuales: pruebas ESTÁTICAS.

No ejecutan Power Fx ni Studio. Comprueban: YAML válido, nombres únicos, referencias resolubles, paréntesis/comillas
balanceados, coherencia con el esquema de la lista y que el Main_Screen original queda intacto.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
PA = RAIZ / "powerapps"
sys.path.insert(0, str(PA))
import aplicar_boton  # noqa: E402
import derivar_pegar  # noqa: E402

PANTALLA = yaml.safe_load((PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))["Screens"]["P9_Confirmacion_Masiva"]
ESQUEMA = json.loads((RAIZ / "sharepoint/esquema_P9_MASIVA_PROTO_LOTES.json").read_text(encoding="utf-8"))
CAMPOS = {c["nombre_tecnico"] for c in ESQUEMA["columnas"]} | {"ID", "Title"}
MANUALES = {"frmLoteP9", "attXlsxP9", "tmrSondeoP9"}
TIPOS_USADOS_EN_P9 = {"GroupContainer@1.5.0", "Rectangle@2.3.0", "Label@2.5.1", "Classic/Button@2.2.0"}


def controles(hijos):
    for h in hijos:
        (nombre, cuerpo), = h.items()
        yield nombre, cuerpo
        yield from controles(cuerpo.get("Children", []))


CONTROLES = dict(controles(PANTALLA["Children"]))


def formulas():
    for nombre, c in CONTROLES.items():
        for prop, valor in c["Properties"].items():
            yield f"{nombre}.{prop}", valor
    for prop in ("OnVisible", "OnHidden"):
        yield f"pantalla.{prop}", PANTALLA["Properties"][prop]


def sin_cadenas(formula):
    return re.sub(r'"(?:[^"]|"")*"', '""', formula)


# --------------------------------------------------------------------------- pantalla
def test_yaml_valido_con_nombres_unicos_y_tipos_conocidos():
    nombres = [n for n, _ in controles(PANTALLA["Children"])]
    assert len(nombres) == len(set(nombres)) == 30
    assert {c["Control"] for c in CONTROLES.values()} <= TIPOS_USADOS_EN_P9


def test_elementos_minimos_pedidos():
    p = lambda n, k="Text": CONTROLES[n]["Properties"][k]  # noqa: E731
    assert p("lblTituloMasivaP9") == '="IMPORTACIÓN MASIVA"'
    assert p("btnDescargarPlantillaP9") == '="DESCARGAR PLANTILLA"' and p("btnDescargarPlantillaP9", "OnSelect") == "=Launch(varUrlPlantillaP9)"
    assert "attXlsxP9.Attachments" in p("lblArchivoSeleccionadoP9")
    assert p("btnPrevalidarP9") == '="PREVALIDAR ARCHIVO"'
    assert "SubmitForm(frmLoteP9)" in p("btnPrevalidarP9", "OnSelect")
    assert "Coalesce(varLoteVivoP9.ESTADO" in p("lblEstadoP9")
    for rotulo in ("Archivo", "Tabla encontrada", "Filas leídas", "Mensaje"):
        assert any(c["Properties"].get("Text") == f'="{rotulo}"' for c in CONTROLES.values()), rotulo
    assert p("btnVolverMasivaP9") == '="VOLVER"'
    assert "Navigate(Main_Screen, ScreenTransition.Fade)" in p("btnVolverMasivaP9", "OnSelect")


def test_titular_de_exito_dice_archivo_recibido_tabla_encontrada_y_filas():
    t = CONTROLES["lblTitularResultadoP9"]["Properties"]["Text"]
    assert "ARCHIVO RECIBIDO · TABLA ENCONTRADA ·" in t and "FILAS LEÍDAS" in t


def test_cinco_estados_del_prototipo_estan_en_el_esquema():
    valores = next(c for c in ESQUEMA["columnas"] if c["nombre_tecnico"] == "ESTADO")["valores"]
    assert valores == ["CARGADO", "PENDIENTE", "PROCESANDO", "COMPLETADO", "ERROR"]
    usados = set()
    for _, f in formulas():
        usados |= set(re.findall(r'"(CARGADO|PENDIENTE|PROCESANDO|COMPLETADO|ERROR)"', f))
    assert usados == set(valores)


def test_las_referencias_a_controles_se_resuelven():
    conocidos = set(CONTROLES) | MANUALES
    for donde, f in formulas():
        for ref in re.findall(r"\b((?:btn|lbl|rect|cnt|frm|att|tmr|txt)[A-Za-z0-9_]*P9)\b", sin_cadenas(f)):
            assert ref in conocidos, (donde, ref)
    assert {r for _, f in formulas() for r in re.findall(r"\b(frmLoteP9|attXlsxP9|tmrSondeoP9)\b", f)} == {"frmLoteP9", "attXlsxP9"}


def test_campos_leidos_del_lote_existen_en_el_esquema():
    for donde, f in formulas():
        for campo in re.findall(r"varLote(?:Vivo)?P9\.([A-Za-z_]+)", sin_cadenas(f)):
            assert campo in CAMPOS, (donde, campo)


def test_la_pantalla_no_usa_Depositos_Activos_ni_tipo_de_cambio_en_formulas():
    for donde, f in formulas():
        limpio = sin_cadenas(f)
        assert "Depositos_Activos" not in limpio and "Depositos_Reversiones" not in limpio, donde
        assert "TIPO_CAMBIO" not in f, donde
    assert "TIPO_CAMBIO" not in (PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    assert any("P9_MASIVA_PROTO_LOTES" in sin_cadenas(f) for _, f in formulas())  # la única fuente de datos es la lista del prototipo


def test_formulas_con_parentesis_y_comillas_balanceados():
    for donde, f in formulas():
        assert f.count('"') % 2 == 0, donde
        limpio = sin_cadenas(f)
        assert limpio.count("(") == limpio.count(")"), donde
        assert limpio.count("{") == limpio.count("}"), donde


def test_geometria_estable_sin_referencias_entre_controles_hermanos():
    for nombre, c in CONTROLES.items():
        for eje in ("X", "Y", "Width", "Height"):
            valor = c["Properties"].get(eje, "")
            assert not re.search(r"\b(?:btn|lbl|rect|cnt)[A-Za-z0-9_]*P9\.", valor), (nombre, eje)


def test_los_fragmentos_de_pegado_son_la_salida_actual_del_derivador():
    fuente = (PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    assert (PA / "P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml").read_text(encoding="utf-8") == derivar_pegar.hijos(fuente)
    assert (PA / "BOTON_MAIN_SCREEN_PEGAR.yaml").read_text(encoding="utf-8") == derivar_pegar.dedentar(aplicar_boton.BLOQUE, 12)
    pegar = yaml.safe_load((PA / "P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml").read_text(encoding="utf-8"))
    assert [list(x)[0] for x in pegar] == ["cntImportacionMasivaP9"]


# --------------------------------------------------------------------------- fórmulas manuales de INSTRUCCIONES_PEGADO.md
def bloques_md():
    texto = (PA / "INSTRUCCIONES_PEGADO.md").read_text(encoding="utf-8")
    return [b for b in re.findall(r"```\n(.*?)```", texto, re.S)]


def test_formulas_manuales_balanceadas_y_con_referencias_conocidas():
    bloques = bloques_md()
    assert len(bloques) == 3  # OnSuccess, OnTimerEnd, OnVisible
    conocidos = set(CONTROLES) | MANUALES
    for b in bloques:
        limpio = sin_cadenas(b)
        assert limpio.count("(") == limpio.count(")") and limpio.count("{") == limpio.count("}")
        for ref in re.findall(r"\b((?:btn|lbl|rect|cnt|frm|att|tmr)[A-Za-z0-9_]*P9)\b", limpio):
            assert ref in conocidos, ref
        for campo in re.findall(r"varLote(?:Vivo)?P9\.([A-Za-z_]+)", limpio):
            assert campo in CAMPOS, campo
        for clave in re.findall(r"\{([^{}]*)\}", limpio):
            for nombre in re.findall(r"(?:^|,)\s*([A-Za-z_]+)\s*:", clave):
                assert nombre in CAMPOS, nombre  # los campos que Patch escribe existen en la lista
    assert "ESTADO: \"PENDIENTE\"" in bloques[0] and "Depositos_Activos" not in "".join(bloques)


def test_la_app_nunca_escribe_estados_del_flujo():
    escribe_estado = re.findall(r'ESTADO: "([A-Z]+)"', "".join(bloques_md()))
    assert set(escribe_estado) == {"CARGADO", "PENDIENTE"}  # PROCESANDO / COMPLETADO / ERROR solo los escribe el flujo


# --------------------------------------------------------------------------- botón en Main_Screen
ORIGINAL = REPO / "p9/reversion/powerapps/Main_Screen.yaml"
CON_BOTON = PA / "Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml"
SHA_ORIGINAL_LF = "99486d668690e425568ca18c5d6d3ff6d953fe4529e0ca0b48b0d99fd98e755a"  # el que fija test_32


def test_el_original_de_Main_Screen_sigue_intacto():
    assert hashlib.sha256(ORIGINAL.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == SHA_ORIGINAL_LF
    assert subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "p9/reversion/powerapps/Main_Screen.yaml"], cwd=REPO).returncode == 0


def test_la_copia_con_boton_difiere_solo_por_el_bloque():
    original, copia = ORIGINAL.read_text(encoding="utf-8"), CON_BOTON.read_text(encoding="utf-8")
    assert copia == aplicar_boton.aplicar(original)
    assert copia.replace(aplicar_boton.BLOQUE, "", 1) == original  # quitar el bloque devuelve el original byte a byte
    assert len(copia.splitlines()) == len(original.splitlines()) + 16


def test_el_boton_es_hijo_de_cntControlDepositosP9_y_navega_a_la_pantalla_nueva():
    doc = yaml.safe_load(CON_BOTON.read_text(encoding="utf-8"))
    raiz = doc["Screens"]["Main_Screen"]["Children"]
    contenedor = next(list(x.values())[0] for x in raiz if "cntControlDepositosP9" in x)
    nombres = [list(x)[0] for x in contenedor["Children"]]
    assert nombres.index("btnImportacionMasivaP9") == nombres.index("btnActualizarP9_1") + 1
    boton = contenedor["Children"][nombres.index("btnImportacionMasivaP9")]["btnImportacionMasivaP9"]
    assert boton["Properties"]["OnSelect"] == "=Navigate(P9_Confirmacion_Masiva, ScreenTransition.Fade)"
    assert boton["Properties"]["Text"] == '="IMPORTACIÓN MASIVA"'
    assert "P9_Confirmacion_Masiva" in yaml.safe_load((PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))["Screens"]
    todos = list(controles(raiz))
    assert len(todos) == 80 and len({n for n, _ in todos}) == 80  # 79 originales + 1


def test_el_boton_no_se_solapa_con_los_controles_de_la_cabecera():
    doc = yaml.safe_load(CON_BOTON.read_text(encoding="utf-8"))
    cabecera = dict(controles(doc["Screens"]["Main_Screen"]["Children"]))
    b = cabecera["btnImportacionMasivaP9"]["Properties"]
    x0, x1 = int(b["X"][1:]), int(b["X"][1:]) + int(b["Width"][1:])
    for otro in ("lblSubtituloControlP9_1", "btnActualizarP9_1"):
        o = cabecera[otro]["Properties"]
        ox0 = int(o["X"][1:])
        assert x1 <= ox0 or x0 >= ox0 + int(o["Width"][1:]), otro


def test_el_prototipo_no_toca_ningun_archivo_de_produccion():
    assert subprocess.run(["git", "status", "--porcelain", "--", ":!proto_masiva"], cwd=REPO, capture_output=True,
                          text=True).stdout.strip() == ""
