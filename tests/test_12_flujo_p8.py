import copy
import csv
import json
import zipfile
import pytest

from p8 import construir_paquete_p8 as paquete
from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado
from p8.validar_p8 import EJEMPLO, acciones_recursivas, validar


@pytest.fixture
def artefacto():
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


@pytest.fixture
def definicion():
    return json.loads(paquete.DEFINICION_SALIDA.read_text(encoding="utf-8"))


def correr(definicion, entrada, **opciones):
    sp = SharePointSimulado(entrada, **opciones)
    corrida = EnsayoWDL(definicion, sp).ejecutar()
    assert len(sp.bitacoras) == 1
    b = sp.bitacoras[0]
    assert b["CANTIDAD_RECIBIDA"] == b["CANTIDAD_NUEVA"] + b["CANTIDAD_YA_EXISTE"] + b["CANTIDAD_ERROR"]
    assert len(b["MENSAJE_ERROR"]) <= 8000
    if b["MENSAJE_ERROR"]:
        json.loads(b["MENSAJE_ERROR"])
    return sp, corrida, b


def test_paquete_y_fuente_son_reproducibles():
    originales = {p: p.read_bytes() for p in (paquete.DEFINICION_SALIDA, paquete.ESQUEMA_LISTAS_SALIDA, paquete.ZIP_SALIDA)}
    anterior = paquete.RAIZ / "P8_CARGA_DEPOSITOS_ACTIVOS.zip"
    bytes_anteriores = anterior.read_bytes()
    paquete.escribir_artefactos()
    assert all(p.read_bytes() == valor for p, valor in originales.items())
    assert anterior.read_bytes() == bytes_anteriores
    nombre = "P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES"
    assert paquete.ZIP_SALIDA.name == nombre + ".zip"
    with zipfile.ZipFile(paquete.ZIP_SALIDA) as z, zipfile.ZipFile(anterior) as viejo:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["details"]["displayName"] == nombre
        recursos_flujo = [r for r in manifest["resources"].values() if r["type"] == "Microsoft.Flow/flows"]
        assert len(recursos_flujo) == 1
        assert recursos_flujo[0]["details"]["displayName"] == nombre
        assert recursos_flujo[0]["suggestedCreationType"] == "New"
        contenido = json.loads(z.read(next(p for p in z.namelist() if p.endswith('/definition.json'))))
        assert contenido["properties"]["displayName"] == nombre
        assert not set(manifest["resources"]) & set(json.loads(viejo.read("manifest.json"))["resources"])
    validar()


def test_acciones_de_listas_usan_table_literal_del_tenant_piloto(definicion):
    sitio = "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu"
    esperado = {"DEPOSITOS_ACTIVOS": "296c450a-25d6-415b-ad10-c909c74817cb",
                "DEPOSITOS_CARGAS": "677aab03-28d0-4893-83cf-1f394850c515"}
    por_accion = {"Obtener_clave_preexistente": "DEPOSITOS_ACTIVOS", "Crear_movimiento": "DEPOSITOS_ACTIVOS",
                  "Reconsultar_CLAVE_TRANSACCION": "DEPOSITOS_ACTIVOS", "Registrar_bitacora_del_lote": "DEPOSITOS_CARGAS"}
    vistas = {}
    for nombre, accion in acciones_recursivas(definicion["actions"]):
        if nombre in por_accion:
            vistas[nombre] = accion["inputs"]["parameters"]
    assert set(vistas) == set(por_accion)
    for nombre, parametros in vistas.items():
        assert parametros["dataset"] == sitio
        assert parametros["table"] == esperado[por_accion[nombre]]
        assert not str(parametros["table"]).startswith("@")


def test_piloto_8_y_reproceso_sin_intentos_de_creacion(definicion, artefacto):
    sp, _, b = correr(definicion, artefacto)
    campos = ("CANTIDAD_RECIBIDA", "CANTIDAD_VALIDA", "CANTIDAD_NUEVA", "CANTIDAD_YA_EXISTE", "CANTIDAD_ERROR")
    assert [b[k] for k in campos] == [8, 8, 8, 0, 0]
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO"
    assert b["HASH_SHA256"] == artefacto["sha256_archivo_fuente"]
    assert "SHA256" not in b and "_x0053_HA256" not in b
    sp2, _, b2 = correr(definicion, artefacto, existentes=sp.activos)
    assert [b2[k] for k in campos] == [8, 8, 0, 8, 0]
    assert b2["ESTADO_LOTE/Value"] == "COMPLETADO"
    assert b2["HASH_SHA256"] == artefacto["sha256_archivo_fuente"]
    assert sp2.coincidencias_preconsulta == 8 and sp2.creaciones == [] and len(sp2.activos) == 8


@pytest.mark.parametrize("caso", ["ilegible", "version", "columnas", "propiedad_raiz", "propiedad_movimiento", "omitido_invalido"])
def test_estructural_siempre_registra_antes_de_terminar(definicion, artefacto, caso):
    if caso == "ilegible":
        entrada = '{"JSON roto":'
    else:
        entrada = copy.deepcopy(artefacto)
        if caso == "version": entrada["esquema"] = "INCOMPATIBLE"
        if caso == "columnas": entrada["columnas"][0] = "OTRA_COLUMNA"
        if caso == "propiedad_raiz": del entrada["lote_id"]
        if caso == "propiedad_movimiento": del entrada["movimientos"][0]["BANCO"]
        if caso == "omitido_invalido":
            entrada["omitidos"] = [{"fila": 9, "estado": "OTRO", "motivo": "", "errores": [], "valores": entrada["movimientos"][0]}]
    sp, r, b = correr(definicion, entrada)
    assert b["ESTADO_LOTE/Value"] == "FALLIDO"
    assert "HASH_SHA256" in b and "SHA256" not in b
    assert b["ARCHIVO_JSON"] == "DEPOSITOS_ACTIVOS__piloto.json"
    assert r.eventos.index("Registrar_bitacora_del_lote") < r.eventos.index("Terminar_FALLIDO")
    assert sp.creaciones == []
    assert {"etapa", "archivo", "mensaje"} <= set(json.loads(b["MENSAJE_ERROR"]))


@pytest.mark.parametrize("estado", ["Failed", "TimedOut"])
@pytest.mark.parametrize("persistir", [False, True])
def test_creacion_fallida_o_timeout_reconsulta_y_continua(definicion, artefacto, estado, persistir):
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    fallo = (estado, 409 if persistir else 500) + (("persistir",) if persistir else ())
    sp, r, b = correr(definicion, artefacto, fallos={("Crear_movimiento", clave): fallo})
    assert b["CANTIDAD_NUEVA"] == 7
    assert b["CANTIDAD_YA_EXISTE"] == int(persistir)
    assert b["CANTIDAD_ERROR"] == int(not persistir)
    assert b["ESTADO_LOTE/Value"] == ("COMPLETADO" if persistir else "COMPLETADO_CON_ERRORES")
    assert len(sp.creaciones) == 8
    assert any(n == "Reconsultar_CLAVE_TRANSACCION" for n, p in sp.llamadas)
    assert r.estado_final == "Succeeded"


@pytest.mark.parametrize("estado_reconsulta", ["Failed", "TimedOut"])
def test_reconsulta_fallida_es_error_de_fila_y_no_del_lote(definicion, artefacto, estado_reconsulta):
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    sp, r, b = correr(definicion, artefacto, fallos={
        ("Crear_movimiento", clave): ("TimedOut", 504),
        ("Reconsultar_CLAVE_TRANSACCION", clave): (estado_reconsulta, 503),
    })
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO_CON_ERRORES"
    assert (b["CANTIDAD_NUEVA"], b["CANTIDAD_ERROR"]) == (7, 1)
    detalle = json.loads(b["MENSAJE_ERROR"])["errores"][0]
    assert detalle["fila"] == 1 and detalle["CLAVE_TRANSACCION"] == clave
    assert "CREAR_TimedOut_HTTP_504" in detalle["codigo"]
    assert f"RECONSULTA_{estado_reconsulta}_HTTP_503" in detalle["codigo"]
    assert len(sp.creaciones) == 8 and r.estado_final == "Succeeded"


def test_fallo_preconsulta_es_estructural_y_cero_creaciones(definicion, artefacto):
    clave = artefacto["movimientos"][-1]["CLAVE_TRANSACCION"]
    sp, r, b = correr(definicion, artefacto, fallos={("Obtener_clave_preexistente", clave): ("Failed", 403)})
    assert b["ESTADO_LOTE/Value"] == "FALLIDO" and b["CANTIDAD_ERROR"] == 8
    assert json.loads(b["MENSAJE_ERROR"])["etapa"] == "PRECONSULTA"
    assert sp.creaciones == []


def test_fallo_lectura_tiene_archivo_del_trigger(definicion):
    sp, r, b = correr(definicion, "", fallos={"Obtener_contenido_del_archivo": ("Failed", 404)})
    assert b["ESTADO_LOTE/Value"] == "FALLIDO"
    assert b["ARCHIVO_JSON"] == "DEPOSITOS_ACTIVOS__piloto.json"
    assert json.loads(b["MENSAJE_ERROR"])["etapa"] == "LECTURA"


def test_fallo_escritura_bitacora_no_se_oculta_ni_termina_exitoso(definicion, artefacto):
    sp = SharePointSimulado(artefacto, fallos={"Registrar_bitacora_del_lote": ("Failed", 403)})
    r = EnsayoWDL(definicion, sp).ejecutar()
    assert not sp.bitacoras and r.estado_final == "Failed"
    assert not any(e.startswith("Terminar_") for e in r.eventos)


@pytest.mark.parametrize("nombre,dispara", [("MANIFIESTO_P7__x.json", False), ("DEPOSITOS_ACTIVOS__x.csv", False), ("otro.json", False), ("DEPOSITOS_ACTIVOS__x.json", True)])
def test_trigger_sharepoint_filtra_nombres_reales(definicion, artefacto, nombre, dispara):
    sp = SharePointSimulado(artefacto, nombre=nombre)
    EnsayoWDL(definicion, sp).ejecutar()
    assert bool(sp.llamadas) == dispara
    if dispara:
        assert sp.llamadas[0][1]["id"] == "identificador-de-prueba"
        assert sp.llamadas[0][1]["inferContentType"] is False


def test_configuracion_binaria_no_adivina_otra_forma(definicion, artefacto):
    sp, r, b = correr(definicion, artefacto, directo=True)
    assert b["ESTADO_LOTE/Value"] == "FALLIDO"
    assert json.loads(b["MENSAJE_ERROR"])["etapa"] == "PARSE_JSON"
    assert not sp.creaciones


def test_error_con_omitidos_conserva_fila_original_y_no_expone_secreto(definicion, artefacto):
    primero = artefacto["movimientos"].pop(0)
    artefacto["omitidos"] = [{"fila": 1, "estado": "ERROR", "motivo": "Authorization: Bearer NO_PUBLICAR", "errores": [], "valores": primero}]
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    sp, r, b = correr(definicion, artefacto, fallos={("Crear_movimiento", clave): ("Failed", 400)})
    assert (b["CANTIDAD_RECIBIDA"], b["CANTIDAD_VALIDA"], b["CANTIDAD_NUEVA"], b["CANTIDAD_ERROR"]) == (8, 7, 6, 2)
    assert [d["fila"] for d in json.loads(b["MENSAJE_ERROR"])["errores"]] == [1, 2]
    assert "NO_PUBLICAR" not in b["MENSAJE_ERROR"]


def test_diagnostico_acotado_mantiene_json_valido_con_textos_largos(definicion, artefacto):
    original = artefacto["movimientos"][0]
    artefacto["movimientos"] = []
    for i in range(25):
        m = copy.deepcopy(original)
        m["CLAVE_TRANSACCION"] = str(i) + "\n\"\\" * 80
        artefacto["movimientos"].append(m)
    fallos = {("Crear_movimiento", m["CLAVE_TRANSACCION"]): ("Failed", 400) for m in artefacto["movimientos"]}
    sp, r, b = correr(definicion, artefacto, fallos=fallos, nombre="DEPOSITOS_ACTIVOS__" + "a" * 200 + ".json")
    d = json.loads(b["MENSAJE_ERROR"])
    assert b["CANTIDAD_ERROR"] == 25 and len(d["errores"]) == 8
    assert d["detalle_omitido"] == 17 and len(b["MENSAJE_ERROR"].encode('utf-16-le')) // 2 <= 8000


def test_extremos_con_utc_y_fecha_testigo_julio_nueve(definicion, artefacto):
    existentes = {m["CLAVE_TRANSACCION"]: {**m, "FECHA_MOVIMIENTO": "1999-01-01T23:00:00Z"} for m in artefacto["movimientos"]}
    sp, r, b = correr(definicion, artefacto, existentes=existentes)
    assert sp.coincidencias_preconsulta == 8 and len(sp.creaciones) == 0
    sp1, _, _ = correr(definicion, artefacto)
    testigo = next(m for m in sp1.activos.values() if m["FECHA_MOVIMIENTO"] == "2026-07-09")
    assert testigo["CLAVE_TRANSACCION"].split("|")[2] == "20260709"
    assert {m["FECHA_CARGA"] for m in sp1.activos.values()} == {m["FECHA_CARGA"] for m in artefacto["movimientos"]}


def test_apostrofos_odata_se_escapan_sin_modificar_clave(definicion, artefacto):
    artefacto["movimientos"][0]["CLAVE_TRANSACCION"] += "|'"
    clave = artefacto["movimientos"][0]["CLAVE_TRANSACCION"]
    sp, r, b = correr(definicion, artefacto, existentes={clave: artefacto["movimientos"][0]})
    assert b["CANTIDAD_YA_EXISTE"] == 1 and len(sp.creaciones) == 7


def test_conjunto_ampliado_cubre_fixtures_sin_cambios(definicion):
    directorio = paquete.RAIZ / "p8/piloto_ampliado"
    tr = json.loads((directorio / "TRAZABILIDAD.json").read_text())
    entrada = json.loads((directorio / tr["artefacto"]).read_text())
    assert len(entrada["movimientos"]) == 4
    with (paquete.RAIZ / tr["fuente"]).open(encoding="utf-8-sig", newline="") as f:
        originales = list(csv.DictReader(f))
    columnas = paquete._cargar_adaptador().COLUMNAS_M365
    for movimiento, referencia in zip(entrada["movimientos"], tr["filas"]):
        original = originales[referencia["fila_datos_dorada"] - 1]
        assert movimiento == {tecnico: original[origen] for origen, tecnico, _, _ in columnas}
    cobertura = {c for fila in tr["filas"] for c in fila["cobertura"]}
    assert cobertura == {"DEBITO_NO_VACIO", "ORIGINANTE", "CLAVE_CON_O_Y_ESPACIO", "HORA_VACIA", "NUMERO_NEGATIVO"}
    sp, _, b = correr(definicion, entrada)
    assert b["CANTIDAD_NUEVA"] == 4
    assert any(m["CREDITO"] is not None and m["CREDITO"] < 0 for m in sp.activos.values())
    sp2, _, b2 = correr(definicion, entrada, existentes=sp.activos)
    assert b2["CANTIDAD_YA_EXISTE"] == 4 and sp2.creaciones == []


def test_lote_vacio_valido(definicion, artefacto):
    artefacto["movimientos"] = []
    sp, r, b = correr(definicion, artefacto)
    assert b["ESTADO_LOTE/Value"] == "COMPLETADO" and b["CANTIDAD_RECIBIDA"] == 0
    assert not sp.creaciones
