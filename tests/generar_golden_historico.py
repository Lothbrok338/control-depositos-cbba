"""Genera golden/historico/MANIFEST_HISTORICO.json: huella de cada EXTRACTO_HISTORICO de los 12 fixtures.

    python generar_golden_historico.py --force

La huella (columnas, filas, zona superior, SHA-256 de valores y formatos) protege contra cambios sin copiar
los movimientos al repositorio. Regenerar solo con motivo explicito (cambio aprobado de la capa 4).
"""
import importlib.util, json, shutil, sys, tempfile
from pathlib import Path

from helpers import EXTRACTOS, FIXTURES, FORMATOS_OK, GOLDEN, RAIZ, cargar_motor, huella_historico

if "--force" not in sys.argv:
    sys.exit("Uso: python generar_golden_historico.py --force")
spec = importlib.util.spec_from_file_location("historico", RAIZ.parent / "historico.py")
hist = importlib.util.module_from_spec(spec); spec.loader.exec_module(hist)
with tempfile.TemporaryDirectory() as t:
    t = Path(t); ent = t / "in"; ent.mkdir()
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    cargar_motor().ejecutar_motor(str(ent), str(t / "out" / "NORMALIZADO.xlsx"))
    info = hist.generar_extractos_historicos(str(t / "out" / "ORIGEN.xlsx"), str(t / "out" / "NORMALIZADO.xlsx"),
                                             str(t / "hist"))
    assert info["estado"] == "OK", info
    man = {a["nombre_archivo"]: huella_historico(a["ruta"]) for a in info["archivos"]}
d = GOLDEN / "historico"; d.mkdir(exist_ok=True)
(d / "MANIFEST_HISTORICO.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(f"{len(man)} huellas escritas en {d / 'MANIFEST_HISTORICO.json'}")
