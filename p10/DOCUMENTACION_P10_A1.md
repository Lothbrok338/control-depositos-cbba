# P10-A.1 · Generador histórico mensual (EXTRACTO + AUDITORIA)

> **ESTADO: CERRADO Y VALIDADO LOCALMENTE (2026-10-09).** Contrato aprobado por Gabriel; no se modifica sin aprobación explícita. La sincronización automática con el tenant es **P10-A.2** (`p10/DOCUMENTACION_P10_A2.md`).

Rama `experiment/p9-masiva-prototipo`. **Alcance de esta fase: solo el generador.** No hay flujos de Power Automate P10, triggers, `P10_Extractos` en el tenant, sincronización de 15 minutos, limpieza de Lists, P10-B ni cambios en Railway. El estado operativo (`Depositos_Activos`) se **simula** con nombres de campo reales; todo lo demás sale del motor P0 sobre los 12 extractos bancarios reales de `tests/fixtures/extractos`.

## 1. Qué hace

```
extractos reales ──► P0: ejecutar_motor() ──► LISTS.csv (26 columnas) + ORIGEN.xlsx
                                                  │
snapshot operativo (≙ Depositos_Activos) ─────────┤   cruce por CLAVE TRANSACCIÓN
                                                  ▼
               un .xlsx por BANCO + CUENTA + MONEDA + MES, regenerado COMPLETO cada vez
               ├─ EXTRACTO   diseño aprobado de la capa 4 (historico.py) + OBSERVACIONES
               └─ AUDITORIA  las 26 COLUMNAS_LISTS + 2 columnas reales de Depositos_Activos, mismo orden de filas que EXTRACTO
```

Nombre: `EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{MONEDA}_{AAAA-MM}.xlsx` (p. ej. `EXTRACTO_HISTORICO_BNB_3000100152_BOB_2026-08.xlsx`). Mes = mes de `FECHA MOVIMIENTO`. Cuenta sin movimientos en el mes → no genera archivo (BISA ME hoy).

Regeneración completa: `extracto acumulado más reciente (LISTS.csv + ORIGEN.xlsx) + snapshot actual → libro mensual`. No se edita el archivo existente fila por fila; por eso es determinista y no puede duplicar movimientos.

## 2. Qué se reutiliza (y qué NO se duplicó)

| Pieza | De dónde | Cambios |
|---|---|---|
| Normalización, `CLAVE TRANSACCIÓN`, importes, débitos, créditos, saldos, validación de saldos | `motor_control_depositos_cbba.ejecutar_motor` (P0) vía `p10/motor_p0.py` | **Ninguno.** P10 no define `crear_clave`, `valor_clave_numero`, `finalizar_dataframe` ni ningún normalizador; no importa `motor_generico`, `deteccion_registro` ni `captura_origen`. |
| Las 26 columnas y su orden | `motor_control_depositos_cbba.COLUMNAS_LISTS` (el mismo objeto) | Ninguno |
| Columnas propias de cada banco, zona superior, formatos, tabla, filtros, verificación de saldos declarados | `historico.construir_extractos_historicos` / `escribir_extracto_historico` (P3b) | **Ninguno** (el archivo `historico.py` está congelado por las huellas de P9: no se tocó). |
| Estados y reversión | `p9.contrato` (`ESTADOS`, `CAMPO_ESTADO`) y `p9.reversion.contrato` (`CAMPOS_LIMPIAR`, `payload_reversion`) | Ninguno |

Como `historico.py` solo escribe una hoja, P10 escribe la hoja EXTRACTO con ese mismo escritor, **reabre el archivo** (se comprobó sin pérdida: valores, formatos, anchos, columna oculta, tabla, títulos de impresión; los paneles se quitan a propósito) y agrega AUDITORIA. Lo único que P10 añade a la hoja aprobada: la 4.ª columna operativa `OBSERVACIONES` y el ancho de `CONFIRMADO POR` (22 → 34, porque guarda el correo completo).

## 3. Contenido del libro

**EXTRACTO**: título, zona superior de la cuenta/período (según el banco), tabla `tblEXTRACTO` con las columnas propias del banco en su orden y nombre, y al final `ESTADO · CONFIRMADO POR · FECHA DE CONFIRMACIÓN · OBSERVACIONES`; `CLAVE TRANSACCIÓN` en una columna oculta de la misma tabla (vínculo técnico). Filtros, fechas `dd/mm/aaaa`, horas reales, importes y saldos numéricos, referencias/códigos como texto con ceros iniciales, textos completos.

**AUDITORIA**: tabla `tblAUDITORIA` con **28 columnas**: las 26 de `COLUMNAS_LISTS` en su orden exacto + `CODIGO_ESTUDIANTE` y `ULTIMA_REVERSION_ID` (columnas reales de `Depositos_Activos` sin equivalente en P0, con su nombre interno de la lista); sin columnas técnicas de P10. Justificación y clasificación completa de las 35 columnas reales: `CONTRATO_AUDITORIA_DEPOSITOS_ACTIVOS.md`. Tipos: códigos/cuentas/lote como texto; `FECHA MOVIMIENTO`, `FECHA CONFIRMACIÓN` y `FECHA DE CARGA` como fecha; `IMPORTE/DÉBITO/CRÉDITO/SALDO` numéricos; `HORA MOVIMIENTO` como texto `HH:MM:SS` (así la guarda `Depositos_Activos`). Los textos se conservan EXACTOS (sin recortar espacios), a diferencia de EXTRACTO que recorta los espacios de relleno del banco.

Exactamente dos hojas, ambas visibles. **Sin paneles inmovilizados en ninguna hoja** (desplazamiento libre, decisión de Gabriel): se quitan al reabrir la hoja EXTRACTO de `historico.py` (que sigue sin modificarse) y no se crean en AUDITORIA; el resto del diseño no cambia.

## 4. Snapshot operativo (≙ `Depositos_Activos`)

Formato (`p10/snapshot.py`), indexado por `CLAVE_TRANSACCION` con los **nombres internos reales** de P8/P9, de modo que la lectura real de la lista cabe sin cambios:

| Campo de `Depositos_Activos` | Columna que alimenta |
|---|---|
| `ESTADO_ASIGNACION` (`DISPONIBLE` / `ASIGNADO`) | `ESTADO` (visible: `DISPONIBLE` / `CONFIRMADO`) |
| `ESTUDIANTE` | `ESTUDIANTE` |
| `SOLICITADO_POR` | `SOLICITADO POR` |
| `SEDE_ASIGNACION` | `SEDE SOLICITANTE` |
| `USUARIO_ASIGNACION` | `CONFIRMADO POR` |
| `FECHA_HORA_ASIGNACION` | `FECHA CONFIRMACIÓN` / `FECHA DE CONFIRMACIÓN` |
| `OBSERVACION` | `OBSERVACIÓN` / `OBSERVACIONES` |
| `CODIGO_ESTUDIANTE` | `CODIGO_ESTUDIANTE` — solo AUDITORIA, al final |
| `ULTIMA_REVERSION_ID` | `ULTIMA_REVERSION_ID` — solo AUDITORIA, al final |

Reglas: clave obligatoria y única (comparación exacta); estado ∈ estados vigentes de P9; fecha ISO **sin** zona horaria (con zona se rechaza). Un movimiento sin fila en el snapshot conserva lo que entrega P0 y se cuenta en el manifiesto (`sin_fila_en_snapshot`); filas del snapshot que no pertenecen al extracto se cuentan aparte (`snapshot_fuera_del_extracto`). ASIGNADO incompleto o DISPONIBLE con datos residuales → advertencia, no bloqueo.

**Lo simulado** (`p10/snapshot_simulado.py`, determinista por CLAVE + semilla): únicamente los campos operativos de arriba (incluidos `CODIGO_ESTUDIANTE` y `ULTIMA_REVERSION_ID`). El snapshot base trae además historia de reversiones realista: ~2 % de los créditos revertidos que vuelven a DISPONIBLE conservando el marcador, y 1 de cada 8 confirmados re-confirmado tras una reversión previa (P9 nunca borra `ULTIMA_REVERSION_ID`). ~12 % de los **créditos** nacen CONFIRMADOS (la app solo confirma créditos) con datos reconocibles como simulados (`ESTUDIANTE SIMULADO 0037`, `usuario.simulado.2@example.invalid`, observaciones `SIMULADO …`); algunas observaciones ejercitan acentos, `=` inicial (no debe ser fórmula), salto de línea y ceros iniciales. Movimientos, claves, importes, saldos, fechas y textos del banco **no** se simulan. La reversión usa el payload real de P9 (`payload_reversion`).

## 5. Validación antes de aceptar cada archivo

`p10/validacion.py` reabre el `.xlsx` recién escrito y lo compara contra las **fuentes** (LISTS.csv de P0, ORIGEN.xlsx de P0, snapshot). Si algo falla, el archivo **no se acepta**: no se escribe ni reemplaza el existente, y queda en `omitidos` con las causas.

Dos hojas visibles exactas · AUDITORIA = las 26 de P0 en orden + `CODIGO_ESTUDIANTE` y `ULTIMA_REVERSION_ID` (cada valor contra el snapshot) · ninguna `CLAVE` duplicada · cantidad de movimientos = P0 para esa cuenta-mes · `IMPORTE`, `DÉBITO`, `CRÉDITO`, `SALDO`, fechas, horas y las 19 columnas no operativas **iguales a P0** (exactas) · totales de créditos/débitos · estados y campos operativos cruzados por CLAVE en AUDITORIA y en EXTRACTO · cada columna propia del banco = su texto en `ORIGEN.xlsx` (importes numéricos; códigos como texto con formato `@`) · tablas con filtros y **sin paneles inmovilizados** en ninguna hoja · `CLAVE` oculta · saldos declarados por el banco (verificación de `historico.py`, previa a escribir).

## 6. Determinismo

Mismas entradas → **mismos bytes** (marcas de tiempo del contenedor ZIP y propiedades `created/modified` fijadas; `created/modified` = `fecha_corte` del snapshot). Lo único que cambia entre dos corridas **de P0** son `LOTE DE CARGA` y `FECHA DE CARGA`, que P0 fija con la hora de su ejecución (comportamiento previo de P0, no modificado). Cambiar el snapshot cambia solo los campos operativos de las claves afectadas (probado con DISPONIBLE → CONFIRMADO y con reversiones). Evidencia con datos reales: `entrega_a1/EVIDENCIA_ESCENARIOS_BNB_MN.md`.

## 7. Cómo ejecutar

```
# pipeline completo (P0 real sobre los extractos + snapshot simulado + libros + ZIP determinista)
python -m p10.generar_a1 --entrada tests/fixtures/extractos --trabajo <dir_p0> --salida <dir_xlsx> --zip <entrega.zip> [--solo BNB_MN]
# evidencia de escenarios (T0 → T1 confirmar → T2 revertir) sobre la salida de P0 de una corrida
python -m p10.evidencia_a1 --trabajo <dir_p0> --salida <dir>
# pruebas
python -m pytest tests/test_33_p10_a1_generador.py -q
```

## 8. Decisiones tomadas (cambiar una = una constante o una línea)

| # | Decisión | Confianza | Alternativa |
|---|---|---|---|
| 1 | `ASIGNADO` se muestra **CONFIRMADO** en ambas hojas (como la app de Power Apps y como pediste) | Alta | Mostrar `ASIGNADO` crudo en AUDITORIA (`ESTADO_VISIBLE` en `p10/contrato.py`) |
| 2 | Un DISPONIBLE con fila en el snapshot muestra `SEDE SOLICITANTE` **vacía** (`SEDE_ASIGNACION` es null en la lista; `MOTOR_SEDE_SOLICITANTE='COCHABAMBA'` es una constante reservada de P0) | Media | Mostrar `COCHABAMBA` también en DISPONIBLE |
| 3 | **(resuelta en la revisión de contrato)** AUDITORIA = 26 de P0 + `CODIGO_ESTUDIANTE` + `ULTIMA_REVERSION_ID`, las 2 columnas reales de la lista sin equivalente en P0 | Alta (esquema del repo + captura del tenant) | — |
| 4 | `FECHA DE CARGA` y `FECHA CONFIRMACIÓN` se guardan a segundos | Alta | — |
| 5 | Nombre de archivo con `MONEDA` (como tu ejemplo; P3b la había omitido) | Alta | — |
| 6 | Ancho de `CONFIRMADO POR` 22 → 34 en EXTRACTO | Alta | Quitarlo |
| 7 | Fecha con zona horaria en el snapshot → **se rechaza** (no se adivina) | Alta | Definir la conversión en A.2 |
| 8 | Sin paneles inmovilizados en EXTRACTO ni AUDITORIA | Decisión de Gabriel | — |
| 9 | Columnas de sistema de SharePoint (`ID`, `Creado`, `Modificado`, …) **no** se incluyen | Media | Agregar solo `ID` al final de AUDITORIA (ver `CONTRATO_AUDITORIA_DEPOSITOS_ACTIVOS.md` §5) |

## 9. Pendiente / no cubierto por esta fase

* **Muestra real requerida:** UNION ME con movimientos (sin fixture), BISA ME con movimientos (el fixture está vacío), débitos reales de BMSC, BISA, Unión, BNB Ahorro/Clínica y ECO Ahorro (sus fixtures no traen débitos), BMSC con planilla en «Reporte de Pagos», BNB con ITF ≠ 0, un mes repartido en más de un extracto de la misma cuenta.
* **Excel Online:** la compatibilidad de archivos generados con openpyxl con Office Scripts/Excel Online sigue sin probarse (prueba manual 12 del diseño §6.10). Los archivos abren y convierten sin error en LibreOffice; no se probaron en Excel de escritorio ni en línea.
* **Tenant:** lectura real de `Depositos_Activos` (zona horaria de `FECHA_HORA_ASIGNACION`, paginación, umbral de 5 000), estado JSON, servicio P10 y sincronización → **P10-A.2**.
* El libro actual no muestra cuándo se tomó el snapshot (queda en las propiedades del archivo y en el manifiesto); se puede agregar una línea en la zona superior si se aprueba.

## 10. Archivos

`p10/CONTRATO_AUDITORIA_DEPOSITOS_ACTIVOS.md` (clasificación del esquema real). `p10/`: `contrato.py`, `snapshot.py`, `snapshot_simulado.py`, `motor_p0.py`, `generador.py`, `validacion.py`, `comparar.py`, `empaque.py`, `generar_a1.py`, `evidencia_a1.py`. Pruebas: `tests/test_33_p10_a1_generador.py` (marcador `p10`). Entrega de revisión visual: `p10/entrega_a1/`.
