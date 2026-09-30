"""P7: adaptador Microsoft 365 (LISTS.csv -> artefacto JSON para Power Automate).

El adaptador es una capa separada: LEE LISTS.csv y escribe archivos nuevos en otra carpeta. Estas pruebas no
regeneran ninguna dorada de P6 y no tocan el motor: solo verifican que el artefacto conserva las 26 columnas,
sus valores y la CLAVE TRANSACCIÓN, que los duplicados se distinguen (NUEVO / YA_EXISTE / ERROR) y que la salida es
determinista.
"""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest
from helpers import COLUMNAS_LISTS_CONTRATO, GOLDEN, RAIZ

pytestmark = pytest.mark.m365

RUTA_ADAPTADOR = RAIZ.parent / "adaptador_m365.py"
AHORA = "2026-09-30T12:00:00Z"


def _cargar_adaptador():
    spec = importlib.util.spec_from_file_location("adaptador_m365_bajo_prueba", RUTA_ADAPTADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ad():
    return _cargar_adaptador()


def _filas_csv(ruta):
    """Lectura independiente del CSV (sin usar el adaptador): (encabezado, filas como listas de texto)."""
    texto = Path(ruta).read_bytes().decode("utf-8-sig")
    lector = csv.reader(io.StringIO(texto, newline=""))
    return next(lector), list(lector)


def _sha(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def _en_orden_original(artefacto):
    """Reconstruye todas las filas del archivo fuente (a_cargar + omitidos) en su orden original."""
    omitidos = {o["fila"]: o["valores"] for o in artefacto["omitidos"]}
    it = iter(artefacto["movimientos"])
    total = len(artefacto["movimientos"]) + len(omitidos)
    return [omitidos[n] if n in omitidos else next(it) for n in range(1, total + 1)]


@pytest.fixture(scope="module")
def lote_dorado(ad, tmp_path_factory):
    """Adaptador sobre la dorada LOTE_12_LISTS.csv (4064 movimientos reales de los 12 formatos)."""
    salida = tmp_path_factory.mktemp("p7_dorada")
    r = ad.adaptar(GOLDEN / "LOTE_12_LISTS.csv", salida, ahora=AHORA)
    return r, _leer_json(r["rutas"]["artefacto"]), _leer_json(r["rutas"]["manifiesto"])


def _dos_dec(txt):
    try:
        return f"{float(txt):.2f}"
    except ValueError:
        return txt  # valor intencionalmente invalido en la prueba


def _csv_sintetico(tmp_path, filas, nombre="LISTS.csv", bom=True):
    """CSV con el contrato de 26 columnas: `filas` = lista de dicts parciales; el resto se completa como el motor."""
    base = {
        "CLAVE TRANSACCIÓN": None, "CÓDIGO DE ASIGNACIÓN": "100", "BANCO": "BNB", "CUENTA BANCARIA": "3000100152",
        "MONEDA": "BOB", "FECHA MOVIMIENTO": "2026-08-01", "HORA MOVIMIENTO": "10:00:00", "IMPORTE": "100.0",
        "DÉBITO": "", "CRÉDITO": "100.0", "TIPO MOVIMIENTO": "CRÉDITO", "SALDO": "1100.0",
        "DESCRIPCIÓN": "DEPOSITO ", "DEPOSITANTE / ORIGINANTE": "", "INFORMACIÓN ADICIONAL": "",
        "ESTADO": "DISPONIBLE", "ESTUDIANTE": "", "SOLICITADO POR": "", "SEDE SOLICITANTE": "COCHABAMBA",
        "CONFIRMADO POR": "", "FECHA CONFIRMACIÓN": "", "OBSERVACIÓN": "", "TEXTO DE BÚSQUEDA": "x",
        "ARCHIVO ORIGEN": "a.xls", "LOTE DE CARGA": "20260801_100000", "FECHA DE CARGA": "2026-08-01 10:00:00.5",
    }
    salida = io.StringIO()
    w = csv.writer(salida, lineterminator="\n")
    w.writerow(COLUMNAS_LISTS_CONTRATO)
    for f in filas:
        d = {**base, **f}
        if d["CLAVE TRANSACCIÓN"] is None:
            d["CLAVE TRANSACCIÓN"] = "|".join([
                d["BANCO"], d["CUENTA BANCARIA"], d["FECHA MOVIMIENTO"].replace("-", ""),
                "".join(ch for ch in d["HORA MOVIMIENTO"] if ch.isdigit()), d["CÓDIGO DE ASIGNACIÓN"],
                d["TIPO MOVIMIENTO"], _dos_dec(d["IMPORTE"]), _dos_dec(d["SALDO"]),
            ])
        w.writerow([d[c] for c in COLUMNAS_LISTS_CONTRATO])
    ruta = tmp_path / nombre
    ruta.write_bytes((b"\xef\xbb\xbf" if bom else b"") + salida.getvalue().encode("utf-8"))
    return ruta


# ============================================================ 1. contrato de columnas

def test_p7_tabla_de_columnas_es_exactamente_columnas_lists_del_motor(ad, motor):
    """COLUMNAS_LISTS del motor es la unica fuente de verdad: 26 columnas, mismo nombre y mismo orden."""
    assert list(ad.COLUMNAS_CSV) == list(motor.COLUMNAS_LISTS) == COLUMNAS_LISTS_CONTRATO
    assert len(ad.COLUMNAS_TECNICAS) == 26 and len(set(ad.COLUMNAS_TECNICAS)) == 26


def test_p7_nombres_tecnicos_ascii_y_sin_choque_con_campos_operativos(ad):
    for t in ad.COLUMNAS_TECNICAS:
        assert t.isascii() and t.replace("_", "").isalnum() and t == t.upper(), t
    assert ad.CAMPOS_OPERATIVOS == (
        "ESTADO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION",
        "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "OBSERVACION",
    )
    assert not set(ad.CAMPOS_OPERATIVOS) & set(ad.COLUMNAS_TECNICAS)
    assert ad.ESTADO_ASIGNACION_INICIAL == "DISPONIBLE"


def test_p7_documento_de_diseno_menciona_las_26_columnas_y_los_8_campos_operativos(ad):
    doc = (RAIZ.parent / "DISENO_LISTA_DEPOSITOS_ACTIVOS.md").read_text(encoding="utf-8")
    for csv_nombre, tecnico, _, _ in ad.COLUMNAS_M365:
        assert f"`{tecnico}`" in doc and csv_nombre in doc, tecnico
    for campo in ad.CAMPOS_OPERATIVOS:
        assert f"`{campo}`" in doc, campo


def test_p7_esquema_parse_json_publicado_coincide_con_el_generado(ad):
    publicado = (RAIZ.parent / "esquema_parse_json_p7.json").read_bytes()
    assert publicado == ad.serializar_esquema()


# ============================================================ 2. conservacion de columnas, valores y clave

def test_p7_las_26_columnas_se_conservan(lote_dorado, ad, motor):
    _, art, _ = lote_dorado
    assert art["esquema"] == "P7_DEPOSITOS_ACTIVOS_V1"
    assert art["columnas"] == list(ad.COLUMNAS_TECNICAS)
    for mov in _en_orden_original(art):
        assert list(mov) == list(ad.COLUMNAS_TECNICAS)  # 26 claves, mismo orden, ninguna de mas
    assert not any(c in mov for mov in art["movimientos"][:50] for c in ad.CAMPOS_OPERATIVOS)  # no se emiten operativos


def test_p7_ningun_valor_cambia_respecto_a_lists_csv_dorada(lote_dorado, ad):
    _, art, _ = lote_dorado
    enc, filas = _filas_csv(GOLDEN / "LOTE_12_LISTS.csv")
    assert enc == COLUMNAS_LISTS_CONTRATO
    movs = _en_orden_original(art)
    assert len(movs) == len(filas) == 4064
    for mov, fila in zip(movs, filas):
        assert [mov[t] for t in ad.COLUMNAS_TECNICAS] == fila  # texto EXACTO (espacios finales incluidos)
    assert any(m["DESCRIPCION"].endswith(" ") for m in movs)  # el caso de espacios finales existe en los datos


def test_p7_valores_iguales_a_lists_csv_de_una_corrida_real_del_motor(corrida_lote, ad, tmp_path):
    """Con la salida REAL del motor (ejecutar_motor sobre los 12 fixtures): mismos valores y misma clave."""
    res, salida_motor = corrida_lote
    lists_csv = salida_motor / "LISTS.csv"
    antes = _sha(lists_csv)
    r = ad.adaptar(lists_csv, tmp_path / "m365", ahora=AHORA)
    art = _leer_json(r["rutas"]["artefacto"])
    enc, filas = _filas_csv(lists_csv)
    movs = _en_orden_original(art)
    assert [[m[t] for t in ad.COLUMNAS_TECNICAS] for m in movs] == filas
    assert _sha(lists_csv) == antes  # LISTS.csv de P6 intacto
    # la clave del artefacto es la que calculo el motor (crear_clave), fila por fila
    assert [m["CLAVE_TRANSACCION"] for m in movs] == res["df_final"]["CLAVE TRANSACCIÓN"].tolist()


def test_p7_la_clave_se_conserva_y_es_la_de_crear_clave_del_motor(lote_dorado, motor, corrida_lote):
    """La clave del artefacto == crear_clave(P6) recalculada sobre la fila del motor; el adaptador no la recalcula."""
    _, art, _ = lote_dorado
    res, _ = corrida_lote
    df = res["df_final"]
    recalculadas = df.apply(motor.crear_clave, axis=1).tolist()
    assert recalculadas == df["CLAVE TRANSACCIÓN"].tolist()
    claves_art = [m["CLAVE_TRANSACCION"] for m in art["movimientos"]]
    assert len(set(claves_art)) == len(claves_art) == 4064  # unica en el lote de referencia
    enc, filas = _filas_csv(GOLDEN / "LOTE_12_LISTS.csv")
    assert claves_art == [f[0] for f in filas]


def test_p7_no_toca_lists_csv_ni_escribe_en_su_carpeta(ad, tmp_path):
    ent = tmp_path / "motor"; ent.mkdir()
    origen = _csv_sintetico(ent, [{}])
    antes, listado = _sha(origen), sorted(p.name for p in ent.iterdir())
    ad.adaptar(origen, tmp_path / "m365", ahora=AHORA)
    assert _sha(origen) == antes and sorted(p.name for p in ent.iterdir()) == listado
    with pytest.raises(ad.ContratoError, match="distinta"):
        ad.adaptar(origen, ent, ahora=AHORA)
    assert sorted(p.name for p in ent.iterdir()) == listado


def test_p7_json_utf8_sin_bom_y_acentos_sin_escapar(lote_dorado):
    r, _, _ = lote_dorado
    raw = Path(r["rutas"]["artefacto"]).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "CRÉDITO".encode("utf-8") in raw and b"\\u00c9" not in raw


# ============================================================ 3. duplicados: NUEVO / YA_EXISTE / ERROR

def test_p7_filas_duplicadas_se_identifican(ad, tmp_path):
    a = {"HORA MOVIMIENTO": "10:00:00"}
    b = {"HORA MOVIMIENTO": "11:00:00"}
    ruta = _csv_sintetico(tmp_path, [a, b, a, a])
    r = ad.adaptar(ruta, tmp_path / "o", ahora=AHORA)
    art, man = _leer_json(r["rutas"]["artefacto"]), _leer_json(r["rutas"]["manifiesto"])
    assert [m["HORA_MOVIMIENTO"] for m in art["movimientos"]] == ["10:00:00", "11:00:00"]  # primera aparicion
    assert [(o["fila"], o["estado"], o["motivo"]) for o in art["omitidos"]] == [
        (3, "YA_EXISTE", "REPETIDA_EN_LOTE"), (4, "YA_EXISTE", "REPETIDA_EN_LOTE")]
    assert (man["cantidad_recibida"], man["cantidad_valida"], man["cantidad_a_cargar"],
            man["cantidad_repetida_en_lote"], man["cantidad_error"]) == (4, 4, 2, 2, 0)


def test_p7_clasificacion_nuevo_ya_existe_error(ad, tmp_path):
    filas = [
        {"HORA MOVIMIENTO": "10:00:00"},                                   # 1 nuevo
        {"HORA MOVIMIENTO": "11:00:00"},                                   # 2 ya esta en la lista
        {"HORA MOVIMIENTO": "10:00:00"},                                   # 3 repetida dentro del archivo
        {"HORA MOVIMIENTO": "12:00:00", "IMPORTE": "abc"},                 # 4 error (importe no numerico)
        {"HORA MOVIMIENTO": "13:00:00", "BANCO": ""},                      # 5 error (obligatorio vacio)
        {"HORA MOVIMIENTO": "14:00:00", "CLAVE TRANSACCIÓN": "BNB|x|1"},   # 6 error (clave mal formada)
        {"HORA MOVIMIENTO": "15:00:00", "SALDO": "9.0", "CLAVE TRANSACCIÓN": "BNB|3000100152|20260801|150000|100|CRÉDITO|100.00|1100.00"},  # 7 clave incoherente con SALDO
    ]
    ruta = _csv_sintetico(tmp_path, filas)
    movs, _, _ = ad.leer_lists_csv(ruta)
    a_cargar, omitidos = ad.separar_lote(movs)
    existentes = {movs[1]["CLAVE_TRANSACCION"]}
    clasif = ad.clasificar(a_cargar, omitidos, existentes)
    assert [(c["fila"], c["estado"]) for c in clasif] == [
        (1, "NUEVO"), (2, "YA_EXISTE"), (3, "YA_EXISTE"), (4, "ERROR"), (5, "ERROR"), (6, "ERROR"), (7, "ERROR")]
    assert clasif[1]["motivo"] == "EN_LISTA" and clasif[2]["motivo"] == "REPETIDA_EN_LOTE"
    assert "NUMERO_INVALIDO:IMPORTE" in clasif[3]["motivo"] and "OBLIGATORIO_VACIO:BANCO" in clasif[4]["motivo"]
    assert clasif[5]["motivo"] == "CLAVE_FORMATO" and clasif[6]["motivo"] == "CLAVE_INCOHERENTE"
    # los ERROR nunca viajan en `movimientos` (no se envian a la lista)
    assert [m["HORA_MOVIMIENTO"] for m in a_cargar] == ["10:00:00", "11:00:00"]


def test_p7_reprocesar_el_mismo_archivo_no_genera_nuevos(ad):
    """Simula dos cargas del mismo LISTS.csv: 1a carga todo NUEVO; 2a carga (claves ya en la lista) todo YA_EXISTE."""
    movs, _, _ = ad.leer_lists_csv(GOLDEN / "LOTE_12_LISTS.csv")
    a_cargar, omitidos = ad.separar_lote(movs)
    lista = set()
    c1 = ad.clasificar(a_cargar, omitidos, lista)
    assert {c["estado"] for c in c1} == {"NUEVO"} and len(c1) == 4064
    lista |= {c["clave"] for c in c1 if c["estado"] == "NUEVO"}
    c2 = ad.clasificar(a_cargar, omitidos, lista)
    assert {c["estado"] for c in c2} == {"YA_EXISTE"} and len(lista) == 4064


def test_p7_lote_solapado_solo_agrega_los_movimientos_nuevos(ad, tmp_path):
    """Un extracto que repite dias ya cargados (rango solapado) solo aporta lo que no estaba."""
    filas = [{"HORA MOVIMIENTO": f"{h}:00:00"} for h in ("08", "09", "10", "11")]
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    r1 = ad.adaptar(_csv_sintetico(tmp_path / "a", filas[:3]), tmp_path / "o1", ahora=AHORA)
    cargadas = {m["CLAVE_TRANSACCION"] for m in _leer_json(r1["rutas"]["artefacto"])["movimientos"]}
    r2 = ad.adaptar(_csv_sintetico(tmp_path / "b", filas[1:]), tmp_path / "o2", ahora=AHORA, claves_existentes=cargadas)
    estados = [(c["fila"], c["estado"]) for c in r2["clasificacion"]]
    assert estados == [(1, "YA_EXISTE"), (2, "YA_EXISTE"), (3, "NUEVO")]
    lineas = Path(r2["rutas"]["clasificacion"]).read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "FILA,CLAVE TRANSACCIÓN,ESTADO,MOTIVO" and len(lineas) == 4


def test_p7_claves_existentes_desde_archivo_de_texto(ad, tmp_path):
    (tmp_path / "k.txt").write_text("BNB|a|1\r\nBNB|b|2\n\n", encoding="utf-8")
    assert ad.leer_claves_existentes(tmp_path / "k.txt") == {"BNB|a|1", "BNB|b|2"}


# ============================================================ 4. determinismo

def test_p7_dos_ejecuciones_sobre_la_misma_entrada_son_identicas(ad, tmp_path):
    e = GOLDEN / "LOTE_12_LISTS.csv"
    r1 = ad.adaptar(e, tmp_path / "1", ahora=AHORA)
    r2 = ad.adaptar(e, tmp_path / "2", ahora=AHORA)
    assert r1["lote_id"] == r2["lote_id"]
    for k in ("artefacto", "manifiesto"):
        assert Path(r1["rutas"][k]).name == Path(r2["rutas"][k]).name
        assert Path(r1["rutas"][k]).read_bytes() == Path(r2["rutas"][k]).read_bytes()


def test_p7_sin_ahora_solo_cambia_la_marca_de_tiempo_del_manifiesto(ad, tmp_path):
    e = GOLDEN / "LOTE_12_LISTS.csv"
    r1 = ad.adaptar(e, tmp_path / "1", ahora="2026-01-01T00:00:00Z")
    r2 = ad.adaptar(e, tmp_path / "2")
    assert Path(r1["rutas"]["artefacto"]).read_bytes() == Path(r2["rutas"]["artefacto"]).read_bytes()
    m1, m2 = _leer_json(r1["rutas"]["manifiesto"]), _leer_json(r2["rutas"]["manifiesto"])
    assert m1.pop("generado_en") != m2.pop("generado_en") and m1 == m2


def test_p7_re_ejecutar_en_la_misma_carpeta_sobrescribe_sin_acumular(ad, tmp_path):
    e = GOLDEN / "LOTE_12_LISTS.csv"
    ad.adaptar(e, tmp_path / "o", ahora=AHORA)
    ad.adaptar(e, tmp_path / "o", ahora=AHORA)
    assert len(list((tmp_path / "o").iterdir())) == 2


def test_p7_el_lote_cambia_si_cambia_el_contenido_del_archivo(ad, tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    a = ad.adaptar(_csv_sintetico(tmp_path / "a", [{}]), tmp_path / "o1", ahora=AHORA)
    b = ad.adaptar(_csv_sintetico(tmp_path / "b", [{"HORA MOVIMIENTO": "11:00:00"}]), tmp_path / "o2", ahora=AHORA)
    assert a["lote_id"] != b["lote_id"] and a["lote_id"].startswith("P7-")


# ============================================================ 5. manifiesto

def test_p7_manifiesto_del_lote_dorado(lote_dorado, ad):
    r, art, man = lote_dorado
    enc, filas = _filas_csv(GOLDEN / "LOTE_12_LISTS.csv")
    idx = {c: i for i, c in enumerate(enc)}
    assert man["esquema"] == "P7_MANIFIESTO_V1" and man["lote_id"] == art["lote_id"] == r["lote_id"]
    assert man["generado_en"] == AHORA
    assert man["archivo_fuente"] == "LOTE_12_LISTS.csv" == art["archivo_fuente"]
    assert man["sha256_archivo_fuente"] == _sha(GOLDEN / "LOTE_12_LISTS.csv") == art["sha256_archivo_fuente"]
    assert man["lote_id"] == "P7-" + man["sha256_archivo_fuente"][:12]
    assert man["bytes_archivo_fuente"] == (GOLDEN / "LOTE_12_LISTS.csv").stat().st_size
    assert (man["cantidad_recibida"], man["cantidad_valida"], man["cantidad_a_cargar"]) == (4064, 4064, 4064)
    assert (man["cantidad_repetida_en_lote"], man["cantidad_error"]) == (0, 0)
    fechas = sorted(f[idx["FECHA MOVIMIENTO"]] for f in filas)
    assert man["rango_fechas"] == {"desde": fechas[0], "hasta": fechas[-1]}
    assert man["bancos"] == sorted({f[idx["BANCO"]] for f in filas})
    cuentas = {(c["banco"], c["cuenta"], c["moneda"]): c["movimientos"] for c in man["cuentas"]}
    assert len(cuentas) == 11 and sum(cuentas.values()) == 4064  # BISA_ME no tiene movimientos
    assert man["archivos_origen"] == sorted({f[idx["ARCHIVO ORIGEN"]] for f in filas})
    assert man["lotes_motor"] == sorted({f[idx["LOTE DE CARGA"]] for f in filas})
    assert man["artefacto"] == {"archivo": Path(r["rutas"]["artefacto"]).name,
                                "sha256": _sha(r["rutas"]["artefacto"])}


def test_p7_manifiesto_cuenta_errores_y_repetidas(ad, tmp_path):
    ruta = _csv_sintetico(tmp_path, [{}, {}, {"IMPORTE": "x"}, {"HORA MOVIMIENTO": "11:00:00"}])
    man = _leer_json(ad.adaptar(ruta, tmp_path / "o", ahora=AHORA)["rutas"]["manifiesto"])
    assert (man["cantidad_recibida"], man["cantidad_valida"], man["cantidad_a_cargar"],
            man["cantidad_repetida_en_lote"], man["cantidad_error"]) == (4, 3, 2, 1, 1)
    assert man["archivo_fuente"] == "LISTS.csv" and man["rango_fechas"] == {"desde": "2026-08-01", "hasta": "2026-08-01"}


# ============================================================ 6. contrato y casos borde

def test_p7_encabezado_distinto_no_genera_nada(ad, tmp_path):
    ruta = tmp_path / "LISTS.csv"
    ruta.write_text("A,B\n1,2\n", encoding="utf-8")
    with pytest.raises(ad.ContratoError, match="COLUMNAS_LISTS"):
        ad.adaptar(ruta, tmp_path / "o", ahora=AHORA)
    assert not (tmp_path / "o").exists()


def test_p7_fila_con_numero_de_campos_incorrecto_no_genera_nada(ad, tmp_path):
    ruta = _csv_sintetico(tmp_path, [{}])
    ruta.write_text(ruta.read_text(encoding="utf-8-sig") + "solo,dos\n", encoding="utf-8")
    with pytest.raises(ad.ContratoError, match="campos"):
        ad.adaptar(ruta, tmp_path / "o", ahora=AHORA)
    assert not (tmp_path / "o").exists()


def test_p7_lists_csv_solo_encabezado_es_un_lote_vacio_valido(ad, tmp_path):
    """Caso real: extracto sin movimientos. El flujo debe poder recibirlo y registrar 0 sin fallar."""
    r = ad.adaptar(_csv_sintetico(tmp_path, []), tmp_path / "o", ahora=AHORA)
    art, man = _leer_json(r["rutas"]["artefacto"]), _leer_json(r["rutas"]["manifiesto"])
    assert art["movimientos"] == [] and art["omitidos"] == []
    assert man["cantidad_recibida"] == 0 and man["rango_fechas"] is None and man["bancos"] == []


def test_p7_csv_con_y_sin_bom_producen_el_mismo_artefacto(ad, tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    con = ad.leer_lists_csv(_csv_sintetico(tmp_path / "a", [{}], bom=True))[0]
    sin = ad.leer_lists_csv(_csv_sintetico(tmp_path / "b", [{}], bom=False))[0]
    assert con == sin


def test_p7_valores_con_comas_comillas_y_saltos_de_linea_se_conservan(ad, tmp_path):
    raro = 'DEPOSITO "A", B\nlinea 2  '
    ruta = _csv_sintetico(tmp_path, [{"DESCRIPCIÓN": raro, "INFORMACIÓN ADICIONAL": "ñ; é | ü"}])
    art = _leer_json(ad.adaptar(ruta, tmp_path / "o", ahora=AHORA)["rutas"]["artefacto"])
    assert art["movimientos"][0]["DESCRIPCION"] == raro
    assert art["movimientos"][0]["INFORMACION_ADICIONAL"] == "ñ; é | ü"


def test_p7_texto_de_una_linea_mayor_a_255_es_error_y_el_largo_admite_mas(ad, tmp_path):
    ruta = _csv_sintetico(tmp_path, [
        {"HORA MOVIMIENTO": "10:00:00", "ARCHIVO ORIGEN": "a" * 256},
        {"HORA MOVIMIENTO": "11:00:00", "DESCRIPCIÓN": "d" * 5000},
    ])
    art = _leer_json(ad.adaptar(ruta, tmp_path / "o", ahora=AHORA)["rutas"]["artefacto"])
    assert [o["motivo"] for o in art["omitidos"]] == ["LONGITUD_EXCEDIDA:ARCHIVO_ORIGEN"]
    assert len(art["movimientos"]) == 1 and len(art["movimientos"][0]["DESCRIPCION"]) == 5000


def test_p7_hora_vacia_es_valida_como_en_banco_union(lote_dorado):
    _, art, _ = lote_dorado
    sin_hora = [m for m in art["movimientos"] if m["HORA_MOVIMIENTO"] == ""]
    assert len(sin_hora) == 32 and {m["BANCO"] for m in sin_hora} == {"BANCO UNIÓN"}


def test_p7_cli_escribe_artefacto_y_esquema_y_devuelve_codigos(ad, tmp_path, capsys):
    ruta = _csv_sintetico(tmp_path, [{}])
    assert ad.main([str(ruta), str(tmp_path / "o"), "--ahora", AHORA]) == 0
    assert len(list((tmp_path / "o").iterdir())) == 2
    assert ad.main(["--esquema", str(tmp_path / "esq.json")]) == 0
    assert json.loads((tmp_path / "esq.json").read_text(encoding="utf-8"))["type"] == "object"
    (tmp_path / "mal.csv").write_text("A\n1\n", encoding="utf-8")
    assert ad.main([str(tmp_path / "mal.csv"), str(tmp_path / "o2")]) == 2
    assert "ERROR de contrato" in capsys.readouterr().err


def test_p7_esquema_declara_las_26_columnas_como_texto(ad):
    esq = ad.esquema_parse_json()
    fila = esq["properties"]["movimientos"]["items"]
    assert list(fila["properties"]) == list(ad.COLUMNAS_TECNICAS)
    assert all(v == {"type": "string"} for v in fila["properties"].values())
    assert fila["required"] == list(ad.COLUMNAS_TECNICAS)


# ============================================================ 6b. contrato P6: validacion fail-fast

def _motor_falso(ruta, columnas_src):
    ruta.write_text(f"import pandas as pd\n\nCOLUMNAS_LISTS = {columnas_src}\n", encoding="utf-8")
    return ruta


def test_p7_contrato_esperado_es_exactamente_el_de_p6(ad, motor):
    assert list(ad.COLUMNAS_LISTS_P6) == list(motor.COLUMNAS_LISTS) == COLUMNAS_LISTS_CONTRATO
    assert len(ad.COLUMNAS_LISTS_P6) == 26
    assert ad.columnas_lists_del_motor(RAIZ.parent / "motor_control_depositos_cbba.py") == ad.COLUMNAS_LISTS_P6


def test_p7_verificar_contrato_contra_el_motor_real(ad):
    assert ad.verificar_contrato() == ad.CONTRATO_VERIFICADO_CONTRA_MOTOR


def test_p7_adaptar_informa_que_el_contrato_fue_verificado(ad, tmp_path):
    r = ad.adaptar(_csv_sintetico(tmp_path, [{}]), tmp_path / "o", ahora=AHORA)
    assert r["contrato"] == "VERIFICADO_CONTRA_MOTOR"


def test_p7_motor_ausente_no_bloquea_pero_se_informa(ad, tmp_path):
    (tmp_path / "e").mkdir()
    r = ad.adaptar(_csv_sintetico(tmp_path / "e", [{}]), tmp_path / "o", ahora=AHORA,
                   ruta_motor=tmp_path / "no_existe.py")
    assert r["contrato"] == "MOTOR_NO_DISPONIBLE"


def _mapeo_alterado(ad, cambio):
    return tuple(cambio(list(ad.COLUMNAS_M365)))


def test_p7_deriva_en_la_tabla_del_adaptador_detiene_todo(ad, monkeypatch, tmp_path):
    ent = tmp_path / "e"; ent.mkdir()
    ruta = _csv_sintetico(ent, [{}])

    def permutar(t): t[0], t[1] = t[1], t[0]; return t
    def renombrar(t): t[2] = ("BANCOS",) + t[2][1:]; return t
    def quitar(t): del t[5]; return t
    def duplicar(t): t.append(t[0]); return t

    for i, cambio in enumerate((permutar, renombrar, quitar, duplicar)):
        monkeypatch.setattr(ad, "COLUMNAS_M365", _mapeo_alterado(ad, cambio))
        with pytest.raises(ad.ContratoError, match="COLUMNAS_M365"):
            ad.adaptar(ruta, tmp_path / f"o{i}", ahora=AHORA)
        assert not (tmp_path / f"o{i}").exists()  # no se escribio nada
    monkeypatch.undo()
    assert ad.verificar_contrato()


def test_p7_el_error_de_contrato_nombra_la_desviacion(ad, monkeypatch):
    def cambio(t): t[2] = ("BANCOS",) + t[2][1:]; return t
    monkeypatch.setattr(ad, "COLUMNAS_M365", _mapeo_alterado(ad, cambio))
    with pytest.raises(ad.ContratoError) as e:
        ad.verificar_contrato()
    assert "faltan ['BANCO']" in str(e.value) and "sobran ['BANCOS']" in str(e.value)


def test_p7_nombre_tecnico_que_choca_con_campo_operativo_detiene_todo(ad, monkeypatch):
    def cambio(t):
        i = [c[1] for c in t].index("MOTOR_ESTUDIANTE")
        t[i] = (t[i][0], "ESTUDIANTE") + t[i][2:]
        return t
    monkeypatch.setattr(ad, "COLUMNAS_M365", _mapeo_alterado(ad, cambio))
    with pytest.raises(ad.ContratoError, match="operativos"):
        ad.verificar_contrato()


def test_p7_deriva_en_columnas_lists_del_motor_detiene_todo(ad, tmp_path):
    ent = tmp_path / "e"; ent.mkdir()
    ruta = _csv_sintetico(ent, [{}])
    cols = list(ad.COLUMNAS_LISTS_P6)
    casos = {
        "columna_de_mas": cols + ["NUEVA COLUMNA"],
        "columna_de_menos": cols[:-1],
        "orden_distinto": [cols[1], cols[0]] + cols[2:],
        "renombrada": cols[:5] + ["FECHA DEL MOVIMIENTO"] + cols[6:],
    }
    for nombre, c in casos.items():
        motor_falso = _motor_falso(tmp_path / f"motor_{nombre}.py", repr(c))
        with pytest.raises(ad.ContratoError, match="COLUMNAS_LISTS del motor"):
            ad.adaptar(ruta, tmp_path / f"o_{nombre}", ahora=AHORA, ruta_motor=motor_falso)
        assert not (tmp_path / f"o_{nombre}").exists()


def test_p7_motor_sin_columnas_lists_o_ilegible_detiene_todo(ad, tmp_path):
    sin = tmp_path / "sin.py"; sin.write_text("X = 1\n", encoding="utf-8")
    roto = tmp_path / "roto.py"; roto.write_text("COLUMNAS_LISTS = [\n", encoding="utf-8")
    dinamico = tmp_path / "dinamico.py"; dinamico.write_text("COLUMNAS_LISTS = [c for c in 'ab']\n", encoding="utf-8")
    for ruta in (sin, roto, dinamico):
        with pytest.raises(ad.ContratoError, match="motor|COLUMNAS_LISTS"):
            ad.verificar_contrato(ruta)


def test_p7_cli_con_deriva_de_contrato_sale_con_error_y_no_escribe(ad, monkeypatch, tmp_path, capsys):
    ent = tmp_path / "e"; ent.mkdir()
    ruta = _csv_sintetico(ent, [{}])
    def cambio(t): del t[5]; return t
    monkeypatch.setattr(ad, "COLUMNAS_M365", _mapeo_alterado(ad, cambio))
    assert ad.main([str(ruta), str(tmp_path / "o"), "--ahora", AHORA]) == 2
    assert ad.main(["--esquema", str(tmp_path / "esq.json")]) == 2
    err = capsys.readouterr().err
    assert err.count("ERROR de contrato") == 2 and "COLUMNAS_M365" in err
    assert not (tmp_path / "o").exists() and not (tmp_path / "esq.json").exists()


def test_p7_encabezado_de_lists_csv_desviado_nombra_la_diferencia(ad, tmp_path):
    ruta = tmp_path / "LISTS.csv"
    cols = list(ad.COLUMNAS_LISTS_P6)
    ruta.write_text(",".join(cols[:-1]) + ",OTRA\n", encoding="utf-8")
    with pytest.raises(ad.ContratoError) as e:
        ad.leer_lists_csv(ruta)
    assert "faltan ['FECHA DE CARGA']" in str(e.value) and "sobran ['OTRA']" in str(e.value)


def test_p7_verificar_contrato_no_modifica_el_motor(ad):
    motor_py = RAIZ.parent / "motor_control_depositos_cbba.py"
    antes = _sha(motor_py)
    ad.verificar_contrato()
    assert _sha(motor_py) == antes


# ============================================================ 6c. documentacion: bitacora Depositos_Cargas

BITACORA_CAMPOS = ("LOTE_ID", "FECHA_HORA_PROCESO", "ARCHIVO_FUENTE", "SHA256", "CANTIDAD_RECIBIDA", "CANTIDAD_VALIDA",
                   "CANTIDAD_NUEVA", "CANTIDAD_YA_EXISTE", "CANTIDAD_ERROR", "ESTADO_LOTE", "MENSAJE_ERROR")


def test_p7_especificacion_del_flujo_define_la_bitacora_depositos_cargas():
    esp = (RAIZ.parent / "ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md").read_text(encoding="utf-8")
    dis = (RAIZ.parent / "DISENO_LISTA_DEPOSITOS_ACTIVOS.md").read_text(encoding="utf-8")
    assert "Depositos_Cargas" in esp and "Depositos_Cargas" in dis
    for campo in BITACORA_CAMPOS:
        assert f"`{campo}`" in esp, campo
    for estado in ("COMPLETADO", "COMPLETADO_CON_ERRORES", "FALLIDO"):
        assert f"`{estado}`" in esp


def test_p7_documentacion_declara_que_no_certifica_la_integracion_end_to_end():
    for nombre in ("README.md", "DISENO_LISTA_DEPOSITOS_ACTIVOS.md",
                   "ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md"):
        txt = (RAIZ.parent / nombre).read_text(encoding="utf-8")
        assert "NO certifica" in txt and "end-to-end" in txt, nombre


# ============================================================ 7. ejemplo publicado

def test_p7_ejemplo_publicado_se_regenera_identico_desde_su_lists_csv(ad, tmp_path):
    """ejemplos_p7/ (BCP_ME real, 8 movimientos): los archivos M365 versionados son los que produce el adaptador."""
    base = RAIZ.parent / "ejemplos_p7"
    r = ad.adaptar(base / "motor" / "LISTS.csv", tmp_path / "o", ahora=AHORA)
    for k in ("artefacto", "manifiesto"):
        publicado = base / "m365" / Path(r["rutas"][k]).name
        assert publicado.read_bytes() == Path(r["rutas"][k]).read_bytes()
    assert len(list((base / "m365").iterdir())) == 2
