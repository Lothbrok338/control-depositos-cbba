# P9 — comprobante mediante Print() (con CUENTA CONTABLE y TIPO DE CAMBIO)

## Estado de esta entrega

**VALIDADO A MANO EN POWER APPS STUDIO / TENANT** (confirmación del usuario, 2026-10-02) con `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml` (SHA-256 `a8eb740c1345d39a615099677b1dbba4faf26072c1f9bdb9a8f23a40effcafcc`). El usuario confirmó:

- `COMPROBANTE PDF` abre correctamente.
- CUENTA CONTABLE funciona para las **13 cuentas del P9**, incluidas Banco Unión MN/ME y BMSC.
- TIPO DE CAMBIO para USD funciona; acepta coma y punto decimal; el EQUIVALENTE EN Bs se calcula correctamente.
- IMPRIMIR se bloquea mientras no haya un tipo de cambio válido.
- Al imprimir, el campo editable no aparece y el tipo de cambio sale como texto.
- `Print()` funciona y el comprobante sigue cabiendo en una página.
- `Main_Screen`, la V4.2 y la confirmación siguen funcionando.

La versión anterior (commit `38a59ccb`, sin cuenta contable ni tipo de cambio) ya se había validado a mano: abría desde P9, mostraba datos reales, imprimía una sola página, VOLVER funcionaba y no afectaba a la V4.2.

**No consta como probado** (no se reportó): los casos de la tabla «Pruebas en tenant» marcados como *No reportado*. Quedan pendientes de comprobación operativa; no son fallos conocidos. Las pruebas del repositorio son estáticas: no ejecutan Power Fx ni el conector SharePoint ni Studio.

### Procedencia

- Repositorio `Lothbrok338/control-depositos-cbba`, rama `candidate/p9-pdf-confirmacion`. Base P9 validada: `7574933`; comprobante inicial: `38a59ccb2a702cfc622d38e1be73af69bcbf253f`.
- **Entrega de pegado vigente:** `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml` (solo controles hijos). `COMPROBANTE_PDF.pa.yaml` es la representación completa (Screens/Properties + exactamente esos controles); un test comprueba que coinciden.
- Se derivó del comprobante de `38a59ccb`, que se conserva sin cambios en `_referencia_comprobante/COMPROBANTE_PDF_38a59cc_SIN_CUENTA_NI_TC.pa.yaml` (SHA-256 `3d4809bf433483e3480f4f9014388ae85395edb65901857ee41b4a749ed3e36f`) para comparar y volver atrás. La pantalla original recibida sigue en `_referencia_comprobante/COMPROBANTE_PDF_ORIGINAL.pa.yaml`.
- Frontend P9 vigente: `P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt` (SHA-256 `3de2d78fe1c789ff5aea0ce76d6b9ea7ae5411d226558022c83990986c06298b`), **sin cambios en esta entrega**. `_base_validada_tenant_2m/` es el mismo frontend sin el botón PDF; `_base_validada_tenant/` es una versión anterior: no usarla para esta integración.
- No se tocó la V4.2, `P9_ASIGNAR_DEPOSITO.Run()`, SharePoint ni `main`.

## Solución

La acción PDF abre una vista del comprobante. El botón IMPRIMIR / GUARDAR PDF ejecuta `Print()`; el usuario elige impresora o Guardar como PDF en el navegador. No se usa `PDF()`, visor experimental, `Download()`, flujo adicional, envío por correo ni almacenamiento de documentos en SharePoint.

La lectura al abrir (sin cambios respecto de `38a59ccb`) sigue esta secuencia:

1. Capturar `ThisItem.ID` en `varP9ComprobanteID`.
2. Limpiar `varP9Comprobante` y bloquear temporalmente los botones PDF.
3. Ejecutar `Refresh(Depositos_Activos)` con su propio manejo de errores.
4. Solo si la actualización tuvo éxito, ejecutar `LookUp(Depositos_Activos, ID = varP9ComprobanteID)`.
5. Rechazar un resultado inexistente o cuyo estado no sea ASIGNADO.
6. Guardar el registro leído en `varP9Comprobante` y navegar a `'COMPROBANTE PDF'`.

No se copia `ThisItem` como fuente del comprobante. En un fallo se limpian el ID y el registro y se avisa; el usuario permanece en P9. La pantalla además comprueba ID y estado en `OnVisible`: sin contexto válido limpia los datos y ejecuta `Back()`. `OnHidden` limpia el comprobante al salir. La vista representa los datos consultados al abrir; no hace consultas periódicas, y `Print()` no vuelve a consultar SharePoint.

## Qué cambió respecto de `38a59ccb`

Solo el comprobante (la pantalla `COMPROBANTE PDF`):

1. **CUENTA CONTABLE automática** (visible), calculada a partir de `varP9Comprobante.CUENTA_BANCARIA`. Ver más abajo.
2. **TIPO DE CAMBIO manual para USD** y **EQUIVALENTE EN Bs** calculado. No se guarda en SharePoint.
3. **Geometría fija.** Todos los X/Y/Width/Height son números; se quitó `AutoHeight` y ningún control se posiciona respecto de otro. Motivo: al pegar el YAML en Studio, un control que referencia por nombre a otro aún no creado no se resuelve (falló en varios intentos). Las únicas referencias entre controles que quedan son las del tipo de cambio.
4. **Protección de página con alturas fijas:** ya no se mide la altura de los textos; IMPRIMIR se deshabilita (y aparece un aviso) si un dato no cabe en su recuadro.
5. **Limpieza del tipo de cambio:** `Reset(txtTipoCambioPDF)` al abrir (`OnVisible`) y al salir (`OnHidden`).

No cambió: el frontend P9 (el botón PDF, la galería, la confirmación), la V4.2, los 14 datos mostrados ni sus formatos, los colores, fuentes y textos validados (un test lo comprueba control por control), `Print()` y `Back()`.

### Controles nuevos respecto de `38a59ccb`

| Nombre | Función |
|---|---|
| `lblTipoCambioTituloPDF` | Título «TIPO DE CAMBIO»; solo si MONEDA = USD |
| `txtTipoCambioPDF` | `TextInput` editable; solo si MONEDA = USD y no se está imprimiendo |
| `lblTipoCambioValorPDF` | Mismo lugar que el `TextInput`; muestra el tipo de cambio como texto solo al imprimir |
| `lblEquivalenteTituloPDF` | Título «EQUIVALENTE EN Bs»; solo si MONEDA = USD |
| `lblEquivalenteValorPDF` | `Bs 3.480,00`, «Ingrese TC» o «TC no válido»; solo si MONEDA = USD |

En total son 49 controles (los 44 de `38a59ccb` más estos 5). Variables: `varP9ComprobanteID`, `varP9Comprobante`, `varP9ComprobanteCargando`; `registroP9` y `tcValor` son nombres locales dentro de `With`.

### Diseño (A4 vertical, 794 × 1123, granate institucional)

Contenedor `cntComprobantePDF`: X=40, Y=66, 714 × 1022. Su borde inferior queda en 1088 (límite 1123 − 24 = 1099). Filas (Y dentro del contenedor):

| Fila | Y título / valor | Alto del valor |
|---|---|---|
| Encabezado, código | 20–192 | — |
| MOVIMIENTO | 216 | — |
| BANCO · CUENTA BANCARIA · MONEDA | 242 / 264 | 50 |
| FECHA/HORA · IMPORTE · ESTADO | 326 / 348 | 76 |
| CUENTA CONTABLE · TIPO DE CAMBIO · EQUIVALENTE EN Bs | 436 / 458 | 36 |
| DESCRIPCIÓN | 506 / 528 | 90 |
| CONFIRMACIÓN | 644 | — |
| ESTUDIANTE · SOLICITADO POR · SEDE | 670 / 692 | 58 |
| CONFIRMADO POR · FECHA/HORA DE CONFIRMACIÓN | 762 / 784 | 46 |
| OBSERVACIÓN | 842 / 864 | 90 |
| Firma / registro de confirmación | 974 / 982 | 2 / 28 |

CUENTA CONTABLE se muestra siempre; la fila no deja hueco para BOB porque las tres columnas comparten una fila. Fuera del contenedor, arriba: VOLVER (izquierda), IMPRIMIR / GUARDAR PDF (derecha) y, entre ambos, el aviso `lblLimiteImpresionPDF`. Nada de eso se imprime.

## CUENTA CONTABLE

El valor depende exclusivamente de `varP9Comprobante.CUENTA_BANCARIA`. Se normaliza quitando guiones, espacios y puntos y se busca con `Switch`; si no está en la tabla muestra **SIN MAPEO**. Una cuenta sin mapear **no bloquea** la impresión.

| Banco en P9 | Cuenta en P9 | Cuenta contable | Origen |
|---|---|---|---|
| BNB MN | 3000100152 | 110103012 | Tabla del usuario |
| BNB ME | 3400041236 | 110104012 | Tabla del usuario |
| BNB AHORRO | 3501936692 | 110103712 | Tabla del usuario |
| BNB CLÍNICA | 3000100705 | 110103022 | Tabla del usuario |
| BCP MN | 301-5005684-3-97 | 110103042 | Tabla del usuario (`3015005684397`, sin guiones) |
| BCP ME | 301-5005425-2-71 | 110104032 | Tabla del usuario (`3015005425271`, sin guiones) |
| BISA MN | 0696870039 | 110103032 | Tabla del usuario, que la trae sin el 0 inicial |
| BISA ME | 0696872023 | 110104022 | Tabla del usuario, que la trae sin el 0 inicial |
| BANCO UNIÓN MN | 10000003224552 | 110103052 | **Confirmado por el usuario** |
| BANCO UNIÓN ME | 20000003224544 | 110104042 | **Confirmado por el usuario** |
| BANCO ECONÓMICO CTA. CTE. | 3041210569 | 110103062 | Tabla del usuario (BANECO MN) |
| BANCO ECONÓMICO AHORRO | 3051446946 | 110103722 | Tabla del usuario (BANECO AH) |
| BMSC CTA. CTE. | 1000872489 | 110103072 | **Confirmado por el usuario** |

Notas del mapeo:

- **Banco Unión** no figura con ese nombre en la tabla del usuario; el usuario confirmó que sus cuentas corresponden a las contables 110103052 (MN) y 110104042 (ME), las mismas que la tabla asigna a BUSA (`13224552` y `23224544`).
- **BMSC cambió de número de cuenta bancaria** pero sigue asociada a la misma cuenta contable 110103072; el número anterior de la tabla (`4010879042`) se conserva en el mapeo.
- **Única equivalencia añadida** a la normalización de guiones, espacios y puntos: el cero inicial de BISA. La tabla trae `696870039`, `696872023` y `0696876517`; P9 usa `0696870039` y `0696872023`. Se aceptan ambas escrituras para las tres cuentas.
- Otras entradas del `Switch` que hoy no corresponden a una cuenta de P9: `13224552` y `23224544` (BUSA), `4010879042` (BMS MN) y `0696876517` (BISA EURO AH).
- Hasta la confirmación del usuario, Banco Unión y BMSC no podían relacionarse de forma inequívoca con la tabla suministrada (se habrían mostrado como SIN MAPEO); las tres entradas se añadieron tras esa confirmación. Coinciden con el mapeo de la pantalla original recibida (`_referencia_comprobante/COMPROBANTE_PDF_ORIGINAL.pa.yaml`).

**Mantenimiento:** si se agrega una cuenta a `cmbCuentaP9` en P9, hay que agregar su par al `Switch` de `lblCuentaContableValorPDF.Text` en `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`, `COMPROBANTE_PDF.pa.yaml` y `FORMULAS_EXACTAS.md`, y actualizar `test_26` (la prueba de las cuentas del P9 fallará hasta entonces).

## TIPO DE CAMBIO y EQUIVALENTE EN Bs

- Solo si `varP9Comprobante.MONEDA = "USD"`: aparecen TIPO DE CAMBIO (campo editable `txtTipoCambioPDF`) y EQUIVALENTE EN Bs. Con otra moneda se oculta toda la sección y no se exige tipo de cambio.
- Entrada válida: `^[0-9]+$` o `^[0-9]+[.,][0-9]+$`, es decir, entero o decimal con **coma o punto** (`6,96`, `6.96`), y mayor que 0. Se ignoran espacios en los extremos. No se aceptan separadores de miles (`6.960,00`), signos, notación científica ni texto.
- Equivalente: `varP9Comprobante.IMPORTE * TC`, formato es-ES. Ejemplo: USD 500,00 con TC 6,96 → `Bs 3.480,00`. Sin TC muestra «Ingrese TC»; con TC no válido, «TC no válido».
- **IMPRIMIR** queda deshabilitado en USD mientras el TC sea vacío, no numérico o ≤ 0.
- **Al imprimir** (`'COMPROBANTE PDF'.Printing`): se oculta el `TextInput` y en su lugar se muestra `lblTipoCambioValorPDF` con el TC como texto (`6,96`), de modo que el PDF no parezca un formulario editable.
- El tipo de cambio **no se guarda** en SharePoint ni se envía a ningún flujo. Se reinicia al abrir y al salir.

## Impresión y protección de una sola página

Con alturas fijas el riesgo ya no es pasar de página sino que un dato se recorte en su recuadro. `btnImprimirPDF.DisplayMode` se deshabilita, y `lblLimiteImpresionPDF` aparece con el aviso «El contenido supera el espacio de una página A4…», cuando:

| Dato | Límite |
|---|---|
| CODIGO_ASIGNACION | 26 caracteres |
| BANCO / CUENTA_BANCARIA | 28 caracteres |
| HORA_MOVIMIENTO | 35 caracteres |
| ESTUDIANTE / SOLICITADO_POR | 51 caracteres |
| SEDE_ASIGNACION | 48 caracteres |
| USUARIO_ASIGNACION | 50 caracteres |
| DESCRIPCION | 5 líneas (62 caracteres por línea, más un salto por cada Enter) |
| OBSERVACION | 5 líneas (64 caracteres por línea, más un salto por cada Enter) |

Son estimaciones conservadoras del ancho de texto de cada recuadro, no una medición de Studio. Los datos reales de ejemplo del repositorio caben con margen y el usuario confirmó una sola página con datos reales. Un texto con muchas letras anchas podría pasar el límite estimado sin que se deshabilite el botón; si se detecta, se ajusta el límite correspondiente (sin cambiar la geometría).

## Pegar en Studio (procedimiento usado en la validación)

Trabajar en una copia de la app, con los mismos orígenes de datos y el mismo flujo V4.2. No volver a importar el flujo. No publicar sobre la app productiva antes de validar.

1. En la pantalla `COMPROBANTE PDF` (Width = 794, Height = 1123, Fill blanco, `LoadingSpinnerColor` granate) **borrar todos los controles**. Si queda alguno con el mismo nombre, Studio crea uno con sufijo `_1` y las fórmulas dejan de resolverse.
2. Seleccionar la pantalla → clic derecho → **Pegar** y pegar el contenido completo de `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`. Contiene solo los controles hijos, ya en orden de resolución: `txtTipoCambioPDF` va antes de cualquier control que lo lee, y `cntComprobantePDF` antes de los controles externos.
3. **Después** del YAML, escribir a mano en la barra de fórmulas de la pantalla `OnVisible` y `OnHidden` (usan `txtTipoCambioPDF`). Usar la variante regional de `FORMULAS_EXACTAS.md` si el Studio usa `;` como separador de argumentos. Los controles pegados no asignan propiedades a la pantalla.
4. Verificar en el árbol que `cntComprobantePDF`, `btnVolverPDF`, `btnImprimirPDF` y `lblLimiteImpresionPDF` sean hijos directos de la pantalla y que los demás estén dentro de `cntComprobantePDF`. Conservar exactamente `btnImprimirPDF.OnSelect = Print()` y `btnVolverPDF.OnSelect = Back()`.
5. Ejecutar el comprobador de aplicaciones y probar **desde P9 en reproducción**; abrir la pantalla directamente en el editor no sirve porque el acceso sin ID válido está bloqueado a propósito.

El botón PDF y los cambios de `btnAsignarP9` (Height/Y) ya están en el frontend versionado. Solo si se parte de la base sin botón (`_base_validada_tenant_2m/`), pegar sobre la plantilla de `galDepositosP9` el bloque `BOTON_COMPROBANTE_P9_PEGAR.yaml` y poner en `btnAsignarP9` las fórmulas de `Height` y `Y` de `FORMULAS_EXACTAS.md`, sin tocar `OnSelect`. Para generar ese bloque, desde la raíz del repositorio (requiere Python y PyYAML; escribe solo en la carpeta hermana `p9-comprobante-exportado`):

```python
python - <<'EOF'
from pathlib import Path
import yaml

front = Path("p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt")
dest = Path("../p9-comprobante-exportado")
dest.mkdir(exist_ok=True)


def nodes(items):
    for item in items:
        name, control = next(iter(item.items()))
        yield name, control
        yield from nodes(control.get("Children", []))


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


Dumper.add_representer(str, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", v, style="|" if "\n" in v else None))
controls = dict(nodes(yaml.safe_load(front.read_text(encoding="utf-8"))))
bloque = [{"btnAbrirComprobanteP9": controls["btnAbrirComprobanteP9"]}]
(dest / "BOTON_COMPROBANTE_P9_PEGAR.yaml").write_text(yaml.dump(bloque, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=2000), encoding="utf-8", newline="\n")
EOF
```

No habilitar características experimentales. Los YAML usan comas para los argumentos y `;` para encadenar acciones (formato de la base validada); `FORMULAS_EXACTAS.md` incluye también la variante regional de cada fórmula.

## Pruebas en tenant

Usar registros de prueba cuando sea necesario cambiar o eliminar un elemento; no borrar depósitos reales.

| Caso | Resultado esperado | Estado |
|---|---|---|
| Abrir PDF de un ASIGNADO desde P9 | Abre y muestra datos reales (los 14 datos del ID releído de SharePoint) | Confirmado a nivel general (`38a59ccb` y versión actual); la comparación campo por campo no se reportó |
| VOLVER | Retorna a P9 | Confirmado (`38a59ccb`) |
| `Print()` en una sola página | Imprime el comprobante en una página; la galería, los botones y el aviso no deben salir | Una sola página: confirmado. Que no salgan galería ni botones: no reportado de forma explícita |
| CUENTA CONTABLE | Correcta para las 13 cuentas del P9 | Confirmado |
| USD: tipo de cambio con coma y con punto | Se acepta; el equivalente en Bs es correcto | Confirmado |
| USD sin TC válido | IMPRIMIR deshabilitado | Confirmado |
| Impresión en USD | Sin `TextInput`; el TC aparece como texto | Confirmado |
| `Main_Screen`, V4.2 y confirmación | Sin cambios de comportamiento | Confirmado |
| DISPONIBLE | No aparece PDF; CONFIRMAR conserva posición y comportamiento | No reportado de forma explícita |
| MONEDA ≠ USD | Sin sección de TC; no se exige TC | No reportado de forma explícita |
| Dos confirmados diferentes | Abrir A, volver y abrir B muestra exclusivamente B; el TC de A no pasa a B | No reportado |
| OBSERVACION vacía o espacios | «Sin observación» | No reportado |
| Datos largos y saltos de línea | Sin solapes; si exceden el límite, aviso y IMPRIMIR deshabilitado | No reportado |
| Registro eliminado o ya no ASIGNADO antes de abrir | Advertencia; permanece en P9 | No reportado |
| Corte de red antes de abrir | Advertencia, sin navegar; se puede reintentar | No reportado |
| Pantalla abierta sin ID válido | Comprobante oculto, advertencia y vuelta atrás | No reportado |
| Vuelta con filtros, selección y scroll | Filtros, `varDepositoSeleccionado` y VER permanecen | No reportado |
| Fecha/hora de confirmación | Coincide con el instante guardado, en la zona local de la app | No reportado |
| Cuenta no mapeada | Muestra SIN MAPEO y no bloquea la impresión | No reportado (no hay cuenta sin mapear en P9) |

### Imprimir y guardar como PDF

1. Abrir un confirmado desde P9 y revisar los datos. En USD, escribir el tipo de cambio.
2. Pulsar IMPRIMIR / GUARDAR PDF.
3. En Edge o Chrome de escritorio, seleccionar A4 y orientación vertical. Revisar escala ajustada a página, márgenes y vista previa.
4. Desactivar encabezados y pies del navegador; activar gráficos de fondo para conservar el granate y los separadores.
5. Comprobar que haya una página y que aparezcan completos descripción, observación, código, importe, cuenta contable, tipo de cambio, equivalente, usuario y fecha/hora. La galería, los botones y el aviso no deben aparecer.
6. Elegir Guardar como PDF, poner un nombre como `Comprobante_<ID>.pdf`, guardar y abrir el archivo. Para papel, elegir la impresora.
7. Repetir la vista previa en carta si ese es el papel de destino, ajustando a una página. El diseño base es A4.

## Pruebas locales

```
python -m pytest tests/test_22_frontend_final_p9.py tests/test_24_flujo_v4_2_firma_8_posicionales_p9.py tests/test_25_comprobante_impresion_p9.py tests/test_26_comprobante_cuenta_tc_p9.py -q
```

- `test_22` y `test_24`: frontend P9 (SHA fijado) y firma V4.2 de 8 posicionales; sin cambios en esta entrega.
- `test_25`: lo que no cambió del comprobante: P9 solo agrega el botón y reubica VER, la fórmula de confirmación idéntica, botón PDF solo para ASIGNADO, lectura con `Refresh` y `LookUp` separados, limpieza al salir (ahora también el tipo de cambio), campos y tipos de SharePoint, sin escrituras, formatos, `Print()`/`Back()`.
- `test_26` (nuevo): el YAML de pegado es solo de controles hijos con huella fijada y coincide con `COMPROBANTE_PDF.pa.yaml`; nombres únicos y sin `_1`; **ningún control referencia a otro inexistente o definido después**, y las únicas referencias entre controles son las tres al tipo de cambio; geometría numérica, todo dentro de una página A4 y sin solapes; mapeo contable exacto y las 13 cuentas del P9; reglas del tipo de cambio (válidos e inválidos, ejemplo USD 500 × 6,96); visibilidad por moneda y al imprimir; protección de página compartida por el botón y el aviso; sin `Patch`, `PDF()`, `Download`, `.Run()`, `User()`, `Now()`; el estilo del comprobante validado no cambió; y `FORMULAS_EXACTAS.md` coincide con los YAML, incluidas las variantes regionales.

Estas pruebas **no** son un compilador Power Fx, no ejecutan el conector SharePoint real y no comprueban el renderizado de Studio ni la impresión.

## Riesgos y límites

- `Print()` funciona en el navegador de escritorio; Microsoft no lo admite en dispositivos móviles ni en formularios integrados de SharePoint.
- `Print()` imprime una pantalla en una página. No hay generación multipágina. Si un dato supera su recuadro, se bloquea la impresión y se avisa; no se recorta en silencio.
- Los límites de caracteres son estimaciones (ver arriba), no mediciones.
- Márgenes, escala, colores y nombre del archivo dependen del diálogo del navegador. No se descarga un archivo automáticamente.
- El registro se revalida al abrir. Los cambios externos posteriores no se reflejan hasta volver a abrirlo.
- La tabla contable vive en una fórmula de Power Apps: una cuenta nueva exige editarla (ver Mantenimiento).
- El tipo de cambio lo escribe el usuario cada vez; no se valida contra ninguna cotización ni se guarda.
- Validar el mapeo de fecha/hora en tenant si el usuario y SharePoint tienen zonas horarias distintas (la hora se muestra como la entrega el conector).
- La selección de la galería no se cambia mediante fórmulas nuevas, pero `Refresh` puede actualizar el conjunto mostrado; comprobarlo en la app real.
- `VerticalAlign` en etiquetas e `IsMatch` se usan por primera vez en este proyecto; funcionaron en la validación del usuario.

Fuentes: [Print()](https://learn.microsoft.com/en-us/power-platform/power-fx/reference/function-print), [copiar y pegar código de controles](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/code-view).
