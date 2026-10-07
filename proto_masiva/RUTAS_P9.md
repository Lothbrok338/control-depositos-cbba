# P9 · Rutas físicas tras la reorganización a `Documents/CONTROL_DEPOSITOS/P9/`

Los recursos de P9 se movieron físicamente a `Documents/CONTROL_DEPOSITOS/P9/` **después** de generar los paquetes de la escala 1999. Este documento lista cada ruta de P9 que usan los artefactos y su estado.
Regla del repositorio: **la carpeta temporal tiene UNA sola fuente** (`proto_masiva/flows/construir.py` → `RAIZ_P9`, `CARPETA_TEMP`); los tres flujos la comparten y `tests/test_10_rutas_p9.py` impide que vuelva la antigua.

| Elemento | Ruta ANTERIOR | Ruta NUEVA | Dónde vive |
|---|---|---|---|
| Raíz física de P9 | (varias, con `Documents` anidado) | `/Documents/CONTROL_DEPOSITOS/P9` | `construir.RAIZ_P9` |
| Carpeta temporal | `/Documents/P9_MASIVA_TEMP` | **`/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP`** | `construir.CARPETA_TEMP` → `PARAM_CARPETA` de los 3 flujos |
| Copias `TMP_<guid>.xlsx` (prevalidación) | `…/P9_MASIVA_TEMP` antigua | misma carpeta nueva | `P9_MASIVA_PROTO_PREVALIDAR` (`Crear_archivo`, `folderPath = PARAM_CARPETA`) |
| Estado `confirmacion_<execution_uid>.json` | (nuevo en la escala 1999: nació con la ruta antigua) | misma carpeta nueva | `P9_MASIVA_PROTO_CONFIRMAR` (`Crear_estado` / `Escribir_*`) y `P9_MASIVA_PROTO_ESTADO` (`Leer_estado`: `PARAM_CARPETA/confirmacion_<uid>.json`) |
| Plantilla `Plantilla_Confirmacion_Masiva_P9.xlsx` | `/personal/gtorricot_univalle_edu/Documents/Documents/P9_MASIVA_PROTO/` | movida dentro de `Documents/CONTROL_DEPOSITOS/P9/` (ruta exacta no registrada aquí) | **no se usa por ruta**: botón `btnDescargarPlantillaP9` → `download.aspx?UniqueId=84b7ef88-43aa-43d2-8d1c-0f0b682dafbd` |
| Excel de prevalidación (`Leer_tabla_Excel`) | — | — | por `Id` del archivo recién creado (no depende de ninguna ruta) |
| Sitio y lista de depósitos | `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` · lista `296c450a-…` | sin cambio | `PARAM_SITIO`, `PARAM_LISTA_DEPOSITOS_ACTIVOS` |

## Qué cambió en los paquetes (y qué no)

Cambió **un solo valor** por flujo: `PARAM_CARPETA`. Ninguna lógica, expresión, contrato ni Power Fx.

| Flujo | ¿Cambió? | Valor |
|---|---|---|
| `P9_MASIVA_PROTO_PREVALIDAR` | **Sí** (solo `PARAM_CARPETA`) | `/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` |
| `P9_MASIVA_PROTO_CONFIRMAR` | **Sí** (solo `PARAM_CARPETA`) | ídem |
| `P9_MASIVA_PROTO_ESTADO` | **Sí** (solo `PARAM_CARPETA`) | ídem |
| Power Apps (`P9_PRUEBA_MASIVA`) | **No** | ninguna fórmula ni control contiene una ruta de carpeta |

## La plantilla: ¿hay que tocar Power Apps?

El botón usa `Launch("…/_layouts/15/download.aspx?UniqueId=84b7ef88-43aa-43d2-8d1c-0f0b682dafbd")`: **solo el UniqueId**, ninguna ruta. En SharePoint/OneDrive **mover** un archivo dentro de la misma biblioteca **conserva** su UniqueId; **copiarlo y volver a subirlo** crea uno nuevo.
El repositorio no puede saber cuál de las dos cosas ocurrió. **Comprobación de 10 segundos:** pega esa URL en el navegador; si descarga `Plantilla_Confirmacion_Masiva_P9.xlsx`, **no cambies nada**. Si no descarga, solo hay que sustituir el UniqueId en la propiedad `OnSelect` de `btnDescargarPlantillaP9` (y en `powerapps/`), nada más.

## Antes de importar (comprobaciones)

1. La carpeta **`Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` debe existir**: la acción *Crear archivo* no crea carpetas; si no existe, la prevalidación fallaría en `Crear_archivo` y la confirmación daría `ERROR_ESTADO` (sin confirmar nada).
2. La ruta de la acción es relativa a la biblioteca `Documents` del OneDrive de `gtorricot_univalle_edu` (la misma biblioteca que ya usaba la prevalidación, validada en el tenant).
3. Importa los TRES ZIP (`P9_MASIVA_PROTO_PREVALIDAR`, `P9_MASIVA_PROTO_CONFIRMAR`, `P9_MASIVA_PROTO_ESTADO`): los tres cambiaron. Por eso el flujo de prevalidación ya funcionando también debe actualizarse: si no, seguiría escribiendo sus `TMP_*.xlsx` en la carpeta antigua.
   Alternativa mínima para la prevalidación sin reimportar: abrir el flujo → `PARAM_CARPETA` → cambiar el valor a la ruta nueva → Guardar (el único cambio del paquete).
