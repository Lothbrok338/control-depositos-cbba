# Pruebas del normalizador (CONTROL DE DEPÓSITOS CBBA)

Ejecutar (desde esta carpeta): `./run_tests.sh`  ·  otro motor: `MOTOR_PATH=/ruta/motor.py ./run_tests.sh`
Genera `reports/INFORME_PRUEBAS.md`. No modifica el motor.

| Archivo | Qué protege |
|---|---|
| `test_01_contrato.py` | 26 columnas de `COLUMNAS_LISTS` y fórmula de `CLAVE TRANSACCIÓN` congeladas; casos válidos de número/fecha/hora |
| `test_02_regresion_formatos.py` | Por cada uno de los 13 formatos: detección, hoja/encabezado, banco/cuenta/moneda, igualdad con dorada, conteo con oráculo independiente, cadena de saldos fila a fila, validación, integridad, clave |
| `test_03_lote.py` | `ejecutar_motor` con los 12 extractos válidos: LISTS.csv = dorada, xlsx (4 hojas, `tblLISTS`, formatos), bloqueos |
| `test_04_defectos_conocidos.py` | 18 defectos reales (D-01…D-17, más D-16b), `xfail` estricto: hoy fallan; al corregirlos pasan a XPASS y hay que quitar la marca |

Referencias doradas (`golden/`): generadas con el motor ACTUAL (`python generar_golden.py --force`).
Son caracterización, no una verdad externa: contrastarlas con un NORMALIZADO.xlsx/LISTS.csv aprobado.
`fixtures/extractos/` contiene extractos reales con datos personales: no publicar ni subir a repositorios abiertos.
Regla de uso: tras cada cambio al motor, la sección 1 (regresión) debe seguir en PASS; la sección de defectos irá pasando a XPASS.


## P1 + P2 (captura de origen)

* `../captura_origen.py` (nuevo) genera `ORIGEN.xlsx` (DATOS_ORIGINALES, METADATOS_EXTRACTO, METADATOS_EXTRA, MAPA_ORIGEN). Se invoca desde el final de `ejecutar_motor`; si falla, NORMALIZADO.xlsx y LISTS.csv salen igual.
* `test_05_preservacion.py`: completitud celda a celda, reconstruccion, mapa 1:1, debitos, cabeceras/pies, metadatos, determinismo, columnas vacias, doradas de NORMALIZADO.xlsx/LISTS.csv y UNION_ME.
* `generar_golden_normalizado.py`: doradas de las 4 hojas de NORMALIZADO.xlsx (generadas con el motor ORIGINAL).
* `evidencia_ab.py <motor_original> <motor_con_P1>`: comparacion A/B de salidas operativas (reloj fijado). Resultado en `reports/EVIDENCIA_MOTOR_SIN_CAMBIOS.txt`.


## P3 (registro + motor genérico en sombra)

* `../registro_bancos.json` y `../motor_generico.py` (nuevos). El motor legado solo añade el paso 16 (pasivo) al final de `ejecutar_motor`.
* `test_06_sombra_p3.py` (109 casos): registro válido y contrato de 13 cuentas; validación de registros inválidos; el genérico no usa la lógica bancaria del legado; los 12 formatos coinciden al 100 % en sombra (detección, movimientos, validación) y reproducen las doradas; `CAMPO_CANONICO` cubre todos los encabezados reales; cuenta nueva por configuración; diferencias D-09/D-10/D-11/«Últimos 12» reportadas; el comparador detecta diferencias inyectadas; con la sombra encendida, apagada, con registro alterado o roto, o con el genérico roto, `NORMALIZADO.xlsx`/`LISTS.csv` son idénticos.
* `evidencia_ab.py <motor_referencia> <motor_actual>` ahora acepta las claves nuevas `origen_estado` y `sombra_estado` e ignora las líneas de ORIGEN/SOMBRA. Evidencia de P3: `reports/EVIDENCIA_P3_SOMBRA.txt` (referencia = motor del checkpoint `8c9c09a`).

