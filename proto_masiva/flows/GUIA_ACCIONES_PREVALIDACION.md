# Guía de acciones de la PREVALIDACIÓN REAL (opción B: armarlo a mano)

> **Úsala solo si no puedes importar el ZIP** (`ACTUALIZAR_FLUJO_PREVALIDACION.md`, opción A). Se **genera** desde la misma definición que el ZIP
> (`python proto_masiva/flows/guia_manual.py`), así que las expresiones son idénticas. **No está validada en el tenant**: son las expresiones que
> pasan las pruebas locales (tenant simulado), no se han ejecutado en Power Automate.
>
> En el diseñador, cada expresión se pega en la pestaña **Expresión** del campo (sin el `@` inicial). Los nombres de las acciones son los que
> aparecen aquí: **respétalos exactamente** (las expresiones se refieren unas a otras por nombre; si renombras una acción, el diseñador reescribe las
> referencias, pero el resto de este documento ya no coincidirá).

## Parte 1 · Al inicio del flujo, después de `PARAM_MAX_FILAS` y entre las variables existentes

Añade, **en este orden**, justo debajo de `PARAM_MAX_FILAS` los dos `Redactar` y, junto a las demás `Inicializar variable`, las siete variables nuevas.


#### 1. `PARAM_LISTA_DEPOSITOS_ACTIVOS`
**Redactar (Compose)** · Entradas:
```
296c450a-25d6-415b-ad10-c909c74817cb
```

#### 2. `PARAM_TOPE_DEPOSITOS`
**Redactar (Compose)** · Entradas:
```
5000
```

#### 3. `Inicializar_varT5` · **Inicializar variable** · Nombre: `varT5` · Tipo: `integer` · Valor: `0`

#### 4. `Inicializar_varT6` · **Inicializar variable** · Nombre: `varT6` · Tipo: `integer` · Valor: `0`

#### 5. `Inicializar_varTotales` · **Inicializar variable** · Nombre: `varTotales` · Tipo: `string` · Valor: `"0"`

#### 6. `Inicializar_varValidas` · **Inicializar variable** · Nombre: `varValidas` · Tipo: `string` · Valor: `"0"`

#### 7. `Inicializar_varConError` · **Inicializar variable** · Nombre: `varConError` · Tipo: `string` · Valor: `"0"`

#### 8. `Inicializar_varUniverso` · **Inicializar variable** · Nombre: `varUniverso` · Tipo: `string` · Valor: `"0"`

#### 9. `Inicializar_varDetalle` · **Inicializar variable** · Nombre: `varDetalle` · Tipo: `string` · Valor: `"[]"`


## Parte 2 · El bloque nuevo (reemplaza a la acción `Resultado_OK`)

**Dónde:** `TRY` → condición `Entrada_valida` (Sí) → `Hay_filas` (Sí) → `Limite_de_lectura` (No) → `Estructura` (No) → `Hay_datos` (Sí) →
`Hay_tope` (**rama No**). En esa rama hoy hay UNA acción: `Resultado_OK`. **Bórrala** y añade, **en este orden y una debajo de otra**, las acciones siguientes.
Las dos acciones finales de la condición `Universo_completo` van **dentro de sus ramas**.


#### 1. `Marca_T5`
**Establecer variable (Set variable)** · Nombre: `varT5` · Valor:
```
ticks(utcNow())
```

#### 2. `Etapa_filas`
**Establecer variable (Set variable)** · Nombre: `varEtapa` · Valor:
```
VALIDACION
```

#### 3. `Filas_con_posicion`
**Seleccionar (Select)** · De (From):
```
range(0,length(outputs('Filas_brutas')))
```
Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
- Clave `n`:
```
add(item(),1)
```
- Clave `f`:
```
outputs('Filas_brutas')?[item()]
```

#### 4. `Filas_texto`
**Seleccionar (Select)** · De (From):
```
body('Filas_con_posicion')
```
Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
- Clave `fila_tabla`:
```
item()?['n']
```
- Clave `banco`:
```
trim(string(coalesce(item()?['f']?['BANCO'],'')))
```
- Clave `cuenta`:
```
trim(string(coalesce(item()?['f']?['CUENTA_BANCARIA'],'')))
```
- Clave `codigo`:
```
trim(string(coalesce(item()?['f']?['CODIGO_ASIGNACION'],'')))
```
- Clave `importe_txt`:
```
trim(string(coalesce(item()?['f']?['IMPORTE'],'')))
```
- Clave `moneda`:
```
toUpper(trim(string(coalesce(item()?['f']?['MONEDA'],''))))
```
- Clave `estudiante`:
```
trim(string(coalesce(item()?['f']?['ESTUDIANTE'],'')))
```
- Clave `solicitado_por`:
```
trim(string(coalesce(item()?['f']?['SOLICITADO_POR'],'')))
```
- Clave `sede`:
```
trim(string(coalesce(item()?['f']?['SEDE'],'')))
```
- Clave `observacion`:
```
trim(string(coalesce(item()?['f']?['OBSERVACION'],'')))
```

#### 5. `Filas_formato`
**Seleccionar (Select)** · De (From):
```
body('Filas_texto')
```
Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
- Clave `fila_tabla`:
```
item()?['fila_tabla']
```
- Clave `banco`:
```
item()?['banco']
```
- Clave `cuenta`:
```
item()?['cuenta']
```
- Clave `codigo`:
```
item()?['codigo']
```
- Clave `importe_txt`:
```
item()?['importe_txt']
```
- Clave `moneda`:
```
item()?['moneda']
```
- Clave `estudiante`:
```
item()?['estudiante']
```
- Clave `solicitado_por`:
```
item()?['solicitado_por']
```
- Clave `sede`:
```
item()?['sede']
```
- Clave `observacion`:
```
item()?['observacion']
```
- Clave `faltan`:
```
concat(if(empty(item()?['banco']),'BANCO, ',''),if(empty(item()?['cuenta']),'CUENTA_BANCARIA, ',''),if(empty(item()?['codigo']),'CODIGO_ASIGNACION, ',''),if(empty(item()?['importe_txt']),'IMPORTE, ',''),if(empty(item()?['moneda']),'MONEDA, ',''),if(empty(item()?['estudiante']),'ESTUDIANTE, ',''),if(empty(item()?['solicitado_por']),'SOLICITADO_POR, ',''),if(empty(item()?['sede']),'SEDE, ',''))
```
- Clave `en_blanco`:
```
and(empty(item()?['banco']),empty(item()?['cuenta']),empty(item()?['codigo']),empty(item()?['importe_txt']),empty(item()?['moneda']),empty(item()?['estudiante']),empty(item()?['solicitado_por']),empty(item()?['sede']),empty(item()?['observacion']))
```
- Clave `formato_ok`:
```
and(not(empty(item()?['importe_txt'])),lessOrEquals(length(item()?['importe_txt']),15),or(equals(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(item()?['importe_txt'],'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),''),and(equals(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(item()?['importe_txt'],'0',''),'1',''),'2',''),'3',''),'4',''),'5',''),'6',''),'7',''),'8',''),'9',''),'.'),greater(indexOf(item()?['importe_txt'],'.'),0),less(indexOf(item()?['importe_txt'],'.'),sub(length(item()?['importe_txt']),1)),lessOrEquals(sub(length(item()?['importe_txt']),add(indexOf(item()?['importe_txt'],'.'),1)),2))))
```

#### 6. `Filas_calculo`
**Seleccionar (Select)** · De (From):
```
body('Filas_formato')
```
Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
- Clave `fila_tabla`:
```
item()?['fila_tabla']
```
- Clave `banco`:
```
item()?['banco']
```
- Clave `cuenta`:
```
item()?['cuenta']
```
- Clave `codigo`:
```
item()?['codigo']
```
- Clave `importe_txt`:
```
item()?['importe_txt']
```
- Clave `moneda`:
```
item()?['moneda']
```
- Clave `estudiante`:
```
item()?['estudiante']
```
- Clave `solicitado_por`:
```
item()?['solicitado_por']
```
- Clave `sede`:
```
item()?['sede']
```
- Clave `observacion`:
```
item()?['observacion']
```
- Clave `faltan`:
```
item()?['faltan']
```
- Clave `en_blanco`:
```
item()?['en_blanco']
```
- Clave `formato_ok`:
```
item()?['formato_ok']
```
- Clave `centavos`:
```
if(item()?['formato_ok'],int(formatNumber(mul(float(item()?['importe_txt']),100),'0')),0)
```
- Clave `importe_ok`:
```
if(item()?['formato_ok'],greater(int(formatNumber(mul(float(item()?['importe_txt']),100),'0')),0),false)
```
- Clave `moneda_ok`:
```
or(equals(item()?['moneda'],'BOB'),equals(item()?['moneda'],'USD'))
```
- Clave `incompleta`:
```
not(empty(item()?['faltan']))
```

#### 7. `Filas_calculadas`
**Seleccionar (Select)** · De (From):
```
body('Filas_calculo')
```
Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
- Clave `fila_tabla`:
```
item()?['fila_tabla']
```
- Clave `banco`:
```
item()?['banco']
```
- Clave `cuenta`:
```
item()?['cuenta']
```
- Clave `codigo`:
```
item()?['codigo']
```
- Clave `importe_txt`:
```
item()?['importe_txt']
```
- Clave `moneda`:
```
item()?['moneda']
```
- Clave `estudiante`:
```
item()?['estudiante']
```
- Clave `solicitado_por`:
```
item()?['solicitado_por']
```
- Clave `sede`:
```
item()?['sede']
```
- Clave `observacion`:
```
item()?['observacion']
```
- Clave `faltan`:
```
item()?['faltan']
```
- Clave `en_blanco`:
```
item()?['en_blanco']
```
- Clave `formato_ok`:
```
item()?['formato_ok']
```
- Clave `centavos`:
```
item()?['centavos']
```
- Clave `importe_ok`:
```
item()?['importe_ok']
```
- Clave `moneda_ok`:
```
item()?['moneda_ok']
```
- Clave `incompleta`:
```
item()?['incompleta']
```
- Clave `clave_ok`:
```
and(not(empty(item()?['banco'])),not(empty(item()?['cuenta'])),not(empty(item()?['codigo'])),item()?['importe_ok'])
```
- Clave `clave`:
```
if(and(not(empty(item()?['banco'])),not(empty(item()?['cuenta'])),not(empty(item()?['codigo'])),item()?['importe_ok']),concat(toLower(item()?['banco']),'¦',toLower(item()?['cuenta']),'¦',toLower(item()?['codigo']),'¦',string(item()?['centavos'])),'')
```

#### 8. `Filas_a_validar`
**Filtrar matriz (Filter array)** · De (From):
```
body('Filas_calculadas')
```
Condición (modo avanzado, expresión):
```
not(item()?['en_blanco'])
```

#### 9. `Marcas_clave`
**Seleccionar (Select)** · De (From):
```
body('Filas_a_validar')
```
Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
(Map en modo texto, una sola expresión):
```
if(item()?['clave_ok'],concat('§',item()?['clave'],'¶'),'')
```

#### 10. `Texto_claves`
**Redactar (Compose)** · Entradas:
```
join(body('Marcas_clave'),'')
```

#### 11. `Hoy_local`
**Redactar (Compose)** · Entradas:
```
convertTimeZone(utcNow(),'UTC','SA Western Standard Time','yyyy-MM-dd')
```

#### 12. `Desde_local`
**Redactar (Compose)** · Entradas:
```
formatDateTime(addToTime(concat(outputs('Hoy_local'),'T00:00:00Z'),-2,'Month'),'yyyy-MM-dd')
```

#### 13. `Etapa_depositos`
**Establecer variable (Set variable)** · Nombre: `varEtapa` · Valor:
```
DEPOSITOS
```

#### 14. `Leer_depositos`
**Enviar una solicitud HTTP a SharePoint** · Dirección del sitio: `@outputs('PARAM_SITIO')` (la misma de `PARAM_SITIO`) · Método: `GET` · Encabezados: `{"Accept": "application/json;odata=verbose"}` · Configuración → Directiva de reintentos: **Ninguna**. Uri (expresión):
```
concat('_api/web/lists(guid''',outputs('PARAM_LISTA_DEPOSITOS_ACTIVOS'),''')/items?$select=Id,CLAVE_TRANSACCION,BANCO,CUENTA_BANCARIA,CODIGO_ASIGNACION,IMPORTE,MONEDA,ESTADO_ASIGNACION,FECHA_MOVIMIENTO&$filter=TIPO_MOVIMIENTO eq ''CRÉDITO'' and FECHA_MOVIMIENTO ge datetime''',outputs('Desde_local'),'T00:00:00Z'' and FECHA_MOVIMIENTO le datetime''',outputs('Hoy_local'),'T00:00:00Z''&$top=',string(outputs('PARAM_TOPE_DEPOSITOS')))
```

#### 15. `Marca_T6`
**Establecer variable (Set variable)** · Nombre: `varT6` · Valor:
```
ticks(utcNow())
```

#### 16. `Depositos`
**Redactar (Compose)** · Entradas:
```
coalesce(body('Leer_depositos')?['d']?['results'],createArray())
```

#### 17. `Universo_completo`
**Condición (Condition)** · modo avanzado, expresión:
```
not(empty(body('Leer_depositos')?['d']?['__next']))
```

> **Rama Sí (True) de `Universo_completo`:**


> #### 18. `Resultado_DEPOSITOS_DEMASIADOS`
> **Establecer variable (Set variable)** · Nombre: `varResultado` · Valor:
```
{"estado": "ERROR", "codigo": "DEPOSITOS_DEMASIADOS", "mensaje": "@concat('Depositos_Activos devolvió más de ',string(outputs('PARAM_TOPE_DEPOSITOS')),' CRÉDITOS de los últimos 2 meses: el resultado podría estar incompleto. Avise al administrador.')", "tabla": "SI", "filas": "@outputs('Cantidad_con_datos')"}
```

> **Rama No (False) de `Universo_completo`:**


> #### 19. `Depositos_normalizados`
> **Seleccionar (Select)** · De (From):
```
outputs('Depositos')
```
> Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> (Map en modo texto, una sola expresión):
```
concat('§',concat(toLower(trim(string(coalesce(item()?['BANCO'],'')))),'¦',toLower(trim(string(coalesce(item()?['CUENTA_BANCARIA'],'')))),'¦',toLower(trim(string(coalesce(item()?['CODIGO_ASIGNACION'],'')))),'¦',string(int(formatNumber(mul(float(string(coalesce(item()?['IMPORTE'],0))),100),'0')))),'¶',string(item()?['Id']),'¦',trim(string(coalesce(item()?['CLAVE_TRANSACCION'],''))),'¦',trim(string(coalesce(item()?['ESTADO_ASIGNACION'],''))),'¦',toUpper(trim(string(coalesce(item()?['MONEDA'],'')))),'¦',take(trim(string(coalesce(item()?['FECHA_MOVIMIENTO'],''))),10),'¤')
```

> #### 20. `Indice_depositos`
> **Redactar (Compose)** · Entradas:
```
join(body('Depositos_normalizados'),'')
```

> #### 21. `Etapa_validacion_filas`
> **Establecer variable (Set variable)** · Nombre: `varEtapa` · Valor:
```
VALIDACION
```

> #### 22. `Filas_coincidencia`
> **Seleccionar (Select)** · De (From):
```
body('Filas_a_validar')
```
> Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> - Clave `fila_tabla`:
```
item()?['fila_tabla']
```
> - Clave `banco`:
```
item()?['banco']
```
> - Clave `cuenta`:
```
item()?['cuenta']
```
> - Clave `codigo`:
```
item()?['codigo']
```
> - Clave `importe_txt`:
```
item()?['importe_txt']
```
> - Clave `moneda`:
```
item()?['moneda']
```
> - Clave `estudiante`:
```
item()?['estudiante']
```
> - Clave `solicitado_por`:
```
item()?['solicitado_por']
```
> - Clave `sede`:
```
item()?['sede']
```
> - Clave `observacion`:
```
item()?['observacion']
```
> - Clave `faltan`:
```
item()?['faltan']
```
> - Clave `en_blanco`:
```
item()?['en_blanco']
```
> - Clave `formato_ok`:
```
item()?['formato_ok']
```
> - Clave `centavos`:
```
item()?['centavos']
```
> - Clave `importe_ok`:
```
item()?['importe_ok']
```
> - Clave `moneda_ok`:
```
item()?['moneda_ok']
```
> - Clave `incompleta`:
```
item()?['incompleta']
```
> - Clave `clave_ok`:
```
item()?['clave_ok']
```
> - Clave `clave`:
```
item()?['clave']
```
> - Clave `n_dup`:
```
if(item()?['clave_ok'],sub(length(split(outputs('Texto_claves'),concat('§',item()?['clave'],'¶'))),1),0)
```
> - Clave `n_dep`:
```
if(item()?['clave_ok'],sub(length(split(outputs('Indice_depositos'),concat('§',item()?['clave'],'¶'))),1),0)
```
> - Clave `dep`:
```
if(item()?['clave_ok'],if(equals(sub(length(split(outputs('Indice_depositos'),concat('§',item()?['clave'],'¶'))),1),1),first(split(last(split(outputs('Indice_depositos'),concat('§',item()?['clave'],'¶'))),'¤')),''),'')
```

> #### 23. `Filas_resultado`
> **Seleccionar (Select)** · De (From):
```
body('Filas_coincidencia')
```
> Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> - Clave `fila_tabla`:
```
item()?['fila_tabla']
```
> - Clave `banco`:
```
item()?['banco']
```
> - Clave `cuenta`:
```
item()?['cuenta']
```
> - Clave `codigo`:
```
item()?['codigo']
```
> - Clave `importe_txt`:
```
item()?['importe_txt']
```
> - Clave `moneda`:
```
item()?['moneda']
```
> - Clave `estudiante`:
```
item()?['estudiante']
```
> - Clave `solicitado_por`:
```
item()?['solicitado_por']
```
> - Clave `sede`:
```
item()?['sede']
```
> - Clave `observacion`:
```
item()?['observacion']
```
> - Clave `faltan`:
```
item()?['faltan']
```
> - Clave `en_blanco`:
```
item()?['en_blanco']
```
> - Clave `formato_ok`:
```
item()?['formato_ok']
```
> - Clave `centavos`:
```
item()?['centavos']
```
> - Clave `importe_ok`:
```
item()?['importe_ok']
```
> - Clave `moneda_ok`:
```
item()?['moneda_ok']
```
> - Clave `incompleta`:
```
item()?['incompleta']
```
> - Clave `clave_ok`:
```
item()?['clave_ok']
```
> - Clave `clave`:
```
item()?['clave']
```
> - Clave `n_dup`:
```
item()?['n_dup']
```
> - Clave `n_dep`:
```
item()?['n_dep']
```
> - Clave `dep`:
```
item()?['dep']
```
> - Clave `resultado`:
```
if(item()?['incompleta'],'FILA_INCOMPLETA',if(not(item()?['importe_ok']),'IMPORTE_INVALIDO',if(not(item()?['moneda_ok']),'MONEDA_INVALIDA',if(greater(item()?['n_dup'],1),'DUPLICADO_ARCHIVO',if(equals(item()?['n_dep'],0),'NO_ENCONTRADO',if(greater(item()?['n_dep'],1),'ASIGNACION_AMBIGUA',if(not(equals(split(item()?['dep'],'¦')[3],item()?['moneda'])),'MONEDA_NO_COINCIDE',if(not(equals(split(item()?['dep'],'¦')[2],'DISPONIBLE')),'NO_DISPONIBLE','VALIDO'))))))))
```
> - Clave `conoce`:
```
and(item()?['clave_ok'],item()?['moneda_ok'],not(item()?['incompleta']),less(item()?['n_dup'],2),equals(item()?['n_dep'],1))
```
> - Clave `dep_id`:
```
if(empty(item()?['dep']),'',split(item()?['dep'],'¦')[0])
```
> - Clave `dep_clave`:
```
if(empty(item()?['dep']),'',split(item()?['dep'],'¦')[1])
```
> - Clave `dep_estado`:
```
if(empty(item()?['dep']),'',split(item()?['dep'],'¦')[2])
```
> - Clave `dep_moneda`:
```
if(empty(item()?['dep']),'',split(item()?['dep'],'¦')[3])
```
> - Clave `dep_fecha`:
```
if(empty(item()?['dep']),'',split(item()?['dep'],'¦')[4])
```

> #### 24. `Detalle_filas`
> **Seleccionar (Select)** · De (From):
```
body('Filas_resultado')
```
> Asignar (Map) · modo clave-valor, una fila por clave; cada valor es una EXPRESIÓN:
> - Clave `fila_excel`:
```
add(item()?['fila_tabla'],5)
```
> - Clave `fila_tabla`:
```
item()?['fila_tabla']
```
> - Clave `resultado`:
```
item()?['resultado']
```
> - Clave `mensaje`:
```
if(equals(item()?['resultado'],'VALIDO'),concat('Depósito disponible encontrado (ID ',item()?['dep_id'],').'),if(equals(item()?['resultado'],'FILA_INCOMPLETA'),concat('Faltan datos obligatorios: ',take(item()?['faltan'],sub(length(item()?['faltan']),2)),'.'),if(equals(item()?['resultado'],'IMPORTE_INVALIDO'),'IMPORTE inválido: use un número mayor que 0, con punto decimal y como máximo 2 decimales.',if(equals(item()?['resultado'],'MONEDA_INVALIDA'),'MONEDA inválida: use BOB o USD.',if(equals(item()?['resultado'],'DUPLICADO_ARCHIVO'),concat('Hay ',string(item()?['n_dup']),' filas del archivo que apuntan al mismo depósito (BANCO + CUENTA + CÓDIGO + IMPORTE).'),if(equals(item()?['resultado'],'NO_ENCONTRADO'),'No hay un depósito CRÉDITO de los últimos 2 meses con ese BANCO, CUENTA, CÓDIGO e IMPORTE.',if(equals(item()?['resultado'],'ASIGNACION_AMBIGUA'),concat('Hay ',string(item()?['n_dep']),' depósitos con esa misma clave: no se puede elegir uno.'),if(equals(item()?['resultado'],'MONEDA_NO_COINCIDE'),concat('La moneda del Excel (',item()?['moneda'],') no coincide con la del depósito (',item()?['dep_moneda'],').'),concat('El depósito no está disponible para confirmar. Estado actual: ',item()?['dep_estado'],'.')))))))))
```
> - Clave `deposito_id`:
```
if(item()?['conoce'],int(item()?['dep_id']),null)
```
> - Clave `clave_transaccion`:
```
if(item()?['conoce'],item()?['dep_clave'],'')
```
> - Clave `estado_actual`:
```
if(item()?['conoce'],item()?['dep_estado'],'')
```
> - Clave `fecha_movimiento`:
```
if(item()?['conoce'],item()?['dep_fecha'],'')
```
> - Clave `moneda_deposito`:
```
if(item()?['conoce'],item()?['dep_moneda'],'')
```
> - Clave `coincidencias`:
```
item()?['n_dep']
```
> - Clave `banco`:
```
item()?['banco']
```
> - Clave `cuenta_bancaria`:
```
item()?['cuenta']
```
> - Clave `codigo_asignacion`:
```
item()?['codigo']
```
> - Clave `importe`:
```
if(item()?['importe_ok'],div(float(item()?['centavos']),100),null)
```
> - Clave `importe_original`:
```
item()?['importe_txt']
```
> - Clave `moneda`:
```
item()?['moneda']
```
> - Clave `estudiante`:
```
item()?['estudiante']
```
> - Clave `solicitado_por`:
```
item()?['solicitado_por']
```
> - Clave `sede`:
```
item()?['sede']
```
> - Clave `observacion`:
```
item()?['observacion']
```

> #### 25. `Filas_validas`
> **Filtrar matriz (Filter array)** · De (From):
```
body('Detalle_filas')
```
> Condición (modo avanzado, expresión):
```
equals(item()?['resultado'],'VALIDO')
```

> #### 26. `Cuenta_validas`
> **Redactar (Compose)** · Entradas:
```
length(body('Filas_validas'))
```

> #### 27. `Cuenta_total`
> **Redactar (Compose)** · Entradas:
```
length(body('Detalle_filas'))
```

> #### 28. `Guardar_totales`
> **Establecer variable (Set variable)** · Nombre: `varTotales` · Valor:
```
string(outputs('Cuenta_total'))
```

> #### 29. `Guardar_validas`
> **Establecer variable (Set variable)** · Nombre: `varValidas` · Valor:
```
string(outputs('Cuenta_validas'))
```

> #### 30. `Guardar_con_error`
> **Establecer variable (Set variable)** · Nombre: `varConError` · Valor:
```
string(sub(outputs('Cuenta_total'),outputs('Cuenta_validas')))
```

> #### 31. `Guardar_universo`
> **Establecer variable (Set variable)** · Nombre: `varUniverso` · Valor:
```
string(length(outputs('Depositos')))
```

> #### 32. `Guardar_detalle`
> **Establecer variable (Set variable)** · Nombre: `varDetalle` · Valor:
```
string(body('Detalle_filas'))
```

> #### 33. `Resultado_prevalidacion`
> **Establecer variable (Set variable)** · Nombre: `varResultado` · Valor:
```
{"estado": "@if(equals(outputs('Cuenta_validas'),outputs('Cuenta_total')),'OK','OBSERVADO')", "codigo": "@if(equals(outputs('Cuenta_validas'),outputs('Cuenta_total')),'PREVALIDACION_OK','PREVALIDACION_CON_ERRORES')", "mensaje": "@concat(string(outputs('Cuenta_validas')),' de ',string(outputs('Cuenta_total')),' filas válidas',if(equals(outputs('Cuenta_validas'),outputs('Cuenta_total')),'. ',concat('; ',string(sub(outputs('Cuenta_total'),outputs('Cuenta_validas'))),' con observaciones. ')),'Prevalidación de solo lectura: no se confirmó ningún depósito.')", "tabla": "SI", "filas": "@outputs('Cuenta_total')"}
```


## Parte 3 · Tres cambios en acciones que ya existen

### 3.1 · `Tiempos` (Redactar, al final del flujo) → reemplaza sus Entradas por:
```
concat('crear=',string(if(greater(variables('varT1'),0),div(sub(variables('varT1'),variables('varT0')),10000),0)),';excel=',string(if(greater(variables('varT5'),0),div(sub(variables('varT5'),variables('varT1')),10000),if(greater(variables('varT2'),0),div(sub(variables('varT2'),variables('varT1')),10000),0))),';depositos=',string(if(greater(variables('varT6'),0),div(sub(variables('varT6'),variables('varT5')),10000),0)),';borrar=',string(if(greater(variables('varT3'),0),div(sub(variables('varT3'),max(variables('varT2'),variables('varT1'),variables('varT0'))),10000),0)),';total=',string(div(sub(variables('varT4'),variables('varT0')),10000)))
```

### 3.2 · `CATCH` → `Clasificar_fallo` → rama No → `Fallo_no_excel` → rama No: hoy contiene `Fallo_ERROR_COPIA` (si la etapa es COPIA) y, si no, `Fallo_ERROR_NO_CONTROLADO`
Cambia el contenido de la **rama No de `Fallo_no_excel`** para que sea esta condición, con la acción antigua `Fallo_ERROR_NO_CONTROLADO` dentro de su rama No:
```
equals(variables('varEtapa'),'DEPOSITOS')
```
**Rama Sí:** `Fallo_ERROR_SHAREPOINT` · **Establecer variable** `varResultado` · Valor (objeto, modo texto):
```
{
 "estado": "ERROR",
 "codigo": "ERROR_SHAREPOINT",
 "mensaje": "@concat('No se pudo leer Depositos_Activos (HTTP ',string(outputs('Leer_depositos')?['statusCode']),'). Vuelva a intentar o avise al administrador.')",
 "tabla": "SI",
 "filas": 0
}
```

### 3.3 · `Responder_a_PowerApps` → añade 5 salidas de tipo **Texto** (después de `tiempos_ms`), una por una (*Agregar una salida → Texto*):

| Título de la salida | Valor (expresión) |
|---|---|
| `filas_totales` | `variables('varTotales')` |
| `filas_validas` | `variables('varValidas')` |
| `filas_con_error` | `variables('varConError')` |
| `depositos_consultados` | `variables('varUniverso')` |
| `detalle_json` | `variables('varDetalle')` |

