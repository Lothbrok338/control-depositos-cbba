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
    # a854d9b4d36a1bb2df473814c38dd7977855b1264650b9bf0c4025b3e8809b71 fue el YAML validado
    # en tenant (checkpoint 7151fbd). El actual es la copia exacta de
    # Main_Screen_CORREGIDO_DROPDOWN.yaml, validado en tenant: verificación previa
    # REVERSIÓN PENDIENTE y selector de banco como Classic/DropDown.
    assert hashlib.sha256(APP.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == (
        '99486d668690e425568ca18c5d6d3ff6d953fe4529e0ca0b48b0d99fd98e755a')
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


# --- UX "REVERSIÓN PENDIENTE": verificación previa al abrir VER ---

def formula(nombre, propiedad):
    return C[nombre]['Properties'][propiedad]


def test_ver_consulta_con_seis_argumentos_solo_para_asignado_y_sin_tocar_v42():
    ver = formula('btnAsignarP9_1', 'OnSelect')
    assert ver.count('P9_SOLICITAR_REVERSION.Run') == 1
    assert argumentos(ver, 'P9_SOLICITAR_REVERSION.Run') == [
        '"CONSULTAR"', 'varDepositoSeleccionado.ID', 'varDepositoSeleccionado.CLAVE_TRANSACCION',
        '""', '""', '""']
    assert ver.index('ESTADO_ASIGNACION.Value = "ASIGNADO"') < ver.index('P9_SOLICITAR_REVERSION.Run')
    # El detalle se abre antes de consultar y la verificación no confirma ni escribe.
    assert ver.index('UpdateContext({mostrarConfirmacion: true})') < ver.index('"VERIFICANDO"') < ver.index('P9_SOLICITAR_REVERSION.Run')
    assert 'P9_ASIGNAR_DEPOSITO' not in ver
    assert not re.search(r'\b(?:Patch|User|Remove|Collect)\s*\(', sin_cadenas(ver))
    assert formula('btnConfirmarDepositoP9_1', 'OnSelect').count('P9_ASIGNAR_DEPOSITO.Run') == 1


def test_estados_del_boton_y_su_habilitacion():
    texto = formula('btnSolicitarReversionP9', 'Text')
    modo = formula('btnSolicitarReversionP9', 'DisplayMode')
    for estado, rotulo in (('VERIFICANDO', 'VERIFICANDO…'), ('ACTIVA', 'REVERSIÓN PENDIENTE'),
                           ('ERROR', 'NO SE PUDO VERIFICAR')):
        assert f'e = "{estado}",\n' in texto and f'"{rotulo}"' in texto
        assert f'e = "{estado}"' in modo
    assert texto.rstrip().endswith('"SOLICITAR REVERSIÓN"\n    )\n)')
    # LISTO y SIN_VERIFICAR (consulta aún no hecha para este depósito) no deshabilitan.
    assert '"LISTO"' not in modo and 'SIN_VERIFICAR' in texto
    assert 'DisplayMode.Disabled,\n    DisplayMode.Edit' in modo
    assert 'Coalesce(varP9RevCargando, false)' in modo
    # El estado solo vale para el depósito verificado.
    for f in (texto, modo, formula('btnSolicitarReversionP9', 'Tooltip')):
        assert 'varP9RevVerif.DepositoID = varDepositoSeleccionado.ID' in f


def test_tooltip_activa_muestra_id_estado_fase_y_limite_y_error_exacto():
    tip = formula('btnSolicitarReversionP9', 'Tooltip')
    for campo, rotulo in (('SolicitudID', 'ID'), ('Decision', 'Estado:'), ('Fase', 'Fase:'),
                          ('FechaLimite', 'Fecha límite (UTC):')):
        assert f'!IsBlank(varP9RevActiva.{campo})' in tip and rotulo in tip
    assert '"No fue posible verificar si existe una reversión activa. Cierra y vuelve a intentar."' in tip
    assert '"Solicitar la reversión de esta confirmación mediante aprobación"' in tip


def test_verificacion_falla_cerrada_y_solo_listo_habilita():
    ver = formula('btnAsignarP9_1', 'OnSelect')
    # Excepción técnica o cualquier respuesta distinta de LISTO/PENDIENTE_EXISTENTE => ERROR.
    assert ver.count('Estado: "ERROR"') == 2
    assert ver.count('Estado: "LISTO"') == 1 and ver.count('Estado: "ACTIVA"') == 1
    assert ver.index('varP9RevPrecheck.resultado = "PENDIENTE_EXISTENTE"') < ver.index('Estado: "ACTIVA"') \
        < ver.index('varP9RevPrecheck.resultado = "LISTO"') < ver.index('Estado: "LISTO"')
    assert ver.count('Set(varP9RevVerif, Blank())') == 1 and ver.count('Set(varP9RevActiva, Blank())') == 1
    assert ver.index('Set(varP9RevVerif, Blank())') < ver.index('UpdateContext({mostrarConfirmacion: true})')


def test_ramas_con_solicitud_conocida_fijan_activa():
    abrir = formula('btnSolicitarReversionP9', 'OnSelect')
    enviar = formula('btnEnviarReversionP9', 'OnSelect')
    assert abrir.count('varP9RevActiva,') == 1 and enviar.count('varP9RevActiva,') == 3
    for f in (abrir, enviar):
        assert f.count('Set(varP9RevVerif, {DepositoID: varDepositoSeleccionado.ID, Estado: "ACTIVA"})') == f.count('varP9RevActiva,')
    for mensaje in ('"SOLICITUD DE REVERSIÓN ENVIADA · ID "', '"Se recuperó la solicitud existente · ID "',
                    '"Ya existe una solicitud activa · ID "'):
        antes = enviar[:enviar.index('Set(varP9RevMensaje, ' + mensaje)]
        assert antes.rstrip().endswith('Estado: "ACTIVA"});'), mensaje
    # No cambian ni los seis argumentos ni el flujo de confirmación del modal.
    assert argumentos(enviar, 'P9_SOLICITAR_REVERSION.Run')[0] == '"ENVIAR"'


# --- Selector de banco: Classic/DropDown validado en tenant ---

BANCOS = ['(Todos)', 'BNB', 'BCP', 'BISA', 'BANCO UNIÓN', 'BANCO ECONÓMICO', 'BMSC']
CUENTAS = [  # etiqueta, cuenta; orden y valores del checkpoint 7151fbd
    ('MN · 3000100152', '3000100152'), ('ME · 3400041236', '3400041236'),
    ('AHORRO · 3501936692', '3501936692'), ('CLÍNICA · 3000100705', '3000100705'),
    ('MN · 301-5005684-3-97', '301-5005684-3-97'), ('ME · 301-5005425-2-71', '301-5005425-2-71'),
    ('MN · 0696870039', '0696870039'), ('ME · 0696872023', '0696872023'),
    ('MN · 10000003224552', '10000003224552'), ('ME · 20000003224544', '20000003224544'),
    ('CTA. CTE. · 3041210569', '3041210569'), ('AHORRO · 3051446946', '3051446946'),
    ('CTA. CTE. · 1000872489', '1000872489')]


def test_selector_banco_dropdown_con_los_mismos_siete_bancos():
    banco = C['cmbBancoP9_1']
    props = banco['Properties']
    assert banco['Control'] == 'Classic/DropDown@2.3.1'
    assert props['Items'] == '=[' + ', '.join(f'"{b}"' for b in BANCOS) + ']'
    assert props['Items.Value'] == '=Value'
    assert props['Default'] == '="(Todos)"'
    assert props['OnChange'] == '=Reset(cmbCuentaP9_1)'
    # El ComboBox clásico y sus propiedades no deben volver.
    for prop in ('DisplayFields', 'SearchFields', 'SelectMultiple', 'IsSearchable'):
        assert prop not in props, prop
    assert 'ComboBox' not in banco['Control']
    assert PADRES['cmbBancoP9_1'] == PADRES['cmbCuentaP9_1'] == 'cntControlDepositosP9'


def test_referencias_al_banco_usan_value():
    texto = APP.read_text(encoding='utf-8')
    assert texto.count('cmbBancoP9_1.Selected.Value') == 9
    assert 'cmbBancoP9_1.Selected.Banco' not in texto
    cuenta = C['cmbCuentaP9_1']['Properties']
    assert cuenta['DisplayMode'] == ('=If(IsBlank(cmbBancoP9_1.Selected.Value) || '
                                     'cmbBancoP9_1.Selected.Value = "(Todos)", DisplayMode.Disabled, DisplayMode.Edit)')
    assert cuenta['Items'].lstrip().startswith('=Switch(\n    cmbBancoP9_1.Selected.Value,')


def test_cuentas_bancarias_sin_alteraciones():
    cuenta = C['cmbCuentaP9_1']
    props = cuenta['Properties']
    assert cuenta['Control'] == 'Classic/ComboBox@2.4.0'
    pares = re.findall(r'\{Label: "([^"]+)", Cuenta: "([^"]+)"\}', props['Items'])
    assert pares == CUENTAS and len(pares) == 13
    assert props['DisplayFields'] == '=["Label"]' and props['SearchFields'] == '=["Label"]'
    assert 'Table({Label: "", Cuenta: ""})' in props['Items']
    for banco in BANCOS[1:]:
        assert f'"{banco}", Table(' in props['Items']
    assert APP.read_text(encoding='utf-8').count('cmbCuentaP9_1.Selected.Cuenta') == 4  # filtros sin cambios
