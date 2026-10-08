# -*- coding: utf-8 -*-
"""
p10/contrato.py · P10-A.1 · contrato del generador histórico.

Solo constantes y tablas de mapeo; NINGUNA lógica de normalización. Las 26 columnas y su orden se
importan del motor P0 (`COLUMNAS_LISTS`), los estados y los campos operativos del contrato P9; nada
se copia a mano.
"""
from motor_control_depositos_cbba import COLUMNAS_LISTS          # P0: única fuente de las 26 columnas
from p9.contrato import CAMPO_ESTADO, ESTADO_ASIGNADO, ESTADO_DISPONIBLE, ESTADOS   # P9: estados vigentes
from p9.reversion.contrato import CAMPOS_LIMPIAR                 # P9: campos que limpia una reversión

VERSION_P10 = "P10-A.1"
VERSION_SNAPSHOT = "P10-SNAPSHOT-1"

# ---------------------------------------------------------------- libro
HOJA_EXTRACTO = "EXTRACTO"
HOJA_AUDITORIA = "AUDITORIA"
HOJAS = (HOJA_EXTRACTO, HOJA_AUDITORIA)             # exactamente dos hojas, ambas visibles
TABLA_EXTRACTO = "tblEXTRACTO"                       # la define historico.py (P3b)
TABLA_AUDITORIA = "tblAUDITORIA"
PLANTILLA_NOMBRE_ARCHIVO = "EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{MONEDA}_{PERIODO}.xlsx"

# Tras las columnas propias del banco, en este orden. CLAVE TRANSACCIÓN va después, oculta (vínculo técnico).
COLUMNA_OBSERVACIONES = "OBSERVACIONES"
COLUMNAS_OPERATIVAS_EXTRACTO = ("ESTADO", "CONFIRMADO POR", "FECHA DE CONFIRMACIÓN", COLUMNA_OBSERVACIONES)
COLUMNA_CLAVE = "CLAVE TRANSACCIÓN"
ANCHO_OBSERVACIONES = 42
# CONFIRMADO POR guarda el correo completo (UPN); el ancho 22 de la capa 4 lo cortaría a la vista.
ANCHO_CONFIRMADO_POR = 34

# ---------------------------------------------------------------- snapshot (Depositos_Activos)
CAMPO_CLAVE = "CLAVE_TRANSACCION"
CAMPOS_SNAPSHOT = (
    CAMPO_CLAVE, CAMPO_ESTADO, "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION",
    "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "OBSERVACION", "ULTIMA_REVERSION_ID",
)
# Columna de las 26 de P0 -> campo operativo de Depositos_Activos que la alimenta (nombres internos reales de P8/P9).
OPERATIVOS = {
    "ESTADO": CAMPO_ESTADO,
    "ESTUDIANTE": "ESTUDIANTE",
    "SOLICITADO POR": "SOLICITADO_POR",
    "SEDE SOLICITANTE": "SEDE_ASIGNACION",
    "CONFIRMADO POR": "USUARIO_ASIGNACION",
    "FECHA CONFIRMACIÓN": "FECHA_HORA_ASIGNACION",
    "OBSERVACIÓN": "OBSERVACION",
}
COLUMNAS_FIJAS = tuple(c for c in COLUMNAS_LISTS if c not in OPERATIVOS)   # las 19 que P10 nunca cambia
# CODIGO_ESTUDIANTE existe en Depositos_Activos pero NO tiene columna en las 26 de P0: P10-A.1 no lo proyecta.
SIN_COLUMNA_EN_26 = ("CODIGO_ESTUDIANTE", "ULTIMA_REVERSION_ID")

# Lo que ve el usuario (Power Apps) para cada estado de P9: ASIGNADO se muestra como CONFIRMADO.
ESTADO_VISIBLE = {ESTADO_DISPONIBLE: "DISPONIBLE", ESTADO_ASIGNADO: "CONFIRMADO"}

# Campos que un depósito ASIGNADO debe traer completos (los obligatorios de P9; CODIGO_ESTUDIANTE puede ir vacío).
OBLIGATORIOS_ASIGNADO = ("ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "USUARIO_ASIGNACION",
                         "FECHA_HORA_ASIGNACION")

# ---------------------------------------------------------------- hoja AUDITORIA: tipo y ancho por columna
TIPO_AUDITORIA = {
    "CLAVE TRANSACCIÓN": "codigo", "CÓDIGO DE ASIGNACIÓN": "codigo", "BANCO": "texto",
    "CUENTA BANCARIA": "codigo", "MONEDA": "texto", "FECHA MOVIMIENTO": "fecha",
    "HORA MOVIMIENTO": "texto",            # la lista Depositos_Activos la guarda como texto (HH:MM:SS)
    "IMPORTE": "importe", "DÉBITO": "importe", "CRÉDITO": "importe", "TIPO MOVIMIENTO": "texto",
    "SALDO": "importe", "DESCRIPCIÓN": "texto", "DEPOSITANTE / ORIGINANTE": "texto",
    "INFORMACIÓN ADICIONAL": "texto", "ESTADO": "texto", "ESTUDIANTE": "texto", "SOLICITADO POR": "texto",
    "SEDE SOLICITANTE": "texto", "CONFIRMADO POR": "texto", "FECHA CONFIRMACIÓN": "fecha_hora",
    "OBSERVACIÓN": "texto", "TEXTO DE BÚSQUEDA": "texto", "ARCHIVO ORIGEN": "texto",
    "LOTE DE CARGA": "codigo", "FECHA DE CARGA": "fecha_hora_seg",
}
ANCHO_AUDITORIA = {
    "CLAVE TRANSACCIÓN": 44, "CÓDIGO DE ASIGNACIÓN": 16, "BANCO": 16, "CUENTA BANCARIA": 20, "MONEDA": 9,
    "FECHA MOVIMIENTO": 13, "HORA MOVIMIENTO": 11, "IMPORTE": 14, "DÉBITO": 14, "CRÉDITO": 14,
    "TIPO MOVIMIENTO": 13, "SALDO": 16, "DESCRIPCIÓN": 34, "DEPOSITANTE / ORIGINANTE": 34,
    "INFORMACIÓN ADICIONAL": 50, "ESTADO": 14, "ESTUDIANTE": 24, "SOLICITADO POR": 22,
    "SEDE SOLICITANTE": 16, "CONFIRMADO POR": ANCHO_CONFIRMADO_POR, "FECHA CONFIRMACIÓN": 18, "OBSERVACIÓN": 34,
    "TEXTO DE BÚSQUEDA": 50, "ARCHIVO ORIGEN": 22, "LOTE DE CARGA": 18, "FECHA DE CARGA": 20,
}

# ---------------------------------------------------------------- invariantes (fallan al importar, no en producción)
assert len(COLUMNAS_LISTS) == 26
assert set(TIPO_AUDITORIA) == set(COLUMNAS_LISTS) == set(ANCHO_AUDITORIA)
assert set(ESTADO_VISIBLE) == set(ESTADOS)
assert set(OPERATIVOS) <= set(COLUMNAS_LISTS) and len(COLUMNAS_FIJAS) == 19
assert set(OPERATIVOS.values()) | set(SIN_COLUMNA_EN_26) <= set(CAMPOS_SNAPSHOT)
assert set(CAMPOS_LIMPIAR) <= set(CAMPOS_SNAPSHOT)
