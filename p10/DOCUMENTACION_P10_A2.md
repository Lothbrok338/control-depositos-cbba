# P10-A.2 — Sincronización automática del histórico mensual

> **Estado: IMPLEMENTADO Y PROBADO LOCALMENTE · EN DESPLIEGUE (por pasos, con Gabriel). Por decisión de Gabriel no se ejecutan más suites/simulaciones en esta fase.**
> Todo lo de esta carpeta es aditivo. No se modificó P0, P7, P8, P9, el motor, `historico.py` ni el generador **P10-A.1 (CERRADO Y VALIDADO LOCALMENTE)**; una prueba (`p10/huellas_cerradas.json`) lo verifica con SHA-256.
> No se hizo ningún cambio en Microsoft 365 ni en Railway. Los pasos para hacerlo, uno por uno, están en la sección 18.
> P10-B (limpieza de `Depositos_Activos`) **no** está hecho: ningún flujo de P10-A.2 escribe en `Depositos_Activos` (una prueba estática lo comprueba).

## 0. Qué hace, en una frase

El usuario solo suelta el extracto en `ENTRADA` y trabaja en Power Apps. Cada 15 minutos un flujo de Power Automate pregunta al servicio `p10-api` (Railway, sin estado) «¿qué cambió?», y mantiene **un único libro Excel por BANCO + CUENTA + MONEDA + MES** en `/CONTROL_DEPOSITOS/P10_HISTORICO/AAAA/MM_MES/BANCO/EXTRACTO_HISTORICO_<BANCO>_<CUENTA>_<MONEDA>_<AAAA-MM>.xlsx`, con el diseño aprobado en A.1 (hojas `EXTRACTO` y `AUDITORIA`, 28 columnas en AUDITORIA, sin paneles inmovilizados, sin columnas de sistema de SharePoint).

## 1. Arquitectura final realmente implementada

```
 ENTRADA ─ P0 (sin cambios) ─▶ PROCESADOS/AAAA/MM_MES/DD/<original>       JSON P7 ─ P8 ─▶ Depositos_Activos ◀─ Power Apps / P9
                                    │  (el original NO se toca)                              │ (confirmar / revertir / modificar)
                                    ▼                                                        ▼
                       ┌──────────────────────────  P10_SINCRONIZAR_HISTORICO  (Power Automate, cada 15 min, 1 ejecución a la vez) ─────┐
                       │  1 lee P10_Control · bloqueo lógico con vigencia (un solo escritor)                                              │
                       │  2 FASE A  extractos nuevos de PROCESADOS  ──▶ /p10/extracto  (MOTOR REAL de P0)                                 │
                       │  3 FASE B1 filas de Depositos_Activos con Modified > cursor ─▶ /p10/delta                                         │
                       │  4 FASE B2 conciliación BANCO+MES con la lista completa ──────▶ /p10/clasificar  (noche · errores · tras extracto)│
                       │  5 por grupo: leer estado ─▶ /p10/sincronizar ─▶ escribir XLSX ─▶ escribir estado ─▶ confirmar en el control       │
                       └──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        Railway  p10-api (stateless, 1 worker, SIN volumen ni base de datos)        OneDrive                                    SharePoint
          · motor de P0 (p0.nucleo) · generador A.1 (sin cambios)                    P10_ESTADO/…/ESTADO_P10_….json.gz           P10_Control (lista)
          · decide y calcula; no guarda nada                                         P10_HISTORICO/…/EXTRACTO_HISTORICO_….xlsx     · LOCK + cursor
                                                                                     P10_CONFIG/P10_API_TOKEN.txt                  · GRUPO / EXTRACTO
```

**Dónde vive el estado canónico y por qué.**

| Opción | Veredicto |
|---|---|
| XLSX como base de datos | **No.** Es una vista: se puede borrar, abrir, alterar. |
| Volumen / base de datos en Railway | **No.** Pediste evitar almacenamiento persistente en Railway; además ataría el histórico a un proveedor y a un volumen. |
| Una fila de lista de SharePoint por movimiento | **No.** Duplicaría `Depositos_Activos` (>5000 filas, umbral de vista), más lento y más caro en acciones. |
| **Un archivo `.json.gz` por grupo en OneDrive (`P10_ESTADO`) + un registro pequeño en `P10_Control`** | **Sí.** Es durable, versionable por OneDrive, sin servicios nuevos, regenerable desde los extractos originales, y el control (SharePoint) guarda *aparte* la versión y el sello del último estado confirmado, de modo que se detecta manipulación o retroceso. |

El **estado canónico** de un grupo (`p10/estado.py`) contiene: los movimientos tal como los entregó el motor de P0 (las 26 columnas y las celdas originales), la cabecera del extracto, la última información operativa conocida de cada movimiento (estado, estudiante, usuario, fecha…), el sello del XLSX que debe existir y un sello de integridad (SHA-256) del propio estado. De ahí se reconstruye el XLSX completo con el generador aprobado de A.1 (byte a byte determinista).

## 2. Componentes

| Archivo | Responsabilidad |
|---|---|
| `p10/estado.py` | Estado canónico por grupo: fusión de extractos **acumulativos** (unión por CLAVE; el mismo archivo mensual crece 1000→1700), aplicar la información de la lista (la lista manda; las filas ausentes NO se borran), sellos de integridad, reconstrucción de las entradas de A.1. |
| `p10/sincronizacion.py` | Dos operaciones con efectos: `procesar_extracto` (**usa `p0.nucleo` = el motor real de P0**; no normaliza nada) y `sincronizar_grupo` (estado + parciales + filas → estado nuevo + XLSX con **el generador A.1 sin cambios**, validado contra sus fuentes antes de entregarlo). |
| `p10/plan.py` | Decisiones puras y probadas: bloqueo, modo NORMAL/COMPLETO, qué extractos incorporar, lectura incremental (`delta`), conciliación (`clasificar`), reconstrucción. |
| `p10/sharepoint.py` | Elemento REST de `Depositos_Activos` → fila de P10. Hora UTC → hora de Bolivia. El mes de un movimiento sale de su **CLAVE TRANSACCIÓN** (no de la columna de fecha, que es «solo fecha»). |
| `p10/api.py`, `p10/Dockerfile`, `p10/railway.json` | Servicio HTTP (FastAPI) **separado de `p0-api`**. |
| `p10/control_lista.py` | Contrato de la lista `P10_Control`. |
| `p10/flujo/construir.py` | Genera los dos flujos y sus ZIP importables (deterministas). |
| `p10/ensayo_wdl.py`, `p10/tenant_simulado.py`, `p10/lista_simulada.py` | Para pruebas: intérprete local de los flujos reales + tenant simulado (OneDrive, SharePoint, `Depositos_Activos` con las escrituras de P9). **No son SharePoint.** |
| `p10/huellas.py`, `p10/huellas_cerradas.json` | SHA-256 de lo cerrado (A.1) y de lo reutilizado sin cambios. |
| A.1 (sin cambios): `contrato.py`, `snapshot.py`, `generador.py`, `validacion.py`, `comparar.py`, `snapshot_simulado.py`, `motor_p0.py`, `empaque.py` | Generador aprobado. |

**No hay un segundo normalizador.** `crear_clave` y las reglas por banco se ejecutan una sola vez, dentro del motor de P0. P10 recibe de ese motor la CLAVE TRANSACCIÓN y las 26 columnas; una prueba comprueba que no hay código de normalización en los módulos de P10 y que las claves de P10 son exactamente las de P0.

## 3. Flujos de Power Automate (importables)

| Flujo | ZIP | Acciones | Para qué |
|---|---|---|---|
| `P10_SINCRONIZAR_HISTORICO` | `P10_SINCRONIZAR_HISTORICO_V1.zip` | 162 (límite de PA: 500) · anidamiento ≤ 8 | El sincronizador. Disparador *Recurrence*: cada 15 min, de 06:00 a 22:45 hora de Bolivia, **concurrencia 1**, máx. 1 en espera. |
| `P10_PROVISIONAR_CONTROL` | `P10_PROVISIONAR_CONTROL_V1.zip` | 23 | Botón de una sola vez: crea la lista `P10_Control` (28 columnas, índices, único en `CLAVE_CONTROL`) y su elemento `LOCK`. Idempotente. |

Estructura del sincronizador (los nombres son los de las acciones del flujo):

1. `P` (Compose con la configuración) · `Leer_token` (OneDrive, salida segura) · `Leer_control` (SharePoint) · `Ciclo_API`.
2. Si el servicio rechaza el ciclo → termina *Failed*. Si otra ejecución tiene el bloqueo vigente → termina *Succeeded* sin hacer nada.
3. `Adquirir_lock`: un `MERGE` con `IF-MATCH = ETag` del elemento `LOCK` (compare-and-swap). Si falla (otra ejecución llegó primero) → termina sin trabajar (`Lock_perdido`).
4. `MAIN` (Scope):
   * **Fase A** — lista `PROCESADOS/AAAA/MM_MES` (carpetas de los meses indicados por el ciclo, `Folders?$expand=Files`), `Plan` decide los extractos nuevos/modificados/en reintento/a reconstruir y, **por cada extracto**: leer archivo → `/p10/extracto` → por cada grupo → bloque de grupo → anotar el extracto en el control (marca de «ya incorporado»).
   * **Fase B1** — `D_GET`: una sola lectura de `Depositos_Activos` con `Modified > cursor` (columna indexada). Casi siempre vacía. Si hay filas → `/p10/delta` → bloque de grupo por cada grupo con cambios → avanzar el cursor (`CURSOR_LISTA` en `LOCK`).
   * **Fase B2** — `Cada_slice`: por cada **BANCO + MES** a conciliar (noche, grupos con error/reconstrucción, grupos que acaban de cambiar por un extracto) lee **solo ese banco y ese mes** de la lista, `/p10/clasificar`, bloque de grupo.
5. `CATCH_MAIN` anota un fallo general. `Liberar_lock` **siempre** (y marca `ULTIMA_COMPLETA` solo si fue un ciclo completo sin fallos). `Cierre`: si hubo fallos, termina *Failed* con la lista (para que lo veas en el historial y en el aviso de Power Automate).
6. **Bloque de grupo** (el mismo para extracto, delta y conciliación): leer control del grupo (fresco) → leer estado (si no existe → «falta»; cualquier error ≠ 404 es fallo técnico, nunca «falta») → `/p10/sincronizar` → **escribir XLSX → escribir estado → escribir control** (el control es la marca de confirmación). Un fallo técnico de un grupo se anota y no detiene a los demás.

Funciones de WDL: todas las expresiones de ambos flujos se analizan en una prueba y solo pueden usar funciones reales de WDL.

## 4. Railway: `p10-api`

* Servicio **nuevo**, separado de `p0-api` (no se toca el Dockerfile, `railway.json` ni `requirements-p0.txt` de la raíz). Imagen: `p10/Dockerfile` (mismos archivos del motor que P0 + `p10/`, `p9/contrato*.py`).
* Sin volumen, sin base de datos, sin bucket. 1 worker (el motor de P0 cambia variables de entorno por corrida). Memoria medida con el extracto más grande (BCP, 2 331 movimientos): ~170 MB; ~3 s por grupo.
* Variable obligatoria: `P10_API_TOKEN` (≥ 16 caracteres; sin ella el servicio responde 503 a todo). Opcional: `P10_MAX_BYTES` (80 MB por defecto).
* Endpoints (todos `POST /p10/<operación>`, JSON, `Authorization: Bearer <token>`; `GET /health` sin autenticación):

| Operación | Entrada | Salida |
|---|---|---|
| `ciclo` | hora local, filas de `P10_Control` | bloqueo, modo, meses a listar, `cursor_desde`, `slices` a conciliar, grupos a verificar, límite de extractos |
| `plan` | archivos de PROCESADOS + control | extractos a incorporar (razón: NUEVO/MODIFICADO/REINTENTO/RECONSTRUIR) |
| `extracto` | un extracto (Base64) | parciales por BANCO+CUENTA+MONEDA+MES + registro de control (PROCESADO/ERROR/ERROR_FINAL) |
| `delta` | filas modificadas de la lista + control | grupos a actualizar + cursor nuevo |
| `clasificar` | filas de un BANCO+MES + control | grupos a sincronizar (cambio, error por reintentar, verificación, fin de reconstrucción) |
| `sincronizar` | estado, parciales, filas, control del grupo, XLSX actual | estado nuevo (si cambió), XLSX nuevo (si cambió), registro de control |

* Logs técnicos (sin contenido bancario). Un extracto rechazado por reglas de negocio responde 200 con `ok:false` y su registro listo; solo un fallo del propio servicio responde 5xx.

## 5. SharePoint: lista `P10_Control` (nueva) y `Depositos_Activos` (solo lectura)

`P10_Control` — creada por `P10_PROVISIONAR_CONTROL`, en el mismo sitio que `Depositos_Activos`. Tres tipos de elemento (columna `TIPO`):

| TIPO | Cuántos | Qué guarda |
|---|---|---|
| `LOCK` | 1 | `LOCK_HASTA`, `LOCK_ID` (bloqueo con vigencia de 60 min), `ULTIMA_COMPLETA` (fecha del último ciclo completo), `CURSOR_LISTA` (hasta dónde se leyó `Depositos_Activos`, UTC) |
| `GRUPO` | 1 por BANCO+CUENTA+MONEDA+MES | `ESTADO` (OK/ERROR/RECONSTRUIR/PENDIENTE), `VERSION_ESTADO` y `HASH_ESTADO` (sello del último estado confirmado), `HASH_XLSX`, rutas, `HASH_OPERATIVO` (última conciliación completa con la lista), `INTENTOS`, `RECONSTRUIR_DESDE`, `DETALLE` |
| `EXTRACTO` | 1 por archivo de PROCESADOS | `ESTADO` (PROCESADO/ERROR/ERROR_FINAL), `BYTES`, `HASH_EXTRACTO`, `GRUPOS` que alimentó, `INTENTOS` — es lo que vuelve **idempotente** al ciclo |

Columnas (todas texto o número; **ninguna fecha de SharePoint**, para evitar conversiones de zona horaria): `CLAVE_CONTROL` (única, indexada), `TIPO` e `PERIODO` (indexadas), `ESTADO`, `BANCO`, `CUENTA`, `MONEDA`, `RUTA_XLSX`, `RUTA_ESTADO`, `HASH_OPERATIVO`, `HASH_INTENTO`, `HASH_ESTADO`, `HASH_XLSX`, `HASH_EXTRACTO`, `CURSOR_LISTA`, `ULTIMA_SYNC`, `RECONSTRUIR_DESDE`, `LOCK_HASTA`, `LOCK_ID`, `ULTIMA_COMPLETA`, `VERSION_ESTADO`, `ESTADO_BYTES`, `XLSX_BYTES`, `MOVIMIENTOS`, `INTENTOS`, `BYTES`, `GRUPOS` (texto largo), `DETALLE` (texto largo). Una prueba verifica que todo campo que el servicio devuelve existe en esta lista.

`Depositos_Activos`: solo `GET`. Columnas leídas: `Id, Modified, CLAVE_TRANSACCION, BANCO, CUENTA_BANCARIA, MONEDA, FECHA_MOVIMIENTO, ESTADO_ASIGNACION, ESTUDIANTE, CODIGO_ESTUDIANTE, SOLICITADO_POR, SEDE_ASIGNACION, USUARIO_ASIGNACION, FECHA_HORA_ASIGNACION, OBSERVACION, ULTIMA_REVERSION_ID, LOTE_CARGA, FECHA_CARGA, ARCHIVO_ORIGEN` (una prueba las contrasta con el esquema real de P8). **Único cambio recomendado en esa lista: un índice en `Modified`** (sección 18.3, punto 5); `BANCO` y `FECHA_MOVIMIENTO` ya están indexadas.

## 6. Variables y configuración

| Dónde | Nombre | Valor | Se cambia cuando… |
|---|---|---|---|
| Flujo, acción `P` | `url_api` | `https://<PEGAR_DOMINIO_P10_RAILWAY>.up.railway.app` → **tu dominio de Railway** | una sola vez |
| Flujo, acción `P` | `sede` | `CBBA` (igual que P0) | nunca |
| Flujo, acción `P` | `prefijo_servidor` | `/personal/gtorricot_univalle_edu/Documents` | si cambia la biblioteca de OneDrive |
| Flujo, acción `P` | `mes_inicio` | `2026-08` — primer mes que el ciclo completo mira en PROCESADOS (hasta 12 meses hacia atrás) | **decidido por Gabriel: 2026-08** |
| Flujo, disparador | horas / minutos | 06–22 / 0, 15, 30, 45 (hora de Bolivia) | para ajustar consumo |
| OneDrive | `/CONTROL_DEPOSITOS/P10_CONFIG/P10_API_TOKEN.txt` | el token (solo el texto) | al rotar el token |
| Railway | `P10_API_TOKEN` | el mismo token (≥ 16 caracteres) | al rotar el token |
| Código (`p10/plan.py`) | `MAX_INTENTOS=3`, `LEASE_MINUTOS=60`, `VENTANA_MESES=3`, `HORA_COMPLETA=2`, `ASENTAR_MIN=5`, `MAX_EXTRACTOS_NORMAL=10` / `COMPLETO=60` | | no se cambian sin probar |

El token **no** está en el repositorio ni en el flujo: el flujo lo lee del archivo de OneDrive (salida segura, nunca visible en el historial) y lo manda en `Authorization`.

## 7. De ENTRADA al histórico (explicación simple)

1. Sueltas el extracto en `ENTRADA`. **P0, P7 y P8 hacen lo de siempre**: el original queda en `PROCESADOS/AAAA/MM_MES/DD/` y los movimientos van a `Depositos_Activos`. Nada de eso cambió.
2. En el siguiente ciclo (≤ 15 min), P10 ve un archivo nuevo en `PROCESADOS` que no está anotado en `P10_Control`.
3. Lo lee y se lo manda a `p10-api`, que lo procesa con **el mismo motor de P0** y devuelve los movimientos separados por BANCO + CUENTA + MONEDA + MES (un extracto de octubre con movimientos de septiembre alimenta dos libros).
4. Esos movimientos se **fusionan** con los que ya había en el estado del grupo (por CLAVE TRANSACCIÓN). Si el extracto es el acumulativo del mes (1000 → 1700 movimientos), los 1000 de antes se reconocen y solo se suman los 700 nuevos; si el archivo es idéntico, no cambia nada.
5. Se regenera **el libro completo** de ese mes (nunca un archivo por día), se valida contra sus fuentes, se guarda y se anota en `P10_Control`.
6. Como el estado cambió, ese banco y mes se concilian además con `Depositos_Activos` en el mismo ciclo (para tomar estados que ya estuvieran en la lista).

## 8. De Power Apps al histórico (explicación simple)

1. Alguien confirma (o revierte, o modifica) un depósito en Power Apps; P9 escribe en `Depositos_Activos` y SharePoint actualiza `Modified`.
2. En el siguiente ciclo, P10 hace **una sola consulta**: «filas con `Modified` posterior a mi cursor». Casi siempre devuelve cero y el ciclo termina.
3. Si devuelve filas, se agrupan por BANCO + CUENTA + MONEDA + **mes de la CLAVE del movimiento** (no el mes de hoy): un movimiento de septiembre confirmado el 12 de octubre actualiza el libro de **septiembre**.
4. La información de esas filas se aplica al estado del grupo; el libro de ese grupo se regenera completo (varias confirmaciones del mismo mes en 15 minutos = **una** regeneración) y se guarda. Los demás libros no se tocan.
5. El cursor avanza solo cuando todo salió bien; si algo falló, se vuelve a leer en el ciclo siguiente.
6. Cada noche (primer ciclo del día, 06:00) se compara **la lista completa por BANCO + MES** contra lo guardado, para atrapar cualquier cambio que el cursor no haya visto.

## 9. Reversiones

P9 deja una reversión como: `ESTADO_ASIGNACION` vuelve a `DISPONIBLE`, se limpian estudiante/usuario/fecha/observación y se escribe `ULTIMA_REVERSION_ID`. Para P10 es una fila cuya información operativa cambió: gana la lista, el movimiento vuelve a `DISPONIBLE` en el libro y `AUDITORIA` conserva `ULTIMA_REVERSION_ID` (columna 28). Probado de extremo a extremo: confirmar → el libro dice CONFIRMADO con estudiante, código, usuario y fecha en hora de Bolivia → revertir → DISPONIBLE + `ULTIMA_REVERSION_ID`. Reglas del contrato A.1 sin cambios.

Si más adelante P10-B elimina registros de `Depositos_Activos`, **el estado conserva** la última información operativa de esas filas (una fila ausente de la lista nunca se borra del estado): el histórico seguirá diciendo CONFIRMADO.

## 10. Concurrencia e idempotencia

* **Un solo escritor lógico.** Hay un único flujo; su disparador tiene concurrencia 1 y como máximo 1 ejecución en espera. Además, antes de trabajar toma un **bloqueo con vigencia (60 min)** con compare-and-swap sobre el ETag del elemento `LOCK`: si otra ejecución (p. ej. una prueba manual) lo tiene, la segunda termina sin hacer nada; si una ejecución muere, el bloqueo vence solo.
* **Dos escritores nunca tocan el mismo archivo:** los libros y estados solo los escribe este flujo; los usuarios los ven en solo lectura.
* **Idempotente en cada nivel:** un extracto ya anotado no se reprocesa (clave = ruta; cambia el tamaño → se reprocesa); aplicar el mismo parcial dos veces no cambia el estado (se reconoce por huella); aplicar las mismas filas de la lista dos veces no cambia nada; regenerar el libro desde el mismo estado da **los mismos bytes**.
* **Orden de escritura = marca de confirmación:** XLSX → estado → control. Si el ciclo muere entre dos de esos pasos, el siguiente ciclo converge sin duplicar nada: el estado puede ir **una versión adelante** del control (se acepta); cualquier otra diferencia (retroceso, alteración) se trata como tal.

## 11. Recuperación ante fallos

| Situación | Cómo se detecta | Qué hace el sistema |
|---|---|---|
| Evento perdido (cambio en la lista que el cursor no vio) | conciliación nocturna por BANCO+MES | aplica la diferencia y regenera el libro |
| Ciclo fallido / servicio caído | el extracto no queda anotado; el cursor no avanza | se reintenta solo en el ciclo siguiente; un fallo técnico **no** gasta los 3 intentos del extracto; la ejecución queda *Failed* con el detalle |
| Ciclo muerto a mitad | `LOCK_HASTA` vencido | el siguiente ciclo (tras la vigencia) retoma y converge |
| XLSX borrado o alterado | ciclo completo: se compara el SHA-256 del archivo real con el sello del estado | se regenera idéntico desde el estado |
| Estado ausente / ilegible / alterado / restaurado a una versión vieja | falta el archivo, falla el sello, o su versión/sello no coincide con lo confirmado en el control | el grupo pasa a `RECONSTRUIR`: se reprocesan **todos** sus extractos originales de PROCESADOS (sin límite de cantidad), se ignora el estado viejo y la marca solo se quita cuando ya no queda ningún extracto por reincorporar; después se concilia con la lista |
| Estado incompleto | misma ruta que arriba (el sello de integridad lo delata) | igual |
| Diferencias con la lista mientras el registro está activo | cursor (minutos) y conciliación nocturna (horas) | la lista manda |
| XLSX que no pasa la validación | `xlsx_valido:false` | el estado se conserva, no se publica un libro dudoso, el grupo queda en `ERROR` con reintento automático (hasta 3 veces; luego espera al ciclo completo de la noche) |
| Extracto rechazado por el motor | `ok:false` con código y mensaje (sin datos bancarios) | `ERROR` → 3 intentos → `ERROR_FINAL` (visible en `P10_Control`; el ciclo completo avisa) |
| Lectura de más de 5000 filas en un BANCO+MES | `REBANADA_EXCEDE_LIMITE` | falla con aviso; no concilia a ciegas |
| `P10_Control` con más de 5000 elementos | `CONTROL_EXCEDE_LIMITE` | el ciclo se detiene antes de trabajar (hay que depurar registros de extractos antiguos) |

Límite honesto: **sin el extracto original en PROCESADOS no se puede reconstruir** el estado de un grupo. El sistema no inventa datos: queda en `RECONSTRUIR` y lo informa. Tras una reconstrucción, el libro tiene el mismo contenido; la propiedad «fecha de modificación» del archivo es la de la reconstrucción, y el lote/fecha de carga de movimientos que aún no están en la lista pueden diferir del original (los que ya están en la lista conservan los de la lista).

## 12. Frecuencia elegida: cada 15 minutos (06:00–22:45, Bolivia)

Criterio: robustez primero, minutos de retraso aceptables, no gastar de más, agrupar cambios.

| Intervalo | Retraso máx. | Ciclos/día (17 h) | Acciones/día (ocioso: 28/ciclo) | Comentario |
|---|---|---|---|---|
| 5 min | 5 | 204 | ≈ 5 700 | cerca del límite diario de las licencias de Microsoft 365; compite con P0/P8/P9 |
| 10 min | 10 | 102 | ≈ 2 900 | viable |
| **15 min** | **15** | **68** | **≈ 1 900 + trabajo real** | **elegido** |
| 30 min | 30 | 34 | ≈ 950 | demasiado lento para quien confirma y quiere ver el libro |

Por qué 15: (1) los usuarios trabajan en horario de oficina y la consulta *Excel histórico* no es una pantalla de operación; (2) el coste ocioso es una sola lectura de `Depositos_Activos` + una de `P10_Control` + el listado de dos meses de PROCESADOS; (3) todos los cambios de 15 minutos se **agrupan** en una regeneración por libro; (4) deja margen de acciones para el trabajo real (un extracto con su grupo ≈ 55 acciones; un grupo con cambios ≈ 30) y para que P0/P8/P9 sigan corriendo bajo el mismo límite. Si tu licencia es *Premium* (límite mucho mayor) puedes bajar a 10 min; si necesitas ahorrar acciones, recorta las horas (sección 18.5, punto 6). El primer ciclo del día es el **completo** (a las 06:00): como máximo, un extracto subido de madrugada espera hasta esa hora.

Límite documentado de Microsoft para licencias de Microsoft 365: 6 000 solicitudes de Power Platform por usuario cada 24 h (verifícalo en tu tenant: Centro de administración de Power Platform → Análisis). Las acciones de un flujo cuentan.

## 13. Pruebas automáticas (119 pruebas nuevas)

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `tests/test_37_p10_a2_nucleo.py` | 30 | claves = las de P0; sin código de normalización en P10; estado, sellos, retroceso/alteración/cierre interrumpido; extractos acumulativos; cruce con la lista (confirmar, revertir, borrar, columnas de carga); regeneración idéntica; reconstrucción; filas parciales; lo cerrado no cambió; columnas contra el esquema real |
| `tests/test_38_p10_a2_plan.py` | 31 | bloqueo, modos, ventanas, cursor y delta, extractos, reconstrucción, conciliación por banco |
| `tests/test_39_p10_a2_api.py` | 13 | autenticación fail-closed, validaciones, tamaño, operaciones por HTTP, extremo a extremo, **la imagen de Docker arranca con solo lo que copia el Dockerfile** |
| `tests/test_40_p10_a2_flujos_e2e.py` | 45 | **los JSON reales de los flujos** ejecutados con el intérprete sobre el tenant simulado: provisión, ENTRADA→histórico, Power Apps→histórico, reversión, orden de escritura, XLSX borrado/alterado, estado borrado/corrupto/retrocedido, servicio caído, caída del ciclo en medio, bloqueo vigente y carrera perdida, token ausente, evento perdido, 5000+, consumo ocioso, límites de Power Automate, expresiones, ZIP |

## 14. Regresión P0 / P7 / P8 / P9

Suite completa (`pytest tests`) tras terminar A.2: **1587 pasaron, 23 omitidas, 13 xfail, 3 fallaron**. De los 3 fallos, **2 ya existían en la base** (`test_16 …sin_cambios_respecto_al_commit_base` y `test_27 …[provisionar]`; la base tenía 1468 pasadas con los mismos 2 fallos). El tercero (`test_33 …no_define_logica_de_clave_ni_de_normalizacion`, de A.1) lo provocó un método de mi simulador de tenant llamado `validar`; se renombró y `test_33 + test_37 + test_40` se re-ejecutaron: **137 pasaron**. Las 1468 pruebas de la base siguen pasando sin cambios de resultado: P0, P7, P8, P9 y A.1 no se modificaron (huellas verificadas por `test_36`, `test_16`, `test_33` y `test_37`). Pendiente de rigor: no volví a correr la suite completa *después* del renombrado (solo las 3 suites afectadas).

## 15. Paquetes / importables

En la raíz del repositorio: `P10_SINCRONIZAR_HISTORICO_V1.zip` y `P10_PROVISIONAR_CONTROL_V1.zip` (formato *Importar paquete (heredado)*, igual que P0/P8/P9). Definiciones legibles en `p10/flujo/*_definition.json`. Se regeneran con `python -m p10.flujo.construir` (deterministas: mismos bytes siempre). También: `p10/Dockerfile` + `p10/railway.json` (Railway).

## 16. SHA-256

| Archivo | SHA-256 |
|---|---|
| `P10_SINCRONIZAR_HISTORICO_V1.zip` | `018e8ebc75cf765e73a281790d911bfa10ba97f027206ea824f5a5c26f0be9a7` |
| `P10_PROVISIONAR_CONTROL_V1.zip` | `7fe0c5347628b3b3b8375417b15a4033930922dd966029dbe15999d2fc1530c7` |
| `p10/Dockerfile` | `f25c396ec98c9d96566397866880a8eb05ed4c00b9fd13d3f7a6947fcdddf8d9` |
| `p10/railway.json` | `d19c8462435c97078a7e3c0d17a0ceba1c2a54ca62a2bc40438934c5b8b0de6f` |
| `p10/Dockerfile.dockerignore` | `76ce64ee79a9dcb8ea8d64de84af09e5393bdfc1b330cf9da68bbbde75172f67` |

Los ZIP son deterministas: `python -m p10.flujo.construir` los regenera con los mismos bytes (lo verifica una prueba).

## 17. Commits

Rama `experiment/p9-masiva-prototipo`, desde el cierre de A.1 (`c3691d2`): `cd699b8` núcleo · `0b511ee` servicio `p10-api` · `372ab4a` sellos cruzados/verificación/reconstrucción · `3b5652c` flujos + intérprete + tenant simulado · `eb15dba` huellas de lo cerrado · `799d34f` lectura incremental y conciliación por BANCO+MES · `c9ef354` documentación, dockerignore propio · `a7334ae` estado del proyecto y roadmap · más el commit final de esta entrega (renombrado en `tenant_simulado.py` y secciones 14/16/17/20).

## 18. Pasos EXACTOS en el tenant (para Gabriel) — nada de esto se ha hecho

**Antes de empezar.** Todo es **aditivo y reversible**: un servicio nuevo en Railway, una lista nueva, tres carpetas nuevas, dos flujos nuevos y un índice en `Depositos_Activos`. Nada borra ni modifica datos existentes. Para deshacer: apaga el flujo, borra el servicio y la lista (sección 18.8).

### 18.1 Railway: crear el servicio `p10-api`

1. Entra a <https://railway.com> → abre el proyecto donde está `p0-api`.
2. Clic en **+ New** → **GitHub Repo** → elige `lothbrok338/control-depositos-cbba`.
3. Cuando pregunte la rama, elige **la misma que usa `p0-api`** (la de P10: `experiment/p9-masiva-prototipo`, mientras no se fusione). Si Railway empieza a construir con la configuración por defecto, no importa: se reconstruye en el paso 6.
4. Abre el servicio nuevo → pestaña **Settings** → en *Service Name* escribe `p10-api`.
5. Pestaña **Settings** → sección **Build**:
   * **Dockerfile Path** = `p10/Dockerfile`
   * (si tu versión del panel lo ofrece) **Config-as-code / Railway Config File** = `/p10/railway.json`
   * (alternativa al *Dockerfile Path*: variable `RAILWAY_DOCKERFILE_PATH` = `p10/Dockerfile`)
   * El `.dockerignore` de la raíz es el de `p0-api` y no deja pasar `historico.py`, `p9/` ni `p10/`; por eso `p10/` trae su propio `p10/Dockerfile.dockerignore` (BuildKit lo usa junto al Dockerfile). **Si el build falla con «historico.py: not found»**, Railway no lo está leyendo: se resuelve en ese momento (decisión de Gabriel: el `.dockerignore` raíz de P0 NO se toca por ahora; se buscaría otra salida, p. ej. un repositorio/rama dedicada para p10-api).
6. Pestaña **Variables** → **+ New Variable**:
   * Nombre `P10_API_TOKEN`, valor = un secreto aleatorio **de 40 o más caracteres** (genéralo con tu gestor de contraseñas). Guárdalo: lo necesitas en 18.2. → **Add**.
   * **No** agregues volumen ni base de datos.
7. Pestaña **Settings** → **Networking** → **Generate Domain**. Copia el dominio (algo como `p10-api-production-xxxx.up.railway.app`).
8. Pestaña **Deployments**: espera a que el despliegue esté en verde. En **Logs** debe verse `Uvicorn running`.
9. **Comprobación:** abre en el navegador `https://<tu-dominio>/health` → debe mostrar `{"status":"ok","servicio":"p10-historico","version":"P10-API-1"}`.
10. No toques los ajustes de `p0-api`.

### 18.2 OneDrive: carpetas y token

1. Abre tu OneDrive en el navegador (`univalleedu-my.sharepoint.com`) → **Mis archivos** → `CONTROL_DEPOSITOS`.
2. **+ Nuevo → Carpeta** (tres veces): `P10_CONFIG`, `P10_HISTORICO`, `P10_ESTADO`.
3. En tu PC crea un archivo de texto `P10_API_TOKEN.txt` que contenga **solo el token** (el mismo de Railway; no importan espacios ni salto de línea finales).
4. Entra a `P10_CONFIG` → **Cargar → Archivos** → sube `P10_API_TOKEN.txt`. Bórralo de tu PC.
5. **No compartas** `P10_CONFIG` ni `P10_ESTADO` con nadie.

### 18.3 SharePoint: crear `P10_Control`

1. Power Automate (<https://make.powerautomate.com>) → **Mis flujos** → **Importar** → **Importar paquete (heredado)** → **Cargar** → `P10_PROVISIONAR_CONTROL_V1.zip`.
2. En *Recursos relacionados* → **SharePoint** → **Seleccionar durante la importación** → elige tu conexión de SharePoint → **Guardar** → **Importar**.
3. Abre el flujo `P10_PROVISIONAR_CONTROL` → **Ejecutar** → **Ejecutar flujo** → **Listo**. Espera 1–3 minutos: debe terminar **Correcto**.
4. **Comprobación:** en el sitio de SharePoint donde está `Depositos_Activos` → **Contenido del sitio** → debe existir **P10_Control** con un elemento `LOCK`. En *Configuración de la lista → Columnas indexadas* deben figurar `CLAVE_CONTROL`, `TIPO` y `PERIODO`; `CLAVE_CONTROL` con valores únicos.
5. **Índice en `Modified` de `Depositos_Activos`** (único cambio en esa lista, reversible): abre `Depositos_Activos` → ⚙ → **Configuración de la lista** → **Columnas indexadas** → **Crear un índice nuevo** → *Columna principal* = **Modificado** → **Crear**. (Sin este índice, en una lista grande SharePoint rechazaría la lectura incremental.)
6. Los permisos de `P10_Control` quedan los del sitio (solo tú). No la compartas.

### 18.4 Importar y configurar el sincronizador

1. **Mis flujos** → **Importar** → **Importar paquete (heredado)** → `P10_SINCRONIZAR_HISTORICO_V1.zip`.
2. En *Recursos relacionados* elige tus conexiones: **SharePoint** y **OneDrive for Business** → **Guardar** → **Importar**.
3. Abre el flujo → **Editar**.
4. Abre la acción **P** (la primera, un *Compose*) → reemplaza **todo** el valor de `url_api` por la URL completa de tu servicio, sin barra final (por ejemplo `https://p10-api-production-ab12.up.railway.app`). Revisa `mes_inicio` (sección 19). **Guardar**.
5. **Comprobaciones del diseñador (2 minutos):**
   * Disparador **Cada_15_minutos**: *Recurrence*, zona horaria *(UTC-04:00) Georgetown, La Paz…*, horas 6–22, minutos 0/15/30/45. Menú ⋯ → **Configuración** → *Control de simultaneidad* **activado** con *Grado de paralelismo = 1*.
   * **Entradas/Salidas seguras** (⋯ → *Configuración*): `Leer_token` (salidas) y todas las acciones **HTTP** (entradas y salidas), `D_GET` y `S_Items` (salidas), las acciones *Crear/Actualizar archivo* (entradas). Si el diseñador las muestra desactivadas, actívalas.
   * No hay avisos rojos en ninguna acción. Si alguno sale en una acción de OneDrive o SharePoint, es la conexión: vuelve a elegirla.
6. **Todavía no lo enciendas.**

### 18.5 Encender y primera ejecución controlada

1. Página del flujo → **Activar**.
2. Sin esperar al siguiente cuarto de hora, pulsa **Ejecutar** → **Ejecutar flujo** (si el botón no estuviera disponible, espera al siguiente :00/:15/:30/:45). Si algo no te convence en cualquier momento: **Desactivar** y no se escribe nada más.
3. La **primera** corrida es un ciclo completo y puede incorporar **varios extractos ya existentes en PROCESADOS** desde `mes_inicio`: tarda minutos (un extracto grande ≈ 15–30 s). Si hay más de 60, las siguientes corridas continúan (cada 15 min).
4. Debe terminar **Correcto**. Abre la ejecución y comprueba, en orden:

| # | Comprobación | Dónde | Debe verse |
|---|---|---|---|
| 1 | Nacieron los libros | OneDrive → `P10_HISTORICO/AAAA/MM_MES/BANCO/` | `EXTRACTO_HISTORICO_<BANCO>_<CUENTA>_<MONEDA>_<AAAA-MM>.xlsx` (abre uno: hojas `EXTRACTO` y `AUDITORIA`, sin paneles inmovilizados) |
| 2 | Nacieron los estados | OneDrive → `P10_ESTADO/…` | `ESTADO_P10_…json.gz` (no los abras ni los muevas) |
| 3 | Registro de extractos y grupos | lista `P10_Control` | elementos `EXTRACTO` con `ESTADO = PROCESADO` y `GRUPO` con `ESTADO = OK` |
| 4 | El bloqueo se liberó | `P10_Control` → elemento `LOCK` | `LOCK_HASTA` vacío, `ULTIMA_COMPLETA` = hoy, `CURSOR_LISTA` con una fecha |
| 5 | Carpetas anidadas | (comprobación 1) | las subcarpetas año/mes/banco las crea *Crear archivo*; si OneDrive rechazó crearlas, la ejecución sale *Failed* en `X_Crear`/`E_Crear`: crea a mano esas subcarpetas y vuelve a ejecutar |
| 6 | *Actualizar archivo* sobrescribe | provoca un cambio (confirma un depósito en Power Apps) y deja pasar otro ciclo | el mismo libro se actualiza (no aparece uno nuevo ni «(1)») |
| 7 | Fechas en hora de Bolivia | abre `AUDITORIA` del libro de la comprobación 6 | `FECHA CONFIRMACIÓN` = la hora a la que confirmaste, en hora de Bolivia |
| 8 | Listado de PROCESADOS | acción `Listar_dias` en la ejecución | devolvió las carpetas de día con sus archivos (un 404 en un mes sin carpeta es normal) |
| 9 | Lectura incremental | acción `D_GET` | en un ciclo sin cambios: lista vacía |

   Si alguna falla, **desactiva el flujo y no sigas**: envíame la ejecución (nombre de la acción y mensaje) y lo ajustamos. Las comprobaciones 5, 6 y 8 son comportamientos de conector que no se pueden verificar sin tenant.
5. Durante el primer día: *Historial de ejecuciones*: un ciclo ocioso dura ~30–40 s y no escribe archivos. Una ejecución *Failed* trae en el mensaje de error qué extracto/grupo falló.
6. Consumo: Centro de administración de Power Platform → *Análisis* (o el panel de uso de tu licencia). Si te acercas al límite, en el disparador deja menos horas (p. ej. 7–20).

### 18.6 Permisos (modelo recomendado) — antes de dar acceso a otros usuarios

| Quién | Qué | Cómo |
|---|---|---|
| **Gabriel (administrador)** | todo | es el propietario del OneDrive y de los flujos |
| **Automatización (cuenta de servicio)** | editar `P10_HISTORICO`, `P10_ESTADO`, `P10_CONFIG`, `P10_Control` | hoy el flujo corre con **tu** conexión de OneDrive/SharePoint (eres a la vez administrador y automatización). Para separar: crea una cuenta de servicio, dale **Editar** en esas carpetas y en la lista, e importa/duplica el flujo con **sus** conexiones |
| **Usuarios normales** | **solo lectura** de los libros | OneDrive web → `CONTROL_DEPOSITOS` → `P10_HISTORICO` → **Compartir** → *Personas específicas* → agrega a los usuarios o al grupo que definas → permiso **Puede ver** → **Enviar**. No se comparte `P10_ESTADO` ni `P10_CONFIG` |
| Contraseña de Excel | **no se usa** | la protección es el permiso de la carpeta, no una contraseña del libro |

Quien tenga solo «Puede ver» no puede cambiar el archivo; el flujo (con permiso de edición) sí lo reescribe aunque alguien lo tenga abierto en modo lectura (en ese caso verá el cambio al reabrirlo).

### 18.7 Prueba de punta a punta

1. Suelta un extracto en `ENTRADA` como siempre.
2. En ≤ 15 min el libro de ese mes aparece/crece en `P10_HISTORICO`.
3. Confirma un depósito en Power Apps → en ≤ 15 min el libro lo muestra como `CONFIRMADO`. Revierte → vuelve a `DISPONIBLE`.

### 18.8 Cómo deshacer

* Apagar: flujo → **Desactivar**. Lo ya generado queda donde está y es inocuo.
* Quitar todo: borrar el flujo, el servicio `p10-api` en Railway, la lista `P10_Control`, las carpetas `P10_*` de OneDrive y (opcional) el índice de `Modified`. P0/P7/P8/P9 no dependen de nada de esto.

## 19. Decisiones y riesgos abiertos (te corresponde decidir o vigilar)

1. **`mes_inicio` = `2026-08` (decidido por Gabriel; pasa a `2027-01` en el go-live).** El histórico se construye desde agosto de 2026 con los extractos que ya están en PROCESADOS.
2. **Comportamientos de conectores sin verificar en tenant** (pruebas 5, 6, 8 de 18.5): crear subcarpetas con *Crear archivo*, *Actualizar archivo* por id y el listado `Folders?$expand=Files`. El intérprete local es una aproximación: **no certifica** el comportamiento de Microsoft.
3. **Cuenta de servicio:** hoy es la tuya (18.6).
4. **Extractos de meses antiguos subidos tarde** (carpeta de más de 2 meses atrás) esperan al ciclo completo del día siguiente.
5. **Crecimiento de `P10_Control`:** un elemento por extracto y por grupo. A ≈ 5 000 elementos el ciclo se detiene con un mensaje claro; hay que depurar registros de extractos antiguos (no afecta a los libros).
6. **Token en un archivo de OneDrive:** evita pegarlo en 6 acciones, pero es un archivo de texto en tu OneDrive. Alternativa (más segura, más trabajo): mover los flujos a una *Solution* y usar una variable de entorno de tipo *Secret*.
7. **Reconstrucción:** requiere los extractos originales en PROCESADOS (sección 11).
8. **Versión de la lista de permisos de SharePoint personal:** `P10_Control` vive en el sitio personal de OneDrive igual que `Depositos_Activos`.
9. **(Superado: validado en operación real el 2026-10-09, ver §21.)** Antes del despliegue solo estaba validado es la lógica (119 pruebas, extractos reales, motor real de P0, generador A.1 sin cambios) y el JSON de los flujos contra un intérprete estricto.


## 20. Corrección tras la primera prueba operativa en tenant (2026-10-09)

**Síntoma.** El histórico inicial se generó bien, pero un depósito confirmado desde Power Apps/P9 seguía como `DISPONIBLE` en el XLSX después de varios ciclos. En los logs de `p10-api` aparecían `ciclo`, `delta` y `plan` en cada ciclo y **nunca** `sincronizar` ni `clasificar`.

**Qué mostraron los logs reales de Railway** (no era que `delta` devolviera cero grupos):
* cada llamada a `/p10/delta` recibía ~2,1 MB (≈5000 filas de `Depositos_Activos`, el tope de la consulta) y respondía ~1,6 MB: devolvía grupos sucios con miles de filas, **el mismo lote cada ciclo**;
* la lectura incremental empezaba «desde ayer» y el cursor **no avanzaba** (lo retenían las filas de grupos sin estado y los fallos de grupo), así que la consulta, ordenada de la más antigua a la más nueva y limitada a 5000 filas, volvía siempre al mismo lote y las filas nuevas —la confirmación— quedaban fuera de la página;
* en cada ciclo `delta` llegaba **antes** que `plan`: la lectura de la lista (`D_GET`, primera acción de su secuencia) tenía `runAfter` vacío y corría **en paralelo** con el listado de PROCESADOS y los extractos. Consecuencia: `Cada_slice` leía `varSlices` antes de que la fase de extractos lo llenara, así que la conciliación BANCO+MES posterior al extracto **nunca corrió** (por eso no hubo `clasificar`) y los grupos nuevos quedaron sin la foto operativa de la lista.

**Cambios (solo P10-A.2):**
| Dónde | Cambio |
|---|---|
| Flujo | `D_GET` espera a `Cada_extracto` (`runAfter`): la fase de la lista corre **después** de la de extractos y `varSlices` está completo. |
| Flujo | Página de la lectura incremental: `$top=1000` (antes 5000), de la fila más antigua a la más nueva. |
| Flujo | El bloque de grupo ya no copia `filas`/`rutas` a una variable (`varG`): usa directamente el elemento del bucle. |
| Flujo | Un fallo técnico de grupo dice **qué acción falló** y su mensaje corto (`GRUPO …: fallo técnico en <acción>: <mensaje>`); `D_Clasificar` ya no falla en silencio. |
| `plan.delta` | El cursor **ya no se queda atrás** por filas de grupos sin estado (se concilian por BANCO+MES cuando su extracto crea el grupo y cada noche). Si la página viene llena, la última hora se vuelve a leer. Una fila malformada ya no tumba la página. |
| `plan.ciclo` | Sin cursor (primera vez) se lee solo la última hora (antes, el día anterior). **Auto-conciliación:** todo grupo `OK` que nunca se conciliara con la lista (`HASH_OPERATIVO` vacío) se encola como BANCO+MES; así los grupos ya creados se corrigen en el siguiente ciclo, sin esperar a la noche. |
| `plan.clasificar` | Un grupo nunca conciliado sin filas en la lista queda constatado (lista vacía) y no se reintenta cada ciclo. |

**Pruebas.** Solo las de P10-A.2 (`tests/test_37`–`test_40`: 126 en verde); nuevas: página llena del delta, fila malformada, auto-conciliación, orden de las fases del flujo, diagnóstico de la acción que falló. El intérprete local (`p10/ensayo_wdl.py`) ahora soporta `result()`.

**Despliegue.** Cambia el servicio **y** el flujo: hay que redeplegar `p10-api` (rama `deploy/p10-api`) **y** actualizar `P10_SINCRONIZAR_HISTORICO_V1.zip` (importar como *Actualizar*, conservando la conexión y el flujo existente). SHA-256 del ZIP: `018e8ebc75cf765e73a281790d911bfa10ba97f027206ea824f5a5c26f0be9a7` (170 acciones).

**Segunda corrección (misma prueba).** En tenant, `GD_Sync` falló con `InvalidTemplate: createArray() expects a comma separated list of parameters`: Power Automate exige al menos un parámetro en `createArray`. Se reemplazó `createArray()` (7 usos) por `json('[]')` / `[]`, y el intérprete local ahora rechaza `createArray()` vacío. Cambio solo del flujo: **no requiere redeploy de `p10-api`**. SHA-256 del ZIP: `018e8ebc75cf765e73a281790d911bfa10ba97f027206ea824f5a5c26f0be9a7`.

## 21. CIERRE — P10 HISTÓRICO VIVO: CERRADO Y VALIDADO EN OPERACIÓN REAL (2026-10-09)

**P10 HISTÓRICO VIVO — CERRADO Y VALIDADO EN OPERACIÓN REAL (2026-10-09).**
* Zip final importado en tenant: `P10_SINCRONIZAR_HISTORICO_V1.zip`, SHA-256 `018e8ebc75cf765e73a281790d911bfa10ba97f027206ea824f5a5c26f0be9a7` (170 acciones), commit `1eb775c` de `experiment/p9-masiva-prototipo`.
* `p10-api` (Railway): deployment `72569ef1` (SUCCESS) desde `deploy/p10-api` @ `456ca36` (= `7bd176b` + archivos de raíz de P10). El commit `1eb775c` solo cambia el flujo/ZIP/documentación, no archivos que copia el Dockerfile: el servicio desplegado es idéntico al de la rama de trabajo.
* Validaciones reales superadas: (1) generación de históricos mensuales por banco+cuenta+moneda+mes ✅; (2) **CONFIRMACIÓN** desde Power Apps/P9 → el histórico pasó de `DISPONIBLE` a `CONFIRMADO` y P10 regeneró el archivo mensual ✅; (3) **REVERSIÓN** desde Power Apps/P9 → el histórico volvió a `DISPONIBLE` y P10 resincronizó ✅; (4) flujo automático P10 y `p10-api` funcionando en producción de prueba ✅.
* Configuración CONGELADA: `mes_inicio = 2026-08`; sin candado en Power Apps; registros de prueba 2026 y `Depositos_Activos` intactos.
* **Decisión de arquitectura 2027 (PENDIENTE DE GO-LIVE, NO IMPLEMENTADA):** desde el 01/01/2027 `Depositos_Activos` es una lista operativa permanente, sin ventana móvil de dos meses; crece indefinidamente y Power Apps busca por FECHA + BANCO + CUENTA BANCARIA. P10 sigue igual: `Power Apps/P9 → Depositos_Activos → Modified → P10 → histórico del mes de FECHA_MOVIMIENTO` (incluso confirmar un movimiento antiguo actualiza su Excel mensual). **P10-B (borrado/limpieza) CANCELADO / NO NECESARIO.** No se borran registros históricos.
* **Únicas tareas de go-live 2027:** (1) `mes_inicio` de P10 → `2027-01`; (2) candado lógico en Power Apps: no mostrar ni permitir fechas `< 01/01/2027`. Los datos 2026 quedan como pruebas, sin borrarlos.

Pruebas finales en tenant: **CONFIRMACIÓN → histórico `CONFIRMADO` ✅ · REVERSIÓN → histórico vuelve a `DISPONIBLE` ✅.** Las secciones 18.x (pasos de tenant) y 19 (riesgos) siguen siendo la referencia de operación; la mención de P10-B en ellas queda superada por esta decisión (cancelado).
