"""Escenarios sintéticos de P9_MASIVA_PROTO_PREVALIDAR contra el tenant SIMULADO.

[VALIDADO LOCALMENTE] significa: el flujo generado, interpretado por el intérprete WDL local, produce este resultado con un
Excel/SharePoint falsos. NO prueba el runtime Microsoft: ver RESULTADO_PROTOTIPO.md («REQUIERE VALIDACIÓN TENANT»).
"""
import json
from pathlib import Path

import pytest

from proto_masiva.flows import construir as F
from simulador import AHORA, TenantSimulado, configurar, procesar

RAIZ = Path(__file__).resolve().parents[1]
XLSX = RAIZ / "xlsx"
ESQUEMA = json.loads((RAIZ / "sharepoint/esquema_P9_MASIVA_PROTO_LOTES.json").read_text(encoding="utf-8"))
ESQUEMA = {**ESQUEMA, "columnas": ESQUEMA["columnas"] + [{"nombre_tecnico": "Title"}]}


def tenant(archivo, **kw):
    t = TenantSimulado(ESQUEMA)
    adjunto = (XLSX / archivo).read_bytes() if archivo else None
    return t, t.crear_lote(adjunto, nombre=archivo or "", **kw)["ID"]


def final(t, lote):
    return t.lotes[lote]


# ------------------------------------------------------------------ A-E (los cinco pedidos)
def test_A_archivo_correcto_3_filas():  # Ejemplo_Confirmacion_Masiva_P9.xlsx (3 filas ficticias)
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    r = procesar(t, lote)
    f = final(t, lote)
    assert r.estado_final == "Succeeded"
    assert (f["ESTADO"], f["CODIGO_RESULTADO"], f["TABLA_ENCONTRADA"], f["FILAS_LEIDAS"]) == ("COMPLETADO", "OK", "SI", 3)
    assert f["MENSAJE"] == "Archivo leído correctamente"
    assert f["ARCHIVO_NOMBRE"] == "Ejemplo_Confirmacion_Masiva_P9.xlsx"


def test_A2_otro_archivo_de_3_filas():
    t, lote = tenant("01_OK_3filas.xlsx")
    procesar(t, lote)
    assert (final(t, lote)["ESTADO"], final(t, lote)["FILAS_LEIDAS"]) == ("COMPLETADO", 3)


@pytest.mark.parametrize("archivo", ["Plantilla_Confirmacion_Masiva_P9.xlsx", "02a_TABLA_VACIA_1fila_en_blanco.xlsx",
                                      "02b_TABLA_SOLO_ENCABEZADO.xlsx"])
def test_B_tabla_vacia_es_ERROR_ARCHIVO_VACIO_controlado(archivo):  # incluye la Plantilla de producción, vacía
    """Diseño: una importación sin filas NO es COMPLETADO (no hay nada que confirmar). Resultado controlado, sin fallo del flujo."""
    t, lote = tenant(archivo)
    r = procesar(t, lote)
    f = final(t, lote)
    assert r.estado_final == "Succeeded"
    assert (f["ESTADO"], f["CODIGO_RESULTADO"], f["TABLA_ENCONTRADA"], f["FILAS_LEIDAS"]) == ("ERROR", "ARCHIVO_VACIO", "SI", 0)


def test_C_sin_tabla():
    t, lote = tenant("03_SIN_TABLA.xlsx")
    r = procesar(t, lote)
    f = final(t, lote)
    assert r.estado_final == "Succeeded"  # el fallo de Excel fue capturado y clasificado
    assert (f["ESTADO"], f["CODIGO_RESULTADO"], f["TABLA_ENCONTRADA"], f["FILAS_LEIDAS"]) == ("ERROR", "TABLA_NO_ENCONTRADA", "NO", 0)


def test_D_encabezado_cambiado():
    t, lote = tenant("05_ENCABEZADO_CAMBIADO.xlsx")
    procesar(t, lote)
    f = final(t, lote)
    assert (f["ESTADO"], f["CODIGO_RESULTADO"], f["TABLA_ENCONTRADA"]) == ("ERROR", "ESTRUCTURA_INVALIDA", "SI")
    assert "CUENTA_BANCARIA" in f["MENSAJE"] and "plantilla oficial" in f["MENSAJE"]
    assert f["FILAS_LEIDAS"] == 0


def test_E_tabla_con_nombre_distinto():
    t, lote = tenant("04_TABLA_NOMBRE_DISTINTO.xlsx")
    procesar(t, lote)
    f = final(t, lote)
    assert (f["ESTADO"], f["CODIGO_RESULTADO"], f["TABLA_ENCONTRADA"]) == ("ERROR", "TABLA_NO_ENCONTRADA", "NO")


# ------------------------------------------------------------------ máquina de estados y seguridad del disparo
def test_el_flujo_marca_PROCESANDO_primero_y_termina_en_estado_terminal_una_sola_vez():
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    procesar(t, lote)
    estados = [c["ESTADO"] for _, i, c in t.escrituras if i == lote and "ESTADO" in c]
    assert estados == ["PROCESANDO", "COMPLETADO"]
    assert final(t, lote)["FECHA_ESTADO"] == AHORA


def test_nunca_escribe_PENDIENTE_ni_se_redispara_con_sus_propias_escrituras():
    t, lote = tenant("03_SIN_TABLA.xlsx")
    procesar(t, lote)
    for _, _, cuerpo in t.escrituras:
        assert cuerpo["ESTADO"] in ("PROCESANDO", "COMPLETADO", "ERROR")
    d = F.construir_definicion()
    from simulador import EnsayoMasivo
    assert not EnsayoMasivo(d, t, t.lotes[lote]).dispara()  # ya terminal: la condición del disparador no se cumple


@pytest.mark.parametrize("estado", ["CARGADO", "PROCESANDO", "COMPLETADO", "ERROR", ""])
def test_solo_se_dispara_con_PENDIENTE(estado):
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx", ESTADO=estado)
    r = procesar(t, lote)
    assert r.estado_final == "NoDisparado" and not t.escrituras and not t.llamadas


def test_reintento_tras_ERROR_vuelve_a_funcionar_sin_chocar_con_el_archivo_anterior():
    t, lote = tenant("03_SIN_TABLA.xlsx")
    procesar(t, lote)
    assert final(t, lote)["ESTADO"] == "ERROR"
    t.adjuntos[lote] = [("corregido.xlsx", (XLSX / "Ejemplo_Confirmacion_Masiva_P9.xlsx").read_bytes())]
    t.lotes[lote]["ESTADO"] = "PENDIENTE"  # lo que hace el botón de la app
    import simulador
    simulador.AHORA  # el nombre de la copia incluye la fecha; fuerza otra copia con otro instante
    d = configurar(F.construir_definicion())
    d["actions"]["TRY"]["actions"]["Hay_adjunto"]["actions"]["Es_xlsx"]["actions"]["Nombre_copia"]["inputs"] = \
        "@concat(outputs('Lote')?['uid'],'_2.xlsx')"
    procesar(t, lote, d)
    assert (final(t, lote)["ESTADO"], final(t, lote)["FILAS_LEIDAS"]) == ("COMPLETADO", 3)
    assert len(t.biblioteca) == 2


# ------------------------------------------------------------------ entradas anómalas
def test_sin_adjunto():
    t, lote = tenant(None)
    procesar(t, lote)
    f = final(t, lote)
    assert (f["ESTADO"], f["CODIGO_RESULTADO"]) == ("ERROR", "SIN_ADJUNTO")
    assert not t.biblioteca


def test_adjunto_que_no_es_xlsx():
    t = TenantSimulado(ESQUEMA)
    lote = t.crear_lote(b"a,b\n1,2\n", nombre="datos.csv")["ID"]
    procesar(t, lote)
    assert (final(t, lote)["ESTADO"], final(t, lote)["CODIGO_RESULTADO"]) == ("ERROR", "NO_ES_XLSX")
    assert not t.biblioteca


def test_xlsx_corrupto_no_se_confunde_con_tabla_ausente():
    t = TenantSimulado(ESQUEMA)
    lote = t.crear_lote(b"esto no es un zip", nombre="roto.xlsx")["ID"]
    procesar(t, lote)
    f = final(t, lote)
    assert (f["ESTADO"], f["CODIGO_RESULTADO"]) == ("ERROR", "ERROR_LECTURA_EXCEL")
    assert "HTTP 400" in f["MENSAJE"]


# ------------------------------------------------------------------ fallos de infraestructura (clasificación)
@pytest.mark.parametrize("clave,http,codigo", [("adjuntos", 500, "ERROR_ADJUNTO"), ("contenido", 500, "ERROR_ADJUNTO"),
                                               ("crear", 409, "ERROR_COPIA_ARCHIVO"), ("crear", 403, "ERROR_COPIA_ARCHIVO"),
                                               ("excel", 423, "ARCHIVO_BLOQUEADO"), ("excel", 500, "ERROR_LECTURA_EXCEL"),
                                               ("excel", 404, "TABLA_NO_ENCONTRADA")])
def test_fallos_de_conector_se_clasifican(clave, http, codigo):
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    t.fallos[clave] = ("Failed", http)
    procesar(t, lote)
    f = final(t, lote)
    assert (f["ESTADO"], f["CODIGO_RESULTADO"]) == ("ERROR", codigo)
    assert f["FILAS_LEIDAS"] == 0


def test_archivo_abierto_bloqueado_423_y_luego_liberado():
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    t.bloqueados.add(f"{t.lotes[lote]['LOTE_UID']}_20261005120000.xlsx")
    procesar(t, lote)
    assert final(t, lote)["CODIGO_RESULTADO"] == "ARCHIVO_BLOQUEADO"


def test_excel_sin_configurar_no_se_presenta_como_tabla_inexistente_salvo_404():
    """Con el marcador <CONFIGURAR_...> sin sustituir, el conector real fallaría; un 500 se reporta como lectura, no como tabla."""
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    t.fallos["excel"] = ("Failed", 500)
    procesar(t, lote, F.construir_definicion())
    assert final(t, lote)["CODIGO_RESULTADO"] == "ERROR_LECTURA_EXCEL"


def test_si_falla_la_escritura_final_el_flujo_falla_visiblemente_y_el_lote_queda_PROCESANDO():
    """Riesgo conocido, documentado: el flujo no tiene a dónde reportar si SharePoint rechaza el último MERGE."""
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    t.fallos["merge_final"] = ("Failed", 500)
    r = procesar(t, lote)
    assert r.estado_final == "Failed" and final(t, lote)["ESTADO"] == "PROCESANDO"


# ------------------------------------------------------------------ aislamiento
def test_solo_toca_la_lista_de_lotes_y_la_carpeta_temporal():
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    procesar(t, lote)
    assert {op for op, _ in t.llamadas} == {"HttpRequest", "GetAttachments", "GetAttachmentContent", "CreateFile", "GetItems"}
    assert all(c == F.CARPETA_TEMP for c, _, _ in t.biblioteca.values())
    texto = json.dumps(F.construir_definicion())
    assert "Depositos_Activos" not in texto and "Depositos_Reversiones" not in texto
    assert "ETag" not in texto and "TIPO_CAMBIO" not in texto


def test_el_flujo_solo_escribe_columnas_declaradas_en_el_esquema():
    declaradas = {c["nombre_tecnico"] for c in ESQUEMA["columnas"]}
    assert set(F.CAMPOS_ESCRITOS) <= declaradas
    t, lote = tenant("Ejemplo_Confirmacion_Masiva_P9.xlsx")
    procesar(t, lote)
    escritas = {k for _, _, c in t.escrituras for k in c}
    assert escritas == set(F.CAMPOS_ESCRITOS) - {"ARCHIVO_NOMBRE"} | ({"ARCHIVO_NOMBRE"} & escritas)
    assert escritas <= set(F.CAMPOS_ESCRITOS)


def test_codigos_de_resultado_del_flujo_estan_en_el_esquema():
    permitidos = next(c for c in ESQUEMA["columnas"] if c["nombre_tecnico"] == "CODIGO_RESULTADO")["valores"]
    assert set(F.CODIGOS) == set(permitidos)
    visto = set(json.dumps(F.construir_definicion()).split('"codigo": "')[1:])
    for fragmento in visto:
        assert fragmento.split('"')[0] in permitidos
