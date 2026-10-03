# P9 — reversión de confirmación

Implementación local de la fase B aprobada, basada en el diseño V2 y en el commit `d08454f7636a49a5711006cd900d79b32bf9c13b`. La validación en Power Automate, SharePoint y Power Apps Studio queda pendiente. Los pasos para esa sesión están en [DESPLIEGUE_P9_REVERSION.md](DESPLIEGUE_P9_REVERSION.md).

## Componentes y recorrido

Power Apps consulta la confirmación, recibe su versión y envía una solicitud con UID. La solicitud se guarda en `Depositos_Reversiones`. Un trabajador obtiene la aprobación, comprueba el depósito y aplica un único MERGE protegido. El historial conserva por separado la decisión humana y el resultado técnico.

| Componente | Función |
|---|---|
| `P9_SOLICITAR_REVERSION` | CONSULTAR devuelve snapshot/ETag; ENVIAR valida, identifica al solicitante y crea o recupera la solicitud. Responde sin esperar la aprobación. |
| `P9_RESOLVER_REVERSION` | Reclama la solicitud por ETag/RUN_ID, espera la aprobación, registra la decisión y ejecuta la reversión autorizada. |
| `P9_EXPIRAR_REVERSIONES` | Cada cinco minutos revisa solicitudes vencidas sin decisión aceptada, con paginación y cierre protegido. |
| `P9_RECUPERAR_REVERSION` | Recuperación manual por un responsable autenticado y autorizado; conserva evidencia de la ejecución anterior. |
| `P9_PROVISIONAR_REVERSION` | Crea/verifica el esquema y devuelve los GUID reales. No ejecuta operaciones sobre elementos de negocio. |

Las definiciones y sus cinco paquetes ZIP se construyen desde `p9/reversion/construir.py`, `flujos.py`, `wdl.py`, `provisionar.py` y `paquete.py`. El constructor trabaja con archivos locales. Sin configuración genera paquetes con valores pendientes de despliegue; esos valores no identifican un tenant real.

## Esquema e identidad

[esquema_reversiones.json](p9/reversion/esquema_reversiones.json) fija los nombres internos, tipos, obligatoriedad, opciones, índices y unicidad. [contrato.py](p9/reversion/contrato.py) valida ese esquema y los invariantes del proceso.

- `Depositos_Reversiones`: historial con versionado, `Title` opcional, 41 columnas propias y campos integrados de SharePoint. `SOLICITUD_UID` y `CLAVE_BLOQUEO` son únicos e indexados. También se indexan depósito, clave, fecha límite, decisión y fase.
- `Depositos_Activos`: solo se incorpora `ULTIMA_REVERSION_ID`, texto opcional de 255 caracteres, sin valor inicial ni índice.
- El snapshot guarda los 34 campos P8/P9, ID, sitio/lista, ETag y marcador anterior. Conserva los vacíos y el texto original; el importe cero no se considera ausente.
- El solicitante procede de `MyProfile_V2` con conexión **Provided by run-only user**. SharePoint usa una conexión de servicio. El payload de Power Apps no lleva correo ni identidad libre.
- En recuperación, el ID autenticado también debe pertenecer a `PARAM_RESPONSABLES_RECUPERACION`. El valor inicial vacío deniega la operación.

El provisionador obtiene los GUID por lecturas del tenant. Detecta diferencias de columnas existentes y falla al verificarlas; no cambia silenciosamente sus tipos o reglas. Los UUID de recursos internos de los ZIP son identificadores del paquete, distintos de los GUID de listas y conexiones del tenant.

## Exclusión, idempotencia y escritura

La clave activa es `ACTIVA|<GUID-lista>|<ID-depósito>`. Al terminar, el mismo elemento pasa a `CERRADA|<SOLICITUD_UID>`. La restricción única permite una sola solicitud activa por depósito y admite una solicitud futura después del cierre confirmado.

Un reintento con el mismo UID recupera la fila original antes de volver a comprobar la versión del depósito. Exige el mismo depósito, lista, clave, ETag, motivo e identidad. Reutilizar el UID con otros datos produce un error. La creación incierta se reconcilia por UID y no se reintenta automáticamente.

La reversión exige propietario vigente, aprobación persistida, GET por ID, clave y asignación válidas, snapshot compatible y ETag original. Cualquier cambio de ETag tiene prioridad como `CONFLICTO`; las diferencias de clave o estado quedan como evidencia diagnóstica y no sustituyen ese resultado. Antes de escribir se guarda el intento y se vuelve a comprobar la propiedad del historial.

El único MERGE del depósito usa `If-Match` con el ETag original y modifica exactamente estos nueve campos:

| Campo | Valor |
|---|---|
| `ESTADO_ASIGNACION` | `DISPONIBLE` |
| `ESTUDIANTE`, `CODIGO_ESTUDIANTE`, `SOLICITADO_POR`, `SEDE_ASIGNACION`, `USUARIO_ASIGNACION`, `FECHA_HORA_ASIGNACION`, `OBSERVACION` | `null` |
| `ULTIMA_REVERSION_ID` | UID de la solicitud |

`CODIGO_ASIGNACION` es un dato bancario del motor y forma parte de `CLAVE_TRANSACCION`; se conserva junto con la clave y las 26 columnas del motor. No se escribe previamente el marcador. El MERGE no admite reintento automático ni `If-Match: *`; tampoco se obtiene una versión nueva para forzar una solicitud antigua.

Las lecturas transitorias tienen hasta tres intentos. Un 403, 429, 5xx o timeout no se convierte en un 404. Las escrituras del historial usan ETag y eventos con identificador estable; un conflicto puede releerse de forma acotada. Una respuesta incierta no provoca una segunda escritura ciega.

## Estados y aprobación

| Dimensión | Valores |
|---|---|
| Decisión humana | `PENDIENTE`, `APROBADO`, `RECHAZADO` |
| Fase | `RECIBIDA`, `ESPERANDO_APROBACION`, `EJECUTANDO_REVERSION`, `RECUPERACION_REQUERIDA`, `FINALIZADA`, `EXPIRADA` |
| Resultado técnico | `PENDIENTE`, `REVERTIDO`, `CONFLICTO`, `YA_NO_ASIGNADO`, `DEPOSITO_NO_ENCONTRADO`, `CLAVE_NO_COINCIDE`, `ERROR`, `NO_EJECUTADO` |

Éxito de reversión significa únicamente `RESULTADO_TECNICO = REVERTIDO`. `APROBADO + CONFLICTO` conserva ambos hechos y no representa una reversión exitosa. Un rechazo finaliza como `RECHAZADO / FINALIZADA / NO_EJECUTADO`, sin modificar el depósito.

La configuración inicial del resolver usa `gtorricot@univalle.edu;lvelasquezs@univalle.edu`, First to respond, notificaciones nativas de Approval y reasignación deshabilitada. Antes de crear la tarjeta se guarda la configuración efectiva en el historial. El ID de Approval se registra cuando existe una salida o evidencia inequívoca; `StartAndWaitForAnApproval` no lo devuelve anticipadamente.

El plazo es `FECHA_SOLICITUD + 168 horas`, fijado por el servidor. La espera de Approval tiene un límite máximo de siete días y una rama paralela espera la fecha límite absoluta, reclama la expiración y termina el trabajador si gana. El expirador independiente cubre el caso en que el trabajador nunca arrancó. Un reintento no reinicia el plazo.

Al vencer sin decisión aceptada y sin ejecución autorizada, un único cierre del historial guarda:

- `ESTADO_SOLICITUD = PENDIENTE`.
- `FASE_PROCESO = EXPIRADA` y `RESULTADO_TECNICO = NO_EJECUTADO`.
- `CLAVE_BLOQUEO = CERRADA|UID`, fecha de cierre y evento de vencimiento.

La vista muestra **EXPIRADA · SIN DECISIÓN · NO EJECUTADA**. Mientras vence pero el cierre aún no se confirma, la consulta devuelve **VENCIDA — CIERRE PENDIENTE** y conserva el bloqueo. Una decisión aceptada y la expiración compiten por el mismo ETag; una respuesta tardía no reabre la solicitud ni escribe el depósito.

## Recuperación y límites

El marcador propio permite acreditar la reversión y completar solo su historial, aunque después otra persona haya confirmado nuevamente el depósito. Una solicitud terminal devuelve su resultado guardado; recuperar A después de B nunca reserva o limpia otra vez el depósito.

Ante un MERGE incierto se conserva la exclusión hasta reconciliarlo. Un 404 posterior no demuestra ausencia de efecto. Sin marcador propio ni prueba suficiente, se mantiene `RECUPERACION_REQUERIDA`; el mero paso del tiempo no libera una escritura incierta.

Un 412 durante recuperación exige releer primero el depósito y su marcador. Si el marcador contiene el UID propio, el resultado es REVERTIDO y se cierra solo el historial, incluso si el depósito ya volvió a ASIGNADO. Un fallo de esa relectura conserva recuperación y bloqueo; no se cierra como CONFLICTO por el 412 aislado.

La terminación de un propietario anterior se comprueba **manualmente en el portal** por un responsable autorizado. El flujo valida identidad, datos y referencias de esa evidencia, y la guarda al reclamar por ETag y asignar el nuevo RUN_ID. La antigüedad del dueño no autoriza esa transferencia. No consulta una API de estado de ejecuciones ni afirma haber comprobado automáticamente lo que observó el operador. Deshabilitar un flujo no prueba que sus ejecuciones terminaron.

La recuperación conserva `CONFIG_APROBACION_JSON`. Si el trabajador nunca la guardó, el responsable debe aportar una copia verificada de `PARAM_APROBADORES` del resolver, con referencia y fecha; no se usa un segundo conjunto independiente de destinatarios. Las operaciones y el formato exacto de evidencia están en la guía de despliegue.

Los textos serializados de snapshot y bitácora tienen una barrera de 60.000 caracteres. No se truncan. Si el snapshot no cabe, se rechaza el envío; si un evento nuevo no cabe en la bitácora, el CAS no puede continuar y puede quedar un bloqueo pendiente de revisión. No se debe borrar evidencia para forzar el cierre. Cualquier ampliación del almacenamiento requiere una decisión posterior.

Una tarjeta huérfana puede seguir visible en Aprobaciones después de expirar el negocio. Su cancelación es una tarea manual del responsable con acceso a la aprobación enviada. Esa tarjeta no puede superar el cierre terminal con ETag. No se configura un canal externo de aviso final; las notificaciones nativas de Approval y la respuesta a Power Apps son las salidas implementadas. La regla H.6 preserva el resultado terminal del negocio ante un fallo posterior; no se afirma haber probado el envío o fallo de un aviso final inexistente.

## Power Apps y preservación

[SOLICITAR_REVERSION_PEGAR.yaml](p9/reversion/powerapps/SOLICITAR_REVERSION_PEGAR.yaml) agrega el botón dentro de VER para `ASIGNADO`, un overlay y un modal independiente. [P9_CONTROL_INGRESOS_CON_REVERSION.txt](p9/reversion/powerapps/P9_CONTROL_INGRESOS_CON_REVERSION.txt) contiene la alternativa completa. [FORMULAS_EXACTAS.md](p9/reversion/powerapps/FORMULAS_EXACTAS.md) detalla pegado, seis argumentos posicionales y fórmulas canónicas/regionales.

El botón ocupa el espacio libre del botón de confirmación, que está oculto al ver un depósito asignado. No se mueve ningún control previo. La copia extendida conserva todos los bytes de la base como prefijo, y su árbol completo coincide con la base al retirar exclusivamente los nuevos controles.

El modal muestra snapshot, motivo obligatorio y plazo. Doble clic queda bloqueado durante una llamada. Ante respuesta incierta conserva UID, depósito, clave, ETag y motivo para el mismo reintento. CANCELAR cierra el modal; no cancela una aprobación ni borra un envío incierto. La retención de estos valores dura la sesión de la app: si esta se reinicia, el responsable debe consultar el historial antes de repetir el envío.

La V4.2, sus ocho argumentos, filtros, ventana de dos meses, búsqueda, VER y comprobante se preservan. Un comprobante ya abierto o un PDF guardado conserva su contenido. Al volver a abrir, la validación vigente bloquea el comprobante de un depósito disponible. La regresión contable compara explícitamente los 20 pares/variantes y las 14 cuentas de destino, sin cambiar fórmulas del comprobante.

## Verificación local

Las cifras finales y los comandos ejecutados se registran en [INFORME_PRUEBAS.md](p9/reversion/evidencias/INFORME_PRUEBAS.md). Las huellas reales de partida están en [huellas_base.json](p9/reversion/evidencias/huellas_base.json). El ZIP anterior conserva SHA y procedencia en [referencia/PROCEDENCIA.md](p9/reversion/referencia/PROCEDENCIA.md).

Las pruebas nuevas cubren contrato/provisión, concurrencia, frontend y expiración/recuperación. Las pruebas de frontend son estáticas; el ensayo local no certifica el comportamiento de los conectores en el tenant.

La auditoría del commit base en una copia Git con LF encontró cinco fallos existentes de reproducibilidad binaria en Windows. Los generadores antiguos cambian finales de línea y metadatos/DEFLATE de ZIP; pruebas posteriores fallan por esos nuevos hashes. Los quince archivos internos de los tres ZIP regenerados resultaron idénticos byte a byte. Esa causa se registra por separado de cualquier fallo nuevo, y no convierte la suite en una ejecución sin fallos. Los tests antiguos que regeneran paquetes deben correrse en copias desechables.

En `test_26`, la comparación de hashes fijados normaliza CRLF a LF solo en memoria: los valores fijados corresponden a blobs Git LF. Las huellas de preservación comparan aparte los bytes reales del checkout. No se reescribió el comprobante para satisfacer la prueba.

En `test_16`, la adenda autorizada de `ESTADO_PROYECTO.md` se admite conservando la comprobación del hash del prefijo original íntegro. No se excluye ese archivo de la protección histórica.
