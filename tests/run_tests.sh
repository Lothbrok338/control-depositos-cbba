#!/usr/bin/env bash
# Uso: ./run_tests.sh   (desde la carpeta tests/). MOTOR_PATH opcional apunta al motor a probar.
set -e
cd "$(dirname "$0")"
pip install -q -r requirements-test.txt 2>/dev/null || true
python -m pytest -q -rxX "$@" || true
python informe.py > /dev/null
echo "Informe: tests/reports/INFORME_PRUEBAS.md"
