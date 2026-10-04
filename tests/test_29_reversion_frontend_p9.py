"""Regresión de la extensión de reversión: árbol, contrato y Power Fx estático.

No ejecuta Power Fx ni certifica el renderizado o los conectores de Studio.
Compara la base completa después de quitar exclusivamente los controles nuevos.
"""
from copy import deepcopy
from pathlib import Path
import json
import re

import pytest
import yaml

pytestmark = pytest.mark.p9
RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / "p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt"
APP = RAIZ / "p9/reversion/powerapps"
FRONT = APP / "P9_CONTROL_INGRESOS_CON_REVERSION.txt"
PEGAR = APP / "SOLICITAR_REVERSION_PEGAR.yaml"
FORMULAS = APP / "FORMULAS_EXACTAS.md"
BASE_DOC = yaml.safe_load(BASE.read_text(encoding="utf-8"))
FRONT_DOC = yaml.safe_load(FRONT.read_text(encoding="utf-8"))
PEGAR_DOC = yaml.safe_load(PEGAR.read_text(encoding="utf-8"))

NUEVOS = {
    "btnSolicitarReversionP9", "overlayReversionP9", "cntSolicitarReversionP9",
    "rectCabeceraReversionP9", "lblTituloReversionP9", "lblDepositoReversionP9",
    "lblAsignacionReversionP9", "lblMotivoReversionP9", "txtMotivoReversionP9",
    "lblPlazoReversionP9", "lblResultadoReversionP9", "btnCancelarReversionP9",
    "btnEnviarReversionP9", "lblUIDReversionP9",
}


def preorden(items, padre=None):
    for item in items:
        (nombre, ctrl), = item.items()
        yield nombre, ctrl, padre
        yield from preorden(ctrl.get("Children", []), nombre)


F = {n: c for n, c, _ in preorden(FRONT_DOC)}
C = {n: c for n, c, _ in preorden(PEGAR_DOC)}
PADRE = {n: p for n, _, p in preorden(FRONT_DOC)}
ABRIR = C["btnSolicitarReversionP9"]["Properties"]["OnSelect"]
ENVIAR = C["btnEnviarReversionP9"]["Properties"]["OnSelect"]


def sin_cadenas(texto):
    return re.sub(r'"(?:[^"]|"")*"', '""', texto)


def sin_nuevos(items):
    resultado = []
    for item in deepcopy(items):
        (nombre, ctrl), = item.items()
        if nombre in NUEVOS:
            continue
        if "Children" in ctrl:
            ctrl["Children"] = sin_nuevos(ctrl["Children"])
        resultado.append(item)
    return resultado


def argumentos(formula, funcion):
    """Lee argumentos superiores; respeta literales y llamadas/records anidados."""
    inicio = formula.index(funcion + "(") + len(funcion) + 1
    args, actual, pila, cadena = [], [], [], False
    i = inicio
    while i < len(formula):
        c = formula[i]
        if cadena:
            actual.append(c)
            if c == '"':
                if i + 1 < len(formula) and formula[i + 1] == '"':
                    actual.append('"')
                    i += 1
                else:
                    cadena = False
        elif c == '"':
            cadena = True
            actual.append(c)
        elif c in "({[":
            pila.append(c)
            actual.append(c)
        elif c in ")}]":
            if not pila:
                assert c == ")"
                args.append("".join(actual).strip())
                return args
            assert pila.pop() == {")": "(", "}": "{", "]": "["}[c]
            actual.append(c)
        elif c == "," and not pila:
            args.append("".join(actual).strip())
            actual = []
        else:
            actual.append(c)
        i += 1
    raise AssertionError("Llamada sin cerrar")


def test_el_frontend_preserva_todos_los_bytes_originales_y_el_arbol_completo():
    assert FRONT.read_bytes().startswith(BASE.read_bytes())
    assert sin_nuevos(FRONT_DOC) == BASE_DOC
    base_nombres = {n for n, _, _ in preorden(BASE_DOC)}
    assert set(F) - base_nombres == NUEVOS
    assert not base_nombres & NUEVOS
    assert len(list(preorden(FRONT_DOC))) == len(F)


def test_pegado_solo_controles_y_coincide_con_la_copia_extendida():
    assert set(C) == NUEVOS
    assert [next(iter(x)) for x in PEGAR_DOC] == [
        "overlayReversionP9", "cntSolicitarReversionP9", "btnSolicitarReversionP9"]
    assert "Screens:" not in PEGAR.read_text(encoding="utf-8")
    for nombre, ctrl in C.items():
        assert ctrl == F[nombre], nombre
        assert set(ctrl) <= {"Control", "Variant", "Properties", "Children"}


def test_el_boton_solo_esta_dentro_de_ver_y_solo_para_asignados():
    assert PADRE["btnSolicitarReversionP9"] == "cntConfirmarDepositoP9"
    assert C["btnSolicitarReversionP9"]["Properties"]["Visible"] == (
        '=!IsBlank(varDepositoSeleccionado.ID) && varDepositoSeleccionado.ESTADO_ASIGNACION.Value = "ASIGNADO"')
    assert C["btnSolicitarReversionP9"]["Properties"]["Text"] == '="SOLICITAR REVERSIÓN"'
    for n in ("overlayReversionP9", "cntSolicitarReversionP9"):
        assert PADRE[n] == "cntControlDepositosP9"
        assert C[n]["Properties"]["Visible"] == "=Coalesce(varP9RevVisible, false)"
    hijos = F["cntControlDepositosP9"]["Children"]
    assert [next(iter(x)) for x in hijos[-3:]] == [
        "cntConfirmarDepositoP9", "overlayReversionP9", "cntSolicitarReversionP9"]


def test_boton_ocupa_el_espacio_libre_y_ningun_control_viejo_se_mueve():
    nuevo = C["btnSolicitarReversionP9"]["Properties"]
    previo = F["btnConfirmarDepositoP9"]["Properties"]
    for propiedad in ("X", "Y", "Width", "Height"):
        assert nuevo[propiedad] == previo[propiedad]
    assert 'ESTADO_ASIGNACION.Value = "DISPONIBLE"' in previo["Visible"]
    assert sin_nuevos(FRONT_DOC) == BASE_DOC


def test_todos_los_campos_mostrados_salen_del_snapshot_autoritativo_tipado():
    assert "ParseJSON(varP9RevRespuesta.snapshot_json)" in ABRIR
    for campo in ("ID", "IMPORTE"):
        assert f"{campo}: Value(s.{campo})" in ABRIR
    textos = (
        "CLAVE_TRANSACCION", "ESTADO_ASIGNACION", "CODIGO_ASIGNACION", "BANCO",
        "CUENTA_BANCARIA", "MONEDA", "ESTUDIANTE", "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION")
    for campo in textos:
        assert f"{campo}: Text(s.{campo})" in ABRIR
    etiquetas = C["lblDepositoReversionP9"]["Properties"]["Text"] + C["lblAsignacionReversionP9"]["Properties"]["Text"]
    for campo in textos[2:] + ("IMPORTE",):
        assert f"varP9RevSnapshot.{campo}" in etiquetas
    assert "varDepositoSeleccionado" not in etiquetas
    assert 'varP9RevSnapshot.ESTADO_ASIGNACION <> "ASIGNADO"' in ABRIR
    assert "IsBlank(varP9RevRespuesta.etag)" in ABRIR


def test_llamadas_solo_al_flujo_nuevo_con_seis_argumentos_sin_correo():
    assert argumentos(ABRIR, "P9_SOLICITAR_REVERSION.Run") == [
        '"CONSULTAR"', "varDepositoSeleccionado.ID", "varDepositoSeleccionado.CLAVE_TRANSACCION", '""', '""', '""']
    assert argumentos(ENVIAR, "P9_SOLICITAR_REVERSION.Run") == [
        '"ENVIAR"', "varP9RevSnapshot.ID", "varP9RevSnapshot.CLAVE_TRANSACCION", "varP9RevETag",
        "varP9RevMotivoEnvio", "varP9RevUID"]
    todas = "\n".join(str(v) for c in C.values() for v in c["Properties"].values())
    assert re.findall(r"\b(\w+)\.Run\s*\(", todas) == ["P9_SOLICITAR_REVERSION", "P9_SOLICITAR_REVERSION"]
    campos = set(re.findall(r"varP9RevRespuesta\.(\w+)", todas))
    assert campos == {
        "resultado", "codigo", "mensaje", "solicitud_id", "solicitud_uid", "snapshot_json", "etag",
        "estado_solicitud", "fase_proceso", "resultado_tecnico", "fecha_limite"}


def test_motivo_obligatorio_limite_y_proteccion_de_doble_clic():
    motivo = C["txtMotivoReversionP9"]["Properties"]
    assert motivo["MaxLength"] == "=4000" and motivo["Mode"] == "=TextMode.MultiLine"
    for formula in (ENVIAR, C["btnEnviarReversionP9"]["Properties"]["DisplayMode"]):
        assert "IsBlank(Trim(txtMotivoReversionP9.Text))" in formula
        assert "Len(Trim(txtMotivoReversionP9.Text)) > 4000" in formula
        assert "Coalesce(varP9RevCargando, false)" in formula
        assert "Coalesce(varP9RevAceptada, false)" in formula
    for boton in ("btnCancelarReversionP9", "btnSolicitarReversionP9"):
        assert "varP9RevCargando" in C[boton]["Properties"]["DisplayMode"]
    assert ENVIAR.index("Set(varP9RevCargando, true)") < ENVIAR.index("P9_SOLICITAR_REVERSION.Run")


def test_reintento_congela_payload_y_cancelar_no_lo_borra():
    assert "GUID()" not in ENVIAR
    assert "Set(varP9RevUID" not in ENVIAR and "Set(varP9RevETag" not in ENVIAR
    assert "Set(varP9RevSnapshot" not in ENVIAR
    congelar = argumentos(ENVIAR[ENVIAR.index("If(\n        !Coalesce"):], "If")
    assert congelar[0] == "!Coalesce(varP9RevEnvioIncierto, false)"
    assert "Set(varP9RevMotivoEnvio, Trim(txtMotivoReversionP9.Text))" in congelar[1]
    assert "Set(varP9RevEnvioIncierto, true)" in congelar[1]
    assert C["btnCancelarReversionP9"]["Properties"]["OnSelect"] == "=Set(varP9RevVisible, false)"
    abrir_args = argumentos(ABRIR, "If")
    assert abrir_args[0] == "Coalesce(varP9RevEnvioIncierto, false)"
    assert "Set(varP9RevVisible, true)" in abrir_args[1]
    assert "P9_SOLICITAR_REVERSION.Run" not in abrir_args[1] and "GUID()" not in abrir_args[1]
    motivo = C["txtMotivoReversionP9"]["Properties"]
    assert "varP9RevEnvioIncierto" in motivo["DisplayMode"]
    assert motivo["Reset"] == "=!Coalesce(varP9RevVisible, false)"
    assert "REINTENTAR MISMO ENVÍO" in C["btnEnviarReversionP9"]["Properties"]["Text"]
    errores = argumentos(ENVIAR, "IfError")[1]
    assert "Set(varP9RevEnvioIncierto, false)" not in errores
    assert "Set(varP9RevUID" not in errores and "Set(varP9RevETag" not in errores


def test_mensajes_de_creacion_exigen_respuesta_completa_y_no_prometen_reversion():
    assert "IsBlank(varP9RevRespuesta.solicitud_id)" in ENVIAR
    assert "varP9RevRespuesta.solicitud_uid <> varP9RevUID" in ENVIAR
    partes = argumentos(ENVIAR, "Switch")
    assert partes[0] == "varP9RevRespuesta.resultado"
    casos = dict(zip(partes[1:-1:2], partes[2:-1:2]))
    assert set(casos) == {'"ENVIADA"', '"EXISTENTE"', '"PENDIENTE_EXISTENTE"', '"CONFLICTO"'}
    assert 'Notify("SOLICITUD DE REVERSIÓN ENVIADA' in casos['"ENVIADA"']
    for clave in ('"EXISTENTE"', '"PENDIENTE_EXISTENTE"', '"CONFLICTO"'):
        assert "NotificationType.Success" not in casos[clave]
    assert "Set(varP9RevEnvioIncierto, false)" not in partes[-1]
    assert "REVERTIDO" not in ENVIAR
    resultado = C["lblResultadoReversionP9"]["Properties"]["Text"]
    estados = argumentos(resultado, "If")
    assert estados[0:2] == ['varP9RevFase = "EXPIRADA"', '"EXPIRADA · SIN DECISIÓN · NO EJECUTADA"']
    assert estados[2] == 'varP9RevResultadoTecnico = "REVERTIDO"'
    assert estados[3].startswith('"REVERTIDO · ID "')
    assert 'varP9RevDecision = "APROBADO"' not in resultado


def test_plazo_servidor_y_sin_cierre_local_de_solicitudes():
    plazo = C["lblPlazoReversionP9"]["Properties"]["Text"]
    assert "168 horas" in plazo and "varP9RevFechaLimite" in plazo
    assert "respuestas posteriores" in plazo
    codigo = sin_cadenas("\n".join(str(v) for c in C.values() for v in c["Properties"].values()))
    for prohibido in (r"\bNow\s*\(", r"\bToday\s*\(", r"\bDateAdd\s*\("):
        assert not re.search(prohibido, codigo)


def test_sin_escrituras_directas_ni_cambios_a_variables_de_base_ni_legacy():
    texto = "\n".join(str(v) for c in C.values() for v in c["Properties"].values())
    codigo = sin_cadenas(texto)
    for prohibido in (
        r"\bPatch\s*\(", r"\bSubmitForm\s*\(", r"\bRemove(?:If)?\s*\(", r"\bUpdateIf\s*\(",
        r"\bUpdateContext\s*\(", r"\bUser\s*\(", r"\bPrint\s*\(", r"\bNavigate\s*\(",
        r"\bRefresh\s*\(", r"\bClearCollect\s*\(", r"\bCollect\s*\(", r"\bSaveData\s*\("):
        assert not re.search(prohibido, codigo), prohibido
    escritos = re.findall(r"\bSet\s*\(\s*(\w+)\s*,", codigo)
    assert escritos and all(v.startswith("varP9Rev") for v in escritos)
    for prohibido in ("P9_ASIGNAR_DEPOSITO", "Depositos_Cargas", "COCHABAMBA", "$top=1", "COMPROBANTE PDF", "If-Match"):
        assert prohibido not in texto
    assert not re.search(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", texto)


CONTROL_REF = re.compile(r"\b((?:lbl|btn|txt|rect|cnt|gal|ico|img|cmb|drp|chk|tgl|frm|dtp|scr|overlay)[A-Z][A-Za-z0-9_]*)\b")


def test_nuevas_formulas_sin_referencias_inexistentes_ni_adelantadas():
    for documento in (FRONT_DOC, PEGAR_DOC):
        posiciones = {n: i for i, (n, _, _) in enumerate(preorden(documento))}
        for n in NUEVOS:
            for prop, valor in C[n]["Properties"].items():
                for ref in CONTROL_REF.findall(sin_cadenas(str(valor))):
                    assert ref in posiciones, (n, prop, ref)
                    assert posiciones[ref] < posiciones[n], (n, prop, ref)


def test_formulas_canonicas_balanceadas_y_sin_separadores_regionales():
    for nombre, control in C.items():
        for prop, formula in control["Properties"].items():
            assert isinstance(formula, str) and formula.startswith("="), (nombre, prop)
            assert formula.count('"') % 2 == 0, (nombre, prop)
            codigo = sin_cadenas(formula)
            assert ";;" not in codigo, (nombre, prop)
            pila = []
            for c in codigo:
                if c in "({[":
                    pila.append(c)
                elif c in ")}]":
                    assert pila and pila.pop() == {")": "(", "}": "{", "]": "["}[c], (nombre, prop)
            assert not pila, (nombre, prop)


def regional(formula):
    """Conversión independiente por tokens: los literales no cambian."""
    tokens = re.split(r'("(?:[^"]|"")*"|\'(?:[^\']|\'\')*\')', formula)
    return "".join(
        token if i % 2 else token.replace(";", "\x00").replace(",", ";").replace("\x00", ";;")
        for i, token in enumerate(tokens))


def test_documentacion_completa_coincide_con_canonicas_y_regionales():
    texto = FORMULAS.read_text(encoding="utf-8")
    secciones = {}
    for match in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", texto, re.M | re.S):
        secciones[match.group(1)] = re.findall(r"```powerfx\n(.*?)\n```", match.group(2), re.S)
    esperado = {f"{n}.{prop}": value[1:] for n, c in C.items() for prop, value in c["Properties"].items()}
    assert set(secciones) == set(esperado)
    for titulo, canonical in esperado.items():
        convertida = regional(canonical)
        assert secciones[titulo] == ([canonical] if convertida == canonical else [canonical, convertida]), titulo
    assert "sesión de la app" in texto and "cierra/reinicia la app" in texto
    assert "Provided by run-only user" in texto
    assert "no certifican" in texto.lower()


def test_geometria_modal_sin_cajas_fuera_ni_solape_entre_interactivos():
    # Dimensiones de escritorio: el contenedor de la base tiene espacio para 900 x 650.
    ancho, alto = 900, 650
    def numero(s):
        s = s[1:].replace("Parent.Width", str(ancho)).replace("Parent.Height", str(alto))
        assert re.fullmatch(r"[0-9 +\-]+", s)
        return eval(s, {"__builtins__": {}})
    cajas = {}
    for nombre, c, padre in preorden(PEGAR_DOC):
        if padre != "cntSolicitarReversionP9":
            continue
        p = c["Properties"]
        x, y, w, h = [numero(p[k]) for k in ("X", "Y", "Width", "Height")]
        assert 0 <= x and 0 <= y and x + w <= ancho and y + h <= alto, nombre
        cajas[nombre] = (x, y, w, h)
    permitidos = {frozenset({"rectCabeceraReversionP9", "lblTituloReversionP9"})}
    for i, a in enumerate(cajas):
        for b in list(cajas)[i + 1:]:
            ax, ay, aw, ah = cajas[a]
            bx, by, bw, bh = cajas[b]
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                assert frozenset({a, b}) in permitidos, (a, b)


def acciones_wdl(objeto):
    """Indexa las acciones de los ámbitos/ramas sin interpretar las expresiones."""
    resultado = {}
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            if clave == "actions" and isinstance(valor, dict):
                resultado.update(valor)
            resultado.update(acciones_wdl(valor))
    elif isinstance(objeto, list):
        for valor in objeto:
            resultado.update(acciones_wdl(valor))
    return resultado


def test_integracion_firma_posicional_powerapps_v2_y_respuesta_wdl():
    from p9.reversion.flujos import construir_solicitar
    d = construir_solicitar()
    trigger = d["triggers"]["manual"]
    assert trigger["kind"] == "PowerAppV2"
    schema = trigger["inputs"]["schema"]
    posiciones = ["text", "number", "text_1", "text_2", "text_3", "text_4"]
    assert list(schema["properties"]) == posiciones
    assert schema["required"] == posiciones
    assert [p["type"] for p in schema["properties"].values()] == ["string", "number", "string", "string", "string", "string"]
    entrada = acciones_wdl(d)["Entrada"]["inputs"]
    for campo, posicion in zip(("operacion", "id", "clave", "etag", "motivo", "uid"), posiciones):
        assert f"triggerBody()?['{posicion}']" in entrada[campo], campo
    campos_ui = set(re.findall(r"varP9RevRespuesta\.(\w+)", ABRIR + ENVIAR))
    salida = d["actions"]["Responder_a_PowerApps"]["inputs"]
    assert set(salida["body"]) == set(salida["schema"]["properties"]) == campos_ui
    assert all(p["type"] == "string" for p in salida["schema"]["properties"].values())


def test_integracion_snapshot_json_tipos_ui_y_identidad_servidor():
    from p9.reversion.flujos import construir_solicitar
    from p9.reversion.validar import decodificar_cuerpo
    acciones = acciones_wdl(construir_solicitar())
    campos_ui = set(re.findall(r"\b(\w+): (?:Text|Value)\(s\.\1\)", ABRIR))
    snapshot = acciones["Snapshot"]["inputs"]
    assert campos_ui <= set(snapshot)
    assert snapshot["ID"].endswith("?['Id']")
    for campo in campos_ui - {"ID"}:
        assert snapshot[campo].endswith(f"?['{campo}']"), campo
    consultar = acciones["Consulta_lista"]["inputs"]["value"]
    assert consultar["resultado"] == "LISTO"
    assert consultar["snapshot_json"] == "@string(outputs('Snapshot'))"
    assert "__metadata" in consultar["etag"]
    identidad = acciones["IDENTIDAD"]["inputs"]
    assert identidad["host"]["operationId"] == "MyProfile_V2"
    creacion = decodificar_cuerpo(acciones["CREAR_SOLICITUD"]["inputs"]["parameters"]["parameters/body"])
    assert "body('IDENTIDAD')?['id']" in creacion["SOLICITANTE_ID"]
    assert "body('IDENTIDAD')?['userPrincipalName']" in creacion["SOLICITANTE_UPN"]
    assert not any("solicitante" in k.lower() or "correo" in k.lower() for k in acciones["Entrada"]["inputs"])


def test_integracion_replay_precede_revalidacion_y_requiere_payload_identico():
    from p9.reversion.flujos import construir_solicitar
    d = construir_solicitar()
    pasos = d["actions"]["TRY"]["actions"]
    assert pasos["Consultar_deposito"]["runAfter"] == {"Reintento_UID_antes_de_ETag": ["Succeeded"]}
    assert pasos["Consultar_deposito"]["expression"] == "@variables('varSeguir')"
    a = acciones_wdl(d)
    assert a["Parar_replay"]["inputs"] == {"name": "varSeguir", "value": False}
    valida = a["Validar_repeticion"]["expression"]
    for campo in ("DEPOSITO_ID", "CLAVE_TRANSACCION", "ETAG_SOLICITUD", "MOTIVO_REVERSION", "SOLICITANTE_ID", "LISTA_DEPOSITO_ID"):
        assert f"['{campo}']" in valida, campo
    assert a["REPLAY_MISMA"]["inputs"]["value"]["resultado"] == "EXISTENTE"
    assert a["REPLAY_AJENA"]["inputs"]["value"]["resultado"] == "ERROR"
    assert a["CREAR_SOLICITUD"]["inputs"]["retryPolicy"]["type"] == "none"


def test_integracion_consulta_activa_muestra_historial_y_plazo_servidor():
    from p9.reversion.flujos import construir_solicitar
    a = acciones_wdl(construir_solicitar())
    activa = a["Respuesta_activa"]["inputs"]["value"]
    assert activa["resultado"] == "PENDIENTE_EXISTENTE"
    assert "SNAPSHOT_JSON" in activa["snapshot_json"]
    assert "ETAG_SOLICITUD" in activa["etag"]
    assert "FECHA_LIMITE" in activa["fecha_limite"]
    assert "VENCIDA" in activa["mensaje"] and "CIERRE PENDIENTE" in activa["mensaje"]
    assert "utcNow()" in activa["mensaje"]
    assert "PENDIENTE_EXISTENTE" in ABRIR
    assert 'Set(varP9RevMensaje, "Solicitud activa · ID "' in ABRIR
    assert "Set(varP9RevAceptada, true)" in ABRIR
    # La plantilla generada debe corresponder al constructor cuando ya existe.
    # Construir siempre se prueba; el empaquetador certifica los cinco JSON/ZIP.
    path = RAIZ / "p9/reversion/flujo_solicitar_definition.json"
    assert path.exists(), "Falta generar la definición de solicitud"
    assert json.loads(path.read_text(encoding="utf-8")) == construir_solicitar()
