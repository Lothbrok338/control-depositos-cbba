"""Deriva P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml (solo controles hijos, como COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml)
y BOTON_MAIN_SCREEN_PEGAR.yaml desde las fuentes únicas: P9_Confirmacion_Masiva.pa.yaml y aplicar_boton.BLOQUE.

    python proto_masiva/powerapps/derivar_pegar.py
"""
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))
from aplicar_boton import BLOQUE  # noqa: E402


def hijos(texto: str) -> str:
    lineas = texto.splitlines(keepends=True)
    inicio = lineas.index("    Children:\n") + 1
    return "".join(l[6:] if l.strip() else l for l in lineas[inicio:])


def dedentar(texto: str, n: int) -> str:
    return "".join(l[n:] if l.strip() else l for l in texto.splitlines(keepends=True))


if __name__ == "__main__":
    fuente = (CARPETA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8")
    (CARPETA / "P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml").write_text(hijos(fuente), encoding="utf-8")
    (CARPETA / "BOTON_MAIN_SCREEN_PEGAR.yaml").write_text(dedentar(BLOQUE, 12), encoding="utf-8")
    print("ok")
