# Power Fx de la CONFIRMACIÓN MASIVA (botón `btnConfirmarMasivamenteP9`)

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

### A · Pantalla `P9_Confirmacion_Masiva` → propiedad **OnVisible**

```
=Set(varProcesandoP9; false);;
Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Set(varProcesandoConfirmacionP9; false);;
Set(varConfirmacionMasivaFinalizadaP9; false);;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varVerObservacionesP9; false);;
Clear(colPrevalidacionP9);;
Clear(colConfirmacionP9);;
ResetForm(frmArchivoP9)
```

### B · Control de adjuntos `attXlsxP9` → propiedades **OnAddFile** y **OnRemoveFile** (la misma fórmula en las dos)

```
=Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varConfirmacionMasivaFinalizadaP9; false);;
Set(varVerObservacionesP9; false);;
Clear(colPrevalidacionP9);;
Clear(colConfirmacionP9)
```

### C · `btnPrevalidarP9` → **DisplayMode**

```
=If(
    Coalesce(varProcesandoP9; false) ||
    Coalesce(varProcesandoConfirmacionP9; false) ||
    IsEmpty(attXlsxP9.Attachments) ||
    !EndsWith(Lower(First(attXlsxP9.Attachments).Name); ".xlsx");
    DisplayMode.Disabled;
    DisplayMode.Edit
)
```

### D · `btnPrevalidarP9` → **OnSelect** (añade el reinicio de la confirmación)

```
=Set(varProcesandoP9; true);;
Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varConfirmacionMasivaFinalizadaP9; false);;
Set(varVerObservacionesP9; false);;
Clear(colPrevalidacionP9);;
Clear(colConfirmacionP9);;
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

### E · `btnConfirmarMasivamenteP9` → **Text**

```
="CONFIRMAR MASIVAMENTE (" & CountRows(Filter(colPrevalidacionP9; resultado = "VALIDO")) & ")"
```

### F · `btnConfirmarMasivamenteP9` → **DisplayMode** (Disabled mientras corre y después de confirmar ese mismo resultado)

```
=If(
    !Coalesce(varProcesandoP9; false) &&
    !Coalesce(varProcesandoConfirmacionP9; false) &&
    !Coalesce(varConfirmacionMasivaFinalizadaP9; false) &&
    CountRows(Filter(colPrevalidacionP9; resultado = "VALIDO")) > 0;
    DisplayMode.Edit;
    DisplayMode.Disabled
)
```

### G · `btnConfirmarMasivamenteP9` → **OnSelect** (UN clic, sin segundo modal)

```
=Set(varProcesandoConfirmacionP9; true);;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varVerObservacionesP9; false);;
Clear(colConfirmacionP9);;
With(
    {inicioConfirmacionP9: Now()};
    IfError(
        Set(
            varResultadoConfirmacionP9;
            P9_MASIVA_PROTO_CONFIRMAR.Run(
                JSON(
                    ShowColumns(Filter(colPrevalidacionP9; resultado = "VALIDO"); "fila_excel"; "deposito_id"; "clave_transaccion"; "banco"; "cuenta_bancaria"; "codigo_asignacion"; "importe"; "moneda"; "estudiante"; "solicitado_por"; "sede"; "observacion");
                    JSONFormat.Compact
                );
                User().Email
            )
        );;
        Set(varMsConfirmacionP9; DateDiff(inicioConfirmacionP9; Now(); TimeUnit.Milliseconds));;
        IfError(
            ClearCollect(
                colConfirmacionP9;
                ForAll(
                    Table(ParseJSON(varResultadoConfirmacionP9.detalle_json));
                    {
                        fila_excel: Value(ThisRecord.Value.fila_excel);
                        deposito_id: Value(ThisRecord.Value.deposito_id);
                        resultado: Text(ThisRecord.Value.resultado);
                        mensaje: Text(ThisRecord.Value.mensaje);
                        estado_final: Text(ThisRecord.Value.estado_final);
                        banco: Text(ThisRecord.Value.banco);
                        cuenta_bancaria: Text(ThisRecord.Value.cuenta_bancaria);
                        codigo_asignacion: Text(ThisRecord.Value.codigo_asignacion);
                        importe: Value(ThisRecord.Value.importe);
                        moneda: Text(ThisRecord.Value.moneda)
                    }
                )
            );
            Notify("No se pudo leer el detalle de la confirmación: " & FirstError.Message; NotificationType.Warning)
        );
        Set(
            varResultadoConfirmacionP9;
            {
                resultado: "ERROR";
                codigo: "FLUJO_SIN_RESPUESTA";
                mensaje: "El flujo no respondió: " & FirstError.Message & ". Es posible que haya seguido confirmando depósitos: vuelva a PREVALIDAR para ver el estado real antes de reintentar.";
                filas_recibidas: "0";
                filas_confirmadas: "0";
                filas_no_confirmadas: "0";
                detalle_json: "[]";
                tiempos_ms: ""
            }
        );;
        Set(varMsConfirmacionP9; DateDiff(inicioConfirmacionP9; Now(); TimeUnit.Milliseconds))
    )
);;
Set(varConfirmacionMasivaFinalizadaP9; true);;
Set(varProcesandoConfirmacionP9; false)
```

### H · `btnVerObservacionesP9` → **Text**

```
=If(Coalesce(varVerObservacionesP9; false); "OCULTAR OBSERVACIONES"; "VER OBSERVACIONES (" & If(!IsBlank(varResultadoConfirmacionP9); CountRows(Filter(colConfirmacionP9; resultado <> "CONFIRMADO")); CountRows(Filter(colPrevalidacionP9; resultado <> "VALIDO"))) & ")")
```

### I · `btnVerObservacionesP9` → **DisplayMode**

```
=If(If(!IsBlank(varResultadoConfirmacionP9); CountRows(Filter(colConfirmacionP9; resultado <> "CONFIRMADO")); CountRows(Filter(colPrevalidacionP9; resultado <> "VALIDO"))) > 0 && !Coalesce(varProcesandoP9; false) && !Coalesce(varProcesandoConfirmacionP9; false); DisplayMode.Edit; DisplayMode.Disabled)
```

### J · `btnVerObservacionesP9` → **OnSelect**

```
=Set(varVerObservacionesP9; !Coalesce(varVerObservacionesP9; false))
```

### K · `galObservacionesP9` → **Items** (antes de confirmar: observaciones de la prevalidación; después: filas no confirmadas)

```
=If(
    !IsBlank(varResultadoConfirmacionP9);
    ShowColumns(Filter(colConfirmacionP9; resultado <> "CONFIRMADO"); "fila_excel"; "resultado"; "mensaje");
    ShowColumns(Filter(colPrevalidacionP9; resultado <> "VALIDO"); "fila_excel"; "resultado"; "mensaje")
)
```

### L · etiqueta de título dentro de la galería (`lblObsTituloP9`) → **Text**

```
="Fila " & ThisItem.fila_excel & " · " & Switch(
    ThisItem.resultado;
    "FILA_INCOMPLETA"; "Datos incompletos";
    "IMPORTE_INVALIDO"; "Importe inválido";
    "MONEDA_INVALIDA"; "Moneda inválida";
    "DUPLICADO_ARCHIVO"; "Fila repetida en el archivo";
    "NO_ENCONTRADO"; "Depósito no encontrado";
    "ASIGNACION_AMBIGUA"; "Asignación ambigua";
    "MONEDA_NO_COINCIDE"; "La moneda no coincide";
    "NO_DISPONIBLE"; "Depósito no disponible";
    "CONFLICTO"; "Conflicto con otro usuario";
    "CONFLICTO_DATOS"; "El depósito cambió";
    "ERROR_FILA"; "Error al procesar la fila";
    ThisItem.resultado
)
```

### M · etiqueta de mensaje dentro de la galería (`lblObsMensajeP9`) → **Text**

```
=ThisItem.mensaje
```

### N · `lblEstadoP9` → **Text**

```
=If(Coalesce(varProcesandoConfirmacionP9; false); "CONFIRMANDO"; If(Coalesce(varProcesandoP9; false); "PROCESANDO"; If(!IsBlank(varResultadoConfirmacionP9); varResultadoConfirmacionP9.resultado; If(!IsBlank(varResultadoP9); varResultadoP9.resultado; If(IsEmpty(attXlsxP9.Attachments); "SIN ARCHIVO"; "CARGADO")))))
```

### O · `lblEstadoP9` → **Fill**

```
=With(
    {estadoP9: If(Coalesce(varProcesandoConfirmacionP9; false); "CONFIRMANDO"; If(Coalesce(varProcesandoP9; false); "PROCESANDO"; If(!IsBlank(varResultadoConfirmacionP9); varResultadoConfirmacionP9.resultado; If(!IsBlank(varResultadoP9); varResultadoP9.resultado; If(IsEmpty(attXlsxP9.Attachments); "SIN ARCHIVO"; "CARGADO")))))};
    Switch(
        estadoP9;
        "OK"; RGBA(46; 125; 50; 1);
        "OBSERVADO"; RGBA(198; 125; 0; 1);
        "PARCIAL"; RGBA(198; 125; 0; 1);
        "ERROR"; RGBA(183; 28; 28; 1);
        "PROCESANDO"; RGBA(230; 126; 34; 1);
        "CONFIRMANDO"; RGBA(230; 126; 34; 1);
        "CARGADO"; RGBA(0; 120; 212; 1);
        RGBA(98; 102; 106; 1)
    )
)
```

### P · `lblTitularResultadoP9` → **Text** (resultado de la confirmación)

```
=If(
    Coalesce(varProcesandoConfirmacionP9; false);
    "Confirmando los depósitos válidos (puede tardar)...";
    If(
        Coalesce(varProcesandoP9; false);
        "Procesando el archivo (puede tardar unos segundos)...";
        If(
            !IsBlank(varResultadoConfirmacionP9);
            Switch(
                varResultadoConfirmacionP9.resultado;
                "OK";
                "CONFIRMACIÓN COMPLETADA" & Char(10) & varResultadoConfirmacionP9.filas_confirmadas & " de " & varResultadoConfirmacionP9.filas_recibidas & " depósitos confirmados.";
                "PARCIAL";
                If(Value(varResultadoConfirmacionP9.filas_confirmadas) = 0; "NO SE CONFIRMÓ NINGÚN DEPÓSITO"; "CONFIRMACIÓN PARCIAL") & Char(10) & varResultadoConfirmacionP9.filas_confirmadas & " de " & varResultadoConfirmacionP9.filas_recibidas & " depósitos confirmados." & Char(10) & varResultadoConfirmacionP9.filas_no_confirmadas & " requieren revisión.";
                "NO SE PUDO CONFIRMAR" & Char(10) & varResultadoConfirmacionP9.mensaje
            );
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
    )
)
```

### Q · `lblResMensajeP9` → **Text**

```
=Coalesce(varResultadoConfirmacionP9.mensaje; varResultadoP9.mensaje; "—")
```

### R · `lblResTiempoTituloP9` → **Text**

```
="TIEMPO DE PROCESAMIENTO"
```

### S · `lblResTiempoP9` → **Text** (tiempo humanizado)

```
=If(IsBlank(Coalesce(varMsConfirmacionP9; varMsAppP9)); "—"; Text(Coalesce(varMsConfirmacionP9; varMsAppP9) / 1000; "0.0") & " segundos")
```

### T · **Visible** de las 11 etiquetas del resumen (`lblResumenTituloP9`, `lblResArchivoTituloP9`, `lblResArchivoP9`, `lblResTablaTituloP9`, `lblResTablaP9`, `lblResFilasTituloP9`, `lblResFilasP9`, `lblResMensajeTituloP9`, `lblResMensajeP9`, `lblResTiempoTituloP9`, `lblResTiempoP9`)

```
=!Coalesce(varVerObservacionesP9; false)
```

### U · `lblSubtituloMasivaP9` → **Text**

```
="Prototipo directo · prevalida un archivo Excel y confirma solo las filas que siguen siendo válidas."
```

### V · `lblAvisoPrototipoP9` → **Text**

```
="PROTOTIPO · CONFIRMAR MASIVAMENTE relee cada depósito antes de escribir y solo confirma lo que sigue válido · sin lotes ni historial."
```
