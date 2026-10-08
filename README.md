# CONTROL DE DEPÓSITOS CBBA · módulo de normalización

Estado y decisiones: `ESTADO_PROYECTO.md` · Hoja de ruta: `ROADMAP.md` · Diseño: `DISENO_TRES_CAPAS.md` · Matriz de campos: `MATRIZ_CAMPOS_ORIGEN.csv`.

**Estado actual (2026-10-08): P0 CERRADO Y VALIDADO EN TENANT REAL.** El flujo `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD` (OneDrive for Business `OnNewFilesV2` + Split On, concurrencia 1) envía cada extracto de `ENTRADA` a la API `p0-api` en Railway, guarda el JSON P7 en `CARGA_EXTRACTOS_BANCARIOS` (lo carga P8 V5) y archiva el original en `PROCESADOS/YYYY/MM_MES/DD/`. Validado con extractos reales BCP (2331 movimientos) y BNB (1184). P0, P7, P8, la API y el motor están cerrados para esta etapa. Siguiente: **P10 Histórico / Limpieza** → Solution nacional → Plan B (normalizador offline). Ver `P0_AUTOMATIZACION_EXTRACTOS.md` y `p0/flujo/INSTRUCCIONES_IMPORTACION.md`.

## Ejecutar las pruebas
```
pip install -r tests/requirements-test.txt
python -m pytest tests -q          # esperado: 620 passed, 23 skipped, 14 xfailed (575 de P6 + 45 de P7)
python tests/informe.py            # regenera tests/reports/INFORME_PRUEBAS.md
```
Comparación contra el checkpoint P5 (evidencia P6): `git worktree add <carpeta> checkpoint-p5` y `cd tests && python evidencia_p6_retiro.py <carpeta>`.

## Ejecutar el motor
```
python motor_control_depositos_cbba.py <carpeta_entrada> <ruta>/NORMALIZADO.xlsx
```
Genera `NORMALIZADO.xlsx`, `LISTS.csv` (**desde P5 normalizados por `motor_generico.py` + `registro_bancos.json`**) y `ORIGEN.xlsx` (captura íntegra de origen, `captura_origen.py`). **Junto al motor deben estar `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json` y `captura_origen.py`.**

## Detección por registro (P4)
Banco, cuenta, moneda y formato se identifican con `registro_bancos.json` a través de `deteccion_registro.py`: **ambos deben estar junto a `motor_control_depositos_cbba.py`** (o `CBBA_REGISTRO_BANCOS=<ruta>` para otro registro). La cuenta se lee solo en la celda rotulada de la cabecera y debe estar registrada; encabezado incompleto, cabecera ambigua, cuenta no registrada o el reporte Unión «Últimos 12» detienen el proceso con el motivo. **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`** (id único, formato, banco, cuenta tal como figura en la cabecera, moneda).

## Normalización por registro (P5)
`archivo → detección por registro → normalización genérica → salida productiva`. `motor_generico.py` normaliza a las 26 `COLUMNAS_LISTS` y valida saldos solo con `registro_bancos.json`; `CLAVE TRANSACCIÓN` sigue saliendo de `crear_clave` (congelada). **Cuenta nueva de un formato conocido = una entrada en `CUENTAS`**: se normaliza sin código, sin `normalizar_*` propio y sin plantilla legada. Sin `motor_generico.py` o con un registro que no sirve para normalizar, el proceso se detiene antes de escribir.

## Retiro del legado (P6 · checkpoint `checkpoint-p6`)
**Checkpoint P6 (rama remota `checkpoint-p6` = `main` al cerrar P6), vigente desde el checkpoint:**
1. **P6 es el primer checkpoint sin motor legado ni sombra**: no existen `normalizar_*` por banco, `validar_archivo`, `HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `encontrar_fila_encabezado`, `leer_tabla_movimientos`, `aplicar_identidad_registro`, el paso 16 ni el comparador de `motor_generico.py`.
2. **P5 (`checkpoint-p5`, `0b182e2`) es el último checkpoint capaz de ejecutar la comparación contra el legado** (referencia en sombra, `evidencia_p5_extra.py`, `generar_golden.py`). Para comparar contra el legado: `git worktree add <carpeta> checkpoint-p5`.
3. **Las doradas actuales (`tests/golden/`, generadas con el motor original) siguen siendo la referencia de regresión histórica**; no se regeneraron en P6 y solo se regeneran con motivo explícito y contra el motor original (checkpoint ≤ P5).
4. **`CBBA_MOTOR_SOMBRA` queda obsoleto y sin efecto**: el motor ya no lo lee; definirlo no cambia nada.
5. **Los artefactos `SOMBRA_REPORTE.json` / `SOMBRA_DIFERENCIAS.csv` de corridas anteriores pueden eliminarse**: no forman parte del runtime, ya no se generan ni se actualizan, y `descubrir_archivos` no los toma como extractos.
6. **Archivos productivos requeridos (únicos)**: `motor_control_depositos_cbba.py`, `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json`, `captura_origen.py`; más `historico.py` solo para la capa 4 (EXTRACTO_HISTORICO).

Los `normalizar_*` por banco, `normalizar_archivo`, `validar_archivo`, `HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `encontrar_fila_encabezado`, `leer_tabla_movimientos`, `texto_de_archivo`, `aplicar_identidad_registro`, la referencia en sombra (paso 16, `SOMBRA_REPORTE.json` / `SOMBRA_DIFERENCIAS.csv`, `CBBA_MOTOR_SOMBRA`, clave `sombra_estado` del retorno), la detección propia de P3 y el modo script de `motor_generico.py` se retiraron. Hojas, encabezados, campos y saldos viven solo en `registro_bancos.json`. Las primitivas compartidas (números, fechas, horas, códigos, texto, lector de Excel, `buscar_columna*`, `extraer_nombre_bnb`, `ecuacion_saldo`, `crear_clave` / `finalizar_dataframe`, `COLUMNAS_LISTS`) siguen en `motor_control_depositos_cbba.py`, sin cambios. Archivos productivos: `motor_control_depositos_cbba.py`, `deteccion_registro.py`, `motor_generico.py`, `registro_bancos.json`, `captura_origen.py` (+ `historico.py` para la capa 4). Si una carpeta de salida conserva `SOMBRA_*` de corridas P3-P5, ya no se actualizan: se pueden borrar.

## Puente Microsoft 365 (P7 · checkpoint `checkpoint-p7`)
```
python adaptador_m365.py <salida>/LISTS.csv <carpeta_m365>      # genera DEPOSITOS_ACTIVOS__<lote>.json + MANIFIESTO_P7__<lote>.json
```
Capa **separada** del motor (solo biblioteca estándar; no modifica `LISTS.csv` ni ninguna salida de P6). El JSON alimenta la Microsoft List `Depositos_Activos` mediante el flujo `P7 - CARGA DEPOSITOS ACTIVOS`; la `CLAVE TRANSACCIÓN` de P6 evita duplicados (`NUEVO` / `YA_EXISTE` / `ERROR`). **Checkpoint P7 (rama remota `checkpoint-p7` = `main` al cerrar P7).** **Alcance: P7 valida localmente el puente P6 → artefacto M365 y NO certifica la integración end-to-end con SharePoint / Power Automate** (pendiente del piloto en un tenant de Microsoft 365). Antes de leer nada, el adaptador comprueba (fail-fast) que el contrato de columnas coincide exactamente con las 26 `COLUMNAS_LISTS` de P6; si no, se detiene con `ERROR de contrato`. Bitácora de lotes: lista `Depositos_Cargas`. Diseño de la lista: `DISENO_LISTA_DEPOSITOS_ACTIVOS.md` · flujo: `ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md` · ejemplo real: `ejemplos_p7/` · pruebas: `tests/test_11_adaptador_m365_p7.py`.

## Entrada automática de extractos (P0 · cerrado y validado en tenant)
```
P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V5.zip     # flujo importable de Power Automate (OneDrive for Business)
python -m p0.flujo.construir                  # regenera definición + ZIP del flujo
cd tests && python -m pytest test_36_flujo_p0_cloud.py -q     # validación estática del flujo y de las huellas de P8/P7/API/motor
uvicorn p0.api:app                            # API local (en producción: Railway, Dockerfile + railway.json)
```
API sin estado (`p0/api.py`, `p0/nucleo.py`): `GET /health` y `POST /procesar-extracto`, autenticada con `Authorization: Bearer <P0_API_TOKEN>` (el token nunca se versiona). Contrato, despliegue y flujo: `P0_AUTOMATIZACION_EXTRACTOS.md`.

## Extracto histórico para Contabilidad / Ingresos (P3b, capa 4)
```
python historico.py <salida>/ORIGEN.xlsx <salida>/NORMALIZADO.xlsx <carpeta_historicos>   # o LISTS.csv
```
Un `EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{AAAA-MM}.xlsx` por cuenta y mes, hoja única `EXTRACTO`, columnas propias de cada banco + `ESTADO`, `CONFIRMADO POR`, `FECHA DE CONFIRMACIÓN`. Se arma solo con ORIGEN + NORMALIZADO + `registro_bancos.json` (no relee el banco) y no modifica ninguna salida del motor.

> Los extractos de `tests/fixtures/` (y `ORIGEN_EJEMPLO.xlsx`) son datos bancarios reales: mantener el repositorio **privado**. Si el repositorio es público, esos archivos (y su historial) quedan expuestos.
