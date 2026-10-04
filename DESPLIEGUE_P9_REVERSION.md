# Despliegue y recuperación — reversión P9

Estado actualizado 2026-10-04: el usuario confirmó provisión, importación manual de ZIP corregidos y prueba end-to-end de **aprobación** satisfactoria: DISPONIBLE, siete campos operativos limpios, clave/código conservados, marcador comprobado, historial/trazabilidad y sin duplicados observados. Rechazo no probado en tenant. Expiración/recuperación reales siguen pendientes. Ver [ESTADO_P9_REVERSION_VALIDADO_TENANT.md](ESTADO_P9_REVERSION_VALIDADO_TENANT.md). `INFORME_CIERRE_FINAL.md` registra las pruebas locales actuales; el informe original de fase B es histórico.

Antes de ENVIAR, comprobar en `Depositos_Reversiones` que `RESULTADO_TECNICO` sea opcional y no tenga valor predeterminado. El esquema anterior usaba obligatorio/PENDIENTE; la corrección exige `null` al crear. La importación del provisionador no modifica columnas existentes.

Si se reimportan los paquetes corregidos, actualizar los cuatro flujos existentes según el mapeo de importación y verificar conexiones y ejecuciones activas. Registrar los SHA-256 del archivo realmente importado. Evitar crear un segundo resolver sobre el mismo historial. Las copias configuradas permanecen fuera del repositorio; los ZIP de la raíz son genéricos y corresponden a los builders actuales.

## 1. Preparar el entorno de prueba

1. Elegir el sitio real y una copia de la app P9 para la validación. Registrar entorno, sitio y responsables operativos.
2. Exportar una copia de la app vigente y conservar la V4.2 y el comprobante actuales. Registrar las solicitudes/ejecuciones activas si esta lista ya se utilizó antes.
3. Identificar una conexión de servicio SharePoint y una conexión Standard Approvals. El servicio necesita leer y actualizar los depósitos e historial; quien ejecute la provisión necesita además administrar listas y columnas.
4. Preparar Office 365 Users para que solicitantes y responsables usen su propia conexión. Compartir la ejecución de solicitud solo con operadores admitidos y la recuperación solo con responsables autorizados. Restringir la edición directa del historial y del marcador; el frontend no los escribe.
5. Obtener los **Object IDs de Entra** de los responsables y comprobarlos contra `MyProfile_V2.id`. No usar correos en el array de IDs. Guardar estos datos en la configuración local de despliegue.

No hay una concesión automática de permisos por importar los ZIP. Se verifican las conexiones y permisos efectivos con dos usuarios antes de habilitar el uso operativo.

## 2. Provisionar y obtener los GUID

1. Importar `P9_PROVISIONAR_REVERSION.zip` como flujo nuevo y mapear su conexión SharePoint al sitio previsto. El ZIP histórico de `referencia/` no se importa.
2. Ejecutar manualmente con **Sitio SharePoint** igual a la URL exacta del sitio, sin barra final. `Depositos_Activos` debe existir.
3. Revisar la acción `RESUMEN_FINAL`: exigir `PROVISION_P9_REVERSION = OK`, dos listas verificadas y `diferencias = []`. Conservar la salida, el ID de ejecución y el hash del esquema.
4. Copiar los GUID devueltos para `Depositos_Activos` y `Depositos_Reversiones`. Confirmar nombres internos, campos, tipos, siete índices del historial, unicidad de UID/bloqueo, versionado y marcador opcional.
5. Si aparece `FAIL`, no habilitar los trabajadores. Revisar las diferencias y cualquier creación parcial. El provisionador no convierte columnas existentes ni elimina datos para corregirlas. Una segunda ejecución vuelve a verificar el estado real.

La provisión crea las columnas con sus nombres internos ASCII y configura título/propiedades. Los cambios sobre metadatos de columnas usan el GUID recién devuelto por SharePoint; no son el MERGE de negocio de un depósito. Ninguna de estas operaciones usa `If-Match: *`.

## 3. Crear copias de paquetes configuradas

El constructor genera primero los cinco paquetes genéricos, sin acceder al tenant:

```powershell
python -m p9.reversion.construir
```

Para el despliegue, guardar un archivo local `configuracion-reversion.json` con datos comprobados. Los textos entre `<...>` son marcadores que deben reemplazarse; no son GUID válidos ni datos para importar:

```json
{
  "sitio_sharepoint": "<URL_HTTPS_REAL_DEL_SITIO_SIN_BARRA_FINAL>",
  "lista_reversiones_id": "<GUID_REAL_DEVUELTO_POR_PROVISION>",
  "responsables_recuperacion_ids": ["<OBJECT_ID_ENTRA_DEL_RESPONSABLE>"],
  "aprobadores": ["gtorricot@univalle.edu", "lvelasquezs@univalle.edu"]
}
```

Generar las copias configuradas en una carpeta separada:

```powershell
python -m p9.reversion.construir --config configuracion-reversion.json --salida paquetes-reversion-tenant
```

Revisar los valores resultantes antes de importar:

| Punto | Valor esperado |
|---|---|
| `PARAM_SITIO_SHAREPOINT` de los cuatro flujos de negocio | URL verificada |
| Trigger SharePoint del resolver: `dataset` | La misma URL |
| Parámetro de definición `LISTA_REVERSIONES_ID` del resolver | GUID real del historial |
| Trigger SharePoint del resolver: `table` | Referencia a ese parámetro |
| `PARAM_APROBADORES` del resolver | Los dos correos aprobados, separados por `;` |
| `PARAM_RESPONSABLES_RECUPERACION` del recuperador | Array de IDs autenticados autorizados |
| Plazo, modalidad, reasignación | 168 horas, FirstToRespond, false |

Los GUID de listas no se deducen de los identificadores internos del ZIP. En cada ejecución se vuelven a obtener los GUID por el título de las listas; el resolver comprueba que el GUID de su trigger corresponde al historial esperado. Mantener los paquetes genéricos y las copias configuradas por separado.

## 4. Importar y verificar las conexiones

Importar como nuevos los otros cuatro flujos desde la carpeta configurada. Mantenerlos sin uso operativo durante la comprobación y comprobar su estado de habilitación después de importar. Si la lista ya tiene solicitudes activas, resolver previamente el plan de continuidad para que no arranquen trabajadores duplicados.

| Flujo | Conexiones |
|---|---|
| SOLICITAR | SharePoint de servicio; Office 365 Users del invocador |
| RESOLVER | SharePoint de servicio; Standard Approvals |
| EXPIRAR | SharePoint de servicio |
| RECUPERAR | SharePoint de servicio; Office 365 Users del invocador; Standard Approvals |

En **Run-only users**, configurar Office 365 Users como **Provided by run-only user** para SOLICITAR y RECUPERAR. Los paquetes la declaran con origen `Invoker`; confirmar que la importación conservó esa propiedad. SharePoint/Approvals usan sus conexiones de servicio. Un solicitante no debe terminar identificado como propietario del flujo.

En el diseñador comprobar:

- SOLICITAR conserva seis inputs **requeridos** y su orden: operación, ID numérico, clave, ETag, motivo y UID. CONSULTAR envía `""` en los tres últimos. No convertir ninguno en opcional, pues cambiaría la firma de Power Apps.
- Las once salidas de Power Apps son texto, incluida `fecha_limite`.
- La tarjeta usa First to respond y `enableReassignment = false`. Confirmar su comportamiento real con ambos aprobadores.
- El MERGE del depósito usa el ETag original, nueve campos y retry `none`.
- El temporizador espera `FECHA_LIMITE`; el expirador corre cada cinco minutos. El `P7D` de la acción Approval es el techo del webhook, y la rama paralela aplica el límite absoluto del negocio.
- El recuperador deniega IDs no incluidos en el array configurado.

No sustituir una conexión antigua del ZIP histórico ni seleccionar listas por parecido de nombre.

## 5. Agregar la interfaz en la copia de Power Apps

1. Agregar el nuevo flujo SOLICITAR a la app y comprobar que Studio reconoce los seis argumentos. Si se actualiza el flujo, refrescar su conexión en la copia y volver a comprobar la firma.
2. Usar [Main_Screen.yaml](p9/reversion/powerapps/Main_Screen.yaml), que es el último YAML completo entregado y pegado por el usuario. Las fórmulas y fragmentos de fase B se conservan como antecedentes, no como fuente de la pantalla actual.
3. Preservar su orden raíz: `cntControlDepositosP9`, `overlayReversionP9`, `cntSolicitarReversionP9`. Overlay y modal son hermanos de la pantalla y quedan delante del contenedor opaco. El botón está dentro de `cntConfirmarDepositoP9_1`; conservar nombres y sufijos existentes.
4. Comprobar fórmulas canónicas al pegar YAML y las variantes regionales en la barra de fórmulas. Verificar `IfError`, conversiones `ParseJSON`, nombres existentes y ausencia de advertencias nuevas.
5. Comprobar modal, motivo largo, cancelación, doble clic y reintento del mismo UID tras perder la respuesta. El modal de escritorio necesita un contenedor de al menos 690 píxeles de alto.
6. Usar ACTUALIZAR tras resolver la solicitud para mostrar el estado reciente. La confirmación y la pantalla COMPROBANTE PDF conservan sus controles y fórmulas originales.

## 6. Pruebas reales antes de uso operativo

Registrar ID/UID de solicitud, ID de depósito, versiones, ejecución y resultado de cada caso:

1. Dos usuarios distintos: identidad de solicitud real; recuperación denegada para un usuario fuera del array.
2. CONSULTAR/ENVIAR de un ASIGNADO; rechazo de motivo vacío, ID inexistente, clave incorrecta, DISPONIBLE y ETag ausente/antiguo.
3. Aprobación normal: snapshot completo, un MERGE de nueve campos, REVERTIDO y bloqueo cerrado. Comprobar `null` de texto/fecha y las 26 columnas bancarias intactas.
4. Rechazo: NO_EJECUTADO, cierre y cero versiones nuevas del depósito.
5. Dos solicitudes simultáneas y doble clic: una sola activa, UID idempotente y una sola Approval. Reutilizar UID con distinto usuario/motivo debe fallar.
6. Editar el depósito durante la espera y entre GET/MERGE: conflicto por versión, incluyendo un 412 real; no sobrescribir la edición.
7. Expiración con trabajador detenido/no iniciado, respuesta inmediata y respuesta tardía. Para ensayar rápido, usar una copia de prueba con plazo corto; verificar por separado que los paquetes de entrega y solicitudes reales conserven 168 horas.
8. Perder la respuesta del MERGE y fallar el cierre del historial. Recuperar mediante marcador; luego repetir A tras una reconfirmación y después de una solicitud B. La confirmación posterior debe permanecer intacta.
9. Fallos 403, 429, 5xx, timeout y 404: revisar clasificación, retención de bloqueo y ausencia de reintento ciego.
10. Regresión completa de confirmar, filtros, búsqueda, dos meses, VER, PDF Carta, Print(), los 20 pares contables, TC con coma/punto y equivalente Bs.

Conservar las ejecuciones y salidas; las pruebas locales no sustituyen estas comprobaciones. Habilitar el uso operativo de la copia solo después de revisar sus resultados con el usuario.

## 7. Recuperación manual de una solicitud

### 7.1 Reunir evidencia antes de tomar propiedad

1. Leer por UID el historial y su RUN_ID. Si es FINALIZADA o EXPIRADA, conservar su resultado; no reservar de nuevo el depósito.
2. Abrir la ejecución anterior en Power Automate y comprobar que terminó o fue cancelada. Deshabilitar el flujo no cancela sus ejecuciones existentes.
3. Examinar Approval, intento MERGE, respuestas, marcador actual y cierres del historial. Clasificar un MERGE como NO_ENVIADO o FALLO_SIN_EFECTO solo si la evidencia demuestra que no tiene efecto ni operación pendiente. Un timeout se clasifica INCIERTO hasta reconciliarlo.
4. Obtener evidencia de la tarjeta por UID/ID si se necesita esperar una Approval existente. No crear una tarjeta nueva porque falte APROBACION_ID en la fila.
5. Ejecutar RECUPERAR con tres entradas: SOLICITUD_UID, OPERACION y EVIDENCIA_JSON. El flujo vuelve a validar la identidad y reclama la fila por ETag.

El flujo guarda la declaración del operador; **no consulta una API de terminalidad**. La verificación humana en el portal es parte del procedimiento autorizado.

### 7.2 Operaciones

| OPERACION | Uso y condiciones |
|---|---|
| `RECONCILIAR` | Buscar prueba del efecto, especialmente marcador propio. No envía un nuevo MERGE del depósito. Sin prueba conserva la revisión. |
| `CONTINUAR` | Continuar una aprobación ya persistida cuando el intento anterior está probado NO_ENVIADO/FALLO_SIN_EFECTO. Mantiene el ETag original. |
| `INICIAR_APROBACION` | Sin decisión; demostrar que Approval no se creó y MERGE no se envió. Mantener fecha límite original. |
| `ESPERAR_APROBACION` | Sin decisión; usar una aprobación CREADA_IDENTIFICADA con su ID, UID y evidencia. No crea otra. |
| `CERRAR_ERROR` | Error permanente con ausencia de efectos/operaciones pendientes acreditada. El marcador propio tiene prioridad y produce REVERTIDO. |

Una solicitud RECIBIDA sin RUN_ID, configuración de Approval ni intento de MERGE puede recuperarse como trabajo nunca reclamado. Si tiene dueño, se exige la prueba de terminación anterior.

La recuperación sí registra evidencia y propiedad en el historial mediante CAS; reconciliar no significa que el historial permanezca sin cambios.

### 7.3 Formato de EVIDENCIA_JSON

Plantilla para un propietario previo. Reemplazar los valores indicados por los hechos comprobados; los textos siguientes no constituyen evidencia válida:

```json
{
  "run_id": "<RUN_ID_ANTERIOR_DEL_HISTORIAL>",
  "estado_run": "<Succeeded|Failed|Cancelled|TimedOut>",
  "url_ejecucion": "https://make.powerautomate.com/<RUTA_REAL_QUE_INCLUYE_EL_RUN_ID>",
  "fecha_fin_run": "<FECHA_UTC_REAL_ISO_8601>",
  "fecha_verificacion": "<FECHA_UTC_REAL_ISO_8601>",
  "verificado_por_id": "<ID_ENTRA_DEL_INVOCADOR_AUTENTICADO>",
  "motivo_recuperacion": "<MOTIVO_COMPROBADO>",
  "evidencia_operaciones": "<ACCIONES, RESPUESTAS Y REFERENCIAS EXAMINADAS>",
  "merge_estado": "<NO_ENVIADO|FALLO_SIN_EFECTO|INCIERTO>",
  "approval_estado": "<NO_CREADA|CREADA_IDENTIFICADA>",
  "aprobacion_id": "<ID_REAL_SI_SE_ESPERA_LA_EXISTENTE>",
  "solicitud_uid": "<UID_DEL_HISTORIAL>",
  "error_permanente": "<DETALLE_SI_SE_SOLICITA_CERRAR_ERROR>"
}
```

`run_id` debe coincidir con el historial; el estado debe ser terminal; la URL debe pertenecer a `https://make.powerautomate.com/` e incluir ese RUN_ID. Se exige `fecha_fin_run <= fecha_verificacion <= ahora` y que `verificado_por_id` sea el ID devuelto por la conexión propia. El responsable conserva evidencia suficiente de la clasificación, no solo el nombre del estado.

Si `CONFIG_APROBACION_JSON` está vacío, agregar a la evidencia una copia verificada del parámetro del resolver:

```json
{
  "config_aprobacion": {
    "aprobadores": "gtorricot@univalle.edu;lvelasquezs@univalle.edu",
    "modalidad": "FirstToRespond",
    "reasignacion": false,
    "plazo_horas": 168
  },
  "fuente_config_url": "https://make.powerautomate.com/<RUTA_REAL_DEL_RESOLVER>",
  "fecha_verificacion_config": "<FECHA_UTC_REAL_ISO_8601>"
}
```

Este objeto se incorpora al JSON principal; no reemplaza la evidencia anterior. Si ya existe configuración guardada, se utiliza sin sustituir destinatarios. La fecha límite siempre procede del historial.

Después de recuperar, releer el historial y comprobar fase, resultado, fecha de cierre y clave. Un 412 en recuperación obliga a releer el marcador: UID propio acredita REVERTIDO y solo cierra historial, aunque exista una nueva confirmación. Si esa relectura falla, se mantiene recuperación y bloqueo. Una caída puede impedir guardar el error; en ese caso, la etapa anterior y la ejecución fallida siguen siendo evidencia. No repetir todo el flujo para resolver un aviso o un cierre pendiente.

## 8. Tarjetas, capacidad y retirada de la extensión

- Para una tarjeta huérfana, el responsable con acceso a la aprobación enviada la identifica por UID/ID en Aprobaciones → Enviadas y la cancela manualmente si sigue abierta. No cambiar la decisión efectiva ni reabrir una solicitud expirada.
- Si snapshot/bitácora supera la barrera de 60.000 caracteres, conservar evidencia y revisar la capacidad. No truncar el snapshot ni borrar eventos para forzar un CAS. Puede requerir una ampliación posterior del diseño.
- No hay un canal configurado para el aviso final por correo/Teams/otro conector nuevo. La regla H.6 conserva el resultado del negocio ante fallos posteriores; no se afirma una prueba de envío o fallo de ese aviso.
- Para retirar la extensión, detener nuevos envíos desde la copia de la app y revisar solicitudes/ejecuciones pendientes. Resolver las escrituras inciertas antes de retirar trabajadores. Deshabilitar un flujo por sí solo no acredita ausencia de efectos.
- Conservar historial, snapshots y marcador; no borrar listas, limpiar marcadores ni restaurar masivamente valores del depósito como rollback. Una reversión ya ejecutada se trata con el proceso operativo de confirmación correspondiente.
- La app base exportada, la V4.2 y COMPROBANTE PDF permiten restaurar la interfaz previa. Verificar que no queden solicitudes activas ocultas al hacerlo.
