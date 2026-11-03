# Corrección P8 después de auditoría

## Actualización V3: nombre técnico HASH_SHA256

Base de esta revisión: `93c16475bfe5b188cd05a53a999950daa22aa773`, rama `candidate/p8-m365-pilot`. V3 aprobada para publicar únicamente en esa rama y probar en tenant. Sin merge a main ni checkpoint.

El tenant confirmó que V2 seguía creando `_x0053_HA256` pese a Name/StaticName/DisplayName SHA256, ID explícito y Options=9. Se retira ese intento. Depositos_Cargas usa ahora InternalName `HASH_SHA256`, con nombre lógico y visible `SHA256`.

- Contrato: solo la entrada del hash cambia; agrega `nombre_logico` y `nombre_visible` y actualiza `nombre_tecnico`. Las 34 columnas de Activos y las otras 12 de Cargas permanecen idénticas.
- Provisión: creación con Name/StaticName/DisplayName HASH_SHA256; MERGE por GUID del campo recién creado para establecer Title SHA256. Se exige InternalName y Title exactos al releer. Las columnas antiguas producen FAIL sin borrado, migración ni segunda columna del mismo título.
- Carga: único cambio en el WDL, `item/SHA256` → `item/HASH_SHA256`. Se conserva `varSha256`, el valor de `sha256_archivo_fuente`, el Parse JSON P7, los contadores y la lógica bancaria/idempotencia.
- Paquetes: nuevos `P8_PROVISIONAR_LISTAS_V3_HASH_SHA256.zip` y `P8_CARGA_DEPOSITOS_ACTIVOS_V3_HASH_SHA256.zip`. Los nombres visibles de los flujos son exactamente los de sus ZIP sin extensión; los manifiestos y las definiciones coinciden, con identificadores propios para importarlos como nuevos. Los ZIP anteriores del provisionador, de carga y el ZIP general anterior se conservan como históricos.
- Pruebas P8: **78 PASS**, incluyendo regresión de nombres/título, listas antiguas con y sin datos, provisión + carga + reproceso usando el inventario de columnas provisionadas y rechazo de escrituras con los nombres internos anteriores.
- Adaptador P7: **45 PASS**. Los 91 archivos del checkpoint P7 son idénticos byte por byte; también se compararon sin diferencias el contrato y el plan compilado de Activos y las otras 12 columnas de Cargas.
- Pendiente: importación y ejecución real de V3 y de la carga actualizada en el tenant. Los ensayos locales no sustituyen esa aceptación.

La evidencia actual está en `p8/provision/evidencia_validacion.json` y `pruebas_provision.log`. Las secciones siguientes documentan la auditoría anterior; sus cifras y estado corresponden a aquella entrega, no a V3.

## Registro histórico de la auditoría anterior

Estado: correcciones y ensayos locales completados; piloto Microsoft 365 pendiente. Sin commit ni checkpoint P8. HEAD/main y origin/checkpoint-p7 siguen en `673754a9b69072e6960bbf0c7ffb0f50dc5d2670`. Todos los archivos versionados de esa base son idénticos por SHA-256 en ambos árboles.

## 1. Comparación reproducida en el mismo entorno

Se ejecutó exactamente `python -m pytest -q -rxX` desde la raíz de cada checkout, con el mismo ejecutable `/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python`. P7 se ejecutó aislado en `/workspace/control-depositos-cbba-p7-auditoria` con HEAD detached en el checkpoint, sin archivos P8. P8 se ejecutó desde `/workspace/control-depositos-cbba`. No se cambiaron dependencias, tolerancias, pruebas heredadas ni doradas durante la corrección.

Versiones: pytest 9.1.1, pandas 2.2.3, numpy 2.3.5, openpyxl 3.1.5, xlrd 2.0.1, python-calamine 0.8.2.

| Suite | PASS | SKIP | XFAIL | FAIL |
|---|---:|---:|---:|---:|
| P7 | 614 | 23 | 14 | 6 |
| P8 | 642 | 23 | 14 | 6 |

Las 657 pruebas heredadas conservan exactamente el mismo resultado individual. Hay 28 pruebas nuevas P8, todas PASS. Los seis fallos se reproducen sin P8; la comparación confirma que no son regresiones introducidas por P8. No demuestra por sí sola qué versión histórica de una dependencia originó las diferencias numéricas.

FAIL exactos, iguales en ambos checkouts:

1. `tests/test_05_preservacion.py::test_normalizado_xlsx_identico_a_su_dorada[RESUMEN]`
2. `tests/test_05_preservacion.py::test_normalizado_xlsx_identico_a_su_dorada[VALIDACION]`
3. `tests/test_05_preservacion.py::test_si_la_captura_falla_normalizado_y_lists_salen_identicos`
4. `tests/test_07_historico_p3b.py::test_normalizado_y_lists_siguen_identicos_a_sus_doradas`
5. `tests/test_09_normalizacion_p5.py::test_p5_las_12_cuentas_reales_como_cuentas_nuevas_solo_por_configuracion`
6. `tests/test_09_normalizacion_p5.py::test_p5_lote_real_completo_sin_ningun_normalizador_legado`

Las trazas muestran serializaciones de coma flotante como `3807655.560000001` frente a `3807655.56`, y una diferencia máxima `1.862645149230957e-09` frente al umbral existente `1e-9`. Se conservan íntegros motor, tolerancias y doradas.

Evidencia: `p8/evidencias/suite_p7.log`, `suite_p8.log`, `resultados_p7.json`, `resultados_p8.json`, `comparacion.json`, `entorno_comparacion.json` y `huellas_archivos_congelados.json`. Las pruebas conjuntas P7+P8 se ejecutaron además por separado; resultado en `pruebas_p7_p8.log`.

## 2. Correcciones implementadas

| Observación | Resultado |
|---|---|
| Terminación antes de bitácora | `FINALLY` registra el lote; `Finalizar_ejecucion` solo corre tras su éxito. JSON ilegible, contrato inválido y propiedades ausentes tienen ruta FALLIDO comprobada. |
| Trigger/ubicación | SharePoint `GetOnNewFileItems`, nombre `{FilenameWithExtension}`, identificación `{Identifier}`, exclusión de `{IsFolder}`; patrón estricto de archivo. |
| Contenido | `inferContentType = false`; Parse JSON usa `json(base64ToString(body('Obtener_contenido_del_archivo')?['$content']))` con el esquema P7 idéntico. |
| Timeout/reconsulta | Crear Failed/TimedOut dispara reconsulta; presencia → YA_EXISTE, ausencia o reconsulta fallida → ERROR de fila. Continúa el lote. |
| Diagnóstico | JSON con etapa/archivo/mensaje, y fila/CLAVE_TRANSACCION/motivo/código por error; máximo 8 detalles y 8000 caracteres. Sin cuerpos ni `result()`. |
| Preconsulta/fechas | Una consulta exacta indexada por clave antes de crear. No usa límites temporales ni depende de conversión UTC. |
| Fecha testigo | `2026-07-09` se copia intacta y coincide con `20260709`; 9 de julio es el testigo visual exigido en tenant. |
| Piloto ampliado | Cuatro filas existentes de doradas/fixtures, con débito, originante, Ó, espacio, hora vacía y crédito `-640.0`; trazabilidad individual. |

La definición inicial P8 ya evitaba Terminate previo al cierre; esta corrección hace explícita y prueba la terminación posterior a una bitácora confirmada. Se corrigieron también dos nombres internos de acción repetidos; el validador exige ahora nombres únicos y dependencias runAfter dentro de cada ámbito.

## 3. Resultado del ensayo local del flujo generado

Se interpreta el JSON WDL entregado con conectores simulados; no es una ejecución en Power Automate. Las pruebas recorren expresiones, scopes, condiciones, bucles y ejecución posterior. Incluyen propagación conservadora de fallos de acciones hijas para comprobar que un error manejado no degrada todo el lote.

| Ejecución | RECIBIDA | VÁLIDA | NUEVA | YA_EXISTE | ERROR | Claves preconsulta | Intentos crear | Activos finales |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Primera | 8 | 8 | 8 | 0 | 0 | 0 | 8 | 8 |
| Reproceso | 8 | 8 | 0 | 8 | 0 | 8 | 0 | 8 |

Ambas terminan COMPLETADO. Las pruebas con fallos de creación/reconsulta terminan COMPLETADO_CON_ERRORES y procesan las siguientes filas. El segundo conjunto crea 4 movimientos y al reprocesar consulta 4 claves y realiza 0 creaciones.

## 4. Archivos y entrega

Actualizados respecto a la entrega P8 anterior: `DOCUMENTACION_TECNICA_P8.md`, `P8_CARGA_DEPOSITOS_ACTIVOS.zip`, `p8/construir_paquete_p8.py`, `p8/flujo_p8_definition.json`, `p8/validar_p8.py`, `tests/test_12_flujo_p8.py` y el ZIP general.

Nuevos en esta corrección: `p8/definicion.py`, `p8/ensayo_wdl.py`, `p8/preparar_piloto.py`, `p8/entregar_correccion.py`, `p8/piloto_ampliado/`, `p8/evidencias/` y este reporte. El esquema de Lists conserva sus columnas y tipos. Todos los archivos P8 siguen sin commit; no hay cambios en archivos versionados de P7/P6.

El ZIP de flujo mantiene la estructura del paquete exportado real disponible en el repositorio. La integridad y reproducibilidad local están verificadas. Su importación efectiva todavía no está certificada por Microsoft 365. El ZIP general incluye documentación, fuentes, pruebas, evidencia y los insumos congelados de P7 necesarios para reproducirlos; excluye caches.

## 5. Pendientes y límites reales

1. Importar/configurar la conexión, sitio, biblioteca, carpeta y listas reales; comprobar que el diseñador acepta la definición.
2. Confirmar las propiedades del trigger y el sobre binario con inferContentType false. Si se observa JSON interpretado, revisar y cambiar conjuntamente configuración y expresión; no adivinar.
3. Ejecutar piloto 8 + reproceso y comprobar ocho claves preconsultadas, cero intentos de crear, total ocho. Verificar visualmente 9 de julio y extremos.
4. Ejecutar el segundo conjunto + reproceso y verificar signos, texto, espacios y acentos.
5. Ningún flujo puede prometer persistencia si la propia lista de bitácora está inaccesible: en ese caso la ejecución queda fallida y requiere revisión de historial. No se declara éxito ni se oculta el fallo.
6. Las consultas por clave priorizan corrección para el piloto. No se optimizan 4000 movimientos. FECHA_CARGA y D-15 siguen intactos.

P8 queda disponible para revisión antes del piloto. No se ha creado Power Apps ni se ha ejecutado ningún cambio sobre Microsoft 365.
