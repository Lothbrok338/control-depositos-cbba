# CONTROL DE DEPÓSITOS CBBA · módulo de normalización

Estado y decisiones: `ESTADO_PROYECTO.md` · Diseño: `DISENO_TRES_CAPAS.md` · Matriz de campos: `MATRIZ_CAMPOS_ORIGEN.csv`.

## Ejecutar las pruebas
```
pip install -r tests/requirements-test.txt
python -m pytest tests -q          # esperado: 577 passed, 22 skipped, 16 xfailed
python tests/informe.py            # regenera tests/reports/INFORME_PRUEBAS.md
```
Comparación A/B contra un motor de referencia: `python tests/evidencia_ab.py <motor_original.py> motor_control_depositos_cbba.py`.

## Ejecutar el motor
```
python motor_control_depositos_cbba.py <carpeta_entrada> <ruta>/NORMALIZADO.xlsx
```
Genera `NORMALIZADO.xlsx`, `LISTS.csv` (**la salida productiva es solo la del motor legado**) y `ORIGEN.xlsx` (captura íntegra de origen, `captura_origen.py`).

## Detección por registro (P4)
Banco, cuenta, moneda y formato se identifican con `registro_bancos.json` a través de `deteccion_registro.py`: **ambos deben estar junto a `motor_control_depositos_cbba.py`** (o `CBBA_REGISTRO_BANCOS=<ruta>` para otro registro). La cuenta se lee solo en la celda rotulada de la cabecera y debe estar registrada; encabezado incompleto, cabecera ambigua, cuenta no registrada o el reporte Unión «Últimos 12» detienen el proceso con el motivo. **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`** (id único, formato, banco, cuenta tal como figura en la cabecera, moneda). La normalización sigue en el motor legado (P5 pendiente).

## Motor genérico en modo sombra (P3)
`registro_bancos.json` describe formatos y cuentas; `motor_generico.py` corre en paralelo, compara contra el legado y escribe `SOMBRA_REPORTE.json` y `SOMBRA_DIFERENCIAS.csv` junto a `NORMALIZADO.xlsx`. No produce salida ni altera la producción. Cuenta nueva de un formato conocido = una entrada en `CUENTAS`. Solo comparar una carpeta: `python motor_generico.py <carpeta_entrada> [<carpeta_reporte>]`. Apagar: `CBBA_MOTOR_SOMBRA=0`.

## Extracto histórico para Contabilidad / Ingresos (P3b, capa 4)
```
python historico.py <salida>/ORIGEN.xlsx <salida>/NORMALIZADO.xlsx <carpeta_historicos>   # o LISTS.csv
```
Un `EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{AAAA-MM}.xlsx` por cuenta y mes, hoja única `EXTRACTO`, columnas propias de cada banco + `ESTADO`, `CONFIRMADO POR`, `FECHA DE CONFIRMACIÓN`. Se arma solo con ORIGEN + NORMALIZADO + `registro_bancos.json` (no relee el banco) y no modifica ninguna salida del motor.

> Los extractos de `tests/fixtures/` (y `ORIGEN_EJEMPLO.xlsx`) son datos bancarios reales: mantener el repositorio **privado**. Si el repositorio es público, esos archivos (y su historial) quedan expuestos.
