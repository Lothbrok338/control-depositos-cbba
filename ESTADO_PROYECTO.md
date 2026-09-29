# ESTADO DEL PROYECTO — CONTROL DE DEPÓSITOS CBBA (módulo de normalización)

**Fecha:** 2026-09-29 (checkpoint P1+P2 = commit `8c9c09a`, tag `checkpoint-p1-p2`; P3 encima) · **Regla rectora:** NORMALIZAR NUNCA DEBE DESTRUIR INFORMACIÓN DE ORIGEN.

## 1. Estado

| Paso | Estado | Qué entregó |
|---|---|---|
| Diagnóstico (Fase 1) | Terminado | Qué conservar, riesgos, redundancias, plan mínimo |
| Pruebas de regresión (Fase 2) | Terminado | 12 extractos reales como fixtures, doradas, defectos D-01…D-17 documentados |
| Diseño tres capas + capa 4 | Aprobado | `DISENO_TRES_CAPAS.md` (copia en el Project: `claude/FASE3_DISENO_TRES_CAPAS.md`) |
| **P1** Captura íntegra de origen | **Terminado** | `captura_origen.py` + paso 15 de `ejecutar_motor` → `ORIGEN.xlsx` |
| **P2** Pruebas de preservación | **Terminado** | `tests/test_05_preservacion.py` |
| **D-20** salidas del sistema como extractos | **Corregido** | `descubrir_archivos` excluye `NORMALIZADO*`, `ORIGEN*.xlsx`, `EXTRACTO_HISTORICO_*.xlsx` |
| **P3** Registro de bancos + motor genérico en modo sombra | **Terminado** | `registro_bancos.json` (6 formatos + 1 rechazado, 13 cuentas), `motor_generico.py`, paso 16 pasivo en `ejecutar_motor`, `tests/test_06_sombra_p3.py`. Producción = solo legado |
| P3b · P4 · P5 · P6 | No iniciados | |

## 2. Resultado de pruebas (suite completa)

**379 PASS · 20 SKIP · 18 XFAIL · 0 FAIL** (≈130 s). Base P1+P2: 270 / 19 / 18; P3 agrega 109 PASS y 1 SKIP (BISA_ME no tiene movimientos para comparar con su dorada).

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
6. **Registro parametrizable** `registro_bancos.json` (FORMATOS / CUENTAS): una cuenta nueva de un formato conocido = una entrada, cero código (P3).
7. **UNION_ME** = `UNION_FECHAS_V1`: estructura **confirmada** por código legado + captura real (7 columnas, incl. `Nro de verificasion`, que el motor legado no lee y que va a ORIGEN e histórico, no a las 26 columnas). Comportamiento con movimientos: **pendiente de fixture real**.

Plan: P1 ✔ · P2 ✔ · **P3** registro + motor genérico en modo sombra · P3b generador de capa 4 · P4 detección al registro · P5 normalización al registro · P6 retiro del legado.

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

**Defectos de la Fase 2 sin corregir (18 XFAIL):** se atacan en su propio carril, después de P3.

**Observación:** el consumidor de `PROCESAR.txt` en Power Automate sigue sin identificarse; el flujo no ejecuta Python.

## 5. P3 — registro + motor genérico en modo sombra (hecho)

* `registro_bancos.json`: `FORMATOS` (BNB, BCP, BISA, ECO, BMSC, `UNION_FECHAS_V1` y `UNION_ULTIMOS12_V1` rechazado) y `CUENTAS` (las 13 actuales, con el mismo id que el código legado). Incluye `campos_canonicos` (llena `CAMPO_CANONICO`, **aún sin conectar** a `ORIGEN.xlsx`: `captura_origen.py` no se tocó).
* **Agregar una cuenta de un formato conocido = una entrada en `CUENTAS`**, cero código (probado con `Registro.con_cuenta`).
* `motor_generico.py`: detecta (firma en cabecera + cuenta registrada), lee, mapea a las 26 columnas y valida saldos solo con el registro. Reutiliza del legado únicamente primitivas de conversión/lectura y `finalizar_dataframe` (que fija `COLUMNAS_LISTS` y `CLAVE TRANSACCIÓN`).
* **Sombra:** al final de `ejecutar_motor` (paso 16, tras escribir la salida productiva) compara la corrida del legado con el genérico y escribe `SOMBRA_REPORTE.json` (diferencias + observaciones) y `SOMBRA_DIFERENCIAS.csv` (solo diferencias) junto a `NORMALIZADO.xlsx`. Clave nueva del retorno: `sombra_estado`. Un fallo o una diferencia **nunca** cambia ni detiene la producción. `CBBA_MOTOR_SOMBRA=0` la apaga; `CBBA_REGISTRO_BANCOS=<ruta>` usa otro registro (pruebas).
* También corre solo: `python motor_generico.py <carpeta_entrada> [<carpeta_reporte>]` (no escribe NORMALIZADO.xlsx ni LISTS.csv).
* **Resultado:** los 12 formatos con extracto real coinciden al 100 % (detección, 26 columnas, índice de fila, tipos, validación de saldos). UNION_ME: sin extracto real; solo proxy sintético.
* **Diferencias conocidas, reportadas y NO corregidas en el legado** (el genérico es más estricto o distinto): D-09 (encabezado incompleto), D-10 (cuenta dentro de una glosa), D-11 (BMSC no verifica cuenta), «Últimos 12 movimientos» (el legado lo detecta como UNION_ME), cuenta ambigua en cabecera. Los defectos D-06, D-16, D-16b, D-17 etc. el genérico los **reproduce** a propósito (siguen XFAIL).
* **Observación:** las sumas de créditos/débitos de la validación difieren ~1e-10 entre legado y genérico (orden de suma en coma flotante). Se informan como *observación* (tolerancia 1e-6, muy por debajo de la tolerancia 0.01 del motor) y no cuentan como diferencia.
* Evidencia: `tests/reports/EVIDENCIA_P3_SOMBRA.txt` (A/B contra el motor del checkpoint: LISTS.csv idéntico byte a byte, NORMALIZADO.xlsx idéntico celda a celda, componentes congelados con texto fuente idéntico).

## 5b. Siguiente paso: P3b (no iniciado)

`registro_bancos.json` con los 13 formatos actuales (`FORMATOS` + `CUENTAS`, con bloque `historico`) y `motor_generico.py` en **modo sombra**: corre en paralelo, compara contra el legado y ante cualquier diferencia falla la prueba, no la producción. La salida sigue siendo la del legado. También llena `CAMPO_CANONICO`, y `BANCO/CUENTA/MONEDA` de extractos sin movimientos.

## 6. Componentes que todavía NO deben modificarse

* `COLUMNAS_LISTS` (26 columnas, su orden y nombres) y `CLAVE TRANSACCIÓN` (fórmula).
* Todas las funciones `normalizar_*` y `finalizar_dataframe`.
* `detectar_formato`, `ENCABEZADOS_ESPERADOS`, `HOJAS_VALIDAS`, `validar_archivo`, y el control del año 2026 fijo.
* Estructura de `NORMALIZADO.xlsx` (4 hojas, `tblLISTS`) y `LISTS.csv` (UTF-8 con BOM).
* El flujo de Power Automate `NORMALIZAR EXTRACTOS DIARIOS CBBA`, Microsoft Lists y Power Apps.
* `captura_origen.py`, el paso 15 y el paso 16 (sombra) de `ejecutar_motor` (aprobados; solo cambian con nueva aprobación).
* Las doradas (`tests/golden/`) y los fixtures reales: solo se regeneran con motivo explícito y contra el motor original.
* Los archivos bancarios originales: siempre evidencia inalterada.
