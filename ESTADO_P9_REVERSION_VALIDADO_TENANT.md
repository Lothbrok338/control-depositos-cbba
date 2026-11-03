# P9 reversión — aprobación validada en tenant

Fecha real de validación: **2026-10-04**, confirmada expresamente por el usuario. La prueba ejecutada fue de **APROBACIÓN**, satisfactoria de punta a punta. **RECHAZO NO PROBADO**. Expiración y recuperación reales no tienen evidencia aportada.

Rama: `candidate/p9-reversion`. Base antes de reversión: `d08454f7636a49a5711006cd900d79b32bf9c13b`. HEAD anterior al cierre: `1feeeb9157c1c677e523ce39c5c1ac5ebeb39871`. SHA final: revisión Git que contiene este documento; obtener con `git log -1 --format=%H -- ESTADO_P9_REVERSION_VALIDADO_TENANT.md`, verificar HEAD/upstream y cotejar con el SHA literal del reporte/prompt de entrega. No se hizo merge a main.

## Evidencia y resultado reales

Fuente: confirmación textual del usuario el 04/10/2026. No se recuperó un export de ejecución ni se accedió al tenant automáticamente. UID/ID de solicitud y ejecución: **no aportados**; el usuario no los tenía a mano. No hay esos identificadores en los artefactos locales de generación o simulación; no sustituirlos por IDs de fixtures.

Power Apps → CONSULTAR → ENVIAR OK; creación en Depositos_Reversiones OK; Approval recibido OK; aprobación humana OK; ASIGNADO/CONFIRMADO → DISPONIBLE OK; limpieza de siete campos OK; CODIGO_ASIGNACION y CLAVE_TRANSACCION conservados OK; ULTIMA_REVERSION_ID comprobado OK; historial/trazabilidad OK; sin duplicados observados OK. La fecha y resultados proceden del usuario, no de los timestamps del simulador.

También reportó provisión `PROVISION_P9_REVERSION=OK`, `diferencias=[]`, lista de historial comprobada visualmente, CONSULTAR con resultado/código LISTO y ETag `"3"`, e importación manual de los ZIP corregidos. No se aportaron IDs de los cuatro flujos/ejecuciones, export de conexiones ni verificación individual de metadatos de columnas.

## Configuración utilizada

Sitio: `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`. Depositos_Activos: `296c450a-25d6-415b-ad10-c909c74817cb`. Depositos_Reversiones: `45ff53dc-fee7-4b7c-81cb-a226f09ba0f2`.

Aprobadores: gtorricot@univalle.edu y lvelasquezs@univalle.edu. Responsable de recuperación: Gabriel Torricot, gtorricot@univalle.edu; Object ID verificado por el usuario mediante Get my profile (V2): `0b598a5a-e435-4696-8de2-933abbc2b265`. No incluir credenciales, JSON de configuración real ni ZIP configurados en Git.

Flujos importados según el usuario: P9_SOLICITAR_REVERSION, P9_RESOLVER_REVERSION, P9_EXPIRAR_REVERSIONES y P9_RECUPERAR_REVERSION. La ejecución positiva confirma SOLICITAR/RESOLVER y Approval; no certifica ejecución real de EXPIRAR/RECUPERAR. SOLICITAR requiere SharePoint de servicio + Users Invoker; RESOLVER SharePoint + Standard Approvals; EXPIRAR SharePoint; RECUPERAR SharePoint + Users Invoker + Standard Approvals. Verificar las conexiones efectivas en futuras sesiones.

## Contrato y secuencia funcional

VER → SOLICITAR REVERSIÓN → CONSULTAR → modal → motivo obligatorio → ENVIAR → historial → resolver → Approval → decisión. Main_Screen.yaml es la copia del último YAML completo pegado por el usuario, con modal delante del fondo, redondeos y columnas finales.

CONSULTAR relee ID/clave/ASIGNADO, devuelve snapshot + ETag y no crea. ENVIAR conserva seis argumentos, revalida versión, usa UID idempotente y reserva única; devuelve ID/UID solo con creación confirmada. El depósito permanece confirmado mientras espera. Identidad autenticada en backend; sin correo libre de Power Apps.

Mantener ETag/If-Match concretos, retry none y nunca asterisco. Decisión y resultado técnico separados. Aprobación usa Start and wait for an approval, FirstToRespond y reasignación deshabilitada. Conflicto de ETag tiene precedencia y conserva cambios adicionales como evidencia.

Un MERGE de nueve campos establece DISPONIBLE, ULTIMA_REVERSION_ID=UID y null únicamente en ESTUDIANTE, CODIGO_ESTUDIANTE, SOLICITADO_POR, SEDE_ASIGNACION, USUARIO_ASIGNACION, FECHA_HORA_ASIGNACION y OBSERVACION. Conserva código, clave y todas las columnas del motor; no elimina depósitos.

Expiración absoluta 168h y cierre protegido. Recuperación exige prueba del fin/cancelación/imposibilidad del trabajador anterior, reclamo por ETag y nuevo RUN_ID; no roba propiedad por antigüedad. Un MERGE incierto conserva bloqueo. En recuperación, 412 exige releer marcador: si es propio, cerrar solo historial REVERTIDO aun tras nueva confirmación. Estas rutas están probadas localmente, sin confirmación de prueba real.

## Problemas encontrados y solución

Modal oculto por el contenedor opaco: corregido en el último YAML colocando overlay y modal después de ese contenedor. No reconstruir la pantalla desde fragmentos históricos.

CREAR SOLICITUD devolvía HTTP 400 Edm.DateTime porque body string contenía expresiones @ literales. `wdl.serializar_cuerpo` evalúa el objeto mediante setProperty y lo serializa al final. Corrige 48 cuerpos operativos; fechas ISO 8601, importe float, depósito int, opcionales null y snapshot intacto. Tests 31 impiden regresiones. RESULTADO_TECNICO inicial null, decisión PENDIENTE y fase RECIBIDA; columna opcional/sin predeterminado. El provisionador no repara columnas existentes. La creación real ya fue confirmada correcta.

## ZIP finales, hashes y reimportación

Los cinco ZIP genéricos de la raíz coinciden con builders/definitions actuales y sus hashes están en `p9/reversion/evidencias/PAQUETES_CIERRE_FINAL_SHA256.txt`. Las cuatro copias configuradas, fuera de Git, fueron cotejadas contra esos builders; sus hashes se registran en `p9/reversion/evidencias/CIERRE_FINAL.json`.

Workspace original: `outputs/correccion-cuerpos-http-p9/tenant/`. Los ZIP de `outputs/tenant-univalle-p9-reversion/` son históricos anteriores al fix y están marcados; su JSON real sigue siendo la configuración local. El ZIP de `p9/reversion/referencia/` es histórico y no se importa.

Para reimportar: preparar copias configuradas separadas, actualizar flujos existentes, mapear conexiones y revisar ejecuciones activas para no duplicar workers. Confirmar seis argumentos y columna opcional/sin default. Preservar el YAML vigente; no importar automáticamente desde scripts de generación. La guía DESPLIEGUE_P9_REVERSION.md conserva el procedimiento.

## Tests, alcance y pendientes reales

Resultados exactos actuales, casos baseline, skips y xfails: `p9/reversion/evidencias/INFORME_CIERRE_FINAL.md` y `CIERRE_FINAL.json`. Las pruebas estáticas/simuladas no se registran como casos tenant. Se conservan V4.2, últimos dos meses, créditos, filtros/búsqueda, VER/PDF, Carta, Print(), contabilidad y TC USD.

Pendientes: rechazo real; expiración/recuperación reales; recuperar UID/IDs y exports de ejecución/conexiones si se desea auditar el caso. Sin duplicados fue una observación de la prueba reportada, no certificación exhaustiva de todas las carreras posibles. No se implementó confirmación masiva ni se decidió persistencia de TIPO_CAMBIO.

El usuario autorizó commit/push final exclusivamente de candidate/p9-reversion después de esta confirmación. Sin merge a main, sin rebase/force push y sin despliegue automático por el agente.
