"""Pantalla P9_Confirmacion_Masiva (camino directo), botón de Main_Screen y fórmulas manuales: pruebas ESTÁTICAS.

No ejecutan Power Fx ni Studio. Comprueban: YAML válido, nombres únicos, referencias resolubles, paréntesis/comillas balanceados,
coherencia con las salidas del flujo y que el Main_Screen original queda intacto.

FUENTE DE VERDAD: `powerapps/P9_Confirmacion_Masiva.pa.yaml` y `powerapps/Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml` son el EXPORT REAL del tenant
(P9_PRUEBA_MASIVA; copias verbatim de `powerapps/tenant/`). Estas pruebas describen lo que ESTÁ en el tenant, no una reconstrucción.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from proto_masiva.flows import construir as F

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
PA = RAIZ / "powerapps"
sys.path.insert(0, str(PA))
import aplicar_boton  # noqa: E402
import auditar_iferror  # noqa: E402
import derivar_pegar  # noqa: E402

PANTALLA = yaml.safe_load((PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))["Screens"]["P9_Confirmacion_Masiva"]
MANUALES = {"frmArchivoP9", "attXlsxP9"}  # se crearon a mano en Studio; el export real del tenant ya los incluye
TIPOS_USADOS_EN_P9 = {"GroupContainer@1.5.0", "Rectangle@2.3.0", "Label@2.5.1", "Classic/Button@2.2.0", "Gallery@2.15.0",
                      "Form@2.4.4", "TypedDataCard@1.0.7", "Attachments@2.3.0",
                      "Classic/Timer@2.1.0"}   # el Temporizador oculto del seguimiento de la confirmación (control NUEVO de la escala 1999; versión del tipo a confirmar al exportar)
CODIGOS_APP = set(F.CODIGOS) | {"FLUJO_SIN_RESPUESTA"}  # este último lo fabrica la app si el flujo no responde
ESTADOS_UI = {"SIN ARCHIVO", "CARGADO", "PROCESANDO", "CONFIRMANDO", "OK", "OBSERVADO", "PARCIAL", "ERROR"}
# VALIDADO EN TENANT (URL pegada en el navegador → se descarga el XLSX): descarga por UniqueId del archivo real. Si el archivo se borra y se
# vuelve a crear, el UniqueId cambia: actualizar la plantilla con «reemplazar»/nueva versión, no borrando.
URL_DESCARGA = ("https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu/_layouts/15/download.aspx"
                "?UniqueId=84b7ef88-43aa-43d2-8d1c-0f0b682dafbd")


def controles(hijos):
    for h in hijos:
        (nombre, cuerpo), = h.items()
        yield nombre, cuerpo
        yield from controles(cuerpo.get("Children", []))


CONTROLES = dict(controles(PANTALLA["Children"]))
# EXPORT REAL del tenant (solo lectura): las pruebas «del tenant» fijan lo VALIDADO/PUBLICADO; PANTALLA/CONTROLES son el tenant + la integración de la confirmación.
PANTALLA_TENANT = yaml.safe_load((PA / "tenant" / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))["Screens"]["P9_Confirmacion_Masiva"]
TENANT = dict(controles(PANTALLA_TENANT["Children"]))
TENANT_V1_AVISO = dict(controles(yaml.safe_load((PA / "tenant_v1" / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))["Screens"]
                                 ["P9_Confirmacion_Masiva"]["Children"]))["lblAvisoPrototipoP9"]["Properties"]["Text"]


def formulas():
    for nombre, c in CONTROLES.items():
        for prop, valor in c["Properties"].items():
            yield f"{nombre}.{prop}", valor
    yield "pantalla.OnVisible", PANTALLA["Properties"]["OnVisible"]


# El formulario del adjunto (frmArchivoP9 y su tarjeta) es el ÚNICO uso de la lista vehículo P9_MASIVA_PROTO_ADJUNTO: es DataSource del control de adjuntos,
# no lógica de negocio. Las pruebas de «no toca listas» miran el resto de fórmulas.
def formulas_de_logica():
    return [(d, f) for d, f in formulas() if not d.startswith(("frmArchivoP9.", "dcAdjuntosP9."))]


def plano(formula):
    """El export del tenant formatea las fórmulas en varias líneas: se compara sin saltos ni sangrías."""
    f = re.sub(r"\s+", " ", formula).strip()
    f = re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", f))
    return re.sub(r"\s+\}", "}", re.sub(r"\{\s+", "{", f))


def sin_cadenas(formula):
    return re.sub(r'"(?:[^"]|"")*"', '""', formula)


# --------------------------------------------------------------------------- pantalla
def test_yaml_valido_con_nombres_unicos_y_tipos_conocidos():
    nombres = [n for n, _ in controles(PANTALLA["Children"])]
    # 44 controles REALES del tenant: contenedor + 30 controles originales + btnConfirmarMasivamenteP9 + btnVerObservacionesP9 + galObservacionesP9
    # (con Title1, Subtitle1, Separator1, Rectangle1, Title1_1) + frmArchivoP9 (con dcAdjuntosP9, DataCardKey1, attXlsxP9, ErrorMessage1, StarVisible1)
    # + tmrProgresoP9 (Temporizador oculto del seguimiento de la confirmación masiva hasta 1999): 45 en la versión de escala; el export V1 real tiene 44
    assert len(nombres) == len(set(nombres)) == 45 and len(TENANT) == 44 and set(CONTROLES) - set(TENANT) == {"tmrProgresoP9"}
    assert {c["Control"] for c in CONTROLES.values()} <= TIPOS_USADOS_EN_P9


def test_elementos_minimos_pedidos():
    p = lambda n, k="Text": CONTROLES[n]["Properties"][k]  # noqa: E731
    assert p("lblTituloMasivaP9") == '="IMPORTACIÓN MASIVA"'
    assert p("btnDescargarPlantillaP9") == '="DESCARGAR PLANTILLA"' and plano(p("btnDescargarPlantillaP9", "OnSelect")) == f'=Launch("{URL_DESCARGA}")'
    assert "attXlsxP9.Attachments" in p("lblArchivoSeleccionadoP9")
    assert p("btnPrevalidarP9") == '="PREVALIDAR ARCHIVO"'
    assert "attXlsxP9.Attachments" in p("lblEstadoP9") and "varResultadoP9.resultado" in p("lblEstadoP9")
    for rotulo in ("Archivo", "Tabla encontrada", "Filas leídas", "Mensaje"):
        assert any(c["Properties"].get("Text") == f'="{rotulo}"' for c in CONTROLES.values()), rotulo
    assert p("btnVolverMasivaP9") == '="VOLVER"'
    assert p("btnVolverMasivaP9", "OnSelect") == "=Navigate(Main_Screen, ScreenTransition.Fade)"


def test_la_descarga_es_por_uniqueid_y_no_quedan_rutas_ni_variables_antiguas():
    boton = plano(CONTROLES["btnDescargarPlantillaP9"]["Properties"]["OnSelect"])
    assert boton == f'=Launch("{URL_DESCARGA}")' and "Download(" not in boton and "?download=1" not in boton
    for ruta in PA.glob("*"):
        if ruta.suffix in {".yaml", ".md", ".txt", ".py"}:
            texto = ruta.read_text(encoding="utf-8")
            assert "varUrlPlantillaP9" not in texto, ruta.name
            assert "/Documents/P9_MASIVA_PROTO/" not in texto.replace("/Documents/Documents/P9_MASIVA_PROTO/", ""), ruta.name  # la ruta sin anidar nunca existió
            assert "/:x:/g/" not in texto, ruta.name  # el enlace compartido abre Excel, no descarga


def test_el_OnVisible_real_del_tenant():
    assert PANTALLA_TENANT["Properties"]["OnVisible"].splitlines() == [
        "=Set(varProcesandoP9, false);", "Set(varResultadoP9, Blank());", "Set(varMsAppP9, Blank());", "Clear(colPrevalidacionP9);",
        "Set(varVerObservacionesP9, false);", "Set(varConfirmarMasivaVisible, false);", "ResetForm(frmArchivoP9)"]
    # CHECKPOINT: varConfirmarMasivaVisible es del segundo modal DESCARTADO, pero SIGUE en el tenant. Se registra tal cual y se retira en la integración
    # de la confirmación (siguiente commit). Aquí solo se fija DÓNDE aparece, para que no se propague a ningún otro sitio.
    texto = (PA / "tenant" / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    assert texto.count("varConfirmarMasivaVisible") == 2
    assert TENANT["btnConfirmarMasivamenteP9"]["Properties"]["OnSelect"] == "=Set(varConfirmarMasivaVisible, true)"


def test_los_labels_de_copia_temporal_estan_ocultos_pero_siguen_existiendo():
    # DeleteFile devuelve 423 (Excel retiene la copia): el usuario no necesita ver «Copia temporal / NO se pudo eliminar»
    for nombre in ("lblResCopiaTituloP9", "lblResCopiaP9"):
        assert CONTROLES[nombre]["Properties"]["Visible"] == "=false", nombre
    assert len(CONTROLES) == 45


def test_prevalidar_llama_al_flujo_con_el_archivo_y_maneja_el_error_de_llamada():
    f = CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"]
    f_plano = plano(f)
    assert f"{F.NOMBRE_FLUJO}.Run({{name: archivoP9.Name, contentBytes: archivoP9.Value}})" in f_plano
    assert "IfError(" in f and "FLUJO_SIN_RESPUESTA" in f and "FirstError.Message" in f
    assert f.count("Set(varProcesandoP9, true)") == 1 and f.rstrip().endswith("Set(varProcesandoP9, false)")  # nunca queda «procesando» colgado
    assert f_plano.count("DateDiff(inicioP9, Now(), TimeUnit.Milliseconds)") == 2  # tiempo medido en éxito y en fallo
    assert "SubmitForm" not in f and "Patch(" not in f  # no escribe en ninguna lista
    assert f.count("ClearCollect(") == 1 and re.search(r"ClearCollect\(\s*colPrevalidacionP9,", f)  # única colección: local, en memoria de la app
    assert "Collect(" not in f.replace("ClearCollect(", "")


def test_la_app_no_tiene_lotes_ni_historial_ni_escrituras_y_el_UNICO_temporizador_es_el_de_progreso():
    texto = (PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    for prohibido in ("tmrSondeo", "Sondeo", "Refresh(", "LOTES", "LOTE", "varLote", "PENDIENTE", "SubmitForm", "Patch(", "TIPO_CAMBIO", "FECHA_ESTADO"):
        assert prohibido not in texto, prohibido
    # la V1 NO tenía temporizador (export real tenant_v1); la escala 1999 añade exactamente UNO, oculto
    assert "Timer" not in (PA / "tenant_v1" / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    timers = [n for n, c in CONTROLES.items() if "Timer" in c["Control"]]
    assert timers == ["tmrProgresoP9"] and texto.count("OnTimerEnd:") == 1


def test_el_boton_se_bloquea_mientras_procesa_y_sin_archivo_xlsx():
    d = CONTROLES["btnPrevalidarP9"]["Properties"]["DisplayMode"]
    assert "Coalesce(varProcesandoP9, false)" in d and "IsEmpty(attXlsxP9.Attachments)" in d and '".xlsx"' in d


def test_las_salidas_del_flujo_que_usa_la_app_existen_en_la_respuesta_del_flujo():
    usados = set()
    for donde, f in formulas():
        usados |= set(re.findall(r"varResultadoP9\.([a-z_]+)", sin_cadenas(f)))
    # el tenant ya no muestra el desglose técnico (tiempos_ms) ni `mensaje` del flujo: el mensaje de las filas observadas sale de colPrevalidacionP9
    assert usados <= set(F.SALIDAS_RESPUESTA) and (set(F.SALIDAS) - {"tiempos_ms", "mensaje"}) <= usados and "detalle_json" in usados
    registro = re.search(r"Set\(\s*varResultadoP9,\s*\{(.*?)\}\s*\)", CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"], re.S)  # el último: el de error
    assert set(re.findall(r"([a-z_]+):", registro[1])) == set(F.SALIDAS_RESPUESTA)  # el resultado de error fabricado por la app tiene la misma forma
    assert re.search(r'detalle_json: "\[\]"', registro[1])  # y un detalle vacío válido, para que ParseJSON no falle


def test_estados_y_codigos_de_la_app_son_los_del_flujo():
    estados, codigos = set(), set()
    for _, f in formulas():
        estados |= set(re.findall(r'"(SIN ARCHIVO|CARGADO|PROCESANDO|CONFIRMANDO|OK|OBSERVADO|PARCIAL|ERROR)"', f))
        codigos |= set(re.findall(r'codigo: "([A-Z_]+)"', f))
    assert estados <= ESTADOS_UI and estados == ESTADOS_UI
    assert codigos <= CODIGOS_APP


def test_las_referencias_a_controles_se_resuelven():
    conocidos = set(CONTROLES) | MANUALES
    for donde, f in formulas():
        for ref in re.findall(r"\b((?:btn|lbl|rect|cnt|frm|att|tmr|txt)[A-Za-z0-9_]*P9)\b", sin_cadenas(f)):
            assert ref in conocidos, (donde, ref)
    asignadas = {r for _, f in formulas() for r in re.findall(r"\b(frmArchivoP9|attXlsxP9)\b", f)}
    assert asignadas == MANUALES


def test_la_pantalla_no_usa_Depositos_Activos_ni_tipo_de_cambio_en_formulas():
    for donde, f in formulas_de_logica():
        limpio = sin_cadenas(f)
        assert "Depositos_Activos" not in limpio and "Depositos_Reversiones" not in limpio, donde
        assert "TIPO_CAMBIO" not in f, donde
    assert not any(re.search(r"\bP9_MASIVA_PROTO_(ADJUNTO|LOTES)\b", sin_cadenas(f)) for _, f in formulas_de_logica())  # el vehículo no se lee ni se escribe


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
    assert [list(x)[0] for x in pegar] == ["cntImportacionMasivaP9", "frmArchivoP9"]  # el export real lleva el formulario como hermano del contenedor


# --------------------------------------------------------------------------- fórmula manual de INSTRUCCIONES_PEGADO.md
def bloques_md():
    texto = (PA / "INSTRUCCIONES_PEGADO.md").read_text(encoding="utf-8")
    return re.findall(r"```\n(.*?)```", texto, re.S)


def test_la_unica_formula_manual_es_el_OnVisible_y_coincide_con_la_del_yaml():
    bloques = bloques_md()
    assert len(bloques) == 1  # ya no hay OnSuccess ni OnTimerEnd
    manual = [l.strip() for l in bloques[0].strip().splitlines()]
    yaml_ = [l.strip() for l in PANTALLA_TENANT["Properties"]["OnVisible"].lstrip("=").splitlines()]
    assert manual == yaml_
    limpio = sin_cadenas(bloques[0])
    assert limpio.count("(") == limpio.count(")")


def test_las_instrucciones_no_mencionan_infraestructura_eliminada_como_requisito():
    for ruta in (PA / "INSTRUCCIONES_PEGADO.md", RAIZ / "flows" / "INSTRUCCIONES_FLUJO.md", RAIZ / "sharepoint" / "INSTRUCCIONES_VEHICULO.md"):
        texto = ruta.read_text(encoding="utf-8")
        assert "OnTimerEnd" not in texto and "tmrSondeoP9" not in texto and "Start = " not in texto, ruta.name
    assert not (RAIZ / "sharepoint" / "esquema_P9_MASIVA_PROTO_LOTES.json").exists()
    assert not (RAIZ / "RUNBOOK.md").exists() and not (RAIZ / "REGISTRO_RESULTADOS.md").exists()


# --------------------------------------------------------------------------- botón en Main_Screen
ORIGINAL = REPO / "p9/reversion/powerapps/Main_Screen.yaml"
CON_BOTON = PA / "Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml"
SHA_ORIGINAL_LF = "99486d668690e425568ca18c5d6d3ff6d953fe4529e0ca0b48b0d99fd98e755a"  # el que fija test_32


def test_el_original_de_Main_Screen_sigue_intacto():
    assert hashlib.sha256(ORIGINAL.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == SHA_ORIGINAL_LF
    assert subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "p9/reversion/powerapps/Main_Screen.yaml"], cwd=REPO).returncode == 0


def test_Main_Screen_del_tenant_es_el_original_mas_el_boton_y_los_ajustes_reales_registrados():
    """Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml es el EXPORT REAL del tenant (copia verbatim de tenant/Main_Screen.pa.yaml).

    Frente al original de producción difiere SOLO por: el botón (btnImportacionMasivaP9) y 3 controles ajustados a mano en Studio.
    """
    assert CON_BOTON.read_bytes() == (PA / "tenant" / "Main_Screen.pa.yaml").read_bytes()
    texto = CON_BOTON.read_text(encoding="utf-8")
    assert texto.count(aplicar_boton.BLOQUE) == 1  # el bloque real del botón está una sola vez
    real = dict(controles(yaml.safe_load(texto)["Screens"]["Main_Screen"]["Children"]))
    prod = dict(controles(yaml.safe_load(ORIGINAL.read_text(encoding="utf-8"))["Screens"]["Main_Screen"]["Children"]))
    assert set(real) - set(prod) == {"btnImportacionMasivaP9"} and set(prod) <= set(real)
    # Ajustes reales (no se «corrigen» desde Git: el tenant prevalece): X de ACTUALIZAR, cmbCuentaP9_1 muestra solo el número y se oculta con el panel
    assert real["btnActualizarP9_1"]["Properties"]["X"] == "=1019" and prod["btnActualizarP9_1"]["Properties"]["X"] == "=1010"
    cuenta = real["cmbCuentaP9_1"]["Properties"]
    assert cuenta["Visible"] == "=Not(Coalesce(mostrarConfirmacion, false))" and "Visible" not in prod["cmbCuentaP9_1"]["Properties"]
    assert cuenta["DisplayFields"] == '=["Cuenta"]' and prod["cmbCuentaP9_1"]["Properties"]["DisplayFields"] == '=["Label"]'
    assert real["btnImportacionMasivaP9"]["Properties"]["Visible"] == "=Not(Coalesce(mostrarConfirmacion, false))"


def test_el_boton_es_hijo_de_cntControlDepositosP9_y_navega_a_la_pantalla_nueva():
    doc = yaml.safe_load(CON_BOTON.read_text(encoding="utf-8"))
    raiz = doc["Screens"]["Main_Screen"]["Children"]
    contenedor = next(list(x.values())[0] for x in raiz if "cntControlDepositosP9" in x)
    nombres = [list(x)[0] for x in contenedor["Children"]]
    assert nombres[-1] == "btnImportacionMasivaP9"  # en el tenant quedó como último hijo del contenedor
    boton = contenedor["Children"][-1]["btnImportacionMasivaP9"]
    assert plano(boton["Properties"]["OnSelect"]) == "=Navigate(P9_Confirmacion_Masiva, ScreenTransition.Fade)"
    assert boton["Properties"]["Text"] == '="IMPORTACION MASIVA"'  # sin tilde: así está rotulado en el tenant
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


def test_la_lista_vehiculo_esta_documentada_solo_como_vehiculo_tecnico_y_no_participa_en_la_logica():
    for ruta in (RAIZ / "sharepoint" / "INSTRUCCIONES_VEHICULO.md", RAIZ / "RESULTADO_PROTOTIPO.md"):
        texto = " ".join(ruta.read_text(encoding="utf-8").split())
        assert "vehículo técnico" in texto, ruta.name
        for no_guarda in ("lotes", "estados", "historial", "trazabilidad", "archivos permanentes"):
            assert no_guarda in texto, (ruta.name, no_guarda)
        assert "no es parte de la lógica de negocio" in texto.lower(), ruta.name
    assert "P9_MASIVA_PROTO_ADJUNTO" not in json.dumps(F.construir_definicion())  # el flujo no la referencia en absoluto
    for donde, f in formulas_de_logica():
        assert not re.search(r"P9_MASIVA_PROTO_ADJUNTO", sin_cadenas(f)), donde  # ninguna fórmula la lee ni la escribe
    # el único uso de la lista es el DataSource del formulario del adjunto (frmArchivoP9), descrito en las instrucciones
    assert CONTROLES["frmArchivoP9"]["Properties"]["DataSource"] == "=P9_MASIVA_PROTO_ADJUNTO"
    assert "`DataSource` = `P9_MASIVA_PROTO_ADJUNTO`" in (PA / "INSTRUCCIONES_PEGADO.md").read_text(encoding="utf-8")



# --------------------------------------------------------------------------- prevalidación real: colección colPrevalidacionP9
ESQUEMA = json.loads((Path(F.__file__).parent / "esquema_detalle_json.json").read_text(encoding="utf-8"))["items"]["properties"]


def test_la_coleccion_se_construye_con_ParseJSON_y_conversion_explicita_de_cada_columna_del_esquema():
    f = CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"]
    assert "ParseJSON(varResultadoP9.detalle_json)" in f and "ClearCollect(" in f
    columnas = re.findall(r"^\s+(\w+): (Value|Text)\(ThisRecord\.Value\.(\w+)\)", f, re.M)
    assert [c for c, _, _ in columnas] == [c for _, _, c in columnas] == list(ESQUEMA) == list(F.PV.DETALLE_CAMPOS)
    for campo, conversor, _ in columnas:
        tipos = ESQUEMA[campo]["type"]
        tipos = tipos if isinstance(tipos, list) else [tipos]
        esperado = "Value" if set(tipos) & {"integer", "number"} else "Text"
        assert conversor == esperado, campo  # nada se asume tipado: cada columna se convierte con Text() o Value()


def test_si_el_detalle_no_se_puede_leer_se_avisa_sin_fingir_que_el_flujo_no_respondio():
    f = CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"]
    assert f.index("ClearCollect(") < f.index("Notify(") < f.index("FLUJO_SIN_RESPUESTA")
    interno = f[f.index("ClearCollect("):f.index("FLUJO_SIN_RESPUESTA")]
    assert "Notify(" in interno and "NotificationType.Warning" in interno and "FLUJO_SIN_RESPUESTA" not in interno


def test_la_pantalla_ya_no_dice_que_no_consulta_Depositos_Activos_ni_usa_estados_antiguos():
    texto = (PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    assert "COMPLETADO" not in texto.replace("CONFIRMACIÓN COMPLETADA", "") and "no se consulta" not in texto and "se borra al terminar" not in texto
    # export del tenant: el aviso era el de la prevalidación; la integración lo cambia
    assert TENANT["lblAvisoPrototipoP9"]["Properties"]["Text"] == '="Prevalidación de SOLO LECTURA"'
    assert "No confirma ningún depósito" in TENANT["lblSubtituloMasivaP9"]["Properties"]["Text"]
    aviso = CONTROLES["lblAvisoPrototipoP9"]["Properties"]["Text"]
    # V1 (export real tenant_v1): sin el prefijo «PROTOTIPO · CONFIRMAR MASIVAMENTE»; la escala 1999 añade «hasta 1999 filas con un clic»
    assert TENANT_V1_AVISO == '="Relee cada depósito antes de escribir y solo confirma lo que sigue válido · sin lotes ni historial."'
    assert aviso == '="Relee cada depósito antes de escribir y solo confirma lo que sigue válido · hasta 1999 filas con un clic · sin lotes ni historial."'
    assert "No confirma" not in CONTROLES["lblSubtituloMasivaP9"]["Properties"]["Text"]
    for estado in ("OK", "OBSERVADO", "PARCIAL", "ERROR", "PROCESANDO", "CONFIRMANDO", "CARGADO"):
        assert f'"{estado}"' in CONTROLES["lblEstadoP9"]["Properties"]["Fill"], estado



# --------------------------------------------------------------------------- UX REAL del tenant (validada visualmente por Gabriel)
def test_ux_de_observaciones_real_del_tenant():
    p = lambda n, k: TENANT[n]["Properties"][k]  # noqa: E731
    boton = plano(p("btnVerObservacionesP9", "Text"))
    assert boton.startswith('=If(Coalesce(varVerObservacionesP9, false), "OCULTAR OBSERVACIONES", "VER OBSERVACIONES (" &')
    assert 'CountRows(Filter(colPrevalidacionP9, resultado <> "VALIDO"))' in boton
    assert plano(p("btnVerObservacionesP9", "OnSelect")) == "=Set(varVerObservacionesP9, !Coalesce(varVerObservacionesP9, false))"
    assert plano(p("btnVerObservacionesP9", "Visible")) == '=CountRows(Filter(colPrevalidacionP9, resultado <> "VALIDO")) > 0'
    # galería: SOLO filas observadas, fondo blanco sólido (no se transparenta el resumen), visible solo con el botón activado
    assert plano(p("galObservacionesP9", "Items")) == '=Filter(colPrevalidacionP9, resultado <> "VALIDO")'
    assert p("galObservacionesP9", "Fill") == p("galObservacionesP9", "TemplateFill") == "=RGBA(255, 255, 255, 1)"
    assert p("galObservacionesP9", "Visible") == "=varVerObservacionesP9"
    # cada elemento: título en negrita y mensaje en etiquetas SEPARADAS (nombres reales de Studio: Title1 y Title1_1)
    assert p("Title1", "FontWeight") == "=FontWeight.Bold" and "FontWeight" not in TENANT["Title1_1"]["Properties"]
    titulo = plano(p("Title1", "Text"))
    assert titulo.startswith('="Fila " & Text(ThisItem.fila_excel) & " · " & Switch(ThisItem.resultado,')
    for rotulo in ("DUPLICADO EN EL EXCEL", "FALTAN DATOS", "DEPÓSITO NO DISPONIBLE", "DEPÓSITO NO ENCONTRADO"):
        assert f'"{rotulo}"' in titulo, rotulo
    assert p("Title1_1", "Text").strip() == "=ThisItem.mensaje"
    # al ver observaciones se oculta el mensaje del resumen que se transparentaba por detrás
    assert p("lblResMensajeP9", "Visible") == "=!varVerObservacionesP9"


def test_tiempo_de_procesamiento_humanizado_sin_desglose_tecnico():
    assert TENANT["lblResTiempoTituloP9"]["Properties"]["Text"] == '="Tiempo de Procesamiento"'
    tiempo = plano(TENANT["lblResTiempoP9"]["Properties"]["Text"])
    assert '" segundos"' in tiempo and "varMsAppP9 / 1000" in tiempo
    assert "flujo:" not in tiempo and "crear=" not in tiempo and "excel=" not in tiempo and "tiempos_ms" not in tiempo


def test_btnConfirmarMasivamenteP9_estado_validado_en_el_tenant_antes_de_integrar():
    """CHECKPOINT: tal como estaba en el export del tenant (aún sin llamar al flujo). La integración cambia SOLO OnSelect y DisplayMode (ver test_08)."""
    b = TENANT["btnConfirmarMasivamenteP9"]["Properties"]
    assert plano(b["Text"]) == '="CONFIRMAR MASIVAMENTE (" & CountRows(Filter(colPrevalidacionP9, resultado = "VALIDO")) & ")"'
    assert plano(b["DisplayMode"]) == ('=If(!varProcesandoP9 && CountRows(Filter(colPrevalidacionP9, resultado = "VALIDO")) > 0, '
                                       "DisplayMode.Edit, DisplayMode.Disabled)")
    assert b["OnSelect"] == "=Set(varConfirmarMasivaVisible, true)" and "P9_MASIVA_PROTO_CONFIRMAR" not in json.dumps(TENANT)


# --------------------------------------------------------------------------- IfError: compatibilidad de tipos (Studio rechaza tabla vs booleano)
def test_el_IfError_de_la_prevalidacion_del_tenant_devuelve_booleanos_en_todas_las_ramas():
    f = CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"]
    llamadas = auditar_iferror.llamadas_iferror(f)
    assert len(llamadas) == 2 and all(len(a) == 2 for a in llamadas)
    assert [auditar_iferror.ultima_sentencia(a) for ll in llamadas for a in ll] == ["true", "false", "true", "false"]
    assert auditar_iferror.incompatibilidades(f) == []


def test_ninguna_formula_del_yaml_mezcla_tabla_y_booleano_en_un_IfError():
    # regla conservadora aplicada a la pantalla MASIVA (Main_Screen de producción ya fue aceptada por Studio y no se audita aquí)
    assert auditar_iferror.auditar(PA / "P9_Confirmacion_Masiva.pa.yaml") == []
    assert auditar_iferror.auditar(PA / "tenant" / "P9_Confirmacion_Masiva.pa.yaml") == []


def test_el_auditor_de_IfError_detecta_el_patron_que_Studio_rechazo():
    malo = 'IfError(ClearCollect(c, x), Notify("e", NotificationType.Warning))'
    assert auditar_iferror.incompatibilidades(malo) == [(0, 0, "ClearCollect(c, x)"), (0, 1, 'Notify("e", NotificationType.Warning)')]
    assert auditar_iferror.incompatibilidades('IfError(ClearCollect(c, x); true, Notify("a, b", NotificationType.Warning); false)') == []
    assert auditar_iferror.incompatibilidades('IfError(Set(v, 1); Set(w, 2), Set(v, 3))') != []  # Set también devuelve algo no booleano
    assert auditar_iferror.incompatibilidades('If(x, 1, 2)') == []  # sin IfError no hay nada que auditar
