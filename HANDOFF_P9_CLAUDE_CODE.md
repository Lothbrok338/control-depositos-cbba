# Handoff — P9 reversión de confirmación

Validación real de **aprobación** completada el 2026-10-04, confirmada expresamente por el usuario: creación, Approval, decisión, DISPONIBLE, siete campos limpios, código/clave conservados, marcador, historial/trazabilidad y sin duplicados observados. Autorizó commit/push únicamente de `candidate/p9-reversion`. **Rechazo no probado en tenant**; expiración/recuperación reales sin evidencia de ejecución. No se aportaron UID/IDs exactos: no inventarlos. La evidencia tenant es la confirmación humana, no un export de ejecución auditado por el agente.

## ESTADO EXACTO PARA CONTINUAR

- REPO: `https://github.com/Lothbrok338/control-depositos-cbba`.
- RAMA: `candidate/p9-reversion`.
- HEAD SHA de cierre: revisión Git que contiene este handoff; resolver con `git log -1 --format=%H -- HANDOFF_P9_CLAUDE_CODE.md` y contrastar con HEAD/upstream. El SHA literal y status post-push están en el reporte/prompt y la copia final exportada. No insertar un SHA previo como si identificara el commit que contiene este documento.
- UPSTREAM: `origin/candidate/p9-reversion`; exigir HEAD=remoto al continuar. HEAD verificado antes del cierre: `1feeeb9157c1c677e523ce39c5c1ac5ebeb39871`, ahead/behind 0/0 tras fetch.
- BASE RELEVANTE anterior a reversión: `d08454f7636a49a5711006cd900d79b32bf9c13b`, `candidate/p9-pdf-confirmacion`.
- MAIN remoto comprobado: `673754a9b69072e6960bbf0c7ffb0f50dc5d2670`; antes del cierre, rama 14 commits por delante y 0 por detrás. No hacer merge a main; medir divergencia actual.
- GIT STATUS: la entrega exige árbol limpio y HEAD=upstream. El inventario precommit está en `p9/reversion/evidencias/CIERRE_FINAL.json`; la copia de entrega incluye status post-push. Verificar Git nuevamente antes de trabajar.
- TESTS: resultados exactos actuales y baseline en `p9/reversion/evidencias/INFORME_CIERRE_FINAL.md`. `INFORME_PRUEBAS.md` conserva resultados históricos de fase B.
- FUENTES DE VERDAD: `p9/reversion/powerapps/Main_Screen.yaml` para Main_Screen; builders, contrato, esquema, definitions y ZIP genéricos actuales para backend. PDF en `p9/powerapps/COMPROBANTE_PDF.pa.yaml` y `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`.
- ARTEFACTOS VALIDADOS: JSON/ZIP cotejados con builders; cinco genéricos y cuatro copias configuradas; SHA-256 en el manifiesto de cierre final.
- TENANT VALIDADO: provisión OK, CONSULTAR LISTO y aprobación end-to-end correcta el 2026-10-04, según el usuario; marcador comprobado. Rechazo no probado. No dar por ejecutados casos negativos por sus pruebas locales.
- PENDIENTES: rechazo/expiración/recuperación reales, UID/IDs de ejecución no aportados y metadatos de despliegue sin export. Confirmación masiva es futura y no se implementó. La autorización de este cierre no cubre futuros commits/push automáticos.

El SHA `1feeeb9...` contiene fase B inicial y no incluye por sí solo esta corrección o pantalla completa. Continuar desde el commit de cierre indicado en la entrega y verificar remoto; no reconstruir desde aquella revisión.

## Qué es P9 y qué existe

P9 presenta depósitos bancarios en Power Apps, permite confirmarlos mediante V4.2, consulta la confirmación y genera un comprobante imprimible Carta de 816×1056. La reversión es una solicitud separada con aprobación e historial; nunca es un Patch directo de Power Apps al depósito.

Flujos: `P9_SOLICITAR_REVERSION`, `P9_RESOLVER_REVERSION`, `P9_EXPIRAR_REVERSIONES`, `P9_RECUPERAR_REVERSION`. `P9_PROVISIONAR_REVERSION` crea/verifica estructura y no ejecuta reversión de negocio.

`p9/reversion/construir.py` configura y genera; `flujos.py` define negocio; `wdl.py` construye expresiones y transporte; `provisionar.py` compila el esquema; `paquete.py` genera los sobres ZIP; `validar.py` valida definición/paquete; `ensayo.py` simula conectores locales. El esquema es `esquema_reversiones.json`, con invariantes en `contrato.py`.

## Fuentes actuales y antecedentes

Leer primero este documento, `ESTADO_P9_REVERSION_VALIDADO_TENANT.md`, `DOCUMENTACION_P9_REVERSION.md`, `DESPLIEGUE_P9_REVERSION.md` y `p9/reversion/powerapps/FUENTES_DE_VERDAD.md`.

`Main_Screen.yaml` es la copia del último YAML completo entregado y pegado por el usuario. SHA original CRLF `4ecc67542dd1a0650975d9e6a1a268857c3947038e055502d45e4545c219f44b`; LF `a854d9b4d36a1bb2df473814c38dd7977855b1264650b9bf0c4025b3e8809b71`. Mantiene 79 controles, nombres/sufijos existentes, redondeos y columnas IMPORTE → DESCRIPCIÓN → CÓDIGO DE ASIGNACIÓN → ESTADO → DATOS DE CONFIRMACIÓN → ACCIÓN. Orden raíz: contenedor principal → overlay → modal. Ambos últimos dependen de `varP9RevVisible`.

Los fragmentos `SOLICITAR_REVERSION_PEGAR.yaml`, `P9_CONTROL_INGRESOS_CON_REVERSION.txt` y su catálogo `FORMULAS_EXACTAS.md` representan la extensión inicial de fase B y permanecen como antecedentes. No reconstruir la pantalla vigente desde ellos. Tests 29 protegen ese contrato histórico; tests 32 protegen la pantalla actual. `p9/reversion/referencia/` conserva un ZIP inicial aportado y sus JSON: nunca importar sus conexiones, listas o lógica.

La base de confirmación V4.2, filtros, PDF, comprobante y motor están protegidos por 36 huellas de `p9/reversion/evidencias/huellas_base.json`. No ejecutar generadores históricos en el checkout real para intentar resolver diferencias binarias de Windows.

## Tenant y conexiones

Sitio reportado: `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`.

Listas: `Depositos_Activos` (`296c450a-25d6-415b-ad10-c909c74817cb`) y `Depositos_Reversiones` (`45ff53dc-fee7-4b7c-81cb-a226f09ba0f2`). Provisión reportada `PROVISION_P9_REVERSION=OK`, `diferencias=[]`; lista de historial verificada visualmente por el usuario.

Aprobadores iniciales: `gtorricot@univalle.edu`, `lvelasquezs@univalle.edu`. Responsable de recuperación: Gabriel Torricot, `gtorricot@univalle.edu`; Object ID verificado por el usuario mediante Office 365 Users → Get my profile (V2): `0b598a5a-e435-4696-8de2-933abbc2b265`.

La configuración JSON real y los ZIP configurados se mantienen fuera de Git. En el workspace original: `outputs/tenant-univalle-p9-reversion/configuracion-reversion.json`; copias corregidas vigentes: `outputs/correccion-cuerpos-http-p9/tenant/`. Los paquetes previos en `outputs/tenant-univalle-p9-reversion/` anteceden al fix REST y son históricos. Los ZIP versionables de la raíz del repo son genéricos.

SOLICITAR usa SharePoint de servicio y Office 365 Users del invocador. RESOLVER usa SharePoint y Standard Approvals. EXPIRAR usa SharePoint. RECUPERAR usa SharePoint, Office 365 Users del invocador y Standard Approvals. Users debe ser Provided by run-only user (`Invoker`); SharePoint y Approvals son `Embedded`. Importar no concede automáticamente permisos de ejecución.

## Contratos e invariantes

V4.2 recibe ocho argumentos: ID, CLAVE_TRANSACCION, ESTUDIANTE, `""`, SOLICITADO_POR, SEDE_ASIGNACION, OBSERVACION, User().Email. No añadir código de estudiante ni alterar su orden.

SOLICITAR recibe seis: OPERACION, ID, CLAVE_TRANSACCION, ETag esperado, motivo, SOLICITUD_UID. CONSULTAR relee ID/clave/ASIGNADO y devuelve snapshot + ETag sin crear. ENVIAR revalida, exige versión, conserva UID y responde creación únicamente si la confirma. Mientras espera, el depósito permanece ASIGNADO/CONFIRMADO.

Una sola solicitud activa por depósito mediante CLAVE_BLOQUEO única; UID único e idempotente; snapshot íntegro; identidad autenticada; ETag/If-Match concretos; retry none en escrituras; nunca `*`. Aprobación humana y resultado técnico se guardan por separado. El ETag cambiado tiene precedencia autoritativa CONFLICTO en resolución, conservando otros cambios como diagnóstico.

Aprobación: Start and wait for an approval, FirstToRespond, dos destinatarios, reasignación deshabilitada. No crear otra tarjeta cuando la primera sea incierta. Una respuesta tardía/huérfana no autoriza escribir una solicitud terminal.

El MERGE protegido del depósito modifica nueve campos: ESTADO_ASIGNACION=DISPONIBLE, ULTIMA_REVERSION_ID=UID y `null` únicamente en ESTUDIANTE, CODIGO_ESTUDIANTE, SOLICITADO_POR, SEDE_ASIGNACION, USUARIO_ASIGNACION, FECHA_HORA_ASIGNACION y OBSERVACION. Conserva CODIGO_ASIGNACION, CLAVE_TRANSACCION y los datos del motor. No elimina depósitos.

Expiración absoluta: FECHA_SOLICITUD +168 horas. Watchdog no roba propiedad por antigüedad. Recuperación requiere evidencia de finalización/cancelación/imposibilidad válida del dueño anterior, reclamo por ETag, nuevo RUN_ID y etapa segura. Un MERGE incierto mantiene bloqueo. Ante 412 de recuperación, releer marcador: si ULTIMA_REVERSION_ID=UID, cerrar solo historial como APROBADO/FINALIZADA/REVERTIDO incluso si hubo otra confirmación después.

No modificar semánticamente últimos dos meses, solo créditos, banco→cuenta, búsqueda descripción, VER/CERRAR/PDF, Print(), Carta 816×1056, cuenta contable, TC USD ni equivalente Bs.

## Bugs resueltos y límites de evidencia

El modal estaba detrás del contenedor principal opaco: el último YAML lo coloca después de ese contenedor y conserva sus hijos. Esta copia de fuente no equivale a una nueva inspección visual del tenant.

CREAR SOLICITUD devolvía HTTP 400 Edm.DateTime por body string con expresiones @ literales. Se corrigieron 48 cuerpos operativos mediante @string(setProperty(...)); las fechas se evalúan como ISO 8601, importe como float, depósito como int y opcionales como null. Snapshot sin alteración. El simulador reproduce la conversión previa que ocultaba el fallo; tests 31 rechazan regresiones.

RESULTADO_TECNICO inicial es null; el campo debe ser opcional y sin predeterminado. La creación real fue confirmada correcta, pero no se aportó lectura independiente de Required/DefaultValue. El provisionador no repara columnas existentes. Mantener la opción histórica PENDIENTE no autoriza usarla como resultado inicial.

## Pruebas y continuidad

Ejecutar primero fetch, status, branch -vv, log y comparar HEAD/upstream. No borrar, resetear, rebasar, hacer force push o sobrescribir trabajo. Ver resultados exactos/baseline en el informe de cierre final. Suites: reversión 27–32; P9 16/18/21/22/24; comprobante 25/26; suite completa.

Comando portable: `python -m pytest -c tests/pytest.ini tests/test_27_reversion_contrato_p9.py tests/test_28_reversion_concurrencia_p9.py tests/test_29_reversion_frontend_p9.py tests/test_30_reversion_expiracion_recuperacion_p9.py tests/test_31_reversion_cuerpos_http_p9.py tests/test_32_reversion_main_screen_actual_p9.py -q`. Instalar dependencias de `tests/requirements-test.txt` y PyYAML si el entorno no las tiene. Ejecutar grupos con generadores en copias aisladas y basetemp propio. No atribuir a código nuevo fallos que se reproduzcan en el baseline.

La aprobación real está confirmada con fecha 2026-10-04 y marcador comprobado. Faltan UID/IDs exactos, rechazo, expiración y recuperación reales. Registrar esas evidencias cuando estén disponibles; no inventar versiones ni ejecuciones. Rechazo debe conservar el depósito y cerrar historial NO_EJECUTADO.

El usuario autorizó este cierre en candidate/p9-reversion. Revisar diff/staging, commit final, push normal de esa rama y comprobar HEAD=remoto/árbol limpio. Para trabajos posteriores, no hacer commit/push/merge automático sin nueva autorización; nunca merge a main por este handoff.

## Próxima fase prevista: P9 — CONFIRMACIÓN MASIVA

No implementada. Plantilla: BANCO, CUENTA_BANCARIA, CODIGO_ASIGNACION, IMPORTE, MONEDA, TIPO_CAMBIO.

Proceso previsto: IMPORTAR → PREVALIDAR → RESUMEN → CONFIRMAR MASIVAMENTE → RESULTADO POR FILA → GENERAR COMPROBANTES. Matching BANCO + CUENTA_BANCARIA + CODIGO_ASIGNACION + IMPORTE; no confirmar ambiguos.

Estados previstos: OK, NO ENCONTRADO, YA CONFIRMADO, IMPORTE NO COINCIDE, BANCO NO COINCIDE, CUENTA NO COINCIDE, ASIGNACIÓN AMBIGUA, USD SIN TC, TC INVÁLIDO, DUPLICADO, CONFLICTO.

Power Apps proporciona UX/prevalidación; backend vuelve a verificar antes de escribir con concurrencia protegida igual que V4.2. Resultado por fila, sin rollback global automático. Sigue pendiente decidir si TIPO_CAMBIO masivo se persiste o es temporal. No tomar esa decisión ahora.

Claude Code debe comenzar con diagnóstico y plan, sin implementar inmediatamente y sin reconstruir trabajo ya validado o la pantalla vigente.

## Resultados actuales comprobados

| Ejecución | Passed | Failed | Errors | Skipped | Xfailed |
|---|---:|---:|---:|---:|---:|
| reversion | 261 | 0 | 0 | 0 | 0 |
| p9 | 263 | 5 | 0 | 0 | 0 |
| baseline_completa | 1252 | 17 | 0 | 23 | 14 |
| candidate_completa | 1289 | 16 | 0 | 23 | 14 |

Fallos nuevos frente al baseline: 0. Comprobante: 61 aprobadas. Los fallos heredados permanecen documentados. Aprobación tenant validada el 2026-10-04; rechazo no probado.
