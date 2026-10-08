# -*- coding: utf-8 -*-
"""
P10 · generador del EXTRACTO_HISTORICO operativo (fase A.1).

Paquete ADITIVO: no modifica ningún módulo de P0..P9. Reutiliza tal cual
  * `motor_control_depositos_cbba.ejecutar_motor`  (P0: normalización, CLAVE TRANSACCIÓN, 26 columnas), y
  * `historico.construir_extractos_historicos` / `escribir_extracto_historico`  (P3b: capa 4 aprobada),
y agrega solo lo nuevo de P10: cruce con el snapshot operativo (Depositos_Activos), la columna
OBSERVACIONES, la hoja AUDITORIA, la validación previa a aceptar el archivo y el empaque determinista.

Los módulos de la raíz del repositorio (motor, historico, registro) se importan por nombre; este
archivo se asegura de que la raíz esté en `sys.path` sin importar cómo se importó `p10`.
"""
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)
