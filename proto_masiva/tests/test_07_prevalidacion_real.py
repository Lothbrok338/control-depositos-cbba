"""PREVALIDACIÓN REAL de cada fila contra Depositos_Activos (SOLO LECTURA), contra un SharePoint SIMULADO.

[VALIDADO LOCALMENTE] = el flujo generado, interpretado por el intérprete WDL local, produce este resultado con un Depositos_Activos
falso. NO prueba el runtime de Power Automate ni los códigos/respuestas reales de SharePoint: los supuestos que solo el tenant puede
confirmar están listados en PREVALIDACION_REAL.md («Qué NO está validado en tenant»).
"""
import json
import random
import re
from datetime import date, datetime
from pathlib import Path

import pytest

import oraculo_prevalidacion as O
import simulador as S
from proto_masiva import contrato_plantilla as P
from proto_masiva.flows import construir as F
from proto_masiva.flows import prevalidacion as PV
from simulador import TenantSimulado, deposito, procesar, xlsx_con_filas

XLSX = Path(__file__).resolve().parents[1] / "xlsx"
HOY = date(2026, 10, 5)   # el reloj simulado arranca el 2026-10-05 12:00 UTC (= 08:00 en Bolivia)


def fila(banco="BNB", cuenta="3000100152", codigo="COD-0001", importe=100.0, moneda="BOB", estudiante="ANA PEREZ",
         solicitado="SOLICITANTE", sede="COCHABAMBA", obs=""):
    return (banco, cuenta, codigo, importe, moneda, estudiante, solicitado, sede, obs)


def corre(filas, depositos, **kw):
    t = kw.pop("tenant", None) or TenantSimulado(depositos=depositos, tope=kw.pop("tope", None))
    t, e = procesar("prevalidar.xlsx", xlsx_con_filas(filas), tenant=t, **kw)
    assert e.estado_final == "Succeeded" and e.respuesta is not None
    return t, e.respuesta


def detalle(respuesta):
    return json.loads(respuesta["detalle_json"])


def resultados(respuesta):
    return [d["resultado"] for d in detalle(respuesta)]


def una(f, depositos):
    """Prevalida UNA fila y devuelve (respuesta global, detalle de la fila)."""
    t, r = corre([f], depositos)
    assert t.depositos == t.depositos_iniciales
    return r, detalle(r)[0]


D1 = deposito(101, "BNB", "3000100152", "COD-0001", 100.0)


# ====================================================================== 1-5 · los resultados básicos
def test_01_fila_valida_devuelve_el_deposito_y_todo_lo_necesario_para_confirmar_despues():
    r, d = una(fila(obs="OBS"), [D1])
    assert (r["resultado"], r["codigo"]) == ("OK", "PREVALIDACION_OK")
    assert (r["filas_totales"], r["filas_validas"], r["filas_con_error"], r["depositos_consultados"]) == ("1", "1", "0", "1")
    assert d == {"fila_excel": 6, "fila_tabla": 1, "resultado": "VALIDO", "mensaje": "Depósito disponible encontrado (ID 101).",
                 "deposito_id": 101, "clave_transaccion": "CLAVE-101", "estado_actual": "DISPONIBLE", "fecha_movimiento": "2026-10-01",
                 "moneda_deposito": "BOB", "coincidencias": 1, "banco": "BNB", "cuenta_bancaria": "3000100152",
                 "codigo_asignacion": "COD-0001", "importe": 100.0, "importe_original": "100", "moneda": "BOB",
                 "estudiante": "ANA PEREZ", "solicitado_por": "SOLICITANTE", "sede": "COCHABAMBA", "observacion": "OBS"}
    assert "etag" not in json.dumps(d).lower()  # la prevalidación NO reserva nada: la confirmación futura obtendrá un ETag fresco


def test_02_deposito_no_encontrado():
    r, d = una(fila(codigo="OTRO"), [D1])
    assert (r["resultado"], r["codigo"], r["filas_validas"], r["filas_con_error"]) == ("OBSERVADO", "PREVALIDACION_CON_ERRORES", "0", "1")
    assert d["resultado"] == "NO_ENCONTRADO" and d["deposito_id"] is None and d["coincidencias"] == 0 and d["clave_transaccion"] == ""


def test_03_dos_depositos_con_la_misma_clave_es_asignacion_ambigua():
    r, d = una(fila(), [D1, deposito(102, "BNB", "3000100152", "COD-0001", 100.0)])
    assert d["resultado"] == "ASIGNACION_AMBIGUA" and d["coincidencias"] == 2 and d["deposito_id"] is None
    assert "2 depósitos" in d["mensaje"]


def test_04_moneda_distinta_es_moneda_no_coincide_y_NO_no_encontrado():
    r, d = una(fila(moneda="BOB"), [deposito(101, "BNB", "3000100152", "COD-0001", 100.0, moneda="USD")])
    assert d["resultado"] == "MONEDA_NO_COINCIDE" and d["moneda"] == "BOB" and d["moneda_deposito"] == "USD"
    assert d["deposito_id"] == 101 and d["estado_actual"] == "DISPONIBLE"  # diagnóstico: se encontró UN depósito


@pytest.mark.parametrize("estado", ["ASIGNADO", "EN_REVISION", "CONFIRMADO", ""])
def test_05_deposito_no_disponible_devuelve_el_estado_real_sin_suponer_que_es_confirmado(estado):
    r, d = una(fila(), [deposito(101, "BNB", "3000100152", "COD-0001", 100.0, estado=estado)])
    assert d["resultado"] == "NO_DISPONIBLE" and d["estado_actual"] == estado and d["deposito_id"] == 101
    assert estado in d["mensaje"]


# ====================================================================== 6-8 · campos
@pytest.mark.parametrize("columna", P.OBLIGATORIAS)
@pytest.mark.parametrize("vacio", [None, "", "   "])
def test_06_campo_requerido_vacio_es_fila_incompleta_y_no_autocompleta_la_sede(columna, vacio):
    f = list(fila())
    f[P.ENCABEZADOS.index(columna)] = vacio
    r, d = una(tuple(f), [D1])
    assert d["resultado"] == "FILA_INCOMPLETA" and columna in d["mensaje"] and d["deposito_id"] is None
    assert d["sede"] == ("" if columna == "SEDE" else "COCHABAMBA")  # SEDE vacía NO se rellena con nada


def test_06b_observacion_es_opcional():
    assert una(fila(obs=None), [D1])[1]["resultado"] == "VALIDO"


def test_06c_se_listan_todos_los_campos_que_faltan():
    d = una(fila(estudiante="", sede="", solicitado=None), [D1])[1]
    assert d["resultado"] == "FILA_INCOMPLETA" and d["mensaje"] == "Faltan datos obligatorios: ESTUDIANTE, SOLICITADO_POR, SEDE."


@pytest.mark.parametrize("importe", ["abc", "-5", "-0.5", 0, "0", "0.00", "1,5", "1.234", 12.345, "1.5.3", "1e3", "1E3", ".5", "5.", "1 500",
                                     "$100", "100 BOB", "١٢٣", "1234567890123456"])
def test_07_importe_invalido(importe):
    d = una(fila(importe=importe), [deposito(101, "BNB", "3000100152", "COD-0001", 100.0)])[1]
    assert d["resultado"] == "IMPORTE_INVALIDO" and d["importe"] is None and d["deposito_id"] is None
    assert d["importe_original"] == str(importe).strip()


@pytest.mark.parametrize("importe,esperado", [(100, 100.0), (100.5, 100.5), ("100.50", 100.5), ("100", 100.0), (" 100.5 ", 100.5),
                                              ("0.01", 0.01), (0.07, 0.07), (1.15, 1.15), (19.99, 19.99), (4.35, 4.35), (8.2, 8.2),
                                              (1234567.89, 1234567.89), ("007.5", 7.5)])
def test_07b_importes_validos_se_comparan_como_numero_exacto_sin_errores_de_redondeo(importe, esperado):
    r, d = una(fila(importe=importe), [deposito(101, "BNB", "3000100152", "COD-0001", esperado)])
    assert (d["resultado"], d["importe"]) == ("VALIDO", esperado)


def test_07c_una_diferencia_de_un_centavo_NO_coincide_y_no_hay_redondeo_arbitrario():
    assert una(fila(importe=100.00), [deposito(101, "BNB", "3000100152", "COD-0001", 100.01)])[1]["resultado"] == "NO_ENCONTRADO"
    assert una(fila(importe="100"), [deposito(101, "BNB", "3000100152", "COD-0001", "100.0")])[1]["resultado"] == "VALIDO"  # IMPORTE del depósito como texto


@pytest.mark.parametrize("moneda", ["EUR", "BS", "bolivianos", "BOB USD", "US"])
def test_08_moneda_invalida(moneda):
    d = una(fila(moneda=moneda), [D1])[1]
    assert d["resultado"] == "MONEDA_INVALIDA" and "BOB o USD" in d["mensaje"] and d["deposito_id"] is None


@pytest.mark.parametrize("moneda", ["bob", " BOB ", "Bob"])
def test_08b_moneda_se_normaliza_con_trim_y_mayusculas(moneda):
    d = una(fila(moneda=moneda), [D1])[1]
    assert (d["resultado"], d["moneda"]) == ("VALIDO", "BOB")


# ====================================================================== 9 · duplicados dentro del Excel
def test_09_duplicado_en_el_excel_deja_AMBAS_filas_como_DUPLICADO_ARCHIVO():
    filas = [fila(codigo="COD-0001"), fila(banco="BCP", cuenta="301-5005684-3-97", codigo="OTRO"), fila(codigo="COD-0001")]
    t, r = corre(filas, [D1, deposito(102, "BCP", "301-5005684-3-97", "OTRO", 100.0)])
    assert resultados(r) == ["DUPLICADO_ARCHIVO", "VALIDO", "DUPLICADO_ARCHIVO"]  # no queda válida una y bloqueada la otra
    assert [d["fila_excel"] for d in detalle(r)] == [6, 7, 8]
    assert (r["resultado"], r["filas_validas"], r["filas_con_error"]) == ("OBSERVADO", "1", "2")


def test_09b_la_clave_de_duplicado_es_banco_cuenta_codigo_importe_la_moneda_no_cuenta():
    t, r = corre([fila(moneda="BOB"), fila(moneda="USD")], [D1])
    assert resultados(r) == ["DUPLICADO_ARCHIVO", "DUPLICADO_ARCHIVO"]


def test_09c_tres_repeticiones_y_normalizacion_de_mayusculas_y_espacios():
    t, r = corre([fila(), fila(banco=" bnb ", codigo="cod-0001"), fila(codigo="COD-0001 ")], [D1])
    assert resultados(r) == ["DUPLICADO_ARCHIVO"] * 3 and "3 filas" in detalle(r)[0]["mensaje"]


def test_09d_distinto_importe_o_cuenta_o_codigo_no_es_duplicado():
    filas = [fila(), fila(importe=100.01), fila(cuenta="3400041236"), fila(codigo="COD-0002")]
    t, r = corre(filas, [D1])
    assert resultados(r) == ["VALIDO", "NO_ENCONTRADO", "NO_ENCONTRADO", "NO_ENCONTRADO"]


def test_09e_fila_incompleta_con_la_misma_clave_no_oculta_el_duplicado_de_la_otra():
    # la fila 1 sigue siendo FILA_INCOMPLETA (precede), pero apunta al mismo depósito que la fila 2: la fila 2 no puede quedar VALIDA
    t, r = corre([fila(sede=""), fila()], [D1])
    assert resultados(r) == ["FILA_INCOMPLETA", "DUPLICADO_ARCHIVO"]


# ====================================================================== 10-11 · ceros iniciales (texto, nunca número)
def test_10_codigo_con_ceros_iniciales_se_conserva_y_no_se_confunde_con_el_mismo_numero():
    deps = [deposito(101, "BNB", "3000100152", "001234", 100.0)]
    assert una(fila(codigo="001234"), deps)[1]["resultado"] == "VALIDO"
    assert una(fila(codigo="1234"), deps)[1]["resultado"] == "NO_ENCONTRADO"       # 1234 != 001234
    d = una(fila(codigo="001234"), deps)[1]
    assert d["codigo_asignacion"] == "001234"                                       # el detalle conserva los ceros
    assert una(fila(codigo="001234"), [deposito(101, "BNB", "3000100152", "1234", 100.0)])[1]["resultado"] == "NO_ENCONTRADO"


def test_11_cuenta_bancaria_con_ceros_iniciales_se_conserva():
    deps = [deposito(101, "BISA", "0696870039", "COD-0001", 100.0)]
    d = una(fila(banco="BISA", cuenta="0696870039"), deps)[1]
    assert (d["resultado"], d["cuenta_bancaria"]) == ("VALIDO", "0696870039")
    assert una(fila(banco="BISA", cuenta="696870039"), deps)[1]["resultado"] == "NO_ENCONTRADO"
    assert una(fila(banco="BISA", cuenta="0696870039"), [deposito(101, "BISA", "696870039", "COD-0001", 100.0)])[1]["resultado"] == "NO_ENCONTRADO"


@pytest.mark.parametrize("cuenta", ["301-5005684-3-97", "10000003224552"])
def test_11b_cuentas_con_guiones_o_largas_del_catalogo(cuenta):
    assert una(fila(banco="BCP", cuenta=cuenta), [deposito(101, "BCP", cuenta, "COD-0001", 100.0)])[1]["resultado"] == "VALIDO"


@pytest.mark.parametrize("banco_excel", ["banco unión", "BANCO UNIÓN", " Banco Unión "])
def test_11c_banco_sin_distinguir_mayusculas_pero_conservando_las_tildes(banco_excel):
    assert una(fila(banco=banco_excel, cuenta="10000003224552"),
               [deposito(101, "BANCO UNIÓN", "10000003224552", "COD-0001", 100.0)])[1]["resultado"] == "VALIDO"
    assert una(fila(banco="BANCO UNION", cuenta="10000003224552"),
               [deposito(101, "BANCO UNIÓN", "10000003224552", "COD-0001", 100.0)])[1]["resultado"] == "NO_ENCONTRADO"


# ====================================================================== 12 · mezcla
def test_12_archivo_mixto_valido_y_con_errores_cada_fila_su_resultado():
    deps = [deposito(101, "BNB", "3000100152", "A", 100.0), deposito(102, "BNB", "3000100152", "B", 200.0, estado="ASIGNADO"),
            deposito(103, "BNB", "3000100152", "C", 300.0, moneda="USD"), deposito(104, "BNB", "3000100152", "D", 400.0),
            deposito(105, "BNB", "3000100152", "D", 400.0)]
    filas = [fila(codigo="A", importe=100.0), fila(codigo="B", importe=200.0), fila(codigo="C", importe=300.0, moneda="BOB"),
             fila(codigo="D", importe=400.0), fila(codigo="ZZ", importe=1.0), fila(codigo="E", importe="x"), fila(codigo="F", moneda="EUR"),
             fila(codigo="G", sede=""), fila(codigo="A", importe=100.0, moneda="USD")]
    t, r = corre(filas, deps)
    assert resultados(r) == ["DUPLICADO_ARCHIVO", "NO_DISPONIBLE", "MONEDA_NO_COINCIDE", "ASIGNACION_AMBIGUA", "NO_ENCONTRADO",
                             "IMPORTE_INVALIDO", "MONEDA_INVALIDA", "FILA_INCOMPLETA", "DUPLICADO_ARCHIVO"]
    assert (r["resultado"], r["codigo"], r["filas_totales"], r["filas_validas"], r["filas_con_error"]) == \
        ("OBSERVADO", "PREVALIDACION_CON_ERRORES", "9", "0", "9")
    assert r["mensaje"] == "0 de 9 filas válidas; 9 con observaciones. Prevalidación de solo lectura: no se confirmó ningún depósito."


def test_12b_validas_y_errores_mezclados_el_resumen_cuenta_bien():
    deps = [deposito(100 + i, "BNB", "3000100152", f"C{i}", 10.0 * i) for i in range(1, 6)]
    filas = [fila(codigo=f"C{i}", importe=10.0 * i) for i in range(1, 6)] + [fila(codigo="NO")]
    t, r = corre(filas, deps)
    assert resultados(r) == ["VALIDO"] * 5 + ["NO_ENCONTRADO"]
    assert (r["resultado"], r["filas_totales"], r["filas_validas"], r["filas_con_error"]) == ("OBSERVADO", "6", "5", "1")


def test_12c_todas_validas_es_OK_y_las_filas_en_blanco_no_cuentan_pero_conservan_la_posicion():
    deps = [deposito(101, "BNB", "3000100152", "A", 100.0), deposito(102, "BNB", "3000100152", "B", 200.0)]
    t, r = corre([fila(codigo="A", importe=100.0), None, (None,) * 9, fila(codigo="B", importe=200.0)], deps)
    assert (r["resultado"], r["codigo"], r["filas_totales"], r["filas_leidas"]) == ("OK", "PREVALIDACION_OK", "2", "2")
    assert [(d["fila_tabla"], d["fila_excel"]) for d in detalle(r)] == [(1, 6), (4, 9)]  # la fila de la hoja sigue alineada con el Excel


# ====================================================================== 13-15 · errores técnicos (no llegan a Depositos_Activos)
@pytest.mark.parametrize("archivo,codigo", [("Plantilla_Confirmacion_Masiva_P9.xlsx", "ARCHIVO_VACIO"),
                                            ("02a_TABLA_VACIA_1fila_en_blanco.xlsx", "ARCHIVO_VACIO"),
                                            ("03_SIN_TABLA.xlsx", "TABLA_NO_ENCONTRADA"),
                                            ("04_TABLA_NOMBRE_DISTINTO.xlsx", "TABLA_NO_ENCONTRADA"),
                                            ("05_ENCABEZADO_CAMBIADO.xlsx", "ESTRUCTURA_INVALIDA")])
def test_13_14_15_cero_filas_tabla_incorrecta_y_encabezado_incorrecto_son_ERROR_y_no_consultan_depositos(archivo, codigo):
    t = TenantSimulado(depositos=[D1])
    t, e = procesar(archivo, (XLSX / archivo).read_bytes(), tenant=t)
    r = e.respuesta
    assert (r["resultado"], r["codigo"]) == ("ERROR", codigo)
    assert r["detalle_json"] == "[]" and (r["filas_totales"], r["filas_validas"], r["filas_con_error"]) == ("0", "0", "0")
    assert t.consultas == [] and "HttpRequest" not in [op for op, _ in t.llamadas]  # ni una sola lectura a Depositos_Activos


def test_15b_cualquier_encabezado_cambiado_se_nombra_y_no_prevalida():
    enc = list(P.ENCABEZADOS)
    enc[1] = "CUENTA"
    t = TenantSimulado(depositos=[D1])
    t, e = procesar("x.xlsx", xlsx_con_filas([fila()], encabezados=enc), tenant=t)
    assert (e.respuesta["codigo"], t.consultas) == ("ESTRUCTURA_INVALIDA", []) and "CUENTA_BANCARIA" in e.respuesta["mensaje"]


def test_16_un_fallo_de_sharepoint_es_ERROR_SHAREPOINT_no_un_resultado_de_filas_y_se_borra_la_copia():
    t = TenantSimulado(depositos=[D1])
    t.fallos["depositos"] = ("Failed", 500)
    t, r = corre([fila()], None, tenant=t)
    assert (r["resultado"], r["codigo"]) == ("ERROR", "ERROR_SHAREPOINT") and "HTTP 500" in r["mensaje"]
    assert r["detalle_json"] == "[]" and r["copia_temporal_eliminada"] == "SI" and not t.biblioteca


@pytest.mark.parametrize("http", [403, 404, 429])
def test_16b_otros_codigos_http_de_sharepoint(http):
    t = TenantSimulado(depositos=[D1])
    t.fallos["depositos"] = ("Failed", http)
    assert corre([fila()], None, tenant=t)[1]["codigo"] == "ERROR_SHAREPOINT"


def test_17_si_el_universo_supera_el_tope_se_avisa_en_vez_de_marcar_NO_ENCONTRADO_por_error():
    deps = [deposito(100 + i, "BNB", "3000100152", f"C{i}", 10.0 * i) for i in range(1, 4)]
    t, r = corre([fila(codigo="C3", importe=30.0)], deps, tope=2)  # SharePoint devuelve __next: hay más de lo leído
    assert (r["resultado"], r["codigo"]) == ("ERROR", "DEPOSITOS_DEMASIADOS") and "incompleto" in r["mensaje"]
    assert r["detalle_json"] == "[]"


# ====================================================================== universo elegible: CRÉDITO + ventana de la galería
def test_18_solo_cuentan_los_creditos_un_debito_con_la_misma_clave_no_es_candidato():
    d = una(fila(), [deposito(101, "BNB", "3000100152", "COD-0001", 100.0, tipo="DÉBITO")])[1]
    assert d["resultado"] == "NO_ENCONTRADO"


@pytest.mark.parametrize("fecha,resultado", [("2026-08-04", "NO_ENCONTRADO"), ("2026-08-05", "VALIDO"), ("2026-10-05", "VALIDO"),
                                             ("2026-10-06", "NO_ENCONTRADO"), ("2026-01-01", "NO_ENCONTRADO")])
def test_19_ventana_de_los_ultimos_2_meses_igual_que_la_galeria_individual(fecha, resultado):
    # galDepositosP9_1: FECHA_MOVIMIENTO >= DateAdd(Today(), -2, TimeUnit.Months) y FECHA_MOVIMIENTO <= Today(); hoy simulado = 2026-10-05
    d = una(fila(), [deposito(101, "BNB", "3000100152", "COD-0001", 100.0, fecha=fecha)])[1]
    assert d["resultado"] == resultado


def test_19b_el_flujo_consulta_con_la_misma_ventana_y_una_sola_vez():
    t, r = corre([fila() for _ in range(3)], [D1])
    assert t.consultas == [(PV.LISTA_DEPOSITOS_ID, "2026-08-05", "2026-10-05", 5000)]


@pytest.mark.parametrize("ahora,desde,hasta", [
    (datetime(2026, 10, 6, 2, 0, 0), "2026-08-05", "2026-10-05"),   # 02:00 UTC = 22:00 del día anterior en Bolivia (UTC-4)
    (datetime(2026, 10, 31, 12, 0, 0), "2026-08-31", "2026-10-31"),
    (datetime(2026, 4, 30, 12, 0, 0), "2026-02-28", "2026-04-30"),  # DateAdd recorta al último día del mes
    (datetime(2026, 3, 31, 12, 0, 0), "2026-01-31", "2026-03-31"),
    (datetime(2026, 1, 15, 12, 0, 0), "2025-11-15", "2026-01-15")])  # cruza de año
def test_19c_hoy_se_calcula_en_hora_de_Bolivia_y_el_mes_se_recorta_como_DateAdd(monkeypatch, ahora, desde, hasta):
    monkeypatch.setattr(S, "INICIO", ahora)
    t, r = corre([fila()], [D1])
    assert t.consultas[0][1:3] == (desde, hasta)
    # y es exactamente lo que calcula la regla escrita de la app
    assert O.hace_dos_meses(date.fromisoformat(hasta)).isoformat() == desde


# ====================================================================== sin N+1, sin escrituras
@pytest.mark.parametrize("n", [1, 10, 50, 100])
def test_20_una_sola_llamada_a_sharepoint_sin_importar_cuantas_filas(n):
    deps = [deposito(1000 + i, "BNB", "3000100152", f"C{i}", 10.0 + i) for i in range(n)]
    t, r = corre([fila(codigo=f"C{i}", importe=10.0 + i) for i in range(n)], deps)
    assert (r["resultado"], r["filas_validas"]) == ("OK", str(n))
    assert [op for op, _ in t.llamadas].count("HttpRequest") == 1 and len(t.consultas) == 1


def test_21_la_prevalidacion_NO_modifica_Depositos_Activos():
    deps = [deposito(101, "BNB", "3000100152", "A", 100.0), deposito(102, "BNB", "3000100152", "B", 5.0, estado="ASIGNADO")]
    t, r = corre([fila(codigo="A"), fila(codigo="B", importe=5.0), fila(codigo="X")], deps)
    assert t.depositos == t.depositos_iniciales                                  # ni un campo cambió
    assert {op for op, _ in t.llamadas} <= {"CreateFile", "GetItems", "HttpRequest", "DeleteFile"}
    assert len(t.consultas) == 1                                                  # un único GET (el simulador rechaza cualquier otro método)


def test_21b_el_simulador_de_SharePoint_rechaza_escrituras_si_el_flujo_las_intentara():
    t = TenantSimulado(depositos=[D1])
    with pytest.raises(AssertionError):
        t._depositos({"dataset": F.SITIO, "parameters/method": "POST", "parameters/uri": "x", "parameters/headers": {}})
    with pytest.raises(AssertionError):
        t._depositos({"dataset": F.SITIO, "parameters/method": "GET", "parameters/uri": "_api/web/lists(guid'x')/items(1)",
                      "parameters/headers": {"Accept": "application/json;odata=verbose"}})


# ====================================================================== contrato de la respuesta y de detalle_json
def esquema():
    return json.loads((Path(PV.__file__).parent / "esquema_detalle_json.json").read_text(encoding="utf-8"))


def valida(valor, sch, donde="raiz"):
    """Validador mínimo del subconjunto de JSON Schema que usa esquema_detalle_json.json (sin dependencias externas)."""
    tipos = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "null": type(None)}
    permitidos = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
    assert any(isinstance(valor, tipos[t]) and not (t in ("integer", "number") and isinstance(valor, bool)) for t in permitidos), (donde, valor)
    if "enum" in sch:
        assert valor in sch["enum"], (donde, valor)
    if isinstance(valor, dict):
        assert set(sch.get("required", [])) <= set(valor), (donde, set(sch["required"]) - set(valor))
        if sch.get("additionalProperties") is False:
            assert set(valor) <= set(sch["properties"]), (donde, set(valor) - set(sch["properties"]))
        for k, v in valor.items():
            valida(v, sch["properties"][k], f"{donde}.{k}")
    if isinstance(valor, list):
        for i, v in enumerate(valor):
            valida(v, sch["items"], f"{donde}[{i}]")


def escenario_completo():
    deps = [deposito(101, "BNB", "3000100152", "A", 100.0), deposito(102, "BNB", "3000100152", "B", 200.0, estado="ASIGNADO"),
            deposito(103, "BNB", "3000100152", "C", 300.0, moneda="USD"), deposito(104, "BNB", "3000100152", "D", 400.0),
            deposito(105, "BNB", "3000100152", "D", 400.0)]
    filas = [fila(codigo="A", importe=100.0), fila(codigo="B", importe=200.0), fila(codigo="C", importe=300.0), fila(codigo="D", importe=400.0),
             fila(codigo="ZZ"), fila(codigo="E", importe="x"), fila(codigo="F", moneda="EUR"), fila(codigo="G", sede=""),
             fila(codigo="H"), fila(codigo="H")]
    return filas, deps


def test_22_detalle_json_es_texto_JSON_valido_y_cumple_el_esquema_para_todos_los_resultados():
    filas, deps = escenario_completo()
    t, r = corre(filas, deps)
    assert isinstance(r["detalle_json"], str)
    datos = json.loads(r["detalle_json"])
    valida(datos, esquema())
    assert {d["resultado"] for d in datos} == set(PV.RESULTADOS_FILA)           # los 9 estados aparecen en este escenario
    assert len(datos) == int(r["filas_totales"]) == int(r["filas_validas"]) + int(r["filas_con_error"])
    assert list(datos[0]) == list(PV.DETALLE_CAMPOS)                            # mismo orden de campos que el contrato


def test_22b_todas_las_salidas_son_texto_y_las_8_originales_se_conservan():
    t, r = corre([fila()], [D1])
    assert all(isinstance(v, str) for v in r.values()) and list(r) == list(F.SALIDAS_RESPUESTA)
    assert r["tabla_encontrada"] == "SI" and r["archivo"] == "prevalidar.xlsx" and r["filas_leidas"] == "1"


def test_22c_el_resultado_global_solo_es_OK_OBSERVADO_o_ERROR():
    filas, deps = escenario_completo()
    for f, d, esperado in (([fila()], [D1], "OK"), (filas, deps, "OBSERVADO"), ([fila()], [], "OBSERVADO")):
        assert corre(f, d)[1]["resultado"] == esperado
    assert F.RESULTADOS_GLOBALES == ("OK", "OBSERVADO", "ERROR")


# ====================================================================== cruce con el ORÁCULO independiente
def generar_caso(rng):
    bancos = [("BNB", "3000100152"), ("BCP", "301-5005684-3-97"), ("BISA", "0696870039"), ("BANCO UNIÓN", "10000003224552")]
    deps, filas = [], []
    for i in range(rng.randint(3, 14)):
        b, c = rng.choice(bancos)
        deps.append(deposito(200 + i, b, c, rng.choice(["001234", "1234", "AB-1", "ab-1", "X9", "0007"]),
                             rng.choice([10.0, 10.01, 99.99, 100.0, 250.5, 1000.0]), moneda=rng.choice(["BOB", "USD"]),
                             estado=rng.choice(["DISPONIBLE", "DISPONIBLE", "ASIGNADO", "OTRO"]),
                             fecha=rng.choice(["2026-10-01", "2026-09-01", "2026-08-05", "2026-08-04", "2026-10-06", "2026-07-01"]),
                             tipo=rng.choice(["CRÉDITO", "CRÉDITO", "CRÉDITO", "DÉBITO"])))
    for _ in range(rng.randint(1, 12)):
        if rng.random() < 0.12:
            filas.append(None)
            continue
        base = rng.choice(deps)
        f = {"BANCO": base["BANCO"], "CUENTA_BANCARIA": base["CUENTA_BANCARIA"], "CODIGO_ASIGNACION": base["CODIGO_ASIGNACION"],
             "IMPORTE": base["IMPORTE"], "MONEDA": base["MONEDA"], "ESTUDIANTE": "E", "SOLICITADO_POR": "S", "SEDE": "COCHABAMBA", "OBSERVACION": ""}
        for _ in range(rng.choice([0, 0, 1, 1, 2])):
            campo = rng.choice(list(f))
            f[campo] = rng.choice({
                "BANCO": ["", " bnb ", "XX", "banco unión"], "CUENTA_BANCARIA": ["", "000", "0696870039"],
                "CODIGO_ASIGNACION": ["", "ab-1", "AB-1 ", "1234", "001234"], "IMPORTE": ["", "x", "0", 10.0, 100.0, "99.99", "1.234", -1],
                "MONEDA": ["", "EUR", "bob", "USD", "BOB"], "ESTUDIANTE": ["", "   "], "SOLICITADO_POR": [""], "SEDE": ["", None],
                "OBSERVACION": ["", "nota"]}[campo])
        filas.append(f)
    return filas, deps


@pytest.mark.parametrize("semilla", range(40))
def test_23_el_flujo_coincide_fila_a_fila_con_el_oraculo_en_escenarios_aleatorios(semilla):
    filas, deps = generar_caso(random.Random(semilla))
    tuplas = [None if f is None else tuple(f[h] for h in P.ENCABEZADOS) for f in filas]
    t, r = corre(tuplas, deps)
    esperado = O.prevalidar(filas, deps, HOY)
    obtenido = [{k: d[k] for k in ("fila_tabla", "fila_excel", "resultado", "coincidencias", "deposito_id", "estado_actual")} for d in detalle(r)]
    assert obtenido == esperado, (semilla, [x["resultado"] for x in obtenido], [x["resultado"] for x in esperado])
    assert t.depositos == t.depositos_iniciales


# ====================================================================== atado a las fuentes REALES del repositorio (solo lectura)
REPO = Path(__file__).resolve().parents[2]


def test_24_los_internal_names_son_los_del_esquema_real_de_Depositos_Activos():
    esquema = json.loads((REPO / "p8" / "esquema_listas_p8.json").read_text(encoding="utf-8"))["Depositos_Activos"]["columnas"]
    tecnicos = {c["nombre_tecnico"] for c in esquema}
    assert set(PV.COLUMNAS_DEPOSITO[1:]) <= tecnicos and "TIPO_MOVIMIENTO" in tecnicos          # todas existen con ese nombre exacto
    assert PV.COLUMNAS_DEPOSITO[0] == "Id"
    v42 = (REPO / "p9" / "asignar" / "flujo_asignar_powerapps_v4_2_definition.json").read_text(encoding="utf-8")
    assert "$select=Id,CLAVE_TRANSACCION,ESTADO_ASIGNACION" in v42                              # Id / CLAVE_TRANSACCION / ESTADO_ASIGNACION: V4.2
    assert PV.LISTA_DEPOSITOS_ID in v42 and F.SITIO in v42                                      # misma lista y mismo sitio que V4.2
    opcion = next(c for c in esquema if c["nombre_tecnico"] == "ESTADO_ASIGNACION")
    assert opcion["tipo"] == "Opcion" and PV.ESTADO_DISPONIBLE in opcion["valores"]
    importe = next(c for c in esquema if c["nombre_tecnico"] == "IMPORTE")
    assert importe["tipo"] == "Numero, 2 decimales"                                             # de ahí el entero de centavos


def test_25_el_universo_es_la_regla_exacta_de_la_galeria_individual_de_P9():
    galeria = (REPO / "p9" / "reversion" / "powerapps" / "Main_Screen.yaml").read_text(encoding="utf-8")
    assert f'TIPO_MOVIMIENTO = "{PV.TIPO_CREDITO}"' in galeria and PV.TIPO_CREDITO == "CRÉDITO"
    assert f"FECHA_MOVIMIENTO >= DateAdd(Today(), -{PV.MESES_VENTANA}, TimeUnit.Months)" in galeria and PV.MESES_VENTANA == 2
    assert "FECHA_MOVIMIENTO <= Today()" in galeria
    assert "CRÉDITO" in (REPO / "DISENO_LISTA_DEPOSITOS_ACTIVOS.md").read_text(encoding="utf-8")


def test_26_la_prevalidacion_no_comparte_codigo_ni_estado_con_la_confirmacion_individual():
    for ruta in ("p9/asignar/flujo_asignar_powerapps_v4_2_definition.json", "p9/reversion/powerapps/Main_Screen.yaml"):
        assert (REPO / ruta).exists()
    salida = __import__("subprocess").run(["git", "status", "--porcelain", "--", ":!proto_masiva"], cwd=REPO, capture_output=True, text=True).stdout
    assert salida.strip() == ""                                                                 # ni V4.2, ni reversión, ni PDF, ni Main_Screen se tocaron


# ====================================================================== artefactos generados: no se desfasan
def test_27_los_ejemplos_de_respuesta_versionados_son_la_salida_actual_del_flujo():
    import ejemplos_respuesta as E
    versionados = {r.name for r in E.DESTINO.glob("*.json")}
    esperados = E.ejemplos()
    assert versionados == set(esperados)
    for nombre, contenido in esperados.items():
        assert json.loads((E.DESTINO / nombre).read_text(encoding="utf-8")) == contenido, nombre
        assert all(isinstance(v, str) for v in contenido["respuesta"].values()) and list(contenido["respuesta"]) == list(F.SALIDAS_RESPUESTA)
        valida(json.loads(contenido["respuesta"]["detalle_json"]), esquema())               # y todos cumplen el esquema


def test_28_el_esquema_de_detalle_json_declara_exactamente_los_campos_del_contrato():
    sch = esquema()
    assert list(sch["items"]["properties"]) == list(PV.DETALLE_CAMPOS) and sch["items"]["required"] == list(PV.DETALLE_CAMPOS)
    assert sch["items"]["properties"]["resultado"]["enum"] == list(PV.RESULTADOS_FILA) and len(PV.RESULTADOS_FILA) == 9
    assert sch["items"]["additionalProperties"] is False


def test_29_la_guia_manual_y_las_formulas_de_power_apps_son_la_salida_actual_del_generador():
    import importlib.util
    for ruta, nombre, doc in (("proto_masiva/flows/guia_manual.py", "guia_manual", "proto_masiva/flows/GUIA_ACCIONES_PREVALIDACION.md"),
                              ("proto_masiva/powerapps/generar_powerfx.py", "generar_powerfx", "proto_masiva/powerapps/PREVALIDACION_POWERFX.md")):
        spec = importlib.util.spec_from_file_location(nombre, REPO / ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        assert (REPO / doc).read_text(encoding="utf-8") == modulo.documento(), doc


def test_30_la_guia_manual_cubre_todas_las_acciones_nuevas_del_flujo():
    guia = (REPO / "proto_masiva/flows/GUIA_ACCIONES_PREVALIDACION.md").read_text(encoding="utf-8")
    from p9.wdl import recorrer
    d = F.construir_definicion()
    nuevas = [n for n, a in recorrer(d["actions"]) if n in dict(recorrer(PV.prevalidar_filas({"X": {"type": "Compose", "inputs": 1, "runAfter": {}}})))]
    assert len(nuevas) >= 30
    for nombre in nuevas:
        if nombre != "X":
            assert f"`{nombre}`" in guia, nombre
    for salida in F.SALIDAS_NUEVAS:
        assert f"`{salida}`" in guia


def test_31_conversion_a_sintaxis_regional_respeta_los_textos_y_separa_sentencias():
    from importlib import util
    spec = util.spec_from_file_location("generar_powerfx", REPO / "proto_masiva/powerapps/generar_powerfx.py")
    m = util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.regional('Set(a, 1); Set(b, "x, y; z")') == 'Set(a; 1);; Set(b; "x, y; z")'
    assert m.regional('If(a, {x: 1, y: "a""b,c"}, 2)') == 'If(a; {x: 1; y: "a""b,c"}; 2)'


def test_32_las_formulas_regionales_estan_balanceadas_y_usan_solo_columnas_del_esquema():
    from importlib import util
    spec = util.spec_from_file_location("generar_powerfx", REPO / "proto_masiva/powerapps/generar_powerfx.py")
    m = util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for nombre, propiedad, _ in m.CAMBIOS:
        f = m.regional(m.formula(nombre, propiedad))
        limpio = re.sub(r'"(?:[^"]|"")*"', '""', f)
        assert limpio.count("(") == limpio.count(")") and limpio.count("{") == limpio.count("}"), nombre
        assert "," not in limpio.replace(" ", "") or nombre == "lblEstadoP9", nombre             # nada quedó con separador de argumentos canónico
        assert not re.search(r"Patch\(|SubmitForm|Collect\((?!\s*colPrevalidacionP9)|Depositos_Activos", limpio), nombre
    campos = set(re.findall(r"ThisRecord\.Value\.(\w+)", m.formula("btnPrevalidarP9", "OnSelect")))
    assert campos == set(PV.DETALLE_CAMPOS)


# ====================================================================== límite de negocio: máximo 1999 filas, sin lectura parcial silenciosa
def _n_filas(n):
    return [fila(codigo=f"LIM-{i:05d}", importe=10.0 + (i % 50)) for i in range(1, n + 1)]


def test_33_1999_filas_se_prevalidan_completas():
    t, e = procesar("limite.xlsx", xlsx_con_filas(_n_filas(1999)), tenant=TenantSimulado(depositos=[]))
    r = e.respuesta
    assert (r["resultado"], r["codigo"], r["filas_totales"]) == ("OBSERVADO", "PREVALIDACION_CON_ERRORES", "1999")  # sin depósitos: todas NO_ENCONTRADO
    assert len(json.loads(r["detalle_json"])) == 1999 and r["filas_leidas"] == "1999"


def test_33b_2000_filas_o_mas_se_rechaza_el_archivo_completo_con_mensaje_claro():
    for n in (2000, 2001):
        t, e = procesar("limite.xlsx", xlsx_con_filas(_n_filas(n)), tenant=TenantSimulado(depositos=[D1]))
        r = e.respuesta
        assert (r["resultado"], r["codigo"]) == ("ERROR", "DEMASIADAS_FILAS")
        assert r["mensaje"] == "El archivo tiene 2000 filas o más y el máximo permitido es 1999. No se procesó ninguna fila: divida el archivo en partes más pequeñas."
        assert r["detalle_json"] == "[]" and (r["filas_totales"], r["filas_validas"]) == ("0", "0")
        assert t.consultas == []                                  # ni siquiera se consulta Depositos_Activos: no hay lectura parcial silenciosa
