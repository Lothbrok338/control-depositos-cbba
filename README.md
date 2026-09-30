# CONTROL DE DEPÓSITOS CBBA · módulo de normalización

Estado y decisiones: `ESTADO_PROYECTO.md` · Diseño: `DISENO_TRES_CAPAS.md` · Matriz de campos: `MATRIZ_CAMPOS_ORIGEN.csv`.

## Ejecutar las pruebas
```
pip install -r tests/requirements-test.txt
python -m pytest tests -q          # esperado: 575 passed, 23 skipped, 14 xfailed
python tests/informe.py            # regenera tests/reports/INFORME_PRUEBAS.md
```
Comparación contra el checkpoint P5 (evidencia P6): `git worktree add <carpeta> checkpoint-p5` y `cd tests && python evidencia_p6_retiro.py <carpeta>`.

## Ejecutar el motor
```
python motor_control_depositos_cbba.py <carpeta_entrada> <ruta>/NORMALIZADO.xlsx
```
Genera `NORMALIZADO.xlsx`, `LISTS.csv` (**desde P5 normalizados por `motor_generico.py` + `registro_bancos.json`**) y `ORIGEN.xlsx` (captura íntegra de origen, `captura_origen.py`). **Junto al motor deben estar `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json` y `captura_origen.py`.**

## Detección por registro (P4)
Banco, cuenta, moneda y formato se identifican con `registro_bancos.json` a través de `deteccion_registro.py`: **ambos deben estar junto a `motor_control_depositos_cbba.py`** (o `CBBA_REGISTRO_BANCOS=<ruta>` para otro registro). La cuenta se lee solo en la celda rotulada de la cabecera y debe estar registrada; encabezado incompleto, cabecera ambigua, cuenta no registrada o el reporte Unión «Últimos 12» detienen el proceso con el motivo. **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`** (id único, formato, banco, cuenta tal como figura en la cabecera, moneda).

## Normalización por registro (P5)
`archivo → detección por registro → normalización genérica → salida productiva`. `motor_generico.py` normaliza a las 26 `COLUMNAS_LISTS` y valida saldos solo con `registro_bancos.json`; `CLAVE TRANSACCIÓN` sigue saliendo de `crear_clave` (congelada). **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`**: se normaliza sin código, sin `normalizar_*` propio y sin plantilla legada. Sin `motor_generico.py` o con un registro que no sirve para normalizar, el proceso se detiene antes de escribir.

## Retiro del legado (P6)
Los `normalizar_*` por banco, `normalizar_archivo`, `validar_archivo`, `HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `encontrar_fila_encabezado`, `leer_tabla_movimientos`, `texto_de_archivo`, `aplicar_identidad_registro`, la referencia en sombra (paso 16, `SOMBRA_REPORTE.json` / `SOMBRA_DIFERENCIAS.csv`, `CBBA_MOTOR_SOMBRA`, clave `sombra_estado` del retorno), la detección propia de P3 y el modo script de `motor_generico.py` se retiraron. Hojas, encabezados, campos y saldos viven solo en `registro_bancos.json`. Las primitivas compartidas (números, fechas, horas, códigos, texto, lector de Excel, `buscar_columna*`, `extraer_nombre_bnb`, `ecuacion_saldo`, `crear_clave` / `finalizar_dataframe`, `COLUMNAS_LISTS`) siguen en `motor_control_depositos_cbba.py`, sin cambios. Archivos productivos: `motor_control_depositos_cbba.py`, `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json`, `captura_origen.py` (+ `historico.py` para la capa 4). Si una carpeta de salida conserva `SOMBRA_*` de corridas P3-P5, ya no se actualizan: se pueden borrar.

## Extracto histórico para Contabilidad / Ingresos (P3b, capa 4)
```
python historico.py <salida>/ORIGEN.xlsx <salida>/NORMALIZADO.xlsx <carpeta_historicos>   # o LISTS.csv
```
Un `EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{AAAA-MM}.xlsx` por cuenta y mes, hoja única `EXTRACTO`, columnas propias de cada banco + `ESTADO`, `CONFIRMADO POR`, `FECHA DE CONFIRMACIÓN`. Se arma solo con ORIGEN + NORMALIZADO + `registro_bancos.json` (no relee el banco) y no modifica ninguna salida del motor.

> Los extractos de `tests/fixtures/` (y `ORIGEN_EJEMPLO.xlsx`) son datos bancarios reales: mantener el repositorio **privado**. Si el repositorio es público, esos archivos (y su historial) quedan expuestos.
