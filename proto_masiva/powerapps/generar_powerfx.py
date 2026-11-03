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


# Orden de pegado: A primero, porque su `Set` DEFINE las variables que usan las demás.
# Parte del export REAL V1 (tenant_v1): solo cambian 9 propiedades + 1 control nuevo (el Timer). Nombres reales.
CAMBIOS_CONFIRMACION = (
    ("btnConfirmarMasivamenteP9", "OnSelect", "A · `btnConfirmarMasivamenteP9` → **OnSelect** (UN clic: responde enseguida y arranca el seguimiento; PEGA ESTA PRIMERO: define las variables nuevas)"),
    ("tmrProgresoP9", "OnTimerEnd", "B · `tmrProgresoP9` (Temporizador NUEVO, ver «Crear el Temporizador») → **OnTimerEnd**"),
    ("pantalla", "OnVisible", "C · Pantalla `P9_Confirmacion_Masiva` → propiedad **OnVisible** (reemplaza todo)"),
    ("attXlsxP9", "OnAddFile", "D · Control de adjuntos `attXlsxP9` → propiedades **OnAddFile** y **OnRemoveFile** (la misma fórmula en las dos)"),
    ("btnPrevalidarP9", "OnSelect", "E · `btnPrevalidarP9` → **OnSelect** (tu fórmula real con `IfError … true / false`, más 4 reinicios)"),
    ("lblTitularResultadoP9", "Text", "F · `lblTitularResultadoP9` → **Text** (avance en dos líneas mientras corre; resultado final en dos líneas; conserva el alto 50)"),
    ("lblResMensajeP9", "Text", "G · `lblResMensajeP9` → **Text**"),
    ("lblResTiempoP9", "Text", "H · `lblResTiempoP9` → **Text** (muestra «En curso» mientras corre)"),
    ("lblAvisoPrototipoP9", "Text", "I · `lblAvisoPrototipoP9` → **Text**"))

NO_CAMBIAN = (
    "`btnConfirmarMasivamenteP9` → **Text** y **DisplayMode** (ya bloquean mientras corre y después de confirmar) y toda su geometría/estilo",
    "`btnVerObservacionesP9`, `galObservacionesP9`, `Title1`, `Title1_1`, `Subtitle1`: tras terminar muestran SOLO las filas no confirmadas, igual que en la V1 (`colConfirmacionP9` ahora trae solo esas)",
    "`lblEstadoP9` (Text y Fill): ya muestran `CONFIRMANDO` mientras corre y `OK` / `PARCIAL` / `ERROR` al terminar",
    "`btnPrevalidarP9` → **DisplayMode**, `btnVolverMasivaP9`, `btnDescargarPlantillaP9`, `frmArchivoP9`, `dcAdjuntosP9` y los demás rótulos del resumen",
    "`Main_Screen`: `btnImportacionMasivaP9`, `cmbCuentaP9_1` y sus `Visible` con `mostrarConfirmacion`",
)

TIMER_PROPIEDADES = (("Duration", "15000"), ("Repeat", "true"), ("AutoStart", "false"), ("Start", "Coalesce(varMonitorearP9; false)"), ("Visible", "false"))


def formula_de(nombre, propiedad):
    if nombre == "pantalla":
        return formula_pantalla(propiedad)
    return formula(nombre, propiedad)


def documento_confirmacion() -> str:
    partes = ['''# Power Fx de la CONFIRMACIÓN MASIVA hasta 1999 filas (un clic, seguimiento por Temporizador)

> **Estado: NO VALIDADO en el tenant.** La V1 (confirmación síncrona de hasta 50 filas) SÍ funcionó de punta a punta en el tenant (commit `82b279e`, ver `../VALIDACION_TENANT_V1.md`).
> Estas fórmulas son la evolución para 1999 filas: se pegan sobre tus controles reales (`tenant_v1/P9_Confirmacion_Masiva.pa.yaml`, el export posterior a la V1) y pasan las pruebas
> estáticas del repositorio (paréntesis, esquemas, **todas las ramas de cada `IfError` devuelven booleano**, **`ShowColumns` sin comillas**), pero **no se ejecutaron en Power Apps Studio**.
> Se **generan** (`python proto_masiva/powerapps/generar_powerfx.py`) desde `P9_Confirmacion_Masiva.pa.yaml`: no las edites a mano aquí.
>
> **Qué cambia:** 9 propiedades en 8 elementos + **1 control nuevo** (un Temporizador oculto). Nada cambia de posición, tamaño ni estilo.
> Reglas que Studio ya impuso en tu tenant y que NO se deben deshacer a mano: `IfError` con ramas `true` / `false`; `ShowColumns(tabla; fila_excel; deposito_id; …)` **sin comillas**.

Escritas con `;` entre argumentos y `;;` entre sentencias (tu configuración regional).

## Antes de pegar: los dos flujos en la app (el contrato de `P9_MASIVA_PROTO_CONFIRMAR` CAMBIÓ)

`P9_MASIVA_PROTO_CONFIRMAR` ya no devuelve el resultado final: **responde enseguida** `resultado / codigo / mensaje / execution_uid / filas_recibidas` y sigue procesando.
Power Apps guarda la forma de las salidas de un flujo al agregarlo, así que hay que **quitarlo y volver a agregarlo**:

1. Panel izquierdo → **Power Automate** (⚡) → en `P9_MASIVA_PROTO_CONFIRMAR` → **⋯** → **Quitar de la aplicación** (los errores rojos de `.Run` que aparecen son esperados; se resuelven en el paso 3).
2. **Agregar flujo** → `P9_MASIVA_PROTO_ESTADO` (nuevo).
3. **Agregar flujo** → `P9_MASIVA_PROTO_CONFIRMAR` (el actualizado; el orden no importa).

## Crear el Temporizador (`tmrProgresoP9`) — único control nuevo

*Insertar → Entrada → Temporizador*; en la pantalla `P9_Confirmacion_Masiva`; renómbralo **`tmrProgresoP9`**. Propiedades (el resto déjalo por defecto):

| Propiedad | Valor |
|---|---|
''' + "\n".join(f"| `{k}` | `{v}` |" for k, v in TIMER_PROPIEDADES) + '''

`Duration = 15000` (15 s: el tope de los 10–15 s previstos; **no** consultar cada segundo — cada consulta ejecuta 12 acciones de Power Automate). Es invisible: no cambia el diseño. Su `OnTimerEnd` es la fórmula **B**.

## Variables y colecciones que usa (todas EN MEMORIA, ninguna se guarda)

| Nombre | Qué es |
|---|---|
| `colPrevalidacionP9` | filas de la prevalidación (ya existe y está validada) |
| `colConfirmacionP9` | SOLO las filas no confirmadas (se llena al terminar, desde el `detalle_json` del estado final) |
| `varEjecucionMasivaP9` | respuesta rápida de `P9_MASIVA_PROTO_CONFIRMAR` (`execution_uid`, `filas_recibidas`…) |
| `varProgresoMasivoP9` | última respuesta de `P9_MASIVA_PROTO_ESTADO` (estado, filas procesadas/confirmadas/no confirmadas, porcentaje, mensaje, detalle) |
| `varMonitorearP9` | `true` mientras el Temporizador debe consultar (es su `Start`) |
| `varFallosEstadoP9` | consultas seguidas que fallaron (a las 5, se detiene el seguimiento con un aviso) |
| `varInicioConfirmacionP9` | hora del clic (para el tiempo mostrado) |
| `varProcesandoConfirmacionP9` | `true` desde el clic hasta que termina: bloquea CONFIRMAR y PREVALIDAR (evita el doble clic) |
| `varConfirmacionMasivaFinalizadaP9` | `true` tras el clic: el botón queda **Disabled** para ese mismo resultado de prevalidación; se reinicia al adjuntar otro archivo o al volver a PREVALIDAR |
| `varResultadoConfirmacionP9` | resultado FINAL derivado del estado (`OK` / `PARCIAL` / `ERROR`); las fórmulas de la V1 siguen leyéndolo igual |
| `varMsConfirmacionP9` | milisegundos totales, mostrados como «8,9 segundos» |
| `varVerObservacionesP9` | VER / OCULTAR OBSERVACIONES (ya existe) |

`varConfirmarMasivaVisible` **no existe** (no hay segundo modal).

## Las fórmulas (en este orden)

Para cada una: selecciona el control → elige la propiedad en la barra de fórmulas → **borra todo** → pega. **Pega primero la A:** define las variables que usan las demás.
''']
    for nombre, propiedad, titulo in CAMBIOS_CONFIRMACION:
        partes.append(f"### {titulo}\n\n```\n={regional(formula_de(nombre, propiedad))}\n```\n")
    partes.append("## Lo que NO cambia (déjalo como está en tu app)\n\n" + "\n".join(f"- {x}" for x in NO_CAMBIAN) + "\n")
    partes.append('''## Qué mirar tras pegar

1. **Comprobador de aplicaciones** (estetoscopio): sin errores nuevos. Posibles puntos: `P9_MASIVA_PROTO_ESTADO.Run`, `P9_MASIVA_PROTO_CONFIRMAR.Run`, `JSON(ShowColumns(…))`, `With` dentro de `ForAll`.
   Cualquier error: copia el texto exacto; se ajusta solo esa línea.
2. **Al pulsar CONFIRMAR MASIVAMENTE (N)** debe verse en segundos «CONFIRMACIÓN EN PROCESO · 0 % / 0 de N procesados…», y cada ~15 s el avance. Al terminar: «CONFIRMACIÓN COMPLETADA» y, si hubo
   fallidas, `VER OBSERVACIONES (K)` con solo esas filas.
3. Si Power Apps se cierra durante el proceso, el backend sigue; esta versión NO recupera el seguimiento al volver (queda fuera de alcance): vuelve a PREVALIDAR para ver el estado real.
''')
    return "\n".join(partes)


if __name__ == "__main__":
    (CARPETA / "PREVALIDACION_POWERFX.md").write_text(documento(), encoding="utf-8")
    (CARPETA / "CONFIRMACION_POWERFX.md").write_text(documento_confirmacion(), encoding="utf-8")
    print(CARPETA / "PREVALIDACION_POWERFX.md")
    print(CARPETA / "CONFIRMACION_POWERFX.md")
