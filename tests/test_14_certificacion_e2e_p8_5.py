"""P8.5: certificación E2E de carga. Todo con SharePoint simulado (no es el runtime Microsoft)."""
import copy
import hashlib
import json
import zipfile
from collections import Counter

import pytest

from p8 import construir_paquete_p8 as paquete
from p8.definicion import CAMPOS_IDENTIDAD
from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado
from p8.validar_p8 import EJEMPLO, acciones_recursivas

RAIZ = paquete.RAIZ
MIXTO = RAIZ / "p8/evidencias/DEPOSITOS_ACTIVOS__P8-MIXTO-2N-2E.json"
AMPLIADO = RAIZ / "p8/piloto_ampliado/DEPOSITOS_ACTIVOS__P7-b4d991f026be.json"
ZIP_V5 = RAIZ / "P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES.zip"
SHA256_ZIP_V5 = "3761f0eba22225605e9acbe227a5cf37d4a773267ac476d5665477c5d9472e57"


@pytest.fixture
def definicion():
    return json.loads(paquete.DEFINICION_SALIDA.read_text(encoding="utf-8"))


@pytest.fixture
def artefacto():
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


def control_ok(entrada):
    n = len(entrada["movimientos"]) + len(entrada["omitidos"])
    return {"version": "P8.5-ORIGEN-1", "sha256_lists": entrada["sha256_archivo_fuente"], "total_archivos": 1,
            "archivos_error": 0, "movimientos_origen": n, "movimientos_normalizados": n,
            "integridad_origen": "OK", "origen_vacio_demostrado": n == 0, "archivos": []}


def correr(definicion, entrada, control="auto", **opciones):
    """control='auto': el artefacto lleva un control_origen coherente y OK; None: sin control;
    dict: ese bloque exacto."""
    if isinstance(entrada, dict) and control is not None:
        entrada = {**entrada, "control_origen": control_ok(entrada) if control == "auto" else control}
    sp = SharePointSimulado(entrada, **opciones)
    corrida = EnsayoWDL(definicion, sp).ejecutar()
    assert len(sp.bitacoras) == 1
    b = sp.bitacoras[0]
    assert b["CANTIDAD_RECIBIDA"] == b["CANTIDAD_NUEVA"] + b["CANTIDAD_YA_EXISTE"] + b["CANTIDAD_ERROR"]
    if b["MENSAJE_ERROR"]:
        json.loads(b["MENSAJE_ERROR"])
    return sp, corrida, b


def cert(b):
    return (b["CANTIDAD_ESPERADA"], b["CANTIDAD_CONFIRMADA"], b["CANTIDAD_FALTANTE"], b["CANTIDAD_DIFERENCIA"],
            b["CANTIDAD_ERROR"], b["ESTADO_CERTIFICACION/Value"])


def llamadas(sp):
    return Counter(n for n, _ in sp.llamadas)


# ---------------------------------------------------------------- escenarios positivos

def test_carga_100_confirmada(definicion, artefacto):
    sp, _, b = correr(definicion, artefacto)
    assert cert(b) == (8, 8, 0, 0, 0, "CERTIFICADO")
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO" and b["MENSAJE_ERROR"] == ""
    assert (b["CANTIDAD_NUEVA"], b["CANTIDAD_YA_EXISTE"]) == (8, 0)
    # Sin llamadas extra por movimiento: 1 lectura + 8 preconsultas + 8 creaciones + 1 bitácora.
    assert llamadas(sp) == {"Obtener_contenido_del_archivo": 1, "Obtener_clave_preexistente": 8,
                            "Crear_movimiento": 8, "Registrar_bitacora_del_lote": 1}


def test_reproceso_100_ya_existe_queda_certificado(definicion, artefacto):
    primera, _, _ = correr(definicion, artefacto)
    sp, _, b = correr(definicion, artefacto, existentes=primera.activos)
    assert (b["CANTIDAD_NUEVA"], b["CANTIDAD_YA_EXISTE"]) == (0, 8)
    assert cert(b) == (8, 8, 0, 0, 0, "CERTIFICADO") and b["ESTADO_LOTE/Value"] == "COMPLETADO"
    assert llamadas(sp) == {"Obtener_contenido_del_archivo": 1, "Obtener_clave_preexistente": 8,
                            "Registrar_bitacora_del_lote": 1}


def test_ya_existente_no_exige_mismo_lote_ni_archivo_origen_y_se_conservan(definicion, artefacto):
    primera, _, _ = correr(definicion, artefacto)
    existentes = copy.deepcopy(primera.activos)
    for fila in existentes.values():
        fila["LOTE_CARGA"], fila["ARCHIVO_ORIGEN"] = "19990101_000000", "extracto_de_otra_descarga.xls"
    sp, _, b = correr(definicion, artefacto, existentes=existentes)
    assert cert(b) == (8, 8, 0, 0, 0, "CERTIFICADO")
    assert {f["LOTE_CARGA"] for f in sp.activos.values()} == {"19990101_000000"}  # trazabilidad intacta
    assert {f["ARCHIVO_ORIGEN"] for f in sp.activos.values()} == {"extracto_de_otra_descarga.xls"}
    assert "LOTE_CARGA" not in CAMPOS_IDENTIDAD and "ARCHIVO_ORIGEN" not in CAMPOS_IDENTIDAD


def test_lote_mixto_nuevos_y_existentes_queda_certificado(definicion, artefacto):
    primera, _, _ = correr(definicion, artefacto)
    mixto = json.loads(MIXTO.read_text(encoding="utf-8"))
    sp, _, b = correr(definicion, mixto, existentes=primera.activos)
    assert (b["CANTIDAD_RECIBIDA"], b["CANTIDAD_NUEVA"], b["CANTIDAD_YA_EXISTE"], b["CANTIDAD_ERROR"]) == (4, 2, 2, 0)
    assert cert(b) == (4, 4, 0, 0, 0, "CERTIFICADO") and b["ESTADO_LOTE/Value"] == "COMPLETADO"
    assert len(sp.activos) == 10
    assert llamadas(sp) == {"Obtener_contenido_del_archivo": 1, "Obtener_clave_preexistente": 4,
                            "Crear_movimiento": 2, "Registrar_bitacora_del_lote": 1}


def test_piloto_ampliado_con_hora_vacia_y_credito_negativo_queda_certificado(definicion):
    entrada = json.loads(AMPLIADO.read_text(encoding="utf-8"))
    primera, _, b = correr(definicion, entrada)
    assert cert(b) == (4, 4, 0, 0, 0, "CERTIFICADO")
    # SharePoint devuelve null para un texto vacío: no debe contarse como diferencia.
    sin_hora = {("Obtener_clave_preexistente", m["CLAVE_TRANSACCION"]): {"HORA_MOVIMIENTO": None}
                for m in entrada["movimientos"] if m["HORA_MOVIMIENTO"] == ""}
    assert len(sin_hora) == 1
    _, _, b2 = correr(definicion, entrada, existentes=primera.activos, alteraciones=sin_hora)
    assert cert(b2) == (4, 4, 0, 0, 0, "CERTIFICADO")
    # En cambio, null donde se esperaba una hora SÍ es diferencia.
    con_hora = {("Obtener_clave_preexistente", m["CLAVE_TRANSACCION"]): {"HORA_MOVIMIENTO": None}
                for m in entrada["movimientos"] if m["HORA_MOVIMIENTO"] != ""}
    _, _, b3 = correr(definicion, entrada, existentes=primera.activos, alteraciones=con_hora)
    assert cert(b3) == (4, 1, 0, 3, 0, "NO_CERTIFICADO")


def test_fecha_iso_con_hora_cero_se_compara_por_su_parte_fecha(definicion, artefacto):
    primera, _, _ = correr(definicion, artefacto)
    iso = {k: {**f, "FECHA_MOVIMIENTO": f["FECHA_MOVIMIENTO"] + "T00:00:00Z"} for k, f in primera.activos.items()}
    _, _, b = correr(definicion, artefacto, existentes=iso)
    assert cert(b) == (8, 8, 0, 0, 0, "CERTIFICADO")


# ---------------------------------------------------------------- faltantes y diferencias

def test_clave_faltante_no_certifica(definicion, artefacto):
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    sp, _, b = correr(definicion, artefacto, fallos={("Crear_movimiento", clave): ("Failed", 500)})
    assert cert(b) == (8, 7, 1, 0, 1, "NO_CERTIFICADO")
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO_CON_ERRORES"
    assert llamadas(sp)["Reconsultar_CLAVE_TRANSACCION"] == 1  # reutiliza la reconsulta que P8 ya hace


@pytest.mark.parametrize("estado", ["Failed", "TimedOut"])
def test_clave_con_reconsulta_fallida_queda_no_confirmada(definicion, artefacto, estado):
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    _, _, b = correr(definicion, artefacto, fallos={("Crear_movimiento", clave): ("TimedOut", 504),
                                                    ("Reconsultar_CLAVE_TRANSACCION", clave): (estado, 503)})
    assert cert(b) == (8, 7, 1, 0, 1, "NO_CERTIFICADO")


VALORES_ERRONEOS = {
    "CLAVE_TRANSACCION": lambda v: v.lower(),
    "BANCO": lambda v: "BNB", "CUENTA_BANCARIA": lambda v: "999-0-00",
    "FECHA_MOVIMIENTO": lambda v: "2026-07-08", "HORA_MOVIMIENTO": lambda v: "00:00:01",
    "CODIGO_ASIGNACION": lambda v: "0", "TIPO_MOVIMIENTO": lambda v: "DÉBITO",
    "IMPORTE": lambda v: 446.0, "SALDO": lambda v: 1.0,
}


def escenario(definicion, artefacto, etapa, cambios):
    """Una fila (la primera) vuelve de SharePoint con `cambios`, según de dónde se obtenga el registro."""
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    if etapa == "preexistente":
        previo, _, _ = correr(definicion, artefacto)
        return correr(definicion, artefacto, existentes=previo.activos,
                      alteraciones={("Obtener_clave_preexistente", clave): cambios})
    if etapa == "nuevo":
        return correr(definicion, artefacto, alteraciones={("Crear_movimiento", clave): cambios})
    # reconsulta: la creación se cae pero persistió; el registro se obtiene de la reconsulta de P8.
    return correr(definicion, artefacto, fallos={("Crear_movimiento", clave): ("Failed", 409, "persistir")},
                  alteraciones={("Reconsultar_CLAVE_TRANSACCION", clave): cambios})


@pytest.mark.parametrize("etapa", ["preexistente", "nuevo", "reconsulta"])
@pytest.mark.parametrize("campo", CAMPOS_IDENTIDAD)
def test_cualquier_campo_de_identidad_distinto_es_diferencia(definicion, artefacto, etapa, campo):
    original = artefacto["movimientos"][0]
    valor = VALORES_ERRONEOS[campo](original[campo])
    assert valor != original[campo]
    sp, _, b = escenario(definicion, artefacto, etapa, {campo: valor})
    assert cert(b) == (8, 7, 0, 1, 0, "NO_CERTIFICADO")
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO"  # ESTADO_LOTE conserva su significado
    detalle = json.loads(b["MENSAJE_ERROR"])
    assert detalle["certificacion"] == "NO_CERTIFICADO" and len(detalle["errores"]) == 1
    assert detalle["errores"][0]["codigo"] == f"DIF:{campo};"
    assert detalle["errores"][0]["CLAVE_TRANSACCION"] == original["CLAVE_TRANSACCION"]
    assert detalle["errores"][0]["fila"] == ("PRECONSULTA" if etapa == "preexistente" else 1)
    # Nunca una consulta SharePoint por movimiento para certificar.
    esperadas = {"preexistente": {"Obtener_clave_preexistente": 8},
                 "nuevo": {"Obtener_clave_preexistente": 8, "Crear_movimiento": 8},
                 "reconsulta": {"Obtener_clave_preexistente": 8, "Crear_movimiento": 8, "Reconsultar_CLAVE_TRANSACCION": 1}}[etapa]
    assert {k: v for k, v in llamadas(sp).items() if k in esperadas} == esperadas
    assert set(llamadas(sp)) <= set(esperadas) | {"Obtener_contenido_del_archivo", "Registrar_bitacora_del_lote"}


def test_cruce_de_banco_y_cuenta_se_detecta(definicion, artefacto):
    sp, _, b = escenario(definicion, artefacto, "preexistente", {"BANCO": "BNB", "CUENTA_BANCARIA": "3000100152"})
    assert cert(b) == (8, 7, 0, 1, 0, "NO_CERTIFICADO")
    assert json.loads(b["MENSAJE_ERROR"])["errores"][0]["codigo"] == "DIF:BANCO;CUENTA_BANCARIA;"


def test_diferencias_se_acotan_y_se_cuentan_todas(definicion, artefacto):
    previo, _, _ = correr(definicion, artefacto)
    cambios = {("Obtener_clave_preexistente", m["CLAVE_TRANSACCION"]): {"BANCO": "BNB"} for m in artefacto["movimientos"]}
    _, _, b = correr(definicion, artefacto, existentes=previo.activos, alteraciones=cambios)
    assert cert(b) == (8, 0, 0, 8, 0, "NO_CERTIFICADO")
    d = json.loads(b["MENSAJE_ERROR"])
    assert len(d["errores"]) == 8 and len(b["MENSAJE_ERROR"].encode("utf-16-le")) // 2 <= 8000
    # 25 filas con diferencia: solo 8 detalles, el resto contado en detalle_omitido.
    original = artefacto["movimientos"][0]
    artefacto["movimientos"] = []
    for i in range(25):
        m = copy.deepcopy(original)
        m["CLAVE_TRANSACCION"] = f"BCP|X|{i:02d}"
        artefacto["movimientos"].append(m)
    existentes = {m["CLAVE_TRANSACCION"]: {**m, "BANCO": "BNB"} for m in artefacto["movimientos"]}
    _, _, b = correr(definicion, artefacto, existentes=existentes)
    d = json.loads(b["MENSAJE_ERROR"])
    assert cert(b) == (25, 0, 0, 25, 0, "NO_CERTIFICADO") and len(d["errores"]) == 8 and d["detalle_omitido"] == 17


# ---------------------------------------------------------------- reglas de cierre

@pytest.mark.parametrize("caso", ["ilegible", "version", "columnas"])
def test_fallo_estructural_nunca_certifica(definicion, artefacto, caso):
    if caso == "ilegible":
        entrada = '{"JSON roto":'
    else:
        entrada = copy.deepcopy(artefacto)
        if caso == "version":
            entrada["esquema"] = "INCOMPATIBLE"
        else:
            entrada["columnas"][0] = "OTRA_COLUMNA"
    _, _, b = correr(definicion, entrada)
    assert b["ESTADO_LOTE/Value"] == "FALLIDO" and b["ESTADO_CERTIFICACION/Value"] == "NO_CERTIFICADO"


def test_fallo_de_preconsulta_nunca_certifica(definicion, artefacto):
    clave = artefacto["movimientos"][-1]["CLAVE_TRANSACCION"]
    _, _, b = correr(definicion, artefacto, fallos={("Obtener_clave_preexistente", clave): ("Failed", 403)})
    assert b["ESTADO_LOTE/Value"] == "FALLIDO" and b["ESTADO_CERTIFICACION/Value"] == "NO_CERTIFICADO"
    assert b["CANTIDAD_ESPERADA"] == 8 and b["CANTIDAD_FALTANTE"] + b["CANTIDAD_CONFIRMADA"] == 8


def test_omitido_error_no_certifica_y_esperada_cuenta_solo_validos(definicion, artefacto):
    primero = artefacto["movimientos"].pop(0)
    artefacto["omitidos"] = [{"fila": 1, "estado": "ERROR", "motivo": "x", "errores": [], "valores": primero}]
    _, _, b = correr(definicion, artefacto)
    assert (b["CANTIDAD_RECIBIDA"], b["CANTIDAD_VALIDA"]) == (8, 7)
    assert cert(b) == (7, 7, 0, 0, 1, "NO_CERTIFICADO")


def test_omitido_ya_existe_no_verificado_no_certifica(definicion, artefacto):
    primero = artefacto["movimientos"].pop(0)
    artefacto["omitidos"] = [{"fila": 1, "estado": "YA_EXISTE", "motivo": "EN_LISTA", "errores": [], "valores": primero}]
    _, _, b = correr(definicion, artefacto)
    assert cert(b) == (8, 7, 1, 0, 0, "NO_CERTIFICADO") and b["ESTADO_LOTE/Value"] == "COMPLETADO"


def test_lote_vacio_solo_certifica_si_el_origen_demuestra_cero(definicion, artefacto):
    artefacto["movimientos"] = []
    _, _, b = correr(definicion, artefacto)  # control demuestra 0 movimientos en todos los archivos
    assert cert(b) == (0, 0, 0, 0, 0, "CERTIFICADO") and b["ESTADO_LOTE/Value"] == "COMPLETADO"
    # Sin esa demostración, 0 movimientos NO se certifica por vacuidad.
    sin_demostrar = {**control_ok(artefacto), "origen_vacio_demostrado": False}
    for control in (None, sin_demostrar):
        _, _, b = correr(definicion, artefacto, control=control)
        assert cert(b) == (0, 0, 0, 0, 0, "NO_CERTIFICADO") and b["ESTADO_LOTE/Value"] == "COMPLETADO"


# ---------------------------------------------------------------- integridad de origen (P8.5)

def test_sin_control_de_origen_no_certifica_aunque_todo_este_confirmado(definicion, artefacto):
    sp, _, b = correr(definicion, artefacto, control=None)
    assert (b["CANTIDAD_NUEVA"], b["ESTADO_LOTE/Value"]) == (8, "COMPLETADO")
    assert cert(b) == (8, 8, 0, 0, 0, "NO_CERTIFICADO") and b["INTEGRIDAD_ORIGEN/Value"] == "ERROR"
    d = json.loads(b["MENSAJE_ERROR"])
    assert d["integridad_origen"] == "ERROR" and "Integridad de origen" in d["mensaje"]


@pytest.mark.parametrize("cambio", [
    {"integridad_origen": "ERROR"},
    {"integridad_origen": "OK ", "total_archivos": 1},
    {"sha256_lists": "0" * 64},              # control de otro LISTS.csv
    {"movimientos_normalizados": 9},         # otro total de filas que el JSON
    {"movimientos_normalizados": 7},
])
def test_control_de_origen_invalido_o_ajeno_no_certifica(definicion, artefacto, cambio):
    control = {**control_ok(artefacto), **cambio}
    _, _, b = correr(definicion, artefacto, control=control)
    assert b["INTEGRIDAD_ORIGEN/Value"] == "ERROR" and b["ESTADO_CERTIFICACION/Value"] == "NO_CERTIFICADO"
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO" and (b["CANTIDAD_NUEVA"], b["CANTIDAD_ERROR"]) == (8, 0)


def test_control_de_origen_ok_certifica_y_se_registra(definicion, artefacto):
    _, _, b = correr(definicion, artefacto)
    assert b["INTEGRIDAD_ORIGEN/Value"] == "OK" and b["ESTADO_CERTIFICACION/Value"] == "CERTIFICADO"


def test_integridad_ok_no_sustituye_la_certificacion_sharepoint(definicion, artefacto):
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    _, _, b = correr(definicion, artefacto, fallos={("Crear_movimiento", clave): ("Failed", 500)})
    assert b["INTEGRIDAD_ORIGEN/Value"] == "OK" and b["ESTADO_CERTIFICACION/Value"] == "NO_CERTIFICADO"


def test_fallo_estructural_deja_integridad_en_error(definicion):
    _, _, b = correr(definicion, '{"JSON roto":')
    assert b["INTEGRIDAD_ORIGEN/Value"] == "ERROR" and b["ESTADO_CERTIFICACION/Value"] == "NO_CERTIFICADO"


# ---------------------------------------------------------------- paquete y estructura

def _definicion_de(zip_ruta):
    with zipfile.ZipFile(zip_ruta) as z:
        nombre = next(n for n in z.namelist() if n.endswith("/definition.json"))
        return json.loads(z.read(nombre))["properties"]["definition"]


def test_v7_no_agrega_llamadas_sharepoint_ni_quita_acciones_de_v5(definicion):
    v5 = dict(acciones_recursivas(_definicion_de(ZIP_V5)["actions"]))
    v6 = dict(acciones_recursivas(definicion["actions"]))
    sp = lambda acciones: sorted((n, a["inputs"]["host"]["operationId"]) for n, a in acciones.items()
                                 if a["type"] == "OpenApiConnection")
    assert sp(v6) == sp(v5) and len(sp(v6)) == 5
    assert set(v5) <= set(v6) and len(v6) - len(v5) == 32
    assert all(v6[n]["type"] != "OpenApiConnection" for n in set(v6) - set(v5))


def test_bitacora_escribe_exactamente_las_columnas_de_certificacion(definicion):
    params = dict(acciones_recursivas(definicion["actions"]))["Registrar_bitacora_del_lote"]["inputs"]["parameters"]
    esquema = json.loads(paquete.ESQUEMA_CERTIFICACION_SALIDA.read_text(encoding="utf-8"))["Depositos_Cargas"]
    nuevas = [c["nombre_tecnico"] for c in esquema["columnas_nuevas"]]
    assert nuevas == ["CANTIDAD_ESPERADA", "CANTIDAD_CONFIRMADA", "CANTIDAD_FALTANTE", "CANTIDAD_DIFERENCIA",
                      "ESTADO_CERTIFICACION", "INTEGRIDAD_ORIGEN"]
    assert esquema["total_columnas_nuevas"] == 6
    escritas = {k.split("/")[1] for k in params if k.startswith("item/")}
    base = json.loads(paquete.ESQUEMA_LISTAS_SALIDA.read_text(encoding="utf-8"))["Depositos_Cargas"]["columnas"]
    assert escritas == {c["nombre_tecnico"] for c in base} | set(nuevas)
    assert params["item/ESTADO_CERTIFICACION/Value"] == "@outputs('Estado_certificacion')"
    assert {c["nombre_tecnico"] for c in base}.isdisjoint(nuevas)
    estado, origen = esquema["columnas_nuevas"][-2:]
    assert estado["valores"] == ["CERTIFICADO", "NO_CERTIFICADO"] and estado["permitir_relleno"] is False
    assert origen["valores"] == ["OK", "ERROR"] and origen["permitir_relleno"] is False
    assert params["item/INTEGRIDAD_ORIGEN/Value"] == "@variables('varIntegridadOrigen')"


def test_paquete_v7_no_sobrescribe_v5(definicion):
    assert hashlib.sha256(ZIP_V5.read_bytes()).hexdigest() == SHA256_ZIP_V5
    assert paquete.ZIP_SALIDA.name == "P8_CARGA_DEPOSITOS_ACTIVOS_V7_CERTIFICACION_E2E_ORIGEN.zip" and paquete.ZIP_SALIDA != ZIP_V5
    with zipfile.ZipFile(paquete.ZIP_SALIDA) as v7, zipfile.ZipFile(ZIP_V5) as v5:
        assert not set(json.loads(v7.read("manifest.json"))["resources"]) & set(json.loads(v5.read("manifest.json"))["resources"])
        assert json.loads(v7.read("manifest.json"))["details"]["displayName"] == "P8_CARGA_DEPOSITOS_ACTIVOS_V7_CERTIFICACION_E2E_ORIGEN"
    # Trigger y ubicaciones del tenant piloto, sin cambios respecto de V5.
    assert _definicion_de(paquete.ZIP_SALIDA)["triggers"] == _definicion_de(ZIP_V5)["triggers"]
    assert definicion["triggers"] == _definicion_de(ZIP_V5)["triggers"]


def test_esquema_de_certificacion_es_reproducible():
    antes = paquete.ESQUEMA_CERTIFICACION_SALIDA.read_bytes()
    paquete.escribir_artefactos()
    assert paquete.ESQUEMA_CERTIFICACION_SALIDA.read_bytes() == antes
    assert hashlib.sha256(ZIP_V5.read_bytes()).hexdigest() == SHA256_ZIP_V5
