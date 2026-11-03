"""Escenarios sintéticos del flujo DIRECTO contra el tenant SIMULADO (sin listas, sin lotes, sin estados persistentes).

[VALIDADO LOCALMENTE] significa: el flujo generado, interpretado por el intérprete WDL local, produce este resultado con un
Excel/SharePoint falsos. NO prueba el runtime Microsoft ni mide tiempos reales: eso es MEDICION_TENANT.md.
"""
import json
import re
from pathlib import Path

import pytest
from openpyxl import load_workbook

from proto_masiva.flows import construir as F
from simulador import TenantSimulado, configurar, depositos_que_coinciden, procesar

XLSX = Path(__file__).resolve().parents[1] / "xlsx"
MED = XLSX / "medicion"
EJEMPLO, PLANTILLA = "Ejemplo_Confirmacion_Masiva_P9.xlsx", "Plantilla_Confirmacion_Masiva_P9.xlsx"


def tenant_para(archivo, ruta=XLSX):
    """Tenant simulado cuya lista Depositos_Activos TIENE un depósito DISPONIBLE por cada fila del archivo (todo debe salir válido)."""
    return TenantSimulado(depositos=depositos_que_coinciden((ruta / archivo).read_bytes()))


def correr(archivo, ruta=XLSX, **kw):
    kw.setdefault("tenant", tenant_para(archivo, ruta))
    return procesar(archivo, (ruta / archivo).read_bytes(), **kw)


def resp(ensayo):
    assert ensayo.estado_final == "Succeeded" and ensayo.respuesta is not None
    return ensayo.respuesta


# ------------------------------------------------------------------ A-E (los cinco pedidos)
def test_A_archivo_correcto_3_filas():
    t, e = correr(EJEMPLO)
    r = resp(e)
    assert (r["resultado"], r["codigo"], r["tabla_encontrada"], r["filas_leidas"]) == ("OK", "PREVALIDACION_OK", "SI", "3")
    assert r["mensaje"].startswith("3 de 3 filas válidas") and r["archivo"] == EJEMPLO
    assert (r["filas_totales"], r["filas_validas"], r["filas_con_error"], r["depositos_consultados"]) == ("3", "3", "0", "3")
    assert r["copia_temporal_eliminada"] == "SI" and not t.biblioteca


def test_A2_otro_archivo_de_3_filas():
    r = resp(correr("01_OK_3filas.xlsx")[1])
    assert (r["resultado"], r["filas_leidas"]) == ("OK", "3")


@pytest.mark.parametrize("archivo", [PLANTILLA, "02a_TABLA_VACIA_1fila_en_blanco.xlsx", "02b_TABLA_SOLO_ENCABEZADO.xlsx"])
def test_B_tabla_vacia_es_ERROR_ARCHIVO_VACIO_controlado(archivo):
    """Diseño: una importación sin filas NO es OK (no hay nada que confirmar). Resultado controlado, el flujo no falla."""
    t, e = correr(archivo)
    r = resp(e)
    assert (r["resultado"], r["codigo"], r["tabla_encontrada"], r["filas_leidas"]) == ("ERROR", "ARCHIVO_VACIO", "SI", "0")
    assert r["copia_temporal_eliminada"] == "SI" and not t.biblioteca


def test_C_sin_tabla():
    t, e = correr("03_SIN_TABLA.xlsx")
    r = resp(e)
    assert (r["resultado"], r["codigo"], r["tabla_encontrada"], r["filas_leidas"]) == ("ERROR", "TABLA_NO_ENCONTRADA", "NO", "0")
    assert r["copia_temporal_eliminada"] == "SI" and not t.biblioteca  # aun con fallo de Excel, la copia se borra


def test_D_encabezado_cambiado():
    r = resp(correr("05_ENCABEZADO_CAMBIADO.xlsx")[1])
    assert (r["resultado"], r["codigo"], r["tabla_encontrada"], r["filas_leidas"]) == ("ERROR", "ESTRUCTURA_INVALIDA", "SI", "0")
    assert "CUENTA_BANCARIA" in r["mensaje"] and "plantilla oficial" in r["mensaje"]


def test_E_tabla_con_nombre_distinto():
    r = resp(correr("04_TABLA_NOMBRE_DISTINTO.xlsx")[1])
    assert (r["resultado"], r["codigo"], r["tabla_encontrada"]) == ("ERROR", "TABLA_NO_ENCONTRADA", "NO")


# ------------------------------------------------------------------ entradas anómalas (el flujo no toca nada)
@pytest.mark.parametrize("nombre,contenido,codigo", [(None, None, "SIN_ARCHIVO"), ("", b"x", "SIN_ARCHIVO"), ("a.xlsx", b"", "SIN_ARCHIVO"),
                                                     ("datos.csv", b"a,b\n", "NO_ES_XLSX"), ("libro.xls", b"x", "NO_ES_XLSX")])
def test_entradas_invalidas_no_crean_copia_ni_llaman_a_excel(nombre, contenido, codigo):
    t, e = procesar(nombre, contenido)
    r = resp(e)
    assert (r["resultado"], r["codigo"], r["copia_temporal_eliminada"]) == ("ERROR", codigo, "NO_APLICA")
    assert t.llamadas == [] and not t.creados


def test_la_extension_no_distingue_mayusculas():
    r = resp(procesar("PLANTILLA.XLSX", (XLSX / EJEMPLO).read_bytes(), tenant=tenant_para(EJEMPLO))[1])
    assert (r["resultado"], r["filas_leidas"]) == ("OK", "3")


def test_xlsx_corrupto_no_se_confunde_con_tabla_ausente_y_se_borra_la_copia():
    t, e = procesar("roto.xlsx", b"esto no es un zip")
    r = resp(e)
    assert (r["resultado"], r["codigo"]) == ("ERROR", "ERROR_LECTURA_EXCEL") and "HTTP 400" in r["mensaje"]
    assert r["copia_temporal_eliminada"] == "SI" and not t.biblioteca


# ------------------------------------------------------------------ fallos de infraestructura
@pytest.mark.parametrize("http", [409, 403, 500])
def test_si_falla_crear_la_copia_no_hay_nada_que_borrar_ni_se_lee_excel(http):
    t = tenant_para(EJEMPLO)
    t.fallos["crear"] = ("Failed", http)
    r = resp(correr(EJEMPLO, tenant=t)[1])
    assert (r["resultado"], r["codigo"], r["copia_temporal_eliminada"]) == ("ERROR", "ERROR_COPIA_ARCHIVO", "NO_APLICA")
    assert [op for op, _ in t.llamadas] == ["CreateFile"]


@pytest.mark.parametrize("http,codigo", [(423, "ARCHIVO_BLOQUEADO"), (500, "ERROR_LECTURA_EXCEL"), (404, "TABLA_NO_ENCONTRADA")])
def test_fallos_de_excel_se_clasifican_y_la_copia_se_borra(http, codigo):
    t = tenant_para(EJEMPLO)
    t.fallos["excel"] = ("Failed", http)
    r = resp(correr(EJEMPLO, tenant=t)[1])
    assert (r["resultado"], r["codigo"], r["filas_leidas"], r["copia_temporal_eliminada"]) == ("ERROR", codigo, "0", "SI")
    assert not t.biblioteca


def test_si_no_se_puede_borrar_la_copia_el_resultado_de_negocio_no_cambia_solo_se_informa():
    t = tenant_para(EJEMPLO)
    t.fallos["borrar"] = ("Failed", 423)
    t2, e = correr(EJEMPLO, tenant=t)
    r = resp(e)
    assert (r["resultado"], r["codigo"], r["filas_leidas"]) == ("OK", "PREVALIDACION_OK", "3")
    assert r["copia_temporal_eliminada"] == "NO" and len(t.biblioteca) == 1  # queda 1 archivo huérfano, y la app lo sabe


def test_fallo_de_excel_y_de_borrado_a_la_vez():
    t = tenant_para(EJEMPLO)
    t.fallos.update(excel=("Failed", 500), borrar=("Failed", 500))
    r = resp(correr(EJEMPLO, tenant=t)[1])
    assert (r["resultado"], r["codigo"], r["copia_temporal_eliminada"]) == ("ERROR", "ERROR_LECTURA_EXCEL", "NO")


def test_archivo_bloqueado_423_luego_liberado():
    t = tenant_para(EJEMPLO)
    r1 = resp(correr(EJEMPLO, tenant=t, definicion=None)[1])
    assert r1["resultado"] == "OK"
    t.fallos["excel"] = ("Failed", 423)
    assert resp(correr(EJEMPLO, tenant=t)[1])["codigo"] == "ARCHIVO_BLOQUEADO"
    del t.fallos["excel"]
    assert resp(correr(EJEMPLO, tenant=t)[1])["resultado"] == "OK"  # reintentar el mismo archivo funciona; no hay estado que limpiar


# ------------------------------------------------------------------ tamaño: el flujo NO inventa límites
def test_sin_tope_configurado_el_flujo_lee_mil_filas():
    t, e = correr("Filas_1000.xlsx", ruta=MED)
    r = resp(e)
    assert (r["resultado"], r["codigo"], r["filas_leidas"]) == ("OK", "PREVALIDACION_OK", "1000") and F.MAX_FILAS == 0


def test_si_la_lectura_alcanza_el_umbral_de_paginacion_avisa_en_vez_de_contar_de_menos():
    t, e = correr("Filas_2000.xlsx", ruta=MED)
    r = resp(e)
    assert (r["resultado"], r["codigo"]) == ("ERROR", "DEMASIADAS_FILAS") and "el máximo permitido es 1999" in r["mensaje"] and "No se procesó ninguna fila" in r["mensaje"]
    assert r["filas_leidas"] == "0" and r["copia_temporal_eliminada"] == "SI"


def test_el_umbral_de_paginacion_es_el_unico_parametro_compartido_entre_la_accion_y_la_comprobacion():
    d = F.construir_definicion()
    assert d["actions"]["PARAM_PAGINACION"]["inputs"] == F.PAGINACION
    excel = d["actions"]["TRY"]["actions"]["Entrada_valida"]["actions"]["Leer_tabla_Excel"]
    assert excel["runtimeConfiguration"]["paginationPolicy"]["minimumItemCount"] == F.PAGINACION


@pytest.mark.parametrize("tope,codigo", [(2, "DEMASIADAS_FILAS"), (3, "PREVALIDACION_OK"), (4, "PREVALIDACION_OK")])
def test_el_maximo_de_filas_es_un_parametro_opcional_que_se_fija_despues_de_medir(tope, codigo):
    d = configurar(F.construir_definicion(max_filas=tope))
    r = resp(correr(EJEMPLO, definicion=d)[1])
    assert r["codigo"] == codigo
    if codigo != "PREVALIDACION_OK":
        assert "máximo permitido es 2" in r["mensaje"] and r["filas_leidas"] == "3" and r["resultado"] == "ERROR"


# ------------------------------------------------------------------ tiempos (para medir en tenant)
def test_la_respuesta_trae_los_tiempos_por_etapa():
    r = resp(correr(EJEMPLO)[1])
    m = re.fullmatch(r"crear=(\d+);excel=(\d+);depositos=(\d+);borrar=(\d+);total=(\d+)", r["tiempos_ms"])
    assert m, r["tiempos_ms"]
    crear, excel, depositos, borrar, total = map(int, m.groups())
    assert crear > 0 and excel > 0 and depositos > 0 and borrar > 0
    assert total >= crear + excel + depositos + borrar  # reloj simulado, no tiempos reales


def test_sin_archivo_las_etapas_no_ejecutadas_valen_cero():
    r = resp(procesar(None, None)[1])
    assert r["tiempos_ms"].startswith("crear=0;excel=0;")


# ------------------------------------------------------------------ aislamiento y ausencia de la infraestructura eliminada
def test_solo_toca_la_carpeta_temporal_y_excel_y_deja_la_biblioteca_como_la_encontro():
    t, e = correr(EJEMPLO)
    assert {op for op, _ in t.llamadas} == {"CreateFile", "GetItems", "HttpRequest", "DeleteFile"}
    assert [n for op, n in t.llamadas if op == "HttpRequest"] == ["Leer_depositos"]  # UNA sola lectura de Depositos_Activos para todo el archivo
    assert all(c == F.CARPETA_TEMP for c, _, _ in t.biblioteca.values()) and t.creados == t.borrados and not t.biblioteca


def test_el_flujo_ya_no_tiene_lotes_ni_estados_ni_sondeo_ni_escrituras():
    texto = json.dumps(F.construir_definicion(), ensure_ascii=False)
    for prohibido in ("LOTE", "Lote", "PENDIENTE", "PROCESANDO", "CARGADO", "GetOnUpdatedItems", "GetAttachments",
                      "GetAttachmentContent", "GetByTitle", "MERGE", "IF-MATCH", "ETag", "Depositos_Reversiones",
                      "TIPO_CAMBIO", "Confirmaciones_Masivas"):
        assert prohibido not in texto, prohibido


def test_cada_ejecucion_es_independiente_no_queda_estado_entre_llamadas():
    t = tenant_para(EJEMPLO)
    a = resp(correr(EJEMPLO, tenant=t)[1])
    b = resp(correr("03_SIN_TABLA.xlsx", tenant=t)[1])
    c = resp(correr(EJEMPLO, tenant=t)[1])
    assert (a["codigo"], b["codigo"], c["codigo"]) == ("PREVALIDACION_OK", "TABLA_NO_ENCONTRADA", "PREVALIDACION_OK") and not t.biblioteca


def test_resultados_posibles_y_codigos_son_los_declarados():
    assert set(F.SALIDAS) == {"resultado", "codigo", "mensaje", "archivo", "tabla_encontrada", "filas_leidas",
                              "copia_temporal_eliminada", "tiempos_ms"}
    assert set(F.SALIDAS_NUEVAS) == {"filas_totales", "filas_validas", "filas_con_error", "depositos_consultados", "detalle_json"}
    declarados = set(F.CODIGOS)
    vistos = set()
    for archivo in (EJEMPLO, PLANTILLA, "03_SIN_TABLA.xlsx", "05_ENCABEZADO_CAMBIADO.xlsx"):
        r = resp(correr(archivo)[1])
        assert r["resultado"] in F.RESULTADOS_GLOBALES
        vistos.add(r["codigo"])
    assert vistos <= declarados
    assert set(re.findall(r'"codigo": "([A-Z_]+)"', json.dumps(F.construir_definicion()))) <= declarados
