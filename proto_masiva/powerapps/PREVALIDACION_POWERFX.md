# Power Fx de la prevalidación real (colección `colPrevalidacionP9`)

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

### 1 · `btnPrevalidarP9` → propiedad **OnSelect** (reemplaza TODO el contenido)

```
=Set(varProcesandoP9; true);;
Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Clear(colPrevalidacionP9);;
With(
    {inicioP9: Now(); archivoP9: First(attXlsxP9.Attachments)};
    IfError(
        Set(varResultadoP9; P9_MASIVA_PROTO_PREVALIDAR.Run({name: archivoP9.Name; contentBytes: archivoP9.Value}));;
        Set(varMsAppP9; DateDiff(inicioP9; Now(); TimeUnit.Milliseconds));;
        IfError(
            ClearCollect(
                colPrevalidacionP9;
                ForAll(
                    Table(ParseJSON(varResultadoP9.detalle_json));
                    {
                        fila_excel: Value(ThisRecord.Value.fila_excel);
                        fila_tabla: Value(ThisRecord.Value.fila_tabla);
                        resultado: Text(ThisRecord.Value.resultado);
                        mensaje: Text(ThisRecord.Value.mensaje);
                        deposito_id: Value(ThisRecord.Value.deposito_id);
                        clave_transaccion: Text(ThisRecord.Value.clave_transaccion);
                        estado_actual: Text(ThisRecord.Value.estado_actual);
                        fecha_movimiento: Text(ThisRecord.Value.fecha_movimiento);
                        moneda_deposito: Text(ThisRecord.Value.moneda_deposito);
                        coincidencias: Value(ThisRecord.Value.coincidencias);
                        banco: Text(ThisRecord.Value.banco);
                        cuenta_bancaria: Text(ThisRecord.Value.cuenta_bancaria);
                        codigo_asignacion: Text(ThisRecord.Value.codigo_asignacion);
                        importe: Value(ThisRecord.Value.importe);
                        importe_original: Text(ThisRecord.Value.importe_original);
                        moneda: Text(ThisRecord.Value.moneda);
                        estudiante: Text(ThisRecord.Value.estudiante);
                        solicitado_por: Text(ThisRecord.Value.solicitado_por);
                        sede: Text(ThisRecord.Value.sede);
                        observacion: Text(ThisRecord.Value.observacion)
                    }
                )
            );
            Notify("No se pudo leer el detalle de la prevalidación: " & FirstError.Message; NotificationType.Warning)
        );
        Set(
            varResultadoP9;
            {
                resultado: "ERROR";
                codigo: "FLUJO_SIN_RESPUESTA";
                mensaje: "El flujo no respondió: " & FirstError.Message;
                archivo: archivoP9.Name;
                tabla_encontrada: "";
                filas_leidas: "0";
                copia_temporal_eliminada: "";
                tiempos_ms: "";
                filas_totales: "0";
                filas_validas: "0";
                filas_con_error: "0";
                depositos_consultados: "0";
                detalle_json: "[]"
            }
        );;
        Set(varMsAppP9; DateDiff(inicioP9; Now(); TimeUnit.Milliseconds))
    )
);;
Set(varProcesandoP9; false)
```

### 2 · `lblEstadoP9` → **Fill**

```
=With(
    {estadoP9: If(Coalesce(varProcesandoP9; false); "PROCESANDO"; If(!IsBlank(varResultadoP9); varResultadoP9.resultado; If(IsEmpty(attXlsxP9.Attachments); "SIN ARCHIVO"; "CARGADO")))};
    Switch(
        estadoP9;
        "OK"; RGBA(46; 125; 50; 1);
        "OBSERVADO"; RGBA(198; 125; 0; 1);
        "ERROR"; RGBA(183; 28; 28; 1);
        "PROCESANDO"; RGBA(230; 126; 34; 1);
        "CARGADO"; RGBA(0; 120; 212; 1);
        RGBA(98; 102; 106; 1)
    )
)
```

### 3 · `lblTitularResultadoP9` → **Text**

```
=If(
    Coalesce(varProcesandoP9; false);
    "Procesando el archivo (puede tardar unos segundos)...";
    If(
        IsBlank(varResultadoP9);
        If(IsEmpty(attXlsxP9.Attachments); "Adjunte un Excel (.xlsx) para empezar."; "Archivo seleccionado. Pulse PREVALIDAR ARCHIVO.");
        If(
            varResultadoP9.resultado = "OK" || varResultadoP9.resultado = "OBSERVADO";
            "PREVALIDACIÓN · " & varResultadoP9.filas_validas & " DE " & varResultadoP9.filas_totales & If(Value(varResultadoP9.filas_totales) = 1; " FILA VÁLIDA"; " FILAS VÁLIDAS");
            "RESULTADO: " & varResultadoP9.codigo
        )
    )
)
```

### 4 · `lblResFilasP9` → **Text**

```
=If(Coalesce(varResultadoP9.tabla_encontrada; "") = "SI"; varResultadoP9.filas_leidas; "—")
```

### 5 · `lblAvisoPrototipoP9` → **Text**

```
="PROTOTIPO · prevalidación de SOLO LECTURA (lee Depositos_Activos, no lo modifica y no confirma ningún depósito) · sin lotes ni historial."
```

## Usar la colección (sin galería bonita todavía)

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
