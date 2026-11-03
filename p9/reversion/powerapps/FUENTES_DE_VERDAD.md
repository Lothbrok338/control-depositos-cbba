# Fuentes de Power Apps de reversión P9

La prueba end-to-end de aprobación fue confirmada por el usuario el 2026-10-04. Rechazo, expiración y recuperación reales permanecen pendientes. Este inventario identifica las fuentes actuales y sus antecedentes.

Hasta el checkpoint `7151fbd`, `Main_Screen.yaml` copiaba exactamente el archivo `Main_Screen_REVERSION_MODAL_CORREGIDO.yaml` entregado al usuario, quien confirmó que lo pegó en el tenant. No se reconstruyó desde el repositorio antiguo. SHA-256 original con CRLF: `4ecc67542dd1a0650975d9e6a1a268857c3947038e055502d45e4545c219f44b`; con LF de Git: `a854d9b4d36a1bb2df473814c38dd7977855b1264650b9bf0c4025b3e8809b71`.

Contiene 79 controles con nombres/sufijos existentes, modal de reversión, redondeos y columnas `IMPORTE → DESCRIPCIÓN → CÓDIGO DE ASIGNACIÓN → ESTADO → DATOS DE CONFIRMACIÓN → ACCIÓN`. Su orden raíz es contenedor principal, overlay y modal. `varP9RevVisible` controla ambos últimos. La confirmación V4.2 conserva sus ocho argumentos; reversión conserva seis. Tests 32 protegen esta fuente y sus contratos sin afirmar ejecución Power Fx.

## Fuente vigente: REVERSIÓN PENDIENTE + selector de banco DropDown (validada en tenant)

La fuente vigente de `Main_Screen` es **Main_Screen.yaml**, copia byte a byte de `Main_Screen_CORREGIDO_DROPDOWN.yaml`, el archivo que el usuario pegó y validó en el tenant (confirmación del usuario, 2026-10-05). SHA-256 (LF, sin BOM): `99486d668690e425568ca18c5d6d3ff6d953fe4529e0ca0b48b0d99fd98e755a`. Rama `candidate/p9-reversion-pendiente-ux`, desde el checkpoint `7151fbd5ed802ed1d1466bd5fbd2c7c9e20cb58a`. No hay cambios de backend, flujos, ZIP, V4.2 ni PDF. Siguen los 79 controles con sus nombres.

Validado en tenant según el usuario: los bancos se muestran; BCP se puede seleccionar; CUENTA BANCARIA se habilita y muestra las cuentas de ese banco; el filtro funciona; la UX REVERSIÓN PENDIENTE sigue funcionando.

Cambios frente a `7151fbd`:

- **Verificación previa al abrir VER** sobre un depósito ASIGNADO: `P9_SOLICITAR_REVERSION` con `CONSULTAR` (los mismos seis argumentos). `PENDIENTE_EXISTENTE` fija `varP9RevActiva` y el botón muestra REVERSIÓN PENDIENTE deshabilitado, con ID, estado, fase y fecha límite en el Tooltip; `LISTO` habilita SOLICITAR REVERSIÓN; una falla técnica o cualquier otra respuesta muestra NO SE PUDO VERIFICAR deshabilitado. El backend sigue siendo la protección autoritativa contra duplicados.
- **Selector de banco `cmbBancoP9_1`**: pasa de `Classic/ComboBox@2.4.0` a `Classic/DropDown@2.3.1`, con `Items = ["(Todos)", "BNB", "BCP", "BISA", "BANCO UNIÓN", "BANCO ECONÓMICO", "BMSC"]`, `Items.Value = Value`, `Default = "(Todos)"` y colores propios. Las 9 referencias siguen siendo `cmbBancoP9_1.Selected.Value`, como en `7151fbd`. `cmbCuentaP9_1` (ComboBox con sus 13 cuentas y etiquetas) no cambió.

Motivo del DropDown: pegado en Studio, el ComboBox clásico del banco mostraba filas sin texto, tanto con `{Value}` como con `{Label, Banco}`. La hipótesis más probable (propiedad oculta `SearchItems` ligada a los datos de muestra del control cuando `IsSearchable` queda en su valor por defecto) no se comprobó en el tenant. No volver a ComboBox para este selector.

**Optimización futura (no implementada):** Durante la validación en tenant se observó una latencia aproximada de 5–10 s en algunas interacciones del flujo de reversión. La causa exacta no fue perfilada en esta fase. Se registra como deuda técnica para una optimización posterior.

Antecedentes que permanecen íntegros por trazabilidad y pruebas de la extensión inicial:

- `P9_CONTROL_INGRESOS_CON_REVERSION.txt`: contenedor extendido inicial de fase B, anterior al YAML completo actual.
- `SOLICITAR_REVERSION_PEGAR.yaml`: fragmentos iniciales; no describen el layout actual ni sus padres.
- `FORMULAS_EXACTAS.md`: catálogo canónico/regional de esos fragmentos históricos.

No usar esos tres antecedentes para reemplazar o regenerar `Main_Screen.yaml`. Tests 29 siguen verificando la extensión inicial y su contrato; tests 32 verifican la pantalla vigente.

La pantalla/comprobante PDF actual conserva sus fuentes en `p9/powerapps/COMPROBANTE_PDF.pa.yaml` y `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`, con documentación `COMPROBANTE_PDF_VALIDACION.md`. Los directorios `_referencia_comprobante`, `_base_validada_tenant*` y `p9/reversion/referencia/` son históricos. Las 36 huellas protegidas impiden modificar por accidente la base P9/PDF.
