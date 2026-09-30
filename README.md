# CONTROL DE DEPÓSITOS CBBA · módulo de normalización

Estado y decisiones: `ESTADO_PROYECTO.md` · Diseño: `DISENO_TRES_CAPAS.md` · Matriz de campos: `MATRIZ_CAMPOS_ORIGEN.csv`.

## Ejecutar las pruebas
```
pip install -r tests/requirements-test.txt
python -m pytest tests -q          # esperado: 620 passed, 24 skipped, 14 xfailed
python tests/informe.py            # regenera tests/reports/INFORME_PRUEBAS.md
```
Comparación A/B contra un motor de referencia: `python tests/evidencia_ab.py <motor_original.py> motor_control_depositos_cbba.py`.

## Ejecutar el motor
```
python motor_control_depositos_cbba.py <carpeta_entrada> <ruta>/NORMALIZADO.xlsx
```
Genera `NORMALIZADO.xlsx`, `LISTS.csv` (**desde P5 normalizados por `motor_generico.py` + `registro_bancos.json`**) y `ORIGEN.xlsx` (captura íntegra de origen, `captura_origen.py`). **Junto al motor deben estar `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json` y `captura_origen.py`.**

## Detección por registro (P4)
Banco, cuenta, moneda y formato se identifican con `registro_bancos.json` a través de `deteccion_registro.py`: **ambos deben estar junto a `motor_control_depositos_cbba.py`** (o `CBBA_REGISTRO_BANCOS=<ruta>` para otro registro). La cuenta se lee solo en la celda rotulada de la cabecera y debe estar registrada; encabezado incompleto, cabecera ambigua, cuenta no registrada o el reporte Unión «Últimos 12» detienen el proceso con el motivo. **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`** (id único, formato, banco, cuenta tal como figura en la cabecera, moneda).

## Normalización por registro (P5)
`archivo → detección por registro → normalización genérica → salida productiva`. `motor_generico.py` normaliza a las 26 `COLUMNAS_LISTS` y valida saldos solo con `registro_bancos.json`; `CLAVE TRANSACCIÓN` sigue saliendo de `crear_clave` (congelada). **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`**: se normaliza sin código, sin `normalizar_*` propio y sin plantilla legada. Sin `motor_generico.py` o con un registro que no sirve para normalizar, el proceso se detiene antes de escribir.

## Referencia legada en sombra (P5; antes «motor genérico en sombra», P3)
Los `normalizar_*` / `validar_archivo` legados ya no producen salida: después de escribirla, el paso 16 los corre como referencia y escribe `SOMBRA_REPORTE.json` (modo `REFERENCIA_LEGADO`) y `SOMBRA_DIFERENCIAS.csv` junto a `NORMALIZADO.xlsx`. Nunca altera ni detiene la producción. Apagar: `CBBA_MOTOR_SOMBRA=0`. Se retira en P6. Comparar solo una carpeta (genérico con su propia detección vs. legado): `python motor_generico.py <carpeta_entrada> [<carpeta_reporte>]`.

## Extracto histórico para Contabilidad / Ingresos (P3b, capa 4)
```
python historico.py <salida>/ORIGEN.xlsx <salida>/NORMALIZADO.xlsx <carpeta_historicos>   # o LISTS.csv
```
Un `EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{AAAA-MM}.xlsx` por cuenta y mes, hoja única `EXTRACTO`, columnas propias de cada banco + `ESTADO`, `CONFIRMADO POR`, `FECHA DE CONFIRMACIÓN`. Se arma solo con ORIGEN + NORMALIZADO + `registro_bancos.json` (no relee el banco) y no modifica ninguna salida del motor.

> Los extractos de `tests/fixtures/` (y `ORIGEN_EJEMPLO.xlsx`) son datos bancarios reales: mantener el repositorio **privado**. Si el repositorio es público, esos archivos (y su historial) quedan expuestos.
