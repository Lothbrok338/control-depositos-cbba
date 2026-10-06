"""Archivos XLSX de MEDICIÓN para el flujo directo: la misma plantilla con N filas FICTICIAS.

    python proto_masiva/generar_medicion.py     ->  proto_masiva/xlsx/medicion/Filas_NNNN.xlsx

Sirven para medir EN EL TENANT cuánto tarda el flujo según el número de filas (ver MEDICION_TENANT.md). No contienen ningún
límite: los tamaños son una escala de prueba, no un dato de la plataforma. Bancos y cuentas salen del catálogo extraído del
Main_Screen del checkpoint (nunca escritos aquí); códigos, importes y nombres son inventados. Salida determinista.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto_masiva import catalogo_p9, generar_plantillas_produccion as G  # noqa: E402

SALIDA = Path(__file__).resolve().parent / "xlsx" / "medicion"
TAMANOS = (10, 50, 100, 250, 500, 1000, 2000)  # escala de prueba; el último coincide con el umbral de lectura configurado en el flujo


def filas(n: int, cat: dict):
    cuentas = cat["cuentas"]
    for i in range(1, n + 1):
        c = cuentas[(i - 1) % len(cuentas)]
        yield (c["banco"], c["cuenta"], f"MEDICION-{i:05d}", round(100 + (i % 97) * 1.25, 2), c["moneda"],
               f"ESTUDIANTE MEDICION {i}", "SOLICITANTE MEDICION", "COCHABAMBA", "FILA DE MEDICION" if i % 10 == 0 else "")


def generar() -> list[Path]:
    cat = catalogo_p9.extraer()
    SALIDA.mkdir(parents=True, exist_ok=True)
    rutas = []
    for n in TAMANOS:
        ruta = SALIDA / f"Filas_{n:04d}.xlsx"
        ruta.write_bytes(G.construir(False, cat, filas=list(filas(n, cat))))
        rutas.append(ruta)
    return rutas


if __name__ == "__main__":
    import hashlib
    for r in generar():
        print(f"{hashlib.sha256(r.read_bytes()).hexdigest()[:16]}  {r.stat().st_size:>7} B  {r.name}")
