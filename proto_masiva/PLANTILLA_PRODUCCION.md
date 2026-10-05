# Plantilla definitiva de trabajo · P9 CONFIRMACIÓN MASIVA

Dos archivos, generados desde cero por un script (nada hecho a mano en Excel):

| Archivo (`proto_masiva/xlsx/`) | Qué es |
|---|---|
| `Plantilla_Confirmacion_Masiva_P9.xlsx` | **Plantilla de producción, vacía**: para entregar al usuario. |
| `Ejemplo_Confirmacion_Masiva_P9.xlsx` | La misma plantilla con **3 filas ficticias** (`EJEMPLO-0001`…) que muestran cómo llenarla. No usar para confirmar. |

Regenerar ambos: `python proto_masiva/generar_plantillas_produccion.py` (también refresca `catalogo_bancos_p9.json`). Salida **determinista** (mismo SHA-256 cada vez). XLSX estándar: **sin macros, VBA ni conexiones externas**.

## De dónde salen los bancos y las cuentas

Nada está escrito en el generador. `catalogo_p9.py` los **extrae** de `p9/reversion/powerapps/Main_Screen.yaml` del checkpoint `3b407e202ca53e8827151d9e03a41c300bb8d84a` (selector `cmbBancoP9_1` y `cmbCuentaP9_1`, el validado en tenant). Antes de extraer exige que el archivo tenga el SHA-256 del checkpoint (`99486d66…e755a`) y que coincida con el objeto git `3b407e2`; si la fuente cambia, el generador **falla** en vez de producir otra plantilla. La **moneda** de cada cuenta no está en el selector: se toma de `registro_bancos.json` y se contrasta con las etiquetas MN/ME.

**Bancos (6).** BNB · BCP · BISA · BANCO UNIÓN · BANCO ECONÓMICO · BMSC. (El selector tiene 7 elementos porque el primero es `(Todos)`, que no es un banco y no se incluye.)

**Cuentas (13), en el orden de la fuente.**

| Banco | Etiqueta del selector | Cuenta | Moneda |
|---|---|---|---|
| BNB | MN | 3000100152 | BOB |
| BNB | ME | 3400041236 | USD |
| BNB | AHORRO | 3501936692 | BOB |
| BNB | CLÍNICA | 3000100705 | BOB |
| BCP | MN | 301-5005684-3-97 | BOB |
| BCP | ME | 301-5005425-2-71 | USD |
| BISA | MN | 0696870039 | BOB |
| BISA | ME | 0696872023 | USD |
| BANCO UNIÓN | MN | 10000003224552 | BOB |
| BANCO UNIÓN | ME | 20000003224544 | USD |
| BANCO ECONÓMICO | CTA. CTE. | 3041210569 | BOB |
| BANCO ECONÓMICO | AHORRO | 3051446946 | BOB |
| BMSC | CTA. CTE. | 1000872489 | BOB |

## Tabla y columnas

Una sola tabla `tblConfirmacionMasiva` (encabezados en la fila 5; título e instrucción arriba, fila superior congelada, filtros de tabla). 9 columnas exactas, en este orden. `TIPO_CAMBIO` no existe.

| Columna | Obligatoria | Formato | Validación |
|---|---|---|---|
| `BANCO` | Sí | texto | **Lista**: los 6 bancos |
| `CUENTA_BANCARIA` | Sí | **TEXTO** (conserva ceros y guiones) | **Lista dependiente del BANCO** de la fila (solo sus cuentas); sin banco, muestra las 13 |
| `CODIGO_ASIGNACION` | Sí | **TEXTO** (conserva ceros iniciales) | — |
| `IMPORTE` | Sí | número, 2 decimales | decimal **mayor que 0** |
| `MONEDA` | Sí | texto | **Lista**: `BOB`, `USD` |
| `ESTUDIANTE` | Sí | texto | longitud 1–255 |
| `SOLICITADO_POR` | Sí | texto | longitud 1–255 |
| `SEDE` | Sí | texto | longitud 1–255. **Texto libre**: el repo no tiene catálogo de sedes (`DISENO_LISTA_DEPOSITOS_ACTIVOS.md`: «Lista de sedes no definida») |
| `OBSERVACION` | **No** | texto | — |

Ayuda visual: encabezado **granate = obligatoria**, **gris = opcional**; formatos y listas preconfigurados hasta la fila 505 (la tabla crece sola). Reglas de color que solo avisan, sin bloquear: obligatorio vacío en una fila en uso (ámbar), cuenta que no es del banco o moneda distinta a la de la cuenta (rojo suave); ayudan cuando se **pega** desde otro Excel, que se salta las listas.

La hoja `_CATALOGOS` (oculta) guarda los catálogos (BANCO, MONEDA, cuentas con su banco, etiqueta y moneda). Las listas dependientes usan `IF/MATCH/OFFSET/COUNTIF`, **sin macros ni `INDIRECT`**.

**Plantilla «vacía»:** una tabla de Excel siempre conserva una fila de datos; la vacía trae **una fila en blanco**. Las filas totalmente en blanco no cuentan como datos en el flujo (`ARCHIVO_VACIO`).

## Qué se verificó (y qué no)

- El generador **se auto-verifica antes de guardar** y sobre los bytes finales: 9 columnas en orden, tabla, sin `TIPO_CAMBIO`, texto en CUENTA/CODIGO, 2 decimales, 6 bancos, 13 cuentas exactas sin duplicados, validaciones de BANCO, CUENTA, MONEDA e IMPORTE, sin macros ni vínculos, 3 filas en el ejemplo y 0 en la plantilla. Un set de 14 plantillas defectuosas se rechaza (`test_05`).
- **[VALIDADO LOCALMENTE]** con LibreOffice 24.2: ambos archivos abren; la fórmula de la lista dependiente devuelve 4/2/2/2/2/1 cuentas por banco y 13 sin banco; las reglas de color se evalúan como se espera.
- **[REQUIERE VALIDACIÓN EN EXCEL]** El comportamiento real de las listas desplegables y de las reglas de color en **Excel de escritorio y Excel Online** no se pudo probar aquí (no hay Excel). Las funciones usadas son estándar de Excel. Si la lista de CUENTA no filtra en Excel Online, la validación sigue permitiendo elegir entre las 13 cuentas.

## DESCARGAR PLANTILLA en Power Apps (preparado, sin URL inventada)

- **Dónde guardar el archivo:** en una biblioteca de documentos de SharePoint que los usuarios de la app puedan **leer**, siempre con el nombre `Plantilla_Confirmacion_Masiva_P9.xlsx` (el prototipo usa `Documents/P9_MASIVA_PROTO/`; la carpeta definitiva se decide después). Hay una sola copia: no se sube el Ejemplo ahí.
- **Qué actualizar cuando tengamos la URL:** **una sola línea**, en `OnVisible` de la pantalla `P9_Confirmacion_Masiva`:
  `Set(varUrlPlantillaP9, "<URL del archivo>?download=1")`.
  El botón `btnDescargarPlantillaP9` ya ejecuta `Launch(varUrlPlantillaP9)` y no cambia. El `?download=1` y la apertura en el navegador no están probados en tu tenant.
- El Excel no se modifica: nada de la URL va dentro del archivo.

## PASOS PARA GABRIEL

1. Abre `Plantilla_Confirmacion_Masiva_P9.xlsx` en Excel y comprueba **una vez** que BANCO y CUENTA_BANCARIA muestran las listas (elige `BCP` y mira que solo salgan sus 2 cuentas). Si no filtra, avísame; igual puedes elegir entre las 13.
2. Súbela a la biblioteca de SharePoint elegida (una sola copia, con ese nombre) y copia su URL.
3. En Power Apps, pega esa URL en la línea `Set(varUrlPlantillaP9, …)` de `OnVisible` de `P9_Confirmacion_Masiva`.
4. Entrega a los usuarios solo la **Plantilla** (vacía); el **Ejemplo** es solo para mostrarles cómo llenarla.
5. Para cambiar bancos o cuentas en el futuro, no edites el Excel: se cambian en `Main_Screen` y se vuelve a ejecutar `python proto_masiva/generar_plantillas_produccion.py`.
