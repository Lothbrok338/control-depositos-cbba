# HOJA DE RUTA — CONTROL DE DEPÓSITOS CBBA

Actualizada: 2026-10-08. Estado detallado por módulo: [`ESTADO_PROYECTO.md`](ESTADO_PROYECTO.md).

## Cerrado

| Módulo | Estado | Notas |
|---|---|---|
| Motor bancario + registro (P1–P6) | Cerrado | `checkpoint-p6`; normalización productiva por `registro_bancos.json` |
| **P7** Puente a Microsoft 365 | Cerrado | `adaptador_m365.py` → JSON `DEPOSITOS_ACTIVOS__*.json` |
| **P8** Carga a `Depositos_Activos` | Cerrado | V5 en tenant escucha `CARGA_EXTRACTOS_BANCARIOS`; duplicados por `CLAVE_TRANSACCION` |
| **P9** Asignación / confirmación / reversión (Power Apps) | Validado en tenant (ver `ESTADO_P9_REVERSION_VALIDADO_TENANT.md`) | Fuera del alcance de este cierre |
| **P10-A.1** Generador del histórico mensual (EXTRACTO + AUDITORIA) | **CERRADO Y VALIDADO LOCALMENTE (2026-10-09)** | Paquete `p10/`; contrato aprobado por Gabriel (28 columnas en AUDITORIA, sin paneles inmovilizados). Validado con extractos reales y snapshot simulado; **sin validación en tenant** (eso es P10-A.2). No se modifica sin aprobación explícita |
| **P0** Entrada automática de extractos (cloud) | **CERRADO Y VALIDADO EN TENANT REAL (2026-10-08)** | Flujo `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD` (V5) + API `p0-api` en Railway. Validado con BCP (2331 mov.) y BNB (1184 mov.). Originales en `PROCESADOS/YYYY/MM_MES/DD/` (creada hasta 31/12/2028) |

**P0, P7, P8, la API y el motor quedan cerrados para esta etapa**: solo cambian con aprobación explícita (huellas en `p0/flujo/huellas_protegidas.json`, verificadas por `tests/test_36_flujo_p0_cloud.py`).

## Próximos módulos (en este orden)

1. **P10 — HISTÓRICO / LIMPIEZA** *(en curso: A.1 cerrado; A.2 = sincronización automática; B = limpieza de `Depositos_Activos`)*. Genera y archiva los históricos normalizados (capa 4, `historico.py`, hoy sin integrar al flujo automático) y define la limpieza/retención de originales en `PROCESADOS`/`ERROR` y de los JSON de `CARGA_EXTRACTOS_BANCARIOS`. No modifica P0, P7, P8, la API ni el motor sin aprobación.
2. **Solution nacional.** Empaquetar flujos y listas en una Solution de Power Platform para varias sedes (la API ya recibe `sede`; `p0/sedes.json`). Incluye el token de P0 como variable de entorno **secreta** (hoy es un marcador en la acción HTTP del paquete) y despliegue repetible.
3. **Plan B — normalizador offline independiente** *(último entregable)*. Ejecución local del motor sin depender de Railway ni de Power Automate, como contingencia.

## Pendientes heredados (sin prioridad nueva)

Listados en `ESTADO_PROYECTO.md` §4 (muestras reales UNION_ME, lista de valores de `ESTADO`, defectos XFAIL) y `HANDOFF_P9_CLAUDE_CODE.md` (rechazo/expiración/recuperación de reversión sin probar en tenant).
