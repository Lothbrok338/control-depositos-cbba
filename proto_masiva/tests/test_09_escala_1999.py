"""ESCALA hasta 1999 filas con UN clic: respuesta temprana, procesamiento en segundo plano, estado en archivo temporal y consulta de avance.

Todo contra el SharePoint SIMULADO: prueba la LÓGICA y los números de diseño (payload, solicitudes, tamaño del estado). NO mide el rendimiento del tenant:
«1999 soportado por diseño» NO significa «1999 validado en el tenant» (ver ESCALA_1999.md, clasificación DOCUMENTADO / SIMULADO / INFERIDO / PENDIENTE).
"""
import json
import re
from collections import Counter

import pytest

import simulador_confirmacion as SC
from proto_masiva.flows import construir_confirmar as K
from proto_masiva.flows import construir_estado as E
from simulador_confirmacion import TenantConfirmacion, confirmar, consultar_estado, deposito, fila_validada

LIMITE_MENSAJE = 100 * 1024 * 1024        # DOCUMENTADO (Power Automate): tamaño de mensaje 100 MB


def lote(n, *, no_disponibles=(), carreras=(), fallos_lectura=(), **extra):
    deps = [deposito(i, codigo=f"C{i}", importe=10.0 + i, **extra) for i in range(1, n + 1)]
    t = TenantConfirmacion(deps)
    for i in no_disponibles:
        t.filas[i]["ESTADO_ASIGNACION"] = "ASIGNADO"
    for i in carreras:
        t.carreras[i] = {"DESCRIPCION": "otro usuario"}
    for i in fallos_lectura:
        t.fallos_lectura[i] = ("Failed", 500)
    return t, [fila_validada(d) for d in deps]


@pytest.fixture(scope="module")
def ejecucion_1999():
    """El ejemplo pedido: 1999 recibidas -> 1978 CONFIRMADO, 12 NO_DISPONIBLE, 5 CONFLICTO, 4 ERROR_FILA."""
    t, filas = lote(1999, no_disponibles=[i * 10 for i in range(1, 13)], carreras=[i * 100 + 1 for i in range(1, 6)],
                    fallos_lectura=[i * 100 + 2 for i in range(1, 5)])
    return confirmar(filas, t), t, filas


# ====================================================================== 1 · tamaños: 1, 50, 1999 y 2000
def test_1_una_fila():
    t, filas = lote(1)
    r = confirmar(filas, t)
    assert (r["resultado"], r["filas_recibidas"]) == ("ACEPTADO", "1") and r.estado["filas_confirmadas"] == 1 and r.estado["estado"] == "TERMINADO"


def test_50_filas_el_antiguo_tope_ya_no_es_un_limite():
    t, filas = lote(50)
    r = confirmar(filas, t)
    assert r.estado["filas_confirmadas"] == 50 and r.fallidas == [] and r.estado["porcentaje"] == 100


def test_51_filas_ya_se_aceptan():
    t, filas = lote(51)
    assert confirmar(filas, t)["resultado"] == "ACEPTADO"


def test_1999_filas_con_fallos_parciales_deja_solo_las_21_no_confirmadas(ejecucion_1999):
    r, t, filas = ejecucion_1999
    assert (r["resultado"], r["codigo"], r["filas_recibidas"]) == ("ACEPTADO", "PROCESAMIENTO_INICIADO", "1999")
    e = r.estado
    assert (e["estado"], e["codigo"], e["filas_totales"], e["filas_procesadas"], e["filas_confirmadas"], e["filas_no_confirmadas"], e["porcentaje"]) == \
        ("TERMINADO", "CONFIRMACION_PARCIAL", 1999, 1999, 1978, 21, 100)
    assert e["mensaje"] == "1978 de 1999 depósitos confirmados; 21 requieren revisión."
    assert Counter(d["resultado"] for d in r.fallidas) == {"NO_DISPONIBLE": 12, "CONFLICTO": 5, "ERROR_FILA": 4} and not e["detalle_truncado"]
    # las 1978 quedan confirmadas (sin rollback) y NO se devuelven a Power Apps
    confirmadas = [i for i in range(1, 2000) if t.filas[i]["ESTADO_ASIGNACION"] == "ASIGNADO" and t.filas[i]["USUARIO_ASIGNACION"] == SC.USUARIO]
    assert len(confirmadas) == 1978 and len(r.fallidas) == 21
    assert Counter(m for m, _, _ in t.llamadas) == {"GET": 1999, "POST": 1983}      # 1 lectura por fila; 1 MERGE por fila que seguía válida (sin reintentos)


def test_2000_filas_se_rechazan_enteras_sin_tocar_nada():
    t, filas = lote(2000)
    r = confirmar(filas, t)
    assert (r["resultado"], r["codigo"], r["filas_recibidas"], r["execution_uid"]) == ("ERROR", "LOTE_EXCEDE_LIMITE", "2000", "")
    assert "máximo por confirmación es 1999" in r["mensaje"] and t.llamadas == [] and t.archivos == {} and t.llamadas_archivo == []


# ====================================================================== 2 · respuesta TEMPRANA y el backend continúa
def test_la_respuesta_a_Power_Apps_llega_antes_de_la_primera_lectura_de_un_deposito_y_con_el_estado_ya_creado():
    t, filas = lote(30)
    r = confirmar(filas, t)
    eventos = t.eventos
    i_resp = eventos.index(("respuesta", "Responder_aceptado"))
    assert eventos[:i_resp] == [("archivo", "CreateFile")]                              # antes de responder SOLO se creó el estado
    assert all(e[0] != "deposito" for e in eventos[:i_resp]) and eventos[i_resp + 1][0] == "deposito"
    assert eventos.count(("respuesta", "Responder_aceptado")) == 1 and not [e for e in eventos if e == ("respuesta", "Responder_error")]
    primera = r.versiones[0]                                                             # lo que ya existía cuando Power Apps recibió el ACEPTADO
    assert (primera["estado"], primera["filas_totales"], primera["filas_procesadas"], primera["filas_confirmadas"], primera["detalle_json"]) == \
        ("PROCESANDO", 30, 0, 0, [])
    assert r.estado["estado"] == "TERMINADO"                                             # y el flujo SIGUIÓ después de responder


def test_el_trabajo_antes_de_responder_no_depende_del_numero_de_filas():
    """El tiempo hasta la respuesta (límite documentado de 120 s) no crece con las filas: validar + contar + crear el estado."""
    def acciones_antes_de_responder(n):
        t, filas = lote(n)
        r = confirmar(filas, t)
        ev = r.ensayo.eventos
        return ev[:ev.index("Responder_aceptado")]
    assert acciones_antes_de_responder(1) == acciones_antes_de_responder(400)


def test_si_Power_Apps_se_cierra_no_cambia_nada_en_el_backend():
    """El flujo no consulta nada de Power Apps después de responder: solo escribe su estado. (DOCUMENTADO: el flujo continúa aunque se cierre la app.)"""
    d = json.dumps(K.construir_definicion())
    assert "triggerBody()" in d and d.count("triggerBody()") == 2                        # solo las dos entradas, leídas en 'Entrada' al inicio
    t, filas = lote(80)
    assert confirmar(filas, t).estado["estado"] == "TERMINADO"


# ====================================================================== 3 · estado: inicial, intermedio y final
def test_estados_PROCESANDO_intermedio_y_TERMINADO_con_avance_cada_25_filas():
    t, filas = lote(60, carreras=[7])
    r = confirmar(filas, t)
    v = r.versiones
    assert [(x["estado"], x["filas_procesadas"]) for x in v] == [("PROCESANDO", 0), ("PROCESANDO", 25), ("PROCESANDO", 50), ("TERMINADO", 60)]
    assert [x["porcentaje"] for x in v] == [0, 41, 83, 100]
    assert all(x["detalle_json"] == [] for x in v[:-1])                                 # durante el avance solo contadores (archivo pequeño)
    assert v[1]["filas_confirmadas"] + v[1]["filas_no_confirmadas"] == 25 and v[2]["filas_no_confirmadas"] == 1
    assert [d["resultado"] for d in v[-1]["detalle_json"]] == ["CONFLICTO"] and v[-1]["mensaje"] == "59 de 60 depósitos confirmados; 1 requieren revisión."
    assert all(a["filas_procesadas"] <= b["filas_procesadas"] for a, b in zip(v, v[1:]))


def test_la_cadencia_de_avance_es_configurable_y_no_es_cada_fila():
    t, filas = lote(30)
    d = K.construir_definicion(intervalo_progreso=10)
    r = confirmar(filas, t, definicion=d)
    assert [x["filas_procesadas"] for x in r.versiones] == [0, 10, 20, 30, 30]          # creación, 3 avances, final
    assert K.INTERVALO_PROGRESO == 25                                                    # por defecto: cada 25 filas (no cada fila)


def test_1999_filas_escriben_81_versiones_del_estado_y_ninguna_pasa_de_unos_KB(ejecucion_1999):
    r, t, filas = ejecucion_1999
    assert len(r.versiones) == 1 + 1999 // 25 + 1 == 81                                  # creación + 79 avances + final
    assert max(len(a["contenido"]) for a in t.archivos.values()) < 10_000
    assert [v["filas_procesadas"] for v in r.versiones][:3] == [0, 25, 50] and r.versiones[-1]["estado"] == "TERMINADO"
    # las invalidas cuentan como procesadas desde el principio; aquí no hay
    assert r.versiones[-2]["estado"] == "PROCESANDO" and r.versiones[-2]["filas_procesadas"] == 1975


def test_fila_mal_formada_cuenta_como_procesada_y_no_confirmada_desde_el_inicio():
    t, filas = lote(30)
    filas[3] = {**filas[3], "sede": ""}
    r = confirmar(filas, t)
    assert r.versiones[0]["filas_procesadas"] == 0                                       # el estado inicial se crea ANTES de validar el contenido
    assert r.estado["filas_no_confirmadas"] == 1 and r.estado["filas_procesadas"] == 30 and r.fila(3)["resultado"] == "ERROR_FILA"
    assert r.versiones[1]["filas_procesadas"] == 25 and r.versiones[1]["filas_no_confirmadas"] == 1


# ====================================================================== 4 · detalle: límite de 131.072 caracteres
def test_el_detalle_final_tiene_como_maximo_MAX_DETALLE_filas_y_lo_demas_se_cuenta():
    t, filas = lote(40, no_disponibles=range(1, 13))
    r = confirmar(filas, t, definicion=K.construir_definicion(max_detalle=5))
    e = r.estado
    assert len(e["detalle_json"]) == 5 and e["detalle_truncado"] is True and e["filas_no_confirmadas"] == 12 and e["filas_confirmadas"] == 28
    assert [d["fila_excel"] for d in e["detalle_json"]] == [6, 7, 8, 9, 10]              # las primeras, en orden


def test_el_peor_caso_realista_del_detalle_cabe_en_string_de_131072_caracteres():
    caso = {"fila_excel": 2005, "deposito_id": 123456789, "resultado": "CONFLICTO_DATOS", "mensaje": "El depósito cambió desde la prevalidación (CODIGO_ASIGNACION). No se aplicó ningún cambio.",
            "estado_final": "DESCONOCIDO", "banco": "BANCO ECONÓMICO", "cuenta_bancaria": "301-5005425-2-71", "codigo_asignacion": "COD-0000000000001", "importe": 123456.78,
            "moneda": "BOB"}
    assert list(caso) == list(K.DETALLE_CAMPOS)
    por_fila = len(json.dumps(caso, ensure_ascii=False, separators=(",", ":")))
    assert K.MAX_DETALLE * por_fila < K.LIMITE_STRING * 0.9, (por_fila, K.MAX_DETALLE * por_fila)


def test_si_el_detalle_NO_cupiera_en_string_el_estado_final_se_escribe_igualmente_con_respaldo_minimo():
    """Límite DOCUMENTADO: string() <= 131.072 caracteres. 320 filas no confirmadas con textos de 250 caracteres lo superan: la primera escritura falla."""
    larga = "X" * 250
    t, filas = lote(320, no_disponibles=range(1, 321), banco=larga, cuenta=larga)
    r = confirmar(filas, t)
    e = r.estado
    assert e["estado"] == "TERMINADO" and e["detalle_json"] == [] and e["detalle_truncado"] is True
    assert (e["filas_totales"], e["filas_confirmadas"], e["filas_no_confirmadas"], e["porcentaje"]) == (320, 0, 320, 100)
    assert "vuelva a PREVALIDAR" in e["mensaje"] and e["codigo"] == "NINGUNA_CONFIRMADA"
    assert [op for op, n in t.llamadas_archivo][-2:] == ["UpdateFile", "UpdateFile"] and "Escribir_final_minimo" in [n for _, n in t.llamadas_archivo]


def test_un_fallo_al_escribir_un_avance_no_detiene_ni_cambia_las_confirmaciones():
    t, filas = lote(60)
    t.fallos_actualizacion = {1}                                                         # falla el primer avance (25 filas)
    r = confirmar(filas, t)
    assert r.estado["filas_confirmadas"] == 60 and r.estado["estado"] == "TERMINADO" and len(t.escrituras) == 60
    assert [v["filas_procesadas"] for v in r.versiones] == [0, 50, 60]                  # se saltó la versión de 25; la de 50 y la final sí


def test_limitacion_conocida_si_fallan_las_dos_escrituras_finales_el_archivo_queda_en_PROCESANDO():
    """No hay forma de escribir el estado si SharePoint rechaza TODAS las escrituras: los depósitos SÍ se confirmaron. Power Apps lo detecta por el tiempo
    (ver ESCALA_1999.md): se documenta, no se oculta."""
    t, filas = lote(10)
    t.fallos_actualizacion = {1, 2}
    r = confirmar(filas, t)
    assert r.estado["estado"] == "PROCESANDO" and all(t.filas[i]["ESTADO_ASIGNACION"] == "ASIGNADO" for i in range(1, 11))


# ====================================================================== 5 · payload de entrada de 1999 filas
def test_payload_de_1999_filas_tipico_y_maximo_razonable_cabe_en_el_limite_documentado(ejecucion_1999):
    r, t, filas = ejecucion_1999
    texto = json.dumps(filas, ensure_ascii=False, separators=(",", ":"))
    tipico = len(texto.encode("utf-8"))
    assert 500_000 < tipico < 800_000 and tipico / 1999 < 400                            # ≈ 0,6 MB (≈ 300 bytes por fila)
    # máximo razonable: los 8 campos de texto obligatorios al máximo permitido (255 caracteres) + observación de 255
    maximo_fila = {c: "Á" * 255 for c in ("clave_transaccion", "banco", "cuenta_bancaria", "codigo_asignacion", "estudiante", "solicitado_por", "sede", "observacion")}
    maximo_fila.update(fila_excel=2005, deposito_id=999999999, importe=9999999.99, moneda="BOB")
    assert list(maximo_fila) != list(K.CAMPOS_ENTRADA)                                   # (solo el orden de las claves difiere)
    assert set(maximo_fila) == set(K.CAMPOS_ENTRADA)
    maximo = 1999 * len(json.dumps(maximo_fila, ensure_ascii=False).encode("utf-8"))
    assert maximo < 9_000_000 < LIMITE_MENSAJE                                           # ≈ 8,6 MB en el peor caso absurdo (acentos = 2 bytes), 11 veces por debajo de 100 MB
    # no existe límite DOCUMENTADO de tamaño para el input de texto del trigger Power Apps (V2): el 100 MB es el del mensaje (ver ESCALA_1999.md)


def test_el_payload_nunca_pasa_por_string_concat_ni_base64():
    """Microsoft limita string()/concat()/base64() a 131.072 caracteres: el JSON de 1999 filas (~0,6 MB) solo se usa con json(), length(), Select y Query."""
    d = K.construir_definicion()
    expresiones = []

    def recorrer(v):
        if isinstance(v, str) and v.startswith("@"):
            expresiones.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                recorrer(x)
        elif isinstance(v, list):
            for x in v:
                recorrer(x)
    recorrer(d["actions"])
    grandes = ("outputs('Filas')", "outputs('Entrada')?['texto']", "body('Filas_texto')", "body('Filas_formato')", "body('Filas_validadas')",
               "body('Filas_a_procesar')", "body('Filas_invalidas')", "body('Resultados_invalidas')")
    for ex in expresiones:
        for g in grandes:
            for funcion in ("string(", "concat(", "base64("):
                assert not re.search(re.escape(funcion) + r"[^@]{0,40}" + re.escape(g), ex), (funcion, g, ex)
    # y lo único que se serializa del estado es: los 13 campos del estado con el detalle limitado por take()
    con_fallidas = [ex for ex in expresiones if "varFallidas" in ex]
    assert con_fallidas and all(re.fullmatch(r"@(take\(variables\('varFallidas'\),outputs\('PARAM_MAX_DETALLE'\)\)|greater\(length\(variables\('varFallidas'\)\),outputs\('PARAM_MAX_DETALLE'\)\))", ex)
               for ex in con_fallidas), con_fallidas


# ====================================================================== 6 · solicitudes (Power Platform requests) y llamadas a SharePoint
def test_solicitudes_estimadas_para_1999_filas(ejecucion_1999):
    """ESTIMACIÓN a partir de la ejecución simulada (camino feliz ≈ 11 acciones por fila; cada una cuenta como solicitud de Power Platform)."""
    def acciones(n):
        t, filas = lote(n)
        r = confirmar(filas, t)
        return len(r.ensayo.eventos), len(t.llamadas) + len(t.llamadas_archivo)
    a1, s1 = acciones(1)
    a101, s101 = acciones(101)
    por_fila = (a101 - a1) / 100
    assert 10 <= por_fila <= 12.5
    total_acciones = a1 + por_fila * 1998
    assert 20_000 < total_acciones < 26_000                                              # ≈ 22 000 acciones para 1999 filas felices
    r, t, filas = ejecucion_1999
    sharepoint = len(t.llamadas) + len(t.llamadas_archivo)
    assert sharepoint == 1999 + 1983 + 1 + 79 + 1                                        # 1999 GET + 1983 MERGE + CreateFile + 79 avances + 1 final = 4063
    assert sharepoint < 4_200 and (s101 - s1) / 100 < 2.1                                # ≈ 2 llamadas a SharePoint por fila
    # DOCUMENTADO: 600 llamadas/minuto por conexión de SharePoint. Con ≈ 2 llamadas por fila y procesamiento secuencial, el límite solo se alcanzaría si una fila
    # tardara menos de 0,2 s; con 5 s por fila serían ≈ 24 llamadas/min (INFERIDO: el tiempo real por fila se medirá en uso real).
    assert 600 / ((s101 - s1) / 100) == pytest.approx(300, rel=0.1)                     # filas/min a partir de las cuales se tocaría el límite


def test_las_acciones_de_la_definicion_estan_por_debajo_del_limite_documentado_de_500():
    from p9.wdl import contar_acciones
    assert contar_acciones(K.construir_definicion()["actions"]) < 500 and contar_acciones(E.construir_definicion()["actions"]) < 500


# ====================================================================== 7 · P9_MASIVA_PROTO_ESTADO
def test_el_flujo_de_estado_devuelve_9_textos_con_el_avance_y_luego_el_resultado_final():
    t, filas = lote(60, carreras=[7])
    r = confirmar(filas, t)
    final = consultar_estado(t, r.uid)
    assert list(final) == list(E.SALIDAS) and all(isinstance(v, str) for v in final.values())
    assert (final["estado"], final["filas_totales"], final["filas_procesadas"], final["filas_confirmadas"], final["filas_no_confirmadas"], final["porcentaje"]) == \
        ("TERMINADO", "60", "60", "59", "1", "100")
    assert json.loads(final["detalle_json"])[0]["resultado"] == "CONFLICTO" and final["mensaje"] == "59 de 60 depósitos confirmados; 1 requieren revisión."
    # mientras corría: se reproduce cada versión intermedia como si fuera el archivo en ese instante
    for v in r.versiones[:-1]:
        t.archivos[r.nombre_archivo]["contenido"] = json.dumps(v)
        en_curso = consultar_estado(t, r.uid)
        assert en_curso["estado"] == "PROCESANDO" and en_curso["filas_procesadas"] == str(v["filas_procesadas"]) and en_curso["detalle_json"] == "[]"
        assert en_curso["porcentaje"] == str(v["porcentaje"])


def test_el_flujo_de_estado_es_de_solo_lectura_y_solo_lee_el_archivo_de_esa_ejecucion():
    from p9.wdl import recorrer
    acciones = dict(recorrer(E.construir_definicion()["actions"]))
    operaciones = {n: a["inputs"]["host"]["operationId"] for n, a in acciones.items() if a["type"] == "OpenApiConnection"}
    assert operaciones == {"Leer_estado": "GetFileContentByPath"}
    t, filas = lote(3)
    r = confirmar(filas, t)
    antes = (dict(t.archivos), len(t.historial_estado), len(t.llamadas))
    consultar_estado(t, r.uid)
    assert (dict(t.archivos), len(t.historial_estado), len(t.llamadas)) == antes


def test_ejecucion_inexistente_es_NO_ENCONTRADO_y_un_uid_invalido_no_lee_ningun_archivo():
    t = TenantConfirmacion([])
    assert consultar_estado(t, "00000000-0000-4000-8000-0000000000ff")["estado"] == "NO_ENCONTRADO"
    t.llamadas_archivo.clear()
    for malo in ("", "../secreto", "g" * 36, "00000000-0000-4000-8000-00000000000/", "..\\..\\x" + "0" * 29, "00000000-0000-4000-8000-0000000000ff.json", " "):
        r = consultar_estado(t, malo)
        assert r["estado"] == "ERROR" and "inválido" in r["mensaje"], malo
    assert t.llamadas_archivo == []                                                      # ni un intento de lectura con una ruta sospechosa


def test_si_la_lectura_del_estado_falla_con_500_responde_ERROR_sin_romper():
    t, filas = lote(2)
    r = confirmar(filas, t)
    original = t._archivo
    t._archivo = lambda op, *a, **k: (_ for _ in ()).throw(SC.FalloConector("Failed", 500)) if op == "GetFileContentByPath" else original(op, *a, **k)
    resp = consultar_estado(t, r.uid)
    assert resp["estado"] == "ERROR" and "segundo plano" in resp["mensaje"]


def test_los_artefactos_del_flujo_de_estado_son_la_salida_actual_del_generador():
    from pathlib import Path
    carpeta = Path(E.__file__).parent
    d = E.construir_definicion()
    assert json.loads((carpeta / f"{E.NOMBRE_FLUJO}_definition.json").read_text(encoding="utf-8")) == d
    assert (carpeta / f"{E.NOMBRE_FLUJO}.zip").read_bytes() == E.zip_bytes(d)
    (nombre, t), = d["triggers"].items()
    esq = t["inputs"]["schema"]
    assert (t["type"], t["kind"]) == ("Request", "PowerAppV2") and [esq["properties"][c]["title"] for c in esq["required"]] == ["execution_uid"]
    import zipfile
    from io import BytesIO
    z = zipfile.ZipFile(BytesIO(E.zip_bytes(d)))
    env = json.loads(z.read(next(n for n in z.namelist() if n.endswith("/definition.json"))))
    assert set(env["properties"]["connectionReferences"]) == {"shared_sharepointonline"} and env["properties"]["displayName"] == "P9_MASIVA_PROTO_ESTADO"
    assert E.NOMBRE_FLUJO != K.NOMBRE_FLUJO and not [n for n in z.namelist() if "CONFIRMAR" in n]


# ====================================================================== 8 · lo que NO debe cambiar
def test_la_logica_por_fila_es_la_misma_que_funciono_en_el_tenant():
    from p9.wdl import recorrer
    acciones = dict(recorrer(K.construir_definicion()["actions"]))
    assert acciones["Leer_deposito"]["inputs"]["retryPolicy"] == {"type": "fixed", "count": 2, "interval": "PT5S"}
    assert acciones["Actualizar_deposito"]["inputs"]["retryPolicy"] == {"type": "none"}
    assert acciones["Actualizar_deposito"]["inputs"]["parameters"]["parameters/headers"]["IF-MATCH"] == "@outputs('Revalidacion')?['etag']"
    assert acciones["Para_cada_fila"]["runtimeConfiguration"]["concurrency"]["repetitions"] == 1
    assert acciones["ETag_fresco"]["inputs"] == "@coalesce(body('Leer_deposito')?['d']?['__metadata']?['etag'],outputs('Leer_deposito')?['headers']?['ETag'],'')"
    assert list(acciones["Cuerpo_actualizacion"]["inputs"]) == list(K.CAMPOS_ESCRITOS)
    assert acciones["Crear_estado"]["inputs"]["retryPolicy"] == {"type": "none"} and acciones["Escribir_progreso"]["inputs"]["retryPolicy"] == K.RETRY_ESTADO
    assert K.RETRY_ESTADO["interval"] == "PT5S"                                          # mínimo permitido por Power Automate
