"""Deriva P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip de la V4.1 (corrección mínima y definitiva de la firma).

PROBLEMA (validado en el tenant): en la V4.1 `text_5` (OBSERVACION) quedó fuera de `required`. Power Apps construye `.Run(...)` con los inputs requeridos como
argumentos posicionales (7) y pasa los opcionales en UN registro final; la llamada de 8 posicionales daba «Text donde se espera Record», y el nombre del campo
del registro no se puede confirmar sin Studio.
ÚNICO cambio respecto de V4.1: `triggers.manual.inputs.schema.required` incluye también `text_5` → los 8 inputs son posicionales y no hay registro opcional.
`required` es solo presencia del parámetro técnico: `Validar_entrada` no cambia (ya no exige CODIGO_ESTUDIANTE y nunca exigió OBSERVACION), así que ambos pueden valer "".

Ejecutar: python -m p9.asignar.convertir_powerapps_v4_2
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
from p9.asignar import convertir_powerapps_v4_1 as V41
from p9.asignar.convertir_powerapps_v2 import _json, _ruta_definicion, cambios

RAIZ = Path(__file__).resolve().parents[2]
BASE_ZIP = V41.NUEVO_ZIP
BASE_SHA256 = "2d656b642baa2e5caa8f41710ae21cffddf6f538e4172e1de3c0eb12f35490a2"  # V4.1 (superada), la que se importó en el tenant
NUEVO_ZIP = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip"
DEFINICION_V4_2 = Path(__file__).resolve().parent / "flujo_asignar_powerapps_v4_2_definition.json"
DIFF_MD = RAIZ / "P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES_DIFF.md"


def transformar(envoltura: dict) -> dict:
    nueva = copy.deepcopy(envoltura)
    esquema = nueva["properties"]["definition"]["triggers"]["manual"]["inputs"]["schema"]
    assert "text_5" not in esquema["required"], "la base no es la V4.1"
    esquema["required"] = list(C.REQUERIDOS_TRIGGER_V4_2)
    assert esquema["required"] == list(esquema["properties"])  # los 8, en el orden de `properties`
    return nueva


def _leer(ruta: Path):
    with zipfile.ZipFile(ruta) as z:
        ruta_def = _ruta_definicion(z)
        return {n: z.read(n) for n in z.namelist()}, ruta_def


def generar():
    assert hashlib.sha256(BASE_ZIP.read_bytes()).hexdigest() == BASE_SHA256, "la V4.1 base no es la importada en el tenant"
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
    DEFINICION_V4_2.write_text(json.dumps(nueva["properties"]["definition"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DIFF_MD.write_text(informe(), encoding="utf-8")
    return NUEVO_ZIP


def _comparar(ruta_a: Path, ruta_b: Path, etiqueta_a: str, etiqueta_b: str):
    archivos_a, ruta_def = _leer(ruta_a)
    archivos_b, _ = _leer(ruta_b)
    archivos = [(n, archivos_a[n] == archivos_b[n]) for n in archivos_a]
    nodos = list(cambios(json.loads(archivos_a[ruta_def]), json.loads(archivos_b[ruta_def])))
    la = archivos_a[ruta_def].decode().replace(",", ",\n").splitlines()
    lb = archivos_b[ruta_def].decode().replace(",", ",\n").splitlines()
    return archivos, nodos, list(difflib.unified_diff(la, lb, etiqueta_a, etiqueta_b, n=0, lineterm=""))


def _tabla(nodos) -> str:
    return "\n".join(f"| `{r}` | `{x[:200]}` | `{y[:200]}` |" if isinstance(x, str) else f"| `{r}` | `{x}` | `{y}` |" for r, x, y in nodos)


def informe() -> str:
    archivos, nodos, diff = _comparar(BASE_ZIP, NUEVO_ZIP, "V4_1.zip", "V4_2.zip")
    _, nodos_v3, _ = _comparar(V3.NUEVO_ZIP, NUEVO_ZIP, "V3.zip", "V4_2.zip")
    filas = "\n".join(f"| `{n}` | {'**distinto**' if not ok else 'idéntico (byte a byte)'} |" for n, ok in archivos)
    return f"""# Diff P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1 → P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES

Base: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip` (SHA256 `{BASE_SHA256}`, **superada**). Nuevo: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip`.
Generado por `python -m p9.asignar.convertir_powerapps_v4_2`. **Único cambio: `text_5` (OBSERVACION) se agrega a `required` del trigger.**

Motivo: con la V4.1 Power Apps pidió 7 argumentos posicionales + un registro para el opcional. Con los 8 en `required` la firma es de 8 posicionales y no hay registro.
`required` solo significa presencia del parámetro técnico; no exige contenido (eso lo decide `Validar_entrada`, que no cambia).

## V4.1 → V4.2: nodos JSON que cambiaron ({len(nodos)})

| Ruta | V4.1 | V4.2 |
|---|---|---|
{_tabla(nodos)}

## Archivos del ZIP (V4.1 → V4.2)

| Archivo | Estado |
|---|---|
{filas}

## Diff de texto V4.1 → V4.2 (definition.json, una propiedad por línea)

```diff
{chr(10).join(diff)}
```

## V3 (validada en el tenant) → V4.2: nodos JSON que difieren ({len(nodos_v3)})

| Ruta | V3 | V4.2 |
|---|---|---|
{_tabla(nodos_v3)}

## Lo que NO cambió

Los 8 inputs del trigger (claves `number`, `text`, `text_1`…`text_6`, mismo orden, títulos, tipos y descripciones), `Validar_entrada` (no exige CODIGO_ESTUDIANTE ni OBSERVACION;
sí clave, estudiante, solicitado por, sede y usuario; límite de 255 e ID inválido), `Entrada`, `Leer_deposito` (GET), `ETag`, `Actualizar_deposito` (MERGE + `IF-MATCH`), condiciones,
`CONFLICTO` / `NO_DISPONIBLE` / `ERROR`, las 6 salidas de la respuesta, las 8 columnas escritas, sitio, GUID de la lista, manifiestos, IDs y `displayName`.
"""


if __name__ == "__main__":
    print(generar())
