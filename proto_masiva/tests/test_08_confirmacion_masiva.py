"""CONFIRMACIÓN MASIVA (P9_MASIVA_PROTO_CONFIRMAR) contra una lista Depositos_Activos SIMULADA con ETags reales.

[VALIDADO LOCALMENTE] = el flujo generado, interpretado por el intérprete WDL local, produce este resultado y estas llamadas con un SharePoint
falso. NO prueba el runtime de Power Automate ni el comportamiento real de SharePoint (412, ETag, límites): ver CONFIRMACION_MASIVA.md §9.
"""
import json
import re
from pathlib import Path

import pytest

import simulador_confirmacion as SC
from proto_masiva.flows import construir_confirmar as K
from proto_masiva.flows import prevalidacion as PV
from simulador_confirmacion import TenantConfirmacion, confirmar, deposito, detalle, fila_validada

REPO = Path(__file__).resolve().parents[2]


def con(depositos):
    t = TenantConfirmacion(depositos)
    return t, [fila_validada(d) for d in depositos]


def resultados(r):
    return [d["resultado"] for d in detalle(r)]


def una_fila_con_cambio(**cambio_en_deposito):
    """El depósito CAMBIÓ en SharePoint después de la prevalidación; la fila que envía la app sigue siendo la de entonces."""
    original = deposito(1)
    t = TenantConfirmacion([{**original, **cambio_en_deposito}])
    r = confirmar([fila_validada(original)], t)
    return t, r, detalle(r)[0]


# ====================================================================== 1-2 · confirmar
def test_01_una_fila_valida_se_confirma_con_los_8_campos_de_V42():
    t, filas = con([deposito(1)])
    r = confirmar([{**filas[0], "observacion": "NOTA"}], t)
    assert (r["resultado"], r["codigo"], r["filas_recibidas"], r["filas_confirmadas"], r["filas_no_confirmadas"]) == \
        ("OK", "CONFIRMACION_OK", "1", "1", "0")
    assert r["mensaje"] == "1 de 1 depósitos confirmados."
    d = detalle(r)[0]
    assert (d["fila_excel"], d["deposito_id"], d["resultado"], d["estado_final"]) == (6, 1, "CONFIRMADO", "ASIGNADO")
    fila = t.filas[1]
    assert (fila["ESTADO_ASIGNACION"], fila["ESTUDIANTE"], fila["SOLICITADO_POR"], fila["SEDE_ASIGNACION"], fila["OBSERVACION"],
            fila["USUARIO_ASIGNACION"]) == ("ASIGNADO", "ESTUDIANTE 1", "SOLICITANTE", "COCHABAMBA", "NOTA", SC.USUARIO)
    assert re.fullmatch(r"2026-10-05T12:00:00\.\d+Z", fila["FECHA_HORA_ASIGNACION"])  # utcNow(), como V4.2


def test_02_varias_validas_se_confirman_todas_una_detras_de_otra():
    t, filas = con([deposito(i, codigo=f"C{i}", importe=10.0 * i) for i in range(1, 8)])
    r = confirmar(filas, t)
    assert (r["resultado"], r["filas_confirmadas"]) == ("OK", "7") and resultados(r) == ["CONFIRMADO"] * 7
    assert all(t.filas[i]["ESTADO_ASIGNACION"] == "ASIGNADO" for i in range(1, 8))
    # secuencial: GET, POST, GET, POST... (nunca dos lecturas seguidas ni un POST sin su propia lectura inmediata)
    assert [m for m, _, _ in t.llamadas] == ["GET", "POST"] * 7 and [i for _, i, _ in t.llamadas] == [x for i in range(1, 8) for x in (i, i)]


# ====================================================================== 3-9 · lo que cambió entre PREVALIDAR y CONFIRMAR
def test_03_si_el_deposito_paso_a_ASIGNADO_es_NO_DISPONIBLE_y_no_se_escribe():
    t, r, d = una_fila_con_cambio(ESTADO_ASIGNACION="ASIGNADO", USUARIO_ASIGNACION="otro@univalle.edu")
    assert (d["resultado"], d["estado_final"]) == ("NO_DISPONIBLE", "ASIGNADO") and "ASIGNADO" in d["mensaje"]
    assert t.escrituras == [] and t.campos_cambiados(1) == set()
    assert (r["resultado"], r["codigo"], r["filas_confirmadas"]) == ("PARCIAL", "NINGUNA_CONFIRMADA", "0")


@pytest.mark.parametrize("estado", ["EN_REVISION", "", "CONFIRMADO"])
def test_03b_cualquier_estado_distinto_de_DISPONIBLE_es_NO_DISPONIBLE_con_su_estado_real(estado):
    t, r, d = una_fila_con_cambio(ESTADO_ASIGNACION=estado)
    assert (d["resultado"], d["estado_final"]) == ("NO_DISPONIBLE", estado) and t.escrituras == []


@pytest.mark.parametrize("campo,valor", [("CLAVE_TRANSACCION", "OTRA-CLAVE"), ("BANCO", "BCP"), ("CUENTA_BANCARIA", "3400041236"),
                                         ("CODIGO_ASIGNACION", "OTRO-COD"), ("IMPORTE", 100.01), ("MONEDA", "USD"),
                                         ("TIPO_MOVIMIENTO", "DÉBITO"), ("FECHA_MOVIMIENTO", "2026-06-01")])
def test_04_a_09_si_cambia_un_dato_relevante_es_CONFLICTO_DATOS_y_no_se_escribe(campo, valor):
    t, r, d = una_fila_con_cambio(**{campo: valor})
    assert d["resultado"] == "CONFLICTO_DATOS" and campo in d["mensaje"]
    assert t.escrituras == [] and t.campos_cambiados(1) == set()


@pytest.mark.parametrize("campo,valor", [("BANCO", "bnb "), ("CUENTA_BANCARIA", " 3000100152"), ("CODIGO_ASIGNACION", "cod-0001"),
                                         ("MONEDA", "bob"), ("IMPORTE", 100)])
def test_09b_mayusculas_y_espacios_no_son_un_cambio_real(campo, valor):
    t, r, d = una_fila_con_cambio(**{campo: valor})
    assert d["resultado"] == "CONFIRMADO"


@pytest.mark.parametrize("fecha,esperado", [("2026-08-05", "CONFIRMADO"), ("2026-10-05", "CONFIRMADO"), ("2026-08-04", "CONFLICTO_DATOS"),
                                            ("2026-10-06", "CONFLICTO_DATOS")])
def test_09c_la_fecha_sigue_dentro_de_la_ventana_de_los_ultimos_2_meses_de_P9(fecha, esperado):
    t, r, d = una_fila_con_cambio(FECHA_MOVIMIENTO=fecha)
    assert d["resultado"] == esperado


def test_09d_el_orden_clave_estado_resto():
    # cambia la CLAVE y además está ASIGNADO: otro depósito distinto -> CONFLICTO_DATOS; solo ASIGNADO -> NO_DISPONIBLE
    assert una_fila_con_cambio(CLAVE_TRANSACCION="X", ESTADO_ASIGNACION="ASIGNADO")[2]["resultado"] == "CONFLICTO_DATOS"
    assert una_fila_con_cambio(ESTADO_ASIGNACION="ASIGNADO", IMPORTE=1.0)[2]["resultado"] == "NO_DISPONIBLE"


# ====================================================================== 10 · no existe
def test_10_si_el_deposito_ya_no_existe_es_NO_ENCONTRADO():
    t = TenantConfirmacion([deposito(1)])
    r = confirmar([fila_validada(deposito(1)), fila_validada(deposito(99))], t)
    assert resultados(r) == ["CONFIRMADO", "NO_ENCONTRADO"] and "ya no existe" in detalle(r)[1]["mensaje"]
    assert [e["id"] for e in t.escrituras] == [1]  # y la fila 1 sí se confirmó


# ====================================================================== 11 · carrera: 412
def test_11_si_otro_usuario_modifica_el_deposito_entre_la_lectura_y_el_MERGE_el_412_es_CONFLICTO():
    t, filas = con([deposito(1)])
    t.carreras[1] = {"DESCRIPCION": "editado por otro usuario"}  # cualquier cambio sube el ETag justo antes de nuestro MERGE
    r = confirmar(filas, t)
    d = detalle(r)[0]
    assert d["resultado"] == "CONFLICTO" and "Otro usuario modificó" in d["mensaje"] and d["estado_final"] == ""
    assert len(t.escrituras) == 1                                   # UN solo intento: sin reintentos
    assert t.escrituras[0]["etag_enviado"] != t.escrituras[0]["etag_vigente"]
    assert t.filas[1]["ESTADO_ASIGNACION"] == "DISPONIBLE" and t.filas[1]["USUARIO_ASIGNACION"] is None  # nuestra confirmación NO se aplicó


def test_11b_el_ETag_es_el_de_ESTA_lectura_no_uno_viejo_ni_el_de_la_prevalidacion():
    t, filas = con([deposito(1), deposito(2)])
    t.etags[1], t.etags[2] = 41, 77                                 # ETags cualesquiera: el flujo usa el que acaba de leer
    confirmar(filas, t)
    assert [(e["id"], e["etag_enviado"]) for e in t.escrituras] == [(1, '"41"'), (2, '"77"')]
    assert all(e["etag_enviado"] == e["etag_vigente"] for e in t.escrituras)


def test_11c_un_412_inyectado_tambien_es_CONFLICTO():
    t, filas = con([deposito(1)])
    t.fallos_escritura[1] = ("Failed", 412)
    assert detalle(confirmar(filas, t))[0]["resultado"] == "CONFLICTO"


# ====================================================================== 12 · errores técnicos por fila
@pytest.mark.parametrize("donde,http,mensaje", [("fallos_lectura", 500, "No se pudo leer el depósito (HTTP 500)"),
                                                ("fallos_lectura", 429, "No se pudo leer el depósito (HTTP 429)"),
                                                ("fallos_escritura", 500, "No se pudo confirmar el depósito (HTTP 500)"),
                                                ("fallos_escritura", 429, "No se pudo confirmar el depósito (HTTP 429)"),
                                                ("fallos_escritura", 403, "No se pudo confirmar el depósito (HTTP 403)")])
def test_12_un_error_tecnico_en_una_fila_es_ERROR_FILA_y_el_flujo_continua_con_las_demas(donde, http, mensaje):
    t, filas = con([deposito(1, codigo="A"), deposito(2, codigo="B"), deposito(3, codigo="C")])
    getattr(t, donde)[2] = ("Failed", http)
    r = confirmar(filas, t)
    assert resultados(r) == ["CONFIRMADO", "ERROR_FILA", "CONFIRMADO"]
    assert mensaje in detalle(r)[1]["mensaje"]
    # tras un intento de escritura fallido no se sabe si SharePoint la aplicó: se dice, no se supone
    assert detalle(r)[1]["estado_final"] == ("DESCONOCIDO" if donde == "fallos_escritura" else "")
    assert (r["resultado"], r["codigo"], r["filas_confirmadas"], r["filas_no_confirmadas"]) == ("PARCIAL", "CONFIRMACION_PARCIAL", "2", "1")
    assert t.filas[1]["ESTADO_ASIGNACION"] == t.filas[3]["ESTADO_ASIGNACION"] == "ASIGNADO"   # las demás siguieron y NO se revirtieron


# ====================================================================== 13 · lote mixto y 20 · sin rollback
def test_13_lote_mixto_confirmado_no_disponible_y_conflicto():
    deps = [deposito(1, codigo="A"), deposito(2, codigo="B", estado="ASIGNADO"), deposito(3, codigo="C"), deposito(4, codigo="D")]
    t = TenantConfirmacion(deps)
    filas = [fila_validada(deposito(1, codigo="A")), fila_validada(deposito(2, codigo="B")), fila_validada(deposito(3, codigo="C")),
             fila_validada(deposito(4, codigo="D", importe=999.0))]
    t.carreras[3] = {"DESCRIPCION": "otro usuario"}
    r = confirmar(filas, t)
    assert resultados(r) == ["CONFIRMADO", "NO_DISPONIBLE", "CONFLICTO", "CONFLICTO_DATOS"]
    assert (r["resultado"], r["codigo"], r["filas_recibidas"], r["filas_confirmadas"], r["filas_no_confirmadas"]) == \
        ("PARCIAL", "CONFIRMACION_PARCIAL", "4", "1", "3")
    assert r["mensaje"] == "1 de 4 depósitos confirmados; 3 requieren revisión."


def test_20_sin_rollback_global_47_confirmadas_2_conflictos_1_no_disponible():
    deps = [deposito(i, codigo=f"C{i}", importe=10.0 + i) for i in range(1, 51)]
    t = TenantConfirmacion(deps)
    filas = [fila_validada(d) for d in deps]
    t.filas[10]["ESTADO_ASIGNACION"] = "ASIGNADO"                   # lo asignó otro usuario
    t.carreras[20] = {"DESCRIPCION": "x"}                          # dos conflictos de concurrencia
    t.carreras[30] = {"DESCRIPCION": "y"}
    r = confirmar(filas, t)
    assert (r["resultado"], r["filas_recibidas"], r["filas_confirmadas"], r["filas_no_confirmadas"]) == ("PARCIAL", "50", "47", "3")
    assert sorted(set(resultados(r))) == ["CONFIRMADO", "CONFLICTO", "NO_DISPONIBLE"]
    assert resultados(r).count("CONFIRMADO") == 47 and resultados(r).count("CONFLICTO") == 2 and resultados(r).count("NO_DISPONIBLE") == 1
    confirmadas = [i for i in range(1, 51) if t.filas[i]["ESTADO_ASIGNACION"] == "ASIGNADO" and t.filas[i]["USUARIO_ASIGNACION"] == SC.USUARIO]
    assert len(confirmadas) == 47                                  # las 47 PERMANECEN confirmadas
    assert not [e for e in t.escrituras if e["body"].get("ESTADO_ASIGNACION") != "ASIGNADO"]  # ninguna escritura de reversión (volver a DISPONIBLE)


# ====================================================================== 14-19 · la escritura es la de V4.2
def v42():
    d = json.loads((REPO / "p9/asignar/flujo_asignar_powerapps_v4_2_definition.json").read_text(encoding="utf-8"))
    return d["actions"]["TRY"]["actions"]["Entrada_valida"]["actions"]["Clave_coincide"]["actions"]["Estado_disponible"]["actions"]["Con_ETag"]["actions"]


def test_14_codigo_estudiante_se_escribe_como_cadena_vacia():
    t, filas = con([deposito(1)])
    confirmar(filas, t)
    assert t.escrituras[0]["body"]["CODIGO_ESTUDIANTE"] == "" and t.filas[1]["CODIGO_ESTUDIANTE"] == ""


@pytest.mark.parametrize("observacion,esperado", [("", ""), (None, ""), ("   ", ""), ("  con espacios  ", "con espacios")])
def test_15_observacion_vacia_se_escribe_como_cadena_vacia_nunca_null(observacion, esperado):
    t, filas = con([deposito(1)])
    confirmar([{**filas[0], "observacion": observacion}], t)
    assert t.escrituras[0]["body"]["OBSERVACION"] == esperado and t.escrituras[0]["body"]["OBSERVACION"] is not None


def test_16_escribe_exactamente_los_mismos_8_campos_que_V42_en_el_mismo_orden():
    campos_v42 = list(v42()["Cuerpo_actualizacion"]["inputs"])
    assert campos_v42 == list(K.CAMPOS_ESCRITOS) and len(campos_v42) == 8
    t, filas = con([deposito(1)])
    confirmar(filas, t)
    assert list(t.escrituras[0]["body"]) == campos_v42
    assert t.escrituras[0]["body"]["ESTADO_ASIGNACION"] == v42()["Cuerpo_actualizacion"]["inputs"]["ESTADO_ASIGNACION"] == "ASIGNADO"


def test_16b_la_llamada_es_la_de_V42_mismo_metodo_cabeceras_y_URI():
    esc = v42()["Actualizar_deposito"]["inputs"]
    def accion_de(nombre):
        from p9.wdl import recorrer
        return dict(recorrer(K.construir_definicion()["actions"]))[nombre]
    mia = accion_de("Actualizar_deposito")["inputs"]
    assert mia["host"] == esc["host"] and mia["authentication"] == esc["authentication"]
    pm, pv = mia["parameters"], esc["parameters"]
    assert pm["parameters/method"] == pv["parameters/method"] == "POST" and set(pm["parameters/headers"]) == set(pv["parameters/headers"])
    assert {k: v for k, v in pm["parameters/headers"].items() if k != "IF-MATCH"} == {k: v for k, v in pv["parameters/headers"].items() if k != "IF-MATCH"}
    assert pm["parameters/body"] == pv["parameters/body"] == "@string(outputs('Cuerpo_actualizacion'))"
    assert pm["parameters/uri"].replace("items('Para_cada_fila')?['id_txt']", "ID") == pv["parameters/uri"].replace("string(outputs('Entrada')?['id'])", "ID")
    assert pm["parameters/uri"].startswith("@concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),")
    assert K.SITIO == json.loads((REPO / "p9/asignar/flujo_asignar_powerapps_v4_2_definition.json").read_text(encoding="utf-8"))["actions"]["PARAM_SITIO_SHAREPOINT"]["inputs"]
    assert K.LISTA_ID == PV.LISTA_DEPOSITOS_ID


def test_17_ningun_otro_campo_de_Depositos_Activos_cambia():
    deps = [deposito(1), deposito(2, estado="ASIGNADO"), deposito(3)]
    t = TenantConfirmacion(deps)
    confirmar([fila_validada(d) for d in deps], t)
    assert t.campos_cambiados(1) <= set(K.CAMPOS_ESCRITOS) and t.campos_cambiados(3) <= set(K.CAMPOS_ESCRITOS)
    assert t.campos_cambiados(2) == set()                           # el ASIGNADO no se tocó en absoluto
    for i in (1, 3):
        for c in ("CLAVE_TRANSACCION", "BANCO", "CUENTA_BANCARIA", "CODIGO_ASIGNACION", "IMPORTE", "MONEDA", "FECHA_MOVIMIENTO", "TIPO_MOVIMIENTO",
                  "DESCRIPCION", "SALDO", "LOTE_CARGA", "MOTOR_ESTADO", "HORA_MOVIMIENTO"):
            assert t.filas[i][c] == t.iniciales[i][c], c


def test_18_el_MERGE_no_tiene_reintentos_y_cada_intento_es_unico():
    from p9.wdl import recorrer
    acciones = dict(recorrer(K.construir_definicion()["actions"]))
    assert acciones["Actualizar_deposito"]["inputs"]["retryPolicy"] == {"type": "none"} == v42()["Actualizar_deposito"]["inputs"]["retryPolicy"]
    t, filas = con([deposito(1)])
    t.fallos_escritura[1] = ("Failed", 500)
    confirmar(filas, t)
    assert len(t.escrituras) == 1                                   # el 500 no se reintenta


def test_19_nunca_If_Match_asterisco_ni_etag_vacio():
    texto = json.dumps(K.construir_definicion(), ensure_ascii=False)
    assert "'*'" not in texto and '"*"' not in texto and "IF-MATCH" in texto
    t, filas = con([deposito(i, codigo=f"C{i}") for i in range(1, 6)])
    confirmar(filas, t)
    assert all(e["headers"]["IF-MATCH"] not in ("*", "") and e["headers"]["IF-MATCH"].startswith('"') for e in t.escrituras)
    # sin ETag en la lectura: NO se escribe (V4.2: SIN_ETAG)
    t2, filas2 = con([deposito(1)])
    orig = t2._leer
    t2._leer = lambda *a, **k: (lambda r: {**r, "headers": {}, "body": {"d": {k_: v for k_, v in r["body"]["d"].items() if k_ != "__metadata"}}})(orig(*a, **k))
    r = confirmar(filas2, t2)
    assert detalle(r)[0]["resultado"] == "ERROR_FILA" and "ETag" in detalle(r)[0]["mensaje"] and t2.escrituras == []


# ====================================================================== entrada, límites y filas inválidas
def test_21_entrada_invalida_no_toca_SharePoint():
    t = TenantConfirmacion([deposito(1)])
    for texto, usuario in (("", SC.USUARIO), ("[]x", SC.USUARIO), ("{}", SC.USUARIO), ('[{"a":1}]', ""), ("no es json", SC.USUARIO)):
        r = confirmar(None, t, usuario=usuario, texto=texto)
        assert (r["resultado"], r["codigo"]) == ("ERROR", "ENTRADA_INVALIDA") and r["detalle_json"] == "[]" and r["filas_confirmadas"] == "0", texto
    assert t.llamadas == []


def test_21b_json_roto_con_formato_de_arreglo_tambien_es_ENTRADA_INVALIDA():
    t = TenantConfirmacion([deposito(1)])
    r = confirmar(None, t, texto='[{"deposito_id": 1,')
    assert (r["resultado"], r["codigo"]) == ("ERROR", "ENTRADA_INVALIDA") and t.llamadas == []


def test_22_sin_filas_y_lote_mayor_al_maximo_por_llamada_se_rechazan_enteros_sin_confirmar_nada():
    deps = [deposito(i, codigo=f"C{i}") for i in range(1, 8)]
    t = TenantConfirmacion(deps)
    r = confirmar([], t)
    assert (r["resultado"], r["codigo"], r["filas_recibidas"]) == ("ERROR", "SIN_FILAS", "0")
    d = K.construir_definicion(max_por_llamada=5)
    r = confirmar([fila_validada(x) for x in deps], t, definicion=d)
    assert (r["resultado"], r["codigo"], r["filas_recibidas"], r["filas_confirmadas"]) == ("ERROR", "LOTE_EXCEDE_LIMITE", "7", "0")
    assert "máximo por confirmación es 5" in r["mensaje"] and t.llamadas == [] and t.escrituras == []
    assert confirmar([fila_validada(x) for x in deps[:5]], t, definicion=d)["resultado"] == "OK"   # justo en el límite


def test_22b_el_limite_de_negocio_1999_prevalece_aunque_se_suba_el_de_la_llamada():
    assert K.MAX_FILAS_ARCHIVO == 1999 and K.MAX_FILAS_POR_LLAMADA == 50
    d = K.construir_definicion(max_por_llamada=5000)
    t = TenantConfirmacion([])
    filas = [fila_validada(deposito(i)) for i in range(1, 2001)]
    r = confirmar(filas, t, definicion=d)
    assert (r["codigo"], r["filas_recibidas"]) == ("LOTE_EXCEDE_LIMITE", "2000") and "máximo por confirmación es 1999" in r["mensaje"] and t.llamadas == []


@pytest.mark.parametrize("cambio,motivo", [({"deposito_id": 0}, "ID_INVALIDO"), ({"deposito_id": "abc"}, "ID_INVALIDO"), ({"deposito_id": None}, "ID_INVALIDO"),
                                           ({"deposito_id": -3}, "ID_INVALIDO"), ({"sede": ""}, "CAMPOS_OBLIGATORIOS"),
                                           ({"estudiante": "  "}, "CAMPOS_OBLIGATORIOS"), ({"clave_transaccion": ""}, "CAMPOS_OBLIGATORIOS"),
                                           ({"solicitado_por": "x" * 256}, "CAMPO_EXCEDE_255"), ({"importe": "abc"}, "IMPORTE_INVALIDO"),
                                           ({"importe": 0}, "IMPORTE_INVALIDO"), ({"importe": 1.234}, "IMPORTE_INVALIDO"),
                                           ({"moneda": "EUR"}, "MONEDA_INVALIDA")])
def test_23_una_fila_mal_formada_es_ERROR_FILA_sin_tocar_SharePoint_y_las_demas_siguen(cambio, motivo):
    t = TenantConfirmacion([deposito(1), deposito(2, codigo="B")])
    r = confirmar([fila_validada(deposito(1), **cambio), fila_validada(deposito(2, codigo="B"))], t)
    por_fila = {d["fila_excel"]: d for d in detalle(r)}
    assert por_fila[6]["resultado"] == "ERROR_FILA" and motivo in por_fila[6]["mensaje"] and por_fila[7]["resultado"] == "CONFIRMADO"
    assert t.lecturas == [2] and t.campos_cambiados(1) == set()    # la fila mala no generó ni una llamada
    assert (r["resultado"], r["filas_recibidas"], r["filas_confirmadas"]) == ("PARCIAL", "2", "1")


def test_24_el_mismo_deposito_dos_veces_en_el_envio_no_se_confirma_dos_veces():
    t, filas = con([deposito(1)])
    r = confirmar([filas[0], {**filas[0], "fila_excel": 99}], t)
    assert resultados(r) == ["CONFIRMADO", "NO_DISPONIBLE"] and len(t.escrituras) == 1


def test_25_reenviar_el_mismo_lote_no_vuelve_a_escribir_idempotente_por_estado_y_ETag():
    deps = [deposito(i, codigo=f"C{i}") for i in range(1, 4)]
    t = TenantConfirmacion(deps)
    filas = [fila_validada(d) for d in deps]
    assert confirmar(filas, t)["resultado"] == "OK"
    escritas = len(t.escrituras)
    r2 = confirmar(filas, t)                                        # p. ej. tras un tiempo de espera de la app que el usuario reintenta
    assert resultados(r2) == ["NO_DISPONIBLE"] * 3 and len(t.escrituras) == escritas and r2["resultado"] == "PARCIAL"


def test_26_un_fallo_global_no_deshace_nada_y_el_resumen_cuenta_lo_ya_confirmado():
    t, filas = con([deposito(1)])
    r = confirmar(None, t, texto=json.dumps([1, 2]))               # elementos que no son objetos: falla fuera de las filas
    assert r["resultado"] == "ERROR" and r["codigo"] == "ERROR_NO_CONTROLADO" and "algunos depósitos pueden haberse confirmado" in r["mensaje"]
    assert (r["filas_recibidas"], r["filas_confirmadas"], r["filas_no_confirmadas"]) == ("2", "0", "2") and t.escrituras == []


# ====================================================================== contrato de respuesta
def esquema():
    return json.loads((Path(K.__file__).parent / "esquema_detalle_confirmacion_json.json").read_text(encoding="utf-8"))


def valida(valor, sch, donde="raiz"):
    tipos = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "null": type(None)}
    permitidos = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
    assert any(isinstance(valor, tipos[t]) and not (t in ("integer", "number") and isinstance(valor, bool)) for t in permitidos), (donde, valor)
    if "enum" in sch:
        assert valor in sch["enum"], (donde, valor)
    if isinstance(valor, dict):
        assert set(sch.get("required", [])) <= set(valor) and set(valor) <= set(sch["properties"]), (donde, set(valor) ^ set(sch["properties"]))
        for k, v in valor.items():
            valida(v, sch["properties"][k], f"{donde}.{k}")
    if isinstance(valor, list):
        for i, v in enumerate(valor):
            valida(v, sch["items"], f"{donde}[{i}]")


def escenario_mixto():
    deps = [deposito(1, codigo="A"), deposito(2, codigo="B", estado="ASIGNADO"), deposito(3, codigo="C"), deposito(4, codigo="D"), deposito(5, codigo="E"),
            deposito(6, codigo="F")]
    t = TenantConfirmacion(deps)
    filas = [fila_validada(deposito(1, codigo="A")), fila_validada(deposito(2, codigo="B")), fila_validada(deposito(3, codigo="C")),
             fila_validada(deposito(4, codigo="D", importe=5.0)), fila_validada(deposito(99, codigo="Z")), fila_validada(deposito(6, codigo="F"), sede="")]
    t.carreras[3] = {"DESCRIPCION": "otro"}
    return t, filas


def test_27_respuesta_8_salidas_en_texto_sin_ETag_y_detalle_conforme_al_esquema():
    t, filas = escenario_mixto()
    r = confirmar(filas, t)
    assert list(r) == list(K.SALIDAS) and all(isinstance(v, str) for v in r.values())
    datos = detalle(r)
    valida(datos, esquema())
    assert {d["resultado"] for d in datos} == set(K.RESULTADOS_FILA) and list(datos[0]) == list(K.DETALLE_CAMPOS)
    assert "etag" not in json.dumps(r).lower()                                      # el ETag nunca viaja al cliente
    assert re.fullmatch(r"total=\d+;filas=6;ms_por_fila=\d+", r["tiempos_ms"])


def test_28_resultado_global_OK_PARCIAL_o_ERROR():
    t, filas = con([deposito(1)])
    assert confirmar(filas, t)["resultado"] == "OK"
    t2, filas2 = escenario_mixto()
    assert confirmar(filas2, t2)["resultado"] == "PARCIAL"
    assert confirmar([], t)["resultado"] == "ERROR"
    assert K.RESULTADOS_GLOBALES == ("OK", "PARCIAL", "ERROR")


# ====================================================================== estructura del flujo
def test_29_el_flujo_es_solo_HttpRequest_secuencial_sin_otras_escrituras_ni_infraestructura():
    from p9.wdl import recorrer
    d = K.construir_definicion()
    acciones = dict(recorrer(d["actions"]))
    http = [(n, a["inputs"]["parameters"]["parameters/method"]) for n, a in acciones.items() if a["type"] == "OpenApiConnection"]
    assert sorted(http) == [("Actualizar_deposito", "POST"), ("Leer_deposito", "GET")]    # UNA lectura y UNA escritura por fila
    assert {a["inputs"]["host"]["operationId"] for a in acciones.values() if a["type"] == "OpenApiConnection"} == {"HttpRequest"}
    bucles = [(n, a["runtimeConfiguration"]["concurrency"]["repetitions"]) for n, a in acciones.items() if a["type"] == "Foreach"]
    assert bucles == [("Para_cada_fila", 1)]                                             # secuencial, sin concurrencia
    assert not [n for n, a in acciones.items() if a["type"] in ("Until", "Terminate", "Wait", "Delay")]
    texto = json.dumps(d, ensure_ascii=False)
    for prohibido in ("LOTE_ID", "LOTE_UID", "Lotes", "P9_MASIVA_PROTO_LOTES", "Confirmaciones_Masivas", "Depositos_Reversiones", "TIPO_CAMBIO", "CreateItem", "PostItem", "DeleteItem", "'DELETE'", "'PUT'", "'PATCH'",
                      "GetOnUpdatedItems", "Revertir", "rollback", "ROLLBACK"):
        assert prohibido not in texto, prohibido


def test_30_los_artefactos_versionados_son_la_salida_actual_del_generador():
    d = K.construir_definicion()
    assert json.loads((Path(K.__file__).parent / f"{K.NOMBRE_FLUJO}_definition.json").read_text(encoding="utf-8")) == d
    assert (Path(K.__file__).parent / f"{K.NOMBRE_FLUJO}.zip").read_bytes() == K.zip_bytes(d)
    from p9.wdl import contar_acciones
    assert contar_acciones(d["actions"]) == 61


def test_31_disparador_power_apps_v2_con_dos_entradas_de_texto_todas_requeridas():
    (nombre, t), = K.construir_definicion()["triggers"].items()
    assert (t["type"], t["kind"]) == ("Request", "PowerAppV2")
    esq = t["inputs"]["schema"]
    assert [esq["properties"][c]["title"] for c in esq["required"]] == ["detalle_json", "usuario_email"] and list(esq["properties"]) == esq["required"]
    assert all(p["type"] == "string" and p["x-ms-content-hint"] == "TEXT" for p in esq["properties"].values())


def test_32_zip_importable_con_UNA_conexion_de_SharePoint():
    import zipfile
    from io import BytesIO
    z = zipfile.ZipFile(BytesIO(K.zip_bytes(K.construir_definicion())))
    env = json.loads(z.read(next(n for n in z.namelist() if n.endswith("/definition.json"))))
    assert set(env["properties"]["connectionReferences"]) == {"shared_sharepointonline"}
    assert env["properties"]["displayName"] == "P9_MASIVA_PROTO_CONFIRMAR" == json.loads(z.read("manifest.json"))["details"]["displayName"]
    assert env["properties"]["definition"] == K.construir_definicion()
    # el ZIP de la prevalidación NO cambió de estructura (misma función de empaquetado, mismos valores por defecto)
    from proto_masiva.flows import construir as F
    assert set(json.loads(zipfile.ZipFile(BytesIO(F.zip_bytes(F.construir_definicion()))).read(
        next(n for n in zipfile.ZipFile(BytesIO(F.zip_bytes(F.construir_definicion()))).namelist() if n.endswith("/definition.json"))))["properties"]["connectionReferences"]) \
        == {"shared_sharepointonline", "shared_excelonlinebusiness"}


def test_33_no_se_toco_nada_de_produccion():
    import subprocess
    assert subprocess.run(["git", "status", "--porcelain", "--", ":!proto_masiva"], cwd=REPO, capture_output=True, text=True).stdout.strip() == ""


# ====================================================================== ejemplos
def test_34_los_ejemplos_de_respuesta_versionados_son_la_salida_actual_del_flujo():
    import ejemplos_confirmacion as E
    esperados = E.ejemplos()
    assert {r.name for r in E.DESTINO.glob("*.json")} == set(esperados)
    for nombre, contenido in esperados.items():
        assert json.loads((E.DESTINO / nombre).read_text(encoding="utf-8")) == contenido, nombre
        valida(json.loads(contenido["respuesta"]["detalle_json"]), esquema())


def test_35_el_esquema_declara_exactamente_los_campos_del_contrato():
    sch = esquema()
    assert list(sch["items"]["properties"]) == list(K.DETALLE_CAMPOS) == sch["items"]["required"]
    assert sch["items"]["properties"]["resultado"]["enum"] == list(K.RESULTADOS_FILA)


# ====================================================================== Power Fx: botón, resultado y reinicios (estáticos)
def _carga(ruta):
    import importlib.util
    spec = importlib.util.spec_from_file_location(Path(ruta).stem, REPO / ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PFX = _carga("proto_masiva/powerapps/generar_powerfx.py")


def sin_cadenas(f):
    return re.sub(r'"(?:[^"]|"")*"', '""', f)


def test_36_el_boton_llama_al_flujo_con_el_JSON_compacto_de_SOLO_las_filas_VALIDO_y_el_correo():
    f = PFX.formula("btnConfirmarMasivamenteP9", "OnSelect")
    assert f"{K.NOMBRE_FLUJO}.Run(" in f and "JSONFormat.Compact" in f and "User().Email" in f
    assert 'Filter(colPrevalidacionP9, resultado = "VALIDO")' in f                       # nunca las filas observadas
    columnas = re.search(r'ShowColumns\(Filter\(colPrevalidacionP9, resultado = "VALIDO"\), ([^)]*)\)', f)[1]
    enviadas = re.findall(r'"(\w+)"', columnas)
    assert enviadas == list(K.CAMPOS_ENTRADA) and set(enviadas) <= set(PV.DETALLE_CAMPOS)  # las 12 del contrato, todas existen en la colección
    assert "CODIGO_ESTUDIANTE" not in f and "codigo_estudiante" not in f                  # lo escribe el flujo como ""


def test_37_no_hay_segundo_modal_ni_doble_confirmacion_ni_escrituras_desde_la_app():
    texto = (REPO / "proto_masiva/powerapps/P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    for prohibido in ("varConfirmarMasivaVisible", "mostrarConfirmacion", "SubmitForm", "Patch(", "Collect(Depositos", "Refresh(", "Timer"):
        assert prohibido not in texto, prohibido
    f = PFX.formula("btnConfirmarMasivamenteP9", "OnSelect")
    assert re.findall(r"\w*Collect\(", f) == ["ClearCollect("] and f.count(".Run(") == 1  # UNA llamada al flujo por clic


def test_38_el_boton_queda_Disabled_mientras_corre_y_despues_de_confirmar_ese_resultado():
    dm = PFX.formula("btnConfirmarMasivamenteP9", "DisplayMode")
    for condicion in ("!Coalesce(varProcesandoP9, false)", "!Coalesce(varProcesandoConfirmacionP9, false)",
                      "!Coalesce(varConfirmacionMasivaFinalizadaP9, false)", 'CountRows(Filter(colPrevalidacionP9, resultado = "VALIDO")) > 0'):
        assert condicion in dm, condicion
    on = PFX.formula("btnConfirmarMasivamenteP9", "OnSelect")
    assert on.index("Set(varProcesandoConfirmacionP9, true)") < on.index(".Run(") < on.index("Set(varConfirmacionMasivaFinalizadaP9, true)") \
        < on.index("Set(varProcesandoConfirmacionP9, false)")
    assert PFX.formula("btnConfirmarMasivamenteP9", "Text") == '"CONFIRMAR MASIVAMENTE (" & CountRows(Filter(colPrevalidacionP9, resultado = "VALIDO")) & ")"'
    # tras un tiempo de espera de la app el botón también queda bloqueado: hay que volver a PREVALIDAR (el flujo pudo seguir confirmando)
    assert on.index("FLUJO_SIN_RESPUESTA") < on.index("Set(varConfirmacionMasivaFinalizadaP9, true)") and "vuelva a PREVALIDAR" in on


def test_39_se_reinicia_al_prevalidar_de_nuevo_y_al_cambiar_de_archivo():
    prev = PFX.formula("btnPrevalidarP9", "OnSelect")
    for necesario in ("Set(varResultadoConfirmacionP9, Blank())", "Set(varConfirmacionMasivaFinalizadaP9, false)", "Set(varVerObservacionesP9, false)",
                      "Clear(colConfirmacionP9)", "Clear(colPrevalidacionP9)"):
        assert necesario in prev, necesario
    assert "Coalesce(varProcesandoConfirmacionP9, false)" in PFX.formula("btnPrevalidarP9", "DisplayMode")  # no se prevalida mientras se confirma
    nuevo = PFX.REINICIO_NUEVO_ARCHIVO
    for necesario in ("Set(varConfirmacionMasivaFinalizadaP9, false)", "Clear(colPrevalidacionP9)", "Set(varResultadoP9, Blank())"):
        assert necesario in nuevo, necesario


def test_40_la_coleccion_de_confirmacion_usa_las_columnas_del_esquema_con_conversion_explicita():
    f = PFX.formula("btnConfirmarMasivamenteP9", "OnSelect")
    assert "ParseJSON(varResultadoConfirmacionP9.detalle_json)" in f
    cols = re.findall(r"^\s+(\w+): (Value|Text)\(ThisRecord\.Value\.(\w+)\)", f, re.M)
    assert [c for c, _, _ in cols] == [c for _, _, c in cols] == list(K.DETALLE_CAMPOS)
    for campo, conv, _ in cols:
        tipos = esquema()["items"]["properties"][campo]["type"]
        tipos = tipos if isinstance(tipos, list) else [tipos]
        assert conv == ("Value" if set(tipos) & {"integer", "number"} else "Text"), campo
    registro = re.search(r"Set\(\s*varResultadoConfirmacionP9,\s*\{(.*?)\}\s*\)", f, re.S)[1]
    assert re.findall(r"(\w+):", sin_cadenas(registro)) == list(K.SALIDAS)       # el resultado fabricado por la app tiene la forma de la respuesta del flujo


def test_41_el_panel_muestra_el_resultado_pedido_sin_otro_modal():
    titular = PFX.formula("lblTitularResultadoP9", "Text")
    for texto in ("CONFIRMACIÓN COMPLETADA", "CONFIRMACIÓN PARCIAL", "NO SE CONFIRMÓ NINGÚN DEPÓSITO", "depósitos confirmados.", "requieren revisión."):
        assert texto in titular, texto
    assert "filas_confirmadas" in titular and "filas_recibidas" in titular and "filas_no_confirmadas" in titular
    items = PFX.formula("galObservacionesP9", "Items")
    assert 'Filter(colConfirmacionP9, resultado <> "CONFIRMADO")' in items and 'Filter(colPrevalidacionP9, resultado <> "VALIDO")' in items  # solo las NO confirmadas
    tiempo = PFX.formula("lblResTiempoP9", "Text")
    assert "segundos" in tiempo and "tiempos_ms" not in tiempo and "ms" not in re.sub(r'"[^"]*"', "", tiempo).replace("varMs", "")  # humanizado, sin desglose técnico
    assert PFX.formula("lblResTiempoTituloP9", "Text") == '"TIEMPO DE PROCESAMIENTO"'


def test_42_las_formulas_regionales_estan_balanceadas_y_no_tocan_listas():
    for nombre, propiedad, _ in PFX.CAMBIOS_CONFIRMACION:
        f = PFX.regional(PFX.formula_de(nombre, propiedad))
        limpio = sin_cadenas(f)
        assert limpio.count("(") == limpio.count(")") and limpio.count("{") == limpio.count("}"), (nombre, propiedad)
        assert not re.search(r"Patch\(|SubmitForm|Depositos_Activos|Remove\(|RemoveIf\(|Update\(", limpio), (nombre, propiedad)


def test_43_los_documentos_generados_son_la_salida_actual_de_los_generadores():
    G = _carga("proto_masiva/flows/guia_manual.py")
    assert (REPO / "proto_masiva/powerapps/CONFIRMACION_POWERFX.md").read_text(encoding="utf-8") == PFX.documento_confirmacion()
    assert (REPO / "proto_masiva/flows/GUIA_ACCIONES_CONFIRMACION.md").read_text(encoding="utf-8") == G.documento_confirmar()
    guia = (REPO / "proto_masiva/flows/GUIA_ACCIONES_CONFIRMACION.md").read_text(encoding="utf-8")
    from p9.wdl import recorrer
    for nombre, _ in recorrer(K.construir_definicion()["actions"]):
        assert f"`{nombre}`" in guia, nombre
