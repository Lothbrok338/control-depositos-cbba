# Informe de pruebas del normalizador (Fase 2 + P1/P2: captura y preservación de origen)

Resumen: PASS=270, SKIP=19, XFAIL=18

## 1. Regresión por banco/formato (extractos reales)

| Formato | Archivo | Detección | Hoja+encab. | Banco/cuenta/moneda | = Dorada | Conteo (oráculo) | Cadena saldos | Validación saldos | Integridad | Clave | Cuenta en cabecera | Resultado |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BCP_ME | bcp_me_1.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BCP_MN | bcp_mn_3.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BISA_ME | bisa_me_2.xls | PASS | PASS | SKIP | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BISA_MN | bisa_mn_2.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BNB_AHORRO | bnb_ahorro_2.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BNB_ME | bnb_me_1_1.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BNB_MN | bnb_mn_3.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BNB_CLINICA | clinica_1.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| ECO_CTA_CTE | economico_1.xlsx | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| ECO_AHORRO | economico_ahorro.xlsx | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BMSC | mercantil_1.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| UNION_MN | union_mn_2.xls | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| UNION_ME (`UNION_FECHAS_V1`) | *sin extracto real en el repo* | PASS (proxy sintético) | PENDIENTE archivo real | — | — | — | — | — | — | — | — | **ESTRUCTURA: CONFIRMADA (código legado + captura real) · ARCHIVO REAL VACÍO: pendiente · MOVIMIENTOS: REQUIERE MUESTRA REAL CON MOVIMIENTOS** |

**Estructura UNION_ME = confirmada por código legado (`HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `detectar_formato`, `normalizar_union`) + captura real; comportamiento con movimientos = pendiente de fixture real.** UNION_ME es un formato válido (`UNION_FECHAS_V1`, hoja `ExtractoMovimientosFechas`, cuenta 20000003224544, columnas `Fecha Movimiento | AG | Descripción | Nro Documento | Monto | Saldo | Nro de verificasion`). `Nro de verificasion` proviene de la captura real; el motor legado no la lee (se pierde) y no entra a las 26 columnas. La muestra real está vacía y aún no está en el repositorio (`fixtures/extractos/union_me_vacio.xls`): sus pruebas estructurales se activan al colocarla. El reporte «Últimos 12 Movimientos» quedó como fixture **negativo** (`fixtures/negativos/`).

## 2. Contrato, lote completo y UNION_ME (estructura)

| Prueba | Casos | Estado |
|---|---|---|
| `test_01_contrato.py::test_columnas_lists_exactas` | 1 | PASS |
| `test_01_contrato.py::test_clave_transaccion_formula_congelada` | 1 | PASS |
| `test_01_contrato.py::test_clave_sin_hora_ni_saldo` | 1 | PASS |
| `test_01_contrato.py::test_numero_casos_validos` | 9 | PASS |
| `test_01_contrato.py::test_normalizar_fecha_casos_validos` | 5 | PASS |
| `test_01_contrato.py::test_normalizar_hora_casos_validos` | 4 | PASS |
| `test_01_contrato.py::test_codigo_texto` | 1 | PASS |
| `test_02_regresion_formatos.py::test_bisa_me_sin_movimientos_es_valido` | 1 | PASS |
| `test_02_regresion_formatos.py::test_totales_pie_de_pagina_coinciden` | 1 | PASS |
| `test_02_regresion_formatos.py::test_union_ultimos12_no_es_fixture_de_union_me_y_se_rechaza` | 1 | PASS |
| `test_02_regresion_formatos.py::test_union_me_contrato_legado_en_constantes_del_motor` | 1 | PASS |
| `test_02_regresion_formatos.py::test_union_me_normalizar_union_asigna_cuenta_y_moneda_en_codigo` | 1 | PASS |
| `test_02_regresion_formatos.py::test_union_me_estructura_proxy_sintetico_se_detecta` | 1 | PASS |
| `test_02_regresion_formatos.py::test_union_me_fixture_estructural_real_detecta_y_tiene_hoja_y_columnas` | 1 | SKIP |
| `test_02_regresion_formatos.py::test_union_me_fixture_estructural_real_sin_movimientos_no_bloquea` | 1 | SKIP |
| `test_02_regresion_formatos.py::test_union_me_movimientos_normalizan` | 1 | SKIP |
| `test_02_regresion_formatos.py::test_union_me_saldos_validan` | 1 | SKIP |
| `test_02_regresion_formatos.py::test_union_me_debitos_conservan_campos` | 1 | SKIP |
| `test_02_regresion_formatos.py::test_union_me_nro_de_verificasion_se_conserva` | 1 | SKIP |
| `test_03_lote.py::test_lote_csv_igual_a_dorada` | 1 | PASS |
| `test_03_lote.py::test_lote_csv_utf8_bom_y_columnas` | 1 | PASS |
| `test_03_lote.py::test_lote_xlsx_hojas_tabla_y_formatos` | 1 | PASS |
| `test_03_lote.py::test_lote_totales_y_orden` | 1 | PASS |
| `test_03_lote.py::test_xlsx_y_csv_tienen_mismas_filas_y_claves` | 1 | PASS |
| `test_03_lote.py::test_lote_bloquea_formato_repetido` | 1 | PASS |
| `test_03_lote.py::test_lote_ignora_archivos_normalizado_y_no_excel` | 1 | PASS |
| `test_03_lote.py::test_d20_archivos_del_sistema_no_son_extractos` | 9 | PASS |
| `test_03_lote.py::test_d20_extractos_reales_con_nombres_parecidos_siguen_incluidos` | 1 | PASS |
| `test_03_lote.py::test_d20_corrida_completa_con_salidas_en_la_carpeta_de_entrada` | 1 | PASS |
| `test_04_defectos_conocidos.py::test_formato_union_nuevo_no_hereda_cuenta_ajena` | 1 | XFAIL |
| `test_04_defectos_conocidos.py::test_union_me_vacio_no_bloquea` | 1 | XFAIL |
| `test_05_preservacion.py::test_union_me_estructura_vacia_se_captura_con_nro_de_verificasion` | 1 | PASS |
| `test_05_preservacion.py::test_union_me_nro_de_verificasion_viaja_a_origen_y_no_a_lists_proxy_sintetico` | 1 | PASS |
| `test_05_preservacion.py::test_union_me_archivo_real_vacio_se_captura_completo` | 1 | SKIP |
| `test_05_preservacion.py::test_union_me_real_completitud_con_movimientos` | 1 | SKIP |
| `test_05_preservacion.py::test_union_me_real_debitos_completos` | 1 | SKIP |
| `test_05_preservacion.py::test_union_me_real_nro_de_verificasion_y_mapa` | 1 | SKIP |

## 2b. Preservación de origen (P2, `test_05_preservacion.py`)

| Prueba | Casos | Estado |
|---|---|---|
| `test_origen_tiene_las_cuatro_hojas_y_columnas` | 1 | PASS |
| `test_completitud_celda_a_celda` | 12 | PASS |
| `test_textos_que_pandas_por_defecto_convierte_en_vacio_se_conservan` | 1 | PASS |
| `test_escritor_no_convierte_texto_en_formula_ni_rompe_con_caracteres_de_control` | 1 | PASS |
| `test_reconstruccion_del_archivo_desde_la_captura` | 12 | PASS |
| `test_mapa_uno_a_uno_con_el_lote` | 1 | PASS |
| `test_cada_movimiento_apunta_a_su_fila_original` | 11 | PASS |
| `test_id_origen_tiene_formato_documentado` | 1 | PASS |
| `test_debitos_conservan_todas_sus_celdas_originales` | 12 | PASS×4/SKIP×8 |
| `test_columnas_hoy_perdidas_estan_en_la_captura` | 8 | PASS |
| `test_bnb_referencia_e_itf_conservan_el_valor_exacto_del_banco` | 1 | PASS |
| `test_cabecera_encabezado_y_pie_conservados` | 12 | PASS |
| `test_valores_especificos_de_cabecera_y_pie` | 1 | PASS |
| `test_hojas_adicionales_de_bmsc_se_conservan_completas` | 1 | PASS |
| `test_metadatos_esperados` | 12 | PASS |
| `test_metadatos_una_fila_por_extracto` | 1 | PASS |
| `test_ids_son_deterministas_entre_corridas` | 1 | PASS |
| `test_ids_no_dependen_del_nombre_ni_de_la_ruta` | 1 | PASS |
| `test_columnas_vacias_del_formato_se_conservan_y_se_declaran` | 12 | PASS |
| `test_columnas_vacias_conocidas` | 1 | PASS |
| `test_normalizado_xlsx_identico_a_su_dorada` | 4 | PASS |
| `test_lists_csv_identico_a_su_dorada_y_a_la_hoja_lists` | 1 | PASS |
| `test_captura_no_agrega_columnas_ni_cambia_clave` | 1 | PASS |
| `test_si_la_captura_falla_normalizado_y_lists_salen_identicos` | 1 | PASS |
| `test_los_extractos_originales_no_se_modifican` | 1 | PASS |
| `test_union_me_estructura_vacia_se_captura_con_nro_de_verificasion` | 1 | PASS |
| `test_union_me_nro_de_verificasion_viaja_a_origen_y_no_a_lists_proxy_sintetico` | 1 | PASS |
| `test_union_me_archivo_real_vacio_se_captura_completo` | 1 | SKIP×1 |
| `test_union_me_real_completitud_con_movimientos` | 1 | SKIP×1 |
| `test_union_me_real_debitos_completos` | 1 | SKIP×1 |
| `test_union_me_real_nro_de_verificasion_y_mapa` | 1 | SKIP×1 |

## 3. Defectos reales confirmados (fallan hoy; deben pasar tras corregir)

| Código | Estado hoy | Defecto demostrado | Cambio necesario (archivo · función) |
|---|---|---|---|
| D-01 Numero | FALLA (defecto vigente) | '1,234' (coma de miles sin decimales) se lee como 1.234 en vez de 1234 | `motor · numero()` — Tratar 'N,NNN' (grupos de 3 tras la coma, sin punto) como miles; conservar '1234,5' como decimal. |
| D-02 Numero | FALLA (defecto vigente) | negativo entre parentesis '(1,234.56)' devuelve NaN | `motor · numero()` — Aceptar negativo entre parentesis y signo '-' final. |
| D-03 Numero | FALLA (defecto vigente) | miles con varios separadores y sin decimales '1.234.567' / '1,234,567' devuelven NaN | `motor · numero()` — Separador repetido (1.234.567 / 1,234,567) = miles. |
| D-04 Fecha | FALLA (defecto vigente) | ISO '2026-04-03' con dayfirst=True se interpreta como 4 de marzo | `motor · normalizar_fecha()` — Si el texto es ISO (AAAA-MM-DD) parsear sin dayfirst; dayfirst solo para dd/mm/aaaa. |
| D-05 Hora | FALLA (defecto vigente) | fraccion de dia de Excel (0.5) se devuelve como 0.5 en vez de '12:00:00' | `motor · normalizar_hora()` — Convertir float 0<=x<1 (fraccion de dia de Excel) a HH:MM:SS. |
| D-06 Fecha | FALLA (defecto vigente) | el filtro de filas usa pd.to_datetime(dayfirst) y descarta EN SILENCIO fechas '24/Ago/2026' (el Economico si las reconoce con normalizar_fecha): dos criterios distintos | `motor · normalizar_bnb/bcp/union/bisa/bmsc` — Usar el mismo parser (normalizar_fecha) para FILTRAR filas y para el valor final, como ya hace normalizar_economico. |
| D-07 Filas | FALLA (defecto vigente) | una fila con importe y fecha NO interpretable se descarta sin error ni conteo (deberia bloquear o informar filas descartadas) | `motor · normalizar_*` — Contar filas descartadas por fecha; si alguna tiene importe/saldo, lanzar ValueError (pies de pagina 'Total ...' siguen permitidos). |
| D-08 Año | FALLA (defecto vigente) | el año 2026 esta fijo: un movimiento de 2027 bloquea toda la exportacion | `motor · ejecutar_motor (paso 6)` — Reemplazar 2026 fijo por año parametrizable (p. ej. derivado de FECHA A PROCESAR) sin bloquear enero 2027. |
| D-09 Encabezado | FALLA (defecto vigente) | encontrar_fila_encabezado acepta puntaje 0 (fila cualquiera) sin error | `motor · encontrar_fila_encabezado / leer_tabla_movimientos` — Exigir puntaje minimo (p. ej. 100% o umbral fijo) y lanzar ValueError con el formato y las filas inspeccionadas. |
| D-10 Cuenta | FALLA (defecto vigente) | la cuenta se busca en las primeras 40 filas de TODO el archivo: un BNB_CLINICA cuya glosa menciona la cuenta BNB_MN se clasifica como BNB_MN | `motor · detectar_formato` — Buscar la cuenta solo en la zona de cabecera (filas previas al encabezado) y exigir UNA sola cuenta conocida. |
| D-11 Cuenta | FALLA (defecto vigente) | BMSC no verifica el numero de cuenta: cualquier archivo con sus palabras clave se acepta como BMSC y recibe la cuenta fija 1000872489 | `motor · detectar_formato (rama BMSC)` — Verificar 1000872489 en cabecera (aparece en fila 7 col F del extracto real) o devolver NO_RECONOCIDO. |
| D-12 Cuenta Nueva | FALLA (defecto vigente) | un formato UNION_* nuevo cae en el 'else' y recibe SIN ERROR la cuenta y moneda de UNION_ME (20000003224544 / USD) | `motor · normalizar_union/bcp/bisa/economico/bnb` — Reemplazar los 'else' implicitos por un diccionario CUENTAS[formato] que falle si el formato no esta registrado. |
| D-16 Vacios | FALLA (defecto vigente) | un extracto BNB con encabezado y SIN movimientos lanza KeyError y bloquea todo el lote (solo BISA maneja 'sin movimientos', y por un efecto colateral de dropna) | `motor · leer_tabla_movimientos / normalizar_*` — Si el encabezado existe pero no hay filas, devolver DataFrame vacio con COLUMNAS_LISTS y estado SIN MOVIMIENTOS (patron ya usado por BISA). |
| D-16b Vacios | FALLA (defecto vigente) | un UNION_ME por fechas SIN movimientos (formato confirmado por codigo legado + captura real, con 'Nro de verificasion') lanza KeyError y bloquearia todo el lote. Probado con PROXY SINTETICO: confirmar con el archivo real vacio | `motor · leer_tabla_movimientos / normalizar_union` — Un UNION_ME sin movimientos debe devolver 0 filas y estado SIN MOVIMIENTOS (mismo cambio que D-16); confirmar con el archivo real vacío. |
| D-17 Columnas | FALLA (defecto vigente) | si la columna requerida 'Adicionales' viene completamente vacia el dia del extracto, dropna(axis=1) la elimina y buscar_columna lanza KeyError (bloquea todo el lote) | `motor · leer_tabla_movimientos` — No eliminar columnas vacias ANTES de buscar las requeridas (o tratarlas como presentes y vacias). |
| D-13 Salidas | FALLA (defecto vigente) | si una corrida falla, NORMALIZADO.xlsx y LISTS.csv de la corrida anterior quedan en la carpeta y un proceso posterior podria cargarlos como si fueran nuevos | `motor · ejecutar_motor (inicio y paso 10-11)` — Eliminar/mover salidas previas al iniciar y escribir a temporal + renombrar al terminar. |
| D-14 Consola | FALLA (defecto vigente) | los print con emojis fallan con UnicodeEncodeError si la salida se redirige con codificacion cp1252 (p. ej. Windows con redireccion a archivo/pipe) | `motor · bloque __main__ / ejecutar_motor` — sys.stdout.reconfigure(encoding='utf-8') (o quitar emojis) antes del primer print. |
| D-15 Zona Horaria | FALLA (defecto vigente) | LOTE DE CARGA y FECHA DE CARGA usan la hora local de la maquina: en un servidor UTC se desfasan 4 h respecto de Bolivia | `motor · ejecutar_motor (CONFIGURAR LOTE)` — Usar hora de America/La_Paz en fecha_carga y lote. |
