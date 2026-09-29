# Normalizador CBBA: diseño de cuatro capas sin pérdida de información (Fase 3, solo diseño)

**Regla rectora:** normalizar nunca destruye información de origen. El archivo bancario sigue siendo la evidencia inalterada. Cada dato que el banco entrega queda en alguna capa y cada movimiento normalizado apunta a su fila original.

**Estado del motor:** no fue modificado. `COLUMNAS_LISTS` (26) y `CLAVE TRANSACCIÓN` no cambian.

**Versión 2 (aprobación conceptual con una modificación):** se agrega la **capa 4, SALIDA_HUMANA / EXTRACTO_HISTORICO** (sección 6). Las capas 2 y 3 son artefactos técnicos internos; la capa 4 es el Excel que usarán Contabilidad e Ingresos. Además, la capa 4 obliga a un ajuste en la capa 2 (ver 3): `DATOS_ORIGINALES` pasa a contener **todas** las celdas, incluidas cabecera y pie.

| Capa | Nombre | Audiencia | Archivo | Cambia el contrato actual |
|---|---|---|---|---|
| 1 | NORMALIZADO_OPERATIVO | Carga a Lists | `NORMALIZADO.xlsx` + `LISTS.csv` (26 columnas) | No |
| 2 | DATOS_ORIGINALES (+ MAPA_ORIGEN) | Sistema / auditoría técnica | `ORIGEN.xlsx` | No (archivo nuevo) |
| 3 | METADATOS_EXTRACTO | Sistema / auditoría técnica | `ORIGEN.xlsx` | No (archivo nuevo) |
| **4** | **SALIDA_HUMANA / EXTRACTO_HISTORICO** | **Contabilidad e Ingresos** | **Un `.xlsx` por banco/cuenta/período** | No (archivo nuevo) |

**Base del análisis:** los 12 extractos reales de `tests/fixtures/extractos` (36.700 celdas no vacías; UNION_ME entra por su contrato legado en el motor + la captura real de 7 columnas, sin inventario de celdas con movimientos). La matriz completa, con 248 filas (una por campo, celda de cabecera o celda de pie), está en `MATRIZ_CAMPOS_ORIGEN.csv` (separador `;`, UTF-8 con BOM, abre directo en Excel).

> **UNION_ME — estado de la evidencia (definitivo):** UNION_ME es un formato válido, `UNION_FECHAS_V1`. **Estructura = CONFIRMADA** por dos fuentes independientes: (a) el **código legado** `motor_control_depositos_cbba.py`, que es la fuente autoritativa del contrato: `HOJAS_VALIDAS["UNION_ME"] = "ExtractoMovimientosFechas"`; `ENCABEZADOS_ESPERADOS["UNION_ME"]` exige `FECHA MOVIMIENTO`, `DESCRIPCION`, `NRO DOCUMENTO`, `MONTO`, `SALDO`; `detectar_formato()` devuelve `UNION_ME` cuando el texto trae `FECHA MOVIMIENTO` + `NRO DOCUMENTO` + la cuenta `20000003224544`; `normalizar_union()` procesa Fecha Movimiento, Descripción/Descripcion, Nro Documento/Nro. Documento, Monto, Saldo y AG/Agencia (opcional), y asigna a UNION_ME cuenta `20000003224544` y moneda `USD`; y (b) la **captura real**, que muestra 7 columnas: `Fecha Movimiento | AG | Descripción | Nro Documento | Monto | Saldo | Nro de verificasion`. `Nro de verificasion` es la única columna que el motor legado **no** contempla: se pierde hoy; debe conservarse en `DATOS_ORIGINALES` y en `EXTRACTO_HISTORICO`, **sin** incorporarla a las 26 `COLUMNAS_LISTS`. **Comportamiento con movimientos = PENDIENTE de fixture real** (datos reales, débitos, cadena de saldo, comportamiento empírico del motor y contenido/formato de `Nro de verificasion`): **REQUIERE MUESTRA REAL CON MOVIMIENTOS**. La muestra vacía se acepta como fixture estructural (aún no está en el repositorio: se espera `union_me_vacio.xls`). El `union_me_1.xls` de «Últimos 12 Movimientos» **no** es representativo: fixture negativo.

---

## 1. Matriz BANCO/FORMATO → CAMPO ORIGINAL → CAMPO NORMALIZADO → DESTINO

Estados usados en la matriz:

| Estado | Significado |
|---|---|
| **MAPEADO** | El valor llega a una de las 26 columnas operativas. |
| **EN TEXTO LIBRE** | Solo sobrevive concatenado dentro de `INFORMACIÓN ADICIONAL`. |
| **SOLO CONTROL** | Se usa para detectar o validar, pero no se guarda como dato. |
| **PERDIDO** | No aparece en ninguna salida. |

### 1.1 Resumen por formato (conteo de campos y celdas de cabecera/pie)

| Formato | Mapeado | En texto libre | Solo control | **Perdido** |
|---|---|---|---|---|
| BCP_ME / BCP_MN | 6 | 3 (sin etiqueta) | 4 | 3 |
| BISA_ME / BISA_MN | 7 | 2 | 4 | **14** |
| BMSC | 8 | 4 | 1 | **19** (incluye una hoja completa) |
| BNB_MN / ME / AHORRO / CLINICA | 8 | 0 | 1 | 3 (incluye **Referencia**) |
| ECO_CTA_CTE / ECO_AHORRO | 7 | 0 | 3 | **17** |
| UNION_MN | 5 | 1 | 1 | **13** |
| UNION_ME (`UNION_FECHAS_V1`) | sin muestra con movimientos | | | Estructura confirmada (código legado + captura real, 7 columnas); sin inventario de celdas con datos |

### 1.2 Columnas de la tabla de movimientos (todas las que entrega cada banco)

El destino propuesto para todas es: **DATOS_ORIGINALES siempre**, y además el operativo cuando hoy se mapean.

**BNB (MN, ME, AHORRO, CLINICA)**, hoja `Hoja 1` (AHORRO: `Hoja`), encabezado en fila 2.

| Campo original | Ejemplo real | Campo LISTS actual | Estado | Canónico propuesto | Uso en débitos |
|---|---|---|---|---|---|
| Fecha | 01/08/2026 | FECHA MOVIMIENTO | Mapeado | FECHA | |
| Hora | 09:10:12 | HORA MOVIMIENTO | Mapeado | HORA | |
| **Oficina** | COCHABAMBA-AGENCIA CENTRAL | — | **PERDIDO** | OFICINA | Agencia de cobro del cheque |
| Descripción | Debito Cta por ACH | DESCRIPCIÓN | Mapeado | DESCRIPCION | Tipo de débito (8 tipos) |
| **Referencia** | 0008125 · 15-9135 · JULIO 2026 | — | **PERDIDO** | REFERENCIA | **Nro. de cheque / ref. pago web** |
| Código de transacción | 3P81086749 | CÓDIGO DE ASIGNACIÓN | Mapeado | CODIGO_TRANSACCION | |
| **ITF** | 0.00 | — | **PERDIDO** | ITF | Impuesto |
| Débitos | 1,601.60 | DÉBITO/IMPORTE/TIPO | Mapeado (texto → número) | DEBITO | |
| Créditos | 65,972.00 | CRÉDITO/IMPORTE/TIPO | Mapeado | CREDITO | |
| Saldo | 7,352,914.48 | SALDO | Mapeado | SALDO | |
| Adicionales | Cuenta Destino: … Nombre: … Banco: … Dato Adicional: … | INFORMACIÓN ADICIONAL (completo) + DEPOSITANTE (regex) | Mapeado con **defecto** (ver 2) | ADICIONALES | **Cuenta, nombre y banco destino, concepto** |

**BCP (MN, ME)**, hoja `HistoricalAccountExcel`, encabezado en fila 11.

| Campo original | Ejemplo | LISTS actual | Estado | Canónico | Uso en débitos |
|---|---|---|---|---|---|
| Fecha / Hora | 01/08/2026 · 09:50:07 | FECHA/HORA | Mapeado | FECHA/HORA | |
| Glosa | CHEQUE 00015496 · PagoHAB-… | DESCRIPCIÓN | Mapeado (el banco la trunca a 20 caracteres) | GLOSA | Nro. de cheque, pago de haberes |
| Tipo | 4401 · 3001 · 2401 · SI · SC | INFO ADICIONAL posición 1 | **En texto sin etiqueta** | TIPO_TRANSACCION | 4401/3001/3002/3003 son débitos |
| Suc. Age. | 301314 | INFO ADICIONAL posición 2 | En texto sin etiqueta | SUCURSAL_AGENCIA | |
| Usuario | HX1 · OBK | INFO ADICIONAL posición 3 | En texto sin etiqueta | USUARIO_BANCO | |
| Importe | -458.82 | IMPORTE/DÉBITO/CRÉDITO/TIPO | Mapeado | IMPORTE_FIRMADO | |
| Saldo | 2,136,281.62 | SALDO | Mapeado | SALDO | |
| Nro. Operación | 15 | CÓDIGO DE ASIGNACIÓN | Mapeado, **no único** (17 repetidos en BCP_MN) | NRO_OPERACION | |

**BISA (MN, ME)**, hoja `Extracto de Movimientos`, encabezado en fila 12.

| Campo original | Ejemplo | LISTS actual | Estado | Canónico |
|---|---|---|---|---|
| Fecha / Hora | 17/08/26 · 10:02 | FECHA/HORA | Mapeado (año de 2 dígitos) | FECHA/HORA |
| **Nro. Cheque** | 0 | — | **PERDIDO** | NRO_CHEQUE |
| Descripción | Transferencia terceros eBISA | DESCRIPCIÓN | Mapeado | DESCRIPCION |
| Importe / Saldo | 1.139,00 · 63.826,52 | IMPORTE…/SALDO | Mapeado | IMPORTE_FIRMADO/SALDO |
| Info. Complementaria | Nombre:FRIAS NATALIA Doc.ID:CCB-… | INFO ADICIONAL | Mapeado (el nombre no se extrae a DEPOSITANTE) | INFO_COMPLEMENTARIA |
| Sucursal / Canal | CB - Principal · e-BISA | INFO ADICIONAL ("Sucursal: ", "Canal: ") | En texto etiquetado | SUCURSAL_AGENCIA/CANAL |
| Nro. Ref. | 53519247217 | CÓDIGO DE ASIGNACIÓN | Mapeado | REFERENCIA |
| **Codigo** | 034 | — | **PERDIDO** | CODIGO_BANCO_TRX |
| **Nro. Lote** | (vacío en la muestra) | — | **PERDIDO** | NRO_LOTE |

**Banco Económico (CTA_CTE, AHORRO)**, hoja `Extracto`, encabezado en fila 17.

| Campo | Ejemplo | LISTS actual | Estado | Canónico | Uso en débitos |
|---|---|---|---|---|---|
| Fecha / Hora | 01/Ago/2026 · 17:02:29 | FECHA/HORA | Mapeado | FECHA/HORA | |
| Nro Trn./Cheque | 358943146 | CÓDIGO DE ASIGNACIÓN | Mapeado | NRO_OPERACION | Nro. de cheque |
| Transacción | CREDITO ACH QR · DEBIT.AUTOMATICO TARJETA… | DESCRIPCIÓN | Mapeado | TIPO_TRANSACCION | Tipo de cargo |
| Nota | BAZAN MEDINA DIANARA (B.UNION) INGRESOS… | INFO ADICIONAL | Mapeado (el nombre no se extrae) | NOTA | Concepto del cargo |
| Monto / Saldo | -6.0 · 273520.8 | IMPORTE…/SALDO | Mapeado | IMPORTE_FIRMADO/SALDO | |

**BMSC**, hoja `Excel`, encabezado en fila 12, con 21 columnas.

| Campo | Ejemplo | LISTS actual | Estado | Canónico |
|---|---|---|---|---|
| Fecha / Hora | 12/08/2026 · 17:31:00 | FECHA/HORA | Mapeado | FECHA/HORA |
| Cod. Bca. | TT26224V735L | CÓDIGO DE ASIGNACIÓN | Mapeado | CODIGO_BANCO_TRX |
| **Nro.Cheque** | (vacío) | — | **PERDIDO** | NRO_CHEQUE |
| **Nro/Nom.Plantilla** | (vacío) | — | **PERDIDO** | PLANTILLA |
| **Cod.Dep.Num** | (vacío) | — | **PERDIDO** | COD_DEP_NUM |
| Doc.Depositante | 4153606TJ | INFO ("DOC: ") | En texto etiquetado | DEPOSITANTE_DOC |
| Nombre/Denominación Depositante | CASTRILLO DE ALTAMIRANO ROSARIO | DEPOSITANTE / ORIGINANTE | Mapeado | DEPOSITANTE_NOMBRE |
| **Tipo transact** | (vacío) | — | **PERDIDO** | TIPO_TRANSACCION |
| Descripción | DEPOSITO DE EFECTIVO 4153606TJ … | DESCRIPCIÓN | Mapeado | DESCRIPCION |
| **Oficina** | " " | — | **PERDIDO** | OFICINA |
| **Banco** | BANCO MERCANTIL SANTA CRUZ S.A | — | **PERDIDO** | BANCO_CONTRAPARTE |
| **Tipo dep** | (vacío) | — | **PERDIDO** | TIPO_DEPOSITO |
| **Nom.Destinatario** | (vacío) | — | **PERDIDO**: clave para débitos | DESTINATARIO_NOMBRE |
| Glosa / Originador / Originador ACH | Transferencia · MONTERO CORTEZ… | INFO ("GLOSA: " …) | En texto etiquetado | GLOSA/ORIGINADOR/ORIGINADOR_ACH |
| **Ciudad Origen** | TA · LP · CB | — | **PERDIDO** | CIUDAD_ORIGEN |
| Débito / Crédito / Saldo | 3,718.00 | DÉBITO/CRÉDITO/SALDO | Mapeado | DEBITO/CREDITO/SALDO |

**Banco Unión (MN y ME, formato `UNION_FECHAS_V1`)**, hoja `ExtractoMovimientosFechas`, encabezado en fila 16 (fila del MN real; la de ME, **REQUIERE ARCHIVO REAL VACÍO**). Las columnas de Excel están combinadas y los datos caen bajo cada encabezado; verificado, no hay celdas de movimiento sin encabezado.

| Campo | Ejemplo | LISTS actual | Estado | Canónico |
|---|---|---|---|---|
| Fecha Movimiento | 01/08/2026 | FECHA MOVIMIENTO | Mapeado (el banco no entrega hora) | FECHA |
| AG | CBB · ORU · LPZ · SUC | INFO ("AG: ") | En texto etiquetado | SUCURSAL_AGENCIA |
| Descripción | N/C TRASP. DESDE MAMANI COPA BERTHA | DESCRIPCIÓN | Mapeado | DESCRIPCION |
| Nro Documento | 74583632 | CÓDIGO DE ASIGNACIÓN | Mapeado | NRO_DOCUMENTO |
| Monto / Saldo | 700.00 · 236,880.41 | IMPORTE…/SALDO | Mapeado | IMPORTE_FIRMADO/SALDO |
| **Nro de verificasion** (UNION_ME; **confirmada por captura real; el motor legado no la contempla**; contenido real pendiente) | sin muestra con movimientos | — | **PERDIDO**: el motor no la lee | NRO_VERIFICACION |

### 1.3 Cabecera, pie y hojas adicionales

Destino propuesto de todas: **METADATOS_EXTRACTO**. La celda de cada campo está en la matriz CSV.

| Formato | Campos de cabecera o pie (ejemplo real) | Estado actual |
|---|---|---|
| BCP | EXTRACTOS BANCARIOS; Fecha: 21/08/2026; Hora: 08:56 AM; Titular; Cuenta: 301-5005425-2-71. **Filas especiales** SALDO INICIAL (Tipo SI) y SALDO AL CIERRE (Tipo SC) | Cuenta y título: solo detección. Filas SI/SC: solo validación (quedan fuera de LISTS). Resto: perdido |
| BISA | Fecha y hora de emisión; Cliente Nro.: 0000069687(lvelasquezs26); Nombre; Al:…; Numero de Cuenta; Nombre de Cuenta; Producto: Bisa Gestion; Moneda: Bs/USD; Estado de Cuenta: Activa; Saldo Inicial: 62.687,52; Desde/Hasta. **Pie:** Total Creditos: 1.139,00; Total Debitos: 0,00 | Saldo inicial por celda fija G8, solo validación. Resto perdido |
| BNB | Número De cuenta: 3000100152 (única cabecera) | Solo detección |
| Económico | Título; En Bolivianos; Del 01/Ago/2026 al 21/Ago/2026; Titular; Cuenta: `CC: 3041210569 (Bs)`; Otros Titulares; Producto: BASICA-PERSONA JURIDICA; Estado; Administración; **Saldo Inicial / Saldo Final**; **Retenciones Judiciales; Fondos Reservados; Dep. por confirmar**; filtros de búsqueda del reporte (texto, montos, rango, fechas) | Saldos solo para validación. Resto perdido |
| BMSC | Extracto de cuenta; Titular; Nro de Cuenta: 1000872489; Fecha de emisión; Tipo de producto: CUENTA CORRIENTE; **Saldo: Bs 201,662.79**; período 01/08/2026 - 21/08/2026. **Hoja adicional `Reporte de Pagos`** (Detalle Planilla: Nro Planilla, Cuenta Débito, Beneficiario, Cuenta/Banco Destino, Monto, Estado, Referencia, Cód. Bancarización…) | Todo perdido. La hoja de planillas nunca se lee: en la muestra solo trae encabezados, **REQUIERE MUESTRA REAL con planilla** |
| Unión | Título; Titular; Cuenta; Producto: UNICUENTA NORMAL PERSONA JURIDICA M/N; Desde/Hasta. **Pie:** Total Créditos 143,466.20; Total Débitos 0.00; **Tránsito 0.00; Consultado 0.00; Congelado 40,578.52; Sobregirado 0.00; Disponible 339,068.09; Total 379,646.61** | Todo perdido |

**Hallazgo útil:** varios bancos ya traen un saldo **independiente** que hoy no se aprovecha.

| Banco | Saldo independiente en el archivo | Comprobación |
|---|---|---|
| Unión | Pie «Total» = 379,646.61 | Coincide con el saldo final |
| BMSC | Cabecera «Saldo: Bs 201,662.79» | Coincide con el saldo final |
| BISA | Totales de pie | Coinciden con lo normalizado |

Hoy los tres bancos reconstruyen su saldo desde la primera fila. Con estos datos, **solo BNB quedaría sin saldo independiente.**

---

## 2. Qué pierde hoy cada normalizador

| Normalizador | Perdido del todo | Degradado (existe, pero no se recupera fielmente) | Débitos |
|---|---|---|---|
| `normalizar_bnb` | Oficina, **Referencia**, ITF; texto literal de la cuenta | **D-18** (defecto nuevo): la regex de DEPOSITANTE sobre-captura. `Nombre Originante: CORREA HOLANDA RIHAN. Banco: BANCO GANADERO. Dato Adicional: …` se guarda completo como depositante, porque solo corta en `;`. | **D-19**: en «Debito Cta por ACH» el `Nombre:` de Adicionales es el **beneficiario**, y en «Debito Pago Cheque Efectivo» es quien cobró el cheque; ambos quedan en `DEPOSITANTE / ORIGINANTE`. Se pierde el **nro. de cheque** y la **ref. de pago web** (Referencia): 620 débitos en BNB_MN. |
| `normalizar_bcp` | Emisión (fecha/hora), titular; filas SALDO INICIAL/AL CIERRE fuera del dato | Tipo, Suc. Age. y Usuario unidos con `|` **sin etiqueta**: solo se recuperan por posición, y un campo vacío corre el resto | 445 débitos (PagoHAB, CHEQUE, PAGO TARJETA): su tipo 4401/300x queda sin etiqueta |
| `normalizar_bisa` | Nro. Cheque, Codigo, Nro. Lote; toda la cabecera; totales de pie | Nombre y Doc.ID del depositante solo en texto libre | Sin débitos en la muestra: **REQUIERE MUESTRA REAL** |
| `normalizar_economico` | Toda la cabecera (producto, estado, retenciones, fondos reservados, depósitos por confirmar, período) | El nombre del depositante vive en Nota y no se extrae | Conserva todo (Transacción, Nota, Nro Trn.) |
| `normalizar_bmsc` | 9 columnas (Nro.Cheque, Plantilla, Cod.Dep.Num, Tipo transact, Oficina, Banco, Tipo dep, **Nom.Destinatario**, Ciudad Origen); cabecera; **hoja Reporte de Pagos** | — | Sin débitos en la muestra; justo las columnas de débito son las perdidas: **REQUIERE MUESTRA REAL** |
| `normalizar_union` | Producto, período, **todo el pie** (fondos congelados, disponible, total) | — | Sin débitos en la muestra: **REQUIERE MUESTRA REAL** |

**Transformaciones sin retorno que afectan a todos:**

- El número se guarda ya convertido (`' 63.826,52'` → 63826.52) y la fecha ya convertida (`17/08/26`, `01/Ago/2026`).
- `codigo_texto` quita espacios y `.0`.
- Se pierden los espacios de relleno del banco (Referencia BNB de 20 caracteres, Tipo BCP `'4401  '`).

No es un error del operativo, pero hoy **no queda el valor tal como lo emitió el banco.**

D-18 y D-19 cambian el contenido de una columna de las 26. Corregirlos es un **cambio de contrato** y queda para tu decisión (ver 7). En esta fase el dato correcto se conserva en `DATOS_ORIGINALES`.

---

## 3. Estructura de `DATOS_ORIGINALES`

**Decisión: formato largo, una fila por celda.** No se crean columnas Referencia 1/2/3 ni un esquema ancho común.

Cada banco aporta exactamente las columnas que trae. Un banco o columna nuevos no cambian la estructura, y la completitud se puede demostrar celda por celda.

| Columna | Tipo | Contenido |
|---|---|---|
| ID_EXTRACTO | texto(64) | SHA-256 de los bytes del archivo original (identifica la evidencia exacta) |
| ID_ORIGEN | texto | `{ID_EXTRACTO[:16]}|{HOJA}|R{FILA_EXCEL}`: identifica la **fila** original |
| ID_CELDA | texto | `ID_ORIGEN|{COLUMNA_EXCEL}` |
| ARCHIVO ORIGEN | texto | Nombre original (igual que en el operativo) |
| HOJA | texto | Nombre de la hoja tal cual |
| FILA_EXCEL | entero | Fila 1-based como se ve en Excel |
| COLUMNA_EXCEL | texto | Letra (A, B, …, AC) |
| ROL_FILA | texto | CABECERA · ENCABEZADO_TABLA · MOVIMIENTO · SALDO_INICIAL · SALDO_CIERRE · TOTAL_PIE · RESUMEN_PIE · SIN_FECHA (descartada) · HOJA_EXTRA · OTRA |
| CAMPO_ORIGINAL | texto | Texto exacto del encabezado del banco (`Nom.Destinatario`, `Suc. Age.`) |
| CAMPO_CANONICO | texto, puede ir vacío | Etiqueta común tomada del registro (REFERENCIA, OFICINA, NRO_CHEQUE…) para consultar entre bancos |
| VALOR_ORIGINAL | texto | Valor **sin recortar ni convertir** |
| TIPO_CELDA | texto | TEXTO · NUMERO · FECHA · BOOLEANO |
| CLAVE TRANSACCIÓN | texto | Solo si ROL_FILA = MOVIMIENTO. Enlaza con el operativo |
| LOTE DE CARGA | texto | Igual que en el operativo |

**Cómo se enlaza con el operativo.** El enlace va en una hoja aparte, `MAPA_ORIGEN`, con una fila por movimiento: CLAVE TRANSACCIÓN, ID_ORIGEN, ARCHIVO ORIGEN, HOJA, FILA_EXCEL y LOTE. La relación es 1:1 dentro del lote.

No se agrega una columna 27 a LISTS en esta fase, para no tocar `tblLISTS` ni la carga a Lists. Ya verifiqué que el enlace es viable sin heurísticas: en los 12 fixtures válidos, cada fila normalizada cumple `FILA_EXCEL = fila_encabezado + 2 + índice`. El motor ya conserva ese índice hasta `finalizar_dataframe` y lo pierde recién en `pd.concat(ignore_index=True)`.

**Distinción importante: ID_ORIGEN no es la identidad del movimiento.** Los extractos son acumulados: los períodos de cabecera van desde el inicio del mes, o incluso desde el 01/01 en BISA_ME, hasta la fecha de descarga. Por eso el mismo movimiento aparece en los archivos de varios días. Por eso:

- `CLAVE TRANSACCIÓN` identifica la transacción.
- `ID_ORIGEN` identifica **cada aparición como evidencia**.

En el histórico, una CLAVE podrá tener varios ID_ORIGEN. Eso es correcto y sirve de pista de auditoría.

**Qué se captura.** Todas las celdas no vacías de **todas** las hojas, **incluidas las de cabecera, encabezado de tabla y pie** (ROL_FILA = CABECERA, ENCABEZADO_TABLA, PIE…). **Ajuste respecto de la versión 1:** antes las celdas de cabecera y pie vivían solo en `METADATOS_EXTRA`; ahora `DATOS_ORIGINALES` es el inventario del 100 % de las celdas y las tablas de METADATOS pasan a ser una **interpretación derivada** de él (se siguen guardando, por comodidad). Motivo: la capa 4 debe poder reconstruirse desde `DATOS_ORIGINALES` + `NORMALIZADO`, sin releer el banco, y necesita el encabezado, el orden de columnas y los datos de la parte superior. Eso incluye las filas SALDO INICIAL/AL CIERRE de BCP, las filas de totales y las filas sin fecha interpretable (ROL_FILA = SIN_FECHA), que hoy desaparecen sin rastro.

**Volumen.** Las 36.700 celdas de esta muestra caben de sobra en Excel. A 20.000 movimientos/mes × ~11 campos serían ~220.000 filas/mes: para archivo o histórico, **no** para Microsoft Lists.

**Vista humana:** ya no se plantea una hoja ancha técnica (`RAW_*`) en `ORIGEN.xlsx`. Esa necesidad la cubre la capa 4 (sección 6), que sí está pensada para personas.

**Fuera del alcance de esta fase (capa 2b, `DERIVADOS`):** subcampos interpretados de textos estructurados, por ejemplo `Cuenta Destino`, `Nombre`, `Banco` y `Dato Adicional` de Adicionales BNB, o `Nombre`/`Doc.ID` de Info. Complementaria BISA. Irían en otra hoja con `CAMPO_PADRE`, sin mezclarse con la evidencia pura. Ahí se resolvería el rol ORIGINANTE vs. BENEFICIARIO de D-19.

---

## 4. Estructura de `METADATOS_EXTRACTO`

**4.1 Tabla fija:** una fila por archivo.

| Grupo | Columnas |
|---|---|
| Identidad | ID_EXTRACTO, ARCHIVO ORIGEN, TAMAÑO_BYTES, LOTE DE CARGA, FECHA DE CARGA, VERSION_MOTOR, VERSION_REGISTRO |
| Reconocimiento | FORMATO (código actual: BNB_MN…), FAMILIA_FORMATO, HOJAS_EN_ARCHIVO, HOJA_LEIDA, FILA_ENCABEZADO, PUNTAJE_ENCABEZADO, COLUMNAS_ORIGINALES (lista en orden) |
| Cuenta | BANCO, CUENTA BANCARIA, CUENTA_EN_ARCHIVO (literal, p. ej. `CC: 3041210569 (Bs)`), MONEDA, MONEDA_EN_ARCHIVO (`Bs`, `USD`, `En Bolivianos`), TITULAR, NOMBRE_CUENTA, PRODUCTO, ESTADO_CUENTA |
| Período y emisión | PERIODO_DESDE, PERIODO_HASTA, PERIODO_TEXTO, FECHA_EMISION, HORA_EMISION, FECHA_CORTE |
| Saldos | SALDO_INICIAL, SALDO_INICIAL_FUENTE (CABECERA · FILA_SI · CELDA_FIJA · RECONSTRUIDO), SALDO_FINAL, SALDO_FINAL_FUENTE (CABECERA · FILA_SC · PIE_TOTAL · ULTIMA_FILA), TOTAL_CREDITOS_PIE, TOTAL_DEBITOS_PIE |
| Conteos | FILAS_TABLA, FILAS_MOVIMIENTO, FILAS_ESPECIALES, FILAS_SIN_FECHA, MOVIMIENTOS_CREDITO, MOVIMIENTOS_DEBITO |
| Resultado | ESTADO_VALIDACION, DIFERENCIA, OBSERVACIONES |

**4.2 Tabla abierta `METADATOS_EXTRA`:** una fila por etiqueta y valor, sin límite de campos.

Columnas (derivadas de `DATOS_ORIGINALES` con las etiquetas del registro): ID_EXTRACTO, HOJA, CELDA_ETIQUETA, ETIQUETA (texto exacto), CELDA_VALOR, VALOR_ORIGINAL, CAMPO_CANONICO (o vacío si el registro no lo conoce), ZONA (CABECERA · PIE · HOJA_EXTRA).

Aquí quedan, sin ampliar la tabla fija: Retenciones Judiciales, Fondos Reservados, Dep. por confirmar, Congelado, Consultado, Sobregirado, Disponible, Cliente Nro. (incluye el usuario de consulta `lvelasquezs26`), filtros del reporte y cualquier etiqueta que un banco agregue mañana.

---

## 5. Registro parametrizable de bancos y cuentas

Es un archivo de configuración versionado, `registro_bancos.json`, con dos niveles: el **formato** describe la estructura del reporte y la **cuenta** describe la instancia. Una cuenta nueva de un formato conocido se agrega con **una entrada y cero código**.

```
FORMATOS
  BNB_EXTRACTO_V1
    hojas_aceptadas:      ["Hoja 1", "Hoja"]
    firma:                todas ["CODIGO DE TRANSACCION", "ADICIONALES"]
    encabezados:          requeridos [Fecha, Hora, Descripción, Código de transacción, Saldo, Adicionales]
                          opcionales [Oficina, Referencia, ITF, Débitos, Créditos]
                          puntaje_minimo = 100 %
    cuenta_en_cabecera:   etiqueta "Número De cuenta", zona = filas previas al encabezado
    fecha:                columna "Fecha", formatos ["dd/mm/aaaa"]
    hora:                 columna "Hora"
    importe:              modo DEBITO_CREDITO (debito "Débitos", credito "Créditos")
    codigo_asignacion:    "Código de transacción"
    descripcion:          "Descripción"
    depositante:          estrategia "legacy_bnb" (función con nombre; conserva el resultado actual)
    info_adicional:       modo CRUDO columna "Adicionales"          ← reproduce el formato actual byte a byte
    filas_excluir:        []
    saldo_inicial:        [RECONSTRUIDO]
    saldo_final:          [ULTIMA_FILA_CRONOLOGICA]
    orden_validacion:     CRONOLOGICO
    metadatos:            []                                         ← no hay más cabecera
    campos_canonicos:     {Oficina: OFICINA, Referencia: REFERENCIA, ITF: ITF, …}

  UNION_FECHAS_V1                       ← aplica a UNION_MN **y UNION_ME**
    hojas_aceptadas:      ["ExtractoMovimientosFechas"]
    encabezados:          requeridos [Fecha Movimiento, Descripción, Nro Documento, Monto]
                          opcionales [AG, Saldo, **Nro de verificasion**]   ← se conserva como campo original
    firma:                todas ["FECHA MOVIMIENTO", "NRO DOCUMENTO"]
    cuenta_en_cabecera:   etiqueta "Cuenta:"
    importe:              modo SIGNO columna "Monto"
    info_adicional:       modo ETIQUETADO [("AG: ", "AG")]
    saldo_final:          [PIE_TOTAL etiqueta "Total", ULTIMA_FILA]   ← gana la fuente independiente
    metadatos:            [Producto:, Desde/Hasta, Total Créditos:, Total Débitos:, Tránsito, Consultado,
                           Congelado, Sobregirado, Disponible, Total]
  UNION_ULTIMOS12_V1
    hojas_aceptadas:      ["ExtractoMovimientosUltimos"]
    aceptado:             NO   ← reporte real que existe, pero NO es un extracto (fixture negativo)
    mensaje:              "Reporte 'Últimos 12 movimientos': descargar el extracto por rango de fechas"

CUENTAS  (el id conserva el código actual para no alterar VALIDACION/DIAGNOSTICO)
  BNB_MN       formato BNB_EXTRACTO_V1   banco "BNB"          cuenta "3000100152"      moneda BOB  activa
  BNB_ME       formato BNB_EXTRACTO_V1   banco "BNB"          cuenta "3400041236"      moneda USD  activa
  …
  UNION_MN     formato UNION_FECHAS_V1   banco "BANCO UNIÓN"  cuenta "10000003224552"  moneda BOB  activa
  UNION_ME     formato UNION_FECHAS_V1   banco "BANCO UNIÓN"  cuenta "20000003224544"  moneda USD  activa   ← muestra vacía; movimientos: REQUIERE MUESTRA REAL
  BMSC         formato BMSC_EXCEL_V1     banco "BMSC"         cuenta "1000872489"      moneda BOB  activa
```

Cada formato recibe además un bloque `historico`, que define qué muestra la capa 4 y cómo (ver 6.7). Es configuración: agregar un banco nuevo no exige código de presentación.

**Motor genérico:** es la misma secuencia para todos los bancos, sin `if formato.startswith(...)`.

1. **Firma → formato.** La firma se busca solo en la cabecera y el encabezado, no en los datos.
2. **Hoja aceptada y puntaje mínimo.** Si faltan, error explícito con el motivo.
3. **Cuenta leída en la cabecera → búsqueda `CUENTAS[(formato, cuenta)]`.** Hay tres salidas:
   - Una coincidencia: se procesa.
   - Formato conocido pero cuenta no registrada: `NO_RECONOCIDO` con el mensaje «formato X reconocido, cuenta Y no registrada».
   - Dos o más cuentas: error.

   Esto cierra D-10, D-11 y D-12.
4. **Captura íntegra de celdas** (capas 2 y 3) **antes** de cualquier limpieza. Esto cierra D-17: ninguna columna vacía se descarta antes de registrarla.
5. **Mapeo al operativo con reglas declarativas.** Tipos de regla: DIRECTO, DEBITO_CREDITO, SIGNO, ETIQUETADO, PIPE_SIN_ETIQUETA (el legado de BCP), CRUDO, CONSTANTE y ESTRATEGIA_CON_NOMBRE.
6. **Validación con fuentes de saldo priorizadas.** Primero la fuente independiente, luego la reconstrucción.

**Excepciones que se conservan como estrategias con nombre, no como ramas por banco:**

- `legacy_bnb` para DEPOSITANTE, hasta que decidas D-18 y D-19.
- `celda_fija G8` de BISA, que conviene reemplazar por la etiqueta «Saldo Inicial:», presente en la cabecera.
- El filtrado de filas SI/SC de BCP, que pasa a ser `filas_excluir` con ROL_FILA.

**Requisito de compatibilidad:** las reglas de `INFORMACIÓN ADICIONAL` deben reproducir **exactamente** el texto actual. Por ejemplo, BCP sin etiqueta con `|`, y BMSC `DOC: …| GLOSA: …`. Las doradas lo controlan.

---

## 6. Cuarta capa: SALIDA_HUMANA / EXTRACTO_HISTORICO

### 6.1 Qué es y qué no es

Es un Excel **para leer, filtrar y rastrear operaciones**: se parece a un extracto bancario, con las columnas propias de cada banco, y al final las tres columnas operativas.

- **No** es `ORIGEN.xlsx` ni `NORMALIZADO.xlsx`. No muestra IDs técnicos, hashes, fila original, versión del motor ni campos de auditoría.
- **No** unifica el esquema visual entre bancos: cada banco conserva sus columnas y sus nombres.
- Es un **artefacto derivado y reproducible**: se construye solo con `DATOS_ORIGINALES` + `NORMALIZADO` (+ registro), sin volver a abrir el archivo bancario.

### 6.2 Unidad de salida: banco / cuenta / período

**Un archivo por cuenta y mes calendario**, con una sola hoja `EXTRACTO`. Nombre propuesto: `EXTRACTO_HISTORICO_{BANCO}_{CUENTA}_{MONEDA}_{AAAA-MM}.xlsx` (por ejemplo `EXTRACTO_HISTORICO_BNB_3000100152_BOB_2026-08.xlsx`).

| Regla | Detalle |
|---|---|
| Período | Mes calendario de `FECHA MOVIMIENTO`, **no** el rango del extracto descargado |
| Extracto que cruza meses | Se reparte en un archivo por mes. Ejemplo real: BISA_ME declara período 01/01/2026–21/08/2026; hoy no tiene movimientos, así que no generaría archivo |
| Cuenta sin movimientos en el mes | No se genera archivo vacío; queda registrado en METADATOS_EXTRACTO (`FILAS_MOVIMIENTO = 0`) |
| Estado actual de la muestra | 12 extractos válidos → 11 archivos (10 de agosto 2026 y BCP_ME de julio 2026); BISA_ME no genera archivo |
| Ruta | Por definir con el bloque de cierre histórico. Se propone la misma lógica banco/cuenta/mes de la carpeta mensual actual; **no la fijo aquí** |

### 6.3 Anatomía de la hoja

```
┌ Zona superior (datos amigables, solo los que vienen en el archivo) ──────────────┐
│ EXTRACTO BANCARIO · BNB · Cuenta 3000100152 · BOB · Agosto 2026                     │
│ Titular / Producto / Período del extracto / Fecha de emisión / Saldo inicial /      │
│ Saldo final / Totales del pie …  (etiquetas tal como las entrega el banco)          │
├ Tabla ────────────────────────────────────────────────────────────────────────────┤
│ [ columnas bancarias en su orden original ]  │ ESTADO │ CONFIRMADO POR │ FECHA DE   │
│ Fecha │ Hora │ Oficina │ … │ Adicionales       │        │                │CONFIRMACIÓN│
└────────────────────────────────────────────────────────────────────────────────────┘
```

- **Fila de encabezado** con filtros y paneles inmovilizados. Datos en formato de tabla de Excel.
- **Bloque bancario** con el estilo del bloque «extracto» de tu plantilla (guindo/burdeos con texto blanco) y **bloque operativo** en grafito/gris, para que se distinga a simple vista qué entregó el banco y qué se completa después.
- **Orden de filas:** cronológico (`FECHA`, `HORA`) y, a igualdad, el **orden original del archivo**. Así se respeta el orden real del banco entre movimientos del mismo segundo (caso BNB_MN, ver Fase 2).
- **Filas SALDO INICIAL y SALDO AL CIERRE (BCP)** no van como movimientos, ya que no llevan ESTADO ni confirmación. Sus valores suben a la zona superior.
- Sin hojas visibles adicionales. Nada de columnas técnicas visibles (ver 6.9).

**Zona superior por banco (solo si el archivo lo trae):**

| Banco | Se muestra | Saldos informados por el banco |
|---|---|---|
| BCP | Titular, Cuenta, fecha y hora de emisión | Saldo inicial y saldo al cierre (filas SI / SC) |
| BISA | Nombre de cuenta, Producto, Moneda, Estado de cuenta, Desde/Hasta | Saldo inicial; Total créditos / débitos (pie) |
| BNB | Solo la cuenta | Ninguno. El período cubierto se calcula de los movimientos y se rotula «calculado» |
| Económico | Titular, Cuenta, Producto, Estado, Administración, Período | Saldo inicial, Saldo final, Retenciones judiciales, Fondos reservados, Dep. por confirmar |
| BMSC | Titular, Nro. de cuenta, Tipo de producto, Fecha de emisión, período | Saldo (a la fecha de emisión) |
| Unión | Titular, Cuenta, Producto, Período | Total créditos/débitos, Tránsito, Consultado, Congelado, Sobregirado, Disponible, Total |

- **No se muestra:** el usuario de consulta de BISA (`Cliente Nro.`), los filtros del reporte de Económico y los títulos de reporte. Siguen en `ORIGEN.xlsx`.
- **Honestidad de los saldos:** los saldos declarados corresponden al período del **extracto**, no necesariamente al mes del archivo. Se rotulan con ese período («Saldo inicial del extracto, desde 01/08/2026»). Un saldo calculado para el mes, si se agrega, se rotula «calculado». Nada se inventa.

### 6.4 Columnas bancarias que muestra cada formato

Regla: **todas las columnas con encabezado que entrega el banco, en su orden y con su nombre**, fijadas por formato en el registro. Así el archivo del mes 1 y el del mes 2 tienen la misma forma aunque una columna venga vacía un período (ejemplo: `Nom.Destinatario` de BMSC, que es clave en los débitos).

| Formato | Columnas visibles (antes de ESTADO / CONFIRMADO POR / FECHA DE CONFIRMACIÓN) |
|---|---|
| BNB (MN, ME, AHORRO, CLINICA) | Fecha · Hora · Oficina · Descripción · **Referencia** · Código de transacción · **ITF** · Débitos · Créditos · Saldo · **Adicionales** (11) |
| BCP (MN, ME) | Fecha · Hora · Glosa · **Tipo** · **Suc. Age.** · **Usuario** · Importe · Saldo · Nro. Operación (9) |
| BISA (MN, ME) | Fecha · Hora · **Nro. Cheque** · Descripción · Importe · Saldo · Info. Complementaria · Sucursal · Canal · Nro. Ref. · **Codigo** · **Nro. Lote** (12) |
| Económico (CTA_CTE, AHORRO) | Fecha · Hora · Nro Trn./Cheque · Transacción · Nota · Monto · Saldo (7) |
| BMSC | Fecha · Hora · Cod. Bca. · **Nro.Cheque** · **Nro/Nom.Plantilla** · **Cod.Dep.Num** · Doc.Depositante · Nombre/Denominación Depositante · **Tipo transact** · Descripción · **Oficina** · **Banco** · **Tipo dep** · **Nom.Destinatario** · Glosa · Originador · Originador ACH · **Ciudad Origen** · Débito · Crédito · Saldo (21) |
| Unión MN | Fecha Movimiento · AG · Descripción · Nro Documento · Monto · Saldo (6, observadas en el MN real) |
| **Unión ME** (`UNION_FECHAS_V1`) | Fecha Movimiento · AG · Descripción · Nro Documento · Monto · Saldo · **Nro de verificasion** (7; **estructura confirmada** por código legado + captura real; contenido y comportamiento con datos: **REQUIERE MUESTRA REAL CON MOVIMIENTOS**) |

En negrita, las columnas que **hoy el operativo pierde o degrada**; aquí reaparecen completas y separadas, no concatenadas.

- **Débitos:** ninguna columna se elimina ni se resume. Un débito de BNB_MN muestra Oficina, Referencia (nro. de cheque o referencia de pago web), Código, ITF y el texto completo de Adicionales; uno de BCP muestra Glosa, Tipo, Suc. Age., Usuario y Nro. Operación.
- **Unión:** `Nro de verificasion` es un campo original del banco: se conserva en `DATOS_ORIGINALES` y se muestra en el histórico de UNION_ME, como texto (no se asume que sea numérico). Si el MN también lo trae algún día, el bloque `historico` lo muestra por cuenta sin tocar código; si el MN no lo trae, esa columna no aparece en su archivo. Las columnas combinadas de Excel del original (los datos caen bajo celdas combinadas) **no** se reproducen; se muestran las 6 columnas reales, no los espaciadores.
- **Columna nueva en un extracto** (el banco agrega un campo): se agrega automáticamente **antes** de las columnas operativas, con su encabezado original, y se deja una advertencia en el diagnóstico. Nunca se pierde en silencio.
- **Quedan fuera de la capa 4** (por tu regla de «únicamente» tres columnas operativas): ESTUDIANTE, SOLICITADO POR, SEDE SOLICITANTE, OBSERVACIÓN y TEXTO DE BÚSQUEDA. Siguen en Lists y en `NORMALIZADO`.

### 6.5 Reglas de presentación de valores

| Tipo de columna | Regla |
|---|---|
| Importes y saldos | **Numéricos**, tomados de `NORMALIZADO` (ya validados y cuadrados), con formato `#,##0.00`. Débitos y créditos siguen la convención de cada banco: BNB y BMSC en columnas separadas; BCP, BISA, Económico y Unión, un solo importe con signo |
| Fechas | Fecha de Excel, formato `dd/mm/aaaa` (el que entregan los bancos bolivianos). Es configurable en el registro |
| Horas | `hh:mm:ss`. Unión no entrega hora: la columna no existe |
| Números de cheque, referencias, códigos, documentos, cuentas | **Siempre texto**, sin perder ceros a la izquierda (`0000335`, `034`) |
| Textos | Contenido **completo**. Solo se recortan los espacios de relleno al inicio y al final (`'4401  '` → `4401`, `'COCHABAMBA…   '`); el valor exacto sigue en `ORIGEN.xlsx` |
| Valores vacíos | Celda vacía; nunca un cero ni un guion inventado |
| Encabezados | El nombre del banco, limpiando saltos de línea (`Monto⏎` → `Monto`) |
| Anchos | Definidos por formato; el texto largo (Adicionales, Descripción) se corta visualmente por el ancho, pero **la celda contiene todo el texto** |

Las columnas de importe, saldo, fecha y hora se llenan desde `NORMALIZADO` (vía `MAPA_ORIGEN`) y **no** se vuelven a convertir desde el texto original. Así el número que ve Contabilidad es exactamente el que se carga a Lists, y no existen dos conversiones que puedan divergir.

### 6.6 Cómo se genera

Es una **función pura**, sin lectura de archivos bancarios:

```
construir_extractos_historicos(DATOS_ORIGINALES, MAPA_ORIGEN, NORMALIZADO, REGISTRO, ESTADOS=None)
    → un resultado por (BANCO, CUENTA, MONEDA, AAAA-MM)
escribir_extracto_historico(resultado, ruta)          ← única parte que escribe Excel
```

Pasos:

1. **Agrupar.** Se toman las filas de `NORMALIZADO` y, con `MAPA_ORIGEN`, se agrupan por `(BANCO, CUENTA BANCARIA, MONEDA, mes de FECHA MOVIMIENTO)`. Cada grupo es un archivo.
2. **Formato.** Del registro se lee, para la cuenta, su formato y el bloque `historico`: columnas, orden, tipos, anchos y datos de la zona superior.
3. **Pivotar los movimientos.** De `DATOS_ORIGINALES` se toman las celdas con `ROL_FILA = MOVIMIENTO` de cada `ID_ORIGEN` del grupo y se acomodan por `COLUMNA_EXCEL` en el orden del formato, con `CAMPO_ORIGINAL` como encabezado.
4. **Reemplazar por valores validados.** Las columnas declaradas `fuente: NORMALIZADO` (fecha, hora, débito, crédito, importe firmado, saldo) se toman de `NORMALIZADO` y no del texto.
5. **Tipar y limpiar** según 6.5.
6. **Zona superior.** Se busca en `DATOS_ORIGINALES` (`CABECERA`, `PIE`, `SALDO_INICIAL`, `SALDO_CIERRE`) cada etiqueta que el registro declare como visible.
7. **Columnas operativas.** `ESTADO`, `CONFIRMADO POR` y `FECHA DE CONFIRMACIÓN` se toman de `NORMALIZADO` (hoy: `DISPONIBLE`, vacío y vacío). Si se entrega la tabla opcional `ESTADOS` (clave = `CLAVE TRANSACCIÓN`), esos valores la reemplazan. Así el bloque de confirmación podrá alimentar la capa 4 sin cambiarla.
8. **Verificar antes de escribir** (ver pruebas 6.10): mismo número de movimientos que `NORMALIZADO`, mismas sumas, ningún movimiento sin su fila de origen, y totales del pie iguales cuando el banco los trae. Si algo falla, no se escribe el archivo y se informa la causa.
9. **Escribir** el `.xlsx` (encabezado, tabla, formatos, colores, filtros, paneles inmovilizados).

**Entradas mínimas:** `ORIGEN.xlsx` (capas 2 y 3) + `NORMALIZADO.xlsx` o `LISTS.csv` + `registro_bancos.json`. **No** se necesita el archivo del banco.

**Reconstruible por diseño:** la salida de una corrida y la salida generada meses después solo con esos tres archivos deben ser idénticas celda por celda (prueba 1 de 6.10).

### 6.7 Bloque `historico` del registro (parametrizable)

Ejemplo conceptual para BMSC y BNB (con los nombres reales de los extractos):

```
FORMATO BNB_EXTRACTO_V1 → historico
  hoja_salida:        "EXTRACTO"
  orden_filas:        [FECHA, HORA, ORDEN_ORIGINAL]
  encabezado_amigable: [ {etiqueta: "Cuenta", fuente: CUENTA_REGISTRADA}, {etiqueta: "Período cubierto", fuente: CALCULADO} ]
  columnas: (orden = orden del banco)
    - {origen: "Fecha",                 fuente: NORMALIZADO:FECHA,       tipo: fecha,  ancho: 12}
    - {origen: "Hora",                  fuente: NORMALIZADO:HORA,        tipo: hora,   ancho: 10}
    - {origen: "Oficina",               fuente: ORIGINAL,                tipo: texto,  ancho: 36}
    - {origen: "Descripción",           fuente: ORIGINAL,                tipo: texto,  ancho: 34}
    - {origen: "Referencia",            fuente: ORIGINAL,                tipo: codigo, ancho: 16}
    - {origen: "Código de transacción", fuente: ORIGINAL,                tipo: codigo, ancho: 16}
    - {origen: "ITF",                   fuente: ORIGINAL,                tipo: importe}
    - {origen: "Débitos",               fuente: NORMALIZADO:DÉBITO,      tipo: importe}
    - {origen: "Créditos",              fuente: NORMALIZADO:CRÉDITO,     tipo: importe}
    - {origen: "Saldo",                 fuente: NORMALIZADO:SALDO,       tipo: importe}
    - {origen: "Adicionales",           fuente: ORIGINAL,                tipo: texto,  ancho: 70}
  columnas_operativas: [ESTADO, CONFIRMADO POR, FECHA DE CONFIRMACIÓN]
  formato_fecha:      "dd/mm/yyyy"

FORMATO BMSC_EXCEL_V1 → historico
  columnas:  … Nom.Destinatario (ORIGINAL, texto) … Débito/Crédito/Saldo (NORMALIZADO) …
  encabezado_amigable: Titular, Nro de Cuenta, Tipo de producto, Fecha de emisión, Saldo (a la emisión) …

FORMATO UNION_FECHAS_V1 → historico
  ignorar_columnas_sin_encabezado: true        ← las columnas combinadas del original
  encabezado_amigable: … Total Créditos, Total Débitos, Tránsito, Consultado, Congelado, Sobregirado, Disponible, Total
```

Un banco o formato nuevo se agrega describiendo sus columnas aquí. No se escribe código de presentación por banco.

### 6.8 Columnas operativas

Solo tres, al final, con el bloque en grafito/gris:

| Columna | Valor al generar | Quién lo completa después |
|---|---|---|
| ESTADO | El de `NORMALIZADO` (`DISPONIBLE`) | Bloque de confirmación (Power Apps / Lists) |
| CONFIRMADO POR | Vacío | Ídem |
| FECHA DE CONFIRMACIÓN | Vacío (formato `dd/mm/aaaa hh:mm`) | Ídem |

La lista válida de estados **no está en ningún archivo**. **REQUIERE DEFINICIÓN** en el bloque de confirmación; aquí no se inventa.

### 6.9 Límites y riesgos de esta capa

1. **Clave de enlace para actualizaciones.** Si más adelante otro bloque debe actualizar ESTADO por fila, necesita `CLAVE TRANSACCIÓN`, que es un dato técnico. Como pediste no mostrarla, hay tres opciones:
   - (a) una **columna oculta** dentro de la tabla (se mueve con el orden y los filtros; no se ve, pero se puede mostrar);
   - (b) **sin clave**: el archivo es de lectura y el estado vive solo en Lists;
   - (c) una hoja oculta paralela (frágil: se desalinea al ordenar la tabla).

   Recomiendo **(a) solo si el archivo se va a actualizar**; si es solo de revisión, **(b)**.
2. **Compatibilidad con Excel Online.** Registraste que una plantilla generada externamente con openpyxl rompió el script de Excel Online (`Bad Request - El script no pudo crear una conexión con Excel`). Antes de conectar la capa 4 a cualquier Office Script o flujo, debe pasar una **prueba de compatibilidad** en Excel Online. Mientras tanto se usa solo como archivo de lectura y no reemplaza la plantilla ni el flujo en producción.
3. **Extractos acumulados.** Como los extractos van desde el inicio del mes hasta la descarga, un mismo mes se regenera cada día. Si un banco entregara un extracto que no cubre todo el mes, la capa 4 mostraría solo lo entregado. Cómo se **conserva** lo ya confirmado entre corridas (regenerar con la tabla `ESTADOS` vs. actualizar el archivo existente) pertenece al bloque de cierre histórico y **no se diseña aquí**. Esta capa solo garantiza que puede recibir esos estados.
4. **Cuentas con datos faltantes en la muestra.** Sin débitos en BMSC, BISA y Unión, y sin movimientos en UNION_ME, la disposición de sus columnas de débito es **REQUIERE MUESTRA REAL** (UNION_ME: **REQUIERE MUESTRA REAL CON MOVIMIENTOS**).
5. **Volumen.** Un mes de BCP_MN son 2.331 filas de 9 columnas; el mayor caso de la muestra (BNB_MN, 1.184 filas × 11) es cómodo para Excel.

### 6.10 Pruebas nuevas (`test_06_historico.py`)

1. **Reconstrucción sin el banco.** El histórico generado dentro de la corrida es idéntico celda por celda al generado después **solo** con `ORIGEN.xlsx` + `NORMALIZADO` + registro, con los fixtures bancarios ausentes.
2. **Sin pérdida.** Todo valor de una columna bancaria de un movimiento en `DATOS_ORIGINALES` aparece en la hoja, en su columna, salvo el recorte de espacios de relleno.
3. **Débitos íntegros.** Los 620 débitos de BNB_MN, 445 de BCP_MN y 3 de ECO_CTA_CTE conservan todas las columnas del banco. Ejemplo: Referencia `0008125` y Oficina de un «Debito Pago Cheque Efectivo».
4. **Columnas.** Las columnas visibles son exactamente las del formato en el registro, en su orden, más las 3 operativas. No aparece ningún campo técnico (ID, hash, fila, versión).
5. **Números.** Importe, débito, crédito y saldo de la hoja son iguales a `NORMALIZADO`; la suma por archivo es igual a la de `NORMALIZADO`.
6. **Textos que no deben cambiar de tipo:** `0000335`, `034`, `4401` y cuentas se mantienen como texto.
7. **Unidad de salida.** 12 extractos válidos → 11 archivos con nombre esperado; BISA_ME no genera archivo; un extracto que cruza dos meses genera dos.
8. **Zona superior.** Muestra los datos que el archivo trae (por ejemplo Congelado 40,578.52 en Unión MN; Retenciones judiciales 0.00 en Económico) y no muestra los que el archivo no trae (BNB no muestra saldos).
9. **Saldos.** Los saldos informados coinciden con los de `VALIDACION`.
10. **Columna nueva.** Si se agrega una columna a un extracto, aparece antes de las operativas y genera advertencia.
11. **Determinismo y doradas.** Dos corridas dan el mismo archivo; se agrega una dorada de valores por formato.
12. **Compatibilidad Excel Online** (manual, con archivo real): abrir, ordenar, filtrar y editar las 3 columnas operativas sin error.

---

## 7. Impacto sobre las pruebas existentes

| Suite | Impacto | Acción |
|---|---|---|
| `test_01_contrato` (26 columnas, fórmula de clave) | Ninguno | Debe seguir en PASS sin tocarse |
| `test_02_regresion_formatos` (doradas por formato, oráculo, saldos) | Ninguno, si las capas nuevas van en archivo aparte | Debe seguir en PASS; es la prueba de que el registro reproduce el legado |
| `test_03_lote` | Ninguno si se escribe **`ORIGEN.xlsx` aparte**. Si en cambio se agregan hojas a NORMALIZADO.xlsx, cambia solo `test_lote_xlsx_hojas_tabla_y_formatos` (lista exacta de 4 hojas) | **Recomiendo archivo aparte:** NORMALIZADO.xlsx y LISTS.csv quedan idénticos y el flujo hacia Lists no se entera |
| `test_04_defectos` | D-10, D-11 y D-12 pasan a XPASS con el registro; D-09 y D-17 con la captura previa | Quitar la marca `xfail` a medida que pasen |
| UNION_ME | **Reclasificado (ya aplicado en la suite):** «Últimos 12» = fixture negativo. **Estructura = confirmada por código legado + captura real**: las pruebas estructurales afirman el contrato directamente sobre las constantes del motor (`HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `detectar_formato`, cuenta/moneda asignadas por `normalizar_union`, AG opcional) y se activan además con `union_me_vacio.xls` cuando llegue. **Comportamiento con movimientos = pendiente**: movimientos/saldos/débitos/`Nro de verificasion` quedan `SKIP` «REQUIERE MUESTRA REAL CON MOVIMIENTOS». **D-16b:** un UNION_ME vacío hoy lanza KeyError (con proxy sintético; por confirmar con el archivo real) | Al llegar el archivo real: confirmar D-16b y activar las 2 pruebas estructurales sobre archivo real |
| **Capa 4** | Ninguno: es un archivo nuevo derivado. `NORMALIZADO.xlsx` y `LISTS.csv` no se tocan | Solo se agrega `test_06_historico.py` |

**Pruebas nuevas (`test_05_preservacion.py` para las capas 2 y 3, `test_06_historico.py` para la capa 4, ver 6.10), sin cambiar las existentes:**

1. **Completitud celda a celda.** Para cada fixture y **cada hoja**, toda celda no vacía está en `DATOS_ORIGINALES` (cabecera, encabezado, movimientos y pie) con igual hoja, fila, columna y VALOR_ORIGINAL. Esta prueba es el invariante «nunca destruir».
2. **Reconstrucción.** Pivotear `DATOS_ORIGINALES` reproduce la cuadrícula leída del archivo.
3. **MAPA_ORIGEN 1:1.** Cada fila de LISTS tiene exactamente un ID_ORIGEN, y cada ID_ORIGEN con ROL_FILA = MOVIMIENTO tiene una fila en LISTS.
4. **Débitos completos.** BNB_MN (620 débitos), BCP_MN (445) y ECO_CTA_CTE (3) conservan todas sus columnas originales. Ejemplo: Referencia `0008125` y Oficina de un «Debito Pago Cheque Efectivo».
5. **Metadatos esperados por fixture.** Producto, período, saldos y CUENTA_EN_ARCHIVO; también Congelado 40,578.52 en UNION_MN.
6. **Saldos independientes.** El saldo final de la cabecera o el pie coincide con la validación (Unión, BMSC, Económico, BCP, BISA).
7. **Determinismo.** Dos corridas del mismo archivo dan los mismos ID_EXTRACTO e ID_ORIGEN.
8. **Registro:**
   - Agregar una cuenta ficticia por configuración no altera ninguna dorada.
   - Un formato conocido con cuenta no registrada se rechaza.
   - Cada cuenta registrada tiene su fixture.
9. **`Nro de verificasion`.** Confirmada por la captura real y no contemplada por el motor legado. Se conserva en `DATOS_ORIGINALES` con su valor exacto (como texto) y en el `EXTRACTO_HISTORICO` de UNION_ME; **no** entra a las 26 `COLUMNAS_LISTS`. Su contenido real se verifica en cuanto exista muestra con movimientos.
10. **Doradas nuevas.** Una dorada de ORIGEN por formato, generada con el mismo procedimiento que las actuales.

---

## 8. Plan mínimo de implementación (compatible con lo que ya funciona)

**Dependencias de la capa 4:** necesita P1 (captura de todas las celdas) y P3 (registro con el bloque `historico`). No necesita P4–P6.

Cada paso termina con toda la regresión actual en PASS y nada de lo que sale hacia Lists cambia. El orden va de menor a mayor riesgo:

| Paso | Qué | Archivos | Riesgo para lo que funciona |
|---|---|---|---|
| **P1** | Captura pasiva: módulo nuevo `captura_origen.py` que lee todas las hojas y celdas y produce DATOS_ORIGINALES, METADATOS_EXTRACTO/EXTRA y MAPA_ORIGEN. No usa ninguna función de normalización | Nuevo módulo; en el motor, **una llamada al final** de `ejecutar_motor` (después de la validación) y conservar el índice de fila antes de `pd.concat` | Nulo en LISTS; se escribe un archivo extra `ORIGEN.xlsx` |
| **P2** | `test_05_preservacion` + doradas de ORIGEN (incluye cabecera y pie) | `tests/` | Ninguno |
| **P3** | `registro_bancos.json` con los 13 formatos actuales + motor genérico en **modo sombra**: corre en paralelo y compara contra el legado; ante cualquier diferencia, falla la prueba, no la producción | Nuevo `registro_bancos.json`, `motor_generico.py` | Nulo: la salida sigue siendo la del legado |
| **P3b** | **Capa 4, generación**: bloque `historico` de los 13 formatos en el registro, `historico.py` (función pura + escritor) y `test_06_historico.py`. Se alimenta del `NORMALIZADO` **legado**, así que no depende de P4 ni P5 | Nuevo `historico.py`; ampliar `registro_bancos.json`; una llamada al final de `ejecutar_motor` (junto a la de P1) | Nulo en LISTS: escribe archivos nuevos aparte |
| **P4** | Cambiar la **detección** al registro (cuenta en cabecera, cuenta registrada, sin `else`) | `detectar_formato` | Bajo: cierra D-10/11/12; doradas iguales |
| **P5** | Cambiar la **normalización** al motor genérico, solo cuando el modo sombra dio 0 diferencias en N corridas reales | `normalizar_*` pasan a ser configuración | Medio, controlado por las doradas |
| **P6** | Retirar las funciones `normalizar_*` heredadas | motor | Después de P5 estable |

Los defectos D-01 a D-17 siguen su propio carril (Fase 2). D-18 y D-19 **no se tocan** hasta tu decisión, porque cambian un valor de las 26 columnas.

### Decisiones que necesito de ti antes de implementar

| Decisión | Opciones | Recomendación (confianza) |
|---|---|---|
| Dónde van las capas 2 y 3 | (a) `ORIGEN.xlsx` aparte · (b) hojas nuevas en NORMALIZADO.xlsx | (a) (alta): cero impacto en el flujo y en `tblLISTS` |
| ID_ORIGEN en Lists | (a) solo MAPA_ORIGEN por ahora · (b) columna 27 cuando se revise el bloque Lists | (a) ahora (alta) |
| D-18 y D-19 (DEPOSITANTE en BNB) | (a) mantener el valor legado y exponer el dato correcto en DERIVADOS · (b) corregir la columna operativa (cambia valores ya cargados en Lists) | (a) en esta fase (media) |
| Formato del registro | JSON · YAML · diccionario Python | JSON (media): sin dependencias y fácil de revisar |
| **Capa 4: unidad de archivo** | (a) un `.xlsx` por cuenta y mes · (b) un libro por mes con una hoja por cuenta | (a) (media): cada banco tiene columnas distintas y encaja con la carpeta mensual actual |
| **Capa 4: clave de enlace** | (a) columna oculta · (b) sin clave, solo lectura | (b) si es solo de revisión, (a) si se va a actualizar (media) |
| **Capa 4: relación con la plantilla actual** | Coexistir · reemplazar la plantilla `PLANTILLA EXTRACTO.xlsx` | Coexistir hasta probar Excel Online (alta) |
| **Capa 4: formato de fecha** | `dd/mm/aaaa` · `mm/dd/aa` (el de Lists) | `dd/mm/aaaa` para personas (media) |

### Muestras reales que faltan

| Banco / archivo | Falta |
|---|---|
| UNION_ME | (1) El **archivo vacío real** (`union_me_vacio.xls`) para activar las pruebas estructurales sobre archivo real; (2) un extracto **con movimientos**, idealmente con al menos un débito, para golden, cadena de saldo, comportamiento empírico y contenido de `Nro de verificasion` |
| BMSC | Extracto **con débitos**, y hoja `Reporte de Pagos` con al menos una planilla |
| BISA y Unión | Extractos **con débitos** |
| BNB | Extracto con ITF distinto de 0, si existe |
| Todos | Lista válida de **ESTADO** (la define el bloque de confirmación) y el flujo real de la carpeta mensual, para fijar la ruta de la capa 4 |


---

## 12. Estado de implementación: P1 + P2 (hecho)

* **P1** — `captura_origen.py` + una llamada al final de `ejecutar_motor` (paso 15; añade la clave `origen_estado` al diccionario devuelto). Genera `ORIGEN.xlsx` junto a `NORMALIZADO.xlsx`. No toca `COLUMNAS_LISTS`, `CLAVE TRANSACCIÓN`, ningún `normalizar_*` ni Power Automate.
* **Desviaciones respecto de este diseño** (todas hacia menos duplicación): `DATOS_ORIGINALES` no lleva `CLAVE TRANSACCIÓN` ni `LOTE DE CARGA` (el enlace vive solo en `MAPA_ORIGEN`; el lote, en `METADATOS_EXTRACTO`), lo que deja `DATOS_ORIGINALES` sin columnas volátiles. `CAMPO_CANONICO` existe pero va vacío hasta P3 (registro). Los roles `SALDO_INICIAL / SALDO_CIERRE / TOTAL_PIE` se asignan por palabra clave sobre filas **no normalizadas**; el resto son `FILA_ESPECIAL` o `PIE`. `METADATOS_EXTRACTO` incluye `COLUMNAS_ORIGINALES` y `COLUMNAS_SIN_DATOS` (columnas que el formato trae pero vacías en todos los movimientos). `BANCO/CUENTA/MONEDA` de un extracto sin movimientos quedan en blanco hasta P3.
* **Enlace movimiento ↔ fila**: se usa el índice de la tabla normalizada (la lista `tablas` que `ejecutar_motor` aún conserva al final), `FILA_EXCEL = fila_encabezado + 2 + índice`, con verificación interna y con `test_cada_movimiento_apunta_a_su_fila_original` (el IMPORTE y el SALDO normalizados aparecen en la fila apuntada, leída por un lector independiente).
* **P2** — `test_05_preservacion.py` (ver `INFORME_PRUEBAS.md`, sección 2b).
* **Riesgo D-20 (CORREGIDO después del checkpoint)**: si la carpeta de salida es la misma que la de entrada, `ORIGEN.xlsx` sería tomado como extracto en la corrida siguiente (`descubrir_archivos` solo excluye nombres con «NORMALIZADO»). Requiere decisión: excluir `ORIGEN.xlsx` en `descubrir_archivos` o garantizar carpetas distintas.
