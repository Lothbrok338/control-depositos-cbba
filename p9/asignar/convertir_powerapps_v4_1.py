"""Deriva P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip de la V4 (corrección mínima de contrato).

SUPERADA POR LA V4.2 (P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip): con `text_5` opcional Power Apps pidió 7 posicionales + un registro final.
Se conserva solo como procedencia reproducible de la V4.2.

PROBLEMA (validado en el tenant): la V4 quitó `text_2` (CODIGO_ESTUDIANTE) del array `required` del trigger «Power Apps (V2)». Power Automate seguía
mostrando los 8 inputs, pero Power Apps, al volver a agregar el flujo, marcó `P9_ASIGNAR_DEPOSITO.Run(...)` con «recibe 8 argumentos; espera entre 6 y 7».
La obligatoriedad de un input en `required` forma parte de la firma que Power Apps construye para `.Run(...)`: no se debe tocar.

ÚNICO cambio respecto de V4: `triggers.manual.inputs.schema.required` vuelve a incluir `text_2`, en su posición original. Con eso el trigger queda
idéntico al de la V3 validada (misma firma de 8 argumentos). Se conserva el cambio de V4 en `Validar_entrada` (el CONTENIDO de CODIGO_ESTUDIANTE ya no
se exige), así que la app puede enviar `""`.

Ejecutar: python -m p9.asignar.convertir_powerapps_v4_1
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import zipfile
from pathlib import Path

from p9 import contrato as C
from p9.asignar import convertir_powerapps_v3 as V3
from p9.asignar import convertir_powerapps_v4 as V4
from p9.asignar.convertir_powerapps_v2 import _json, _ruta_definicion, cambios

RAIZ = Path(__file__).resolve().parents[2]
BASE_ZIP = V4.NUEVO_ZIP
BASE_SHA256 = "df1855a4892e28a650078cf99ad5d47e82bfb14b1628b3b848c8442726500184"  # V4 (descartada), la que se importó en el tenant
NUEVO_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip"
DEFINICION_V4_1 = Path(__file__).resolve().parent / "flujo_asignar_powerapps_v4_1_definition.json"
DIFF_MD = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS_DIFF.md"


def transformar(envoltura: dict) -> dict:
    nueva = copy.deepcopy(envoltura)
    esquema = nueva["properties"]["definition"]["triggers"]["manual"]["inputs"]["schema"]
    assert C.ENTRADA_OPCIONAL_V4 not in esquema["required"], "la base no es la V4 descartada"
    esquema["required"] = list(C.REQUERIDOS_TRIGGER)
    assert C.ENTRADA_OPCIONAL_V4 in esquema["required"] and "text_5" not in esquema["required"]
    return nueva


def _leer(ruta: Path):
    with zipfile.ZipFile(ruta) as z:
        ruta_def = _ruta_definicion(z)
        return {n: z.read(n) for n in z.namelist()}, ruta_def


def generar():
    assert hashlib.sha256(BASE_ZIP.read_bytes()).hexdigest() == BASE_SHA256, "la V4 base no es la importada en el tenant"
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
    DEFINICION_V4_1.write_text(json.dumps(nueva["properties"]["definition"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DIFF_MD.write_text(informe(), encoding="utf-8")
    return NUEVO_ZIP


def _comparar(ruta_a: Path, ruta_b: Path, etiqueta_a: str, etiqueta_b: str):
    archivos_a, ruta_def = _leer(ruta_a)
    archivos_b, _ = _leer(ruta_b)
    archivos = [(n, archivos_a[n] == archivos_b[n]) for n in archivos_a]
    nodos = list(cambios(json.loads(archivos_a[ruta_def]), json.loads(archivos_b[ruta_def])))
    la = archivos_a[ruta_def].decode().replace(",", ",\n").splitlines()
    lb = archivos_b[ruta_def].decode().replace(",", ",\n").splitlines()
    diff = list(difflib.unified_diff(la, lb, etiqueta_a, etiqueta_b, n=0, lineterm=""))
    return archivos, nodos, diff


def _tabla_nodos(nodos) -> str:
    return "\n".join(f"| `{r}` | `{x}` | `{y}` |" for r, x, y in nodos)


def informe() -> str:
    archivos, nodos, diff = _comparar(BASE_ZIP, NUEVO_ZIP, "V4.zip", "V4_1.zip")
    _, nodos_v3, _ = _comparar(V3.NUEVO_ZIP, NUEVO_ZIP, "V3.zip", "V4_1.zip")
    filas = "\n".join(f"| `{n}` | {'**distinto**' if not ok else 'idéntico (byte a byte)'} |" for n, ok in archivos)
    return f"""# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V4 → P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip` (SHA256 `{BASE_SHA256}`, **descartada**). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip`.
> **SUPERADA por la V4.2** (`P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip`): con `text_5` opcional Power Apps pidió 7 posicionales + un registro final.

Generado por `python -m p9.asignar.convertir_powerapps_v4_1`. **Único cambio: `text_2` (CODIGO_ESTUDIANTE) vuelve a estar en `required` del trigger.**

Motivo: con la V4, Power Apps marcó `P9_ASIGNAR_DEPOSITO.Run(...)` con «recibe 8 argumentos; espera entre 6 y 7». El `required` del trigger forma parte de la firma de `.Run(...)`.

## V4 → V4.1: nodos JSON que cambiaron ({len(nodos)})

| Ruta | V4 | V4.1 |
|---|---|---|
{_tabla_nodos(nodos)}

## Archivos del ZIP (V4 → V4.1)

| Archivo | Estado |
|---|---|
{filas}

## Diff de texto V4 → V4.1 (definition.json, una propiedad por línea)

```diff
{chr(10).join(diff)}
```

## V3 (validada en el tenant) → V4.1: nodos JSON que difieren ({len(nodos_v3)})

El trigger de V4.1 es idéntico al de la V3 validada (misma firma de 8 argumentos). Lo único que difiere de la V3 es la validación de contenido de `CODIGO_ESTUDIANTE`:

| Ruta | V3 | V4.1 |
|---|---|---|
{_tabla_nodos(nodos_v3)}

## Lo que NO cambió

Los 8 inputs del trigger (claves `number`, `text`, `text_1`…`text_6`, mismo orden, nombres, tipos y descripciones), el `required` de la V3, `OBSERVACION` (`text_5`) opcional, la
validación de contenido de V4 en `Validar_entrada`, `Entrada`, validación de longitud (> 255) y de ID, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`),
condiciones, `CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, las 6 salidas de la respuesta, las 8 columnas escritas (`CODIGO_ESTUDIANTE` se sigue escribiendo, vacío),
sitio, GUID de la lista, manifiestos, IDs y `displayName`. El frontend no cambia.
"""


if __name__ == "__main__":
    print(generar())
