# Fuentes de Power Apps de reversión P9

La prueba end-to-end de aprobación fue confirmada por el usuario el 2026-10-04. Rechazo, expiración y recuperación reales permanecen pendientes. Este inventario identifica las fuentes actuales y sus antecedentes.

La fuente vigente de `Main_Screen` es **Main_Screen.yaml**. Copia exactamente el archivo `Main_Screen_REVERSION_MODAL_CORREGIDO.yaml` entregado al usuario, quien confirmó que lo pegó en el tenant. No se reconstruyó desde el repositorio antiguo. SHA-256 original con CRLF: `4ecc67542dd1a0650975d9e6a1a268857c3947038e055502d45e4545c219f44b`; con LF de Git: `a854d9b4d36a1bb2df473814c38dd7977855b1264650b9bf0c4025b3e8809b71`.

Contiene 79 controles con nombres/sufijos existentes, modal de reversión, redondeos y columnas `IMPORTE → DESCRIPCIÓN → CÓDIGO DE ASIGNACIÓN → ESTADO → DATOS DE CONFIRMACIÓN → ACCIÓN`. Su orden raíz es contenedor principal, overlay y modal. `varP9RevVisible` controla ambos últimos. La confirmación V4.2 conserva sus ocho argumentos; reversión conserva seis. Tests 32 protegen esta fuente y sus contratos sin afirmar ejecución Power Fx.

Antecedentes que permanecen íntegros por trazabilidad y pruebas de la extensión inicial:

- `P9_CONTROL_INGRESOS_CON_REVERSION.txt`: contenedor extendido inicial de fase B, anterior al YAML completo actual.
- `SOLICITAR_REVERSION_PEGAR.yaml`: fragmentos iniciales; no describen el layout actual ni sus padres.
- `FORMULAS_EXACTAS.md`: catálogo canónico/regional de esos fragmentos históricos.

No usar esos tres antecedentes para reemplazar o regenerar `Main_Screen.yaml`. Tests 29 siguen verificando la extensión inicial y su contrato; tests 32 verifican la pantalla vigente.

La pantalla/comprobante PDF actual conserva sus fuentes en `p9/powerapps/COMPROBANTE_PDF.pa.yaml` y `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`, con documentación `COMPROBANTE_PDF_VALIDACION.md`. Los directorios `_referencia_comprobante`, `_base_validada_tenant*` y `p9/reversion/referencia/` son históricos. Las 36 huellas protegidas impiden modificar por accidente la base P9/PDF.
