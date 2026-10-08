# -*- coding: utf-8 -*-
"""
p10/generar_a1.py · P10-A.1 · pipeline completo: extractos reales -> P0 -> snapshot -> libros mensuales.

    python -m p10.generar_a1 --entrada tests/fixtures/extractos --trabajo <dir> --salida <dir>
                             [--snapshot snapshot.json] [--solo BNB_MN,BCP_MN] [--zip entrega.zip]

1. Ejecuta el motor REAL de P0 (`ejecutar_motor`) sobre la carpeta de extractos -> LISTS.csv + ORIGEN.xlsx.
2. Toma el snapshot operativo: el indicado con --snapshot o, si no se indica, el SIMULADO (T0) de este módulo.
3. Genera un .xlsx por BANCO + CUENTA + MONEDA + MES (EXTRACTO + AUDITORIA), validando cada archivo antes de
   aceptarlo, y el manifiesto JSON. Con --zip empaqueta los libros de forma determinista y muestra su SHA-256.
"""
import argparse
import json
import os
import sys

from . import empaque, generador, motor_p0, snapshot_simulado
from .snapshot import cargar_snapshot
import historico as H


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True, help="carpeta con los extractos bancarios originales")
    ap.add_argument("--trabajo", required=True, help="carpeta donde P0 deja NORMALIZADO.xlsx, LISTS.csv y ORIGEN.xlsx")
    ap.add_argument("--salida", required=True, help="carpeta de los libros .xlsx")
    ap.add_argument("--snapshot", help="snapshot JSON (por defecto, el SIMULADO base)")
    ap.add_argument("--solo", help="ids del registro separados por coma (p. ej. BNB_MN)")
    ap.add_argument("--zip", help="ruta del ZIP determinista con los libros generados")
    ap.add_argument("--verbose", action="store_true", help="mostrar la consola de P0")
    a = ap.parse_args(argv)

    p0 = motor_p0.ejecutar_p0(a.entrada, a.trabajo, silencioso=not a.verbose)
    print(f"P0: {p0.movimientos:,} movimientos -> {p0.lists_csv}")
    if a.snapshot:
        snap = cargar_snapshot(a.snapshot)
    else:
        snap = snapshot_simulado.snapshot_simulado(H.leer_normalizado(p0.lists_csv))
        ruta_snap = os.path.join(a.trabajo, "SNAPSHOT_SIMULADO_T0.json")
        with open(ruta_snap, "w", encoding="utf-8", newline="\n") as f:
            json.dump(snap.a_dict(), f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"Snapshot SIMULADO: {len(snap)} filas -> {ruta_snap}")

    solo = {s.strip() for s in a.solo.split(",")} if a.solo else None
    info = generador.generar_libros(p0.origen_xlsx, p0.lists_csv, snap, a.salida, solo_cuentas=solo)
    for f in info["archivos"]:
        est = " · ".join(f"{k}: {v}" for k, v in sorted(f["estados"].items()))
        print(f"OK   {f['nombre_archivo']}  {f['movimientos']:>5} mov · {est} · {f['sha256'][:12]}")
    for o in info["omitidos"]:
        print(f"NO ACEPTADO {o['nombre_archivo']}: {'; '.join(o['errores'])}")
    for n in info["extractos_sin_movimientos"]:
        print(f"SIN MOVIMIENTOS {n} (no genera archivo)")
    ruta_man = os.path.join(a.salida, "MANIFIESTO_P10_A1.json")
    generador.escribir_manifiesto(info, ruta_man)
    if a.zip and info["archivos"]:
        sha = empaque.crear_zip([f["ruta"] for f in info["archivos"]], a.zip)
        print(f"ZIP {a.zip}\nSHA-256 {sha}")
    print(f"Estado: {info['estado']} · {len(info['archivos'])} archivo(s) en {a.salida}")
    return 0 if info["estado"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
