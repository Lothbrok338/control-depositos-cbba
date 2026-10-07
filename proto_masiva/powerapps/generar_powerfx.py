"""Genera PREVALIDACION_POWERFX.md: las fórmulas de la prevalidación real, LEÍDAS del YAML (única fuente) y mostradas en la sintaxis
de la configuración regional de Gabriel (`;` entre argumentos y `;;` entre sentencias).

    python proto_masiva/powerapps/generar_powerfx.py
"""
from pathlib import Path

import yaml

CARPETA = Path(__file__).resolve().parent


def regional(formula: str) -> str:
    """Sintaxis canónica (comas) -> configuración regional con `;` (argumentos) y `;;` (sentencias). Respeta los textos entre comillas."""
    salida, en_texto, i = [], False, 0
    while i < len(formula):
        c = formula[i]
        if c == '"':
            if en_texto and formula[i + 1:i + 2] == '"':  # comilla escapada dentro de un texto
                salida.append('""')
                i += 2
                continue
            en_texto = not en_texto
        elif not en_texto and c == ";":
            salida.append(";;")
            i += 1
            continue
        elif not en_texto and c == ",":
            salida.append(";")
            i += 1
            continue
        salida.append(c)
        i += 1
    return "".join(salida)


def controles():
    doc = yaml.safe_load((CARPETA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))
    raiz = doc["Screens"]["P9_Confirmacion_Masiva"]["Children"]
    salida = {}

    def recorrer(hijos):
        for h in hijos:
            (nombre, c), = h.items()
            salida[nombre] = c
            recorrer(c.get("Children", []))
    recorrer(raiz)
    return salida


def formula(nombre, propiedad):
    return controles()[nombre]["Properties"][propiedad].lstrip("=")


CAMBIOS = (("btnPrevalidarP9", "OnSelect", "1 · `btnPrevalidarP9` → propiedad **OnSelect** (reemplaza TODO el contenido)"),
           ("lblEstadoP9", "Fill", "2 · `lblEstadoP9` → **Fill**"),
           ("lblTitularResultadoP9", "Text", "3 · `lblTitularResultadoP9` → **Text**"),
           ("lblResFilasP9", "Text", "4 · `lblResFilasP9` → **Text**"),
           ("lblAvisoPrototipoP9", "Text", "5 · `lblAvisoPrototipoP9` → **Text**"))


def documento() -> str:
    partes = ['''# Power Fx de la prevalidación real (colección `colPrevalidacionP9`)

> **Estado: la prevalidación con esta colección ya fue validada en el tenant** (fase anterior). Las fórmulas que se muestran son las **vigentes**, que
> incluyen los reinicios de la fase de confirmación: lo que cambia en esta fase, con los pasos exactos, está en **`CONFIRMACION_POWERFX.md`**.
> Este archivo se **genera** desde `P9_Confirmacion_Masiva.pa.yaml` (`python proto_masiva/powerapps/generar_powerfx.py`): no lo edites a mano.

Las fórmulas están escritas para tu configuración regional: `;` entre argumentos y `;;` entre sentencias.

## Qué hace

1. `P9_MASIVA_PROTO_PREVALIDAR.Run(...)` devuelve ahora **13 salidas, todas texto**. Power Automate **no puede devolver un arreglo estructurado** a Power Apps
   (solo valores simples), por eso `detalle_json` llega como **texto JSON**.
2. `ParseJSON(varResultadoP9.detalle_json)` lo convierte en un valor **sin tipo**. **No se asume ningún tipo:** cada columna se convierte de forma explícita con
   `Text(...)` o `Value(...)`.
3. `ClearCollect(colPrevalidacionP9; ...)` deja una colección con **una fila por fila del Excel** y **las 20 columnas** de `detalle_json`
   (`fila_excel`, `resultado`, `mensaje`, `deposito_id`, `estado_actual`, …). Ver `flows/esquema_detalle_json.json`.
4. Si el detalle no se puede leer, se muestra un aviso (`Notify`) y **no** se confunde con «el flujo no respondió».

`ThisRecord.Value.<campo>` es la forma documentada de leer un elemento de `Table(ParseJSON(...))`. Si Studio marca error en `ThisRecord.Value`, prueba
`ThisRecord.<campo>` solo en esa línea y avísame qué firma aceptó.
`deposito_id` e `importe` pueden venir `null` en el JSON: `Value(...)` los deja en blanco, no en 0.

## Los 5 cambios en la pantalla `P9_Confirmacion_Masiva` (de `P9_PRUEBA_MASIVA`)

Selecciona cada control, elige la propiedad en la barra de fórmulas, **borra todo el contenido** y pega el bloque.
''']
    for nombre, propiedad, titulo in CAMBIOS:
        partes.append(f"### {titulo}\n\n```\n={regional(formula(nombre, propiedad))}\n```\n")
    partes.append('''## Usar la colección (sin galería bonita todavía)

Para ver la colección sin diseñar nada: *Insertar → Tabla de datos* → `Items` = `colPrevalidacionP9` → marca los campos `fila_excel`, `resultado`, `mensaje`,
`deposito_id`, `estado_actual`. Después de pulsar PREVALIDAR ARCHIVO debe tener una fila por cada fila del Excel.

Fórmulas de apoyo (úsalas en una etiqueta de prueba):

```
CountRows(Filter(colPrevalidacionP9; resultado = "VALIDO"))
CountRows(Filter(colPrevalidacionP9; resultado <> "VALIDO"))
Concat(Filter(colPrevalidacionP9; resultado = "NO_DISPONIBLE"); "Fila " & fila_excel & ": " & estado_actual; Char(10))
```

La futura confirmación solo deberá tomar `Filter(colPrevalidacionP9; resultado = "VALIDO")` y, **por cada fila, releer el depósito por `deposito_id`**:
la prevalidación **no reserva nada** (ver `PREVALIDACION_REAL.md`, «Concurrencia»).
''')
    return "\n".join(partes)


def formula_pantalla(propiedad):
    doc = yaml.safe_load((CARPETA / "P9_Confirmacion_Masiva.pa.yaml").read_text(encoding="utf-8"))
    return doc["Screens"]["P9_Confirmacion_Masiva"]["Properties"][propiedad].lstrip("=")


# Reinicio cuando el usuario adjunta o quita un archivo: el control de adjuntos es MANUAL (no está en el YAML), por eso la fórmula vive aquí
REINICIO_NUEVO_ARCHIVO = """Set(varResultadoP9, Blank());
Set(varMsAppP9, Blank());
Set(varResultadoConfirmacionP9, Blank());
Set(varMsConfirmacionP9, Blank());
Set(varConfirmacionMasivaFinalizadaP9, false);
Set(varVerObservacionesP9, false);
Clear(colPrevalidacionP9);
Clear(colConfirmacionP9)"""

CAMBIOS_CONFIRMACION = (
    ("pantalla", "OnVisible", "A · Pantalla `P9_Confirmacion_Masiva` → propiedad **OnVisible**"),
    ("attXlsxP9", "OnAddFile", "B · Control de adjuntos `attXlsxP9` → propiedades **OnAddFile** y **OnRemoveFile** (la misma fórmula en las dos)"),
    ("btnPrevalidarP9", "DisplayMode", "C · `btnPrevalidarP9` → **DisplayMode**"),
    ("btnPrevalidarP9", "OnSelect", "D · `btnPrevalidarP9` → **OnSelect** (añade el reinicio de la confirmación)"),
    ("btnConfirmarMasivamenteP9", "Text", "E · `btnConfirmarMasivamenteP9` → **Text**"),
    ("btnConfirmarMasivamenteP9", "DisplayMode", "F · `btnConfirmarMasivamenteP9` → **DisplayMode** (Disabled mientras corre y después de confirmar ese mismo resultado)"),
    ("btnConfirmarMasivamenteP9", "OnSelect", "G · `btnConfirmarMasivamenteP9` → **OnSelect** (UN clic, sin segundo modal)"),
    ("btnVerObservacionesP9", "Text", "H · `btnVerObservacionesP9` → **Text**"),
    ("btnVerObservacionesP9", "DisplayMode", "I · `btnVerObservacionesP9` → **DisplayMode**"),
    ("btnVerObservacionesP9", "OnSelect", "J · `btnVerObservacionesP9` → **OnSelect**"),
    ("galObservacionesP9", "Items", "K · `galObservacionesP9` → **Items** (antes de confirmar: observaciones de la prevalidación; después: filas no confirmadas)"),
    ("lblObsTituloP9", "Text", "L · etiqueta de título dentro de la galería (`lblObsTituloP9`) → **Text**"),
    ("lblObsMensajeP9", "Text", "M · etiqueta de mensaje dentro de la galería (`lblObsMensajeP9`) → **Text**"),
    ("lblEstadoP9", "Text", "N · `lblEstadoP9` → **Text**"),
    ("lblEstadoP9", "Fill", "O · `lblEstadoP9` → **Fill**"),
    ("lblTitularResultadoP9", "Text", "P · `lblTitularResultadoP9` → **Text** (resultado de la confirmación)"),
    ("lblResMensajeP9", "Text", "Q · `lblResMensajeP9` → **Text**"),
    ("lblResTiempoTituloP9", "Text", "R · `lblResTiempoTituloP9` → **Text**"),
    ("lblResTiempoP9", "Text", "S · `lblResTiempoP9` → **Text** (tiempo humanizado)"),
    ("lblResumenTituloP9", "Visible", "T · **Visible** de las 11 etiquetas del resumen (`lblResumenTituloP9`, `lblResArchivoTituloP9`, `lblResArchivoP9`, `lblResTablaTituloP9`, "
                                      "`lblResTablaP9`, `lblResFilasTituloP9`, `lblResFilasP9`, `lblResMensajeTituloP9`, `lblResMensajeP9`, `lblResTiempoTituloP9`, `lblResTiempoP9`)"),
    ("lblSubtituloMasivaP9", "Text", "U · `lblSubtituloMasivaP9` → **Text**"),
    ("lblAvisoPrototipoP9", "Text", "V · `lblAvisoPrototipoP9` → **Text**"))


def formula_de(nombre, propiedad):
    if nombre == "pantalla":
        return formula_pantalla(propiedad)
    if nombre == "attXlsxP9":
        return REINICIO_NUEVO_ARCHIVO
    return formula(nombre, propiedad)


def documento_confirmacion() -> str:
    partes = ['''# Power Fx de la CONFIRMACIÓN MASIVA (botón `btnConfirmarMasivamenteP9`)

> **Estado: preparado, NO validado en el tenant.** Las fórmulas pasan las pruebas estáticas del repositorio (paréntesis, columnas contra los esquemas
> de `detalle_json`, sin `Patch`/`SubmitForm`, sin segundo modal), pero **no se ejecutaron en Power Apps Studio**. Se **generan** desde
> `P9_Confirmacion_Masiva.pa.yaml` (`python proto_masiva/powerapps/generar_powerfx.py`): no las edites a mano aquí.
>
> **Importante:** los controles `btnVerObservacionesP9`, `galObservacionesP9`, `btnConfirmarMasivamenteP9` y el resto de la UX de observaciones **ya los creaste a mano en el
> tenant**; el YAML del repositorio es una **reconstrucción a partir de su descripción** (no hay export del tenant). **No pegues los controles encima:** cambia solo las
> fórmulas de abajo. Si tus controles internos se llaman distinto (p. ej. las etiquetas dentro de la galería), aplica la fórmula al control equivalente.

Escritas con `;` entre argumentos y `;;` entre sentencias (tu configuración regional).

## Variables y colecciones que usa (todas EN MEMORIA, ninguna se guarda)

| Nombre | Qué es |
|---|---|
| `colPrevalidacionP9` | filas de la prevalidación (ya existe) |
| `colConfirmacionP9` | resultado por fila de la confirmación (nuevo; se llena desde `detalle_json`) |
| `varProcesandoConfirmacionP9` | `true` mientras corre la confirmación (bloquea todos los botones) |
| `varConfirmacionMasivaFinalizadaP9` | `true` tras confirmar: el botón queda **Disabled** para ese mismo resultado de prevalidación; se reinicia al adjuntar otro archivo o al volver a PREVALIDAR |
| `varResultadoConfirmacionP9` | la respuesta del flujo (8 textos) |
| `varMsConfirmacionP9` | milisegundos de la confirmación (la pantalla los muestra como «8,9 segundos») |
| `varVerObservacionesP9` | VER / OCULTAR OBSERVACIONES |

`varConfirmarMasivaVisible` **ya no se usa** (no hay segundo modal): bórrala si la dejaste en alguna fórmula.

## Las fórmulas

Para cada una: selecciona el control → elige la propiedad en la barra de fórmulas → **borra todo** → pega.
''']
    for nombre, propiedad, titulo in CAMBIOS_CONFIRMACION:
        partes.append(f"### {titulo}\n\n```\n={regional(formula_de(nombre, propiedad))}\n```\n")
    return "\n".join(partes)


if __name__ == "__main__":
    (CARPETA / "PREVALIDACION_POWERFX.md").write_text(documento(), encoding="utf-8")
    (CARPETA / "CONFIRMACION_POWERFX.md").write_text(documento_confirmacion(), encoding="utf-8")
    print(CARPETA / "PREVALIDACION_POWERFX.md")
    print(CARPETA / "CONFIRMACION_POWERFX.md")
