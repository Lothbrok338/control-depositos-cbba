# Guía de acciones de `P9_MASIVA_PROTO_ESTADO` (opción B: armarlo a mano)

> **Úsala solo si no puedes importar el ZIP.** Se **genera** desde la misma definición que el ZIP (`python proto_masiva/flows/guia_manual.py`). **No está validada en el tenant.**
> Es de **solo lectura**: lee `confirmacion_<execution_uid>.json` de `Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` y lo devuelve a Power Apps. Cada expresión va en la pestaña **Expresión** (sin el `@` inicial).

## Disparador

**Desencadenador:** *Power Apps (V2)* con **una** entrada:

1. Entrada de tipo **Texto** · Título: `execution_uid` · Descripción: Identificador devuelto por P9_MASIVA_PROTO_CONFIRMAR (execution_uid)

## Acciones, de arriba abajo

Las acciones `CATCH` y `Responder_a_PowerApps` usan **«Configurar ejecución posterior»**: `CATCH` = *ha error* y *superó el tiempo de espera* de `TRY`; `Responder_a_PowerApps` = **todas** las casillas de `TRY` y `CATCH`.

#### 1. `PARAM_SITIO`
**Redactar (Compose)** · Entradas:
```
https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu
```

#### 2. `PARAM_CARPETA`
**Redactar (Compose)** · Entradas:
```
/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP
```

#### 3. `Entrada`
**Redactar (Compose)** · Entradas:
```
{"uid": "@trim(coalesce(triggerBody()?['text'],''))"}
```

#### 4. `Inicializar_varEstado`
**Inicializar variable** · Nombre: `varEstado` · Tipo: `object` · Valor: `{}`

#### 5. `Inicializar_varFalloEstado`
**Inicializar variable** · Nombre: `varFalloEstado` · Tipo: `string` · Valor: `"ERROR"`

#### 6. `Inicializar_varFalloMensaje`
**Inicializar variable** · Nombre: `varFalloMensaje` · Tipo: `string` · Valor: `"No se pudo leer el progreso de la confirmación."`

#### 7. `Validar_uid`
**Redactar (Compose)** · Entradas:
```
if(or(not(equals(length(outputs('Entrada')?['uid']),36)),not(empty(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(toLower(outputs('Entrada')?['uid']),'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'a',''),'b',''),'c',''),'d',''),'e',''),'f',''),'-','')))),'UID_INVALIDO','')
```

#### 8. `TRY`
**Ámbito (Scope)** · se ejecuta después de: `{"Validar_uid": ["Succeeded"]}`

> **Dentro de `TRY`:**


> #### 9. `Uid_valido`
> **Condición (Condition)** · modo avanzado, expresión:
```
empty(outputs('Validar_uid'))
```

> > **Rama Sí (True) de `Uid_valido`:**


> > #### 10. `Leer_estado`
> > **Obtener contenido del archivo con la ruta de acceso (Get file content using path)** · conector **SharePoint** · Configuración → Directiva de reintentos: **Ninguna**. Campos:
> > - Dirección del sitio:
```
outputs('PARAM_SITIO')
```
> > - Ruta de acceso del archivo (expresión):
```
concat(outputs('PARAM_CARPETA'),'/','confirmacion_',outputs('Entrada')?['uid'],'.json')
```
> > - Inferir tipo de contenido:
```
No (desactivado)
```

> > #### 11. `Guardar_estado`
> > **Establecer variable (Set variable)** · Nombre: `varEstado` · Valor:
```
if(empty(body('Leer_estado')?['$content']),body('Leer_estado'),json(base64ToString(body('Leer_estado')?['$content'])))
```

> > **Rama No (False) de `Uid_valido`:**


> > #### 12. `Uid_invalido`
> > **Establecer variable (Set variable)** · Nombre: `varFalloMensaje` · Valor:
```
execution_uid inválido.
```

#### 13. `CATCH`
**Ámbito (Scope)** · se ejecuta después de: `{"TRY": ["Failed", "TimedOut"]}`

> **Dentro de `CATCH`:**


> #### 14. `Clasificar`
> **Condición (Condition)** · modo avanzado, expresión:
```
equals(outputs('Leer_estado')?['statusCode'],404)
```

> > **Rama Sí (True) de `Clasificar`:**


> > #### 15. `No_encontrado_estado`
> > **Establecer variable (Set variable)** · Nombre: `varFalloEstado` · Valor:
```
NO_ENCONTRADO
```

> > #### 16. `No_encontrado_mensaje`
> > **Establecer variable (Set variable)** · Nombre: `varFalloMensaje` · Valor:
```
Todavía no existe el registro de progreso de esta ejecución.
```

> > **Rama No (False) de `Clasificar`:**


> > #### 17. `Error_estado`
> > **Establecer variable (Set variable)** · Nombre: `varFalloEstado` · Valor:
```
ERROR
```

> > #### 18. `Error_mensaje`
> > **Establecer variable (Set variable)** · Nombre: `varFalloMensaje` · Valor:
```
No se pudo leer el progreso de la confirmación. Puede seguir ejecutándose en segundo plano.
```

#### 19. `Responder_a_PowerApps`
**Responder a una aplicación de PowerApps o a un flujo** · una salida de tipo **Texto** por cada fila (título → valor):
- `estado`:
```
coalesce(variables('varEstado')?['estado'],variables('varFalloEstado'))
```
- `filas_totales`:
```
string(coalesce(variables('varEstado')?['filas_totales'],0))
```
- `filas_procesadas`:
```
string(coalesce(variables('varEstado')?['filas_procesadas'],0))
```
- `filas_confirmadas`:
```
string(coalesce(variables('varEstado')?['filas_confirmadas'],0))
```
- `filas_no_confirmadas`:
```
string(coalesce(variables('varEstado')?['filas_no_confirmadas'],0))
```
- `porcentaje`:
```
string(coalesce(variables('varEstado')?['porcentaje'],0))
```
- `mensaje`:
```
coalesce(variables('varEstado')?['mensaje'],variables('varFalloMensaje'))
```
- `detalle_json`:
```
string(coalesce(variables('varEstado')?['detalle_json'],createArray()))
```
- `tiempos_ms`:
```
coalesce(variables('varEstado')?['tiempos_ms'],'')
```
