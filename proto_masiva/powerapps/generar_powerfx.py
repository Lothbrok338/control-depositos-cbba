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

> **Estado: preparado, NO validado en el tenant.** Las fórmulas pasan las pruebas estáticas del repositorio (paréntesis, nombres de columna contra
> `flows/esquema_detalle_json.json`, sin escrituras), pero **no se han ejecutado en Power Apps Studio**. Este archivo se **genera** desde
> `P9_Confirmacion_Masiva.pa.yaml` (`python proto_masiva/powerapps/generar_powerfx.py`): no lo edites a mano.

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


if __name__ == "__main__":
    (CARPETA / "PREVALIDACION_POWERFX.md").write_text(documento(), encoding="utf-8")
    print(CARPETA / "PREVALIDACION_POWERFX.md")
