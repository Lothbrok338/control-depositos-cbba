"""P10-A.2 — servicio HTTP p10-api: autenticación, validación, operaciones y empaquetado (Dockerfile) autosuficiente."""
import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from p10 import api, estado as E  # noqa: E402

pytestmark = pytest.mark.p10

TOKEN = "t" * 24
FIXTURE = RAIZ / "tests/fixtures/extractos/bnb_ahorro_2.xls"
RUTA = "/CONTROL_DEPOSITOS/P0_EXTRACTOS/PROCESADOS/2026/10_OCTUBRE/08/bnb_ahorro_2.xls"
AHORA = "2026-10-08T10:00:00"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def cli(monkeypatch):
    monkeypatch.setenv("P10_API_TOKEN", TOKEN)
    return TestClient(api.app)


def test_health_sin_autenticacion(cli):
    assert cli.get("/health").json()["status"] == "ok"


def test_sin_token_configurado_el_servicio_se_niega(monkeypatch):
    monkeypatch.delenv("P10_API_TOKEN", raising=False)
    r = TestClient(api.app).post("/p10/ciclo", json={}, headers=H)
    assert r.status_code == 503 and r.json()["codigo_error"] == "API_NO_CONFIGURADA"
    monkeypatch.setenv("P10_API_TOKEN", "corto")
    assert TestClient(api.app).post("/p10/ciclo", json={}, headers={"Authorization": "Bearer corto"}).status_code == 503


def test_token_ausente_o_incorrecto(cli):
    assert cli.post("/p10/ciclo", json={}).status_code == 401
    assert cli.post("/p10/ciclo", json={}, headers={"Authorization": "Bearer " + "x" * 24}).status_code == 401
    assert cli.post("/p10/ciclo", json={}, headers={"Authorization": "Basic " + TOKEN}).status_code == 401


def test_validaciones_de_solicitud(cli):
    assert cli.post("/p10/nada", json={}, headers=H).status_code == 404
    assert cli.post("/p10/ciclo", content=b"x", headers={**H, "Content-Type": "text/plain"}).status_code == 400
    assert cli.post("/p10/ciclo", content=b"{no", headers={**H, "Content-Type": "application/json"}).status_code == 400
    assert cli.post("/p10/ciclo", json=[1], headers=H).status_code == 400
    r = cli.post("/p10/ciclo", json={"control": []}, headers=H)
    assert r.status_code == 400 and "ahora_local" in r.json()["mensaje"]
    assert cli.post("/p10/ciclo", json={"ahora_local": "mañana", "control": []}, headers=H).status_code == 400
    assert cli.post("/p10/ciclo", json={"ahora_local": AHORA, "control": [1]}, headers=H).status_code == 400
    r = cli.post("/p10/extracto", json={"sede": "CBBA", "nombre_archivo": "x.xls", "ruta": "/x", "ahora_local": AHORA,
                                        "contenido_base64": "###"}, headers=H)
    assert r.status_code == 400 and r.json()["codigo_error"] == "CONTENIDO_INVALIDO"


def test_tamano_maximo(cli, monkeypatch):
    monkeypatch.setenv("P10_MAX_BYTES", "100")
    r = cli.post("/p10/ciclo", json={"ahora_local": AHORA, "control": [], "relleno": "x" * 500}, headers=H)
    assert r.status_code == 413


def test_ciclo_plan_clasificar_por_http(cli):
    lock = {"Id": 1, "CLAVE_CONTROL": "LOCK", "TIPO": "LOCK", "LOCK_HASTA": "", "__metadata": {"etag": '"1"'}}
    r = cli.post("/p10/ciclo", json={"ahora_local": AHORA, "control": [lock]}, headers=H).json()
    assert r["ok"] and r["modo"] == "COMPLETO" and r["lock"]["libre"]
    assert cli.post("/p10/plan", json={"ahora_local": AHORA, "modo": "NORMAL", "archivos": [], "control": []}, headers=H).json()["extractos"] == []
    assert cli.post("/p10/verificar", json={}, headers=H).status_code == 404         # la verificación vive en /sincronizar
    r = cli.post("/p10/clasificar", json={"periodo": "2026-10", "items": [], "control": [], "hay_mas": True}, headers=H).json()
    assert r["codigo_error"] == "REBANADA_EXCEDE_LIMITE"


def test_extracto_y_sincronizar_por_http_extremo_a_extremo(cli):
    contenido = base64.b64encode(FIXTURE.read_bytes()).decode()
    r = cli.post("/p10/extracto", json={"sede": "CBBA", "nombre_archivo": FIXTURE.name, "ruta": RUTA, "ahora_local": AHORA,
                                        "contenido_base64": contenido}, headers=H).json()
    assert r["ok"] and r["control"]["ESTADO"] == "PROCESADO" and len(r["grupos"]) == 1
    g = r["grupos"][0]
    s = cli.post("/p10/sincronizar", json={"sede": "CBBA", "grupo_id": g["grupo_id"], "parciales_base64": [g["parcial_b64"]],
                                           "ahora_local": AHORA}, headers=H).json()
    assert s["ok"] and s["xlsx_valido"] and s["cambio_estado"] and s["xlsx_b64"]
    assert s["control"]["ESTADO"] == "OK" and s["rutas"]["ruta_xlsx"].startswith("/CONTROL_DEPOSITOS/P10_HISTORICO/2026/08_AGOSTO/BNB/")
    again = cli.post("/p10/sincronizar", json={"sede": "CBBA", "grupo_id": g["grupo_id"], "estado_base64": s["estado_b64"],
                                               "parciales_base64": [g["parcial_b64"]], "ahora_local": AHORA}, headers=H).json()
    assert again["ok"] and not again["cambio_estado"] and not again["cambio_xlsx"] and again["xlsx_b64"] is None   # idempotente


def test_extracto_rechazado_responde_200_con_ok_false(cli):
    r = cli.post("/p10/extracto", json={"sede": "CBBA", "nombre_archivo": "x.xls", "ruta": RUTA, "ahora_local": AHORA,
                                        "contenido_base64": base64.b64encode(b"no soy excel").decode()}, headers=H)
    assert r.status_code == 200 and not r.json()["ok"] and r.json()["control"]["ESTADO"] == "ERROR"


def test_sincronizar_con_estado_corrupto_pide_reconstruir(cli):
    r = cli.post("/p10/sincronizar", json={"sede": "CBBA", "grupo_id": "BNB|3501936692|BOB|2026-08", "ahora_local": AHORA,
                                           "estado_base64": base64.b64encode(b"basura").decode()}, headers=H).json()
    assert not r["ok"] and r["control"]["ESTADO"] == "RECONSTRUIR"


def test_los_errores_internos_no_filtran_contenido(cli, monkeypatch):
    def explota(_):
        raise RuntimeError("DATO BANCARIO 3501936692")
    monkeypatch.setitem(api.RUTAS, "ciclo", explota)
    r = cli.post("/p10/ciclo", json={"ahora_local": AHORA, "control": []}, headers=H)
    assert r.status_code == 500 and "3501936692" not in r.text


# ---------------------------------------------------------------- imagen de Docker
def test_el_dockerfile_copia_todo_lo_que_p10_necesita_y_arranca_sin_el_resto_del_repositorio(tmp_path):
    """Reproduce la imagen: copia SOLO lo que lista el Dockerfile y ejecuta un ciclo extracto->sincronizar en ese directorio."""
    docker = (RAIZ / "p10/Dockerfile").read_text(encoding="utf-8")
    destino = tmp_path / "app"
    for linea in re.findall(r"^COPY (.+)$", docker, re.M):
        *origenes, fin = linea.split()
        if origenes[0] == "requirements-p0.txt":
            continue
        for o in origenes:
            src = RAIZ / o
            assert src.exists(), o
            if fin.endswith("/") and not (src.is_dir()):
                (destino / fin).mkdir(parents=True, exist_ok=True)
                shutil.copy(src, destino / fin / src.name)
            elif src.is_dir():
                shutil.copytree(src, destino / fin.rstrip("/"), ignore=shutil.ignore_patterns("__pycache__", "flujo"))
            else:
                destino.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, destino / src.name)
    (tmp_path / "e.xls").write_bytes(FIXTURE.read_bytes())
    prueba = tmp_path / "prueba.py"
    prueba.write_text(
        "import sys, os\nsys.path.insert(0, os.environ['APP'])\n"
        "from p10 import api, sincronizacion as S\n"
        f"r = S.procesar_extracto(open({str(tmp_path / 'e.xls')!r}, 'rb').read(), 'e.xls', 'CBBA', {RUTA!r}, {AHORA!r})\n"
        "assert r['ok'], r\n"
        "s = S.sincronizar_grupo('CBBA', r['grupos'][0]['grupo_id'], None, "
        "[__import__('base64').b64decode(r['grupos'][0]['parcial_b64'])], None, " + repr(AHORA) + ")\n"
        "assert s['ok'] and s['xlsx_valido'], s\nprint('IMAGEN_OK')\n", encoding="utf-8")
    out = subprocess.run([sys.executable, str(prueba)], cwd=str(tmp_path), capture_output=True, text=True,
                         env={"APP": str(destino), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert "IMAGEN_OK" in out.stdout, out.stderr[-1500:]


def test_railway_json_y_dockerfile_de_p10_no_tocan_los_de_p0():
    cfg = json.loads((RAIZ / "p10/railway.json").read_text())
    assert cfg["build"]["dockerfilePath"] == "p10/Dockerfile" and cfg["deploy"]["healthcheckPath"] == "/health"
    d = (RAIZ / "p10/Dockerfile").read_text()
    assert "--workers 1" in d and "USER p10" in d and "VOLUME" not in d
    raiz = json.loads((RAIZ / "railway.json").read_text())
    assert raiz["build"]["dockerfilePath"] == "Dockerfile"


def test_delta_por_http_devuelve_grupos_rutas_y_cursor(cli):
    item = {"Id": 1, "Modified": "2026-10-08T12:00:00Z", "CLAVE_TRANSACCION": "BNB|3501936692|20260803|123822|3P63339949|CRÉDITO|25.00|256422.49",
            "BANCO": "BNB", "CUENTA_BANCARIA": "3501936692", "MONEDA": "BOB", "FECHA_MOVIMIENTO": "2026-08-03T00:00:00Z",
            "ESTADO_ASIGNACION": "ASIGNADO", "ESTUDIANTE": "X", "FECHA_HORA_ASIGNACION": "2026-10-08T11:00:00Z"}
    ctl = [{"CLAVE_CONTROL": "GRUPO|BNB|3501936692|BOB|2026-08", "TIPO": "GRUPO", "PERIODO": "2026-08", "BANCO": "BNB", "ESTADO": "OK",
            "VERSION_ESTADO": 1}]
    r = cli.post("/p10/delta", json={"ahora_local": AHORA, "items": [item], "control": ctl, "cursor_desde": "2026-10-07T14:00:00Z"}, headers=H).json()
    assert r["ok"] and r["cursor_nuevo"] == "2026-10-08T12:00:00Z"
    g = r["sucios"][0]
    assert g["grupo_id"] == "BNB|3501936692|BOB|2026-08" and g["parcial_lista"] is True
    assert g["filas"][0]["FECHA_HORA_ASIGNACION"] == "2026-10-08T07:00:00"          # hora de Bolivia
    assert g["rutas"]["ruta_xlsx"].endswith("EXTRACTO_HISTORICO_BNB_3501936692_BOB_2026-08.xlsx")
