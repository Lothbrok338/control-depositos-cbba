"""Bloque REAL de `btnImportacionMasivaP9` tal como está en el tenant (P9_PRUEBA_MASIVA, `tenant/Main_Screen.pa.yaml`).

CHECKPOINT «sync tenant»: `Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml` YA NO se genera desde p9/reversion/powerapps/Main_Screen.yaml;
es una copia VERBATIM del `Main_Screen.pa.yaml` exportado del tenant (que además lleva los fixes manuales de `Visible` con
`mostrarConfirmacion` y el resto de cambios hechos en Studio). `BLOQUE` solo alimenta `BOTON_MAIN_SCREEN_PEGAR.yaml`. Este módulo ya no escribe
ningún archivo.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ORIGEN = RAIZ / "p9/reversion/powerapps/Main_Screen.yaml"
DESTINO = Path(__file__).resolve().parent / "Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml"
ANCLA = "            - lblCantidadResultadosP9_1:\n"
BLOQUE = """            - btnImportacionMasivaP9:
                Control: Classic/Button@2.2.0
                Properties:
                  BorderStyle: =BorderStyle.None
                  Color: =RGBA(255, 255, 255, 1)
                  Fill: =RGBA(123, 22, 50, 1)
                  Font: =Font.'Segoe UI'
                  FontWeight: =FontWeight.Bold
                  Height: =32
                  OnSelect: |-
                    =Navigate(
                        P9_Confirmacion_Masiva,
                        ScreenTransition.Fade
                    )
                  Size: =9
                  Text: ="IMPORTACION MASIVA"
                  Visible: =Not(Coalesce(mostrarConfirmacion, false))
                  Width: =173
                  X: =828
                  Y: =27
"""


def aplicar(texto: str) -> str:
    assert texto.count(ANCLA) == 1, "ancla no encontrada o repetida"
    return texto.replace(ANCLA, BLOQUE + ANCLA)


if __name__ == "__main__":
    raise SystemExit("Obsoleto: Main_Screen_CON_BOTON_IMPORTACION_MASIVA.yaml es el export real del tenant; no se regenera.")
