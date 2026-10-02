# P9 — Asignación de depósitos (Power Apps + Power Automate)

**Iteración vigente (VALIDADA EN EL TENANT con la V4.2):** (1) el código de estudiante sale de la experiencia operativa; (2) la app solo muestra y busca movimientos de los últimos 2 meses. Entregables: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip` (+ `…_DIFF.md`) y `p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt`. **Las V4 y V4.1 están descartadas/superadas** (rompían la firma de `.Run(...)`; ver §9.1). Detalle en §9. Lo de abajo describe la base anterior, que sigue siendo válida para todo lo no mencionado en §9 y queda como **rollback**: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip` + `p9/powerapps/_base_validada_tenant/P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt` (frontend que exige el código de estudiante, sin ventana de 2 meses).

Estado de la base: **validada en el tenant** (Power Apps sin errores, confirmación real ejecutada). Rama `candidate/p9-powerapps-asignacion`, base `candidate/p8-5-certificacion-e2e` `c43585f71aea35e81b4c215f692d498b8e1087be`.

**Validado en el tenant (por el usuario):** la app Power Apps abre sin errores; se ejecutó una confirmación real; `Depositos_Activos` se actualiza en SharePoint y la app lo refleja; el estado visible es `DISPONIBLE` / `CONFIRMADO`; solo se muestran `CRÉDITO`; el filtro `BANCO` → `CUENTA BANCARIA` es dependiente; `DESCRIPCIÓN contiene` busca en dos etapas; se ven fecha, hora, descripción, código de asignación e importe; queda trazado quién confirmó y cuándo; `OBSERVACION` es opcional; el backend conserva ETag / If-Match / MERGE. Lo que sigue sin validarse en tenant se lista en §6.

Tenant piloto (solo piloto P9): sitio `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu`, lista `Depositos_Activos` `296c450a-25d6-415b-ad10-c909c74817cb`. La migración al sitio institucional queda para producción.

## 1. Qué entrega

| Archivo | Para qué |
|---|---|
| `P9_HABILITAR_ESTADO_ASIGNADO.zip` | Paquete independiente: habilita `ASIGNADO` en la columna `ESTADO_ASIGNACION` (ahora solo `DISPONIBLE`) y verifica/crea los 7 índices que necesita la app. Manual e idempotente. |
| `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip` | **Backend VIGENTE, validado en tenant.** Los 8 inputs del trigger están en `required` (presencia técnica del parámetro, no contenido) → `.Run(...)` con 8 argumentos posicionales y sin registro opcional. `CODIGO_ESTUDIANTE` y `OBSERVACION` pueden valer `""`: `Validar_entrada` no los exige. Diff V4.1→V4.2 y V3→V4.2: `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES_DIFF.md`. |
| `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_1_FIRMA_8_ARGUMENTOS.zip` | **V4.1 — SUPERADA, NO IMPORTAR.** Dejó `text_5` fuera de `required`: Power Apps pidió 7 posicionales + un registro final («Text donde se espera Record»). Solo procedencia de la V4.2. |
| `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_SIN_CODIGO_ESTUDIANTE.zip` | **V4 — DESCARTADA, NO IMPORTAR.** Quitó `text_2` de `required` y Power Apps dejó de aceptar los 8 argumentos (§9.1). Se conserva solo como base reproducible de la V4.1. |
| `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA.zip` | **Backend validado en tenant (ROLLBACK; base de la V4/V4.1/V4.2).** Flujo con trigger **Power Apps (V2)** y respuesta a Power Apps con 6 salidas tipadas: `DISPONIBLE → ASIGNADO` con control optimista If-Match/ETag. Su diff contra la versión previa está en `P9_ASIGNAR_DEPOSITO_POWERAPPS_V3_RESPUESTA_DIFF.md` (único cambio: marca `x-ms-dynamically-added` en las 6 salidas). |
| `P9_ASIGNAR_DEPOSITO.zip`, `P9_ASIGNAR_DEPOSITO_POWERAPPS_V2.zip` | **Versiones previas, NO usar** (trigger manual / Power Apps V2 sin salidas tipadas: la app recibe la respuesta vacía). Se conservan como procedencia; diff en `P9_ASIGNAR_DEPOSITO_POWERAPPS_V2_DIFF.md`. |
| `p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt` | **Frontend VIGENTE, validado en tenant:** la base validada sin código de estudiante y con ventana de 2 meses (§9). Se pega igual que la base. |
| `p9/powerapps/_base_validada_tenant/P9_CONTROL_INGRESOS_FINAL_VALIDADO_TENANT.txt` | **Frontend base validado en tenant** (archivado para volver atrás; no es el vigente) (control YAML único `cntControlDepositosP9`, ManualLayout) para «Pegar código» en Power Apps Studio. SHA-256 `595a95b4434f4e0f9d1a2737a35dcfaf0f993db1e3193c9050a5187bb828fc64`. Sustituye a todos los frontends anteriores (que se retiraron del repositorio). |
| `p9/` | Código que genera los paquetes (`python -m p9.asignar.construir`, `python -m p9.asignar.convertir_powerapps_v2`, `python -m p9.asignar.convertir_powerapps_v3`, `python -m p9.habilitar.construir`), simulador local y huellas del commit base. |
| `tests/test_16_…`, `test_18_…`, `test_21_…`, `test_22_…`, `test_24_…` (V4.2) | Pruebas locales (ver §7). |

**No se tocó P6/P7/P8/P8.5.** Todo lo de P9 es archivo nuevo, salvo una línea de marcador en `tests/pytest.ini`. `p9/evidencias/huellas_base_p8_5.json` guarda el SHA-256 de los 72 archivos no-test del commit base y una prueba comprueba que ninguno cambió. El provisionador P8 no se modificó ni se reutilizó: P9 tiene el suyo.

**Fuera de alcance (no existe en P9):** cierre histórico, SAP, facturación, pregrado/posgrado, reversión, reasignación, anulación, dashboards, catálogo de sedes, regla por `TIPO_MOVIMIENTO`, estados distintos de `DISPONIBLE` y `ASIGNADO`.

## 2. Arquitectura y garantías

```
Power Apps (solo LEE Depositos_Activos)
   └─ P9_ASIGNAR_DEPOSITO.Run(ID, CLAVE, ESTUDIANTE, CODIGO_ESTUDIANTE, SOLICITADO_POR, SEDE, OBSERVACION, User().Email)
        └─ Power Automate
             1. valida entradas (0 llamadas a SharePoint si faltan datos)
             2. GET  elemento por ID  → ETag
             3. CLAVE_TRANSACCION igual (exacta) y ESTADO_ASIGNACION = DISPONIBLE
             4. POST + X-HTTP-Method: MERGE + IF-MATCH: <ETag leído>   ← control optimista
             5. responde: ASIGNADO | NO_DISPONIBLE | CONFLICTO | ERROR
```

* **Nunca se elimina un movimiento:** el flujo solo hace un GET y un MERGE sobre un elemento; no tiene DELETE (comprobado por prueba estática).
* **Dos usuarios, un depósito:** hay dos defensas. (a) El flujo **lee el estado en el momento de confirmar**: si otro ya asignó, devuelve `NO_DISPONIBLE`. (b) Para la carrera de milisegundos entre esa lectura y la escritura, el MERGE lleva `If-Match = ETag`: si el elemento cambió, SharePoint responde 412 y el flujo devuelve `CONFLICTO` sin escribir. Nunca se usa `If-Match: *` al asignar.
* **Solo escribe 8 columnas operativas:** `ESTADO_ASIGNACION`, `ESTUDIANTE`, `CODIGO_ESTUDIANTE`, `SOLICITADO_POR`, `SEDE_ASIGNACION`, `OBSERVACION`, `USUARIO_ASIGNACION`, `FECHA_HORA_ASIGNACION`. Ninguna de las 26 columnas del motor. `FECHA_HORA_ASIGNACION = utcNow()` del flujo (no confía en el reloj de la app).
* **Resultado incierto no se reporta como éxito:** si el MERGE falla por timeout/5xx, se devuelve `ERROR / ACTUALIZACION_NO_CONFIRMADA` y se pide verificar la lista. No hay reintentos automáticos (`retryPolicy: none`): un reintento con el mismo ETag podría dar un `CONFLICTO` falso.
* El flujo **siempre responde** a la app (el `Response` corre tras TRY y CATCH en cualquier estado).

### Contrato del flujo

Entradas, **en este orden** (Power Apps las pasa por posición):

| # | Clave interna | Título | Tipo | Obligatoria |
|---|---|---|---|---|
| 1 | `number` | ID SharePoint | número | sí |
| 2 | `text` | CLAVE_TRANSACCION | texto | sí (no se recorta; coincide exacta) |
| 3 | `text_1` | ESTUDIANTE | texto | sí |
| 4 | `text_2` | CODIGO_ESTUDIANTE | texto | sí en la firma técnica (`required`); **sin exigir contenido** (V4.1/V4.2): la app envía `""` |
| 5 | `text_3` | SOLICITADO_POR | texto | sí |
| 6 | `text_4` | SEDE_ASIGNACION | texto | sí |
| 7 | `text_5` | OBSERVACION | texto | sí en la firma técnica desde la V4.2 (`required`); **nunca se exige contenido**: puede ser `""` |
| 8 | `text_6` | USUARIO_ASIGNACION | texto | sí |

Los textos se recortan (`trim`) y se rechazan si exceden 255 caracteres (límite de la columna). La primera acción con lógica (`Entrada`) es el único lugar donde se asignan las claves del trigger a nombres lógicos.

Salidas (todas texto): `resultado`, `codigo`, `mensaje`, `estado_actual`, `asignado_por`, `fecha_hora_asignacion`.

| `resultado` | `codigo` | Cuándo | Llamadas SharePoint |
|---|---|---|---|
| `ASIGNADO` | `ASIGNADO` | Todo correcto | 2 |
| `NO_DISPONIBLE` | `NO_DISPONIBLE` | El estado ya no es `DISPONIBLE` (devuelve `estado_actual` y `asignado_por`) | 1 |
| `CONFLICTO` | `CONFLICTO` | El MERGE recibió 412 (ETag desactualizado) | 2 |
| `ERROR` | `CAMPOS_OBLIGATORIOS` | Falta un obligatorio (vacío o solo espacios) | 0 |
| `ERROR` | `CAMPO_EXCEDE_255` | Un texto > 255 caracteres | 0 |
| `ERROR` | `ID_INVALIDO` | ID < 1 o no entero | 0 |
| `ERROR` | `CLAVE_NO_COINCIDE` | La clave enviada no es la del elemento con ese ID | 1 |
| `ERROR` | `DEPOSITO_NO_ENCONTRADO` | GET devolvió 404 | 1 |
| `ERROR` | `ERROR_LECTURA` | GET falló (5xx, 429, timeout) | 1 |
| `ERROR` | `SIN_ETAG` | SharePoint no devolvió ETag; no se escribe | 1 |
| `ERROR` | `ACTUALIZACION_NO_CONFIRMADA` | MERGE falló distinto de 412 (timeout, 5xx, 400) | 2 |
| `ERROR` | `ERROR_NO_CONTROLADO` | Fallo antes de tocar SharePoint | 0–1 |

## 3. Instalación, paso a paso

### 3.1 Habilitar `ASIGNADO` (una sola vez, antes del flujo de asignación)

1. https://make.powerautomate.com → **Mis flujos** → **Importar** → **Importar paquete (heredado)** → **Cargar** → `P9_HABILITAR_ESTADO_ASIGNADO.zip`.
2. En **Contenido del paquete**, junto a la conexión de SharePoint → **Seleccionar durante la importación** → elige tu conexión de SharePoint → **Guardar** → **Importar**.
3. Abre el flujo `P9_HABILITAR_ESTADO_ASIGNADO` → **Probar** → **Manualmente** → **Probar** → **Ejecutar flujo**.
4. Abre la ejecución → acción **RESUMEN_FINAL** → **Salidas**. Esperado la primera vez: `"P9_HABILITAR_ESTADO_ASIGNADO": "OK"`, `"accion": "HABILITADO"`, `"opciones_despues": "DISPONIBLE|ASIGNADO"`, `"indices_creados": ["CODIGO_ASIGNACION","IMPORTE","TIPO_MOVIMIENTO"]`, `"indices_ya_existian"` con los otros 4, `"indices_verificados_al_final": 7`, `diferencias: []`. Una segunda ejecución debe dar `"accion": "NINGUNA"`, `"estado_antes": "YA_HABILITADO"`, `"indices_creados": []`, `"indices_ya_existian"` con los 7.
5. Si da `FAIL`, el flujo **no modificó nada** salvo, como mucho, intentar agregar la opción; lee `diferencias`. Alternativa manual equivalente: SharePoint → lista `Depositos_Activos` → ⚙ **Configuración de la lista** → columna `ESTADO_ASIGNACION` → agregar la opción `ASIGNADO` (sin tocar el predeterminado `DISPONIBLE`, sin permitir relleno) → **Aceptar**; luego ejecuta el flujo otra vez: solo verifica y debe dar `OK`.

### 3.2 Importar `P9_ASIGNAR_DEPOSITO`

1. Igual que 3.1 con `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip` (la V3 sirve solo si aún se exige el código de estudiante; **no uses la V4 ni la V4.1**). Quedará como flujo manual con trigger **Power Apps (V2)**.
2. **Conexión de SharePoint para los operadores** (decisión tuya, ver §6-5): flujo → **Detalles** → **Usuarios de solo ejecución** → **Editar** → SharePoint → **Usar esta conexión (tu usuario)**. Con eso los operadores solo necesitan permiso de *lectura* en la lista y el flujo escribe con tu conexión.
3. **Activar** el flujo.

### 3.3 Probar el flujo en el tenant SIN la app (obligatorio antes de publicar la app)

Necesitas `ID` y `CLAVE_TRANSACCION` de un depósito `DISPONIBLE`: en la lista, vista **Todos los elementos** → ⚙ → agrega la columna `ID` (o abre el elemento y toma `?ID=` de la URL) y copia la clave.

Flujo → **Probar** → **Manualmente** → **Probar** → completa los 8 campos → **Ejecutar flujo**. El resultado está en la acción **Responder a PowerApps** → **Salidas**.

| Prueba | Cómo | Esperado |
|---|---|---|
| T1 normal | ID y clave correctos, los 5 campos obligatorios | `ASIGNADO`; en la lista el elemento queda `ASIGNADO` con los campos y `FECHA_HORA_ASIGNACION` |
| T2 ya asignado | Repite T1 con el mismo elemento | `NO_DISPONIBLE`, `asignado_por` = el usuario de T1; el elemento no cambia |
| T3 clave | Cambia una letra de la clave en un elemento `DISPONIBLE` | `ERROR / CLAVE_NO_COINCIDE`; el elemento no cambia |
| T4 campos | Deja `ESTUDIANTE` vacío | `ERROR / CAMPOS_OBLIGATORIOS` |
| **T5 If-Match real** | Ver abajo | `CONFLICTO`; el elemento sigue `DISPONIBLE` con tu edición manual |

**T5 — comprueba que If-Match con ETag funciona en TU tenant** (es la única forma de saberlo; ver §6-1):

1. En el flujo → **Guardar como** → `P9_ASIGNAR_DEPOSITO_PRUEBA_ETAG` (copia desechable).
2. En la copia, dentro de la rama «sí» de la condición `Con_ETag`, **antes** de la acción `Ahora`, agrega **Retraso** de **1 minuto**. Guarda.
3. Ejecuta la copia con un depósito `DISPONIBLE`. Mientras espera, abre ese elemento en SharePoint y edita cualquier campo (p. ej. `OBSERVACION`) → guardar.
4. Al terminar el retraso, **Responder a PowerApps** debe mostrar `CONFLICTO` y la acción `Actualizar_deposito` debe estar en error 412. En la lista el elemento sigue `DISPONIBLE` y conserva tu edición.
5. Si en vez de eso da `ASIGNADO`, **If-Match no se está respetando**: no publiques la app y avísame. Borra la copia.

### 3.4 Pegar el frontend final en la app

1. Power Apps Studio → abre la app → pantalla donde irá el control → en **Vista de árbol** selecciona la pantalla.
2. Abre `p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt`, copia **todo** el contenido.
3. En el lienzo: clic derecho → **Pegar código** (o Ctrl+V sobre la pantalla). Debe aparecer el contenedor `cntControlDepositosP9`.
4. Orígenes de datos: `Depositos_Activos` (SharePoint) y el flujo `P9_ASIGNAR_DEPOSITO` (versión V3 con respuesta). Si el flujo se reimporta, quítalo y vuelve a agregarlo a la app para que Studio lea las 6 salidas.
5. Tras habilitar `ASIGNADO`, quita y vuelve a agregar el origen `Depositos_Activos` para que Power Apps vea la opción.

Comportamiento del frontend (base validada; los cambios de la iteración actual están en §9): lista solo `CRÉDITO` en estado `DISPONIBLE` o `ASIGNADO` (se muestra como `DISPONIBLE` / `CONFIRMADO`); filtros fecha desde/hasta, importe, banco → cuenta bancaria dependiente, código de asignación y `DESCRIPCIÓN contiene` (búsqueda en dos etapas: primero se filtra en origen y después se aplica el texto sobre ese resultado); muestra fecha, hora, banco, cuenta, importe, código, descripción, estado y datos de confirmación (usuario y fecha-hora). Botón `CONFIRMAR` solo sobre `DISPONIBLE` (sobre `CONFIRMADO` el botón dice `VER`). Al confirmar: valida 3 campos obligatorios (estudiante, solicitado por, sede; `OBSERVACION` es opcional y el código de estudiante ya no existe en la interfaz, ver §9), refresca, relee el registro por ID (si ya no está `DISPONIBLE` avisa y cierra), llama a `P9_ASIGNAR_DEPOSITO.Run(...)` con los 8 argumentos en orden, vuelve a refrescar/leer y decide por `varRespuestaP9.resultado` (`ASIGNADO`, `NO_DISPONIBLE`, `CONFLICTO`; cualquier otro valor muestra `ERROR (codigo): mensaje`). La app **no escribe** en SharePoint (sin `Patch`/`SubmitForm`/`Remove`); toda escritura pasa por el flujo.

## 4. Respuestas directas

* **Acciones del flujo `P9_ASIGNAR_DEPOSITO`: 35 acciones** definidas (recuento recursivo): 8 Redactar, 2 Inicializar variable, 12 Establecer variable, 8 Condición, 2 Ámbito (TRY/CATCH), 2 HTTP a SharePoint, 1 Responder a PowerApps. En el camino normal se **ejecutan 21**. `P9_HABILITAR_ESTADO_ASIGNADO` tiene 68 acciones (incluye el bucle de índices; en una ejecución con todo ya hecho solo hace 4 lecturas GET y 0 escrituras).
* **Llamadas SharePoint por asignación: 2** (GET + MERGE) en el camino normal y en `CONFLICTO`; 1 en `NO_DISPONIBLE` y errores de clave/lectura; 0 si las entradas son inválidas.
* **Conector premium: no.** Trigger Power Apps (V2) y Responder a PowerApps son integrados; «Enviar una solicitud HTTP a SharePoint» es del conector estándar de SharePoint (no el conector HTTP, que sí es premium). La clasificación efectiva depende de la política DLP del tenant y de la licencia de los usuarios; eso no se pudo verificar desde aquí.
* **¿If-Match funciona con el patrón del tenant ya usado en P8?** Es **el mismo patrón** (`HttpRequest` + `X-HTTP-Method: MERGE` + cabecera `IF-MATCH`) que P8 ejecutó en tu tenant, pero P8 solo lo usó con `IF-MATCH: *` (que acepta cualquier versión). Con un **ETag concreto no está validado en tu tenant**: lo único probado es el simulador local. Por diseño SharePoint responde 412 si el ETag no coincide y el flujo lo traduce a `CONFLICTO`; la prueba **T5** (§3.3) lo comprueba de verdad. Adicionalmente, el cuerpo del MERGE usa `Content-Type: application/json;odata=nometadata` sin `__metadata` (P8 envía `odata=verbose` con `__metadata` porque modifica columnas, no elementos): también es un supuesto a confirmar con T1.
* **Limitaciones reales:** §6.

## 5. `P9_HABILITAR_ESTADO_ASIGNADO`: qué hace exactamente

**Parte A — opciones de `ESTADO_ASIGNACION`**, leída por `InternalName`:

| Opciones actuales | Acción |
|---|---|
| `DISPONIBLE` (y es tipo Choice) | MERGE de la columna: opciones = `DISPONIBLE`, `ASIGNADO` (misma cabecera `IF-MATCH: *` que usó P8 para columnas) |
| `DISPONIBLE`, `ASIGNADO` | No escribe |
| Cualquier otra cosa | No escribe las opciones; reporta `FAIL` |

Después vuelve a leer y verifica: `InternalName`, tipo Choice, obligatoria, no oculta, predeterminado `DISPONIBLE`, sin relleno libre y opciones exactamente `DISPONIBLE|ASIGNADO`. Solo existen esos dos estados.

**Parte B — los 7 índices de `Depositos_Activos`.** Lee los campos una sola vez y, por cada índice:

| Índice | Origen | Qué hace el flujo |
|---|---|---|
| `ESTADO_ASIGNACION`, `FECHA_MOVIMIENTO`, `BANCO`, `LOTE_CARGA` | ya creados por P8 | **Solo verifica**; si faltara alguno, lo crea (no falla) |
| `CODIGO_ASIGNACION`, `IMPORTE`, `TIPO_MOVIMIENTO` | nuevos de P9 | **Crea** si no está indexado; si ya lo está, no lo recrea |

* Crear = un MERGE `{"Indexed": true}` sobre la columna **ya existente** (mismo patrón REST de P8, `IF-MATCH: *`). Es lo único que se envía: nunca `Indexed: false`, nunca se elimina un índice ni se crean/borran columnas.
* Si una columna no existe (o hay duplicados) o la respuesta de campos llega paginada, no crea nada de ese índice y lo reporta.
* Si falla la creación de uno (403, 500, timeout), lo registra como `INDICE_NO_CREADO` con el código HTTP, **sigue con los demás**, y la verificación final lo confirma como `INDICE_AUSENTE_O_NO_INDEXADO`; el flujo termina `Failed`. Al corregir la causa y reejecutar, crea solo el que faltaba.
* Verificación final: vuelve a leer los campos y comprueba que los 7 estén indexados (`indices_verificados_al_final` debe ser 7).
* `CLAVE_TRANSACCION` (índice único de P8) no forma parte de los 7: no se toca ni se verifica.

`RESUMEN_FINAL` incluye `indices_esperados`, `indices_creados`, `indices_ya_existian` e `indices_verificados_al_final`.

El flujo **no lee ni modifica elementos**, no crea ni borra columnas y no toca las 26 columnas del motor. Las partes A y B son independientes: si las opciones están en un estado inesperado igual se crean/verifican los índices (operación inocua), y el resultado final es `FAIL`. **Supuestos no verificados en tenant:** que SharePoint acepte el MERGE de `Choices` con `Collection(Edm.String)` y el MERGE de `Indexed` con el tipo de metadatos de cada columna (`SP.FieldText`, `SP.FieldNumber`, `SP.FieldDateTime`, `SP.FieldChoice`). Alternativa manual para las opciones: §3.1-5; para los índices: Configuración de la lista → *Índices* → *Crear un nuevo índice* y luego reejecuta el flujo (solo verifica).

## 6. Limitaciones reales (leer antes de importar)

1. **Qué está validado y qué no.** Validado por el usuario en el tenant: backend V3 + frontend final + una confirmación real (ver cabecera). Las pruebas del repositorio usan un intérprete WDL local y un SharePoint simulado (incluye ETag/412 y concurrencia con hilos) y revisión estática del YAML: prueban la lógica y el contrato, no el runtime. **No** consta como validado en tenant: la prueba de conflicto de ETag concreto (T5, §3.3) ni la conducta con dos usuarios simultáneos reales, y el flujo `P9_HABILITAR_ESTADO_ASIGNADO` salvo lo que el usuario haya ejecutado.
2. **Orden de instalación:** si no se ejecuta antes `P9_HABILITAR_ESTADO_ASIGNADO`, SharePoint rechaza el valor `ASIGNADO` y el flujo responde `ERROR / ACTUALIZACION_NO_CONFIRMADA` (el depósito sigue `DISPONIBLE`; probado).
3. **Re-ejecutar el provisionador P8 después de P9 dará `FAIL`** en `ESTADO_ASIGNACION / Choices` (su contrato dice solo `DISPONIBLE`). No repara ni escribe (probado con su simulador). Se dejó `p8/esquema_listas_p8.json` intacto a propósito; actualizar el contrato P8 es un cambio aparte que decides tú tras validar P9.
4. **`USUARIO_ASIGNACION` lo envía la app** (`User().Email`). Cualquiera que pueda invocar el flujo podría enviar otro correo; el flujo solo exige que no esté vacío. Endurecerlo (tomar la identidad del propio trigger) no se implementó porque no pude verificar esa cabecera en tu tenant.
5. **Quién figura en «Modificado por»:** con «Usar esta conexión (tu usuario)» el historial de SharePoint dirá que siempre modificó el dueño de la conexión; el operador queda solo en `USUARIO_ASIGNACION`. Con conexión del propio operador, «Modificado por» sí es el operador, pero necesita permiso de edición sobre la lista (y podría editarla a mano). Elige según auditoría; no hay seguridad por columna.
6. **Es un sitio personal (OneDrive)** (`/personal/gtorricot_univalle_edu`): los operadores del piloto necesitan acceso de lectura a esa lista (o a ese sitio) para que la app la lea. Es una restricción del piloto.
7. **`equals` de WDL entre textos** se asume sensible a mayúsculas (así lo documentan los tutoriales de Power Automate; no lo probé en el tenant). Si no lo fuera, una clave que difiera solo en mayúsculas pasaría; el ID es la identificación principal y la clave es una comprobación adicional.
8. **Claves del trigger (`number`, `text`, `text_1`…):** son las que genera el diseñador de Power Apps (V2). Si editas el trigger en el diseñador (agregar/quitar entradas) pueden renumerarse; las fórmulas de `Run(...)` van por posición, no por nombre. Verifica la firma que muestra Studio al escribir `P9_ASIGNAR_DEPOSITO.Run(`.
9. **Delegación y umbral de 5000:** el frontend final funciona en el tenant, pero la galería usa patrones `IsBlank(x) || …` y, en la segunda etapa de `DESCRIPCIÓN contiene`, filtra localmente un conjunto ya filtrado en origen (el resultado está sujeto al límite de filas de datos de la app). Revisa las advertencias de delegación en Studio con tu volumen real. `P9_HABILITAR_ESTADO_ASIGNADO` ya indexa `CODIGO_ASIGNACION`, `IMPORTE` y `TIPO_MOVIMIENTO`, pero eso no elimina el límite de SharePoint: con >5000 elementos una consulta puede fallar por umbral de vista si su primer filtro indexado devuelve más de 5000 filas (p. ej. todos los `DISPONIBLE`). Conviene acotar por fecha en producción.
10. **Sin reversión:** una asignación equivocada solo se corrige editando el elemento a mano en SharePoint. Es decisión de alcance (no hay reasignación/anulación).
11. **Solo `CRÉDITO` se filtra en la app**, no en el flujo: el flujo asigna cualquier tipo si se le invoca directamente. La regla de qué tipo se puede asignar en el backend sigue sin aprobarse.
12. **`Value()` y regional:** los importes del filtro se escriben con el separador decimal de la configuración regional del usuario (en es-BO, la coma).
13. **Concurrencia del trigger:** no se limita a 1 ejecución a propósito; la exclusión la da el ETag, no una cola. Si prefieres serializar además, se agrega en la configuración del trigger.
14. **Piloto:** `Depositos_Activos` tiene 10 elementos según la validación V5. Para volúmenes reales hay que revisar el umbral de vista (punto 9).

## 7. Pruebas locales (`tests/test_16`, `test_18`, `test_21`, `test_22`)

Ejecutar desde la raíz del repo: `python -m pytest tests/test_16_asignacion_p9.py tests/test_18_asignar_powerapps_v2.py tests/test_21_respuesta_v3_p9.py tests/test_22_frontend_final_p9.py -q`.

| Pedido | Pruebas |
|---|---|
| Asignación normal | `test_asignacion_normal` (8 columnas, ETag, 2 llamadas, 21 acciones, resto de filas intactas), `test_observacion_es_opcional_...` |
| Clave incorrecta | 6 variantes (vacía, prefijo, espacio, minúsculas, otra clave, truncada) + ID de otro depósito con clave ajena |
| Ya asignado | `NO_DISPONIBLE`, no pisa la primera asignación, ni intenta escribir |
| Dos intentos concurrentes | 15 repeticiones con 2 hilos y barrera: siempre 1 `ASIGNADO` + 1 `CONFLICTO`, una sola escritura efectiva. Comprobado que un mutante con `If-Match: *` produce 2 `ASIGNADO` |
| ETag desactualizado | Otro usuario edita entre lectura y MERGE → `CONFLICTO`, sin escritura ni reintento |
| Campos obligatorios vacíos | 5 campos × 3 vacíos, nulos/ausentes, >255, ID inválido: 0 llamadas a SharePoint |
| 26 columnas del motor | Valores idénticos tras 8 asignaciones; el cuerpo del MERGE nunca incluye una; los 26 nombres coinciden con `adaptador_m365`, el motor y `esquema_listas_p8.json`; los 72 archivos del commit base sin cambios |
| Reproceso P8 | La carga P8 sobre elementos ya `ASIGNADO` da 0 NUEVA / 8 YA_EXISTE y deja todos los campos intactos; P8 solo usa `GetFileContent`/`GetItems`/`PostItem` |
| Habilitar (opciones) | Agrega `ASIGNADO`, idempotente, sin tocar elementos; opciones inesperadas → FAIL sin escribir; propiedades distintas; errores REST |
| Habilitar (índices) | Los 7 ya existen (0 escrituras); faltan los 3 nuevos; falta cada uno de los 4 antiguos; falta uno antiguo + los nuevos; dos ejecuciones seguidas; fallo al crear uno (500, 403, timeout) con recuperación al reejecutar; fallo al leer campos; columna ausente; respuesta paginada; ningún elemento ni versión modificados; las 26 columnas intactas; solo 2 estados; el flujo solo puede enviar `Indexed: true` |
| Fallos REST | 404, 5xx, timeout al leer; 5xx/timeout/400 al escribir; sin ETag |
| Backend V3 | Único cambio respecto de V2 = las 6 marcas de salidas; mismo comportamiento y concurrencia; 8 entradas idénticas (`test_18`, `test_21`) |
| Frontend final | SHA-256 fijado; control raíz ManualLayout; sin `Patch`/`SubmitForm`/`Remove`/AutoLayout; 8 argumentos de `Run` en orden; solo lee `resultado`/`codigo`/`mensaje`; solo `Depositos_Activos`, solo `CRÉDITO`; observación opcional; trazabilidad de quién y cuándo (`test_21`, `test_22`). Revisión estática, **no** ejecución en Studio |

Estas pruebas **no** certifican Microsoft 365 (ver §6-1).

## 8. Migración a producción (sitio institucional)

1. Provisionar las listas en el sitio institucional con el provisionador P8 y ejecutar allí `P9_HABILITAR_ESTADO_ASIGNADO`.
2. En `p9/contrato.py` cambiar `SITIO_SHAREPOINT` y `LISTA_DEPOSITOS_ACTIVOS_ID`, regenerar los ZIP (`python -m p9.asignar.construir`, `python -m p9.asignar.convertir_powerapps_v2`, `python -m p9.asignar.convertir_powerapps_v3`, `python -m p9.habilitar.construir`) — o editar a mano las dos acciones `PARAM_SITIO_SHAREPOINT` y `PARAM_LISTA_DEPOSITOS_ACTIVOS` al inicio de cada flujo (son las únicas que contienen el sitio y la lista).
3. En la app, agregar el origen de datos del sitio institucional.

## 9. Iteración: sin código de estudiante y ventana de 2 meses

**Estado: VALIDADO EN EL TENANT con la V4.2 + el frontend vigente.** Comprobado por el usuario: Power Apps sin errores; el flujo acepta los 8 argumentos posicionales; confirmación real ejecutada; `CODIGO_ESTUDIANTE` vacío y `OBSERVACION` vacía funcionan; `Depositos_Activos` se actualiza en SharePoint; el estado visible pasa de `DISPONIBLE` a `CONFIRMADO`; usuario y fecha/hora de confirmación quedan registrados; la ventana de los últimos 2 meses funciona; el frontend completo carga. Pruebas locales en `tests/test_22` y `tests/test_24`. Sin cambios en arquitectura ni en la concurrencia (ETag / If-Match / MERGE).

### 9.1 Código de estudiante fuera de la experiencia operativa

* **Power Apps:** se quitaron la etiqueta y el campo `CÓDIGO ESTUDIANTE`, sus `Reset`, su validación y el texto del aviso (ahora «Completa Estudiante, Solicitado por y Sede.»). El modal no lo muestra en ninguna parte. Los campos `SOLICITADO POR` y `SEDE` se reubicaron para no dejar un hueco (solo cambian X/Y).
* **Firma de `.Run(...)` (V4.2):** los 8 inputs del trigger están en `required`, así que Power Apps los recibe como **8 argumentos posicionales**, sin registro opcional: `P9_ASIGNAR_DEPOSITO.Run(ID, CLAVE_TRANSACCION, Trim(txtEstudianteP9.Text), "", Trim(txtSolicitadoP9.Text), Trim(txtSedeP9.Text), Trim(txtObservacionP9.Text), User().Email)`. El 4.º (`CODIGO_ESTUDIANTE`) va como `""`; `OBSERVACION` (7.º) puede ir vacía. `required` es solo presencia del parámetro técnico; el contenido lo valida `Validar_entrada` (exige clave, estudiante, solicitado por, sede y usuario; no exige código de estudiante ni observación).
* **Power Automate (V4.2):** el trigger es el de la V3 con **`text_5` también en `required`** (los 8 inputs, mismo orden). Respecto de la V3, `Validar_entrada` ya no comprueba que `CODIGO_ESTUDIANTE` tenga contenido, así que acepta `""`. El flujo sigue escribiendo la columna `CODIGO_ESTUDIANTE` (vacía); el límite de 255 caracteres se conserva.
* **SharePoint:** la columna `CODIGO_ESTUDIANTE` **no se elimina** ni se modifica (no es obligatoria en la lista). Los datos históricos con código se conservan; una asignación ya hecha no se reescribe.
* **El «CÓDIGO» de la tabla y el filtro `CÓDIGO ASIGNACIÓN` son otra cosa** (código del movimiento bancario, `CODIGO_ASIGNACION`) y se mantienen.
* **Al importar la V4.2:** importa con «Actualizar» (mismo ID de flujo) o desactiva/elimina la versión anterior si «Crear como nuevo»; en Studio quita y vuelve a agregar el flujo `P9_ASIGNAR_DEPOSITO` para que relea la firma, y comprueba que `.Run(...)` no marca errores (8 posicionales). El frontend nuevo y el flujo V4.1 deben ir juntos; con la V3 la app fallaría con `CAMPOS_OBLIGATORIOS` (el código llega vacío).

**Por qué la V4 se descartó (hallazgo del tenant).** La V4 quitó `text_2` del array `required` del trigger. Power Automate seguía mostrando los 8 inputs, pero Power Apps, al volver a agregar el flujo, marcó `.Run(...)` con «recibe 8 argumentos, cuando espera entre 6 y 7»: el `required` del trigger forma parte de la firma que Power Apps construye. **Regla: no tocar `required` ni los inputs del trigger; la flexibilidad se resuelve en la validación de contenido.** No pude reproducir cómo Power Apps calcula esa aridad; la corrección se apoya en que el trigger de la V4.1 es idéntico, nodo a nodo, al de la V3 con la que sí se validó la llamada de 8 argumentos (`tests/test_23`). Queda por confirmar en el tenant que Power Automate acepta `""` en un input que está en `required` (para el esquema JSON basta con que la clave esté presente y sea texto).

**Segundo hallazgo (V4.1 en el tenant).** Con `text_2` restaurado, Power Apps aceptó la cantidad de argumentos pero marcó «Text donde se espera Record»: en la V4.1 `text_5` (OBSERVACION) seguía fuera de `required`, y Power Apps tomó los 7 requeridos como posicionales y el opcional como un registro final (el nombre de su campo no se podía confirmar sin Studio). **V4.2** pone también `text_5` en `required` (cambio mínimo, solo ese nodo) y el frontend vuelve a la llamada simple de 8 posicionales, sin registro opcional. Queda por confirmar en el tenant que Power Automate acepta `""` en inputs que están en `required` (para el esquema JSON basta con que la clave esté presente y sea texto).

### 9.2 Ventana temporal de 2 meses

* Al abrir: `FECHA DESDE` = `DateAdd(Today(), -2, TimeUnit.Months)` y `FECHA HASTA` = `Today()` (`DefaultDate`; `LIMPIAR` vuelve a estos valores).
* **Límite duro en la fórmula de la galería**, no solo en los selectores: en las dos etapas de `galDepositosP9.Items` se agregó, como argumentos propios de `Filter` (AND) y antes de los filtros del usuario, `FECHA_MOVIMIENTO >= DateAdd(Today(), -2, TimeUnit.Months)` y `FECHA_MOVIMIENTO <= Today()`. Aunque el usuario elija una fecha anterior, no aparecen registros de más de 2 meses.
* Se mantiene el enfoque de dos etapas: (1) filtro base delegable en SharePoint (estado, `CRÉDITO`, ventana, importe, banco → cuenta, código de asignación); (2) filtro local `DESCRIPCIÓN contiene` sobre ese resultado. No se usa `StartsWith` en `DESCRIPCION`.
* El aviso bajo «INGRESOS» indica «Últimos 2 meses (desde dd/mm/aaaa)».
* **Solo es una restricción de la experiencia de Power Apps:** SharePoint conserva todo el histórico; no se borra ni archiva nada.
* **Qué no se hizo:** no se bloquea el calendario del selector (`DatePicker` no tiene fecha mínima; agregar `OnChange` no está en las propiedades verificadas en los exports reales). Elegir una `FECHA DESDE` anterior no tiene efecto: rige el límite.
* **Por confirmar en Studio:** que `galDepositosP9.Items` no muestre advertencias de delegación nuevas con `DateAdd(Today(), -2, TimeUnit.Months)` y `Today()`; el patrón es el habitual para columnas de fecha de SharePoint, pero no se pudo abrir Studio aquí.
