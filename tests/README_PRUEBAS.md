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



## P3b (capa 4, EXTRACTO_HISTORICO)

* `../historico.py` (nuevo) y bloque `historico` de `../registro_bancos.json`. El motor NO cambia.
* `test_07_historico_p3b.py` (126 PASS + 2 SKIP): 11 archivos por cuenta/mes con nombre esperado (BISA_ME sin archivo; extracto que cruza meses = 2 archivos); hoja única `EXTRACTO`; columnas del banco por formato y en el orden original + 3 operativas; conservación celda a celda de referencias, cheques, códigos, glosas y débitos (620 BNB_MN, 445 BCP_MN, 3 ECO); importes/fecha/hora = NORMALIZADO; formato `dd/mm/yyyy`; ESTADO/CONFIRMADO POR/FECHA DE CONFIRMACIÓN y tabla opcional de estados; orden cronológico con empates en orden del archivo; zona superior y saldos declarados = VALIDACION; bloqueo si un saldo declarado no cuadra o falta la fila de origen; reconstrucción idéntica **sin poder abrir ningún extracto** desde NORMALIZADO.xlsx y desde LISTS.csv; sin IDs/hashes visibles (CLAVE oculta); columna nueva del banco con advertencia; UNION_ME estructural con proxy sintético (`Nro de verificasion` como texto) y vacío sin archivo; NORMALIZADO.xlsx/LISTS.csv/ORIGEN.xlsx sin cambios; CLI.
* SKIP (2): UNION_ME real con movimientos y con débitos — `REQUIERE MUESTRA REAL CON MOVIMIENTOS`.
* `generar_golden_historico.py --force`: huella dorada `golden/historico/MANIFEST_HISTORICO.json` (sin copiar movimientos).


## P4 (detección productiva por registro)

* `../deteccion_registro.py` (nuevo) y bloques `deteccion` / `legado` de `../registro_bancos.json`. En el motor cambian solo `detectar_formato` (delega en el registro) y `ejecutar_motor` (usa la detección completa: identidad del registro, id del normalizador legado y motivo de rechazo).
* `test_08_deteccion_p4.py`: los 12 formatos reales detectados exactamente como antes (mismo id, hoja y fila de encabezado que su normalizador); lote de 12 idéntico a las doradas; registro válido y coherente con `HOJAS_VALIDAS`/`ENCABEZADOS_ESPERADOS` y 12 mutaciones inválidas rechazadas; cuenta nueva solo por configuración (BNB en «Hoja 1» y «Hoja», Unión junto a extractos reales, histórico P3b); cuenta en glosa que no altera la detección; cuenta fuera de la cabecera ignorada; BMSC con cuenta incorrecta / de otro banco / sin cuenta rechazado; cabecera ambigua (dos cuentas, dos rótulos, dos formatos) rechazada; encabezado incompleto rechazado con las columnas que faltan; Unión «Últimos 12» (real, con hoja renombrada y con Saldo agregado) rechazado; UNION_ME sintético sigue detectándose.
* `test_04`: D-10 y D-11 **corregidos** (ya no son xfail). D-09 y D-12 siguen XFAIL (primitivas de normalización, P5) aunque la ruta productiva ya no los alcanza.
* `test_06`: las diferencias de detección que la sombra reportaba en P3 (D-09, D-10, D-11, «Últimos 12», cuenta ambigua) ahora **coinciden**; un registro roto detiene la producción con error claro; un registro que contradice al normalizador legado detiene la producción.
* `evidencia_ab.py` acepta la clave nueva `deteccion_estado`. Evidencia de P4: `reports/EVIDENCIA_P4_DETECCION.txt` (referencia = `main` 9a3eae8).


## P5 (normalización productiva por registro)

* En el motor cambia solo `ejecutar_motor` (pasos 1, 2, 7, 15 y 16) y se agregan `modulo_generico`, `normalizador_registro`, `normalizar_extracto`, `validar_extracto` y `contrato_origen_registro`. `motor_generico.py`: exige `puntaje_minimo` al leer la tabla (D-09) y reemplaza `ejecutar_sombra_produccion` por `ejecutar_referencia_legado` (el legado pasa a ser la sombra). Los `normalizar_*`, `validar_archivo`, `encontrar_fila_encabezado`, `crear_clave`, `finalizar_dataframe` y `COLUMNAS_LISTS` no cambian.
* `conftest.py`: la fixture `normalizado` corre la **ruta productiva** (detección + motor genérico), así que `test_02` (regresión contra doradas, oráculo, cadena de saldos, integridad) prueba lo que produce la salida. `normalizado_legado` conserva la referencia para las comparaciones de `test_06`.
* `test_09_normalizacion_p5.py`: `ejecutar_motor` no nombra la normalización legada; lote real completo con **todo** el legado inutilizado = salida aprobada (LISTS.csv + 4 hojas); los 12 formatos idénticos a la referencia legada (26 columnas, índice, tipos, valores, validación sin tolerancia) y con la identidad del registro; referencia legada 12/12 sin diferencias ni observaciones; misma hoja/fila que la detección; cuentas nuevas solo por configuración (las 13 renombradas sobre el lote real, Económico real con otro número, BNB en «Hoja 1» y «Hoja», BMSC, Unión junto al lote real) sin ningún `normalizar_*`; UNION_ME por `UNION_FECHAS_V1` (proxy sintético) y 2 SKIP `REQUIERE MUESTRA REAL CON MOVIMIENTOS`.
* `test_04`: D-09 y D-12 **corregidos** (PASS sobre la ruta productiva; +1 prueba de encabezado parcial). D-06, D-07, D-16, D-16b y D-17 se prueban ahora sobre la ruta productiva (siguen XFAIL: el genérico los reproduce a propósito).
* `test_06` §9: la producción es la del genérico y la referencia legada en sombra la compara (encendida o apagada = misma producción; un dato del registro cambia la producción y la referencia lo reporta; identidad del registro que contradice al legado = diferencia reportada, ya no detiene; registro inválido para normalizar o `motor_generico.py` ausente = proceso detenido; una referencia rota o un `normalizar_*` roto no alteran la producción).
* `evidencia_p5_extra.py <carpeta_referencia> [<commit>]`: ORIGEN, históricos, tabla por archivo, referencia legada, producción sin legado y cuentas nuevas por configuración (LISTS.csv byte a byte), componentes congelados. Evidencia de P5: `reports/EVIDENCIA_P5_NORMALIZACION.txt` (referencia = checkpoint P4 `998158e`).
