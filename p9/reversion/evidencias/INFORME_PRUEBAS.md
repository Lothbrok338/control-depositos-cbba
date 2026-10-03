# Informe de pruebas — fase B de reversión P9

Base: `d08454f7636a49a5711006cd900d79b32bf9c13b`. Rama: `candidate/p9-reversion`. Resultados obtenidos en Windows el 2026-10-03. Las pruebas nuevas pasan. La suite completa conserva 16 fallos que también aparecen, con los mismos identificadores, en la base limpia; no se declara una suite completamente verde.

## Resultados

| Grupo | Passed | Failed | Errors | Skipped | Xfailed |
|---|---:|---:|---:|---:|---:|
| 27–30, versión final en suite completa | 225 | 0 | 0 | 0 | 0 |
| P9 existente, base limpia LF | 262 | 5 | 0 | 0 | 0 |
| P9 existente, candidate aislado | 263 | 5 | 0 | 0 | 0 |
| Suite completa base limpia | 1027 | 16 | 0 | 23 | 14 |
| Suite completa candidate | 1253 | 16 | 0 | 23 | 14 |

| Grupo | Passed | Failed | Errors | Skipped | Xfailed |
|---|---:|---:|---:|---:|---:|
| test_27_reversion_contrato_p9 | 111 | 0 | 0 | 0 | 0 |
| test_28_reversion_concurrencia_p9 | 47 | 0 | 0 | 0 | 0 |
| test_29_reversion_frontend_p9 | 19 | 0 | 0 | 0 | 0 |
| test_30_reversion_expiracion_recuperacion_p9 | 48 | 0 | 0 | 0 | 0 |

Los 225 casos nuevos finales se ejecutaron dentro de la suite completa. `candidate-nuevos-03` registra una ejecución anterior de 202 casos, antes de añadir los últimos 23 casos de constructor/paquetes al test 27; no es el total final. La base completa tiene 1.080 casos y candidate 1.306: 225 nuevos más una regresión contable adicional. No hay casos nuevos omitidos, xfailed ni errores de colección.

## P9, V4.2 y comprobante

| Grupo | Passed | Failed | Errors | Skipped | Xfailed |
|---|---:|---:|---:|---:|---:|
| test_16_asignacion_p9 | 108 | 1 | 0 | 0 | 0 |
| test_18_asignar_powerapps_v2 | 24 | 2 | 0 | 0 | 0 |
| test_21_respuesta_v3_p9 | 17 | 1 | 0 | 0 | 0 |
| test_22_frontend_final_p9 | 20 | 0 | 0 | 0 | 0 |
| test_24_flujo_v4_2_firma_8_posicionales_p9 | 33 | 1 | 0 | 0 | 0 |
| test_25_comprobante_impresion_p9 | 15 | 0 | 0 | 0 | 0 |
| test_26_comprobante_cuenta_tc_p9 | 46 | 0 | 0 | 0 | 0 |

Tests 25 y 26: 61 pasan, incluido el mapeo explícito de 20 variantes hacia 14 cuentas. V4.2: 33 pasan y 1 falla porque test 21 regeneró un ZIP histórico y cambió su hash. En la ejecución P9 aislada hay 263 passed y 5 failed; sumando los nuevos verificados son 488 passed y 5 failed en esos dos alcances. Dentro de la suite completa, P9 existente tiene 262 passed y 6 failed: se agrega la comprobación de archivos P8 mutados por sus propios generadores anteriores. Ese sexto fallo también existe en la base completa.

## Fallos comparados

Los siguientes 16 identificadores fallan en ambas suites completas. `RESULTADOS_PRUEBAS.json` conserva además cada caso y los motivos de los 23 skips y 14 xfails; sus conjuntos también coinciden.

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

Clasificación:

- Siete fallos de test 06: nombre de directorio `con`, reservado por Windows (WinError 267/3).
- Uno de test 07: el hijo escribe CP1252 y la prueba captura UTF-8; el carácter `·` hace fallar el hilo lector y stdout queda None aunque el proceso devuelve 0. Ver `DIAGNOSTICO_CODIFICACION_WINDOWS.md`.
- Uno de test 12: reproducción binaria/textual de paquetes antiguos en Windows.
- Uno de test 12: lee el JSON UTF-8 del fixture ampliado como CP1252; produce mojibake y cambia la clave comparada. La lectura UTF-8 coincide con la CSV dorada.
- Uno de test 16: prueba de preservación P6/P7/P8/P8.5 detecta archivos P8 regenerados por tests anteriores dentro de la copia desechable.
- Cinco de P9: reproducibilidad binaria y efectos en cadena de test 16/21, documentados en `AUDITORIA_BASELINE_P9_WINDOWS.md`.

No se modificaron los generadores históricos para ocultar estos fallos. Los 15 miembros de los tres ZIP históricos regenerados resultaron idénticos descomprimidos; cambiaron metadatos `create_system` y tamaños DEFLATE. Los ZIP del checkout principal siguen idénticos a HEAD.

## Método y entorno

- Una carpeta nueva por ejecución, creada desde `git -c core.autocrlf=false archive HEAD`; candidate superpone únicamente archivos nuevos/modificados. No hay reset, checkout de archivos ni limpieza del trabajo principal.
- La copia del frontend extendido se normaliza a LF solo dentro de esa copia para compararla con el frontend base Git LF. La rama principal conserva sus bytes.
- Los comandos, rutas, duración, entorno y overlay están en los JSON de cada ejecución. Las salidas de pytest y JUnit se conservan íntegramente.
- El primer intento de baseline completo detectó dependencias de pruebas faltantes (`xlrd`, `python-calamine`). Tras instalarlas en `work/testdeps`, la ejecución válida de comparación es `baseline-completa-02`; no se mezclan las cifras de ese intento preliminar.
- Python 3.14.3; pytest 9.1.1; pandas 3.0.1; openpyxl 3.1.5; xlrd 2.0.2; python-calamine 0.8.2; PyYAML 6.0.3; Windows 10.0.19045; zlib 1.3.1.zlib-ng.
- El wrapper completó pytest y guardó JSON/XML/log. Su impresión final encontró U+FFFD no representable en cp1252. Se corrigió solo la vista de consola; resultados persistidos íntegros, sin repetir tests.
- `validar_iteracion.py.txt` y `audit_baseline_regression.py.txt` conservan el código del instrumental local. Para reproducirlo en este workspace, sus originales están en `work/`; no son módulos del producto.

## Alcance de las comprobaciones

El ensayo ejecuta las definiciones WDL generadas con simulación de SharePoint, Approval, tiempo y fallos. Cubre CAS/ETag, UID y bloqueo únicos, dos trabajadores concurrentes, prioridad de versión, MERGE de nueve campos, marcador propio tras reconfirmación, 412 durante recuperación, rechazo, vencimiento y respuesta tardía, cancelación/terminación acreditada, aprobación incierta, fallos HTTP y cierre de historial incierto. El frontend se verifica estáticamente.

`VALIDACION_ESTATICA.json` acredita referencias y dependencias WDL, límites, payload, ETag, retry, conexiones e igualdad builder/JSON/ZIP. Los tests rechazan mutaciones inseguras. Ninguna de estas verificaciones sustituye importación en Power Automate, Power Apps Studio, permisos o conectores reales.

Los 36 archivos protegidos conservan su SHA-256 de partida; los tres ZIP históricos se compararon también con los blobs HEAD. Ver `huellas_base.json` y `huellas_finales.json`.
