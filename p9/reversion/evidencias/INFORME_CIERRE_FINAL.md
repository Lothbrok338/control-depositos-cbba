# Pruebas del cierre P9 reversión

Fecha: 2026-10-04. HEAD antes del cierre: `1feeeb9157c1c677e523ce39c5c1ac5ebeb39871`. Aprobación end-to-end confirmada por el usuario; rechazo no probado. Commit/push autorizados únicamente en candidate/p9-reversion.

| Ejecución | Passed | Failed | Errors | Skipped | Xfailed |
|---|---:|---:|---:|---:|---:|
| reversion | 261 | 0 | 0 | 0 | 0 |
| p9 | 263 | 5 | 0 | 0 | 0 |
| baseline_completa | 1252 | 17 | 0 | 23 | 14 |
| candidate_completa | 1289 | 16 | 0 | 23 | 14 |

La comparación se hizo contra el HEAD remoto real, no contra una base supuesta. Los fallos nuevos son 0.

Los tests P9 incluyen 25/26 de comprobante: 61 aprobadas, cero fallos. No se declara toda la suite verde.

## Fallos de la suite completa reproducidos en baseline

- `test_06_registro_generico::test_el_registro_gobierna_la_normalizacion_productiva`
- `test_06_registro_generico::test_la_identidad_sale_del_registro`
- `test_06_registro_generico::test_p4_sin_registro_valido_la_produccion_se_detiene_con_error_claro[archivo_inexistente-no se pudo leer el registro]`
- `test_06_registro_generico::test_p4_sin_registro_valido_la_produccion_se_detiene_con_error_claro[json_roto-no es JSON v\xe1lido]`
- `test_06_registro_generico::test_p4_sin_registro_valido_la_produccion_se_detiene_con_error_claro[registro_invalido-CUENTAS vac\xedo]`
- `test_06_registro_generico::test_p5_motor_sin_motor_generico_al_lado_se_detiene_con_error_claro`
- `test_06_registro_generico::test_p5_registro_valido_para_detectar_pero_no_para_normalizar_detiene_la_produccion`
- `test_07_historico_p3b::test_cli_genera_desde_origen_y_lists_csv`
- `test_12_flujo_p8::test_conjunto_ampliado_cubre_fixtures_sin_cambios`
- `test_12_flujo_p8::test_paquete_y_fuente_son_reproducibles`
- `test_16_asignacion_p9::test_archivos_p6_p7_p8_p85_sin_cambios_respecto_al_commit_base`
- `test_16_asignacion_p9::test_paquetes_reproducibles_y_con_estructura_importable`
- `test_18_asignar_powerapps_v2::test_generacion_reproducible_y_sin_efectos_sobre_la_base`
- `test_18_asignar_powerapps_v2::test_la_base_es_exactamente_el_zip_validado_en_el_tenant_y_no_se_modifica`
- `test_21_respuesta_v3_p9::test_base_pinned_generacion_reproducible_y_acciones`
- `test_24_flujo_v4_2_firma_8_posicionales_p9::test_bases_pinned_cadena_reproducible_y_zip_v42`

Fallo presente solo en baseline y ya no reproducido después de sincronizar esquema/paquete:
- `test_27_reversion_contrato_p9::test_artefactos_persistidos_json_zip_builder_sincronizados_solo_lectura[provisionar]`

Skips y xfails: inventario exacto en CIERRE_FINAL.json; mismos IDs entre baseline/candidate: True/True.

## Entorno y aislamiento

Python 3.14.3 / Windows 10.0.19045 / zlib 1.3.1.zlib-ng. Copias nuevas con git archive LF, sin generadores históricos en el checkout original. Dependencias PyPI aisladas (pytest 9.1.1, calamine 0.8.2); wheels comprobados contra SHA-256 publicado.

Los primeros intentos tuvieron errores de infraestructura: dependencias inaccesibles y ACL 0700 de temporales de pytest. Esos intentos no validan la suite. Las ejecuciones finales usan basetemp propio y una adaptación de mkdir 0700→0755 únicamente dentro de la copia desechable; no se modificaron tests ni lógica para ocultar fallos. Los resultados definitivos aparecen en la tabla y los casos originales fallidos quedan registrados.

## Artefactos

48 cuerpos HTTP corregidos; cinco JSON igual a builders y properties.definition de ZIP; cuatro copias configuradas cotejadas; 36/36 huellas protegidas idénticas. Main_Screen copiado byte por byte del último archivo entregado. Tests 31 protegen transporte/tipos; tests 32 fuente, modal, V4.2, seis argumentos, columnas y referencias.

## Evidencia tenant y continuidad

Aprobación validada por el usuario el 2026-10-04: creación, Approval, aprobación humana, DISPONIBLE, siete campos limpios, código/clave intactos, marcador comprobado, historial/trazabilidad y sin duplicados observados. UID/IDs exactos no aportados. Rechazo no probado; expiración/recuperación reales sin evidencia. La confirmación humana no se sustituye por fixtures ni resultados simulados. El usuario autorizó commit/push de candidate/p9-reversion, sin merge a main.
