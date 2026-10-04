"""Protege la pantalla entregada y pegada por el usuario, sin ejecutar Power Fx."""
from pathlib import Path
import hashlib
import re

import pytest
import yaml

from test_29_reversion_frontend_p9 import argumentos, sin_cadenas

pytestmark = pytest.mark.p9
APP = Path(__file__).resolve().parents[1] / 'p9/reversion/powerapps/Main_Screen.yaml'
DOC = yaml.safe_load(APP.read_text(encoding='utf-8'))
SCREEN = DOC['Screens']['Main_Screen']


def recorrer(items, padre='Main_Screen'):
    for item in items:
        (nombre, control), = item.items()
        yield nombre, control, padre
        yield from recorrer(control.get('Children', []), nombre)


NODOS = list(recorrer(SCREEN['Children']))
C = {n: c for n, c, _ in NODOS}
PADRES = {n: p for n, _, p in NODOS}


def test_fuente_entregada_exacta_y_nombres_sin_duplicados():
    # Git puede convertir CRLF/LF; ningún otro byte del YAML puede cambiar.
    assert hashlib.sha256(APP.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == (
        'a854d9b4d36a1bb2df473814c38dd7977855b1264650b9bf0c4025b3e8809b71')
    assert len(NODOS) == len(C) == 79
    assert set(DOC['Screens']) == {'Main_Screen'}


def test_modal_delante_del_contenedor_opaco_y_visible_por_variable():
    assert [next(iter(x)) for x in SCREEN['Children']] == [
        'cntControlDepositosP9', 'overlayReversionP9', 'cntSolicitarReversionP9']
    for n in ('overlayReversionP9', 'cntSolicitarReversionP9'):
        assert PADRES[n] == 'Main_Screen'
        assert C[n]['Properties']['Visible'] == '=Coalesce(varP9RevVisible, false)'
    assert C['overlayReversionP9']['Properties']['X'] == '=0'
    assert C['overlayReversionP9']['Properties']['Y'] == '=0'
    assert PADRES['btnSolicitarReversionP9'] == 'cntConfirmarDepositoP9_1'


def test_v42_con_ocho_argumentos_y_codigo_estudiante_vacio():
    formula = C['btnConfirmarDepositoP9_1']['Properties']['OnSelect']
    assert argumentos(formula, 'P9_ASIGNAR_DEPOSITO.Run') == [
        'varDepositoSeleccionado.ID', 'varDepositoSeleccionado.CLAVE_TRANSACCION',
        'Trim(txtEstudianteP9_1.Text)', '""', 'Trim(txtSolicitadoP9_1.Text)',
        'Trim(txtSedeP9_1.Text)', 'Trim(txtObservacionP9_1.Text)', 'User().Email']


def test_reversion_con_seis_argumentos_y_sin_identidad_libre():
    abrir = C['btnSolicitarReversionP9']['Properties']['OnSelect']
    enviar = C['btnEnviarReversionP9']['Properties']['OnSelect']
    assert argumentos(abrir, 'P9_SOLICITAR_REVERSION.Run') == [
        '"CONSULTAR"', 'varDepositoSeleccionado.ID', 'varDepositoSeleccionado.CLAVE_TRANSACCION',
        '""', '""', '""']
    assert argumentos(enviar, 'P9_SOLICITAR_REVERSION.Run') == [
        '"ENVIAR"', 'varP9RevSnapshot.ID', 'varP9RevSnapshot.CLAVE_TRANSACCION',
        'varP9RevETag', 'varP9RevMotivoEnvio', 'varP9RevUID']
    assert 'Set(varP9RevETag, varP9RevRespuesta.etag)' in abrir
    assert 'Set(varP9RevVisible, true)' in abrir
    assert 'IsBlank(Trim(txtMotivoReversionP9.Text))' in enviar
    for formula in (abrir, enviar):
        assert not re.search(r'\b(?:Patch|User)\s*\(', sin_cadenas(formula))


def test_columnas_visuales_y_datos_conservados():
    nombres = ['headImporteP9_1', 'headDescripcionP9_1', 'headCodigoP9_1',
               'headEstadoP9', 'headDatosConfirmacionP9', 'headAccionP9_1']
    def x(n):
        texto = C[n]['Properties']['X'][1:]
        return 1366 - int(texto.split('-')[1]) if texto.startswith('Parent.Width') else int(texto)
    assert [x(n) for n in nombres] == sorted(x(n) for n in nombres)
    assert C['headCodigoP9_1']['Properties']['Text'] == '="CÓDIGO DE ASIGNACIÓN"'
    assert C['rowCodigoP9_1']['Properties']['Text'] == '=ThisItem.CODIGO_ASIGNACION'
    assert 'ThisItem.DESCRIPCION' in C['rowDescripcionP9_1']['Properties']['Text']
    assert int(C['headDescripcionP9_1']['Properties']['Width'][1:]) >= 260
    for n in ('lblResumenConfirmacionP9_1', 'lblEstadoConfirmacionP9'):
        assert C[n]['Control'] == 'Classic/Button@2.2.0'
        for esquina in ('TopLeft', 'TopRight', 'BottomLeft', 'BottomRight'):
            assert C[n]['Properties']['Radius' + esquina] == '=12'


def test_referencias_a_controles_existentes():
    patron = r'\b((?:lbl|btn|txt|rect|cnt|gal|ico|img|cmb|drp|overlay)[A-Z][A-Za-z0-9_]*)\b'
    for nombre, control, _ in NODOS:
        for prop, valor in control.get('Properties', {}).items():
            for ref in re.findall(patron, sin_cadenas(str(valor))):
                assert ref in C, (nombre, prop, ref)
