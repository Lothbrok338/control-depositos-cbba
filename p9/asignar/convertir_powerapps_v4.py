"""Deriva P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip de la V3 (backend validado en tenant).

DESCARTADA — NO IMPORTAR: al quitar `text_2` de `required`, Power Apps dejó de aceptar los 8 argumentos de `.Run(...)` (esperaba 6–7). Se conserva solo como
procedencia (base de P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip, que corrige exactamente eso; ver p9/asignar/convertir_powerapps_v4_1.py).

CAMBIO DE NEGOCIO: el operador ya no captura el código de estudiante. La firma de .Run(...) NO cambia (8 entradas, mismo orden y mismas
claves del trigger); la 4.ª entrada (`text_2`, CODIGO_ESTUDIANTE) deja de ser obligatoria y la app la envía vacía.
ÚNICOS cambios, ambos en definition.json:
  1. triggers.manual.inputs.schema.required: se quita "text_2".
  2. Validar_entrada: se quita `empty(codigo_estudiante)` del chequeo de obligatorios (el de longitud >255 se conserva).
Todo lo demás, byte a byte igual a V3: ETag, If-Match, MERGE, respuesta con 6 salidas, columnas escritas (CODIGO_ESTUDIANTE se sigue
escribiendo, ahora vacío), sitio, lista, manifiestos.

Ejecutar: python -m p9.asignar.convertir_powerapps_v4
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import zipfile
from pathlib import Path

from p9 import contrato as C
from p9.asignar.convertir_powerapps_v2 import _json, _ruta_definicion, cambios

RAIZ = Path(__file__).resolve().parents[2]
BASE_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip"
BASE_SHA256 = "023db6b4a95b30320f27a1e4d0d38b09bcaac8889ec2e0d3e383d2eb3adb3a44"  # V3 validada en el tenant
NUEVO_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip"
DEFINICION_V4 = Path(__file__).resolve().parent / "flujo_asignar_powerapps_v4_definition.json"
DIFF_MD = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE_DIFF.md"
FRAGMENTO_OBLIGATORIO = "empty(outputs('Entrada')?['codigo_estudiante']),"


def transformar(envoltura: dict) -> dict:
    nueva = copy.deepcopy(envoltura)
    definicion = nueva["properties"]["definition"]
    esquema = definicion["triggers"]["manual"]["inputs"]["schema"]
    assert C.ENTRADA_OPCIONAL_V4 in esquema["required"]
    esquema["required"] = [k for k in esquema["required"] if k != C.ENTRADA_OPCIONAL_V4]
    validar = definicion["actions"]["Validar_entrada"]["inputs"]
    assert validar.count(FRAGMENTO_OBLIGATORIO) == 1
    definicion["actions"]["Validar_entrada"]["inputs"] = validar.replace(FRAGMENTO_OBLIGATORIO, "")
    return nueva


def generar():
    assert hashlib.sha256(BASE_ZIP.read_bytes()).hexdigest() == BASE_SHA256, "la V3 base no es la validada"
    with zipfile.ZipFile(BASE_ZIP) as base:
        entradas = [(i, base.read(i.filename)) for i in base.infolist()]
        ruta_def = _ruta_definicion(base)
        envoltura = json.loads(base.read(ruta_def))
    nueva = transformar(envoltura)
    with zipfile.ZipFile(NUEVO_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for info, contenido in entradas:
            nuevo = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            nuevo.compress_type, nuevo.external_attr = info.compress_type, info.external_attr
            z.writestr(nuevo, _json(nueva) if info.filename == ruta_def else contenido)
    DEFINICION_V4.write_text(json.dumps(nueva["properties"]["definition"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DIFF_MD.write_text(informe(), encoding="utf-8")
    return NUEVO_ZIP


def informe() -> str:
    with zipfile.ZipFile(BASE_ZIP) as a, zipfile.ZipFile(NUEVO_ZIP) as b:
        archivos = [(n, a.read(n) == b.read(n)) for n in a.namelist()]
        defa, defb = json.loads(a.read(_ruta_definicion(a))), json.loads(b.read(_ruta_definicion(b)))
        bytes_a, bytes_b = a.read(_ruta_definicion(a)), b.read(_ruta_definicion(b))
    nodos = list(cambios(defa, defb))
    la = bytes_a.decode().replace(",", ",\n").splitlines()
    lb = bytes_b.decode().replace(",", ",\n").splitlines()
    diff = list(difflib.unified_diff(la, lb, "V3_RESPUESTA.zip", "V4_SIN_CODIGO_ESTUDIANTE.zip", n=0, lineterm=""))
    filas = "\n".join(f"| `{n}` | {'**distinto**' if not ok else 'idéntico (byte a byte)'} |" for n, ok in archivos)
    cambios_md = "\n".join(f"| `{r}` | `{x}` | `{y}` |" for r, x, y in nodos)
    return f"""# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA → P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip` (SHA256 `{BASE_SHA256}`). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip`.
> **DESCARTADA — NO IMPORTAR.** Con esta V4 Power Apps marcó `.Run(...)` con «recibe 8 argumentos; espera entre 6 y 7». La corrige `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip`.

Generado por `python -m p9.asignar.convertir_powerapps_v4`. **Único cambio: `CODIGO_ESTUDIANTE` (`text_2`) deja de ser obligatorio.**

## Nodos JSON que cambiaron ({len(nodos)})

| Ruta | Antes | Después |
|---|---|---|
{cambios_md}

## Archivos del ZIP

| Archivo | Estado |
|---|---|
{filas}

## Diff de texto (definition.json, una propiedad por línea)

```diff
{chr(10).join(diff)}
```

## Lo que NO cambió

Firma de `.Run(...)` (8 entradas, mismo orden, mismas claves `number`, `text`, `text_1`…`text_6`), `Entrada`, validación de longitud (> 255), validación de ID,
`Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones, `CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, las 6 salidas de la respuesta,
las 8 columnas que se escriben (`CODIGO_ESTUDIANTE` se sigue escribiendo, vacío), sitio, GUID de la lista, manifiestos, IDs y `displayName`.
"""


if __name__ == "__main__":
    print(generar())
