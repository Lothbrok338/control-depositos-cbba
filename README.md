# CONTROL DE DEPÓSITOS CBBA · módulo de normalización

Estado y decisiones: `ESTADO_PROYECTO.md` · Diseño: `DISENO_TRES_CAPAS.md` · Matriz de campos: `MATRIZ_CAMPOS_ORIGEN.csv`.

## Ejecutar las pruebas
```
pip install -r tests/requirements-test.txt
python -m pytest tests -q          # esperado: 379 passed, 20 skipped, 18 xfailed
python tests/informe.py            # regenera tests/reports/INFORME_PRUEBAS.md
```
Comparación A/B contra un motor de referencia: `python tests/evidencia_ab.py <motor_original.py> motor_control_depositos_cbba.py`.

## Ejecutar el motor
```
python motor_control_depositos_cbba.py <carpeta_entrada> <ruta>/NORMALIZADO.xlsx
```
Genera `NORMALIZADO.xlsx`, `LISTS.csv` (**la salida productiva es solo la del motor legado**) y `ORIGEN.xlsx` (captura íntegra de origen, `captura_origen.py`).

## Motor genérico en modo sombra (P3)
`registro_bancos.json` describe formatos y cuentas; `motor_generico.py` corre en paralelo, compara contra el legado y escribe `SOMBRA_REPORTE.json` y `SOMBRA_DIFERENCIAS.csv` junto a `NORMALIZADO.xlsx`. No produce salida ni altera la producción. Cuenta nueva de un formato conocido = una entrada en `CUENTAS`. Solo comparar una carpeta: `python motor_generico.py <carpeta_entrada> [<carpeta_reporte>]`. Apagar: `CBBA_MOTOR_SOMBRA=0`.

> Los extractos de `tests/fixtures/` (y `ORIGEN_EJEMPLO.xlsx`) son datos bancarios reales: mantener el repositorio **privado**. Si el repositorio es público, esos archivos (y su historial) quedan expuestos.
