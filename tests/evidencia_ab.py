"""Evidencia A/B: el motor con P1 produce EXACTAMENTE las mismas salidas operativas que el motor original.

    python evidencia_ab.py <motor_original.py> <motor_con_P1.py>

Ambos corren sobre los 12 fixtures con el reloj fijado (asi LOTE/FECHA DE CARGA coinciden) y se compara:
LISTS.csv byte a byte, NORMALIZADO.xlsx celda a celda (valor + formato + tablas), df_final/df_validacion/
resumen, y la salida de consola (salvo las lineas de ORIGEN).  Termina con codigo 1 si algo difiere.
"""
import contextlib, importlib.util, io, shutil, sys, tempfile
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from helpers import EXTRACTOS, FIXTURES, FORMATOS_OK

FIJO = pd.Timestamp("2026-08-21 09:00:00")


def correr(ruta_motor, tag, base):
    spec = importlib.util.spec_from_file_location(f"motor_{tag}", ruta_motor)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    ent, sal = base / tag / "in", base / tag / "out"
    ent.mkdir(parents=True)
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    orig_now = pd.Timestamp.now
    pd.Timestamp.now = classmethod(lambda cls, tz=None: FIJO)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = m.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx"))
    finally:
        pd.Timestamp.now = orig_now
    return res, sal, buf.getvalue()


def celdas(ruta):
    wb = load_workbook(ruta)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = {
            "dim": ws.dimensions, "tablas": {t.name: t.ref for t in ws.tables.values()},
            "celdas": {(c.row, c.column): (c.value, c.number_format) for f in ws.iter_rows() for c in f if c.value is not None},
        }
    return out


def main(a, b):
    fallos = []
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ra, sa, oa = correr(a, "original", t)
        rb, sb, ob = correr(b, "con_P1", t)
        def check(nombre, ok, detalle=""):
            print(("IDENTICO  " if ok else "DIFERENTE ") + nombre + (f"  {detalle}" if detalle else ""))
            if not ok: fallos.append(nombre)
        ba, bb = (sa / "LISTS.csv").read_bytes(), (sb / "LISTS.csv").read_bytes()
        check("LISTS.csv (bytes)", ba == bb, f"{len(ba)} bytes; sha " + __import__('hashlib').sha256(ba).hexdigest()[:16])
        ca, cb = celdas(sa / "NORMALIZADO.xlsx"), celdas(sb / "NORMALIZADO.xlsx")
        check("NORMALIZADO.xlsx hojas", list(ca) == list(cb), str(list(ca)))
        for h in ca:
            check(f"NORMALIZADO.xlsx · {h} (valores+formatos+tablas)", ca[h] == cb[h], f"{len(ca[h]['celdas'])} celdas")
        for k in ("df_final", "df_validacion", "resumen", "df_resultado_archivos", "df_deteccion_final"):
            try:
                pd.testing.assert_frame_equal(ra[k], rb[k]); ok = True
            except AssertionError:
                ok = False
            check(f"retorno['{k}']", ok)
        check("claves del retorno", set(rb) - set(ra) == {"origen_estado"} and set(ra) <= set(rb), f"nuevas: {sorted(set(rb) - set(ra))}")
        # se ignoran las lineas de ORIGEN, las lineas en blanco y la carpeta temporal de cada corrida
        def limpio(texto, carpeta):
            return [x.replace(str(carpeta), "<TMP>") for x in texto.splitlines()
                    if x.strip() and "ORIGEN" not in x and "Archivo técnico" not in x]
        la, lb = limpio(oa, t / "original"), limpio(ob, t / "con_P1")
        check("salida de consola (sin lineas de ORIGEN)", la == lb, f"{len(la)} lineas")
        print("ORIGEN.xlsx solo en el motor con P1:", (sb / "ORIGEN.xlsx").exists(), "/", (sa / "ORIGEN.xlsx").exists())
        print("archivos de salida original:", sorted(p.name for p in sa.iterdir()))
        print("archivos de salida con P1  :", sorted(p.name for p in sb.iterdir()))
    print("\nRESULTADO:", "SIN CAMBIOS DE COMPORTAMIENTO OPERATIVO" if not fallos else f"DIFERENCIAS: {fallos}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
