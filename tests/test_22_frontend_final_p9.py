"""Frontend vigente P9 (P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt): sin código de estudiante y limitado a los últimos 2 meses.
Derivado de la base validada en tenant (p9/powerapps/_base_validada_tenant). Revisión estática del YAML: no es ejecución en Power Apps Studio."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from p9 import contrato as C  # noqa: E402

pytestmark = pytest.mark.p9

RUTA = RAIZ / "p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt"
SHA = "3de2d78fe1c789ff5aea0ce76d6b9ea7ae5411d226558022c83990986c06298b"
BASE = RAIZ / "p9/powerapps/_base_validada_tenant/P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt"
SHA_BASE = "595a95b4434f4e0f9d1a2737a35dcfaf0f993db1e3193c9050a5187bb828fc64"
LIMITE = "DateAdd(Today(), -2, TimeUnit.Months)"
TXT = RUTA.read_text(encoding="utf-8")
RAIZ_YAML = yaml.safe_load(TXT)


def nodos(items):
    for it in items:
        (n, c), = it.items()
        yield n, c
        yield from nodos(c.get("Children", []))


CTRL = dict(nodos(RAIZ_YAML))


def sin_cadenas(texto):
    return re.sub(r'"(?:""|[^"])*"', '""', texto)


def test_sha256_del_frontend_final_y_unico_frontend_p9():
    assert hashlib.sha256(RUTA.read_bytes()).hexdigest() == SHA
    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == SHA_BASE  # la base validada en tenant se conserva intacta, archivada aparte
    assert sorted(p.name for p in (RAIZ / "p9/powerapps").glob("*.txt")) == [RUTA.name]  # un solo frontend vigente en la carpeta
    for obsoleto in ("P9_CONTROL_DEPOSITOS_COMPLETO.txt", "P9_CONTROL_DEPOSITOS_MANUAL_LAYOUT.txt", "P9RootContainer_PEGAR_EN_STUDIO.txt",
                     "P9_RESTO_A_FILTROS_HEADERS.txt", "FORMULAS_POWER_FX_P9.md"):
        assert not (RAIZ / obsoleto).exists()


def test_un_solo_control_raiz_manual_layout_pegable():
    assert len(RAIZ_YAML) == 1 and list(RAIZ_YAML[0]) == ["cntControlDepositosP9"]
    raiz = RAIZ_YAML[0]["cntControlDepositosP9"]
    assert raiz["Control"].startswith("GroupContainer") and raiz["Variant"] == "ManualLayout"
    for prohibido in ("AutoLayout", "Screens:", "Form@"):
        assert prohibido not in TXT


def test_la_app_no_escribe_en_sharepoint():
    codigo = sin_cadenas(TXT)
    for prohibido in ("Patch(", "SubmitForm(", "Remove(", "RemoveIf(", "UpdateIf(", "Collect(", "ClearCollect("):
        assert prohibido not in codigo, prohibido


def test_run_con_8_argumentos_posicionales_sin_registro_opcional():
    """Trigger V4.2: los 8 inputs en `required` => 8 posicionales (ID, CLAVE, ESTUDIANTE, CODIGO_ESTUDIANTE "", SOLICITADO, SEDE, OBSERVACION, USUARIO)."""
    assert TXT.count("P9_ASIGNAR_DEPOSITO.Run(") == 1
    run = re.search(r"P9_ASIGNAR_DEPOSITO\.Run\((.*?)\n\s*\)\n\s*\)", TXT, re.S)[1]
    args = [a.strip() for a in run.strip().split(",\n")]
    assert len(args) == len(C.REQUERIDOS_TRIGGER_V4_2) == len(C.ENTRADAS) == 8
    patrones = [r"varDepositoSeleccionado\.ID$", r"varDepositoSeleccionado\.CLAVE_TRANSACCION$", r"txtEstudianteP9", r'^""$',  # 4.º = CODIGO_ESTUDIANTE: vacío
                r"txtSolicitadoP9", r"txtSedeP9", r"txtObservacionP9", r"User\(\)\.Email$"]
    assert all(re.search(p, a) for a, p in zip(args, patrones))
    assert "{" not in run and "text_5" not in TXT  # ningún registro opcional


def test_solo_lee_las_salidas_que_define_el_flujo_v3():
    leidas = set(re.findall(r"varRespuestaP9\.([A-Za-z_]+)", TXT))
    assert leidas == {"resultado", "codigo", "mensaje"} and leidas <= set(C.SALIDAS)
    for r in ("ASIGNADO", "NO_DISPONIBLE", "CONFLICTO"):
        assert f'"{r}"' in TXT
    assert 'Notify("ERROR (' in TXT or "ERROR (" in TXT


def test_solo_creditos_y_solo_estados_disponible_y_asignado():
    items = CTRL["galDepositosP9"]["Properties"]["Items"]
    assert items.count('TIPO_MOVIMIENTO = "CRÉDITO"') == 2  # ambas etapas de la búsqueda
    assert '"DÉBITO"' not in TXT
    assert items.count('ESTADO_ASIGNACION.Value = "DISPONIBLE"') == 2 and items.count('ESTADO_ASIGNACION.Value = "ASIGNADO"') == 2
    assert set(re.findall(r"\[@(\w+)\]", TXT)) == {"Depositos_Activos"}


def test_busqueda_descripcion_en_dos_etapas():
    items = CTRL["galDepositosP9"]["Properties"]["Items"]
    assert "txtTextoP9" in items and "With(" in items and "in Lower(Coalesce(DESCRIPCION" in items
    assert items.index("With(") < items.index("in Lower(Coalesce(DESCRIPCION")


def test_filtro_banco_cuenta_dependiente():
    assert CTRL["cmbBancoP9"]["Properties"]["OnChange"] == "=Reset(cmbCuentaP9)"
    assert "cmbBancoP9" in CTRL["cmbCuentaP9"]["Properties"]["Items"]


def test_estado_visible_y_trazabilidad():
    assert 'If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO", "CONFIRMADO", "DISPONIBLE")' in CTRL["rowEstadoP9"]["Properties"]["Text"]
    datos = CTRL["rowDatosConfirmacionP9"]["Properties"]["Text"]
    assert "USUARIO_ASIGNACION" in datos and "FECHA_HORA_ASIGNACION" in datos
    for columna in ("FECHA_MOVIMIENTO", "DESCRIPCION", "CODIGO_ASIGNACION", "IMPORTE"):
        assert columna in TXT


def test_columnas_usadas_existen_en_la_lista():
    esquema = json.loads((RAIZ / "p8/esquema_listas_p8.json").read_text(encoding="utf-8"))["Depositos_Activos"]["columnas"]
    reales = {c["nombre_tecnico"] for c in esquema}
    usadas = set(re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", sin_cadenas(TXT)))
    assert usadas <= reales | {"P9_ASIGNAR_DEPOSITO"}, usadas - reales


def test_observacion_opcional_y_campos_obligatorios():
    onselect = CTRL["btnConfirmarDepositoP9"]["Properties"]["OnSelect"]
    validacion = onselect[:onselect.index("P9_ASIGNAR_DEPOSITO.Run(")]
    for obligatorio in ("txtEstudianteP9", "txtSolicitadoP9", "txtSedeP9"):
        assert obligatorio in validacion
    assert "txtObservacionP9" not in validacion  # opcional


def test_confirmar_relee_antes_y_despues_de_llamar_al_flujo():
    onselect = CTRL["btnConfirmarDepositoP9"]["Properties"]["OnSelect"]
    i = onselect.index("P9_ASIGNAR_DEPOSITO.Run(")
    assert "Refresh(Depositos_Activos)" in onselect[:i] and "LookUp(Depositos_Activos, ID =" in onselect[:i]
    assert "Refresh(Depositos_Activos)" in onselect[i:] and "LookUp(Depositos_Activos, ID =" in onselect[i:]
    assert re.search(r"Set\(\s*varRespuestaP9,\s*P9_ASIGNAR_DEPOSITO\.Run\(", onselect)
    assert "IfError(" in onselect


# ------------------------------------------------------------------ cambio 1: sin código de estudiante
def test_codigo_de_estudiante_no_existe_en_la_interfaz():
    assert not re.search(r"estudiante\s*P9|CODIGO_ESTUDIANTE|c[oó]digo\s+(de\s+)?estudiante|CodigoEstudiante", TXT.replace("txtEstudianteP9", "").replace("lblEstudianteP9", ""), re.I)
    assert not [n for n in CTRL if "codigoestudiante" in n.lower()]
    assert "txtEstudianteP9" in CTRL and "lblEstudianteP9" in CTRL  # el nombre del estudiante sigue
    assert "CÓDIGO ASIGNACIÓN" in TXT and "CODIGO_ASIGNACION" in TXT  # el código del movimiento bancario NO es el del estudiante


def test_la_confirmacion_no_pide_codigo_de_estudiante():
    onselect = CTRL["btnConfirmarDepositoP9"]["Properties"]["OnSelect"]
    assert "Código estudiante" not in onselect and "Completa Estudiante, Solicitado por y Sede." in onselect
    for nombre in ("btnCancelarConfirmacionP9",):
        assert "Codigo" not in CTRL[nombre]["Properties"]["OnSelect"]
    assert "Codigo" not in CTRL["cntConfirmarDepositoP9"]["Properties"].get("Visible", "")


def test_modal_reubicado_sin_huecos_ni_solapes():
    pos = {n: (CTRL[n]["Properties"]["X"], CTRL[n]["Properties"]["Y"]) for n in ("txtEstudianteP9", "txtSolicitadoP9", "txtSedeP9", "txtObservacionP9")}
    assert len(set(pos.values())) == 4  # ningún campo encima de otro
    assert pos["txtEstudianteP9"][1] == pos["txtSolicitadoP9"][1] == "=208" and pos["txtSedeP9"][1] == "=288"


# ------------------------------------------------------------------ cambio 2: ventana de 2 meses
def test_ventana_de_2_meses_en_ambas_etapas_de_la_galeria():
    items = CTRL["galDepositosP9"]["Properties"]["Items"]
    assert items.count(f"FECHA_MOVIMIENTO >= {LIMITE},") == 2 and items.count("FECHA_MOVIMIENTO <= Today(),") == 2
    # el límite es un argumento propio de Filter (AND), antes de los filtros que el usuario controla y sin `||`
    for linea in items.splitlines():
        if LIMITE in linea or "<= Today()" in linea:
            assert "||" not in linea and "IsBlank" not in linea
    primera, base = re.split(r"\bWith\(", items, maxsplit=1)  # etapa 1 (sin texto) y etapa 2 (With + filtro local)
    for etapa in (primera, base.split("baseP9: Filter(", 1)[1]):
        assert etapa.index(LIMITE) < etapa.index("IsBlank(dpFechaDesdeP9")
    assert 'TIPO_MOVIMIENTO = "CRÉDITO"' in items and items.count("ESTADO_ASIGNACION.Value") == 4


def test_selectores_de_fecha_por_defecto():
    desde, hasta = CTRL["dpFechaDesdeP9"]["Properties"], CTRL["dpFechaHastaP9"]["Properties"]
    assert desde["DefaultDate"] == f"={LIMITE}" and hasta["DefaultDate"] == "=Today()"
    assert "Blank()" not in desde["DefaultDate"] + hasta["DefaultDate"]
    assert "Reset(dpFechaDesdeP9)" in CTRL["btnLimpiarP9"]["Properties"]["OnSelect"] and "Reset(dpFechaHastaP9)" in CTRL["btnLimpiarP9"]["Properties"]["OnSelect"]


def test_aviso_visible_de_la_ventana():
    texto = CTRL["lblAyudaResultadosP9"]["Properties"]["Text"]
    assert "Últimos 2 meses" in texto and LIMITE in texto and "CRÉDITOS" in texto


def test_no_se_reintroduce_startswith_en_descripcion_ni_search():
    codigo = sin_cadenas(TXT)
    assert "Search(" not in codigo and not re.search(r"StartsWith\(\s*DESCRIPCION", codigo)
    assert re.findall(r"StartsWith\((\w+)", codigo) == ["CODIGO_ASIGNACION"] * 2  # solo el filtro por código de asignación, como en la base validada
    assert codigo.count("in Lower(Coalesce(DESCRIPCION") == 1


def _modelo_ventana(filas, hoy, desde_picker, hasta_picker):
    """Modelo en Python del predicado de la galería (mismos argumentos de Filter, en AND)."""
    from datetime import timedelta
    mes = hoy.month - 2 or 12
    anio = hoy.year - (1 if hoy.month <= 2 else 0)
    import calendar
    limite = hoy.replace(year=anio, month=mes, day=min(hoy.day, calendar.monthrange(anio, mes)[1]))
    return [f for f in filas
            if f["tipo"] == "CRÉDITO" and limite <= f["fecha"] <= hoy
            and (desde_picker is None or f["fecha"] >= desde_picker) and (hasta_picker is None or f["fecha"] <= hasta_picker)], limite


def test_modelo_nunca_muestra_mas_de_2_meses_aunque_se_elija_una_fecha_anterior():
    from datetime import date
    hoy = date(2026, 10, 2)
    filas = [{"fecha": date(2026, 10, 2), "tipo": "CRÉDITO"}, {"fecha": date(2026, 8, 2), "tipo": "CRÉDITO"}, {"fecha": date(2026, 8, 1), "tipo": "CRÉDITO"},
             {"fecha": date(2025, 1, 5), "tipo": "CRÉDITO"}, {"fecha": date(2026, 9, 1), "tipo": "DÉBITO"}]
    for desde in (None, date(2026, 8, 2), date(2020, 1, 1), date(2026, 9, 15)):
        vistas, limite = _modelo_ventana(filas, hoy, desde, hoy)
        assert limite == date(2026, 8, 2) and all(limite <= f["fecha"] <= hoy and f["tipo"] == "CRÉDITO" for f in vistas)
    assert len(_modelo_ventana(filas, hoy, date(2020, 1, 1), hoy)[0]) == 2  # 02/10 y 02/08; el 01/08, el de 2025 y el DÉBITO no
    assert len(filas) == 5  # el modelo solo filtra la vista: no borra nada
