# Power Fx de la CONFIRMACIÓN MASIVA (botón `btnConfirmarMasivamenteP9`)

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

### A · `btnConfirmarMasivamenteP9` → **OnSelect** (UN clic, sin segundo modal; PEGA ESTA PRIMERO: define las variables y `colConfirmacionP9`)

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
                    ShowColumns(
                        Filter(
                            colPrevalidacionP9;
                            resultado = "VALIDO"
                        );
                        "fila_excel";
                        "deposito_id";
                        "clave_transaccion";
                        "banco";
                        "cuenta_bancaria";
                        "codigo_asignacion";
                        "importe";
                        "moneda";
                        "estudiante";
                        "solicitado_por";
                        "sede";
                        "observacion"
                    );
                    JSONFormat.Compact
                );
                User().Email
            )
        );;
        Set(
            varMsConfirmacionP9;
            DateDiff(
                inicioConfirmacionP9;
                Now();
                TimeUnit.Milliseconds
            )
        );;
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
            );;
            true;
            Notify(
                "No se pudo leer el detalle de la confirmación: " & FirstError.Message;
                NotificationType.Warning
            );;
            false
        );;
        true;
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
        Set(
            varMsConfirmacionP9;
            DateDiff(
                inicioConfirmacionP9;
                Now();
                TimeUnit.Milliseconds
            )
        );;
        false
    )
);;

Set(varConfirmacionMasivaFinalizadaP9; true);;
Set(varProcesandoConfirmacionP9; false)
```

### B · `btnConfirmarMasivamenteP9` → **DisplayMode** (Disabled mientras corre y después de confirmar ese mismo resultado)

```
=If(
    !Coalesce(varProcesandoP9; false) &&
    !Coalesce(varProcesandoConfirmacionP9; false) &&
    !Coalesce(varConfirmacionMasivaFinalizadaP9; false) &&
    CountRows(
        Filter(
            colPrevalidacionP9;
            resultado = "VALIDO"
        )
    ) > 0;
    DisplayMode.Edit;
    DisplayMode.Disabled
)
```

### C · Pantalla `P9_Confirmacion_Masiva` → propiedad **OnVisible** (reemplaza todo; retira `varConfirmarMasivaVisible`)

```
=Set(varProcesandoP9; false);;
Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Set(varProcesandoConfirmacionP9; false);;
Set(varConfirmacionMasivaFinalizadaP9; false);;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Clear(colPrevalidacionP9);;
Clear(colConfirmacionP9);;
Set(varVerObservacionesP9; false);;
ResetForm(frmArchivoP9)
```

### D · Control de adjuntos `attXlsxP9` → propiedades **OnAddFile** y **OnRemoveFile** (la misma fórmula en las dos)

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

### E · `btnPrevalidarP9` → **DisplayMode**

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

### F · `btnPrevalidarP9` → **OnSelect** (tu fórmula real con `IfError … true / false`, más el reinicio de la confirmación)

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
        Set(
            varResultadoP9;
            P9_MASIVA_PROTO_PREVALIDAR.Run(
                {
                    name: archivoP9.Name;
                    contentBytes: archivoP9.Value
                }
            )
        );;
        Set(
            varMsAppP9;
            DateDiff(
                inicioP9;
                Now();
                TimeUnit.Milliseconds
            )
        );;
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
            );;
            true;
            Notify(
                "No se pudo leer el detalle de la prevalidación: " & FirstError.Message;
                NotificationType.Warning
            );;
            false
        );;
        true;

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
        Set(
            varMsAppP9;
            DateDiff(
                inicioP9;
                Now();
                TimeUnit.Milliseconds
            )
        );;
        false
    )
);;

Set(varProcesandoP9; false)
```

### G · `btnVerObservacionesP9` → **Text**

```
=If(
    Coalesce(varVerObservacionesP9; false);
    "OCULTAR OBSERVACIONES";
    "VER OBSERVACIONES (" &
    If(
        !IsBlank(varResultadoConfirmacionP9);
        CountRows(
            Filter(
                colConfirmacionP9;
                resultado <> "CONFIRMADO"
            )
        );
        CountRows(
            Filter(
                colPrevalidacionP9;
                resultado <> "VALIDO"
            )
        )
    ) &
    ")"
)
```

### H · `btnVerObservacionesP9` → **Visible**

```
=If(
    !IsBlank(varResultadoConfirmacionP9);
    CountRows(
        Filter(
            colConfirmacionP9;
            resultado <> "CONFIRMADO"
        )
    );
    CountRows(
        Filter(
            colPrevalidacionP9;
            resultado <> "VALIDO"
        )
    )
) > 0
```

### I · `galObservacionesP9` → **Items** (antes de confirmar: observaciones de la prevalidación; después: filas no confirmadas)

```
=If(
    !IsBlank(varResultadoConfirmacionP9);
    ForAll(
        Filter(
            colConfirmacionP9;
            resultado <> "CONFIRMADO"
        );
        {
            fila_excel: fila_excel;
            resultado: resultado;
            mensaje: mensaje;
            clave_transaccion: With(
                {filaP9: ThisRecord.fila_excel};
                Coalesce(
                    LookUp(
                        colPrevalidacionP9;
                        fila_excel = filaP9
                    ).clave_transaccion;
                    ""
                )
            )
        }
    );
    ShowColumns(
        Filter(
            colPrevalidacionP9;
            resultado <> "VALIDO"
        );
        "fila_excel";
        "resultado";
        "mensaje";
        "clave_transaccion"
    )
)
```

### J · `Title1` (etiqueta de título DENTRO de `galObservacionesP9`) → **Text** (añade los resultados de la confirmación)

```
="Fila " & Text(ThisItem.fila_excel) &
" · " &
Switch(
    ThisItem.resultado;
    "NO_DISPONIBLE"; "DEPÓSITO NO DISPONIBLE";
    "NO_ENCONTRADO"; "DEPÓSITO NO ENCONTRADO";
    "MONEDA_NO_COINCIDE"; "MONEDA NO COINCIDE";
    "ASIGNACION_AMBIGUA"; "COINCIDENCIA AMBIGUA";
    "DUPLICADO_ARCHIVO"; "DUPLICADO EN EL EXCEL";
    "FILA_INCOMPLETA"; "FALTAN DATOS";
    "IMPORTE_INVALIDO"; "IMPORTE INVÁLIDO";
    "MONEDA_INVALIDA"; "MONEDA INVÁLIDA";
    "CONFLICTO"; "CONFLICTO CON OTRO USUARIO";
    "CONFLICTO_DATOS"; "EL DEPÓSITO CAMBIÓ";
    "ERROR_FILA"; "ERROR AL PROCESAR LA FILA";
    ThisItem.resultado
)
```

### K · `lblEstadoP9` → **Text**

```
=If(
    Coalesce(varProcesandoConfirmacionP9; false);
    "CONFIRMANDO";
    If(
        Coalesce(varProcesandoP9; false);
        "PROCESANDO";
        If(
            !IsBlank(varResultadoConfirmacionP9);
            varResultadoConfirmacionP9.resultado;
            If(
                !IsBlank(varResultadoP9);
                varResultadoP9.resultado;
                If(
                    IsEmpty(attXlsxP9.Attachments);
                    "SIN ARCHIVO";
                    "CARGADO"
                )
            )
        )
    )
)
```

### L · `lblEstadoP9` → **Fill**

```
=With(
    {
        estadoP9:
            If(
                Coalesce(varProcesandoConfirmacionP9; false);
                "CONFIRMANDO";
                If(
                    Coalesce(varProcesandoP9; false);
                    "PROCESANDO";
                    If(
                        !IsBlank(varResultadoConfirmacionP9);
                        varResultadoConfirmacionP9.resultado;
                        If(
                            !IsBlank(varResultadoP9);
                            varResultadoP9.resultado;
                            If(
                                IsEmpty(attXlsxP9.Attachments);
                                "SIN ARCHIVO";
                                "CARGADO"
                            )
                        )
                    )
                )
            )
    };
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

### M · `lblTitularResultadoP9` → **Text** (resultado de la confirmación en dos líneas; conserva el alto 50 del tenant)

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
                "CONFIRMACIÓN COMPLETADA" & Char(10) &
                varResultadoConfirmacionP9.filas_confirmadas & " de " & varResultadoConfirmacionP9.filas_recibidas & " depósitos confirmados.";
                "PARCIAL";
                If(
                    Value(varResultadoConfirmacionP9.filas_confirmadas) = 0;
                    "NO SE CONFIRMÓ NINGÚN DEPÓSITO";
                    "CONFIRMACIÓN PARCIAL"
                ) & Char(10) &
                varResultadoConfirmacionP9.filas_confirmadas & " de " & varResultadoConfirmacionP9.filas_recibidas & " depósitos confirmados · " &
                varResultadoConfirmacionP9.filas_no_confirmadas & " requieren revisión.";
                "NO SE PUDO CONFIRMAR" & Char(10) & "Vea el mensaje en el resumen."
            );
            If(
                IsBlank(varResultadoP9);
                If(
                    IsEmpty(attXlsxP9.Attachments);
                    "Adjunte un Excel (.xlsx) para empezar.";
                    "Archivo seleccionado. Pulse PREVALIDAR ARCHIVO."
                );
                If(
                    varResultadoP9.resultado = "OK" || varResultadoP9.resultado = "OBSERVADO";
                    "PREVALIDACIÓN · " &
                    varResultadoP9.filas_validas &
                    " DE " &
                    varResultadoP9.filas_totales &
                    If(
                        Value(varResultadoP9.filas_totales) = 1;
                        " FILA VÁLIDA";
                        " FILAS VÁLIDAS"
                    );
                    "RESULTADO: " & varResultadoP9.codigo
                )
            )
        )
    )
)
```

### N · `lblResMensajeP9` → **Text**

```
=If(
    !IsBlank(varResultadoConfirmacionP9);
    varResultadoConfirmacionP9.mensaje;
    If(
        IsBlank(varResultadoP9);
        "—";
        If(
            varResultadoP9.resultado = "OK";
            "Todas las filas están listas para confirmar.";
            Concat(
                Filter(
                    colPrevalidacionP9;
                    resultado <> "VALIDO"
                );
                "Fila " & Text(fila_excel) & " · " &
                Switch(
                    resultado;
                    "NO_DISPONIBLE"; "DEPÓSITO NO DISPONIBLE";
                    "NO_ENCONTRADO"; "DEPÓSITO NO ENCONTRADO";
                    "MONEDA_NO_COINCIDE"; "MONEDA NO COINCIDE";
                    "ASIGNACION_AMBIGUA"; "COINCIDENCIA AMBIGUA";
                    "DUPLICADO_ARCHIVO"; "DUPLICADO EN EL EXCEL";
                    "FILA_INCOMPLETA"; "FALTAN DATOS";
                    "IMPORTE_INVALIDO"; "IMPORTE INVÁLIDO";
                    "MONEDA_INVALIDA"; "MONEDA INVÁLIDA";
                    resultado
                ) &
                ": " & mensaje;
                Char(10)
            )
        )
    )
)
```

### O · `lblResTiempoP9` → **Text** (tiempo humanizado, mismo formato «8,9 segundos»)

```
=If(
    IsBlank(Coalesce(varMsConfirmacionP9; varMsAppP9));
    "—";
    Text(
        Round(Coalesce(varMsConfirmacionP9; varMsAppP9) / 1000; 1);
        "0,0"
    ) & " segundos"
)
```

### P · `lblSubtituloMasivaP9` → **Text**

```
="Prototipo directo · prevalida un archivo Excel y confirma solo las filas que siguen siendo válidas."
```

### Q · `lblAvisoPrototipoP9` → **Text**

```
="PROTOTIPO · CONFIRMAR MASIVAMENTE relee cada depósito antes de escribir y solo confirma lo que sigue válido · sin lotes ni historial."
```

## Lo que NO cambia (déjalo como está en tu app)

- `btnConfirmarMasivamenteP9` → **Text** (ya cuenta las filas `VALIDO`) y toda su geometría/estilo
- `btnVerObservacionesP9` → **OnSelect** (ya alterna `varVerObservacionesP9`) y su aspecto
- `Title1_1` (etiqueta del mensaje dentro de la galería) → `=ThisItem.mensaje`, y `Subtitle1`, `Separator1`, `Rectangle1`
- `lblResMensajeP9` → **Visible** (`=!varVerObservacionesP9`) y `lblResTiempoTituloP9` («Tiempo de Procesamiento»)
- `btnDescargarPlantillaP9`, `btnVolverMasivaP9`, `frmArchivoP9`, `dcAdjuntosP9`, el panel y los demás rótulos del resumen
- `Main_Screen`: `btnImportacionMasivaP9`, `cmbCuentaP9_1` y sus `Visible` con `mostrarConfirmacion`

## Qué mirar tras pegar

1. **Comprobador de aplicaciones** (estetoscopio): sin errores nuevos. Cualquier error en `P9_MASIVA_PROTO_CONFIRMAR.Run`, `JSON(ShowColumns(…))`, `ThisRecord.Value` o `With` dentro
   de `ForAll`: copia el texto exacto; se ajusta solo esa línea.
2. **Alto del titular:** el resultado de la confirmación ocupa dos líneas dentro del alto 50 que ya tienes; si se corta, sube el alto de `lblTitularResultadoP9` (único ajuste visual posible).
3. Pruebas en el tenant: `flows/INSTRUCCIONES_CONFIRMAR.md`, Parte 3 (empieza con **1 fila**).
