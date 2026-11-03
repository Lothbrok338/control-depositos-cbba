"""Deriva P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip de la V2 (trigger «Power Apps (V2)» ya validado en el tenant).

PROBLEMA: «Responder a PowerApps» quedó sin outputs en el diseñador («Add an output») y Power Apps no tipa el registro devuelto por
.Run(...). El cuerpo de la respuesta ya mapeaba bien las 6 claves de varRespuesta; las 6 propiedades de `schema` no llevaban la marca
`x-ms-dynamically-added: true` (la misma que llevan las entradas del trigger), que es lo que hace que el diseñador las trate como outputs.
ÚNICO cambio: esa marca en las 6 propiedades de Responder_a_PowerApps.inputs.schema.properties. Todo lo demás, byte a byte igual a V2.

Ejecutar: python -m p9.asignar.convertir_powerapps_v3
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
BASE_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip"
BASE_SHA256 = "4a73ee22f9246cf8170cb9e8934ed7006f7a087f1aca460f0abac77a0e913dc6"  # V2 con el trigger Power Apps (V2) ya importado
NUEVO_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip"
DEFINICION_V3 = Path(__file__).resolve().parent / "flujo_asignar_powerapps_v3_definition.json"
DIFF_MD = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA_DIFF.md"
ACCION = "Responder_a_PowerApps"
SALIDAS = list(C.SALIDAS)  # resultado, codigo, mensaje, estado_actual, asignado_por, fecha_hora_asignacion


def generar():
    assert hashlib.sha256(BASE_ZIP.read_bytes()).hexdigest() == BASE_SHA256, "la V2 base no es la validada"
    with zipfile.ZipFile(BASE_ZIP) as base:
        entradas = [(i, base.read(i.filename)) for i in base.infolist()]
        ruta_def = _ruta_definicion(base)
        envoltura = json.loads(base.read(ruta_def))
    respuesta = envoltura["properties"]["definition"]["actions"][ACCION]
    esquema = respuesta["inputs"]["schema"]["properties"]
    assert list(esquema) == SALIDAS == list(respuesta["inputs"]["body"]), "estructura real de la respuesta distinta de la esperada"
    nueva = copy.deepcopy(envoltura)
    props = nueva["properties"]["definition"]["actions"][ACCION]["inputs"]["schema"]["properties"]
    for nombre in SALIDAS:
        props[nombre] = {"title": nombre, "x-ms-dynamically-added": True, "type": "string"}  # mismo estilo que las entradas del trigger
    with zipfile.ZipFile(NUEVO_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for info, contenido in entradas:
            nuevo = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            nuevo.compress_type, nuevo.external_attr = info.compress_type, info.external_attr
            z.writestr(nuevo, _json(nueva) if info.filename == ruta_def else contenido)
    DEFINICION_V3.write_text(json.dumps(nueva["properties"]["definition"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    diff = list(difflib.unified_diff(la, lb, "V2.zip", "V3_RESPUESTA.zip", n=0, lineterm=""))
    filas = "\n".join(f"| `{n}` | {'**distinto**' if not ok else 'idéntico (byte a byte)'} |" for n, ok in archivos)
    cambios_md = "\n".join(f"| `{r}` | `{x}` | `{y}` |" for r, x, y in nodos)
    return f"""# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V2 → P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip` (SHA256 `{BASE_SHA256}`). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip`.
Generado por `python -m p9.asignar.convertir_powerapps_v3`. **Único cambio: la marca `x-ms-dynamically-added: true` en las 6 propiedades del esquema de `{ACCION}`.**

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

Trigger «Power Apps (V2)» y sus 8 entradas, `Entrada`, validaciones, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones,
`CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, `varRespuesta` (inicialización y los 10 `Resultado_*` que la escriben), el `body` de la respuesta, sitio, GUID de la lista,
manifiestos, IDs y `displayName`.
"""


if __name__ == "__main__":
    print(generar())
