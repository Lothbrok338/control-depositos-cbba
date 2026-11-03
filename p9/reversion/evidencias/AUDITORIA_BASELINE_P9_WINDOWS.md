# Auditoría del baseline P9 en Windows

Base comprobada: `d08454f7636a49a5711006cd900d79b32bf9c13b`.

Las dos pruebas usan una copia desechable creada con `git archive HEAD`; no ejecutan generadores antiguos en el checkout de trabajo. Los tests y constructores del baseline se ejecutan sin modificaciones. Se ejecutaron los siete archivos P9 existentes: 16, 18, 21, 22, 24, 25 y 26.

| Copia | Extracción | Resultado | Duración de pytest |
|---|---|---|---|
| `baseline-regression` | `git archive HEAD`, hereda `core.autocrlf=true` del Git del sistema | 256 pasan, 11 fallan | 4,02 s |
| `baseline-regression-lf` | `git -c core.autocrlf=false archive HEAD`, contenido LF | 262 pasan, 5 fallan | 4,24 s |

Git archive en este entorno convierte texto a CRLF si hereda autocrlf=true. Se verificó directamente: el comprobante tiene 780 secuencias CRLF dentro del primer archivo ZIP y ninguna en el blob Git. El segundo archive conserva LF. La configuración del repositorio y la del sistema no se cambiaron; `-c` se aplicó únicamente a ese comando.

## Fallos que permanecen usando LF

1. `test_16::test_paquetes_reproducibles_y_con_estructura_importable`: los constructores regeneran dos ZIP y JSON. Los JSON de texto escritos por Python cambian de LF a CRLF en Windows; los ZIP cambian metadatos y flujo DEFLATE.
2. `test_18::test_la_base_es_exactamente_el_zip_validado_en_el_tenant_y_no_se_modifica`: detecta el ZIP base regenerado por test_16, cuyo hash difiere.
3. `test_18::test_generacion_reproducible_y_sin_efectos_sobre_la_base`: el constructor V2 rechaza ese ZIP base porque su hash dejó de coincidir con el fijado. Es consecuencia del punto 1.
4. `test_21::test_base_pinned_generacion_reproducible_y_acciones`: el constructor V3 produce un ZIP con metadatos/DEFLATE diferentes y texto con los finales de línea del sistema.
5. `test_24::test_bases_pinned_cadena_reproducible_y_zip_v42`: detecta el ZIP V3 regenerado por test_21. Es consecuencia del punto 4.

En la copia CRLF se suman seis comprobaciones de hashes de texto del baseline. Estas pasan al ejecutar sobre los blobs LF sin modificar sus pruebas.

## Comparación de paquetes antes y después

Cambian únicamente estos tres ZIP en ambas copias de prueba:

- `P9_ASIGNAR_DEPOSITO.zip`
- `P9_HABILITAR_ESTADO_ASIGNADO.zip`
- `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip`

En los quince miembros de esos tres ZIP, el contenido descomprimido es idéntico byte a byte y el orden de miembros permanece igual. `create_system` pasa de 3 (Unix) a 0 (Windows). Algunos miembros cambian de tamaño comprimido, aunque conservan tamaño original y CRC; por tanto, las diferencias no se limitan al byte del sistema creador.

Runtime de esta prueba: Python 3.14.3, Windows 10.0.19045, zlib de compilación y ejecución `1.3.1.zlib-ng`. El cambio de plataforma del creador está acreditado por los metadatos. La diferencia de DEFLATE está acreditada por los tamaños comprimidos y la igualdad de contenido. No se conoce aquí la versión exacta del compresor que produjo los ZIP históricos.

Los tres ZIP del checkout principal continúan coincidiendo con sus blobs de Git HEAD. Los dos incluidos en `huellas_base.json` también coinciden con esa evidencia. Estas ejecuciones los leyeron solo para crear el archive.

## Evidencias locales

- `baseline-regression-platform.json` y `baseline-regression-lf-platform.json`: entorno, tiempo, hashes y diferencias por miembro ZIP.
- `baseline-regression-p9.log` y `baseline-regression-lf-p9.log`: salidas completas de pytest.
- `baseline-regression-junit.xml` y `baseline-regression-lf-junit.xml`: resultados estructurados.
- `audit_baseline_regression.py`: extracción aislada, ejecución y comparación. Cada corrida exige una carpeta nueva; no borra ni sobrescribe una anterior.

No se cambió ningún test antiguo o constructor para hacer pasar esta auditoría. Los resultados muestran fallos previos de reproducibilidad binaria en Windows y sus efectos en cadena; no certifican una ejecución completa sin fallos.
