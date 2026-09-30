# Informe de pruebas del normalizador (Fase 2 + P1/P2: captura y preservación de origen + P3: motor genérico en sombra + P3b: EXTRACTO_HISTORICO + P4: detección por registro + P5: normalización por registro)

Resumen: PASS=620, SKIP=24, XFAIL=14

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

**Desde P5 la matriz corre sobre la RUTA PRODUCTIVA (detección por registro + motor genérico).** UNION_ME se normaliza con `UNION_FECHAS_V1` (misma configuración que UNION_MN, identidad propia del registro): proxy sintético PASS; lo que depende de movimientos reales sigue SKIP.


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
| `test_04_defectos_conocidos.py::test_formato_union_nuevo_no_hereda_cuenta_ajena` | 1 | PASS |
| `test_04_defectos_conocidos.py::test_union_me_vacio_no_bloquea` | 1 | XFAIL |
| `test_05_preservacion.py::test_union_me_estructura_vacia_se_captura_con_nro_de_verificasion` | 1 | PASS |
| `test_05_preservacion.py::test_union_me_nro_de_verificasion_viaja_a_origen_y_no_a_lists_proxy_sintetico` | 1 | PASS |
| `test_05_preservacion.py::test_union_me_archivo_real_vacio_se_captura_completo` | 1 | SKIP |
| `test_05_preservacion.py::test_union_me_real_completitud_con_movimientos` | 1 | SKIP |
| `test_05_preservacion.py::test_union_me_real_debitos_completos` | 1 | SKIP |
| `test_05_preservacion.py::test_union_me_real_nro_de_verificasion_y_mapa` | 1 | SKIP |
| `test_06_sombra_p3.py::test_sombra_bisa_me_sin_movimientos_deja_df_vacio_como_el_legado` | 1 | PASS |
| `test_06_sombra_p3.py::test_diferencia_union_ultimos12_resuelta_en_p4` | 1 | PASS |
| `test_06_sombra_p3.py::test_sombra_union_me_proxy_sintetico_con_movimiento_coincide` | 1 | PASS |
| `test_06_sombra_p3.py::test_sombra_union_me_vacio_proxy_falla_igual_que_el_legado_d16b` | 1 | PASS |

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

## 2c. Registro de bancos + comparador genérico ↔ legado (P3, `test_06_sombra_p3.py`)

Desde P5 la producción es la del motor genérico; los `normalizar_*` legados corren en sombra como referencia y solo reportan (`SOMBRA_REPORTE.json`, `SOMBRA_DIFERENCIAS.csv`).

| Prueba | Casos | Estado |
|---|---|---|
| `test_registro_es_valido` | 1 | PASS |
| `test_registro_tiene_las_13_cuentas_actuales_y_coinciden_con_el_contrato` | 1 | PASS |
| `test_registro_hojas_y_encabezados_coinciden_con_las_constantes_del_legado` | 1 | PASS |
| `test_registro_formatos_de_la_misma_familia_se_comparten` | 1 | PASS |
| `test_registro_invalido_se_detecta` | 15 | PASS |
| `test_registro_json_roto_falla_con_mensaje` | 1 | PASS |
| `test_motor_generico_no_usa_la_logica_bancaria_del_legado` | 1 | PASS |
| `test_primitivas_compartidas_son_solo_conversion_y_lectura` | 1 | PASS |
| `test_registro_no_se_modifica_al_procesar` | 1 | PASS |
| `test_sombra_formato_coincide_al_100_con_el_legado` | 12 | PASS |
| `test_sombra_generico_reproduce_la_dorada` | 12 | PASS×11/SKIP×1 |
| `test_generico_identidad_banco_cuenta_moneda_siempre_completa` | 12 | PASS |
| `test_sombra_bisa_me_sin_movimientos_deja_df_vacio_como_el_legado` | 1 | PASS |
| `test_generico_es_determinista` | 1 | PASS |
| `test_campo_canonico_cubre_todos_los_encabezados_reales` | 12 | PASS |
| `test_campo_canonico_ejemplos` | 1 | PASS |
| `test_cuenta_nueva_de_formato_conocido_se_agrega_solo_con_configuracion` | 1 | PASS |
| `test_cuenta_nueva_produce_lo_mismo_que_una_cuenta_conocida_con_el_mismo_contenido` | 1 | PASS |
| `test_con_cuenta_rechaza_configuraciones_invalidas` | 1 | PASS |
| `test_cuenta_ambigua_en_cabecera_se_reporta_como_ambiguo` | 1 | PASS |
| `test_diferencia_d10_cuenta_dentro_de_una_glosa_resuelta_en_p4` | 1 | PASS |
| `test_diferencia_d11_bmsc_con_otra_cuenta_resuelta_en_p4` | 1 | PASS |
| `test_diferencia_union_ultimos12_resuelta_en_p4` | 1 | PASS |
| `test_d09_encabezado_incompleto_lo_rechazan_el_generico_y_la_produccion` | 1 | PASS |
| `test_sombra_bnb_orden_descendente_valida_saldos_igual_que_el_legado` | 1 | PASS |
| `test_sombra_bnb_sinteticos_coinciden_con_el_legado` | 3 | PASS |
| `test_sombra_union_me_proxy_sintetico_con_movimiento_coincide` | 1 | PASS |
| `test_sombra_union_me_vacio_proxy_falla_igual_que_el_legado_d16b` | 1 | PASS |
| `test_sombra_no_corrige_d16_bnb_sin_movimientos` | 1 | PASS |
| `test_el_comparador_reporta_diferencias_inyectadas` | 7 | PASS |
| `test_una_fuente_de_saldo_distinta_que_da_el_mismo_resultado_no_es_diferencia` | 1 | PASS |
| `test_el_comparador_reporta_diferencia_de_validacion` | 1 | PASS |
| `test_comparar_frames_detecta_columna_indice_y_familia_de_tipo` | 1 | PASS |
| `test_lote_corre_con_la_referencia_legada_sin_diferencias_y_escribe_el_informe` | 1 | PASS |
| `test_lote_la_produccion_generica_es_identica_a_la_dorada_del_legado` | 1 | PASS |
| `test_referencia_encendida_o_apagada_da_exactamente_la_misma_produccion` | 1 | PASS |
| `test_p5_el_registro_gobierna_la_normalizacion_y_la_referencia_legada_reporta_la_diferencia` | 1 | PASS |
| `test_p5_identidad_del_registro_que_contradice_al_legado_se_reporta_en_la_referencia` | 1 | PASS |
| `test_p4_sin_registro_valido_la_produccion_se_detiene_con_error_claro` | 3 | PASS |
| `test_p5_registro_valido_para_detectar_pero_no_para_normalizar_detiene_la_produccion` | 1 | PASS |
| `test_una_referencia_legada_que_explota_no_detiene_la_produccion` | 1 | PASS |
| `test_un_normalizador_legado_que_falla_solo_se_reporta` | 1 | PASS |
| `test_p5_motor_sin_motor_generico_al_lado_se_detiene_con_error_claro` | 1 | PASS |
| `test_archivos_de_sombra_no_se_toman_como_extractos` | 1 | PASS |
| `test_cli_compara_una_carpeta_sin_escribir_produccion` | 1 | PASS |

## 2d. Capa 4 EXTRACTO_HISTORICO (P3b, `test_07_historico_p3b.py`)

Un Excel por banco/cuenta/mes para Contabilidad/Ingresos, construido solo con ORIGEN.xlsx + NORMALIZADO + registro; el motor no cambia.

| Prueba | Casos | Estado |
|---|---|---|
| `test_once_archivos_uno_por_cuenta_y_mes_con_nombre_esperado` | 1 | PASS |
| `test_movimientos_por_archivo_igual_a_normalizado` | 1 | PASS |
| `test_extracto_que_cruza_dos_meses_genera_dos_archivos` | 1 | PASS |
| `test_una_sola_hoja_visible_llamada_extracto` | 11 | PASS |
| `test_columnas_visibles_son_las_del_banco_en_su_orden_mas_tres_operativas` | 11 | PASS |
| `test_orden_de_columnas_igual_al_orden_original_del_banco` | 11 | PASS |
| `test_registro_declara_el_bloque_historico_de_todos_los_formatos_aceptados` | 1 | PASS |
| `test_registro_sigue_siendo_valido_para_el_motor_generico` | 1 | PASS |
| `test_sin_perdida_cada_columna_bancaria_conserva_el_valor_del_banco` | 11 | PASS |
| `test_codigos_cheques_y_referencias_son_texto_y_conservan_ceros` | 1 | PASS |
| `test_glosas_nombres_y_datos_de_contraparte_se_conservan` | 1 | PASS |
| `test_debitos_conservan_todas_las_columnas_del_banco` | 1 | PASS |
| `test_importes_saldos_fecha_y_hora_son_los_de_normalizado` | 11 | PASS |
| `test_formato_visible_de_fecha_dd_mm_yyyy_y_de_importes` | 11 | PASS |
| `test_hora_bisa_respeta_el_formato_del_banco_hh_mm` | 1 | PASS |
| `test_estado_confirmado_por_y_fecha_de_confirmacion_al_final` | 11 | PASS |
| `test_tabla_estados_opcional_reemplaza_los_valores_operativos` | 1 | PASS |
| `test_orden_cronologico_y_empates_en_el_orden_original_del_archivo` | 11 | PASS |
| `test_empates_del_mismo_segundo_en_bnb_mn_siguen_el_orden_del_archivo` | 1 | PASS |
| `test_zona_superior_muestra_lo_que_trae_cada_banco` | 1 | PASS |
| `test_saldos_declarados_coinciden_con_la_validacion_del_motor` | 1 | PASS |
| `test_un_saldo_declarado_que_no_cuadra_bloquea_el_archivo` | 1 | PASS |
| `test_movimiento_sin_fila_de_origen_bloquea_solo_su_archivo` | 1 | PASS |
| `test_reconstruccion_sin_el_banco_es_identica_celda_a_celda` | 2 | PASS |
| `test_historico_no_depende_del_motor_ni_de_la_captura_ni_de_lectores_de_xls` | 1 | PASS |
| `test_generacion_determinista_y_huella_dorada` | 1 | PASS |
| `test_ningun_id_hash_ni_campo_tecnico_es_visible` | 11 | PASS |
| `test_clave_oculta_permite_sincronizar_con_lists` | 1 | PASS |
| `test_columna_nueva_del_banco_aparece_antes_de_las_operativas_con_advertencia` | 1 | PASS |
| `test_union_me_proxy_sintetico_con_movimiento_muestra_nro_de_verificasion` | 1 | PASS |
| `test_union_me_vacio_no_genera_archivo_ni_bloquea` | 1 | PASS |
| `test_union_me_real_historico_con_movimientos` | 1 | SKIP×1 |
| `test_union_me_real_historico_debitos` | 1 | SKIP×1 |
| `test_generar_historicos_no_modifica_normalizado_lists_ni_origen` | 1 | PASS |
| `test_normalizado_y_lists_siguen_identicos_a_sus_doradas` | 1 | PASS |
| `test_el_motor_no_cambio_y_no_escribe_historicos` | 1 | PASS |
| `test_cli_genera_desde_origen_y_lists_csv` | 1 | PASS |

## 2e. Detección productiva por registro (P4, `test_08_deteccion_p4.py`)

Banco, cuenta, moneda y formato salen de `registro_bancos.json` (`deteccion_registro.py`).

| Prueba | Casos | Estado |
|---|---|---|
| `test_p4_formato_real_se_detecta_exactamente_como_hoy` | 12 | PASS |
| `test_p4_detectar_formato_conserva_su_contrato` | 12 | PASS |
| `test_p4_lote_12_salidas_identicas_y_deteccion_por_registro` | 1 | PASS |
| `test_p4_registro_valido_para_detectar_y_coherente_con_los_normalizadores` | 1 | PASS |
| `test_p4_registro_invalido_se_rechaza_al_cargar` | 12 | PASS |
| `test_p4_cuenta_nueva_sin_registrar_se_rechaza_con_motivo` | 1 | PASS |
| `test_p4_cuenta_nueva_se_incorpora_solo_con_una_entrada_en_cuentas` | 1 | PASS |
| `test_p4_cuenta_nueva_tambien_llega_al_historico_p3b` | 1 | PASS |
| `test_p4_cuenta_nueva_normaliza_igual_que_su_plantilla_salvo_la_identidad` | 1 | PASS |
| `test_p4_cuenta_nueva_en_hoja_alternativa_usa_la_plantilla_de_esa_hoja` | 1 | PASS |
| `test_p4_cuenta_nueva_de_union_junto_al_lote_real` | 1 | PASS |
| `test_p4_cuenta_nueva_no_modifica_el_registro_productivo` | 1 | PASS |
| `test_p4_cuenta_en_glosa_no_altera_la_deteccion` | 1 | PASS |
| `test_p4_cuenta_no_registrada_con_glosa_que_menciona_una_registrada_se_rechaza` | 1 | PASS |
| `test_p4_cuenta_fuera_de_la_cabecera_no_cuenta` | 1 | PASS |
| `test_p4_los_extractos_reales_tienen_otras_cuentas_en_sus_movimientos_y_no_confunden` | 1 | PASS |
| `test_p4_bmsc_con_cuenta_incorrecta_se_rechaza` | 1 | PASS |
| `test_p4_bmsc_con_cuenta_de_otro_banco_se_rechaza_y_lo_dice` | 1 | PASS |
| `test_p4_bmsc_con_su_cuenta_registrada_se_acepta` | 1 | PASS |
| `test_p4_bmsc_sin_cuenta_en_la_cabecera_se_rechaza` | 1 | PASS |
| `test_p4_dos_cuentas_en_la_celda_de_cuenta_es_ambiguo` | 1 | PASS |
| `test_p4_dos_rotulos_de_cuenta_distintos_es_ambiguo` | 1 | PASS |
| `test_p4_una_cuenta_registrada_y_otra_desconocida_en_la_cabecera_es_ambiguo` | 1 | PASS |
| `test_p4_archivo_con_estructura_de_dos_formatos_es_ambiguo` | 1 | PASS |
| `test_p4_cabecera_ambigua_detiene_el_lote_sin_escribir` | 1 | PASS |
| `test_p4_encabezado_incompleto_se_rechaza_y_dice_que_falta` | 1 | PASS |
| `test_p4_encabezado_con_una_sola_columna_faltante_tambien_se_rechaza` | 1 | PASS |
| `test_p4_hoja_sin_encabezado_reconocible_no_se_asigna_a_ningun_formato` | 1 | PASS |
| `test_p4_union_ultimos12_real_se_rechaza_en_la_deteccion` | 1 | PASS |
| `test_p4_union_ultimos12_detiene_el_lote_con_su_mensaje` | 1 | PASS |
| `test_p4_union_ultimos12_con_la_hoja_renombrada_tampoco_pasa_como_union_me` | 1 | PASS |
| `test_p4_union_ultimos12_aunque_traiga_saldo_se_rechaza_por_su_cabecera` | 1 | PASS |
| `test_p4_union_me_proxy_sintetico_sigue_detectandose` | 1 | PASS |
| `test_p4_la_deteccion_no_contiene_logica_de_normalizacion` | 1 | PASS |
| `test_p4_cuenta_conocida_que_contradice_al_registro_no_se_corrige_en_silencio` | 1 | PASS |

## 2f. Normalización productiva por registro (P5, `test_09_normalizacion_p5.py`)

archivo → detección por registro → normalización genérica (`motor_generico.py` + `registro_bancos.json`) → salida productiva. Los `normalizar_*` legados solo como referencia en sombra hasta P6.

| Prueba | Casos | Estado |
|---|---|---|
| `test_p5_ejecutar_motor_no_nombra_la_normalizacion_legada` | 1 | PASS |
| `test_p5_lote_real_completo_sin_ningun_normalizador_legado` | 1 | PASS |
| `test_p5_formato_real_identico_a_la_referencia_legada` | 12 | PASS |
| `test_p5_formato_real_clasificacion_banco_cuenta_moneda` | 12 | PASS |
| `test_p5_lote_real_referencia_legada_sin_diferencias_ni_observaciones` | 1 | PASS |
| `test_p5_la_normalizacion_lee_la_misma_hoja_y_fila_que_la_deteccion` | 1 | PASS |
| `test_p5_registro_de_la_version_de_normalizacion` | 1 | PASS |
| `test_p5_las_12_cuentas_reales_como_cuentas_nuevas_solo_por_configuracion` | 1 | PASS |
| `test_p5_cuenta_nueva_con_extracto_real_del_economico` | 2 | PASS |
| `test_p5_cuenta_nueva_bnb_de_punta_a_punta_sin_legado` | 1 | PASS |
| `test_p5_cuenta_nueva_bnb_en_hoja_alternativa_sin_plantilla_legada` | 1 | PASS |
| `test_p5_cuenta_nueva_bmsc_sin_legado` | 1 | PASS |
| `test_p5_cuenta_nueva_union_junto_al_lote_real_sin_legado` | 1 | PASS |
| `test_p5_cuenta_nueva_la_referencia_legada_coincide` | 1 | PASS |
| `test_p5_cuenta_sin_registrar_sigue_rechazada` | 1 | PASS |
| `test_p5_union_me_proxy_sintetico_se_normaliza_por_registro` | 1 | PASS |
| `test_p5_union_me_real_con_movimientos_se_normaliza_por_registro` | 1 | SKIP×1 |
| `test_p5_union_me_real_validacion_y_debitos` | 1 | SKIP×1 |

## 3. Defectos reales confirmados (fallan hoy; deben pasar tras corregir)

| Código | Estado hoy | Defecto demostrado | Cambio necesario (archivo · función) |
|---|---|---|---|
| D-01 Numero | FALLA (defecto vigente) | '1,234' (coma de miles sin decimales) se lee como 1.234 en vez de 1234 | `motor · numero()` — Tratar 'N,NNN' (grupos de 3 tras la coma, sin punto) como miles; conservar '1234,5' como decimal. |
| D-02 Numero | FALLA (defecto vigente) | negativo entre parentesis '(1,234.56)' devuelve NaN | `motor · numero()` — Aceptar negativo entre parentesis y signo '-' final. |
| D-03 Numero | FALLA (defecto vigente) | miles con varios separadores y sin decimales '1.234.567' / '1,234,567' devuelven NaN | `motor · numero()` — Separador repetido (1.234.567 / 1,234,567) = miles. |
| D-04 Fecha | FALLA (defecto vigente) | ISO '2026-04-03' con dayfirst=True se interpreta como 4 de marzo | `motor · normalizar_fecha()` — Si el texto es ISO (AAAA-MM-DD) parsear sin dayfirst; dayfirst solo para dd/mm/aaaa. |
| D-05 Hora | FALLA (defecto vigente) | fraccion de dia de Excel (0.5) se devuelve como 0.5 en vez de '12:00:00' | `motor · normalizar_hora()` — Convertir float 0<=x<1 (fraccion de dia de Excel) a HH:MM:SS. |
| D-06 Fecha | FALLA (defecto vigente) | el filtro de filas usa pd.to_datetime(dayfirst) y descarta EN SILENCIO fechas '24/Ago/2026' (el Economico si las reconoce con normalizar_fecha): dos criterios distintos | `motor_generico.py · filtro_fecha del registro (P5; antes normalizar_*)` — Usar el mismo parser (normalizar_fecha) para FILTRAR filas y para el valor final, como ya hace normalizar_economico. |
| D-07 Filas | FALLA (defecto vigente) | una fila con importe y fecha NO interpretable se descarta sin error ni conteo (deberia bloquear o informar filas descartadas) | `motor_generico.py · MotorGenerico.normalizar (P5; antes normalizar_*)` — Contar filas descartadas por fecha; si alguna tiene importe/saldo, lanzar ValueError (pies de pagina 'Total ...' siguen permitidos). |
| D-08 Año | FALLA (defecto vigente) | el año 2026 esta fijo: un movimiento de 2027 bloquea toda la exportacion | `motor · ejecutar_motor (paso 6)` — Reemplazar 2026 fijo por año parametrizable (p. ej. derivado de FECHA A PROCESAR) sin bloquear enero 2027. |
| D-09 Encabezado | CORREGIDO EN P5 (PASS) | sin encabezado reconocible la normalizacion productiva lanza ValueError (antes leia desde una fila cualquiera) | `motor_generico.py · MotorGenerico._leer_tabla (P5)` — CORREGIDO EN P5: la normalizacion productiva exige encabezados.puntaje_minimo del registro y lanza ValueError con los encabezados que faltan (la deteccion ya lo exigia desde P4). La primitiva legada encontrar_fila_encabezado queda sin cambios, solo como referencia (P6). |
| D-09 Encabezado | CORREGIDO EN P5 (PASS) | encabezado parcial (3/7) = ValueError con los encabezados que faltan | `motor_generico.py · MotorGenerico._leer_tabla (P5)` — CORREGIDO EN P5: la normalizacion productiva exige encabezados.puntaje_minimo del registro y lanza ValueError con los encabezados que faltan (la deteccion ya lo exigia desde P4). La primitiva legada encontrar_fila_encabezado queda sin cambios, solo como referencia (P6). |
| D-10 Cuenta | CORREGIDO EN P4 (PASS) | un BNB_CLINICA cuya glosa menciona la cuenta BNB_MN ya NO se clasifica como BNB_MN | `deteccion_registro.py (P4)` — CORREGIDO EN P4: la cuenta se lee solo en la celda rotulada de la cabecera (filas previas al encabezado) y debe ser UNA cuenta registrada. |
| D-11 Cuenta | CORREGIDO EN P4 (PASS) | un BMSC con otra cuenta ya NO se acepta con la cuenta fija 1000872489 | `deteccion_registro.py (P4)` — CORREGIDO EN P4: BMSC exige la cuenta 1000872489 registrada en la cabecera; otra cuenta = CUENTA_NO_REGISTRADA. |
| D-12 Cuenta Nueva | CORREGIDO EN P5 (PASS) | una cuenta UNION nueva recibe su cuenta y moneda del registro, nunca las de UNION_ME | `motor_generico.py · MotorGenerico.normalizar (P5)` — CORREGIDO EN P5: BANCO / CUENTA BANCARIA / MONEDA salen de la entrada de CUENTAS del registro; la normalizacion productiva no tiene ramas por cuenta. Los 'else' de los normalizar_* legados quedan solo como referencia (P6). |
| D-16 Vacios | FALLA (defecto vigente) | un extracto BNB con encabezado y SIN movimientos lanza KeyError y bloquea todo el lote (solo BISA maneja 'sin movimientos', y por un efecto colateral de dropna) | `motor_generico.py · MotorGenerico._leer_tabla / normalizar (P5)` — Si el encabezado existe pero no hay filas, devolver DataFrame vacio con COLUMNAS_LISTS y estado SIN MOVIMIENTOS (patron ya usado por BISA). |
| D-16b Vacios | FALLA (defecto vigente) | un UNION_ME por fechas SIN movimientos (formato confirmado por codigo legado + captura real, con 'Nro de verificasion') lanza KeyError y bloquearia todo el lote. Probado con PROXY SINTETICO: confirmar con el archivo real vacio | `motor_generico.py · MotorGenerico._leer_tabla / normalizar (P5)` — Un UNION_ME sin movimientos debe devolver 0 filas y estado SIN MOVIMIENTOS (mismo cambio que D-16); confirmar con el archivo real vacío. |
| D-17 Columnas | FALLA (defecto vigente) | si la columna requerida 'Adicionales' viene completamente vacia el dia del extracto, dropna(axis=1) la elimina y buscar_columna lanza KeyError (bloquea todo el lote) | `motor_generico.py · MotorGenerico._leer_tabla (P5)` — No eliminar columnas vacias ANTES de buscar las requeridas (o tratarlas como presentes y vacias). |
| D-13 Salidas | FALLA (defecto vigente) | si una corrida falla, NORMALIZADO.xlsx y LISTS.csv de la corrida anterior quedan en la carpeta y un proceso posterior podria cargarlos como si fueran nuevos | `motor · ejecutar_motor (inicio y paso 10-11)` — Eliminar/mover salidas previas al iniciar y escribir a temporal + renombrar al terminar. |
| D-14 Consola | FALLA (defecto vigente) | los print con emojis fallan con UnicodeEncodeError si la salida se redirige con codificacion cp1252 (p. ej. Windows con redireccion a archivo/pipe) | `motor · bloque __main__ / ejecutar_motor` — sys.stdout.reconfigure(encoding='utf-8') (o quitar emojis) antes del primer print. |
| D-15 Zona Horaria | FALLA (defecto vigente) | LOTE DE CARGA y FECHA DE CARGA usan la hora local de la maquina: en un servidor UTC se desfasan 4 h respecto de Bolivia | `motor · ejecutar_motor (CONFIGURAR LOTE)` — Usar hora de America/La_Paz en fecha_carga y lote. |
