# -*- coding: utf-8 -*-
"""
p10/control_lista.py · P10-A.2 · contrato de la lista de SharePoint `P10_Control` (control, registro y bloqueo del sincronizador).

Una sola lista, tres tipos de elemento (columna TIPO):
    LOCK      un único elemento (CLAVE_CONTROL = LOCK): bloqueo lógico con vigencia (LOCK_HASTA/LOCK_ID), ULTIMA_COMPLETA y CURSOR_LISTA
    GRUPO     BANCO+CUENTA+MONEDA+MES: último estado confirmado (versión, sellos, rutas, hash de lo último aplicado de la lista)
    EXTRACTO  registro de cada extracto de PROCESADOS incorporado (idempotencia: ruta, bytes, grupos que alimentó)
    (el cursor de lectura de Depositos_Activos —CURSOR_LISTA— vive en el elemento LOCK)
Todas las columnas son texto o número: ninguna fecha de SharePoint (sin conversiones de zona horaria).
"""
LISTA_CONTROL = "P10_Control"

# (nombre interno, tipo, longitud o decimales, indexada, valores únicos)
CAMPOS_CONTROL = (
    ("CLAVE_CONTROL", "Text", 255, True, True),
    ("TIPO", "Text", 20, True, False),
    ("PERIODO", "Text", 7, True, False),
    ("ESTADO", "Text", 20, False, False),
    ("BANCO", "Text", 50, False, False),
    ("CUENTA", "Text", 50, False, False),
    ("MONEDA", "Text", 10, False, False),
    ("RUTA_XLSX", "Text", 255, False, False),
    ("RUTA_ESTADO", "Text", 255, False, False),
    ("HASH_OPERATIVO", "Text", 64, False, False),
    ("HASH_INTENTO", "Text", 64, False, False),
    ("HASH_ESTADO", "Text", 64, False, False),
    ("HASH_XLSX", "Text", 64, False, False),
    ("HASH_EXTRACTO", "Text", 64, False, False),
    ("CURSOR_LISTA", "Text", 20, False, False),
    ("ULTIMA_SYNC", "Text", 19, False, False),
    ("RECONSTRUIR_DESDE", "Text", 19, False, False),
    ("LOCK_HASTA", "Text", 19, False, False),
    ("LOCK_ID", "Text", 64, False, False),
    ("ULTIMA_COMPLETA", "Text", 10, False, False),
    ("VERSION_ESTADO", "Number", 0, False, False),
    ("ESTADO_BYTES", "Number", 0, False, False),
    ("XLSX_BYTES", "Number", 0, False, False),
    ("MOVIMIENTOS", "Number", 0, False, False),
    ("INTENTOS", "Number", 0, False, False),
    ("BYTES", "Number", 0, False, False),
    ("GRUPOS", "Note", 0, False, False),
    ("DETALLE", "Note", 0, False, False),
)
NOMBRES_CONTROL = tuple(c[0] for c in CAMPOS_CONTROL)
TIPOS = ("LOCK", "GRUPO", "EXTRACTO")
