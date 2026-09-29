# CONTROL DE DEPÓSITOS CBBA · módulo de normalización

Estado y decisiones: `ESTADO_PROYECTO.md` · Diseño: `DISENO_TRES_CAPAS.md` · Matriz de campos: `MATRIZ_CAMPOS_ORIGEN.csv`.

## Ejecutar las pruebas
```
pip install -r tests/requirements-test.txt
python -m pytest tests -q          # esperado: 270 passed, 19 skipped, 18 xfailed
python tests/informe.py            # regenera tests/reports/INFORME_PRUEBAS.md
```
Comparación A/B contra un motor de referencia: `python tests/evidencia_ab.py <motor_original.py> motor_control_depositos_cbba.py`.

## Ejecutar el motor
```
python motor_control_depositos_cbba.py <carpeta_entrada> <ruta>/NORMALIZADO.xlsx
```
Genera `NORMALIZADO.xlsx`, `LISTS.csv` y `ORIGEN.xlsx` (captura íntegra de origen, `captura_origen.py`).

> Los extractos de `tests/fixtures/` son datos bancarios reales: mantener el repositorio **privado**.
