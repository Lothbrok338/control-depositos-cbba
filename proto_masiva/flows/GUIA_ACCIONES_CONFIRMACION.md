# Guía de acciones de `P9_MASIVA_PROTO_CONFIRMAR` (opción B: armarlo a mano)

> **Úsala solo si no puedes importar el ZIP** (`INSTRUCCIONES_CONFIRMAR.md`, opción A). Se **genera** desde la misma definición que el ZIP
> (`python proto_masiva/flows/guia_manual.py`): las expresiones son idénticas. **No está validada en el tenant** (la V1 síncrona sí; esta es la de escala hasta 1999).
> Cada expresión se pega en la pestaña **Expresión** (sin el `@` inicial). Respeta los nombres de las acciones: se refieren unas a otras por nombre.

## Disparador

**Desencadenador:** *Power Apps (V2)* con **dos** entradas, en este orden (la app las pasa como argumentos posicionales):

1. Entrada de tipo **Texto** · Título: `detalle_json` · Descripción: Filas VALIDO de la prevalidación, como arreglo JSON (JSON(..., JSONFormat.Compact))
2. Entrada de tipo **Texto** · Título: `usuario_email` · Descripción: Correo del usuario que confirma (User().Email), como en la confirmación individual

## Cómo funciona (léelo antes de armarlo)

1. `PREPARAR` valida la entrada, cuenta las filas y crea el archivo de estado `confirmacion_<execution_uid>.json` en `Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP` (estado PROCESANDO).
2. `RESPONDER` contiene **dos** acciones *Responder a una aplicación de PowerApps o a un flujo*, una en cada rama de la condición: **solo una se ejecuta**. Responde ACEPTADO (con `execution_uid`) o ERROR.
3. `PROCESAR` va **después** de responder: el flujo SIGUE ejecutándose (documentado por Microsoft: las acciones posteriores a la respuesta continúan más allá del límite de 120 s; una ejecución puede durar hasta 30 días).
   Recorre las filas válidas en secuencia (**Control de simultaneidad: Activado, paralelismo 1**) y cada 25 filas actualiza el estado. Al terminar escribe TERMINADO con SOLO las filas no confirmadas.
4. Las variables (`Inicializar_*`) se crean **al principio del flujo, fuera de cualquier condición o ámbito** (requisito de Power Automate).

## Acciones, de arriba abajo (lo indentado va dentro del bloque que lo contiene)

Cada acción se ejecuta **después de la anterior** salvo que se indique otra cosa. Las acciones con **«Configurar ejecución posterior»** (⋯ → Configurar la ejecución posterior) marcan las casillas de su `runAfter`:
`*_CATCH` y `CATCH_FILA`: *ha error* y *superó el tiempo de espera*; `RESPONDER`, `FINALIZAR`, `Contar_procesada` y los de `runAfter` con las cuatro casillas: **todas**.

#### 1. `PARAM_SITIO`
**Redactar (Compose)** · Entradas:
```
https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu
```

#### 2. `PARAM_LISTA_DEPOSITOS_ACTIVOS`
**Redactar (Compose)** · Entradas:
```
296c450a-25d6-415b-ad10-c909c74817cb
```

#### 3. `PARAM_CARPETA`
**Redactar (Compose)** · Entradas:
```
/Documents/CONTROL_DEPOSITOS/P9/P9_MASIVA_TEMP
```

#### 4. `PARAM_MAX_FILAS_POR_LLAMADA`
**Redactar (Compose)** · Entradas:
```
1999
```

#### 5. `PARAM_MAX_FILAS_ARCHIVO`
**Redactar (Compose)** · Entradas:
```
1999
```

#### 6. `PARAM_INTERVALO_PROGRESO`
**Redactar (Compose)** · Entradas:
```
25
```

#### 7. `PARAM_MAX_DETALLE`
**Redactar (Compose)** · Entradas:
```
300
```

#### 8. `Entrada`
**Redactar (Compose)** · Entradas:
```
{"texto": "@trim(coalesce(triggerBody()?['text'],''))", "usuario": "@trim(coalesce(triggerBody()?['text_1'],''))"}
```

#### 9. `Inicializar_varT0`
**Inicializar variable** · Nombre: `varT0` · Tipo: `integer` · Valor: `"@ticks(utcNow())"`

#### 10. `Inicializar_varEtapa`
**Inicializar variable** · Nombre: `varEtapa` · Tipo: `string` · Valor: `"ENTRADA"`

#### 11. `Inicializar_varFallidas`
**Inicializar variable** · Nombre: `varFallidas` · Tipo: `array` · Valor: `[]`

#### 12. `Inicializar_varTotal`
**Inicializar variable** · Nombre: `varTotal` · Tipo: `integer` · Valor: `0`

#### 13. `Inicializar_varProcesadas`
**Inicializar variable** · Nombre: `varProcesadas` · Tipo: `integer` · Valor: `0`

#### 14. `Inicializar_varConfirmadas`
**Inicializar variable** · Nombre: `varConfirmadas` · Tipo: `integer` · Valor: `0`

#### 15. `Inicializar_varNoConfirmadas`
**Inicializar variable** · Nombre: `varNoConfirmadas` · Tipo: `integer` · Valor: `0`

#### 16. `Inicializar_varUid`
**Inicializar variable** · Nombre: `varUid` · Tipo: `string` · Valor: `""`

#### 17. `Inicializar_varEstadoId`
**Inicializar variable** · Nombre: `varEstadoId` · Tipo: `string` · Valor: `""`

#### 18. `Inicializar_varErrorCodigo`
**Inicializar variable** · Nombre: `varErrorCodigo` · Tipo: `string` · Valor: `""`

#### 19. `Inicializar_varErrorMensaje`
**Inicializar variable** · Nombre: `varErrorMensaje` · Tipo: `string` · Valor: `""`

#### 20. `Validar_entrada`
**Redactar (Compose)** · Entradas:
```
if(or(empty(outputs('Entrada')?['texto']),empty(outputs('Entrada')?['usuario']),greater(length(outputs('Entrada')?['usuario']),255),not(startsWith(outputs('Entrada')?['texto'],'['))),'ENTRADA_INVALIDA','')
```

#### 21. `PREPARAR`
**Ámbito (Scope)** · se ejecuta después de: `{"Validar_entrada": ["Succeeded"]}`

> **Dentro de `PREPARAR`:**


> #### 22. `Entrada_valida`
> **Condición (Condition)** · modo avanzado, expresión:
```
empty(outputs('Validar_entrada'))
```

> > **Rama Sí (True) de `Entrada_valida`:**


> > #### 23. `Filas`
> > **Redactar (Compose)** · Entradas:
```
json(outputs('Entrada')?['texto'])
```

> > #### 24. `Total`
> > **Redactar (Compose)** · Entradas:
```
length(outputs('Filas'))
```

> > #### 25. `Guardar_total`
> > **Establecer variable (Set variable)** · Nombre: `varTotal` · Valor:
```
outputs('Total')
```

> > #### 26. `Validar_lote`
> > **Redactar (Compose)** · Entradas:
```
if(equals(outputs('Total'),0),'SIN_FILAS',if(greater(outputs('Total'),min(outputs('PARAM_MAX_FILAS_POR_LLAMADA'),outputs('PARAM_MAX_FILAS_ARCHIVO'))),'LOTE_EXCEDE_LIMITE',''))
```

> > #### 27. `Lote_valido`
> > **Condición (Condition)** · modo avanzado, expresión:
```
empty(outputs('Validar_lote'))
```

> > > **Rama Sí (True) de `Lote_valido`:**


> > > #### 28. `Etapa_estado`
> > > **Establecer variable (Set variable)** · Nombre: `varEtapa` · Valor:
```
ESTADO
```

> > > #### 29. `Generar_uid`
> > > **Redactar (Compose)** · Entradas:
```
guid()
```

> > > #### 30. `Guardar_uid`
> > > **Establecer variable (Set variable)** · Nombre: `varUid` · Valor:
```
string(outputs('Generar_uid'))
```

> > > #### 31. `Nombre_estado`
> > > **Redactar (Compose)** · Entradas:
```
concat('confirmacion_',variables('varUid'),'.json')
```

> > > #### 32. `Estado_inicial`
> > > **Redactar (Compose)** · Entradas:
```
{"execution_uid": "@variables('varUid')", "estado": "PROCESANDO", "codigo": "PROCESAMIENTO_INICIADO", "filas_totales": "@variables('varTotal')", "filas_procesadas": "@variables('varProcesadas')", "filas_confirmadas": "@variables('varConfirmadas')", "filas_no_confirmadas": "@variables('varNoConfirmadas')", "porcentaje": "@div(mul(100,variables('varProcesadas')),max(1,variables('varTotal')))", "mensaje": "Confirmación iniciada. Procesando los depósitos válidos.", "detalle_json": [], "detalle_truncado": false, "actualizado_utc": "@utcNow()", "tiempos_ms": "@concat('total=',string(div(sub(ticks(utcNow()),variables('varT0')),10000)),';filas=',string(variables('varTotal')),';ms_por_fila=',string(div(div(sub(ticks(utcNow()),variables('varT0')),10000),max(1,variables('varTotal')))))"}
```

> > > #### 33. `Crear_estado`
> > > **Crear archivo (Create file)** · conector **SharePoint** · Configuración → Directiva de reintentos: **Ninguna**. Campos:
> > > - Dirección del sitio:
```
outputs('PARAM_SITIO')
```
> > > - Ruta de acceso a la carpeta:
```
outputs('PARAM_CARPETA')
```
> > > - Nombre del archivo:
```
outputs('Nombre_estado')
```
> > > - Contenido del archivo (expresión):
```
string(outputs('Estado_inicial'))
```

> > > #### 34. `Guardar_id_estado`
> > > **Establecer variable (Set variable)** · Nombre: `varEstadoId` · Valor:
```
string(body('Crear_estado')?['Id'])
```

> > > **Rama No (False) de `Lote_valido`:**


> > > #### 35. `Error_de_lote`
> > > **Condición (Condition)** · modo avanzado, expresión:
```
equals(outputs('Validar_lote'),'SIN_FILAS')
```

> > > > **Rama Sí (True) de `Error_de_lote`:**


> > > > #### 36. `Sin_filas_codigo`
> > > > **Establecer variable (Set variable)** · Nombre: `varErrorCodigo` · Valor:
```
SIN_FILAS
```

> > > > #### 37. `Sin_filas_mensaje`
> > > > **Establecer variable (Set variable)** · Nombre: `varErrorMensaje` · Valor:
```
No hay filas VALIDO para confirmar. No se confirmó ningún depósito.
```

> > > > **Rama No (False) de `Error_de_lote`:**


> > > > #### 38. `Lote_excede_codigo`
> > > > **Establecer variable (Set variable)** · Nombre: `varErrorCodigo` · Valor:
```
LOTE_EXCEDE_LIMITE
```

> > > > #### 39. `Lote_excede_mensaje`
> > > > **Establecer variable (Set variable)** · Nombre: `varErrorMensaje` · Valor:
```
concat('Se enviaron ',string(outputs('Total')),' filas y el máximo por confirmación es ',string(min(outputs('PARAM_MAX_FILAS_POR_LLAMADA'),outputs('PARAM_MAX_FILAS_ARCHIVO'))),'. No se confirmó ningún depósito.')
```

> > **Rama No (False) de `Entrada_valida`:**


> > #### 40. `Entrada_invalida_codigo`
> > **Establecer variable (Set variable)** · Nombre: `varErrorCodigo` · Valor:
```
ENTRADA_INVALIDA
```

> > #### 41. `Entrada_invalida_mensaje`
> > **Establecer variable (Set variable)** · Nombre: `varErrorMensaje` · Valor:
```
Faltan detalle_json o usuario_email, o detalle_json no es un arreglo JSON. No se confirmó ningún depósito.
```

#### 42. `PREPARAR_CATCH`
**Ámbito (Scope)** · se ejecuta después de: `{"PREPARAR": ["Failed", "TimedOut"]}`

> **Dentro de `PREPARAR_CATCH`:**


> #### 43. `Clasificar_fallo`
> **Condición (Condition)** · modo avanzado, expresión:
```
equals(variables('varEtapa'),'ESTADO')
```

> > **Rama Sí (True) de `Clasificar_fallo`:**


> > #### 44. `Fallo_estado_codigo`
> > **Establecer variable (Set variable)** · Nombre: `varErrorCodigo` · Valor:
```
ERROR_ESTADO
```

> > #### 45. `Fallo_estado_mensaje`
> > **Establecer variable (Set variable)** · Nombre: `varErrorMensaje` · Valor:
```
No se pudo crear el registro de progreso en P9_MASIVA_TEMP. No se confirmó ningún depósito: vuelva a intentar.
```

> > **Rama No (False) de `Clasificar_fallo`:**


> > #### 46. `Fallo_entrada_codigo`
> > **Establecer variable (Set variable)** · Nombre: `varErrorCodigo` · Valor:
```
ENTRADA_INVALIDA
```

> > #### 47. `Fallo_entrada_mensaje`
> > **Establecer variable (Set variable)** · Nombre: `varErrorMensaje` · Valor:
```
detalle_json no es un arreglo JSON válido. No se confirmó ningún depósito.
```

#### 48. `RESPONDER`
**Condición (Condition)** · modo avanzado, expresión:
```
empty(variables('varErrorCodigo'))
```

> **Rama Sí (True) de `RESPONDER`:**


> #### 49. `Responder_aceptado`
> **Responder a una aplicación de PowerApps o a un flujo** · una salida de tipo **Texto** por cada fila (título → valor):
> - `resultado`:
```
ACEPTADO
```
> - `codigo`:
```
PROCESAMIENTO_INICIADO
```
> - `mensaje`:
```
concat('Confirmación iniciada: ',string(variables('varTotal')),' depósitos en proceso.')
```
> - `execution_uid`:
```
variables('varUid')
```
> - `filas_recibidas`:
```
string(variables('varTotal'))
```

> **Rama No (False) de `RESPONDER`:**


> #### 50. `Responder_error`
> **Responder a una aplicación de PowerApps o a un flujo** · una salida de tipo **Texto** por cada fila (título → valor):
> - `resultado`:
```
ERROR
```
> - `codigo`:
```
variables('varErrorCodigo')
```
> - `mensaje`:
```
variables('varErrorMensaje')
```
> - `execution_uid`:
```

```
> - `filas_recibidas`:
```
string(variables('varTotal'))
```

#### 51. `PROCESAR`
**Condición (Condition)** · modo avanzado, expresión:
```
empty(variables('varErrorCodigo'))
```

> **Rama Sí (True) de `PROCESAR`:**


> #### 52. `PROCESAR_PREPARACION`
> **Ámbito (Scope)**

> > **Dentro de `PROCESAR_PREPARACION`:**


> > #### 53. `Etapa_preparar`
> > **Establecer variable (Set variable)** · Nombre: `varEtapa` · Valor:
```
PREPARAR
```

> > #### 54. `Hoy_local`
> > **Redactar (Compose)** · Entradas:
```
convertTimeZone(utcNow(),'UTC','SA Western Standard Time','yyyy-MM-dd')
```

> > #### 55. `Desde_local`
> > **Redactar (Compose)** · Entradas:
```
formatDateTime(addToTime(concat(outputs('Hoy_local'),'T00:00:00Z'),-2,'Month'),'yyyy-MM-dd')
```

> > #### 56. `Filas_texto`
> > **Seleccionar (Select)** · De (From):
```
outputs('Filas')
```
> > Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> > - Clave `fila_excel`:
```
item()?['fila_excel']
```
> > - Clave `id_txt`:
```
trim(string(coalesce(item()?['deposito_id'],'')))
```
> > - Clave `clave`:
```
trim(string(coalesce(item()?['clave_transaccion'],'')))
```
> > - Clave `banco`:
```
trim(string(coalesce(item()?['banco'],'')))
```
> > - Clave `cuenta`:
```
trim(string(coalesce(item()?['cuenta_bancaria'],'')))
```
> > - Clave `codigo`:
```
trim(string(coalesce(item()?['codigo_asignacion'],'')))
```
> > - Clave `importe_txt`:
```
trim(string(coalesce(item()?['importe'],'')))
```
> > - Clave `moneda`:
```
toUpper(trim(string(coalesce(item()?['moneda'],''))))
```
> > - Clave `estudiante`:
```
trim(string(coalesce(item()?['estudiante'],'')))
```
> > - Clave `solicitado_por`:
```
trim(string(coalesce(item()?['solicitado_por'],'')))
```
> > - Clave `sede`:
```
trim(string(coalesce(item()?['sede'],'')))
```
> > - Clave `observacion`:
```
trim(string(coalesce(item()?['observacion'],'')))
```

> > #### 57. `Filas_formato`
> > **Seleccionar (Select)** · De (From):
```
body('Filas_texto')
```
> > Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> > - Clave `fila_excel`:
```
item()?['fila_excel']
```
> > - Clave `id_txt`:
```
item()?['id_txt']
```
> > - Clave `clave`:
```
item()?['clave']
```
> > - Clave `banco`:
```
item()?['banco']
```
> > - Clave `cuenta`:
```
item()?['cuenta']
```
> > - Clave `codigo`:
```
item()?['codigo']
```
> > - Clave `importe_txt`:
```
item()?['importe_txt']
```
> > - Clave `moneda`:
```
item()?['moneda']
```
> > - Clave `estudiante`:
```
item()?['estudiante']
```
> > - Clave `solicitado_por`:
```
item()?['solicitado_por']
```
> > - Clave `sede`:
```
item()?['sede']
```
> > - Clave `observacion`:
```
item()?['observacion']
```
> > - Clave `id_ok`:
```
and(not(empty(item()?['id_txt'])),lessOrEquals(length(item()?['id_txt']),9),equals(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(item()?['id_txt'],'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),''))
```
> > - Clave `formato_ok`:
```
and(not(empty(item()?['importe_txt'])),lessOrEquals(length(item()?['importe_txt']),15),or(equals(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(item()?['importe_txt'],'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),''),and(equals(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(item()?['importe_txt'],'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'.'),greater(indexOf(item()?['importe_txt'],'.'),0),less(indexOf(item()?['importe_txt'],'.'),sub(length(item()?['importe_txt']),1)),lessOrEquals(sub(length(item()?['importe_txt']),add(indexOf(item()?['importe_txt'],'.'),1)),2))))
```

> > #### 58. `Filas_validadas`
> > **Seleccionar (Select)** · De (From):
```
body('Filas_formato')
```
> > Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> > - Clave `fila_excel`:
```
item()?['fila_excel']
```
> > - Clave `id_txt`:
```
item()?['id_txt']
```
> > - Clave `clave`:
```
item()?['clave']
```
> > - Clave `banco`:
```
item()?['banco']
```
> > - Clave `cuenta`:
```
item()?['cuenta']
```
> > - Clave `codigo`:
```
item()?['codigo']
```
> > - Clave `importe_txt`:
```
item()?['importe_txt']
```
> > - Clave `moneda`:
```
item()?['moneda']
```
> > - Clave `estudiante`:
```
item()?['estudiante']
```
> > - Clave `solicitado_por`:
```
item()?['solicitado_por']
```
> > - Clave `sede`:
```
item()?['sede']
```
> > - Clave `observacion`:
```
item()?['observacion']
```
> > - Clave `id_ok`:
```
item()?['id_ok']
```
> > - Clave `formato_ok`:
```
item()?['formato_ok']
```
> > - Clave `centavos`:
```
if(item()?['formato_ok'],int(formatNumber(mul(float(item()?['importe_txt']),100),'0')),0)
```
> > - Clave `invalida`:
```
if(or(not(item()?['id_ok']),if(item()?['id_ok'],equals(int(item()?['id_txt']),0),false)),'ID_INVALIDO',if(or(empty(item()?['clave']),empty(item()?['banco']),empty(item()?['cuenta']),empty(item()?['codigo']),empty(item()?['moneda']),empty(item()?['estudiante']),empty(item()?['solicitado_por']),empty(item()?['sede'])),'CAMPOS_OBLIGATORIOS',if(or(greater(length(item()?['clave']),255),greater(length(item()?['banco']),255),greater(length(item()?['cuenta']),255),greater(length(item()?['codigo']),255),greater(length(item()?['moneda']),255),greater(length(item()?['estudiante']),255),greater(length(item()?['solicitado_por']),255),greater(length(item()?['sede']),255),greater(length(item()?['observacion']),255)),'CAMPO_EXCEDE_255',if(not(item()?['formato_ok']),'IMPORTE_INVALIDO',if(equals(int(formatNumber(mul(float(item()?['importe_txt']),100),'0')),0),'IMPORTE_INVALIDO',if(not(or(equals(item()?['moneda'],'BOB'),equals(item()?['moneda'],'USD'))),'MONEDA_INVALIDA',''))))))
```

> > #### 59. `Filas_a_procesar`
> > **Filtrar matriz (Filter array)** · De (From):
```
body('Filas_validadas')
```
> > Condición (modo avanzado, expresión):
```
empty(item()?['invalida'])
```

> > #### 60. `Filas_invalidas`
> > **Filtrar matriz (Filter array)** · De (From):
```
body('Filas_validadas')
```
> > Condición (modo avanzado, expresión):
```
not(empty(item()?['invalida']))
```

> > #### 61. `Resultados_invalidas`
> > **Seleccionar (Select)** · De (From):
```
body('Filas_invalidas')
```
> > Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> > - Clave `fila_excel`:
```
item()?['fila_excel']
```
> > - Clave `deposito_id`:
```
if(item()?['id_ok'],int(item()?['id_txt']),null)
```
> > - Clave `resultado`:
```
ERROR_FILA
```
> > - Clave `mensaje`:
```
concat('Fila inválida en los datos enviados (',item()?['invalida'],'). No se aplicó ningún cambio.')
```
> > - Clave `estado_final`:
```

```
> > - Clave `banco`:
```
item()?['banco']
```
> > - Clave `cuenta_bancaria`:
```
item()?['cuenta']
```
> > - Clave `codigo_asignacion`:
```
item()?['codigo']
```
> > - Clave `importe`:
```
if(item()?['formato_ok'],div(float(item()?['centavos']),100.0),null)
```
> > - Clave `moneda`:
```
item()?['moneda']
```

> > #### 62. `Cargar_invalidas`
> > **Establecer variable (Set variable)** · Nombre: `varFallidas` · Valor:
```
body('Resultados_invalidas')
```

> > #### 63. `Contar_invalidas_no_confirmadas`
> > **Establecer variable (Set variable)** · Nombre: `varNoConfirmadas` · Valor:
```
length(body('Resultados_invalidas'))
```

> > #### 64. `Contar_invalidas_procesadas`
> > **Establecer variable (Set variable)** · Nombre: `varProcesadas` · Valor:
```
length(body('Resultados_invalidas'))
```

> > #### 65. `Etapa_confirmar`
> > **Establecer variable (Set variable)** · Nombre: `varEtapa` · Valor:
```
CONFIRMAR
```

> #### 66. `PROCESAR_PREPARACION_CATCH`
> **Ámbito (Scope)** · se ejecuta después de: `{"PROCESAR_PREPARACION": ["Failed", "TimedOut"]}`

> > **Dentro de `PROCESAR_PREPARACION_CATCH`:**


> > #### 67. `Fallo_global_codigo`
> > **Establecer variable (Set variable)** · Nombre: `varErrorCodigo` · Valor:
```
ERROR_NO_CONTROLADO
```

> > #### 68. `Fallo_global_mensaje`
> > **Establecer variable (Set variable)** · Nombre: `varErrorMensaje` · Valor:
```
El proceso se interrumpió antes de terminar: algunos depósitos pueden haberse confirmado. Vuelva a PREVALIDAR para ver el estado real de cada uno antes de reintentar.
```

> #### 69. `Para_cada_fila`
> **Aplicar a cada uno (Apply to each)** · Seleccione una salida de los pasos anteriores:
```
body('Filas_a_procesar')
```
> Configuración (⋯) → **Control de simultaneidad: Activado, grado de paralelismo = 1** (secuencial).

> > **Dentro de `Para_cada_fila`:**


> > #### 70. `TRY_FILA`
> > **Ámbito (Scope)**

> > > **Dentro de `TRY_FILA`:**


> > > #### 71. `Leer_deposito`
> > > **Enviar una solicitud HTTP a SharePoint** · Dirección del sitio: `@outputs('PARAM_SITIO')` (la misma de `PARAM_SITIO`) · Método: `GET` · Encabezados: `{"Accept": "application/json;odata=verbose"}` · Configuración → Directiva de reintentos: **Intervalo fijo, 2 reintentos, PT5S**. Uri (expresión):
```
concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')','/items(',items('Para_cada_fila')?['id_txt'],')?$select=Id,CLAVE_TRANSACCION,ESTADO_ASIGNACION,TIPO_MOVIMIENTO,FECHA_MOVIMIENTO,BANCO,CUENTA_BANCARIA,CODIGO_ASIGNACION,IMPORTE,MONEDA,USUARIO_ASIGNACION,FECHA_HORA_ASIGNACION')
```

> > > #### 72. `Cambio`
> > > **Redactar (Compose)** · Entradas:
```
if(not(equals(string(coalesce(body('Leer_deposito')?['d']?['Id'],body('Leer_deposito')?['d']?['ID'],0)),items('Para_cada_fila')?['id_txt'])),'ID',if(not(equals(trim(string(coalesce(body('Leer_deposito')?['d']?['CLAVE_TRANSACCION'],''))),items('Para_cada_fila')?['clave'])),'CLAVE_TRANSACCION',if(not(equals(trim(string(coalesce(body('Leer_deposito')?['d']?['ESTADO_ASIGNACION'],''))),'DISPONIBLE')),'ESTADO_ASIGNACION',if(not(equals(trim(string(coalesce(body('Leer_deposito')?['d']?['TIPO_MOVIMIENTO'],''))),'CRÉDITO')),'TIPO_MOVIMIENTO',if(or(less(take(string(coalesce(body('Leer_deposito')?['d']?['FECHA_MOVIMIENTO'],'')),10),outputs('Desde_local')),greater(take(string(coalesce(body('Leer_deposito')?['d']?['FECHA_MOVIMIENTO'],'')),10),outputs('Hoy_local'))),'FECHA_MOVIMIENTO',if(not(equals(toLower(trim(string(coalesce(body('Leer_deposito')?['d']?['BANCO'],'')))),toLower(items('Para_cada_fila')?['banco']))),'BANCO',if(not(equals(toLower(trim(string(coalesce(body('Leer_deposito')?['d']?['CUENTA_BANCARIA'],'')))),toLower(items('Para_cada_fila')?['cuenta']))),'CUENTA_BANCARIA',if(not(equals(toLower(trim(string(coalesce(body('Leer_deposito')?['d']?['CODIGO_ASIGNACION'],'')))),toLower(items('Para_cada_fila')?['codigo']))),'CODIGO_ASIGNACION',if(not(equals(int(formatNumber(mul(float(string(coalesce(body('Leer_deposito')?['d']?['IMPORTE'],0))),100),'0')),items('Para_cada_fila')?['centavos'])),'IMPORTE',if(not(equals(toUpper(trim(string(coalesce(body('Leer_deposito')?['d']?['MONEDA'],'')))),items('Para_cada_fila')?['moneda'])),'MONEDA',''))))))))))
```

> > > #### 73. `ETag_fresco`
> > > **Redactar (Compose)** · Entradas:
```
coalesce(body('Leer_deposito')?['d']?['__metadata']?['etag'],outputs('Leer_deposito')?['headers']?['ETag'],'')
```

> > > #### 74. `Revalidacion`
> > > **Redactar (Compose)** · Entradas:
```
{"codigo": "@if(empty(outputs('Cambio')),if(empty(outputs('ETag_fresco')),'ERROR_FILA','OK'),if(equals(outputs('Cambio'),'ESTADO_ASIGNACION'),'NO_DISPONIBLE','CONFLICTO_DATOS'))", "campo": "@outputs('Cambio')", "estado": "@trim(string(coalesce(body('Leer_deposito')?['d']?['ESTADO_ASIGNACION'],'')))", "etag": "@outputs('ETag_fresco')"}
```

> > > #### 75. `Puede_confirmar`
> > > **Condición (Condition)** · modo avanzado, expresión:
```
equals(outputs('Revalidacion')?['codigo'],'OK')
```

> > > > **Rama Sí (True) de `Puede_confirmar`:**


> > > > #### 76. `Cuerpo_actualizacion`
> > > > **Redactar (Compose)** · Entradas:
```
{"ESTADO_ASIGNACION": "ASIGNADO", "ESTUDIANTE": "@items('Para_cada_fila')?['estudiante']", "CODIGO_ESTUDIANTE": "", "SOLICITADO_POR": "@items('Para_cada_fila')?['solicitado_por']", "SEDE_ASIGNACION": "@items('Para_cada_fila')?['sede']", "OBSERVACION": "@items('Para_cada_fila')?['observacion']", "USUARIO_ASIGNACION": "@outputs('Entrada')?['usuario']", "FECHA_HORA_ASIGNACION": "@utcNow()"}
```

> > > > #### 77. `Actualizar_deposito`
> > > > **Enviar una solicitud HTTP a SharePoint** · Dirección del sitio: `@outputs('PARAM_SITIO')` (la misma de `PARAM_SITIO`) · Método: `POST` · Encabezados: `{"Accept": "application/json;odata=nometadata", "Content-Type": "application/json;odata=nometadata", "X-HTTP-Method": "MERGE", "IF-MATCH": "@outputs('Revalidacion')?['etag']"}` · Configuración → Directiva de reintentos: **Ninguna**. Uri (expresión):
```
concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')','/items(',items('Para_cada_fila')?['id_txt'],')')
```

> > > > #### 78. `Sumar_confirmada`
> > > > **Incrementar variable (Increment variable)** · Nombre: `varConfirmadas` · Valor: `1`

> > > > **Rama No (False) de `Puede_confirmar`:**


> > > > #### 79. `Agregar_no_confirmado`
> > > > **Anexar a variable de matriz (Append to array variable)** · Nombre: `varFallidas` · Valor (objeto; cada propiedad es una expresión o un texto fijo):
> > > > - Propiedad `fila_excel`:
```
items('Para_cada_fila')?['fila_excel']
```
> > > > - Propiedad `deposito_id`:
```
int(items('Para_cada_fila')?['id_txt'])
```
> > > > - Propiedad `resultado`:
```
outputs('Revalidacion')?['codigo']
```
> > > > - Propiedad `mensaje`:
```
if(equals(outputs('Revalidacion')?['codigo'],'NO_DISPONIBLE'),concat('El depósito ya no está DISPONIBLE (estado actual: ',outputs('Revalidacion')?['estado'],'). No se aplicó ningún cambio.'),if(equals(outputs('Revalidacion')?['codigo'],'CONFLICTO_DATOS'),concat('El depósito cambió desde la prevalidación (',outputs('Revalidacion')?['campo'],'). No se aplicó ningún cambio.'),'SharePoint no devolvió el ETag del depósito; no se aplicó ningún cambio.'))
```
> > > > - Propiedad `estado_final`:
```
outputs('Revalidacion')?['estado']
```
> > > > - Propiedad `banco`:
```
items('Para_cada_fila')?['banco']
```
> > > > - Propiedad `cuenta_bancaria`:
```
items('Para_cada_fila')?['cuenta']
```
> > > > - Propiedad `codigo_asignacion`:
```
items('Para_cada_fila')?['codigo']
```
> > > > - Propiedad `importe`:
```
div(float(items('Para_cada_fila')?['centavos']),100.0)
```
> > > > - Propiedad `moneda`:
```
items('Para_cada_fila')?['moneda']
```

> > > > #### 80. `Sumar_no_confirmada`
> > > > **Incrementar variable (Increment variable)** · Nombre: `varNoConfirmadas` · Valor: `1`

> > #### 81. `CATCH_FILA`
> > **Ámbito (Scope)** · se ejecuta después de: `{"TRY_FILA": ["Failed", "TimedOut"]}`

> > > **Dentro de `CATCH_FILA`:**


> > > #### 82. `Agregar_error_fila`
> > > **Anexar a variable de matriz (Append to array variable)** · Nombre: `varFallidas` · Valor (objeto; cada propiedad es una expresión o un texto fijo):
> > > - Propiedad `fila_excel`:
```
items('Para_cada_fila')?['fila_excel']
```
> > > - Propiedad `deposito_id`:
```
int(items('Para_cada_fila')?['id_txt'])
```
> > > - Propiedad `resultado`:
```
if(and(equals(actions('Actualizar_deposito')?['status'],'Failed'),equals(outputs('Actualizar_deposito')?['statusCode'],412)),'CONFLICTO',if(equals(actions('Actualizar_deposito')?['status'],'Failed'),'ERROR_FILA',if(and(equals(actions('Leer_deposito')?['status'],'Failed'),equals(outputs('Leer_deposito')?['statusCode'],404)),'NO_ENCONTRADO','ERROR_FILA')))
```
> > > - Propiedad `mensaje`:
```
if(and(equals(actions('Actualizar_deposito')?['status'],'Failed'),equals(outputs('Actualizar_deposito')?['statusCode'],412)),'Otro usuario modificó el depósito mientras se confirmaba. No se aplicó tu confirmación.',if(equals(actions('Actualizar_deposito')?['status'],'Failed'),concat('No se pudo confirmar el depósito (HTTP ',string(outputs('Actualizar_deposito')?['statusCode']),'). Verifique su estado con PREVALIDAR antes de reintentar.'),if(and(equals(actions('Leer_deposito')?['status'],'Failed'),equals(outputs('Leer_deposito')?['statusCode'],404)),'El depósito ya no existe en SharePoint. No se aplicó ningún cambio.',if(equals(actions('Leer_deposito')?['status'],'Failed'),concat('No se pudo leer el depósito (HTTP ',string(outputs('Leer_deposito')?['statusCode']),'). No se aplicó ningún cambio.'),'Error inesperado al procesar la fila. Verifique el depósito con PREVALIDAR antes de reintentar.'))))
```
> > > - Propiedad `estado_final`:
```
if(and(equals(actions('Actualizar_deposito')?['status'],'Failed'),not(equals(outputs('Actualizar_deposito')?['statusCode'],412))),'DESCONOCIDO','')
```
> > > - Propiedad `banco`:
```
items('Para_cada_fila')?['banco']
```
> > > - Propiedad `cuenta_bancaria`:
```
items('Para_cada_fila')?['cuenta']
```
> > > - Propiedad `codigo_asignacion`:
```
items('Para_cada_fila')?['codigo']
```
> > > - Propiedad `importe`:
```
div(float(items('Para_cada_fila')?['centavos']),100.0)
```
> > > - Propiedad `moneda`:
```
items('Para_cada_fila')?['moneda']
```

> > > #### 83. `Sumar_error_fila`
> > > **Incrementar variable (Increment variable)** · Nombre: `varNoConfirmadas` · Valor: `1`

> > #### 84. `Contar_procesada`
> > **Incrementar variable (Increment variable)** · Nombre: `varProcesadas` · Valor: `1`

> > #### 85. `Progreso`
> > **Condición (Condition)** · modo avanzado, expresión:
```
equals(mod(variables('varProcesadas'),outputs('PARAM_INTERVALO_PROGRESO')),0)
```

> > > **Rama Sí (True) de `Progreso`:**


> > > #### 86. `Estado_progreso`
> > > **Redactar (Compose)** · Entradas:
```
{"execution_uid": "@variables('varUid')", "estado": "PROCESANDO", "codigo": "PROCESAMIENTO_INICIADO", "filas_totales": "@variables('varTotal')", "filas_procesadas": "@variables('varProcesadas')", "filas_confirmadas": "@variables('varConfirmadas')", "filas_no_confirmadas": "@variables('varNoConfirmadas')", "porcentaje": "@div(mul(100,variables('varProcesadas')),max(1,variables('varTotal')))", "mensaje": "@concat(string(variables('varProcesadas')),' de ',string(variables('varTotal')),' procesados.')", "detalle_json": [], "detalle_truncado": false, "actualizado_utc": "@utcNow()", "tiempos_ms": "@concat('total=',string(div(sub(ticks(utcNow()),variables('varT0')),10000)),';filas=',string(variables('varTotal')),';ms_por_fila=',string(div(div(sub(ticks(utcNow()),variables('varT0')),10000),max(1,variables('varTotal')))))"}
```

> > > #### 87. `Escribir_progreso`
> > > **Actualizar archivo (Update file)** · conector **SharePoint** · Configuración → Directiva de reintentos: **Intervalo fijo, 2 reintentos, PT5S**. Campos:
> > > - Dirección del sitio:
```
outputs('PARAM_SITIO')
```
> > > - Identificador del archivo:
```
variables('varEstadoId')
```
> > > - Contenido del archivo (expresión):
```
string(outputs('Estado_progreso'))
```

> #### 88. `FINALIZAR`
> **Ámbito (Scope)** · se ejecuta después de: `{"Para_cada_fila": ["Succeeded", "Failed", "Skipped", "TimedOut"], "PROCESAR_PREPARACION_CATCH": ["Succeeded", "Failed", "Skipped", "TimedOut"]}`

> > **Dentro de `FINALIZAR`:**


> > #### 89. `Estado_final`
> > **Redactar (Compose)** · Entradas:
```
{"execution_uid": "@variables('varUid')", "estado": "@if(not(empty(variables('varErrorCodigo'))),'ERROR','TERMINADO')", "codigo": "@if(not(empty(variables('varErrorCodigo'))),variables('varErrorCodigo'),if(equals(variables('varNoConfirmadas'),0),'CONFIRMACION_OK',if(equals(variables('varConfirmadas'),0),'NINGUNA_CONFIRMADA','CONFIRMACION_PARCIAL')))", "filas_totales": "@variables('varTotal')", "filas_procesadas": "@variables('varProcesadas')", "filas_confirmadas": "@variables('varConfirmadas')", "filas_no_confirmadas": "@variables('varNoConfirmadas')", "porcentaje": "@if(not(empty(variables('varErrorCodigo'))),div(mul(100,variables('varProcesadas')),max(1,variables('varTotal'))),100)", "mensaje": "@if(not(empty(variables('varErrorCodigo'))),variables('varErrorMensaje'),concat(string(variables('varConfirmadas')),' de ',string(variables('varTotal')),' depósitos confirmados',if(equals(variables('varNoConfirmadas'),0),'.',concat('; ',string(variables('varNoConfirmadas')),' requieren revisión.'))))", "detalle_json": "@take(variables('varFallidas'),outputs('PARAM_MAX_DETALLE'))", "detalle_truncado": "@greater(length(variables('varFallidas')),outputs('PARAM_MAX_DETALLE'))", "actualizado_utc": "@utcNow()", "tiempos_ms": "@concat('total=',string(div(sub(ticks(utcNow()),variables('varT0')),10000)),';filas=',string(variables('varTotal')),';ms_por_fila=',string(div(div(sub(ticks(utcNow()),variables('varT0')),10000),max(1,variables('varTotal')))))"}
```

> > #### 90. `ESCRIBIR_FINAL`
> > **Ámbito (Scope)** · se ejecuta después de: `{"Estado_final": ["Succeeded"]}`

> > > **Dentro de `ESCRIBIR_FINAL`:**


> > > #### 91. `Escribir_final`
> > > **Actualizar archivo (Update file)** · conector **SharePoint** · Configuración → Directiva de reintentos: **Intervalo fijo, 2 reintentos, PT5S**. Campos:
> > > - Dirección del sitio:
```
outputs('PARAM_SITIO')
```
> > > - Identificador del archivo:
```
variables('varEstadoId')
```
> > > - Contenido del archivo (expresión):
```
string(outputs('Estado_final'))
```

> > #### 92. `ESCRIBIR_FINAL_RESPALDO`
> > **Ámbito (Scope)** · se ejecuta después de: `{"ESCRIBIR_FINAL": ["Failed", "TimedOut"]}`

> > > **Dentro de `ESCRIBIR_FINAL_RESPALDO`:**


> > > #### 93. `Estado_final_minimo`
> > > **Redactar (Compose)** · Entradas:
```
{"execution_uid": "@variables('varUid')", "estado": "@if(not(empty(variables('varErrorCodigo'))),'ERROR','TERMINADO')", "codigo": "@if(not(empty(variables('varErrorCodigo'))),variables('varErrorCodigo'),if(equals(variables('varNoConfirmadas'),0),'CONFIRMACION_OK',if(equals(variables('varConfirmadas'),0),'NINGUNA_CONFIRMADA','CONFIRMACION_PARCIAL')))", "filas_totales": "@variables('varTotal')", "filas_procesadas": "@variables('varProcesadas')", "filas_confirmadas": "@variables('varConfirmadas')", "filas_no_confirmadas": "@variables('varNoConfirmadas')", "porcentaje": "@if(not(empty(variables('varErrorCodigo'))),div(mul(100,variables('varProcesadas')),max(1,variables('varTotal'))),100)", "mensaje": "@concat(concat(string(variables('varConfirmadas')),' de ',string(variables('varTotal')),' depósitos confirmados',if(equals(variables('varNoConfirmadas'),0),'.',concat('; ',string(variables('varNoConfirmadas')),' requieren revisión.'))),' El detalle de las filas no confirmadas no se pudo guardar: vuelva a PREVALIDAR para verlas.')", "detalle_json": [], "detalle_truncado": true, "actualizado_utc": "@utcNow()", "tiempos_ms": "@concat('total=',string(div(sub(ticks(utcNow()),variables('varT0')),10000)),';filas=',string(variables('varTotal')),';ms_por_fila=',string(div(div(sub(ticks(utcNow()),variables('varT0')),10000),max(1,variables('varTotal')))))"}
```

> > > #### 94. `Escribir_final_minimo`
> > > **Actualizar archivo (Update file)** · conector **SharePoint** · Configuración → Directiva de reintentos: **Intervalo fijo, 2 reintentos, PT5S**. Campos:
> > > - Dirección del sitio:
```
outputs('PARAM_SITIO')
```
> > > - Identificador del archivo:
```
variables('varEstadoId')
```
> > > - Contenido del archivo (expresión):
```
string(outputs('Estado_final_minimo'))
```
