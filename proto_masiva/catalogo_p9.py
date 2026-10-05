"""Catálogo de bancos y cuentas de P9, EXTRAÍDO (nunca escrito a mano) del Main_Screen validado en tenant.

Fuente de verdad: `p9/reversion/powerapps/Main_Screen.yaml` del checkpoint
`candidate/p9-reversion-pendiente-ux` @ 3b407e202ca53e8827151d9e03a41c300bb8d84a (SHA-256 LF fijado abajo, el mismo que
protege tests/test_32):
  - bancos  <- `cmbBancoP9_1.Items` (se descarta «(Todos)», que no es un banco)
  - cuentas <- `cmbCuentaP9_1.Items` (Switch por banco; etiqueta y número de cuenta exactos, en el orden de la fuente)
La MONEDA no figura en el selector: se toma de `registro_bancos.json` (CUENTAS[].moneda) y se contrasta con las
etiquetas MN/ME del selector. Si la fuente cambia, la extracción falla en voz alta en vez de generar una plantilla distinta.

    python proto_masiva/catalogo_p9.py        # regenera proto_masiva/catalogo_bancos_p9.json
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
CHECKPOINT_COMMIT = "3b407e202ca53e8827151d9e03a41c300bb8d84a"
SHA256_MAIN_SCREEN_LF = "99486d668690e425568ca18c5d6d3ff6d953fe4529e0ca0b48b0d99fd98e755a"
FUENTE_MAIN_SCREEN = "p9/reversion/powerapps/Main_Screen.yaml"
FUENTE_MONEDA = "registro_bancos.json"
JSON_SALIDA = Path(__file__).resolve().parent / "catalogo_bancos_p9.json"
ETIQUETA_MONEDA = {"MN": "BOB", "ME": "USD"}  # solo para CONTRASTAR; AHORRO / CLÍNICA / CTA. CTE. no indican moneda


class CatalogoInvalido(Exception):
    pass


def _bytes_fuente(raiz: Path) -> tuple[bytes, str]:
    """Bytes de Main_Screen.yaml. Si hay git con el commit del checkpoint, exige que el archivo coincida con ese objeto."""
    datos = (raiz / FUENTE_MAIN_SCREEN).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(datos).hexdigest() != SHA256_MAIN_SCREEN_LF:
        raise CatalogoInvalido("Main_Screen.yaml no es el validado en tenant (SHA-256 distinto del checkpoint).")
    origen = "archivo"
    try:
        git = subprocess.run(["git", "show", f"{CHECKPOINT_COMMIT}:{FUENTE_MAIN_SCREEN}"], cwd=raiz, capture_output=True)
        if git.returncode == 0:
            if git.stdout.replace(b"\r\n", b"\n") != datos:
                raise CatalogoInvalido("Main_Screen.yaml difiere del objeto git del checkpoint 3b407e2.")
            origen = "archivo + objeto git del checkpoint"
    except FileNotFoundError:
        pass
    return datos, origen


def _controles(hijos):
    for h in hijos:
        (nombre, cuerpo), = h.items()
        yield nombre, cuerpo
        yield from _controles(cuerpo.get("Children", []))


def extraer(raiz: Path = RAIZ) -> dict:
    datos, origen = _bytes_fuente(raiz)
    doc = yaml.safe_load(datos.decode("utf-8"))
    controles = dict(_controles(doc["Screens"]["Main_Screen"]["Children"]))
    bancos = [b for b in re.findall(r'"([^"]+)"', controles["cmbBancoP9_1"]["Properties"]["Items"]) if b != "(Todos)"]
    cuentas, banco = [], None
    for linea in controles["cmbCuentaP9_1"]["Properties"]["Items"].splitlines():
        m = re.match(r'^\s*"([^"]+)",\s*Table\(', linea)
        if m:
            banco = m[1]
            continue
        m = re.search(r'\{Label:\s*"([^"]*)",\s*Cuenta:\s*"([^"]*)"\}', linea)
        if m and m[2]:
            cuentas.append({"banco": banco, "etiqueta": m[1], "cuenta": m[2]})
    registro = {(c["banco"], c["cuenta"]): c["moneda"]
                for c in json.loads((raiz / FUENTE_MONEDA).read_text(encoding="utf-8"))["CUENTAS"]}
    for c in cuentas:
        c["moneda"] = registro.get((c["banco"], c["cuenta"]))
    catalogo = {
        "fuente": {"archivo": FUENTE_MAIN_SCREEN, "checkpoint_commit": CHECKPOINT_COMMIT, "sha256_lf": SHA256_MAIN_SCREEN_LF,
                   "verificado_contra": origen, "controles": ["cmbBancoP9_1", "cmbCuentaP9_1"],
                   "moneda_desde": FUENTE_MONEDA},
        "bancos": bancos,
        "cuentas": cuentas,
    }
    validar(catalogo, registro)
    return catalogo


def validar(catalogo: dict, registro: dict | None = None) -> None:
    bancos, cuentas = catalogo["bancos"], catalogo["cuentas"]
    errores = []
    if len(bancos) != len(set(bancos)) or not bancos:
        errores.append("bancos vacíos o repetidos")
    if "(Todos)" in bancos:
        errores.append("«(Todos)» no es un banco")
    numeros = [c["cuenta"] for c in cuentas]
    if len(numeros) != len(set(numeros)):
        errores.append("cuentas duplicadas")
    for c in cuentas:
        if c["banco"] not in bancos:
            errores.append(f"cuenta {c['cuenta']}: banco {c['banco']} no está en el selector")
        if c["moneda"] not in ("BOB", "USD"):
            errores.append(f"cuenta {c['cuenta']}: sin moneda en {FUENTE_MONEDA}")
        prefijo = c["etiqueta"].split(" · ")[0]
        if prefijo in ETIQUETA_MONEDA and ETIQUETA_MONEDA[prefijo] != c["moneda"]:
            errores.append(f"cuenta {c['cuenta']}: etiqueta {prefijo} contradice la moneda {c['moneda']}")
        if not c["etiqueta"].endswith(c["cuenta"]):
            errores.append(f"cuenta {c['cuenta']}: la etiqueta no termina en el número")
    for b in bancos:
        if not any(c["banco"] == b for c in cuentas):
            errores.append(f"banco {b} sin cuentas")
    # las cuentas de un mismo banco deben ser contiguas (la lista dependiente de Excel usa un rango contiguo por banco)
    orden = [c["banco"] for c in cuentas]
    if any(orden[i] != orden[i - 1] and orden[i] in orden[:i] for i in range(1, len(orden))):
        errores.append("las cuentas de un banco no son contiguas")
    if registro is not None and {(c["banco"], c["cuenta"]) for c in cuentas} != set(registro):
        errores.append(f"las cuentas del selector no coinciden con {FUENTE_MONEDA}")
    if errores:
        raise CatalogoInvalido("; ".join(errores))


def escribir_json(catalogo: dict, destino: Path = JSON_SALIDA) -> Path:
    destino.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


if __name__ == "__main__":
    c = extraer()
    print(escribir_json(c), f"({len(c['bancos'])} bancos, {len(c['cuentas'])} cuentas)")
