"""Pantalla P9_Confirmacion_Masiva (camino directo), botón de Main_Screen y fórmulas manuales: pruebas ESTÁTICAS.

No ejecutan Power Fx ni Studio. Comprueban: YAML válido, nombres únicos, referencias resolubles, paréntesis/comillas balanceados,
coherencia con las salidas del flujo y que el Main_Screen original queda intacto.
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
import derivar_pegar  # noqa: E402

PANTALLA = yaml.safe_load((PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))["Screens"]["P9_Confirmacion_Masiva"]
MANUALES = {"frmArchivoP9", "attXlsxP9"}  # los únicos controles que se crean a mano en Studio
TIPOS_USADOS_EN_P9 = {"GroupContainer@1.5.0", "Rectangle@2.3.0", "Label@2.5.1", "Classic/Button@2.2.0"}
CODIGOS_APP = set(F.CODIGOS) | {"FLUJO_SIN_RESPUESTA"}  # este último lo fabrica la app si el flujo no responde
ESTADOS_UI = {"SIN ARCHIVO", "CARGADO", "PROCESANDO", "OK", "OBSERVADO", "ERROR"}
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


def formulas():
    for nombre, c in CONTROLES.items():
        for prop, valor in c["Properties"].items():
            yield f"{nombre}.{prop}", valor
    yield "pantalla.OnVisible", PANTALLA["Properties"]["OnVisible"]


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
    assert p("btnDescargarPlantillaP9") == '="DESCARGAR PLANTILLA"' and p("btnDescargarPlantillaP9", "OnSelect") == f'=Launch("{URL_DESCARGA}")'
    assert "attXlsxP9.Attachments" in p("lblArchivoSeleccionadoP9")
    assert p("btnPrevalidarP9") == '="PREVALIDAR ARCHIVO"'
    assert "attXlsxP9.Attachments" in p("lblEstadoP9") and "varResultadoP9.resultado" in p("lblEstadoP9")
    for rotulo in ("Archivo", "Tabla encontrada", "Filas leídas", "Mensaje"):
        assert any(c["Properties"].get("Text") == f'="{rotulo}"' for c in CONTROLES.values()), rotulo
    assert p("btnVolverMasivaP9") == '="VOLVER"'
    assert p("btnVolverMasivaP9", "OnSelect") == "=Navigate(Main_Screen, ScreenTransition.Fade)"


def test_la_descarga_es_por_uniqueid_y_no_quedan_rutas_ni_variables_antiguas():
    boton = CONTROLES["btnDescargarPlantillaP9"]["Properties"]["OnSelect"]
    assert boton == f'=Launch("{URL_DESCARGA}")' and "Download(" not in boton and "?download=1" not in boton
    for ruta in PA.glob("*"):
        if ruta.suffix in {".yaml", ".md", ".txt", ".py"}:
            texto = ruta.read_text(encoding="utf-8")
            assert "varUrlPlantillaP9" not in texto, ruta.name
            assert "/Documents/P9_MASIVA_PROTO/" not in texto.replace("/Documents/Documents/P9_MASIVA_PROTO/", ""), ruta.name  # la ruta sin anidar nunca existió
            assert "/:x:/g/" not in texto, ruta.name  # el enlace compartido abre Excel, no descarga


def test_el_OnVisible_final_no_tiene_variable_de_plantilla():
    assert PANTALLA["Properties"]["OnVisible"].splitlines() == [
        "=Set(varProcesandoP9, false);", "Set(varResultadoP9, Blank());", "Set(varMsAppP9, Blank());", "ResetForm(frmArchivoP9)"]


def test_los_labels_de_copia_temporal_estan_ocultos_pero_siguen_existiendo():
    # DeleteFile devuelve 423 (Excel retiene la copia): el usuario no necesita ver «Copia temporal / NO se pudo eliminar»
    for nombre in ("lblResCopiaTituloP9", "lblResCopiaP9"):
        assert CONTROLES[nombre]["Properties"]["Visible"] == "=false", nombre
    assert len(CONTROLES) == 30


def test_prevalidar_llama_al_flujo_con_el_archivo_y_maneja_el_error_de_llamada():
    f = CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"]
    assert f"{F.NOMBRE_FLUJO}.Run({{name: archivoP9.Name, contentBytes: archivoP9.Value}})" in f
    assert "IfError(" in f and "FLUJO_SIN_RESPUESTA" in f and "FirstError.Message" in f
    assert f.count("Set(varProcesandoP9, true)") == 1 and f.rstrip().endswith("Set(varProcesandoP9, false)")  # nunca queda «procesando» colgado
    assert f.count("DateDiff(inicioP9, Now(), TimeUnit.Milliseconds)") == 2  # tiempo medido en éxito y en fallo
    assert "SubmitForm" not in f and "Patch(" not in f  # no escribe en ninguna lista
    assert f.count("ClearCollect(") == 1 and re.search(r"ClearCollect\(\s*colPrevalidacionP9,", f)  # única colección: local, en memoria de la app
    assert "Collect(" not in f.replace("ClearCollect(", "")


def test_la_app_es_directa_no_hay_temporizador_sondeo_lotes_ni_estados_persistentes():
    texto = (PA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    for prohibido in ("Timer", "tmrSondeo", "Sondeo", "OnTimerEnd", "Refresh(", "LOTES", "LOTE", "varLote", "PENDIENTE", "SubmitForm",
                      "Patch(", "TIPO_CAMBIO", "FECHA_ESTADO"):
        assert prohibido not in texto, prohibido


def test_el_boton_se_bloquea_mientras_procesa_y_sin_archivo_xlsx():
    d = CONTROLES["btnPrevalidarP9"]["Properties"]["DisplayMode"]
    assert "Coalesce(varProcesandoP9, false)" in d and "IsEmpty(attXlsxP9.Attachments)" in d and '".xlsx"' in d


def test_las_salidas_del_flujo_que_usa_la_app_existen_en_la_respuesta_del_flujo():
    usados = set()
    for donde, f in formulas():
        usados |= set(re.findall(r"varResultadoP9\.([a-z_]+)", sin_cadenas(f)))
    assert usados <= set(F.SALIDAS_RESPUESTA) and set(F.SALIDAS) <= usados and "detalle_json" in usados  # las 8 de siempre + las nuevas
    registro = re.search(r"Set\(\s*varResultadoP9,\s*\{(.*?)\}\s*\)", CONTROLES["btnPrevalidarP9"]["Properties"]["OnSelect"], re.S)
    assert set(re.findall(r"([a-z_]+):", registro[1])) == set(F.SALIDAS_RESPUESTA)  # el resultado de error fabricado por la app tiene la misma forma
    assert re.search(r'detalle_json: "\[\]"', registro[1])  # y un detalle vacío válido, para que ParseJSON no falle


def test_estados_y_codigos_de_la_app_son_los_del_flujo():
    estados, codigos = set(), set()
    for _, f in formulas():
        estados |= set(re.findall(r'"(SIN ARCHIVO|CARGADO|PROCESANDO|OK|OBSERVADO|ERROR)"', f))
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
    for donde, f in formulas():
        limpio = sin_cadenas(f)
        assert "Depositos_Activos" not in limpio and "Depositos_Reversiones" not in limpio, donde
        assert "TIPO_CAMBIO" not in f, donde
    assert not any(re.search(r"\bP9_MASIVA_PROTO_(ADJUNTO|LOTES)\b", sin_cadenas(f)) for _, f in formulas())  # el vehículo no se lee ni se escribe


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


# --------------------------------------------------------------------------- fórmula manual de INSTRUCCIONES_PEGADO.md
def bloques_md():
    texto = (PA / "INSTRUCCIONES_PEGADO.md").read_text(encoding="utf-8")
    return re.findall(r"```\n(.*?)```", texto, re.S)


def test_la_unica_formula_manual_es_el_OnVisible_y_coincide_con_la_del_yaml():
    bloques = bloques_md()
    assert len(bloques) == 1  # ya no hay OnSuccess ni OnTimerEnd
    manual = [l.strip() for l in bloques[0].strip().splitlines()]
    yaml_ = [l.strip() for l in PANTALLA["Properties"]["OnVisible"].lstrip("=").splitlines()]
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


def test_la_lista_vehiculo_esta_documentada_solo_como_vehiculo_tecnico_y_no_participa_en_la_logica():
    for ruta in (RAIZ / "sharepoint" / "INSTRUCCIONES_VEHICULO.md", RAIZ / "RESULTADO_PROTOTIPO.md"):
        texto = " ".join(ruta.read_text(encoding="utf-8").split())
        assert "vehículo técnico" in texto, ruta.name
        for no_guarda in ("lotes", "estados", "historial", "trazabilidad", "archivos permanentes"):
            assert no_guarda in texto, (ruta.name, no_guarda)
        assert "no es parte de la lógica de negocio" in texto.lower(), ruta.name
    assert "P9_MASIVA_PROTO_ADJUNTO" not in json.dumps(F.construir_definicion())  # el flujo no la referencia en absoluto
    for donde, f in formulas():
        assert not re.search(r"P9_MASIVA_PROTO_ADJUNTO", sin_cadenas(f)), donde  # ninguna fórmula la lee ni la escribe
    # el único uso de la lista es el DataSource del formulario manual, descrito en las instrucciones
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
    assert "COMPLETADO" not in texto and "no se consulta" not in texto and "se borra al terminar" not in texto
    aviso = CONTROLES["lblAvisoPrototipoP9"]["Properties"]["Text"]
    assert "SOLO LECTURA" in aviso and "no lo modifica" in aviso and "no confirma" in aviso
    assert "OK" in CONTROLES["lblEstadoP9"]["Properties"]["Fill"] and "OBSERVADO" in CONTROLES["lblEstadoP9"]["Properties"]["Fill"]
