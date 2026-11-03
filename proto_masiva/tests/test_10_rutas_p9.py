"""Rutas físicas de P9 tras mover los recursos a Documents/CONTROL_DEPOSITOS/P9/.

Los tres flujos comparten UNA carpeta temporal (constante `construir.CARPETA_TEMP`): `P9_MASIVA_PROTO_PREVALIDAR` (copias TMP_*.xlsx),
`P9_MASIVA_PROTO_CONFIRMAR` (confirmacion_<uid>.json) y `P9_MASIVA_PROTO_ESTADO` (lee ese mismo archivo). La plantilla de Excel se descarga por UniqueId
(sin ruta), así que moverla no obliga a tocar Power Apps. Estas pruebas impiden que vuelva la ruta anterior (`/Documents/P9_MASIVA_TEMP`).
"""
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from proto_masiva.flows import construir as F
from proto_masiva.flows import construir_confirmar as K
from proto_masiva.flows import construir_estado as E

RAIZ = Path(__file__).resolve().parents[1]
NUEVA = "/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP"
ANTIGUA = "/Documents/P9_MASIVA_TEMP"
FLUJOS = {"P9_MASIVA_PROTO_PREVALIDAR": F, "P9_MASIVA_PROTO_CONFIRMAR": K, "P9_MASIVA_PROTO_ESTADO": E}


def cadenas(valor):
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from cadenas(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from cadenas(v)


def test_la_carpeta_temporal_es_una_sola_constante_con_la_nueva_estructura():
    assert F.RAIZ_P9 == "/Documents/CONTROL_DEPOSITOS/P9" and F.CARPETA_TEMP == NUEVA == K.CARPETA_ESTADO
    assert F.CARPETA_TEMP_ANTIGUA == ANTIGUA and NUEVA.startswith(F.RAIZ_P9 + "/")


@pytest.mark.parametrize("nombre", list(FLUJOS))
def test_los_tres_flujos_apuntan_a_la_misma_carpeta_nueva_en_generador_json_y_zip(nombre):
    modulo = FLUJOS[nombre]
    carpeta = Path(modulo.__file__).parent
    definiciones = {"generador": modulo.construir_definicion(), "json": json.loads((carpeta / f"{nombre}_definition.json").read_text(encoding="utf-8"))}
    z = zipfile.ZipFile(BytesIO((carpeta / f"{nombre}.zip").read_bytes()))
    definiciones["zip"] = json.loads(z.read(next(n for n in z.namelist() if n.endswith("/definition.json"))))["properties"]["definition"]
    for origen, d in definiciones.items():
        assert d["actions"]["PARAM_CARPETA"]["inputs"] == NUEVA, (nombre, origen)
        rutas = {c for c in cadenas(d) if "/Documents/" in c}
        assert rutas == {NUEVA}, (nombre, origen, rutas)                            # la ÚNICA ruta física que contiene cada flujo
        assert ANTIGUA not in json.dumps(d, ensure_ascii=False), (nombre, origen)


def test_ningun_artefacto_generado_ni_fuente_contiene_la_ruta_antigua():
    permitidos = {"construir.py", "test_10_rutas_p9.py"}                           # la constante CARPETA_TEMP_ANTIGUA y este test la nombran a propósito
    for ruta in list(RAIZ.rglob("*.py")) + list((RAIZ / "flows").glob("*.json")) + list((RAIZ / "powerapps").rglob("*.yaml")):
        if ruta.name in permitidos or "tenant" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8")
        assert not re.search(r"(?<![A-Za-z_/])" + re.escape(ANTIGUA) + r"(?![A-Za-z0-9_])", texto), ruta.relative_to(RAIZ)
    for zip_ in (RAIZ / "flows").glob("*.zip"):
        z = zipfile.ZipFile(zip_)
        assert all(ANTIGUA.encode() not in z.read(n) for n in z.namelist()), zip_.name


def test_prevalidacion_confirmacion_y_estado_escriben_y_leen_en_la_misma_carpeta():
    import simulador as S
    import simulador_confirmacion as SC
    # prevalidación: la copia TMP_*.xlsx se crea en la carpeta nueva (el simulador exige folderPath == F.CARPETA_TEMP al ejecutar CreateFile)
    ejemplo = RAIZ / "xlsx" / "Ejemplo_Confirmacion_Masiva_P9.xlsx"
    t, ensayo = S.procesar("Ejemplo.xlsx", ejemplo.read_bytes())
    assert ensayo.respuesta["resultado"] in ("OK", "OBSERVADO", "ERROR") and any(op == "CreateFile" for op, _ in t.llamadas)
    assert t.creados                                                                 # se creó la copia temporal: el simulador ya comprobó que fue en F.CARPETA_TEMP (== NUEVA)
    # confirmación + estado: CreateFile en la carpeta nueva; GetFileContentByPath por una ruta dentro de ella
    ten = SC.TenantConfirmacion([SC.deposito(1)])
    r = SC.confirmar([SC.fila_validada(SC.deposito(1))], ten)
    assert r.nombre_archivo in ten.archivos
    assert SC.consultar_estado(ten, r.uid)["estado"] == "TERMINADO"                  # leído por la ruta NUEVA (el simulador exige el prefijo de la carpeta)
    lectura = E.construir_definicion()["actions"]["TRY"]["actions"]["Uid_valido"]["actions"]["Leer_estado"]["inputs"]["parameters"]["path"]
    assert lectura == "@concat(outputs('PARAM_CARPETA'),'/','confirmacion_',outputs('Entrada')?['uid'],'.json')"


def test_la_plantilla_de_excel_se_descarga_por_UniqueId_y_no_depende_de_ninguna_ruta():
    """Mover el archivo dentro de la biblioteca conserva su UniqueId: el botón de Power Apps NO cambia. (Si se hubiera COPIADO/re-subido, el UniqueId cambia.)"""
    for yaml_ in ("P9_Confirmacion_Masiva.pa.yaml", "tenant_v1/P9_Confirmacion_Masiva.pa.yaml"):
        texto = (RAIZ / "powerapps" / yaml_).read_text(encoding="utf-8")
        urls = re.findall(r'"(https://[^"]*download\.aspx[^"]*)"', texto)
        assert urls == ["https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu/_layouts/15/download.aspx?UniqueId=84b7ef88-43aa-43d2-8d1c-0f0b682dafbd"]
        assert "SourceUrl" not in texto and "P9_MASIVA_PROTO/" not in texto and "CONTROL_DEPOSITOS" not in texto and "P9_MASIVA_TEMP" not in texto
