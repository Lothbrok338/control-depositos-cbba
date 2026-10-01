"""Deriva P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip del ZIP YA VALIDADO EN TENANT (P9_ASIGNAR_DEPOSITO.zip).

ÚNICO cambio: triggers.manual.kind  "Button" ("Manually trigger a flow")  ->  "PowerAppV2" ("Power Apps (V2)").
Las 8 entradas (number, text, text_1..text_6) ya tienen el nombre, tipo y orden de la firma .Run(...); no hay nada que remapear.
Todo lo demás se copia byte a byte del ZIP base. No importa ni modifica p9/asignar/construir.py.

Ejecutar: python -m p9.asignar.convertir_powerapps_v2
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO.zip"
BASE_SHA256 = "90890c1f4bd5ee741c1b61f862cde5085ed51b8e08f0f8f5949b694d79b05a85"  # el ZIP probado en el tenant
NUEVO_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip"
DEFINICION_V2 = Path(__file__).resolve().parent / "flujo_asignar_powerapps_v2_definition.json"
DIFF_MD = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V2_DIFF.md"
KIND_ANTES, KIND_DESPUES = "Button", "PowerAppV2"


def _json(valor) -> bytes:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _ruta_definicion(z: zipfile.ZipFile) -> str:
    return next(n for n in z.namelist() if n.endswith("/definition.json"))


def cambios(antes, despues, ruta=""):
    """Rutas JSON que difieren (hoja a hoja)."""
    if isinstance(antes, dict) and isinstance(despues, dict):
        for k in sorted(set(antes) | set(despues)):
            if k not in antes or k not in despues:
                yield (f"{ruta}.{k}".lstrip("."), antes.get(k, "<ausente>"), despues.get(k, "<ausente>"))
            else:
                yield from cambios(antes[k], despues[k], f"{ruta}.{k}")
    elif isinstance(antes, list) and isinstance(despues, list) and len(antes) == len(despues):
        for i, (a, d) in enumerate(zip(antes, despues)):
            yield from cambios(a, d, f"{ruta}[{i}]")
    elif antes != despues:
        yield (ruta.lstrip("."), antes, despues)


def generar():
    base_bytes = BASE_ZIP.read_bytes()
    assert hashlib.sha256(base_bytes).hexdigest() == BASE_SHA256, "el ZIP base no es el validado en el tenant"
    with zipfile.ZipFile(BASE_ZIP) as base:
        entradas = [(i, base.read(i.filename)) for i in base.infolist()]
        ruta_def = _ruta_definicion(base)
        envoltura = json.loads(base.read(ruta_def))
    definicion = envoltura["properties"]["definition"]
    manual = definicion["triggers"]["manual"]
    assert manual["type"] == "Request" and manual["kind"] == KIND_ANTES
    nueva = copy.deepcopy(envoltura)
    nueva["properties"]["definition"]["triggers"]["manual"]["kind"] = KIND_DESPUES
    with zipfile.ZipFile(NUEVO_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for info, contenido in entradas:
            nuevo_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            nuevo_info.compress_type, nuevo_info.external_attr = info.compress_type, info.external_attr
            z.writestr(nuevo_info, _json(nueva) if info.filename == ruta_def else contenido)
    DEFINICION_V2.write_text(json.dumps(nueva["properties"]["definition"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DIFF_MD.write_text(informe(), encoding="utf-8")
    return NUEVO_ZIP


def informe() -> str:
    with zipfile.ZipFile(BASE_ZIP) as a, zipfile.ZipFile(NUEVO_ZIP) as b:
        assert a.namelist() == b.namelist()
        archivos = [(n, a.read(n) == b.read(n)) for n in a.namelist()]
        defa, defb = json.loads(a.read(_ruta_definicion(a))), json.loads(b.read(_ruta_definicion(b)))
        bytes_a, bytes_b = a.read(_ruta_definicion(a)), b.read(_ruta_definicion(b))
    nodos = list(cambios(defa, defb))
    lineas_a = bytes_a.decode().replace(",", ",\n").splitlines()
    lineas_b = bytes_b.decode().replace(",", ",\n").splitlines()
    diff = [l for l in difflib.unified_diff(lineas_a, lineas_b, "P9_ASIGNAR_DEPOSITO.zip", "P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip", n=0, lineterm="")]
    acciones = defa["properties"]["definition"]["actions"]
    filas = "\n".join(f"| `{n}` | {'**distinto**' if not ok else 'idéntico (byte a byte)'} |" for n, ok in archivos)
    cambios_md = "\n".join(f"| `{r}` | `{x}` | `{y}` |" for r, x, y in nodos)
    return f"""# Diff P9_ASIGNAR_DEPOSITO → P9_ASIGNAR_DEPOSITO_POWERAPPS_V2

Base: `P9_ASIGNAR_DEPOSITO.zip` (SHA256 `{BASE_SHA256}`, el probado en el tenant). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip`.
Generado por `python -m p9.asignar.convertir_powerapps_v2`. **Único cambio: `triggers.manual.kind`.**

## Nodos JSON que cambiaron ({len(nodos)})

| Ruta | Antes | Después |
|---|---|---|
{cambios_md}

## Archivos del ZIP

| Archivo | Estado |
|---|---|
{filas}

(La diferencia en `definition.json` es exactamente la sustitución de `"kind":"{KIND_ANTES}"` por `"kind":"{KIND_DESPUES}"`.)

## Diff de texto (definition.json, una propiedad por línea)

```diff
{chr(10).join(diff)}
```

## Lo que NO cambió

`actions` completo ({len(acciones)} acciones de primer nivel, ver prueba): `PARAM_SITIO_SHAREPOINT`, `PARAM_LISTA_DEPOSITOS_ACTIVOS`, `Entrada`, validaciones, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones, manejo de `CONFLICTO`/`NO_DISPONIBLE`/`ERROR`, `Responder_a_PowerApps` (mismos 6 campos), las entradas del trigger (`number`, `text`, `text_1`…`text_6`: mismo orden, tipos y títulos), `parameters`, `contentVersion`, manifiestos, IDs de recursos, `displayName`.
"""


if __name__ == "__main__":
    print(generar())
