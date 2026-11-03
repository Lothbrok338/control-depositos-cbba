# Historial de hitos

Cada línea es un hito cerrado; el detalle técnico está en `ESTADO_PROYECTO.md`.

- **2026-11-03** · Trazabilidad: README, CHANGELOG, `docs/` (mapa y presentación) y resumen de despliegue. App con variante sin límite de fechas (`docs/powerapps/`).
- **2026-10-09** · **P10 cerrado y validado en operación real.** Histórico mensual vivo; confirmación y reversión reflejadas en el Excel. Correcciones de la prueba real: lectura incremental atascada, fase de lista en paralelo con extractos, `createArray()` vacío inválido en Power Automate. Decisión 2027: lista permanente, P10-B cancelado.
- **2026-10-09** · P10-A.2 desplegado: `p10-api` en Railway desde `deploy/p10-api`; flujo `P10_SINCRONIZAR_HISTORICO`; lista `P10_Control`.
- **2026-10-09** · P10-A.1 cerrado: generador del histórico mensual (EXTRACTO + AUDITORIA).
- **2026-10-08** · **P0 cerrado y validado en tenant real** (BCP 2331 y BNB 1184 movimientos): entrada automática de extractos.
- **2026-10-04** · P9: reversión con aprobación validada en tenant (camino de aprobación).
- **2026-10-02** · P9: asignación desde Power Apps validada en tenant.
- **2026-10-01** · P8: carga a `Depositos_Activos` certificada de punta a punta.
- **2026-09-30** · Motor bancario y registro de bancos (P1–P6) y puente a Microsoft 365 (P7).
