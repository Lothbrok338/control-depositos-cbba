# Evidencia P10-A.1 · regeneración con cambios de estado · BNB_MN

Archivo: `EXTRACTO_HISTORICO_BNB_3000100152_BOB_2026-08.xlsx` · generado SOLO desde LISTS.csv + ORIGEN.xlsx de P0 y un snapshot SIMULADO de Depositos_Activos (regeneración completa; no se edita el archivo existente).

| Paso | Estado operativo | Movimientos | CONFIRMADO | DISPONIBLE | SHA-256 del libro |
|---|---|---|---|---|---|
| T0 · snapshot base | snapshot `48ca3e90c50d` | 1184 | 72 | 1112 | `7163241dd9c6d1a8…` |
| T1 · 4 DISPONIBLE → CONFIRMADO | snapshot `c31a1a03a556` | 1184 | 76 | 1108 | `13d77ad33650e7d6…` |
| T2 · 2 reversiones (payload P9) | snapshot `435a8242f173` | 1184 | 74 | 1110 | `97b1a8091711af62…` |

El nombre del archivo, el número de filas (sin duplicados), el orden de los movimientos y la zona superior son idénticos en los tres pasos.

## T0 → T1 · 4 movimientos pasan de DISPONIBLE a CONFIRMADO

* **EXTRACTO**: 13 celdas cambiaron, en 4 movimientos; columnas: CONFIRMADO POR (4), ESTADO (4), FECHA DE CONFIRMACIÓN (4), OBSERVACIONES (1); otras diferencias: 0.
* **AUDITORIA**: 25 celdas cambiaron, en 4 movimientos; columnas: CONFIRMADO POR (4), ESTADO (4), ESTUDIANTE (4), FECHA CONFIRMACIÓN (4), OBSERVACIÓN (1), SEDE SOLICITANTE (4), SOLICITADO POR (4); otras diferencias: 0.

Hoja EXTRACTO:

| Movimiento (FECHA · HORA · IMPORTE) | Columna | Antes | Después |
|---|---|---|---|
| 2026-08-20 20:37:04 · 600.00 | ESTADO | DISPONIBLE | CONFIRMADO |
| 2026-08-20 20:37:04 · 600.00 | CONFIRMADO POR |  | usuario.simulado.1@example.invalid |
| 2026-08-20 20:37:04 · 600.00 | FECHA DE CONFIRMACIÓN |  | 2026-08-22 14:02:00 |
| 2026-08-05 17:12:03 · 12,696.40 | ESTADO | DISPONIBLE | CONFIRMADO |
| 2026-08-05 17:12:03 · 12,696.40 | CONFIRMADO POR |  | usuario.simulado.2@example.invalid |
| 2026-08-05 17:12:03 · 12,696.40 | FECHA DE CONFIRMACIÓN |  | 2026-08-06 10:21:00 |
| 2026-08-18 08:37:53 · 75,398.74 | ESTADO | DISPONIBLE | CONFIRMADO |
| 2026-08-18 08:37:53 · 75,398.74 | CONFIRMADO POR |  | usuario.simulado.3@example.invalid |
| 2026-08-18 08:37:53 · 75,398.74 | FECHA DE CONFIRMACIÓN |  | 2026-08-18 10:52:00 |
| 2026-08-13 13:50:57 · 1,000.00 | ESTADO | DISPONIBLE | CONFIRMADO |
| 2026-08-13 13:50:57 · 1,000.00 | CONFIRMADO POR |  | usuario.simulado.2@example.invalid |
| 2026-08-13 13:50:57 · 1,000.00 | FECHA DE CONFIRMACIÓN |  | 2026-08-13 14:00:57 |
| 2026-08-13 13:50:57 · 1,000.00 | OBSERVACIONES |  | SIMULADO 0004521 código con ceros a la izquierda |

## T1 → T2 · 2 reversiones (una confirmada en T0 y una confirmada en T1)

* **EXTRACTO**: 6 celdas cambiaron, en 2 movimientos; columnas: CONFIRMADO POR (2), ESTADO (2), FECHA DE CONFIRMACIÓN (2); otras diferencias: 0.
* **AUDITORIA**: 12 celdas cambiaron, en 2 movimientos; columnas: CONFIRMADO POR (2), ESTADO (2), ESTUDIANTE (2), FECHA CONFIRMACIÓN (2), SEDE SOLICITANTE (2), SOLICITADO POR (2); otras diferencias: 0.

Hoja EXTRACTO:

| Movimiento (FECHA · HORA · IMPORTE) | Columna | Antes | Después |
|---|---|---|---|
| 2026-08-12 11:32:15 · 30,000.00 | ESTADO | CONFIRMADO | DISPONIBLE |
| 2026-08-12 11:32:15 · 30,000.00 | CONFIRMADO POR | usuario.simulado.1@example.invalid |  |
| 2026-08-12 11:32:15 · 30,000.00 | FECHA DE CONFIRMACIÓN | 2026-08-13 13:26:00 |  |
| 2026-08-20 20:37:04 · 600.00 | ESTADO | CONFIRMADO | DISPONIBLE |
| 2026-08-20 20:37:04 · 600.00 | CONFIRMADO POR | usuario.simulado.1@example.invalid |  |
| 2026-08-20 20:37:04 · 600.00 | FECHA DE CONFIRMACIÓN | 2026-08-22 14:02:00 |  |

## Reconstrucción y determinismo

* Regenerar T1 por segunda vez: mismos bytes = **True**, diferencias lógicas = 0.
* Confirmar 3 movimientos y revertirlos produce el mismo contenido lógico que T0: diferencias = **0**.
* T0 → T2: solo difieren 4 movimientos (3 confirmados en T1 que siguen confirmados + 1 confirmado en T0 que se revirtió); el movimiento confirmado en T1 y revertido en T2 vuelve a ser idéntico a T0.

Los campos `ULTIMA_REVERSION_ID` y `CODIGO_ESTUDIANTE` existen en el snapshot pero no se proyectan a ninguna hoja (no tienen columna en las 26 de P0).
