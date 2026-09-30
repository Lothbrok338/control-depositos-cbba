# ESTADO DEL PROYECTO — CONTROL DE DEPÓSITOS CBBA (módulo de normalización)

**Fecha del checkpoint P5:** 2026-09-30 · **P6 terminado, pendiente de aprobación, sin checkpoint** (checkpoint P5 = rama remota `checkpoint-p5` = `main` al cerrar P5; anteriores: P4 = rama remota `checkpoint-p4` (`998158e`); P3b = rama remota `checkpoint-p3b`; P1+P2 = commit `8c9c09a`, tag local `checkpoint-p1-p2`; P3 = rama remota `checkpoint-p3`; el entorno no puede subir tags) · **Regla rectora:** NORMALIZAR NUNCA DEBE DESTRUIR INFORMACIÓN DE ORIGEN.

## 1. Estado

| Paso | Estado | Qué entregó |
|---|---|---|
| Diagnóstico (Fase 1) | Terminado | Qué conservar, riesgos, redundancias, plan mínimo |
| Pruebas de regresión (Fase 2) | Terminado | 12 extractos reales como fixtures, doradas, defectos D-01…D-17 documentados |
| Diseño tres capas + capa 4 | Aprobado | `DISENO_TRES_CAPAS.md` (copia en el Project: `claude/FASE3_DISENO_TRES_CAPAS.md`) |
| **P1** Captura íntegra de origen | **Terminado** | `captura_origen.py` + paso 15 de `ejecutar_motor` → `ORIGEN.xlsx` |
| **P2** Pruebas de preservación | **Terminado** | `tests/test_05_preservacion.py` |
| **D-20** salidas del sistema como extractos | **Corregido** | `descubrir_archivos` excluye `NORMALIZADO*`, `ORIGEN*.xlsx`, `EXTRACTO_HISTORICO_*.xlsx` |
| **P3** Registro de bancos + motor genérico en modo sombra | **TERMINADO Y APROBADO** | `registro_bancos.json` (6 formatos + 1 rechazado, 13 cuentas), `motor_generico.py`, paso 16 pasivo en `ejecutar_motor`, `tests/test_06_sombra_p3.py`. Producción = solo legado |
| **P3b** Capa 4 (EXTRACTO_HISTORICO) | **TERMINADO Y APROBADO** | `historico.py` (función pura + escritor + CLI), bloque `historico` en `registro_bancos.json` (6 formatos), `tests/test_07_historico_p3b.py`, huella dorada `tests/golden/historico/MANIFEST_HISTORICO.json`. **No se integró a `ejecutar_motor`** (ver §5c) |
| **P4** Detección productiva por registro | **TERMINADO Y APROBADO** (577 PASS · 22 SKIP · 16 XFAIL · 0 FAIL) | `deteccion_registro.py` (nuevo); bloques `deteccion` + `legado` por formato y `version_deteccion: P4-1` en `registro_bancos.json`; `detectar_formato` delega en el registro; `ejecutar_motor` usa la detección completa; `tests/test_08_deteccion_p4.py`. Normalización = legado (sin cambios). Ver §5d |
| **P5** Normalización productiva por registro | **TERMINADO Y APROBADO** (620 PASS · 24 SKIP · 14 XFAIL · 0 FAIL) | La normalización productiva ya la ejecuta `motor_generico.py`: `ejecutar_motor` normaliza y valida con `motor_generico.py` + registro (pasos 2 y 7; ORIGEN con contrato del registro, paso 15); legado solo como referencia en sombra (paso 16); `tests/test_09_normalizacion_p5.py`; D-09 y D-12 corregidos. Ver §5e |
| **P6** Retiro del legado | **TERMINADO — PENDIENTE DE TU APROBACIÓN** (575 PASS · 23 SKIP · 14 XFAIL · 0 FAIL; sin checkpoint) | Retirados los `normalizar_*`, `validar_archivo`, `HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `encontrar_fila_encabezado`, `leer_tabla_movimientos`, `texto_de_archivo`, `aplicar_identidad_registro`, la referencia en sombra (paso 16), el comparador y la detección P3 de `motor_generico.py`, el cruce legado de `deteccion_registro.py` y los bloques `legado` del registro. Salidas P5 = P6. Ver §5f |

## 2. Resultado de pruebas (suite completa)

**Con P6 (pendiente de aprobación): 575 PASS · 23 SKIP · 14 XFAIL · 0 FAIL** (≈255 s). Diferencia con P5 (620 · 24 · 14): `test_06_sombra_p3.py` (112 PASS + 1 SKIP) se reemplaza por `test_06_registro_generico.py` (63 PASS; se retiran 49 pruebas y 1 SKIP que solo comparaban contra el legado o probaban el comparador/CLI); `test_08` −6 (4 mutaciones de la plantilla legada, 1 normalización con plantilla, 1 `aplicar_identidad_registro`); `test_09` −2 (referencia legada en sombra; las 12 comparaciones contra el legado pasan a compararse contra la referencia congelada: doradas + manifest); `test_10_retiro_legado_p6.py` +12. Los mismos 14 XFAIL. Salidas de los 12 fixtures idénticas a P5 (`tests/reports/EVIDENCIA_P6_RETIRO.txt`).

**Con P5 (aprobado): 620 PASS · 24 SKIP · 14 XFAIL · 0 FAIL** (≈285 s). P5 agrega `test_09_normalizacion_p5.py` (39 PASS + 2 SKIP UNION_ME con movimientos reales), pasa D-09 y D-12 de XFAIL a PASS (+1 prueba de encabezado parcial) y la fixture `normalizado` corre la ruta productiva. Salidas de los 12 fixtures idénticas a P4 (`tests/reports/EVIDENCIA_P5_NORMALIZACION.txt`).

**Con P4 (aprobado): 577 PASS · 22 SKIP · 16 XFAIL · 0 FAIL** (P4 agrega `test_08_deteccion_p4.py` con 68 PASS, pasa D-10 y D-11 de XFAIL a PASS y adapta `test_06` a la detección por registro; ≈290 s). Con P3b: 505 PASS · 22 SKIP · 18 XFAIL · 0 FAIL (P3b agrega 126 PASS y 2 SKIP de UNION_ME con movimientos reales). Antes de P3b: **379 PASS · 20 SKIP · 18 XFAIL · 0 FAIL** (≈130 s). **12 formatos reales coinciden al 100 % en sombra** (0 diferencias, 12/12 archivos). **UNION_ME: pendiente de fixture real** (solo proxy sintético en sombra). Base P1+P2: 270 / 19 / 18; P3 agrega 109 PASS y 1 SKIP (BISA_ME no tiene movimientos para comparar con su dorada).

* **PASS (270):** regresión de los 12 formatos contra doradas; lote de 12; preservación P2 (completitud celda a celda, reconstrucción del archivo, mapa 1:1, débitos, cabeceras/pies, metadatos, determinismo de IDs, columnas vacías, NORMALIZADO.xlsx y LISTS.csv idénticos a sus doradas); D-20 (9 nombres excluidos, 4 nombres reales que siguen incluidos, corrida completa con salida = entrada).
* **SKIP (19):** todos por falta de muestra real. UNION_ME: `REQUIERE MUESTRA REAL CON MOVIMIENTOS` (movimientos, saldos, débitos, `Nro de verificasion`, completitud y mapa) y archivo vacío real pendiente (`union_me_vacio.xls`). 8 pruebas de débitos en formatos sin débitos en su fixture (BCP_ME, BISA_ME, BISA_MN, BMSC, ECO_AHORRO, BNB_AHORRO, BNB_CLINICA, UNION_MN).
* **XFAIL (18):** defectos reales vigentes, aún **no** corregidos por decisión de fase: D-01…D-15, D-16, D-16b, D-17 (numeración del informe; D-18 y D-19 son de contenido y no tienen prueba).
* **Evidencia de que el motor operativo no cambió:** `tests/reports/EVIDENCIA_MOTOR_SIN_CAMBIOS.txt` (A/B motor original vs. actual: LISTS.csv idéntico byte a byte; NORMALIZADO.xlsx idéntico celda a celda; DataFrames de retorno y consola idénticos). Cambios totales del motor respecto del original: constante `PREFIJOS_SALIDA_SISTEMA` + una condición en `descubrir_archivos` (D-20) y el paso 15 al final de `ejecutar_motor` (P1).

## 3. Arquitectura aprobada

1. **NORMALIZADO_OPERATIVO** — las 26 `COLUMNAS_LISTS` sin cambios; `CLAVE TRANSACCIÓN` congelada. Es lo único que va a Microsoft Lists.
2. **DATOS_ORIGINALES** (+ **MAPA_ORIGEN**) — una fila por celda no vacía de todas las hojas, texto exacto y tipo original; `ID_EXTRACTO` = SHA-256 del archivo; `ID_ORIGEN` = `{ID_EXTRACTO[:16]}|{HOJA}|R{FILA}`. Enlace 1:1 con el movimiento vía `MAPA_ORIGEN` (CLAVE TRANSACCIÓN ↔ ID_ORIGEN).
3. **METADATOS_EXTRACTO** (+ **METADATOS_EXTRA**) — tabla fija por extracto + etiquetas/valores abiertos de cabecera, pie y hojas extra.
4. **EXTRACTO_HISTORICO** (capa 4, sin implementar) — un Excel amigable por banco/cuenta/periodo, con las columnas útiles propias de cada banco y solo `ESTADO`, `CONFIRMADO POR`, `FECHA DE CONFIRMACIÓN` añadidas; sin IDs técnicos; reconstruible desde DATOS_ORIGINALES + MAPA_ORIGEN + NORMALIZADO sin releer el banco.
5. `ORIGEN.xlsx` (capas 2 y 3) es un artefacto técnico y **separado**; no es el histórico de Contabilidad.
6. **Registro parametrizable** `registro_bancos.json` (FORMATOS / CUENTAS): una cuenta nueva de un formato conocido = una entrada, cero código (P3). **Desde P4 es la fuente productiva de la detección** (banco, cuenta, moneda, formato).
7. **UNION_ME** = `UNION_FECHAS_V1`: estructura **confirmada** por código legado + captura real (7 columnas, incl. `Nro de verificasion`, que el motor legado no lee y que va a ORIGEN e histórico, no a las 26 columnas). Comportamiento con movimientos: **pendiente de fixture real**.

Plan: P1 ✔ · P2 ✔ · P3 ✔ · P3b ✔ · P4 ✔ · P5 ✔ · **P6 retiro del legado (hecho, pendiente de aprobación)**.

## 4. Pendientes

**Muestras que faltan (de ti):**
* `union_me_vacio.xls` (activa 2 pruebas estructurales sobre archivo real y confirma D-16b).
* Extracto UNION_ME **con movimientos**, idealmente con al menos un débito.
* BMSC con débitos y con planilla en «Reporte de Pagos»; BISA y Unión con débitos; BNB con ITF distinto de cero.

**Decisiones tuyas:**
* Lista de valores válidos de `ESTADO` (hoy: REQUIERE DEFINICIÓN).
* D-18/D-19 (BNB `DEPOSITANTE`: sobre-captura y beneficiario en débitos): mantener el valor legado y exponer el dato correcto en DERIVADOS, o cambiar el contrato de la columna.
* Unidad de la capa 4 (archivo por cuenta-mes), formato de fecha, columna CLAVE oculta vs. protegida, y convivencia con `PLANTILLA EXTRACTO.xlsx` hasta probar Excel Online.
* Política de `ORIGEN.xlsx`: hoy se escribe junto a NORMALIZADO.xlsx y se sobrescribe en cada corrida.

**Defectos de la Fase 2 sin corregir (14 XFAIL):** se atacan en su propio carril. D-10 y D-11 se corrigieron con P4 (detección); D-09 y D-12 con P5 (normalización por registro). D-06, D-07, D-16, D-16b y D-17 se prueban desde P5 sobre la ruta productiva (el genérico los reproduce a propósito).

**Observación:** el consumidor de `PROCESAR.txt` en Power Automate sigue sin identificarse; el flujo no ejecuta Python.

## 5. P3 — registro + motor genérico en modo sombra (hecho)

* `registro_bancos.json`: `FORMATOS` (BNB, BCP, BISA, ECO, BMSC, `UNION_FECHAS_V1` y `UNION_ULTIMOS12_V1` rechazado) y `CUENTAS` (las 13 actuales, con el mismo id que el código legado). Incluye `campos_canonicos` (llena `CAMPO_CANONICO`, **aún sin conectar** a `ORIGEN.xlsx`: `captura_origen.py` no se tocó).
* **Agregar una cuenta de un formato conocido = una entrada en `CUENTAS`**, cero código (probado con `Registro.con_cuenta`).
* `motor_generico.py`: detecta (firma en cabecera + cuenta registrada), lee, mapea a las 26 columnas y valida saldos solo con el registro. Reutiliza del legado únicamente primitivas de conversión/lectura y `finalizar_dataframe` (que fija `COLUMNAS_LISTS` y `CLAVE TRANSACCIÓN`).
* **Sombra:** al final de `ejecutar_motor` (paso 16, tras escribir la salida productiva) compara la corrida del legado con el genérico y escribe `SOMBRA_REPORTE.json` (diferencias + observaciones) y `SOMBRA_DIFERENCIAS.csv` (solo diferencias) junto a `NORMALIZADO.xlsx`. Clave nueva del retorno: `sombra_estado`. Un fallo o una diferencia **nunca** cambia ni detiene la producción. `CBBA_MOTOR_SOMBRA=0` la apaga; `CBBA_REGISTRO_BANCOS=<ruta>` usa otro registro (pruebas).
* También corre solo: `python motor_generico.py <carpeta_entrada> [<carpeta_reporte>]` (no escribe NORMALIZADO.xlsx ni LISTS.csv).
* **Resultado:** los 12 formatos con extracto real coinciden al 100 % (detección, 26 columnas, índice de fila, tipos, validación de saldos). UNION_ME: sin extracto real; solo proxy sintético.
* **Diferencias conocidas, reportadas y NO corregidas en el legado** (el genérico es más estricto o distinto) — **las de detección quedaron resueltas en P4 (§5d)**: D-09 (encabezado incompleto), D-10 (cuenta dentro de una glosa), D-11 (BMSC no verifica cuenta), «Últimos 12 movimientos» (el legado lo detecta como UNION_ME), cuenta ambigua en cabecera. Los defectos D-06, D-16, D-16b, D-17 etc. el genérico los **reproduce** a propósito (siguen XFAIL).
* **Observación:** las sumas de créditos/débitos de la validación difieren ~1e-10 entre legado y genérico (orden de suma en coma flotante). Se informan como *observación* (tolerancia 1e-6, muy por debajo de la tolerancia 0.01 del motor) y no cuentan como diferencia.
* Evidencia: `tests/reports/EVIDENCIA_P3_SOMBRA.txt` (A/B contra el motor del checkpoint: LISTS.csv idéntico byte a byte, NORMALIZADO.xlsx idéntico celda a celda, componentes congelados con texto fuente idéntico).

## 5c. P3b — capa 4 EXTRACTO_HISTORICO (hecho y aprobado)

* **Qué genera:** un `.xlsx` por banco / cuenta / mes (`EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{AAAA-MM}.xlsx`), con **una sola hoja `EXTRACTO`**: título, zona superior (banco, cuenta, moneda, titular, producto, período del mes y del extracto, emisión, y los saldos/totales que el banco declara), tabla con las **columnas propias de cada banco en su orden y con su nombre**, y al final **solo** `ESTADO · CONFIRMADO POR · FECHA DE CONFIRMACIÓN`. `CLAVE TRANSACCIÓN` va en una columna **oculta** de la misma tabla (para sincronizar después). Fecha visible `dd/mm/yyyy`.
* **Fuentes:** solo `DATOS_ORIGINALES + MAPA_ORIGEN` (ORIGEN.xlsx) + `NORMALIZADO.xlsx` (hoja LISTS) **o** `LISTS.csv` + `registro_bancos.json`. No abre el extracto bancario, no importa el motor ni `captura_origen.py`, no escribe en NORMALIZADO/LISTS/ORIGEN.
* **Valores:** fecha, hora, débito, crédito, importe con signo y saldo desde NORMALIZADO (mismos números que van a Lists); el resto, texto del banco sin los espacios de relleno. Códigos/cheques/referencias siempre texto (`0000335`, `034`, `4401`).
* **Verificación antes de escribir:** cada movimiento con su fila de origen, mismas cantidades y sumas que NORMALIZADO, y saldos/totales declarados (marcados `verifica` en el registro) cuadran con los movimientos (tolerancia 0,01). Si falla, **ese** archivo no se escribe y se informa la causa.
* **Uso:** `python historico.py <ORIGEN.xlsx> <NORMALIZADO.xlsx|LISTS.csv> <carpeta_salida> [registro.json]` o `generar_extractos_historicos(...)`.
* **Resultado con los 12 fixtures:** 11 archivos (10 de agosto + BCP_ME de julio); BISA_ME sin movimientos no genera archivo; 0 advertencias, 0 errores.
* **Desviaciones respecto del diseño §6/§8:** (1) **no** hay paso 17 en `ejecutar_motor`: el motor queda intacto y el histórico corre después, desde los archivos (la ruta de salida sigue sin definir y `test_06_sombra_p3` fija los archivos de la carpeta productiva); (2) nombre de archivo sin moneda, según tu ejemplo; (3) `version_registro` sigue en `P3-1` (lo exige la prueba de sombra) y se agrega `version_historico: P3b-1`; (4) la dorada de la capa 4 es una **huella** (columnas, filas, zona superior y SHA-256 de valores) para no duplicar movimientos reales en el repositorio.

## 5b. (histórico) Plan original de P3b

Capa 4 (`EXTRACTO_HISTORICO`, ver `DISENO_TRES_CAPAS.md` §6): bloque `historico` de los formatos en `registro_bancos.json`, `historico.py` (función pura + escritor) y `test_06_historico.py`, alimentado del `NORMALIZADO` legado. No depende de P4 ni P5. Sin decidir todavía: ruta de salida, lista de `ESTADO`, formato de fecha y convivencia con `PLANTILLA EXTRACTO.xlsx` (sección 4).

## 5d. P4 — detección productiva por registro (hecho y aprobado · checkpoint `checkpoint-p4`)

* **Qué cambió:** banco, cuenta, moneda y formato se identifican con `registro_bancos.json` (`deteccion_registro.py`, junto al motor). `detectar_formato(archivo)` conserva su contrato (id de cuenta o `NO_RECONOCIDO`) y `detectar_extracto(archivo)` devuelve el detalle (estado, motivo, hoja, fila de encabezado, cuenta leída, id del normalizador legado). `ejecutar_motor` agrega al retorno `deteccion_estado` (versión, ruta y SHA-256 del registro, detalle por archivo).
* **Reglas:** firma solo en cabecera + encabezado; encabezado con menos de `puntaje_minimo` (100 %) = `ENCABEZADO_INCOMPLETO` con las columnas que faltan; la cuenta se lee **solo** en la celda que sigue a una etiqueta de `deteccion.etiquetas_cuenta` en las filas anteriores al encabezado (nunca glosas ni movimientos); debe ser **una** cuenta registrada para ese formato (`CUENTA_NO_REGISTRADA`, `SIN_CUENTA`, `AMBIGUO` si no); dos formatos válidos en el mismo libro = `AMBIGUO`; «Últimos 12 movimientos» = `RECHAZADO` (por hoja o por `cabecera_prohibida`). Cualquier rechazo detiene el lote **antes de escribir** y el mensaje nombra archivo, estado y motivo.
* **Cuenta nueva = una entrada en `CUENTAS`** (probado de punta a punta: NORMALIZADO, LISTS, ORIGEN, sombra y EXTRACTO_HISTORICO). Como la normalización sigue en el legado, la cuenta nueva se normaliza con la plantilla de su formato (`legado.plantilla_por_hoja`) y BANCO / CUENTA BANCARIA / MONEDA se toman del registro; `CLAVE TRANSACCIÓN` se recalcula con `crear_clave` (fórmula congelada). Para las 13 cuentas actuales el normalizador recibe su propio id, como antes; si el registro contradijera su banco/cuenta/moneda, el proceso se detiene.
* **Dependencia nueva:** sin `registro_bancos.json` válido y `deteccion_registro.py` junto al motor, el proceso se detiene con error claro (antes solo fallaba la sombra). Al desplegar el motor hay que copiar esos dos archivos.
* **Defectos:** D-10 y D-11 **corregidos** (sus pruebas pasan a regresión). D-09 y D-12: la ruta productiva ya no los alcanza (no se normaliza sin encabezado completo; una cuenta nueva no hereda la identidad de la plantilla), pero la primitiva (`encontrar_fila_encabezado` / `else` de los `normalizar_*`) sigue igual → **siguen XFAIL** hasta P5.
* **Sombra (P3):** las diferencias de detección que reportaba (D-09, D-10, D-11, «Últimos 12», cuenta ambigua) ya no existen: producción y genérico coinciden. Sigue comparando la normalización (12/12 sin diferencias).
* **Evidencia:** `tests/reports/EVIDENCIA_P4_DETECCION.txt` (referencia `main` 9a3eae8): LISTS.csv idéntico byte a byte; NORMALIZADO.xlsx (4 hojas), ORIGEN.xlsx (4 hojas) y los 11 EXTRACTO_HISTORICO idénticos; DataFrames de retorno y consola idénticos; texto fuente idéntico de `COLUMNAS_LISTS`, `crear_clave`, `finalizar_dataframe`, los 6 `normalizar_*`, `validar_archivo`, primitivas de número/fecha/hora; `captura_origen.py`, `historico.py`, `motor_generico.py` sin cambios.

## 5e. P5 — normalización productiva por registro (hecho y aprobado · checkpoint `checkpoint-p5`)

* **Estado:** la normalización y la validación de saldos productivas **ya las ejecuta `motor_generico.py`** gobernado por `registro_bancos.json`. Los `normalizar_*` legados solo corren como referencia en sombra (paso 16) hasta P6.

* **Flujo productivo:** archivo → detección por registro (P4, sin cambios) → `normalizar_extracto` (motor genérico + `registro_bancos.json`) → validación `validar_extracto` (mismas fuentes de saldo, misma ecuación y tolerancia) → NORMALIZADO.xlsx / LISTS.csv / ORIGEN.xlsx. `CLAVE TRANSACCIÓN` y las 26 columnas siguen saliendo de `finalizar_dataframe` / `crear_clave` (sin cambios).
* **Motor:** cambia solo `ejecutar_motor` (paso 1 carga también el normalizador y exige que use el mismo registro que la detección; paso 2 normaliza con el genérico; paso 7 valida con el genérico sobre las mismas filas; paso 15 arma el contrato de ORIGEN con hoja y encabezado del registro; paso 16 corre el legado como referencia). Funciones nuevas: `modulo_generico`, `normalizador_registro`, `normalizar_extracto`, `validar_extracto`, `contrato_origen_registro`. Ningún `normalizar_*`, `validar_archivo`, `encontrar_fila_encabezado`, `HOJAS_VALIDAS` ni `ENCABEZADOS_ESPERADOS` cambió.
* **`motor_generico.py`:** versión `P5-1`; la tabla solo se lee desde un encabezado que cumple `puntaje_minimo` (D-09); `ejecutar_sombra_produccion` se reemplaza por `ejecutar_referencia_legado` (el legado pasa a ser la sombra: modo `REFERENCIA_LEGADO` en `SOMBRA_REPORTE.json`). **Registro:** `version_normalizacion: P5-1` y textos de ayuda; ninguna regla de formato o cuenta cambió.
* **Cuenta nueva = una entrada en `CUENTAS`**, normalizada sin `normalizar_*` propio ni plantilla legada (probado con las 13 cuentas renombradas sobre el lote real → LISTS.csv idéntico byte a byte, con el legado inutilizado).
* **Defectos:** D-09 y D-12 **corregidos** en la ruta productiva. Desaparece también el ruido de coma flotante (~1e-10) que P3 informaba como observación: producción y referencia validan las mismas filas.
* **Cambio de comportamiento respecto de P4 (fuera de los extractos válidos):** (1) si el registro contradice la identidad fija de un normalizador legado, P4 detenía la producción; P5 usa el registro (fuente única) y la referencia legada lo reporta como diferencia; (2) `motor_generico.py` pasa a ser dependencia productiva: si falta, o el registro no sirve para normalizar, el proceso se detiene antes de escribir. Al desplegar: copiar `motor_control_depositos_cbba.py`, `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json` y `captura_origen.py` juntos.
* **Todavía depende del legado:** (a) primitivas compartidas del motor (número, fecha, hora, código, texto, lector de Excel, `buscar_columna*`, `finalizar_dataframe`/`crear_clave`, `ecuacion_saldo`, `extraer_nombre_bnb` = estrategia `legacy_bnb`), que son contrato congelado, no normalizadores; (b) la detección P4 valida el registro contra `HOJAS_VALIDAS` / `ENCABEZADOS_ESPERADOS` y calcula `formato_legado` (bloque `legado` del registro), hoy solo usado por la referencia; (c) el paso 16 (referencia en sombra) usa `normalizar_*`, `validar_archivo` y `aplicar_identidad_registro`. Todo esto se retira o se reubica en P6.
* **Evidencia:** `tests/reports/EVIDENCIA_P5_NORMALIZACION.txt` (referencia = checkpoint P4 `998158e`): LISTS.csv idéntico byte a byte; NORMALIZADO.xlsx 4 hojas idénticas celda a celda; ORIGEN.xlsx 4 hojas idénticas; 11 EXTRACTO_HISTORICO idénticos; por archivo mismos movimientos, importes, saldos, claves y banco/cuenta/moneda; retorno y consola idénticos; producción sin ningún normalizador legado = P4 byte a byte.

## 5f. P6 — retiro controlado del legado (hecho · PENDIENTE DE APROBACIÓN · sin checkpoint)

* **Retirado del motor** (`motor_control_depositos_cbba.py`): `normalizar_bnb`, `normalizar_bcp`, `normalizar_union`, `normalizar_economico`, `normalizar_bisa`, `normalizar_bmsc`, `normalizar_archivo`, `validar_archivo`, `HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `encontrar_fila_encabezado`, `leer_tabla_movimientos`, `texto_de_archivo`, `aplicar_identidad_registro` y el paso 16 (referencia legada en sombra: `SOMBRA_REPORTE.json`, `SOMBRA_DIFERENCIAS.csv`, `CBBA_MOTOR_SOMBRA`, clave `sombra_estado` del retorno). `detector_registro` ya no pasa las constantes legadas; `ejecutar_motor` pierde el paso 16 y la línea de consola «cuenta registrada solo en registro_bancos.json» (todas lo están).
* **Retirado de `motor_generico.py`**: comparador y sombra (`ejecutar_referencia_legado`, `referencia_archivo`, `sombra_archivo`, `comparar_*`, `armar_informe`, `escribir_informe`), `cargar_legado`, la detección propia de P3 (`MotorGenerico.detectar`, `procesar`, `Deteccion`, `ResultadoGenerico`; la productiva es `deteccion_registro.py` desde P4) y el modo script. `PRIMITIVAS_LEGADO` / `namespace_legado` pasan a `PRIMITIVAS_MOTOR` / `namespace_primitivas` (misma lista). `normalizar`, `validar` y `Registro` quedan con el mismo código (solo docstrings). Versión `P6-1` (no se escribe en ninguna salida).
* **Retirado de `deteccion_registro.py`**: validación contra `HOJAS_VALIDAS` / `ENCABEZADOS_ESPERADOS` / `legado.plantilla_por_hoja`, `_formato_legado`, estado `HOJA_INCOMPATIBLE` y los campos `formato_legado` / `cuenta_nueva` (y `FORMATO_LEGADO` / `CUENTA_NUEVA` de `deteccion_estado`). Las reglas de detección no cambian (`version_deteccion` P4-1).
* **Registro**: se quitan los 6 bloques `legado` y su ayuda; ninguna regla de formato ni cuenta cambia.
* **Primitivas compartidas que permanecen en el motor (sin cambios, sin duplicar)**: `COLUMNAS_LISTS`, `crear_clave`, `valor_clave_numero`, `finalizar_dataframe` (26 columnas y CLAVE), `ecuacion_saldo` (validación), `extraer_nombre_bnb` (estrategia `legacy_bnb`, D-18/D-19), `numero`, `normalizar_fecha`, `normalizar_hora`, `codigo_texto`, `normalizar_texto`, `buscar_columna*`, `leer_excel_robusto`, `leer_todas_hojas` (usadas por `motor_generico.py` y `deteccion_registro.py`), `descubrir_archivos`. No se movieron a un módulo común para no agregar un archivo de despliegue.
* **Archivos productivos**: `motor_control_depositos_cbba.py`, `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json`, `captura_origen.py` (+ `historico.py` para la capa 4). Probado: con solo esos 5 archivos en una carpeta aislada, los 12 fixtures dan LISTS.csv / NORMALIZADO.xlsx / ORIGEN.xlsx idénticos a P5.
* **Pruebas**: `helpers.HOJAS` / `helpers.ENCABEZADOS` = copia congelada de las constantes legadas; la equivalencia con el legado queda fijada por las doradas; `test_06_registro_generico.py` (reemplaza `test_06_sombra_p3.py`) y `test_10_retiro_legado_p6.py` (nuevo). `generar_golden.py` exige un motor con legado (checkpoint ≤ P5).
* **Evidencia**: `tests/reports/EVIDENCIA_P6_RETIRO.txt` (referencia = checkpoint P5 `0b182e2`): LISTS.csv idéntico byte a byte; NORMALIZADO.xlsx y ORIGEN.xlsx idénticos celda a celda; 11 EXTRACTO_HISTORICO idénticos; por archivo mismos movimientos, importes, saldos, claves y banco/cuenta/moneda; retorno idéntico salvo `sombra_estado`; nombres legados en el código productivo P5 = 19 / 23 / 7 → P6 = 0; `captura_origen.py`, `historico.py`, Power Automate, doradas y fixtures sin cambios; código productivo 8 997 → 6 060 líneas.
* **Riesgos pendientes**: (1) quien leyera `sombra_estado`, `FORMATO_LEGADO` / `CUENTA_NUEVA` o `SOMBRA_REPORTE.json` deja de recibirlos (en el repositorio nadie; el consumidor de Power Automate no ejecuta Python); (2) carpetas de salida con `SOMBRA_*` de corridas anteriores: ya no se actualizan (se pueden borrar; no se toman como extractos); (3) desaparece la red de comparación en vivo contra el legado: la protección queda en las doradas y en las pruebas; (4) `evidencia_p4_extra.py` / `evidencia_p5_extra.py` y `generar_golden.py` solo corren sobre su checkpoint.

## 6. Componentes que todavía NO deben modificarse

* `COLUMNAS_LISTS` (26 columnas, su orden y nombres) y `CLAVE TRANSACCIÓN` (fórmula).
* `finalizar_dataframe`, `crear_clave` y las primitivas compartidas del motor (desde P6 los `normalizar_*`, `validar_archivo`, `HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `encontrar_fila_encabezado` y `leer_tabla_movimientos` ya no existen).
* El control del año 2026 fijo.
* `deteccion_registro.py`, los bloques `deteccion` / `legado` del registro, `detectar_formato` y los pasos 1, 2, 7 y 15 de `ejecutar_motor` (P4): solo cambian con aprobación.
* Estructura de `NORMALIZADO.xlsx` (4 hojas, `tblLISTS`) y `LISTS.csv` (UTF-8 con BOM).
* El flujo de Power Automate `NORMALIZAR EXTRACTOS DIARIOS CBBA`, Microsoft Lists y Power Apps.
* `captura_origen.py` y el paso 15 de `ejecutar_motor` (aprobados; solo cambian con nueva aprobación). El paso 16 (sombra) se retiró en P6.
* `historico.py` y el bloque `historico` del registro (P3b): solo cambian con aprobación; su huella dorada se regenera con `tests/generar_golden_historico.py --force` y motivo explícito.
* Las doradas (`tests/golden/`) y los fixtures reales: solo se regeneran con motivo explícito y contra el motor original.
* Los archivos bancarios originales: siempre evidencia inalterada.
