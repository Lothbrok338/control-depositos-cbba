"""Contrato P9: única fuente de nombres, entradas, salidas y valores de los dos flujos.

Solo constantes. No importa nada de P6/P7/P8: los valores del piloto se repiten aquí como literales y la
prueba `test_16` comprueba que coinciden con los de P8 (si P8 cambia de sitio/lista, P9 lo detecta).
"""

# ---------------------------------------------------------------- tenant piloto (SOLO piloto P9)
SITIO_SHAREPOINT = "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu"
LISTA_DEPOSITOS_ACTIVOS_ID = "296c450a-25d6-415b-ad10-c909c74817cb"
LISTA_DEPOSITOS_ACTIVOS = "Depositos_Activos"

# ---------------------------------------------------------------- estados (NO se agregan más)
ESTADO_DISPONIBLE = "DISPONIBLE"
ESTADO_ASIGNADO = "ASIGNADO"
ESTADOS = (ESTADO_DISPONIBLE, ESTADO_ASIGNADO)
CAMPO_ESTADO = "ESTADO_ASIGNACION"

# ---------------------------------------------------------------- flujos
NOMBRE_FLUJO_ASIGNAR = "P9_ASIGNAR_DEPOSITO"
NOMBRE_FLUJO_HABILITAR = "P9_HABILITAR_ESTADO_ASIGNADO"
ZIP_ASIGNAR = "P9_ASIGNAR_DEPOSITO.zip"
ZIP_HABILITAR = "P9_HABILITAR_ESTADO_ASIGNADO.zip"

# Entradas del trigger «Power Apps (V2)», EN ORDEN. Power Apps las pasa por posición en `.Run(...)`.
# (clave interna del trigger, nombre lógico, tipo, obligatorio, título visible en Power Automate)
ENTRADAS = (
    ("number", "id", "number", True, "ID SharePoint"),
    ("text", "clave", "string", True, "CLAVE_TRANSACCION"),
    ("text_1", "estudiante", "string", True, "ESTUDIANTE"),
    ("text_2", "codigo_estudiante", "string", True, "CODIGO_ESTUDIANTE"),
    ("text_3", "solicitado_por", "string", True, "SOLICITADO_POR"),
    ("text_4", "sede_asignacion", "string", True, "SEDE_ASIGNACION"),
    ("text_5", "observacion", "string", False, "OBSERVACION"),
    ("text_6", "usuario", "string", True, "USUARIO_ASIGNACION"),
)
OBLIGATORIOS_TEXTO = ("clave", "estudiante", "codigo_estudiante", "solicitado_por", "sede_asignacion", "usuario")
MAX_TEXTO = 255  # columnas «Texto de una línea» de SharePoint

# Columnas de Depositos_Activos que ESTE flujo escribe (todas operativas; ninguna de las 26 del motor).
CAMPOS_ESCRITOS = (
    "ESTADO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION",
    "OBSERVACION", "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION",
)

# Salida hacia Power Apps (claves del Response).
SALIDAS = ("resultado", "codigo", "mensaje", "estado_actual", "asignado_por", "fecha_hora_asignacion")
RESULTADOS = ("ASIGNADO", "NO_DISPONIBLE", "CONFLICTO", "ERROR")

# Las 26 columnas del motor tal como viven en Depositos_Activos (InternalName). Literal independiente de
# adaptador_m365.COLUMNAS_TECNICAS: si alguien cambia una, la prueba lo detecta.
COLUMNAS_MOTOR_26 = (
    "CLAVE_TRANSACCION", "CODIGO_ASIGNACION", "BANCO", "CUENTA_BANCARIA", "MONEDA", "FECHA_MOVIMIENTO",
    "HORA_MOVIMIENTO", "IMPORTE", "DEBITO", "CREDITO", "TIPO_MOVIMIENTO", "SALDO", "DESCRIPCION",
    "DEPOSITANTE_ORIGINANTE", "INFORMACION_ADICIONAL", "MOTOR_ESTADO", "MOTOR_ESTUDIANTE",
    "MOTOR_SOLICITADO_POR", "MOTOR_SEDE_SOLICITANTE", "MOTOR_CONFIRMADO_POR", "MOTOR_FECHA_CONFIRMACION",
    "MOTOR_OBSERVACION", "TEXTO_BUSQUEDA", "ARCHIVO_ORIGEN", "LOTE_CARGA", "FECHA_CARGA",
)

# ---------------------------------------------------------------- índices de Depositos_Activos (P9_HABILITAR_ESTADO_ASIGNADO)
# (InternalName, tipo de metadatos REST de la columna, origen). El provisionador P9 verifica los 7 y crea los que falten;
# nunca elimina ni desactiva un índice. CLAVE_TRANSACCION (índice único de P8) no forma parte de este contrato: no se toca.
INDICES_EXISTENTES = (
    ("ESTADO_ASIGNACION", "SP.FieldChoice"),
    ("FECHA_MOVIMIENTO", "SP.FieldDateTime"),
    ("BANCO", "SP.FieldText"),
    ("LOTE_CARGA", "SP.FieldText"),
)
INDICES_NUEVOS = (
    ("CODIGO_ASIGNACION", "SP.FieldText"),
    ("IMPORTE", "SP.FieldNumber"),
    ("TIPO_MOVIMIENTO", "SP.FieldText"),
)
INDICES = INDICES_EXISTENTES + INDICES_NUEVOS
