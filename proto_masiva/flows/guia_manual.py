"""Genera GUIA_ACCIONES_PREVALIDACION.md: la lista EXACTA (acción por acción, con sus expresiones) de lo que añade la prevalidación real.

    python proto_masiva/flows/guia_manual.py

Es la opción B (armar a mano en el diseñador de Power Automate) por si la importación del ZIP no se pudiera usar. Se GENERA desde la misma
definición que el ZIP, así que las expresiones son idénticas, no una copia mantenida a mano. Las expresiones se muestran SIN el `@` inicial,
tal como se pegan en la pestaña «Expresión» del diseñador.
"""
import json
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parents[1]))
from proto_masiva.flows import construir as F  # noqa: E402


def politica_reintentos(rp):
    """Texto de «Configuración → Directiva de reintentos» a partir del `retryPolicy` REAL de la acción."""
    if rp.get("type") == "none":
        return "Ninguna"
    assert rp["type"] == "fixed", rp
    return f"Intervalo fijo, {rp['count']} reintentos, {rp['interval']}"


ETIQUETAS_SP = {
    "CreateFile": ("Crear archivo (Create file)", [("dataset", "Dirección del sitio"), ("folderPath", "Ruta de acceso a la carpeta"),
                                                    ("name", "Nombre del archivo"), ("body", "Contenido del archivo (expresión)")]),
    "UpdateFile": ("Actualizar archivo (Update file)", [("dataset", "Dirección del sitio"), ("id", "Identificador del archivo"),
                                                         ("body", "Contenido del archivo (expresión)")]),
    "GetFileContentByPath": ("Obtener contenido del archivo con la ruta de acceso (Get file content using path)",
                             [("dataset", "Dirección del sitio"), ("path", "Ruta de acceso del archivo (expresión)"),
                              ("inferContentType", "Inferir tipo de contenido")])}


def mostrar(valor, nivel=0):
    if isinstance(valor, str) and valor.startswith("@"):
        return valor[1:]
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def bloque_codigo(texto):
    return f"```\n{texto}\n```"


def describir(nombre, accion, numero, sangria=""):
    tipo = accion["type"]
    sal = [f"{sangria}#### {numero}. `{nombre}`"]
    i = accion.get("inputs", {})
    if tipo == "SetVariable":
        etiqueta = "Establecer variable (Set variable)"
        sal += [f"{sangria}**{etiqueta}** · Nombre: `{i['name']}` · Valor:", bloque_codigo(mostrar(i["value"]))]
    elif tipo == "Compose":
        sal += [f"{sangria}**Redactar (Compose)** · Entradas:", bloque_codigo(mostrar(i))]
    elif tipo == "Select":
        sal += [f"{sangria}**Seleccionar (Select)** · De (From):", bloque_codigo(mostrar(i["from"])),
                f"{sangria}Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:"]
        if isinstance(i["select"], dict):
            for clave, valor in i["select"].items():
                sal += [f"{sangria}- Clave `{clave}`:", bloque_codigo(mostrar(valor))]
        else:
            sal += [f"{sangria}(Map en modo texto, una sola expresión):", bloque_codigo(mostrar(i["select"]))]
    elif tipo == "Query":
        sal += [f"{sangria}**Filtrar matriz (Filter array)** · De (From):", bloque_codigo(mostrar(i["from"])),
                f"{sangria}Condición (modo avanzado, expresión):", bloque_codigo(mostrar(i["where"]))]
    elif tipo == "OpenApiConnection" and i["host"]["operationId"] != "HttpRequest":
        p, op = i["parameters"], i["host"]["operationId"]
        etiqueta, campos = ETIQUETAS_SP[op]
        sal += [f"{sangria}**{etiqueta}** · conector **SharePoint** · Configuración → Directiva de reintentos: **{politica_reintentos(i['retryPolicy'])}**. Campos:"]
        for parametro, titulo in campos:
            sal += [f"{sangria}- {titulo}:", bloque_codigo(mostrar(p[parametro]) if parametro != "inferContentType" else "No (desactivado)")]
    elif tipo == "OpenApiConnection":
        p = i["parameters"]
        sal += [f"{sangria}**Enviar una solicitud HTTP a SharePoint** · Dirección del sitio: `{p['dataset']}` (la misma de `PARAM_SITIO`) · "
                f"Método: `{p['parameters/method']}` · Encabezados: `{json.dumps(p['parameters/headers'])}` · "
                f"Configuración → Directiva de reintentos: **{politica_reintentos(i['retryPolicy'])}**. Uri (expresión):", bloque_codigo(mostrar(p["parameters/uri"]))]
    elif tipo == "If":
        sal += [f"{sangria}**Condición (Condition)** · modo avanzado, expresión:", bloque_codigo(mostrar(accion["expression"]))]
    elif tipo == "IncrementVariable":
        sal += [f"{sangria}**Incrementar variable (Increment variable)** · Nombre: `{i['name']}` · Valor: `{i['value']}`"]
    elif tipo == "InitializeVariable":
        v = i["variables"][0]
        sal += [f"{sangria}**Inicializar variable** · Nombre: `{v['name']}` · Tipo: `{v['type']}` · Valor: `{json.dumps(v['value'], ensure_ascii=False)}`"]
    elif tipo == "AppendToArrayVariable":
        sal += [f"{sangria}**Anexar a variable de matriz (Append to array variable)** · Nombre: `{i['name']}` · Valor (objeto; cada propiedad es una expresión o un texto fijo):"]
        for clave, valor in i["value"].items():
            sal += [f"{sangria}- Propiedad `{clave}`:", bloque_codigo(mostrar(valor))]
    elif tipo == "Scope":
        sal += [f"{sangria}**Ámbito (Scope)**" + (f" · se ejecuta después de: `{json.dumps(accion['runAfter'], ensure_ascii=False)}`" if accion.get("runAfter") else "")]
    elif tipo == "Foreach":
        sal += [f"{sangria}**Aplicar a cada uno (Apply to each)** · Seleccione una salida de los pasos anteriores:", bloque_codigo(mostrar(accion["foreach"])),
                f"{sangria}Configuración (⋯) → **Control de simultaneidad: Activado, grado de paralelismo = 1** (secuencial)."]
    elif tipo == "Response":
        sal += [f"{sangria}**Responder a una aplicación de PowerApps o a un flujo** · una salida de tipo **Texto** por cada fila (título → valor):"]
        for clave, valor in i["body"].items():
            sal += [f"{sangria}- `{clave}`:", bloque_codigo(mostrar(valor))]
    else:
        raise AssertionError(tipo)
    return "\n".join(sal)


def aplanar(acciones, contador, sangria=""):
    texto = []
    for nombre, accion in acciones.items():
        contador[0] += 1
        texto.append(describir(nombre, accion, contador[0], sangria))
        if accion["type"] in ("Scope", "Foreach"):
            texto.append(f"{sangria}> **Dentro de `{nombre}`:**\n")
            texto.append(aplanar(accion["actions"], contador, sangria + "> "))
        if accion["type"] == "If":
            texto.append(f"{sangria}> **Rama Sí (True) de `{nombre}`:**\n")
            texto.append(aplanar(accion["actions"], contador, sangria + "> "))
            if accion["else"]["actions"]:
                texto.append(f"{sangria}> **Rama No (False) de `{nombre}`:**\n")
                texto.append(aplanar(accion["else"]["actions"], contador, sangria + "> "))
    return "\n\n".join(texto)


def buscar(acciones, nombre):
    """El diccionario de acciones (un bloque) que contiene la acción `nombre`."""
    if nombre in acciones:
        return acciones
    for a in acciones.values():
        for hijo in (a.get("actions", {}), a.get("else", {}).get("actions", {})):
            r = buscar(hijo, nombre) if hijo else None
            if r:
                return r
    return None


def documento():
    d = F.construir_definicion()
    bloque = buscar(d["actions"], "Marca_T5")
    nuevas_init = [n for n in d["actions"] if n in ("PARAM_LISTA_DEPOSITOS_ACTIVOS", "PARAM_TOPE_DEPOSITOS", "Inicializar_varT5", "Inicializar_varT6",
                                                  "Inicializar_varTotales", "Inicializar_varValidas", "Inicializar_varConError",
                                                  "Inicializar_varUniverso", "Inicializar_varDetalle")]
    partes = ['''# Guía de acciones de la PREVALIDACIÓN REAL (opción B: armarlo a mano)

> **Úsala solo si no puedes importar el ZIP** (`ACTUALIZAR_FLUJO_PREVALIDACION.md`, opción A). Se **genera** desde la misma definición que el ZIP
> (`python proto_masiva/flows/guia_manual.py`), así que las expresiones son idénticas. **No está validada en el tenant**: son las expresiones que
> pasan las pruebas locales (tenant simulado), no se han ejecutado en Power Automate.
>
> En el diseñador, cada expresión se pega en la pestaña **Expresión** del campo (sin el `@` inicial). Los nombres de las acciones son los que
> aparecen aquí: **respétalos exactamente** (las expresiones se refieren unas a otras por nombre; si renombras una acción, el diseñador reescribe las
> referencias, pero el resto de este documento ya no coincidirá).

## Parte 1 · Al inicio del flujo, después de `PARAM_MAX_FILAS` y entre las variables existentes

Añade, **en este orden**, justo debajo de `PARAM_MAX_FILAS` los dos `Redactar` y, junto a las demás `Inicializar variable`, las siete variables nuevas.
''']
    n = 0
    for nombre in nuevas_init:
        n += 1
        partes.append(describir(nombre, d["actions"][nombre], n) if d["actions"][nombre]["type"] != "InitializeVariable" else
                      f"#### {n}. `{nombre}` · **Inicializar variable** · Nombre: `{d['actions'][nombre]['inputs']['variables'][0]['name']}` · "
                      f"Tipo: `{d['actions'][nombre]['inputs']['variables'][0]['type']}` · Valor: "
                      f"`{json.dumps(d['actions'][nombre]['inputs']['variables'][0]['value'])}`")
    partes.append('''
## Parte 2 · El bloque nuevo (reemplaza a la acción `Resultado_OK`)

**Dónde:** `TRY` → condición `Entrada_valida` (Sí) → `Hay_filas` (Sí) → `Limite_de_lectura` (No) → `Estructura` (No) → `Hay_datos` (Sí) →
`Hay_tope` (**rama No**). En esa rama hoy hay UNA acción: `Resultado_OK`. **Bórrala** y añade, **en este orden y una debajo de otra**, las acciones siguientes.
Las dos acciones finales de la condición `Universo_completo` van **dentro de sus ramas**.
''')
    contador = [0]
    partes.append(aplanar(bloque, contador))
    sal_t = d["actions"]["Tiempos"]["inputs"]
    cuerpo = d["actions"]["Responder_a_PowerApps"]["inputs"]["body"]
    catch = d["actions"]["CATCH"]["actions"]["Clasificar_fallo"]["else"]["actions"]["Fallo_no_excel"]["else"]["actions"]["Fallo_no_copia"]
    partes.append('''
## Parte 3 · Tres cambios en acciones que ya existen

### 3.1 · `Tiempos` (Redactar, al final del flujo) → reemplaza sus Entradas por:
''' + bloque_codigo(mostrar(sal_t)) + '''

### 3.2 · `CATCH` → `Clasificar_fallo` → rama No → `Fallo_no_excel` → rama No: hoy contiene `Fallo_ERROR_COPIA` (si la etapa es COPIA) y, si no, `Fallo_ERROR_NO_CONTROLADO`
Cambia el contenido de la **rama No de `Fallo_no_excel`** para que sea esta condición, con la acción antigua `Fallo_ERROR_NO_CONTROLADO` dentro de su rama No:
''' + bloque_codigo(mostrar(catch["expression"])) + '''
**Rama Sí:** `Fallo_ERROR_SHAREPOINT` · **Establecer variable** `varResultado` · Valor (objeto, modo texto):
''' + bloque_codigo(json.dumps(catch["actions"]["Fallo_ERROR_SHAREPOINT"]["inputs"]["value"], ensure_ascii=False, indent=1)) + '''

### 3.3 · `Responder_a_PowerApps` → añade 5 salidas de tipo **Texto** (después de `tiempos_ms`), una por una (*Agregar una salida → Texto*):

| Título de la salida | Valor (expresión) |
|---|---|
''' + "\n".join(f"| `{k}` | `{mostrar(cuerpo[k])}` |" for k in F.SALIDAS_NUEVAS) + "\n")
    return "\n\n".join(p if isinstance(p, str) else str(p) for p in partes) + "\n"


def documento_confirmar() -> str:
    from proto_masiva.flows import construir_confirmar as K
    d = K.construir_definicion()
    (nombre, disparo), = d["triggers"].items()
    entradas = "\n".join(f"{n}. Entrada de tipo **Texto** · Título: `{p['title']}` · Descripción: {p['description']}"
                         for n, (c, p) in enumerate(disparo["inputs"]["schema"]["properties"].items(), 1))
    encabezado = f'''# Guía de acciones de `P9_MASIVA_PROTO_CONFIRMAR` (opción B: armarlo a mano)

> **Úsala solo si no puedes importar el ZIP** (`INSTRUCCIONES_CONFIRMAR.md`, opción A). Se **genera** desde la misma definición que el ZIP
> (`python proto_masiva/flows/guia_manual.py`): las expresiones son idénticas. **No está validada en el tenant** (la V1 síncrona sí; esta es la de escala hasta 1999).
> Cada expresión se pega en la pestaña **Expresión** (sin el `@` inicial). Respeta los nombres de las acciones: se refieren unas a otras por nombre.

## Disparador

**Desencadenador:** *Power Apps (V2)* con **dos** entradas, en este orden (la app las pasa como argumentos posicionales):

{entradas}

## Cómo funciona (léelo antes de armarlo)

1. `PREPARAR` valida la entrada, cuenta las filas y crea el archivo de estado `confirmacion_<execution_uid>.json` en `Documents/P9_MASIVA_TEMP` (estado PROCESANDO).
2. `RESPONDER` contiene **dos** acciones *Responder a una aplicación de PowerApps o a un flujo*, una en cada rama de la condición: **solo una se ejecuta**. Responde ACEPTADO (con `execution_uid`) o ERROR.
3. `PROCESAR` va **después** de responder: el flujo SIGUE ejecutándose (documentado por Microsoft: las acciones posteriores a la respuesta continúan más allá del límite de 120 s; una ejecución puede durar hasta 30 días).
   Recorre las filas válidas en secuencia (**Control de simultaneidad: Activado, paralelismo 1**) y cada 25 filas actualiza el estado. Al terminar escribe TERMINADO con SOLO las filas no confirmadas.
4. Las variables (`Inicializar_*`) se crean **al principio del flujo, fuera de cualquier condición o ámbito** (requisito de Power Automate).

## Acciones, de arriba abajo (lo indentado va dentro del bloque que lo contiene)

Cada acción se ejecuta **después de la anterior** salvo que se indique otra cosa. Las acciones con **«Configurar ejecución posterior»** (⋯ → Configurar la ejecución posterior) marcan las casillas de su `runAfter`:
`*_CATCH` y `CATCH_FILA`: *ha error* y *superó el tiempo de espera*; `RESPONDER`, `FINALIZAR`, `Contar_procesada` y los de `runAfter` con las cuatro casillas: **todas**.
'''
    contador = [0]
    cuerpo = aplanar(d["actions"], contador)
    return encabezado + "\n" + cuerpo + "\n"


def documento_estado() -> str:
    from proto_masiva.flows import construir_estado as E
    d = E.construir_definicion()
    (nombre, disparo), = d["triggers"].items()
    entradas = "\n".join(f"{n}. Entrada de tipo **Texto** · Título: `{p['title']}` · Descripción: {p['description']}"
                         for n, (c, p) in enumerate(disparo["inputs"]["schema"]["properties"].items(), 1))
    encabezado = f'''# Guía de acciones de `P9_MASIVA_PROTO_ESTADO` (opción B: armarlo a mano)

> **Úsala solo si no puedes importar el ZIP.** Se **genera** desde la misma definición que el ZIP (`python proto_masiva/flows/guia_manual.py`). **No está validada en el tenant.**
> Es de **solo lectura**: lee `confirmacion_<execution_uid>.json` de `Documents/P9_MASIVA_TEMP` y lo devuelve a Power Apps. Cada expresión va en la pestaña **Expresión** (sin el `@` inicial).

## Disparador

**Desencadenador:** *Power Apps (V2)* con **una** entrada:

{entradas}

## Acciones, de arriba abajo

Las acciones `CATCH` y `Responder_a_PowerApps` usan **«Configurar ejecución posterior»**: `CATCH` = *ha error* y *superó el tiempo de espera* de `TRY`; `Responder_a_PowerApps` = **todas** las casillas de `TRY` y `CATCH`.
'''
    contador = [0]
    return encabezado + "\n" + aplanar(d["actions"], contador) + "\n"


if __name__ == "__main__":
    (CARPETA / "GUIA_ACCIONES_ESTADO.md").write_text(documento_estado(), encoding="utf-8")
    print(CARPETA / "GUIA_ACCIONES_ESTADO.md")
    (CARPETA / "GUIA_ACCIONES_PREVALIDACION.md").write_text(documento(), encoding="utf-8")
    (CARPETA / "GUIA_ACCIONES_CONFIRMACION.md").write_text(documento_confirmar(), encoding="utf-8")
    print(CARPETA / "GUIA_ACCIONES_PREVALIDACION.md")
    print(CARPETA / "GUIA_ACCIONES_CONFIRMACION.md")
