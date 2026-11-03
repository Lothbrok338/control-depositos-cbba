"""Contrato ÚNICO de la plantilla de confirmación masiva (V1). Solo constantes.

Lo importan el generador de plantillas, el generador del flujo, el generador de fixtures y las pruebas:
las 9 columnas y el nombre de la tabla NO se repiten en ningún otro archivo.
"""

NOMBRE_TABLA = "tblConfirmacionMasiva"
ENCABEZADOS = ("BANCO", "CUENTA_BANCARIA", "CODIGO_ASIGNACION", "IMPORTE", "MONEDA",
               "ESTUDIANTE", "SOLICITADO_POR", "SEDE", "OBSERVACION")
OPCIONALES = ("OBSERVACION",)
OBLIGATORIAS = tuple(h for h in ENCABEZADOS if h not in OPCIONALES)
MONEDAS = ("BOB", "USD")
ARCHIVO_PLANTILLA = "Plantilla_Confirmacion_Masiva_P9.xlsx"   # VACÍA, para entregar al usuario
ARCHIVO_EJEMPLO = "Ejemplo_Confirmacion_Masiva_P9.xlsx"       # misma plantilla con 3 filas ficticias
HOJA_CARGA = "CARGA"
HOJA_CATALOGOS = "_CATALOGOS"
