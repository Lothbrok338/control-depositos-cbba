"""Frontend final P9 (P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt, validado por el usuario en el tenant).
Revisión estática del YAML: no es ejecución en Power Apps Studio."""
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

RUTA = RAIZ / "p9/powerapps/P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt"
SHA = "595a95b4434f4e0f9d1a2737a35dcfaf0f993db1e3193c9050a5187bb828fc64"
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
    assert sorted(p.name for p in (RAIZ / "p9/powerapps").glob("*.txt")) == [RUTA.name]  # ningún frontend obsoleto confundible
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


def test_run_con_los_8_argumentos_en_el_orden_del_flujo():
    assert TXT.count("P9_ASIGNAR_DEPOSITO.Run(") == 1
    run = re.search(r"P9_ASIGNAR_DEPOSITO\.Run\((.*?)\n\s*\)\n\s*\)", TXT, re.S)[1]
    args = [a.strip() for a in run.strip().split(",\n")]
    assert len(args) == len(C.ENTRADAS) == 8
    patrones = [r"varDepositoSeleccionado\.ID$", r"varDepositoSeleccionado\.CLAVE_TRANSACCION$", r"txtEstudianteP9", r"txtCodigoEstudianteP9",
                r"txtSolicitadoP9", r"txtSedeP9", r"txtObservacionP9", r"User\(\)\.Email$"]
    assert all(re.search(p, a) for a, p in zip(args, patrones))


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
    for obligatorio in ("txtEstudianteP9", "txtCodigoEstudianteP9", "txtSolicitadoP9", "txtSedeP9"):
        assert obligatorio in validacion
    assert "txtObservacionP9" not in validacion  # opcional


def test_confirmar_relee_antes_y_despues_de_llamar_al_flujo():
    onselect = CTRL["btnConfirmarDepositoP9"]["Properties"]["OnSelect"]
    i = onselect.index("P9_ASIGNAR_DEPOSITO.Run(")
    assert "Refresh(Depositos_Activos)" in onselect[:i] and "LookUp(Depositos_Activos, ID =" in onselect[:i]
    assert "Refresh(Depositos_Activos)" in onselect[i:] and "LookUp(Depositos_Activos, ID =" in onselect[i:]
    assert re.search(r"Set\(\s*varRespuestaP9,\s*P9_ASIGNAR_DEPOSITO\.Run\(", onselect)
    assert "IfError(" in onselect
