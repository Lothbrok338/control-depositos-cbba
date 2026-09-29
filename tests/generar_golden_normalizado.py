"""Genera las referencias doradas de NORMALIZADO.xlsx (4 hojas) y LISTS.csv del lote de 12 fixtures.

Se ejecuta UNA vez contra el motor ORIGINAL (sin P1):
    MOTOR_PATH=/ruta/al/motor_original.py python generar_golden_normalizado.py --force
Cada hoja se guarda como CSV de texto (sin columnas volatiles LOTE/FECHA DE CARGA) en golden/.
"""
import shutil, sys, tempfile
from pathlib import Path

import pandas as pd

from helpers import EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN, cargar_motor, COLS_VOLATILES

HOJAS = ["LISTS", "VALIDACION", "RESUMEN", "DIAGNOSTICO"]


def hoja_a_texto(xlsx, hoja):
    d = pd.read_excel(xlsx, sheet_name=hoja, dtype=str, keep_default_na=False)
    d = d.drop(columns=[c for c in COLS_VOLATILES if c in d.columns])
    return d.to_csv(index=False, lineterminator="\n")


def main():
    if "--force" not in sys.argv:
        sys.exit("Use --force para sobrescribir las doradas de NORMALIZADO.xlsx")
    motor = cargar_motor()
    with tempfile.TemporaryDirectory() as t:
        ent = Path(t) / "in"; ent.mkdir()
        for fm in FORMATOS_OK:
            shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
        salida = Path(t) / "out" / "NORMALIZADO.xlsx"
        motor.ejecutar_motor(str(ent), str(salida))
        for h in HOJAS:
            (GOLDEN / f"LOTE_12_NORMALIZADO__{h}.csv").write_text(hoja_a_texto(salida, h), encoding="utf-8")
    print("doradas escritas:", [f"LOTE_12_NORMALIZADO__{h}.csv" for h in HOJAS])


if __name__ == "__main__":
    main()
