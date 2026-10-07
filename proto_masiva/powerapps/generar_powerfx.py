"""Genera PREVALIDACION_POWERFX.md y CONFIRMACION_POWERFX.md: las fórmulas LEÍDAS del YAML (única fuente) y mostradas en la sintaxis
de la configuración regional de Gabriel (`;` entre argumentos y `;;` entre sentencias).

- PREVALIDACION_POWERFX.md  ← `tenant/P9_Confirmacion_Masiva.pa.yaml` (export REAL del tenant: lo ya validado en la prevalidación).
- CONFIRMACION_POWERFX.md   ← `P9_Confirmacion_Masiva.pa.yaml` (el export real + la integración de la confirmación: solo cambian fórmulas).

    python proto_masiva/powerapps/generar_powerfx.py
"""
from pathlib import Path

import yaml

CARPETA = Path(__file__).resolve().parent
TENANT = CARPETA / "tenant" / "P9_Confirmacion_Masiva.pa.yaml"      # export real, solo lectura
INTEGRADO = CARPETA / "P9_Confirmacion_Masiva.pa.yaml"             # export real + fórmulas de la confirmación


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


def controles(archivo=INTEGRADO):
    doc = yaml.safe_load(archivo.read_text(encoding="utf-8"))
    raiz = doc["Screens"]["P9_Confirmacion_Masiva"]["Children"]
    salida = {}

    def recorrer(hijos):
        for h in hijos:
            (nombre, c), = h.items()
            salida[nombre] = c
            recorrer(c.get("Children", []))
    recorrer(raiz)
    return salida


def formula(nombre, propiedad, archivo=INTEGRADO):
    return controles(archivo)[nombre]["Properties"][propiedad].lstrip("=")


CAMBIOS = (("btnPrevalidarP9", "OnSelect", "1 · `btnPrevalidarP9` → propiedad **OnSelect** (reemplaza TODO el contenido)"),
           ("lblEstadoP9", "Fill", "2 · `lblEstadoP9` → **Fill**"),
           ("lblTitularResultadoP9", "Text", "3 · `lblTitularResultadoP9` → **Text**"),
           ("lblResFilasP9", "Text", "4 · `lblResFilasP9` → **Text**"),
           ("lblAvisoPrototipoP9", "Text", "5 · `lblAvisoPrototipoP9` → **Text**"))


def documento() -> str:
    partes = ['''# Power Fx de la prevalidación real (colección `colPrevalidacionP9`)

> **Estado: la prevalidación con esta colección ya fue validada en el tenant.** Las fórmulas que se muestran son las **REALES de `P9_PRUEBA_MASIVA`** (export del tenant,
> `tenant/P9_Confirmacion_Masiva.pa.yaml`), incluida la corrección `IfError(…;; true, …;; false)`. Lo que cambia en la fase de confirmación, con los pasos exactos,
> está en **`CONFIRMACION_POWERFX.md`**. Este archivo se **genera** (`python proto_masiva/powerapps/generar_powerfx.py`): no lo edites a mano.

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
        partes.append(f"### {titulo}\n\n```\n={regional(formula(nombre, propiedad, TENANT))}\n```\n")
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
    doc = yaml.safe_load(INTEGRADO.read_text(encoding="utf-8"))
    return doc["Screens"]["P9_Confirmacion_Masiva"]["Properties"][propiedad].lstrip("=")


# Orden de pegado: A primero, porque su `Set`/`ClearCollect` DEFINE las variables y la colección que usan las demás fórmulas.
# Nombres REALES del tenant (Title1 es la etiqueta del título dentro de la galería, como la nombró Studio).
CAMBIOS_CONFIRMACION = (
    ("btnConfirmarMasivamenteP9", "OnSelect", "A · `btnConfirmarMasivamenteP9` → **OnSelect** (UN clic, sin segundo modal; PEGA ESTA PRIMERO: define las variables y `colConfirmacionP9`)"),
    ("btnConfirmarMasivamenteP9", "DisplayMode", "B · `btnConfirmarMasivamenteP9` → **DisplayMode** (Disabled mientras corre y después de confirmar ese mismo resultado)"),
    ("pantalla", "OnVisible", "C · Pantalla `P9_Confirmacion_Masiva` → propiedad **OnVisible** (reemplaza todo; retira `varConfirmarMasivaVisible`)"),
    ("attXlsxP9", "OnAddFile", "D · Control de adjuntos `attXlsxP9` → propiedades **OnAddFile** y **OnRemoveFile** (la misma fórmula en las dos)"),
    ("btnPrevalidarP9", "DisplayMode", "E · `btnPrevalidarP9` → **DisplayMode**"),
    ("btnPrevalidarP9", "OnSelect", "F · `btnPrevalidarP9` → **OnSelect** (tu fórmula real con `IfError … true / false`, más el reinicio de la confirmación)"),
    ("btnVerObservacionesP9", "Text", "G · `btnVerObservacionesP9` → **Text**"),
    ("btnVerObservacionesP9", "Visible", "H · `btnVerObservacionesP9` → **Visible**"),
    ("galObservacionesP9", "Items", "I · `galObservacionesP9` → **Items** (antes de confirmar: observaciones de la prevalidación; después: filas no confirmadas)"),
    ("Title1", "Text", "J · `Title1` (etiqueta de título DENTRO de `galObservacionesP9`) → **Text** (añade los resultados de la confirmación)"),
    ("lblEstadoP9", "Text", "K · `lblEstadoP9` → **Text**"),
    ("lblEstadoP9", "Fill", "L · `lblEstadoP9` → **Fill**"),
    ("lblTitularResultadoP9", "Text", "M · `lblTitularResultadoP9` → **Text** (resultado de la confirmación en dos líneas; conserva el alto 50 del tenant)"),
    ("lblResMensajeP9", "Text", "N · `lblResMensajeP9` → **Text**"),
    ("lblResTiempoP9", "Text", "O · `lblResTiempoP9` → **Text** (tiempo humanizado, mismo formato «8,9 segundos»)"),
    ("lblSubtituloMasivaP9", "Text", "P · `lblSubtituloMasivaP9` → **Text**"),
    ("lblAvisoPrototipoP9", "Text", "Q · `lblAvisoPrototipoP9` → **Text**"))

NO_CAMBIAN = (
    "`btnConfirmarMasivamenteP9` → **Text** (ya cuenta las filas `VALIDO`) y toda su geometría/estilo",
    "`btnVerObservacionesP9` → **OnSelect** (ya alterna `varVerObservacionesP9`) y su aspecto",
    "`Title1_1` (etiqueta del mensaje dentro de la galería) → `=ThisItem.mensaje`, y `Subtitle1`, `Separator1`, `Rectangle1`",
    "`lblResMensajeP9` → **Visible** (`=!varVerObservacionesP9`) y `lblResTiempoTituloP9` («Tiempo de Procesamiento»)",
    "`btnDescargarPlantillaP9`, `btnVolverMasivaP9`, `frmArchivoP9`, `dcAdjuntosP9`, el panel y los demás rótulos del resumen",
    "`Main_Screen`: `btnImportacionMasivaP9`, `cmbCuentaP9_1` y sus `Visible` con `mostrarConfirmacion`",
)


def formula_de(nombre, propiedad):
    if nombre == "pantalla":
        return formula_pantalla(propiedad)
    return formula(nombre, propiedad)


def documento_confirmacion() -> str:
    partes = ['''# Power Fx de la CONFIRMACIÓN MASIVA (botón `btnConfirmarMasivamenteP9`)

> **Estado: preparado sobre el export REAL de `P9_PRUEBA_MASIVA`; NO validado en el tenant.** Las fórmulas pasan las pruebas estáticas del repositorio (paréntesis,
> columnas contra los esquemas de `detalle_json`, sin `Patch`/`SubmitForm`, sin segundo modal, **todas las ramas de cada `IfError` devuelven booleano**), pero **no se
> ejecutaron en Power Apps Studio**. Se **generan** (`python proto_masiva/powerapps/generar_powerfx.py`) desde `P9_Confirmacion_Masiva.pa.yaml`: no las edites a mano aquí.
>
> **No pegues controles ni el YAML:** los controles ya existen en tu app con estos nombres (el export del tenant es la fuente de verdad: `tenant/P9_Confirmacion_Masiva.pa.yaml`).
> Solo se **reemplazan 18 propiedades** en 13 elementos (la pantalla y 12 controles; las de abajo). Nada cambia de posición, tamaño ni estilo. Las fórmulas conservan tu corrección de tipos en `IfError`:
> ambas ramas terminan en `true` / `false`, como ya aceptó Studio en la prevalidación.

Escritas con `;` entre argumentos y `;;` entre sentencias (tu configuración regional).

## Antes de pegar: agregar el flujo a la app

Panel izquierdo → **Power Automate** (⚡) → **Agregar flujo** → `P9_MASIVA_PROTO_CONFIRMAR` (ver `flows/INSTRUCCIONES_CONFIRMAR.md`). Sin esto, `P9_MASIVA_PROTO_CONFIRMAR.Run` no se resuelve.

## Variables y colecciones que usa (todas EN MEMORIA, ninguna se guarda)

| Nombre | Qué es |
|---|---|
| `colPrevalidacionP9` | filas de la prevalidación (ya existe y está validada) |
| `colConfirmacionP9` | resultado por fila de la confirmación (nuevo; se llena desde `detalle_json`) |
| `varProcesandoConfirmacionP9` | `true` mientras corre la confirmación (bloquea CONFIRMAR y PREVALIDAR) |
| `varConfirmacionMasivaFinalizadaP9` | `true` tras confirmar: el botón queda **Disabled** para ese mismo resultado de prevalidación; se reinicia al adjuntar otro archivo o al volver a PREVALIDAR |
| `varResultadoConfirmacionP9` | la respuesta del flujo (8 textos) |
| `varMsConfirmacionP9` | milisegundos de la confirmación (la pantalla los muestra como «8,9 segundos») |
| `varVerObservacionesP9` | VER / OCULTAR OBSERVACIONES (ya existe) |

`varConfirmarMasivaVisible` **ya no se usa** (no hay segundo modal): el paso C la quita del `OnVisible`, y el paso A reemplaza el `OnSelect` que la ponía en `true`.
Si tenías la variable en otro sitio, bórrala.

## Las fórmulas (en este orden)

Para cada una: selecciona el control → elige la propiedad en la barra de fórmulas → **borra todo** → pega. **Pega primero la A:** define las variables y la colección que usan las demás.
''']
    for nombre, propiedad, titulo in CAMBIOS_CONFIRMACION:
        partes.append(f"### {titulo}\n\n```\n={regional(formula_de(nombre, propiedad))}\n```\n")
    partes.append("## Lo que NO cambia (déjalo como está en tu app)\n\n" + "\n".join(f"- {x}" for x in NO_CAMBIAN) + "\n")
    partes.append('''## Qué mirar tras pegar

1. **Comprobador de aplicaciones** (estetoscopio): sin errores nuevos. Cualquier error en `P9_MASIVA_PROTO_CONFIRMAR.Run`, `JSON(ShowColumns(…))`, `ThisRecord.Value` o `With` dentro
   de `ForAll`: copia el texto exacto; se ajusta solo esa línea.
2. **Alto del titular:** el resultado de la confirmación ocupa dos líneas dentro del alto 50 que ya tienes; si se corta, sube el alto de `lblTitularResultadoP9` (único ajuste visual posible).
3. Pruebas en el tenant: `flows/INSTRUCCIONES_CONFIRMAR.md`, Parte 3 (empieza con **1 fila**).
''')
    return "\n".join(partes)


if __name__ == "__main__":
    (CARPETA / "PREVALIDACION_POWERFX.md").write_text(documento(), encoding="utf-8")
    (CARPETA / "CONFIRMACION_POWERFX.md").write_text(documento_confirmacion(), encoding="utf-8")
    print(CARPETA / "PREVALIDACION_POWERFX.md")
    print(CARPETA / "CONFIRMACION_POWERFX.md")
