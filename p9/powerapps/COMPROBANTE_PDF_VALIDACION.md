# P9 — comprobante mediante Print()

## Estado de esta entrega

Implementación candidata pendiente de validación en Power Apps Studio y tenant. No se ha importado ni publicado la app. Guardar esta versión en Git no constituye validación funcional ni autorización de despliegue. No se ha hecho merge ni rebase.

- Repositorio: `Lothbrok338/control-depositos-cbba`.
- Rama base consultada mediante fetch: `candidate/p9-powerapps-asignacion`.
- Commit base validado: `7574933370c1f87854b9f774a073c063e3ce3046`.
- Rama local de trabajo: `candidate/p9-pdf-confirmacion`, creada desde ese commit con árbol limpio.
- Frontend vigente: `P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt`, identificado por el mensaje del commit validado. Coincide byte por byte con el archivo final descargado antes de esta modificación.
- SHA256 original: `eb68f73700d259bfb4db43d787e4a2ff050ee8c08754b7b5138468f003e050c8`.
- Se conserva ese frontend en `_base_validada_tenant_2m/` para comparar y volver atrás.
- La pantalla recibida se conserva en `_referencia_comprobante/COMPROBANTE_PDF_ORIGINAL.pa.yaml`.

`_base_validada_tenant/` contiene una versión anterior: no usarla para esta integración. No se tocó main; el checkout se obtuvo directamente de la rama candidata y no contiene una rama local main.

## Solución

La acción PDF abre una vista del comprobante. El botón IMPRIMIR / GUARDAR PDF ejecuta `Print()`; el usuario elige impresora o Guardar como PDF en el navegador. No se usa PDF(), visor experimental, Download(), flujo adicional, envío por correo ni almacenamiento de documentos en SharePoint.

La lectura al abrir sigue esta secuencia:

1. Capturar `ThisItem.ID` en `varP9ComprobanteID`.
2. Limpiar `varP9Comprobante` y bloquear temporalmente los botones PDF.
3. Ejecutar `Refresh(Depositos_Activos)` con su propio manejo de errores.
4. Solo si la actualización tuvo éxito, ejecutar `LookUp(Depositos_Activos, ID = varP9ComprobanteID)`.
5. Rechazar un resultado inexistente o cuyo estado no sea ASIGNADO.
6. Guardar el registro leído en `varP9Comprobante` y navegar a `'COMPROBANTE PDF'`.

No se copia ThisItem como fuente del comprobante. La actualización y la lectura tienen ramas de error separadas para no continuar con una lectura de caché después de un fallo de Refresh.

En un fallo se limpian el ID y el registro y se avisa. Como aún no se navegó, el usuario permanece en P9. La pantalla del comprobante además comprueba ID y estado en OnVisible; si se abre sin contexto válido, limpia los datos y ejecuta Back(). OnHidden limpia el comprobante al salir.

La vista representa los datos consultados al abrir. No hace consultas periódicas mientras permanece abierta. Si un administrador cambia o elimina el registro después de abrirla, debe cerrarse y abrirse de nuevo para releerlo; Print() no vuelve a consultar SharePoint. Esta iteración no modifica la concurrencia ni la confirmación.

## Alcance exacto

En P9 se agrega `btnAbrirComprobanteP9` dentro de `galDepositosP9`. Para ASIGNADO, el botón existente VER pasa a Y=6 y Height=28, y PDF ocupa Y=40 y Height=28. Ambos caben dentro de la fila actual de 76 px. Para DISPONIBLE, el botón CONFIRMAR conserva Y=22 y Height=32.

No cambia ninguna otra propiedad de los controles existentes de P9. La fórmula de confirmación completa, la llamada V4.2 de ocho argumentos, los filtros, la ventana de dos meses, Banco → Cuenta, la búsqueda por descripción y el modal se conservan. El botón PDF no hace Select(Parent), Reset ni asignaciones a varDepositoSeleccionado. El Refresh solicitado sí puede actualizar los resultados recibidos de SharePoint; comprobar selección y desplazamiento en tenant.

La pantalla del comprobante conserva los nombres y tipos de los 36 controles del adjunto. Se mantienen colores, distribución manual y estilo. Se ocultan los dos controles de cuenta contable y se elimina su cálculo fijo. Los campos de texto crecen verticalmente y las filas siguientes se posicionan en función de su altura.

### Controles nuevos respecto de ambas fuentes

| Nombre | Ubicación |
|---|---|
| btnAbrirComprobanteP9 | Plantilla de galDepositosP9 |
| lblAreaPDF | cntComprobantePDF: CONTROL DE INGRESOS |
| lblMovimientoPDF | cntComprobantePDF: encabezado MOVIMIENTO |
| lblConfirmacionPDF | cntComprobantePDF: encabezado CONFIRMACIÓN |
| lblMonedaTituloPDF | cntComprobantePDF: título MONEDA |
| lblMonedaValorPDF | cntComprobantePDF: valor MONEDA |
| lblDescripcionTituloPDF | cntComprobantePDF: título DESCRIPCIÓN |
| lblDescripcionValorPDF | cntComprobantePDF: descripción completa |
| lblLimiteImpresionPDF | Pantalla, fuera del contenedor: aviso de exceso de una página |

Variables nuevas: `varP9ComprobanteID`, `varP9Comprobante`, `varP9ComprobanteCargando`. `registroP9` es un nombre local dentro de With. No requieren fórmulas nuevas en App.OnStart.

### Campos y presentación

BANCO, CUENTA_BANCARIA, MONEDA, HORA_MOVIMIENTO, CODIGO_ASIGNACION, DESCRIPCION, ESTUDIANTE, SOLICITADO_POR, SEDE_ASIGNACION, OBSERVACION y USUARIO_ASIGNACION son texto. No se les añade .Value ni .DisplayName. ESTADO_ASIGNACION sí es una opción y usa .Value.

- IMPORTE: número con dos decimales, separadores es-ES y moneda persistida. Un importe cero se muestra como cero; un valor vacío se muestra como raya.
- FECHA_MOVIMIENTO: dd/mm/yyyy; HORA_MOVIMIENTO conserva el texto del banco.
- FECHA_HORA_ASIGNACION: dd/mm/yyyy hh:mm:ss, desde el valor DateTime del conector. No se añade un desplazamiento UTC manual. Verificar contra la configuración regional de SharePoint y del usuario para evitar una conversión doble.
- OBSERVACION: vacía o compuesta de espacios → Sin observación. El texto no vacío se conserva.
- Usuario y fecha/hora nunca se sustituyen por User().Email o Now(). Esas funciones no aparecen en el nuevo comprobante.

## Pegar en Studio

Trabajar en una copia de validación de la app, con los mismos orígenes de datos y el mismo flujo V4.2. No volver a importar el flujo. No publicar sobre la app productiva antes de validar.

### Fuentes versionadas y bloques de pegado

Las fuentes completas son `p9/powerapps/P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt` y `p9/powerapps/COMPROBANTE_PDF.pa.yaml`. Las copias y fragmentos de la entrega en outputs no se duplican en el commit. Las dos referencias originales conservadas en subdirectorios son entradas de los tests de preservación y trazabilidad.

Para obtener los archivos de pegado mencionados abajo desde un checkout de esta rama, ejecutar este bloque en PowerShell desde la raíz del repositorio. Requiere Python y PyYAML, usado también por los tests. Escribe únicamente en la carpeta hermana `p9-comprobante-exportado`; no modifica las fuentes:

```powershell
@'
from pathlib import Path
import yaml

src = Path("p9/powerapps")
dest = Path("../p9-comprobante-exportado")
dest.mkdir(exist_ok=True)
front = src / "P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt"
receipt = src / "COMPROBANTE_PDF.pa.yaml"
screen = yaml.safe_load(receipt.read_text(encoding="utf-8"))["Screens"]["COMPROBANTE PDF"]

def nodes(items):
    for item in items:
        name, control = next(iter(item.items()))
        yield name, control
        yield from nodes(control.get("Children", []))

class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

def represent_string(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)

Dumper.add_representer(str, represent_string)
controls = dict(nodes(yaml.safe_load(front.read_text(encoding="utf-8"))))
blocks = {
    "COMPROBANTE_PDF_CONTROLES_PEGAR.yaml": screen["Children"],
    "BOTON_COMPROBANTE_P9_PEGAR.yaml": [{"btnAbrirComprobanteP9": controls["btnAbrirComprobanteP9"]}],
}
for name, content in blocks.items():
    (dest / name).write_text(yaml.dump(content, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=2000), encoding="utf-8", newline="\n")
for original, name in [(front, "P9_CONTROL_INGRESOS_CON_COMPROBANTE.yaml"), (receipt, "COMPROBANTE_PDF.pa.yaml"), (src / "FORMULAS_EXACTAS.md", "FORMULAS_EXACTAS.md")]:
    (dest / name).write_bytes(original.read_bytes())
'@ | python -
```

### 1. Pantalla del comprobante

1. Si ya existe `'COMPROBANTE PDF'`, conservarla y aplicar las diferencias de propiedades y los controles nuevos indicados en los archivos de entrega. No pegar duplicados de los controles existentes.
2. Si aún no está incorporada, crear una pantalla y nombrarla exactamente `COMPROBANTE PDF`. Aplicar Fill=RGBA(255,255,255,1), Width=794, Height=1123 y LoadingSpinnerColor=RGBA(123,22,50,1).
3. Para incorporar la pantalla adjunta con los cambios, seleccionar la pantalla y pegar el archivo `COMPROBANTE_PDF_CONTROLES_PEGAR.yaml` mediante Pegar código. Contiene sus controles completos derivados del adjunto. El archivo `COMPROBANTE_PDF.pa.yaml` es la representación completa con Screens/Properties; no pegar ese encabezado en un destino que acepte únicamente controles.
4. Aplicar OnVisible y OnHidden desde `FORMULAS_EXACTAS.md`. Los controles pegados por sí solos no asignan propiedades a la pantalla.
5. Verificar que cntComprobantePDF y los dos botones estén como hijos directos de la pantalla, y que los campos estén dentro de cntComprobantePDF. El aviso de tamaño también queda fuera.
6. Conservar exactamente `btnImprimirPDF.OnSelect = Print()` y `btnVolverPDF.OnSelect = Back()`.

### 2. Integración mínima en P9

1. Seleccionar la plantilla de `galDepositosP9` y pegar `BOTON_COMPROBANTE_P9_PEGAR.yaml`. Verificar en el árbol que btnAbrirComprobanteP9 sea hijo de esa galería.
2. En `btnAsignarP9`, cambiar únicamente Height y Y con las fórmulas de `FORMULAS_EXACTAS.md`. No cambiar OnSelect.
3. Confirmar que no se hayan creado nombres con sufijos, como btnAbrirComprobanteP9_1.
4. El archivo `P9_CONTROL_INGRESOS_CON_COMPROBANTE.yaml` contiene el frontend completo actualizado para revisión o importación integral controlada. No hace falta reemplazar la pantalla existente para aplicar estos tres cambios.

### 3. Fórmulas y validación inicial

- Los YAML utilizan el mismo formato de fórmulas que la base validada: comas para argumentos y punto y coma para encadenar acciones.
- `FORMULAS_EXACTAS.md` incluye las versiones canónicas y las versiones con separadores regionales para pegado manual. Usar una sola variante según la barra de fórmulas de Studio. No modificar las comas dentro de cadenas de formato monetario.
- No habilitar características experimentales. La gestión de errores con IfError ya se usa en el frontend validado.
- Ejecutar App checker. Verificar que no haya errores de nombres, tipos, referencias o navegación.
- Probar desde P9 en reproducción, no abriendo directamente la pantalla del comprobante en el editor: el acceso sin ID está bloqueado deliberadamente.

## Pruebas en tenant

Usar registros de prueba cuando sea necesario cambiar o eliminar un elemento; no borrar depósitos reales para probar.

| Caso | Resultado esperado |
|---|---|
| DISPONIBLE | No aparece PDF; CONFIRMAR conserva posición y comportamiento. |
| ASIGNADO | Se muestran VER y PDF; VER abre el mismo modal anterior. |
| PDF de ASIGNADO | Los catorce datos corresponden al ID releído de SharePoint. |
| Dos confirmados diferentes | Abrir A, volver y abrir B muestra exclusivamente B. |
| OBSERVACION vacía o espacios | Sin observación. |
| Importe cero, grande, MN y ME | Formato legible con dos decimales y moneda real. |
| Datos largos y saltos de línea | Se distribuyen sin solaparse; si exceden A4, aviso y botón de impresión deshabilitado. |
| Registro de prueba eliminado o ya no ASIGNADO antes de abrir | Advertencia; permanece en P9; no aparece el comprobante anterior. |
| Corte de red antes de abrir | Advertencia, sin navegación ni comprobante anterior; al recuperar conexión puede reintentarse. |
| Pantalla abierta sin ID válido | Comprobante oculto, advertencia y vuelta atrás cuando hay historial. |
| VOLVER | Retorna a P9; filtros, varDepositoSeleccionado y funcionamiento de VER permanecen. Comprobar también selección y scroll. |
| Fecha/hora | Coincide con el instante guardado en SharePoint, presentado en la zona local que ya usa la app. |
| Confirmación V4.2 | Ensayo con un depósito de prueba: mismos ocho argumentos y cuarto argumento vacío; usuario/fecha persistidos. |

### Imprimir y guardar como PDF

1. Abrir un confirmado desde P9 y revisar los datos en la pantalla dedicada.
2. Pulsar IMPRIMIR / GUARDAR PDF.
3. En Edge o Chrome de escritorio, seleccionar A4 y orientación vertical. Revisar escala ajustada a página, márgenes y vista previa.
4. Desactivar encabezados y pies del navegador; activar gráficos de fondo para conservar el granate y los separadores.
5. Comprobar que haya una página y que aparezcan completos descripción, observación, código, importe, usuario y fecha/hora. La galería y los botones no deben aparecer.
6. Elegir Guardar como PDF, poner un nombre como `Comprobante_<ID>.pdf`, guardar y abrir el archivo. Para papel, elegir la impresora.
7. Repetir la vista previa en carta si ese es el papel de destino, ajustando a una página. El diseño base es A4.

## Tests locales

Se ejecutaron primero 54 pruebas existentes sobre la base limpia, todas correctas. Después de la integración pasaron 69 pruebas: las 54 anteriores y 15 nuevas.

```powershell
python -m pytest tests/test_22_frontend_final_p9.py tests/test_24_flujo_v4_2_firma_8_posicionales_p9.py tests/test_25_comprobante_impresion_p9.py -q
```

Las nuevas pruebas verifican procedencia, igualdad de todos los controles previos salvo Height/Y de VER, fórmula completa de confirmación intacta, datos persistidos, campos/tipos, manejo separado de errores, limpieza, visibilidad, Print/Back, tamaño A4, protección ante desbordamiento y referencias a controles. Los tests existentes siguen verificando firma V4.2 y concurrencia simulada. Solo se actualizaron sus dos huellas esperadas del frontend, conservando todas las aserciones.

Estas pruebas no son un compilador Power Fx, no ejecutan el conector SharePoint real y no comprueban el renderizado de Studio. La validación de tenant sigue pendiente.

## Riesgos y límites

- Print() funciona en el navegador de escritorio; Microsoft no lo admite en dispositivos móviles ni formularios integrados de SharePoint.
- Print() imprime una pantalla en una página. Si el texto excede el A4, se bloquea la impresión y se avisa; no se recorta ni se reduce silenciosamente a un tamaño ilegible. No hay generación multipágina en esta entrega.
- Márgenes, escala, colores y nombre del archivo dependen del diálogo del navegador. No se descarga un archivo automáticamente.
- El registro se revalida al abrir. Los cambios externos posteriores no se reflejan hasta volver a abrirlo.
- Hay que validar el mapeo de fecha/hora en tenant, especialmente si el usuario y SharePoint tienen zonas horarias distintas.
- La selección de la galería no se cambia mediante fórmulas nuevas, pero Refresh puede actualizar el conjunto mostrado; comprobarlo en la app real.

Fuentes: [Print()](https://learn.microsoft.com/en-us/power-platform/power-fx/reference/function-print), [copiar y pegar código de controles](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/code-view).
