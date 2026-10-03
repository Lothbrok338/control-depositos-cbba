# Codificación de las pruebas históricas en Windows

Diagnóstico de lectura y reproducción mínima, sin modificar el motor ni volver a ejecutar la suite.

## Test 07: captura CLI

`tests/test_07_historico_p3b.py`, líneas 642–646, usa `subprocess.run(capture_output=True, text=True, encoding="utf-8")`. El proceso hijo imprime `·` y no configura stdout. En este entorno `utf8_mode=0`, locale/stdout CP1252 y no están definidas PYTHONUTF8/PYTHONIOENCODING.

Una reproducción mínima sin archivos que imprime `chr(183)` en un hijo y usa esa captura produce returncode 0, stdout None y UnicodeDecodeError del byte 0xb7. En Windows el hilo lector de subprocess agrega el resultado de `fh.read()` a un buffer; si falla al decodificar, el buffer queda vacío y communicate devuelve None. El filtro de UserWarning de tests/pytest.ini oculta el PytestUnhandledThreadExceptionWarning.

La excepción original del hilo no quedó en el log, pero el código y la reproducción sostienen este diagnóstico. No es evidencia de fallo funcional del CLI: el proceso terminó con código 0.

## Test 12: JSON ampliado

`tests/test_12_flujo_p8.py`, líneas 221–222, lee JSON con Path.read_text() sin encoding; la CSV dorada se lee con utf-8-sig. En el mismo archivo, la lectura predeterminada CP1252 produce mojibake en BANCO/TIPO_MOVIMIENTO/CLAVE. Leyendo UTF-8 coincide con la CSV. El dato del artefacto no está corrupto: la interpretación del texto en la prueba es distinta.

## Vista final del instrumental

Tras terminar pytest y guardar JSON/XML/log, la impresión final del wrapper encontró U+FFFD no representable en cp1252. Se modificó solo work/validar_iteracion.py para escapar caracteres de esa vista de consola y comprobar las huellas antes de imprimir. No cambia los resultados persistidos ni requirió repetir la suite.
