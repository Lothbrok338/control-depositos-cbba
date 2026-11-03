# -*- coding: utf-8 -*-
"""
p10/motor_p0.py · P10-A.1 · puerta al motor REAL de P0.

P10 no normaliza nada: ejecuta `motor_control_depositos_cbba.ejecutar_motor` (el mismo punto de entrada que
usa la producción) sobre los extractos bancarios y toma sus salidas tal como salen:

    LISTS.csv     las 26 columnas (CLAVE TRANSACCIÓN, BANCO, CUENTA, MONEDA, FECHA, HORA, IMPORTE, DÉBITO,
                  CRÉDITO, SALDO, ...) ya validadas contra el saldo del banco
    ORIGEN.xlsx   captura íntegra del extracto (de aquí salen las columnas propias de cada banco)

Este módulo no contiene ninguna regla de normalización ni de clave. No cambia el comportamiento de P0.
"""
import contextlib
import io
import os
from dataclasses import dataclass

import motor_control_depositos_cbba as _motor


class ErrorP0(RuntimeError):
    """P0 no produjo las salidas que P10 necesita."""


@dataclass(frozen=True)
class SalidaP0:
    carpeta: str
    lists_csv: str
    normalizado_xlsx: str
    origen_xlsx: str
    movimientos: int


def motor_real():
    """El módulo del motor P0 tal cual está en el repositorio."""
    return _motor


def ejecutar_p0(carpeta_entrada, carpeta_salida, silencioso=True):
    """Corre P0 sobre `carpeta_entrada` y deja NORMALIZADO.xlsx, LISTS.csv y ORIGEN.xlsx en `carpeta_salida`."""
    os.makedirs(carpeta_salida, exist_ok=True)
    ruta = os.path.join(os.path.abspath(carpeta_salida), "NORMALIZADO.xlsx")
    consola = io.StringIO()
    with (contextlib.redirect_stdout(consola) if silencioso else contextlib.nullcontext()):
        res = _motor.ejecutar_motor(os.path.abspath(carpeta_entrada), ruta)
    origen = res.get("origen_estado") or {}
    if origen.get("estado") != "OK" or not origen.get("ruta_origen"):
        raise ErrorP0(f"P0 no generó ORIGEN.xlsx: {origen.get('error') or origen}")
    salida = SalidaP0(carpeta=os.path.dirname(ruta), lists_csv=res["ruta_lists_csv"], normalizado_xlsx=ruta,
                      origen_xlsx=origen["ruta_origen"], movimientos=len(res["df_final"]))
    for p in (salida.lists_csv, salida.origen_xlsx):
        if not os.path.exists(p):
            raise ErrorP0(f"falta la salida de P0: {p}")
    return salida
