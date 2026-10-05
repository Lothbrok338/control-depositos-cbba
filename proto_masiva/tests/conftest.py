import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for ruta in (RAIZ, Path(__file__).resolve().parent):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))
