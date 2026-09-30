"""Genera las referencias doradas A PARTIR DEL MOTOR ACTUAL (caracterizacion).
Uso:  python generar_golden.py --force
IMPORTANTE: son 'lo que el motor produce hoy', no una verdad externa. Deben contrastarse contra
un NORMALIZADO.xlsx / LISTS.csv aprobados por el usuario cuando esten disponibles.
Solo ejecutar con el motor productivo en un estado aprobado.
P6: usa normalizar_archivo / validar_archivo, retirados del motor en P6. Las doradas se regeneran SOLO contra el motor
ORIGINAL (p. ej. `git worktree add <carpeta> checkpoint-p5` y MOTOR_PATH=<carpeta>/motor_control_depositos_cbba.py)."""
import json, shutil, sys, tempfile
from pathlib import Path
import pandas as pd
from helpers import EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN, a_texto, cargar_motor

if "--force" not in sys.argv:
    sys.exit("Rechazado: usa --force para (re)generar las referencias doradas.")
motor = cargar_motor()
if not hasattr(motor, "normalizar_archivo"):
    sys.exit("Rechazado: el motor en MOTOR_PATH no tiene la normalizacion legada (retirada en P6). Las doradas se "
             "generan contra el motor ORIGINAL: MOTOR_PATH=<checkpoint-p5>/motor_control_depositos_cbba.py")
GOLDEN.mkdir(exist_ok=True)
manifest = {}
ts = pd.Timestamp("2026-01-01")
for fm in FORMATOS_OK:
    ruta = str(EXTRACTOS / FIXTURES[fm])
    df = motor.normalizar_archivo(ruta, fm, "LOTE_TEST", ts, nombre_origen=FIXTURES[fm])
    val = motor.validar_archivo(ruta, fm, df)
    (GOLDEN / f"{fm}.csv").write_text(a_texto(df), encoding="utf-8")
    manifest[fm] = {"archivo": FIXTURES[fm], "movimientos": int(len(df)),
                    "estado_validacion": val["ESTADO"],
                    "saldo_inicial": None if pd.isna(val["SALDO INICIAL"]) else round(float(val["SALDO INICIAL"]), 2),
                    "saldo_final": None if pd.isna(val["SALDO FINAL"]) else round(float(val["SALDO FINAL"]), 2)}
with tempfile.TemporaryDirectory() as t:
    ent = Path(t) / "in"; ent.mkdir()
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    motor.ejecutar_motor(str(ent), str(Path(t) / "out" / "NORMALIZADO.xlsx"))
    shutil.copy(Path(t) / "out" / "LISTS.csv", GOLDEN / "LOTE_12_LISTS.csv")
(GOLDEN / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
print("Doradas generadas en", GOLDEN)
