# Medición en el tenant del flujo directo (a rellenar por quien lo ejecute)

**Estado: NO MEDIDO por tamaño.** El protocolo de abajo (10 a 2000 filas) **no se ha ejecutado**: la tabla de resultados sigue en blanco y ningún número de ella se ha supuesto. Solo existen dos mediciones sueltas observadas durante la validación del flujo (sección «Observaciones sueltas»). **No se ha supuesto ningún límite** de filas, de tiempo ni de tamaño. La pregunta es una sola: *¿el flujo directo (la app espera la respuesta) termina dentro de tiempos razonables, y hasta cuántas filas?* La respuesta sale de la tabla de abajo, no de la teoría.

Si aparece un tiempo de espera real, la decisión ya tomada es **fijar un máximo de filas por archivo** (`PARAM_MAX_FILAS` en el flujo, hoy 0 = sin tope) y **no** crear infraestructura de lotes.

## Archivos de medición (`xlsx/medicion/`, 100 % ficticios, mismas 9 columnas)

| Archivo | Filas | Tamaño | SHA-256 |
|---|---|---|---|
| `Filas_0010.xlsx` | 10 | 17 KB | `cf8978d78383…` |
| `Filas_0050.xlsx` | 50 | 18 KB | `4b42a67f38fd…` |
| `Filas_0100.xlsx` | 100 | 20 KB | `1db837cfd82a…` |
| `Filas_0250.xlsx` | 250 | 24 KB | `e869e7f68d09…` |
| `Filas_0500.xlsx` | 500 | 31 KB | `65247d21c77e…` |
| `Filas_1000.xlsx` | 1000 | 52 KB | `df074e7bdd79…` |
| `Filas_2000.xlsx` | 2000 | 92 KB | `002ee17fdc9d…` |

Se generan con `python proto_masiva/generar_medicion.py` (deterministas). Los tamaños son una **escala de prueba**, no un dato de la plataforma; `Filas_2000.xlsx` coincide con el umbral de paginación configurado (2000) y **debe** responder `DEMASIADAS_FILAS` (no un recuento truncado).

## Observaciones sueltas (validación del flujo, 2026-10-06; NO sustituyen al protocolo)

Dos ejecuciones reales en el tenant (el archivo usado en cada una no quedó registrado; la validación funcional se hizo con `Ejemplo_Confirmacion_Masiva_P9.xlsx`, 3 filas). **No se generalizan** a otros tamaños:

| | Power Apps | Flujo total | Crear archivo | Excel | Borrar |
|---|---|---|---|---|---|
| Ejecución 1 | 14,108 s | 10,443 s | 1,684 s | 5,259 s | 3,439 s |
| Ejecución 2, tras agregar a mano un Delay de 10 s y reintentos al borrado | 22,004 s | 19,216 s | 2,177 s | 3,738 s | 13,268 s |

En ambas el borrado de la copia terminó en HTTP 423 (Locked); ver `ESTADO_CHECKPOINT_TENANT.md`. El tiempo de «Borrar» de la ejecución 2 incluye la espera y los reintentos agregados a mano, que no están en el generador del flujo.

## Protocolo

Para cada archivo, **3 ejecuciones** (la primera tras un rato sin usar el flujo suele ser la más lenta: anótalo como «fría»). En la pantalla *IMPORTACIÓN MASIVA*: adjuntar → PREVALIDAR ARCHIVO. En cada ejecución copia de la pantalla (fila *Tiempo*):

- **App (ms):** de pulsar a recibir la respuesta (incluye red + arranque del flujo + espera).
- **Flujo `crear/excel/borrar/total` (ms):** lo mide el propio flujo por etapa.
- **Resultado / código / filas leídas / copia eliminada** (`SI` / `NO`).
- Si la app muestra `FLUJO_SIN_RESPUESTA`: copia el **mensaje exacto** y mira en Power Automate → *Historial de ejecuciones* si el flujo **terminó igualmente** (Succeeded/Failed) y cuánto duró. Eso distingue «la app dejó de esperar» de «el flujo falló».

## Resultados

| Filas | Ejec. | Resultado / código | Filas leídas | App (ms) | Flujo crear / excel / borrar / total (ms) | Copia eliminada | Observaciones (fría, error exacto…) |
|---|---|---|---|---|---|---|---|
| 10 | NO MEDIDO | | | | | | |
| 50 | NO MEDIDO | | | | | | |
| 100 | NO MEDIDO | | | | | | |
| 250 | NO MEDIDO | | | | | | |
| 500 | NO MEDIDO | | | | | | |
| 1000 | NO MEDIDO | | | | | | |
| 2000 | NO MEDIDO | | | | | | |

(Repite cada fila de la tabla 3 veces.)

## Comportamiento (una ejecución cada uno; apunta resultado, código, mensaje exacto y tiempos)

| Caso | Archivo | Esperado (simulación) | Real |
|---|---|---|---|
| A. Correcto | `Ejemplo_Confirmacion_Masiva_P9.xlsx` | COMPLETADO, 3 filas | **Validado en tenant:** COMPLETADO · ARCHIVO RECIBIDO · TABLA ENCONTRADA · 3 FILAS LEÍDAS · «Archivo leído correctamente» |
| B. Tabla vacía | `Plantilla_Confirmacion_Masiva_P9.xlsx` | ERROR / ARCHIVO_VACIO |  PENDIENTE (no probado en tenant) |
| C. Sin tabla | `03_SIN_TABLA.xlsx` | ERROR / TABLA_NO_ENCONTRADA (**supuesto: HTTP 404**) |  PENDIENTE (no probado en tenant) |
| D. Encabezado cambiado | `05_ENCABEZADO_CAMBIADO.xlsx` | ERROR / ESTRUCTURA_INVALIDA |  PENDIENTE (no probado en tenant) |
| E. Otra tabla | `04_TABLA_NOMBRE_DISTINTO.xlsx` | ERROR / TABLA_NO_ENCONTRADA |  PENDIENTE (no probado en tenant) |
| F. Archivo abierto | `Ejemplo…` abierto en Excel mientras se adjunta | (a observar) |  PENDIENTE (no probado en tenant) |
| G. No es xlsx | cualquier `.csv` | ERROR / NO_ES_XLSX (no llega al flujo si la app lo bloquea) |  PENDIENTE (no probado en tenant) |

## Cosas a observar además

1. **Primera llamada:** `.Run({name, contentBytes})` **funciona tal cual en el tenant** (validado). Nada que anotar salvo que Studio cambie.
2. **Borrado de la copia:** **observado: sale `NO` (HTTP 423 Locked)**; un Delay de 10 s y reintentos agregados a mano no lo resolvieron. Decisión vigente: se aceptan `TMP_*.xlsx` residuales; no se agrega limpiador ni infraestructura.
3. **Carpeta `P9_MASIVA_TEMP`** al final de la sesión: contendrá `TMP_*.xlsx` residuales (ver arriba). Anota cuántos quedaron y en cuál de las dos carpetas con ese nombre (ver `ESTADO_CHECKPOINT_TENANT.md`).

## Cómo decidir el máximo de filas (sin inventar números)

1. Mira el mayor tamaño que dio **3/3 ejecuciones correctas** en un tiempo que te parezca aceptable para quien espera frente a la pantalla.
2. Fija `PARAM_MAX_FILAS` **por debajo** de ese tamaño, con margen, y ajusta el mensaje a «máximo N filas por archivo».
3. Recuerda: estas mediciones son solo de **lectura y prevalidación**. La confirmación hará además una lectura y una escritura **por fila** sobre `Depositos_Activos` y tardará mucho más por fila: su máximo se medirá aparte y probablemente sea menor.
