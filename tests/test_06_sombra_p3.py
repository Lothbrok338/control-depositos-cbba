"""P3: registro_bancos.json + motor_generico.py en MODO SOMBRA.

Reglas que estas pruebas protegen:
  * el motor genérico NO produce salida: la producción sigue siendo la del legado;
  * cualquier diferencia genérico ↔ legado queda REPORTADA (SOMBRA_REPORTE.json / SOMBRA_DIFERENCIAS.csv);
  * un fallo del motor genérico no detiene ni altera al legado;
  * una cuenta nueva de un formato conocido se agrega por configuración, sin lógica bancaria nueva;
  * el genérico no reutiliza la lógica bancaria del legado (detección, encabezados, normalizar_*, validar_archivo).
"""
import ast
import copy
import importlib.util
import json
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from helpers import (CONTRATO, EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN, RAIZ, UNION_ULTIMOS12, a_texto,
                     crear_xlsx_bmsc_otra_cuenta, crear_xlsx_bnb, crear_xlsx_union_me_con_movimiento,
                     crear_xlsx_union_me_vacio)

pytestmark = pytest.mark.sombra

REPO = RAIZ.parent
TS = pd.Timestamp("2026-01-01 00:00:00")
FIJO = pd.Timestamp("2026-08-21 09:00:00")


# ------------------------------- fixtures -------------------------------
@pytest.fixture(scope="session")
def mg():
    spec = importlib.util.spec_from_file_location("motor_generico_bajo_prueba", REPO / "motor_generico.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # dataclasses necesita el modulo registrado
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def registro(mg):
    return mg.Registro.cargar(REPO / "registro_bancos.json")


@pytest.fixture(scope="session")
def generico(mg, registro, motor):
    return mg.MotorGenerico(registro, motor)


def _sombra_fixture(mg, gen, motor, normalizado, ruta_fixture, fm):
    df, val = normalizado[fm]
    return mg.sombra_archivo(gen, FIXTURES[fm], ruta_fixture(fm), fm, "LOTE_TEST", TS,
                             tabla_legado=df, validacion_legado=val)


# ------------------------------- 1. REGISTRO -------------------------------
def test_registro_es_valido(registro):
    assert registro.validar() == []


def test_registro_tiene_las_13_cuentas_actuales_y_coinciden_con_el_contrato(registro):
    ids = {c["id"] for c in registro.cuentas}
    assert ids == set(CONTRATO) and len(registro.cuentas) == 13
    for c in registro.cuentas:
        assert (c["banco"], c["cuenta"], c["moneda"]) == CONTRATO[c["id"]], c["id"]
        assert c["activa"] is True


def test_registro_hojas_y_encabezados_coinciden_con_las_constantes_del_legado(registro, motor):
    """El registro reproduce HOJAS_VALIDAS y ENCABEZADOS_ESPERADOS (solo lectura del legado)."""
    for c in registro.cuentas:
        fmt = registro.formato(c["formato"])
        assert motor.HOJAS_VALIDAS[c["id"]] in fmt["hojas_aceptadas"], c["id"]
        assert fmt["encabezados"]["puntaje"] == motor.ENCABEZADOS_ESPERADOS[c["id"]], c["id"]


def test_registro_formatos_de_la_misma_familia_se_comparten(registro):
    por_formato = {}
    for c in registro.cuentas:
        por_formato.setdefault(c["formato"], []).append(c["id"])
    assert por_formato == {
        "BISA_EXTRACTO_V1": ["BISA_MN", "BISA_ME"],
        "BNB_EXTRACTO_V1": ["BNB_MN", "BNB_ME", "BNB_AHORRO", "BNB_CLINICA"],
        "BCP_EXTRACTO_V1": ["BCP_MN", "BCP_ME"],
        "UNION_FECHAS_V1": ["UNION_MN", "UNION_ME"],
        "ECO_EXTRACTO_V1": ["ECO_CTA_CTE", "ECO_AHORRO"],
        "BMSC_EXCEL_V1": ["BMSC"],
    }
    assert registro.formato("UNION_ULTIMOS12_V1")["aceptado"] is False


def _mutar(registro, fn):
    d = copy.deepcopy(registro.datos)
    fn(d)
    return d


MUTACIONES_INVALIDAS = {
    "id_duplicado": lambda d: d["CUENTAS"].append(dict(d["CUENTAS"][0], cuenta="1234567")),
    "formato_inexistente": lambda d: d["CUENTAS"][0].update(formato="NO_EXISTE"),
    "misma_cuenta_y_formato": lambda d: d["CUENTAS"].append(dict(d["CUENTAS"][2], id="OTRA")),
    "cuenta_contenida_en_otra": lambda d: d["CUENTAS"].append(
        {"id": "X", "formato": "BNB_EXTRACTO_V1", "banco": "BNB", "cuenta": "300010015", "moneda": "BOB"}),
    "cuenta_a_formato_no_aceptado": lambda d: d["CUENTAS"].append(
        {"id": "X", "formato": "UNION_ULTIMOS12_V1", "banco": "U", "cuenta": "1", "moneda": "BOB"}),
    "cuenta_sin_moneda": lambda d: d["CUENTAS"][0].update(moneda=""),
    "falta_rol_obligatorio": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["campos"].pop("SALDO"),
    "puntaje_minimo_invalido": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["encabezados"].update(puntaje_minimo=0),
    "modo_importe_invalido": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["importe"].update(modo="OTRO"),
    "depositante_campo_inexistente": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["depositante"].update(campo="NADA"),
    "info_campo_inexistente": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["info_adicional"]["partes"].append({"campo": "NADA"}),
    "filtro_fecha_invalido": lambda d: d["FORMATOS"]["ECO_EXTRACTO_V1"].update(filtro_fecha="OTRO"),
    "firma_vacia": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"].update(firma={}),
    "fuente_saldo_invalida": lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["saldo"]["inicial"].update(fuente="MAGIA"),
    "formato_no_aceptado_sin_mensaje": lambda d: d["FORMATOS"]["UNION_ULTIMOS12_V1"].pop("mensaje"),
}


@pytest.mark.parametrize("nombre", list(MUTACIONES_INVALIDAS))
def test_registro_invalido_se_detecta(mg, registro, nombre):
    reg = mg.Registro(_mutar(registro, MUTACIONES_INVALIDAS[nombre]))
    assert reg.validar(), f"la mutación '{nombre}' debió invalidar el registro"


def test_registro_json_roto_falla_con_mensaje(mg, tmp_path):
    ruta = tmp_path / "r.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    with pytest.raises(mg.RegistroError):
        mg.Registro.cargar(ruta)


# ------------------------------- 2. INDEPENDENCIA DEL LEGADO -------------------------------
PROHIBIDOS = {
    "detectar_formato", "encontrar_fila_encabezado", "leer_tabla_movimientos", "validar_archivo",
    "normalizar_archivo", "normalizar_bnb", "normalizar_bcp", "normalizar_union", "normalizar_economico",
    "normalizar_bisa", "normalizar_bmsc", "texto_de_archivo", "descubrir_archivos", "ejecutar_motor",
    "ENCABEZADOS_ESPERADOS", "HOJAS_VALIDAS",
}


def test_motor_generico_no_usa_la_logica_bancaria_del_legado():
    """El registro y el motor genérico (clases Registro y MotorGenerico) no nombran la lógica del legado.
    Solo la parte de COMPARACIÓN (comparar_carpeta / cargar_legado) puede llamarla, porque compara contra ella."""
    arbol = ast.parse((REPO / "motor_generico.py").read_text(encoding="utf-8"))
    usados = set()
    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef) and nodo.name in ("Registro", "MotorGenerico"):
            for n in ast.walk(nodo):
                if isinstance(n, ast.Name):
                    usados.add(n.id)
                elif isinstance(n, ast.Attribute):
                    usados.add(n.attr)
                elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                    usados.add(n.value)
    assert usados & PROHIBIDOS == set()


def test_primitivas_compartidas_son_solo_conversion_y_lectura(mg):
    """Las primitivas que el genérico toma del legado no contienen lógica por banco (salvo la estrategia con nombre)."""
    assert set(mg.PRIMITIVAS_LEGADO) == {
        "COLUMNAS_LISTS", "normalizar_texto", "buscar_columna", "buscar_columna_opcional", "numero", "codigo_texto",
        "normalizar_fecha", "normalizar_hora", "leer_excel_robusto", "leer_todas_hojas", "finalizar_dataframe",
        "ecuacion_saldo", "extraer_nombre_bnb"}    # extraer_nombre_bnb = estrategia 'legacy_bnb' (D-18/D-19 sin tocar)


def test_registro_no_se_modifica_al_procesar(registro, generico, ruta_fixture):
    antes = json.dumps(registro.datos, sort_keys=True)
    generico.procesar(ruta_fixture("BNB_ME"), "L", TS, nombre_origen="x")
    assert json.dumps(registro.datos, sort_keys=True) == antes


# ------------------------------- 3. SOMBRA: 12 FORMATOS REALES -------------------------------
@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_sombra_formato_coincide_al_100_con_el_legado(mg, generico, motor, normalizado, ruta_fixture, formato):
    """Detección + movimientos normalizados (26 columnas, índice, valores, tipos) + validación de saldos."""
    r = _sombra_fixture(mg, generico, motor, normalizado, ruta_fixture, formato)
    assert r["diferencias"] == [], r["diferencias"][:5]
    assert r["estado"] == "COINCIDE" and r["cuenta_generico"] == formato
    assert r["movimientos_generico"] == r["movimientos_legado"]


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_sombra_generico_reproduce_la_dorada(generico, ruta_fixture, formato):
    """Independiente del legado: el genérico reproduce la referencia dorada congelada."""
    g = generico.procesar(ruta_fixture(formato), "LOTE_TEST", TS, nombre_origen=FIXTURES[formato])
    if len(g.df) == 0:
        pytest.skip("extracto sin movimientos: sin filas que comparar con la dorada")
    assert a_texto(g.df) == (GOLDEN / f"{formato}.csv").read_text(encoding="utf-8")


@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_generico_identidad_banco_cuenta_moneda_siempre_completa(generico, ruta_fixture, formato):
    """También para un extracto válido SIN movimientos (BISA_ME), donde el DataFrame legado queda vacío."""
    g = generico.procesar(ruta_fixture(formato), "L", TS, nombre_origen=FIXTURES[formato])
    banco, cuenta, moneda = CONTRATO[formato]
    assert (g.identidad["BANCO"], g.identidad["CUENTA BANCARIA"], g.identidad["MONEDA"]) == (banco, cuenta, moneda)
    assert g.identidad["CUENTA_ID"] == formato


def test_sombra_bisa_me_sin_movimientos_deja_df_vacio_como_el_legado(generico, ruta_fixture):
    g = generico.procesar(ruta_fixture("BISA_ME"), "L", TS, nombre_origen="bisa_me_2.xls")
    assert g.sin_movimientos and len(g.df) == 0
    assert g.identidad["CUENTA BANCARIA"] == "0696872023" and g.validacion["ESTADO"] == "OK"


def test_generico_es_determinista(generico, ruta_fixture):
    a = generico.procesar(ruta_fixture("BCP_MN"), "L", TS, nombre_origen="x")
    b = generico.procesar(ruta_fixture("BCP_MN"), "L", TS, nombre_origen="x")
    pd.testing.assert_frame_equal(a.df, b.df)
    assert a.validacion == b.validacion


# ------------------------------- 4. CAMPO_CANONICO -------------------------------
@pytest.mark.parametrize("formato", FORMATOS_OK)
def test_campo_canonico_cubre_todos_los_encabezados_reales(generico, registro, motor, ruta_fixture, formato):
    """Cada encabezado de tabla que entrega el banco tiene etiqueta común en el registro."""
    ruta = ruta_fixture(formato)
    hojas = motor.leer_todas_hojas(ruta)
    fmt = registro.formato(registro.cuenta(formato)["formato"])
    hoja = generico._hoja_aceptada(hojas, fmt)
    fila, _, _ = generico._fila_encabezado(hojas[hoja], fmt["encabezados"]["puntaje"])
    encabezados = [str(x) for x in hojas[hoja].loc[fila].tolist() if pd.notna(x) and str(x).strip()]
    assert encabezados
    sin = [e for e in encabezados
           if not registro.campo_canonico(registro.cuenta(formato)["formato"], e, motor.normalizar_texto)]
    assert sin == [], f"encabezados sin CAMPO_CANONICO en {formato}: {sin}"


def test_campo_canonico_ejemplos(registro, motor):
    n = motor.normalizar_texto
    assert registro.campo_canonico("BNB_EXTRACTO_V1", "Referencia", n) == "REFERENCIA"
    assert registro.campo_canonico("BNB_EXTRACTO_V1", "  código  de transacción ", n) == "CODIGO_TRANSACCION"
    assert registro.campo_canonico("BMSC_EXCEL_V1", "Nom.Destinatario", n) == "DESTINATARIO_NOMBRE"
    assert registro.campo_canonico("UNION_FECHAS_V1", "Nro de verificasion", n) == "NRO_VERIFICACION"
    assert registro.campo_canonico("BCP_EXTRACTO_V1", "Suc. Age.", n) == "SUCURSAL_AGENCIA"
    assert registro.campo_canonico("BNB_EXTRACTO_V1", "Columna nueva del banco", n) == ""


# ------------------------------- 5. CUENTA NUEVA POR CONFIGURACIÓN -------------------------------
def test_cuenta_nueva_de_formato_conocido_se_agrega_solo_con_configuracion(mg, registro, motor, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "nueva.xlsx", "9999999999", [
        {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0},
        {"fecha": "02/08/2026", "deb": 30.0, "saldo": 1070.0}])
    # sin registrar: se rechaza con motivo explícito (y el legado tambien la rechaza)
    sin = mg.MotorGenerico(registro, motor).procesar(str(ruta), "L", TS, nombre_origen="nueva.xlsx")
    assert sin.deteccion.estado == "NO_RECONOCIDO" and "cuenta no registrada" in sin.deteccion.motivo
    assert motor.detectar_formato(str(ruta)) == "NO_RECONOCIDO"
    # registrada: UNA entrada de configuración, cero código
    nuevo = registro.con_cuenta("BNB_PRUEBA", "BNB_EXTRACTO_V1", "BNB", "9999999999", "USD")
    assert len(registro.cuentas) == 13 and len(nuevo.cuentas) == 14          # el registro original no cambia
    g = mg.MotorGenerico(nuevo, motor).procesar(str(ruta), "L", TS, nombre_origen="nueva.xlsx")
    assert g.deteccion.estado == "OK" and g.deteccion.cuenta_id == "BNB_PRUEBA"
    assert set(g.df["BANCO"]) == {"BNB"} and set(g.df["CUENTA BANCARIA"]) == {"9999999999"}
    assert set(g.df["MONEDA"]) == {"USD"}
    assert g.df["IMPORTE"].tolist() == [100.0, 30.0] and g.df["TIPO MOVIMIENTO"].tolist() == ["CRÉDITO", "DÉBITO"]
    assert g.validacion["ESTADO"] == "OK"
    assert g.df["CLAVE TRANSACCIÓN"].iloc[0].startswith("BNB|9999999999|20260801|")


def test_cuenta_nueva_produce_lo_mismo_que_una_cuenta_conocida_con_el_mismo_contenido(mg, registro, motor, tmp_path):
    """Mismo contenido bajo una cuenta conocida (BNB_CLINICA) y bajo una cuenta nueva: solo cambian
    BANCO/CUENTA/MONEDA/CLAVE; el resto de las columnas es idéntico (no hay lógica por cuenta)."""
    filas = [{"fecha": "02/08/2026", "deb": 30.0, "saldo": 1070.0, "adic": "Nombre: ACME; x"},
             {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0}]
    conocida = crear_xlsx_bnb(tmp_path / "c.xlsx", "3000100705", filas)
    nueva = crear_xlsx_bnb(tmp_path / "n.xlsx", "8888888888", filas)
    reg = registro.con_cuenta("BNB_NUEVA", "BNB_EXTRACTO_V1", "BNB", "8888888888", "BOB")
    a = mg.MotorGenerico(reg, motor).procesar(str(conocida), "L", TS, nombre_origen="c.xlsx")
    b = mg.MotorGenerico(reg, motor).procesar(str(nueva), "L", TS, nombre_origen="c.xlsx")
    variables = ["CUENTA BANCARIA", "CLAVE TRANSACCIÓN"]
    pd.testing.assert_frame_equal(a.df.drop(columns=variables), b.df.drop(columns=variables))
    assert a.validacion == b.validacion


def test_con_cuenta_rechaza_configuraciones_invalidas(registro):
    with pytest.raises(Exception):
        registro.con_cuenta("BNB_MN", "BNB_EXTRACTO_V1", "BNB", "1234567", "BOB")      # id repetido
    with pytest.raises(Exception):
        registro.con_cuenta("Z", "FORMATO_QUE_NO_EXISTE", "X", "1", "BOB")             # formato desconocido
    with pytest.raises(Exception):
        registro.con_cuenta("Z", "BNB_EXTRACTO_V1", "BNB", "3000100152", "BOB")        # cuenta ya registrada


def test_cuenta_ambigua_en_cabecera_se_reporta_como_ambiguo(mg, generico, motor, normalizado, tmp_path):
    ruta = crear_xlsx_bnb(tmp_path / "a.xlsx", "3000100152 y 3000100705", [{"fecha": "01/08/2026", "cred": 1.0, "saldo": 1.0}])
    g = generico.detectar(str(ruta))
    assert g.estado == "AMBIGUO" and set(g.candidatos) == {"BNB_MN", "BNB_CLINICA"}
    assert motor.detectar_formato(str(ruta)) == "BNB_MN"          # el legado elige la primera sin avisar
    r = mg.sombra_archivo(generico, "a.xlsx", str(ruta), "BNB_MN", "L", TS)
    assert r["estado"] == "DIFIERE" and any(d["nivel"] == "DETECCION" for d in r["diferencias"])


# ------------------------------- 6. DIFERENCIAS DOCUMENTADAS: SE REPORTAN, NO SE CORRIGEN EN EL LEGADO -------------------------------
def _sombra_ad_hoc(mg, gen, motor, ruta, nombre):
    try:
        fl = motor.detectar_formato(str(ruta))
    except Exception:
        fl = "ERROR"
    tabla = val = err = None
    if fl not in ("NO_RECONOCIDO", "ERROR"):
        try:
            tabla = motor.normalizar_archivo(str(ruta), fl, "L", TS, nombre_origen=nombre)
            val = motor.validar_archivo(str(ruta), fl, tabla)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return fl, mg.sombra_archivo(gen, nombre, str(ruta), fl, "L", TS, tabla_legado=tabla,
                                 validacion_legado=val, error_legado=err)


def test_diferencia_d10_cuenta_dentro_de_una_glosa_se_reporta(mg, generico, motor, tmp_path):
    """D-10 (legado): un BNB_CLINICA cuya glosa menciona la cuenta de BNB_MN se clasifica como BNB_MN.
    El genérico lee la cuenta solo en la cabecera y acierta; la diferencia queda REPORTADA."""
    ruta = crear_xlsx_bnb(tmp_path / "x.xlsx", "3000100705", [
        {"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0, "adic": "Transferencia desde cuenta 3000100152"}])
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "x.xlsx")
    assert fl == "BNB_MN" and r["cuenta_generico"] == "BNB_CLINICA"
    assert r["estado"] == "DIFIERE" and [d["nivel"] for d in r["diferencias"]][0] == "DETECCION"


def test_diferencia_d11_bmsc_con_otra_cuenta_se_reporta(mg, generico, motor, tmp_path):
    """D-11 (legado): BMSC no verifica la cuenta. El genérico lo rechaza: 'cuenta no registrada'."""
    ruta = crear_xlsx_bmsc_otra_cuenta(tmp_path / "b.xlsx", "9999999999")
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "b.xlsx")
    assert fl == "BMSC" and r["cuenta_generico"] == "NO_RECONOCIDO"
    assert r["estado"] == "DIFIERE"
    assert "cuenta no registrada" in r["diferencias"][0]["detalle"]


def test_diferencia_union_ultimos12_se_reporta(mg, generico, motor):
    """El legado detecta el reporte 'Últimos 12 movimientos' como UNION_ME (y recién falla al leer la hoja).
    El genérico lo rechaza en la detección con un mensaje explícito."""
    fl, r = _sombra_ad_hoc(mg, generico, motor, UNION_ULTIMOS12, "union_ultimos12.xls")
    assert fl == "UNION_ME" and r["cuenta_generico"] == "NO_RECONOCIDO"
    assert r["estado"] == "DIFIERE" and "Ultimos 12" in r["diferencias"][0]["detalle"]


def test_d09_encabezado_incompleto_lo_rechaza_el_generico(mg, registro, motor, tmp_path):
    """D-09 (legado): acepta una fila cualquiera aunque no coincida con ningún encabezado.
    El genérico exige puntaje_minimo (100 %) y lo declara NO_RECONOCIDO."""
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Hoja 1"
    ws.append(["Cuenta:", "3000100152"])
    ws.append(["Fecha", "Hora", "Codigo de transaccion", "Adicionales"])       # faltan 4 de 7 encabezados
    ws.append(["01/08/2026", "10:00:00", "77", "x"])
    ruta = tmp_path / "inc.xlsx"; wb.save(ruta)
    g = mg.MotorGenerico(registro, motor).detectar(str(ruta))
    assert g.estado == "NO_RECONOCIDO" and "encabezado incompleto" in g.motivo
    assert motor.detectar_formato(str(ruta)) == "BNB_MN"


# ------------------------------- 7. EQUIVALENCIA EN CASOS SINTÉTICOS -------------------------------
def test_sombra_bnb_orden_descendente_valida_saldos_igual_que_el_legado(mg, generico, motor, tmp_path):
    """BNB suele venir de más reciente a más antiguo: la validación se ordena cronológicamente."""
    ruta = crear_xlsx_bnb(tmp_path / "d.xlsx", "3000100705", [
        {"fecha": "03/08/2026", "hora": "09:00:00", "deb": 30.0, "saldo": 1170.0},
        {"fecha": "02/08/2026", "hora": "09:00:00", "cred": 70.0, "saldo": 1200.0},
        {"fecha": "01/08/2026", "hora": "09:00:00", "cred": 100.0, "saldo": 1130.0}])
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "d.xlsx")
    assert r["estado"] == "COINCIDE" and fl == "BNB_CLINICA", r["diferencias"]


@pytest.mark.parametrize("filas", [
    [{"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0}],
    [{"fecha": "01/08/2026", "deb": 5.5, "saldo": 994.5}, {"fecha": "01/08/2026", "hora": "11:00:00", "cred": 5.5, "saldo": 1000.0}],
    [{"fecha": "01/08/2026", "cred": 100.0, "saldo": 1100.0}, {"fecha": "no es fecha", "cred": 5.0, "saldo": 5.0}],
], ids=["un_credito", "debito_y_credito", "fila_sin_fecha_interpretable"])
def test_sombra_bnb_sinteticos_coinciden_con_el_legado(mg, generico, motor, tmp_path, filas):
    ruta = crear_xlsx_bnb(tmp_path / "s.xlsx", "3000100705", filas)
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "s.xlsx")
    assert r["estado"] == "COINCIDE", r["diferencias"]


def test_sombra_union_me_proxy_sintetico_con_movimiento_coincide(mg, generico, motor, tmp_path):
    """PROXY SINTÉTICO (no es un extracto real de UNION_ME): comprueba que la configuración compartida
    UNION_FECHAS_V1 sirve también para UNION_ME. NO valida el comportamiento real con movimientos."""
    ruta = crear_xlsx_union_me_con_movimiento(tmp_path / "u1.xlsx")
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "u1.xlsx")
    assert fl == "UNION_ME" and r["cuenta_generico"] == "UNION_ME"
    assert r["estado"] == "COINCIDE", r["diferencias"]


def test_sombra_union_me_vacio_proxy_falla_igual_que_el_legado_d16b(mg, generico, motor, tmp_path):
    """D-16b (legado, XFAIL vigente): UNION_ME sin movimientos lanza KeyError. El genérico NO lo corrige
    todavía: falla igual, por lo que la sombra no muestra diferencia (y el defecto sigue documentado)."""
    ruta = crear_xlsx_union_me_vacio(tmp_path / "u0.xlsx")
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "u0.xlsx")
    assert fl == "UNION_ME" and r["estado"] == "COINCIDE" and "ambos fallan: KeyError" in r.get("detalle", "")


def test_sombra_no_corrige_d16_bnb_sin_movimientos(mg, generico, motor, tmp_path):
    """D-16 (legado, XFAIL vigente): BNB con encabezado y sin movimientos lanza KeyError; el genérico igual."""
    ruta = crear_xlsx_bnb(tmp_path / "v.xlsx", "3000100705", [])
    fl, r = _sombra_ad_hoc(mg, generico, motor, ruta, "v.xlsx")
    assert r["estado"] == "COINCIDE" and "ambos fallan: KeyError" in r.get("detalle", "")


# ------------------------------- 8. EL COMPARADOR DETECTA DIFERENCIAS -------------------------------
def _reg_mutado(mg, registro, fn):
    return mg.Registro(_mutar(registro, fn))


CASOS_DIFERENCIA = {
    "etiqueta_info_bisa": ("BISA_MN", lambda d: d["FORMATOS"]["BISA_EXTRACTO_V1"]["info_adicional"]["partes"][1].update(etiqueta="Suc"),
                           "NORMALIZADO", "INFORMACIÓN ADICIONAL"),
    "moneda_bnb_mn": ("BNB_MN", lambda d: [c.update(moneda="USD") for c in d["CUENTAS"] if c["id"] == "BNB_MN"],
                      "NORMALIZADO", "MONEDA"),
    "cuenta_bnb_mn": ("BNB_MN", lambda d: [c.update(cuenta="1111111111") for c in d["CUENTAS"] if c["id"] == "BNB_MN"],
                      "DETECCION", "(formato/cuenta)"),   # la cuenta registrada ya no aparece en la cabecera
    "depositante_bnb_vacio": ("BNB_MN", lambda d: d["FORMATOS"]["BNB_EXTRACTO_V1"]["depositante"].update(estrategia="VACIO"),
                              "NORMALIZADO", "DEPOSITANTE / ORIGINANTE"),
    "bcp_sin_excluir_saldos": ("BCP_MN", lambda d: d["FORMATOS"]["BCP_EXTRACTO_V1"].update(filas_excluir=[]),
                               "NORMALIZADO", "(filas)"),
    "eco_filtro_fecha": ("ECO_CTA_CTE", lambda d: d["FORMATOS"]["ECO_EXTRACTO_V1"].update(filtro_fecha="PANDAS_DAYFIRST"),
                         "NORMALIZADO", "(filas)"),
    "bmsc_separador_info": ("BMSC", lambda d: d["FORMATOS"]["BMSC_EXCEL_V1"]["info_adicional"].update(separador=" / "),
                            "NORMALIZADO", "INFORMACIÓN ADICIONAL"),
    "saldo_final_eco": ("ECO_CTA_CTE", lambda d: d["FORMATOS"]["ECO_EXTRACTO_V1"]["saldo"].update(
                            final={"fuente": "ULTIMA_FILA"}, inicial={"fuente": "RECONSTRUIDO"}),
                        None, None),   # cambia la fuente de saldo: puede coincidir numericamente (se verifica abajo)
}


@pytest.mark.parametrize("nombre", [n for n, c in CASOS_DIFERENCIA.items() if c[2]])
def test_el_comparador_reporta_diferencias_inyectadas(mg, registro, motor, normalizado, ruta_fixture, nombre):
    fm, fn, nivel, columna = CASOS_DIFERENCIA[nombre]
    reg = _reg_mutado(mg, registro, fn)
    assert reg.validar() == []
    gen = mg.MotorGenerico(reg, motor)
    df, val = normalizado[fm]
    r = mg.sombra_archivo(gen, FIXTURES[fm], ruta_fixture(fm), fm, "LOTE_TEST", TS, tabla_legado=df, validacion_legado=val)
    assert r["estado"] == "DIFIERE"
    assert any(d["nivel"] == nivel and d["columna"] == columna for d in r["diferencias"]), r["diferencias"][:6]


def test_una_fuente_de_saldo_distinta_que_da_el_mismo_resultado_no_es_diferencia(mg, registro, motor, normalizado, ruta_fixture):
    """La comparación es de RESULTADOS: cambiar la fuente de saldo sin cambiar el valor no reporta nada."""
    fm, fn, _, _ = CASOS_DIFERENCIA["saldo_final_eco"]
    gen = mg.MotorGenerico(_reg_mutado(mg, registro, fn), motor)
    df, val = normalizado[fm]
    r = mg.sombra_archivo(gen, FIXTURES[fm], ruta_fixture(fm), fm, "LOTE_TEST", TS, tabla_legado=df, validacion_legado=val)
    assert r["estado"] == "COINCIDE"


def test_el_comparador_reporta_diferencia_de_validacion(mg, registro, motor, normalizado, ruta_fixture):
    reg = _reg_mutado(mg, registro, lambda d: d["FORMATOS"]["BISA_EXTRACTO_V1"]["saldo"].update(
        inicial={"fuente": "CELDA_FIJA", "fila": 9, "columna": 7}))
    gen = mg.MotorGenerico(reg, motor)
    df, val = normalizado["BISA_MN"]
    r = mg.sombra_archivo(gen, "bisa_mn_2.xls", ruta_fixture("BISA_MN"), "BISA_MN", "LOTE_TEST", TS,
                          tabla_legado=df, validacion_legado=val)
    assert r["estado"] == "DIFIERE" and any(d["nivel"] == "VALIDACION" for d in r["diferencias"])


def test_comparar_frames_detecta_columna_indice_y_familia_de_tipo(mg):
    a = pd.DataFrame({"x": [1.0, 2.0], "y": ["a", "b"]}, index=[5, 6])
    assert mg.comparar_frames(a, a.copy()) == []
    assert mg.comparar_frames(a, a.rename(columns={"y": "z"}))[0]["columna"] == "(columnas)"
    assert mg.comparar_frames(a, a.iloc[:1])[0]["columna"] == "(filas)"
    assert mg.comparar_frames(a, a.set_axis([0, 1]))[0]["columna"] == "(indice)"
    d = mg.comparar_frames(a, a.assign(x=["1", "2"]))
    assert any("familia de tipo" in x["detalle"] for x in d)
    d = mg.comparar_frames(a, a.assign(y=["a", "c"]))
    assert [(x["columna"], x["valor_legado"], x["valor_generico"]) for x in d] == [("y", "b", "c")]


# ------------------------------- 9. INTEGRACIÓN: ejecutar_motor + SOMBRA -------------------------------
def test_lote_corre_en_sombra_sin_diferencias_y_escribe_el_informe(corrida_lote):
    res, salida = corrida_lote
    s = res["sombra_estado"]
    assert s["estado"] == "SIN_DIFERENCIAS", s
    assert (s["archivos_comparados"], s["archivos_coinciden"], s["archivos_difieren"], s["diferencias_total"]) == (12, 12, 0, 0)
    informe = json.loads((salida / "SOMBRA_REPORTE.json").read_text(encoding="utf-8"))
    assert informe["modo"] == "SOMBRA" and informe["estado"] == "SIN_DIFERENCIAS"
    assert informe["version_registro"] == "P3-1" and len(informe["sha256_registro"]) == 64
    assert {a["cuenta_generico"] for a in informe["archivos"]} == set(FORMATOS_OK)
    assert all(a["estado"] == "COINCIDE" for a in informe["archivos"])
    # solo ruido de coma flotante (< 1e-6) en sumas de validación, informado aparte y sin contar como diferencia
    obs = [o for a in informe["archivos"] for o in a["observaciones"]]
    assert len(obs) == informe["observaciones_total"]
    assert all(o["nivel"] == "OBSERVACION" and o["columna"] in ("CRÉDITOS", "DÉBITOS")
               and abs(o["valor_legado"] - o["valor_generico"]) <= 1e-6 for o in obs)
    csv = pd.read_csv(salida / "SOMBRA_DIFERENCIAS.csv", encoding="utf-8-sig")
    assert len(csv) == 0 and "DETALLE" in csv.columns


def test_lote_la_produccion_sigue_siendo_la_del_legado(corrida_lote):
    """LISTS.csv y NORMALIZADO.xlsx productivos = doradas generadas con el motor ORIGINAL (no con el genérico)."""
    from helpers import leer_csv_texto
    res, salida = corrida_lote
    pd.testing.assert_frame_equal(leer_csv_texto(salida / "LISTS.csv"), leer_csv_texto(GOLDEN / "LOTE_12_LISTS.csv"))
    x = pd.read_excel(salida / "NORMALIZADO.xlsx", sheet_name="LISTS", dtype=str)
    x = x.drop(columns=["LOTE DE CARGA", "FECHA DE CARGA"])
    e = pd.read_csv(GOLDEN / "LOTE_12_NORMALIZADO__LISTS.csv", dtype=str, keep_default_na=False).drop(
        columns=["LOTE DE CARGA", "FECHA DE CARGA"], errors="ignore")
    assert list(x.columns) == list(e.columns) and len(x) == len(e) == 4064
    assert x["CLAVE TRANSACCIÓN"].tolist() == e["CLAVE TRANSACCIÓN"].tolist()
    assert {p.name for p in salida.iterdir()} == {"LISTS.csv", "NORMALIZADO.xlsx", "ORIGEN.xlsx",
                                                  "SOMBRA_REPORTE.json", "SOMBRA_DIFERENCIAS.csv"}


# Subconjunto de extractos pequeños: las variantes de integración (sombra apagada, registro alterado, fallos)
# corren el motor completo varias veces y no necesitan los extractos de miles de filas.
PEQUENO = ("BNB_ME", "BCP_ME", "BISA_ME", "BISA_MN", "ECO_AHORRO", "BMSC", "BNB_CLINICA", "BNB_AHORRO", "UNION_MN")


def _correr(motor, base, sombra=True, registro_env=None):
    ent, sal = base / "in", base / "out"
    ent.mkdir(parents=True)
    for fm in PEQUENO:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: FIJO))
        mp.setenv("CBBA_MOTOR_SOMBRA", "1" if sombra else "0")
        if registro_env is not None:
            mp.setenv("CBBA_REGISTRO_BANCOS", str(registro_env))
        else:
            mp.delenv("CBBA_REGISTRO_BANCOS", raising=False)
        return motor.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx")), sal


def _misma_produccion(a, sa, b, sb):
    from evidencia_ab import celdas
    assert (sa / "LISTS.csv").read_bytes() == (sb / "LISTS.csv").read_bytes()
    assert celdas(sa / "NORMALIZADO.xlsx") == celdas(sb / "NORMALIZADO.xlsx")
    for k in ("df_final", "df_validacion", "resumen", "df_resultado_archivos", "df_deteccion_final"):
        pd.testing.assert_frame_equal(a[k], b[k])


@pytest.fixture(scope="module")
def sin_sombra(motor, tmp_path_factory):
    """Línea base: el legado con la sombra APAGADA (mismo reloj fijo)."""
    return _correr(motor, tmp_path_factory.mktemp("sin_sombra"), sombra=False)


def test_sombra_encendida_o_apagada_da_exactamente_la_misma_produccion(motor, tmp_path, sin_sombra):
    sin, s_sin = sin_sombra
    con, s_con = _correr(motor, tmp_path / "con", sombra=True)
    assert sin["sombra_estado"]["estado"] == "DESACTIVADO" and con["sombra_estado"]["estado"] == "SIN_DIFERENCIAS"
    assert con["sombra_estado"]["archivos_comparados"] == len(PEQUENO)
    _misma_produccion(con, s_con, sin, s_sin)
    assert (s_con / "SOMBRA_REPORTE.json").exists() and not (s_sin / "SOMBRA_REPORTE.json").exists()


def test_una_diferencia_en_sombra_se_reporta_y_no_altera_la_produccion(motor, registro, tmp_path, sin_sombra):
    """Registro con un dato distinto (moneda de BNB_ME): el informe lo señala; NORMALIZADO/LISTS no cambian."""
    d = _mutar(registro, lambda x: [c.update(moneda="BOB") for c in x["CUENTAS"] if c["id"] == "BNB_ME"])
    ruta_reg = tmp_path / "registro_alterado.json"
    ruta_reg.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    sin, s_sin = sin_sombra
    con, s_con = _correr(motor, tmp_path / "con", sombra=True, registro_env=ruta_reg)
    s = con["sombra_estado"]
    assert s["estado"] == "CON_DIFERENCIAS" and s["archivos_difieren"] == 1 and s["diferencias_total"] >= 1
    csv = pd.read_csv(s_con / "SOMBRA_DIFERENCIAS.csv", encoding="utf-8-sig", dtype=str)
    assert set(csv["ARCHIVO"]) == {"bnb_me_1_1.xls"} and "MONEDA" in set(csv["COLUMNA"])
    filas = csv[(csv["COLUMNA"] == "MONEDA") & csv["FILA (ÍNDICE)"].notna()]     # sin la fila resumen "N más"
    assert set(filas["VALOR LEGADO"]) == {"USD"} and set(filas["VALOR GENÉRICO"]) == {"BOB"}
    _misma_produccion(con, s_con, sin, s_sin)
    assert set(con["df_final"].loc[con["df_final"]["CUENTA BANCARIA"] == "3400041236", "MONEDA"]) == {"USD"}


@pytest.mark.parametrize("caso", ["json_roto", "registro_invalido", "archivo_inexistente"])
def test_un_fallo_del_generico_no_detiene_ni_altera_al_legado(motor, registro, tmp_path, sin_sombra, caso):
    ruta = tmp_path / "r.json"
    if caso == "json_roto":
        ruta.write_text("{ roto", encoding="utf-8")
    elif caso == "registro_invalido":
        ruta.write_text(json.dumps(_mutar(registro, lambda d: d["CUENTAS"].clear())), encoding="utf-8")
    else:
        ruta = tmp_path / "no_existe.json"
    sin, s_sin = sin_sombra
    con, s_con = _correr(motor, tmp_path / "con", sombra=True, registro_env=ruta)
    assert con["sombra_estado"]["estado"] == "ERROR" and con["sombra_estado"]["error"]
    assert not (s_con / "SOMBRA_REPORTE.json").exists()
    _misma_produccion(con, s_con, sin, s_sin)
    assert con["origen_estado"]["estado"] == "OK"


def _motor_aparte(tmp_path, nombre, generico_src=None):
    """Copia el legado (y captura_origen.py) a una carpeta propia, con o sin motor_generico.py al lado."""
    d = tmp_path / nombre
    d.mkdir()
    shutil.copy(REPO / "motor_control_depositos_cbba.py", d / "motor_control_depositos_cbba.py")
    shutil.copy(REPO / "captura_origen.py", d / "captura_origen.py")
    if generico_src is not None:
        shutil.copy(REPO / "registro_bancos.json", d / "registro_bancos.json")
        (d / "motor_generico.py").write_text(generico_src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"motor_{nombre}", d / "motor_control_depositos_cbba.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_un_generico_que_explota_no_detiene_al_legado(tmp_path, sin_sombra):
    """Aunque el punto de entrada del genérico lance una excepción, el legado termina igual."""
    src = (REPO / "motor_generico.py").read_text(encoding="utf-8")
    roto = _motor_aparte(tmp_path, "roto", src + "\n\ndef ejecutar_sombra_produccion(*a, **k):\n    raise RuntimeError('boom')\n")
    sin, s_sin = sin_sombra
    con, s_con = _correr(roto, tmp_path / "con", sombra=True)
    assert con["sombra_estado"]["estado"] == "ERROR" and "boom" in con["sombra_estado"]["error"]
    _misma_produccion(con, s_con, sin, s_sin)


def test_motor_sin_motor_generico_al_lado_tampoco_falla(tmp_path, sin_sombra):
    """Si motor_generico.py no existe junto al motor, la producción sigue igual (sombra_estado = ERROR)."""
    aislado = _motor_aparte(tmp_path, "solo_legado")
    sin, s_sin = sin_sombra
    con, s_con = _correr(aislado, tmp_path / "con", sombra=True)
    assert con["sombra_estado"]["estado"] == "ERROR"
    _misma_produccion(con, s_con, sin, s_sin)


def test_archivos_de_sombra_no_se_toman_como_extractos(motor, tmp_path):
    for n in ("SOMBRA_REPORTE.json", "SOMBRA_DIFERENCIAS.csv"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    shutil.copy(EXTRACTOS / FIXTURES["BNB_ME"], tmp_path / "bnb.xls")
    assert set(motor.descubrir_archivos(str(tmp_path))) == {"bnb.xls"}


def test_cli_compara_una_carpeta_sin_escribir_produccion(tmp_path):
    ent, rep = tmp_path / "in", tmp_path / "rep"
    ent.mkdir()
    for fm in ("BNB_ME", "ECO_AHORRO"):
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    p = subprocess.run([sys.executable, "-W", "ignore", str(REPO / "motor_generico.py"), str(ent), str(rep)],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "SIN_DIFERENCIAS" in p.stdout
    assert sorted(x.name for x in rep.iterdir()) == ["SOMBRA_DIFERENCIAS.csv", "SOMBRA_REPORTE.json"]
    assert not (ent / "NORMALIZADO.xlsx").exists() and not (rep / "LISTS.csv").exists()
