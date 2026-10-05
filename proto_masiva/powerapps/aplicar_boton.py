"""Genera, SIN modificar el original, una copia de Main_Screen.yaml con el botón IMPORTACIÓN MASIVA.

    python proto_masiva/powerapps/aplicar_boton.py

Lee p9/reversion/powerapps/Main_Screen.yaml (fuente validada en tenant; intacta) y escribe
proto_masiva/powerapps/Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml. El único cambio es insertar BLOQUE justo antes de
`lblCantidadResultadosP9_1` (dentro de `cntControlDepositosP9`, a continuación de `btnActualizarP9_1`).
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ORIGEN = RAIZ / "p9/reversion/powerapps/Main_Screen.yaml"
DESTINO = Path(__file__).resolve().parent / "Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml"
ANCLA = "            - lblCantidadResultadosP9_1:\n"
BLOQUE = """            - btnImportacionMasivaP9:
                Control: Classic/Button@2.2.0
                Properties:
                  BorderColor: =RGBA(123, 22, 50, 1)
                  BorderThickness: =1
                  Color: =RGBA(123, 22, 50, 1)
                  Fill: =RGBA(255, 255, 255, 1)
                  Font: =Font.'Segoe UI'
                  FontWeight: =FontWeight.Bold
                  Height: =32
                  OnSelect: =Navigate(P9_Confirmacion_Masiva, ScreenTransition.Fade)
                  Size: =9
                  Text: ="IMPORTACIÓN MASIVA"
                  Width: =190
                  X: =700
                  Y: =27
"""


def aplicar(texto: str) -> str:
    assert texto.count(ANCLA) == 1, "ancla no encontrada o repetida"
    return texto.replace(ANCLA, BLOQUE + ANCLA)


if __name__ == "__main__":
    DESTINO.write_bytes(aplicar(ORIGEN.read_bytes().decode("utf-8")).encode("utf-8"))
    print(DESTINO)
