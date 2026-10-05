# Registro de resultados — P9 MASIVA Fase 0.5

**Todo está sin ejecutar.** Rellena solo con lo que midas en el tenant. Estado inicial de cada fila: `NO EJECUTADO`. No sustituyas una celda vacía por una suposición.

Datos de la sesión de pruebas: fecha ______ · usuario ______ · navegador ______ · Excel de escritorio sí/no ______

## Resultados por prueba

| PRUEBA | RESULTADO | TIEMPO | CONFIABLE SÍ/NO | RECOMENDACIÓN |
|---|---|---|---|---|
| A. Subida con control de adjuntos (SubmitForm) | NO EJECUTADO | | | |
| A. Flujo encuentra el adjunto al ser llamado desde `OnSuccess` | NO EJECUTADO | | | |
| A. Copia a `Documents/P9_MASIVA_PROTO` | NO EJECUTADO | | | |
| A1–A3. Excel lee la tabla sin Delay ni retry | NO EJECUTADO | | | |
| A4. Excel con retry 4×PT5S | NO EJECUTADO | | | |
| A5. Excel con Delay 5 s | NO EJECUTADO | | | |
| A6. Excel con Delay 10 s | NO EJECUTADO | | | |
| G. Archivo abierto (Excel Online / escritorio / otro usuario) | NO EJECUTADO | | | |
| H. Sin tabla (`03`) y tabla con otro nombre (`04`) | NO EJECUTADO | | | |
| I. Encabezado cambiado (`05`) | NO EJECUTADO | | | |
| J. Tabla vacía (`02a`, `02b`) | NO EJECUTADO | | | |
| B1. Response temprano — tiempo de respuesta (×5) | NO EJECUTADO | | | |
| B1. El flujo continúa tras responder | NO EJECUTADO | | | |
| B1. Actualiza el lote hasta COMPLETADO | NO EJECUTADO | | | |
| B1. Fallo posterior capturado (`FALLO_CAPTURADO`) | NO EJECUTADO | | | |
| B1. Fallo posterior no capturado (`FALLO_NO_CAPTURADO`) | NO EJECUTADO | | | |
| B1. Cierre de la app durante el proceso | NO EJECUTADO | | | |
| B2. Latencia del trigger (×5, caliente) | NO EJECUTADO | | | |
| B2. Latencia del trigger tras >1 h sin uso | NO EJECUTADO | | | |
| Sondeo 2 s / 3 s / 5 s / 10 s | NO EJECUTADO | | | |

## Registro bruto

Copia aquí una fila por ejecución (UTC; `Created` = columna Creado del lote).

### Prueba A

| Run | Archivo | Retry | Delay | Created | T_FLUJO_INICIO | T_ARCHIVO_COPIADO | T_EXCEL_LEIDO | FILAS_LEIDAS | Estado final | Error exacto (si lo hay) |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | 01 | Ninguno | 0 | | | | | | | |
| A2 | 01 | Ninguno | 0 | | | | | | | |
| A3 | 01 | Ninguno | 0 | | | | | | | |
| A4 | 01 | 4×PT5S | 0 | | | | | | | |
| A5 | 01 | Ninguno | 5 | | | | | | | |
| A6 | 01 | Ninguno | 10 | | | | | | | |

### Casos de `P9_MASIVA_PROTO_LEER`

| Caso | Archivo | Estado de la ejecución | Código HTTP | Mensaje exacto | Filas / claves devueltas | Duración |
|---|---|---|---|---|---|---|
| G1 | 01 abierto en Excel Online | | | | | |
| G2 | 01 abierto en Excel escritorio | | | | | |
| G3 | 01 abierto por otro usuario | | | | | |
| H1 | 03 sin tabla | | | | | |
| H2 | 04 tabla `Tabla1` | | | | | |
| I | 05 encabezado cambiado | | | | | |
| J1 | 02a una fila en blanco | | | | | |
| J2 | 02b solo encabezado | | | | | |

### Prueba B

| Run | Patrón | Escenario | ms de respuesta (`varMsB1`) | T_RESPONSE | T_FIN | ¿Siguió tras responder? | Estado final | Notas |
|---|---|---|---|---|---|---|---|---|
| B1-1 | Response temprano | NINGUNO | | | | | | |
| B1-2 | | NINGUNO | | | | | | |
| B1-3 | | NINGUNO | | | | | | |
| B1-4 | | NINGUNO | | | | | | |
| B1-5 | | NINGUNO | | | | | | |
| B1-F1 | | FALLO_CAPTURADO | | | | | | |
| B1-F2 | | FALLO_NO_CAPTURADO | | | | | | |
| B1-C | | NINGUNO, app cerrada a los 5 s | | | | | | |

| Run | Patrón | T_PENDIENTE_MOD | T_FLUJO_INICIO | Latencia (s) | Caliente/frío | Estado final |
|---|---|---|---|---|---|---|
| B2-1 | Trigger por estado | | | | | |
| B2-2 | | | | | | |
| B2-3 | | | | | | |
| B2-4 | | | | | | |
| B2-5 | | | | | | |
| B2-F | | | | | frío (>1 h) | |

| Intervalo | Lote | Retraso hasta que la pantalla vio COMPLETADO (s) | Nº de Refresh | Observaciones |
|---|---|---|---|---|
| 2 s | | | | |
| 3 s | | | | |
| 5 s | | | | |
| 10 s | | | | |

## Conclusiones (rellenar tras medir; no antes)

- Arquitectura asíncrona recomendada: ______
- Polling recomendado: ______
- Delay/retry necesario antes de leer Excel: ______
- Limitaciones encontradas (licencia, permisos, etc.): ______

## Recursos temporales creados en el tenant — lista y limpieza

| Recurso | Dónde | Cómo eliminarlo |
|---|---|---|
| Lista `P9_MASIVA_PROTO_LOTES` | Sitio P9 → Contenido del sitio | Contenido del sitio → ⋯ junto a la lista → **Eliminar** (va a la papelera; vacíala también) |
| Carpeta `P9_MASIVA_PROTO` con las copias `*.xlsx` y los 5 archivos de prueba | Documentos | Documentos → seleccionar carpeta → **Eliminar**; después, Papelera → **Vaciar** |
| Flujo `P9_MASIVA_PROTO_PREVALIDAR` | Power Automate → Mis flujos | ⋯ → **Desactivar**, luego **Eliminar** |
| Flujo `P9_MASIVA_PROTO_TRIGGER` | ídem | ídem (desactívalo **antes** de borrar la lista, para que no dispare errores) |
| Flujo `P9_MASIVA_PROTO_LEER` | ídem | ⋯ → **Eliminar** |
| App «P9_MASIVA_PROTO» | Power Apps → Aplicaciones | ⋯ → **Eliminar** |
| Conexiones creadas solo para la prueba (Excel Online (Business), si es la primera vez) | Power Automate → Datos → Conexiones | ⋯ → **Eliminar** (opcional; conservarlas no cuesta nada) |

Orden recomendado: 1) desactivar `TRIGGER`; 2) eliminar los tres flujos; 3) eliminar la app; 4) eliminar la lista; 5) eliminar la carpeta; 6) vaciar papeleras. Si borraste la lista antes que el flujo, el flujo falla en cada ejecución: no es un problema, bórralo.
