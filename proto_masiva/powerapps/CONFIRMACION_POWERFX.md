# Power Fx de la CONFIRMACIÓN MASIVA hasta 1999 filas (un clic, seguimiento por Temporizador)

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
| `Duration` | `15000` |
| `Repeat` | `true` |
| `AutoStart` | `false` |
| `Start` | `Coalesce(varMonitorearP9; false)` |
| `Visible` | `false` |

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

### A · `btnConfirmarMasivamenteP9` → **OnSelect** (UN clic: responde enseguida y arranca el seguimiento; PEGA ESTA PRIMERO: define las variables nuevas)

```
=Set(varProcesandoConfirmacionP9; true);;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varEjecucionMasivaP9; Blank());;
Set(varProgresoMasivoP9; Blank());;
Set(varFallosEstadoP9; 0);;
Set(varMonitorearP9; false);;
Set(varVerObservacionesP9; false);;
Clear(colConfirmacionP9);;
Set(varInicioConfirmacionP9; Now());;

IfError(
    Set(
        varEjecucionMasivaP9;
        P9_MASIVA_PROTO_CONFIRMAR.Run(
            JSON(
                ShowColumns(
                    Filter(
                        colPrevalidacionP9;
                        resultado = "VALIDO"
                    );
                    fila_excel;
                    deposito_id;
                    clave_transaccion;
                    banco;
                    cuenta_bancaria;
                    codigo_asignacion;
                    importe;
                    moneda;
                    estudiante;
                    solicitado_por;
                    sede;
                    observacion
                );
                JSONFormat.Compact
            );
            User().Email
        )
    );;
    true;
    Set(
        varEjecucionMasivaP9;
        {
            resultado: "ERROR";
            codigo: "FLUJO_SIN_RESPUESTA";
            mensaje: "El flujo no respondió: " & FirstError.Message & ". Es posible que haya empezado a confirmar depósitos: vuelva a PREVALIDAR para ver el estado real antes de reintentar.";
            execution_uid: "";
            filas_recibidas: "0"
        }
    );;
    false
);;

Set(varConfirmacionMasivaFinalizadaP9; true);;

If(
    varEjecucionMasivaP9.resultado = "ACEPTADO";
    Set(
        varProgresoMasivoP9;
        {
            estado: "PROCESANDO";
            filas_totales: varEjecucionMasivaP9.filas_recibidas;
            filas_procesadas: "0";
            filas_confirmadas: "0";
            filas_no_confirmadas: "0";
            porcentaje: "0";
            mensaje: varEjecucionMasivaP9.mensaje;
            detalle_json: "[]";
            tiempos_ms: ""
        }
    );;
    Set(varMonitorearP9; true);
    Set(
        varResultadoConfirmacionP9;
        {
            resultado: "ERROR";
            codigo: varEjecucionMasivaP9.codigo;
            mensaje: varEjecucionMasivaP9.mensaje;
            filas_recibidas: varEjecucionMasivaP9.filas_recibidas;
            filas_confirmadas: "0";
            filas_no_confirmadas: "0";
            detalle_json: "[]";
            tiempos_ms: ""
        }
    );;
    Set(
        varMsConfirmacionP9;
        DateDiff(
            varInicioConfirmacionP9;
            Now();
            TimeUnit.Milliseconds
        )
    );;
    Set(varProcesandoConfirmacionP9; false)
)
```

### B · `tmrProgresoP9` (Temporizador NUEVO, ver «Crear el Temporizador») → **OnTimerEnd**

```
=IfError(
    Set(
        varProgresoMasivoP9;
        P9_MASIVA_PROTO_ESTADO.Run(varEjecucionMasivaP9.execution_uid)
    );;
    Set(
        varFallosEstadoP9;
        If(
            varProgresoMasivoP9.estado = "NO_ENCONTRADO";
            varFallosEstadoP9 + 1;
            0
        )
    );;
    true;
    Set(varFallosEstadoP9; varFallosEstadoP9 + 1);;
    false
);;

If(
    varFallosEstadoP9 >= 5 && varProgresoMasivoP9.estado <> "TERMINADO" && varProgresoMasivoP9.estado <> "ERROR";
    Set(
        varProgresoMasivoP9;
        {
            estado: "ERROR";
            filas_totales: Coalesce(varProgresoMasivoP9.filas_totales; varEjecucionMasivaP9.filas_recibidas);
            filas_procesadas: Coalesce(varProgresoMasivoP9.filas_procesadas; "0");
            filas_confirmadas: Coalesce(varProgresoMasivoP9.filas_confirmadas; "0");
            filas_no_confirmadas: Coalesce(varProgresoMasivoP9.filas_no_confirmadas; "0");
            porcentaje: Coalesce(varProgresoMasivoP9.porcentaje; "0");
            mensaje: "No se pudo consultar el progreso de la confirmación. Puede seguir ejecutándose en segundo plano: vuelva a PREVALIDAR para ver el estado real antes de reintentar.";
            detalle_json: "[]";
            tiempos_ms: ""
        }
    )
);;

If(
    varProgresoMasivoP9.estado = "TERMINADO" || varProgresoMasivoP9.estado = "ERROR";
    Set(varMonitorearP9; false);;
    Set(
        varMsConfirmacionP9;
        DateDiff(
            varInicioConfirmacionP9;
            Now();
            TimeUnit.Milliseconds
        )
    );;
    Set(
        varResultadoConfirmacionP9;
        {
            resultado: If(
                varProgresoMasivoP9.estado = "ERROR";
                "ERROR";
                If(
                    Value(varProgresoMasivoP9.filas_no_confirmadas) = 0;
                    "OK";
                    "PARCIAL"
                )
            );
            codigo: If(
                varProgresoMasivoP9.estado = "ERROR";
                "ERROR_NO_CONTROLADO";
                If(
                    Value(varProgresoMasivoP9.filas_no_confirmadas) = 0;
                    "CONFIRMACION_OK";
                    "CONFIRMACION_PARCIAL"
                )
            );
            mensaje: varProgresoMasivoP9.mensaje;
            filas_recibidas: varProgresoMasivoP9.filas_totales;
            filas_confirmadas: varProgresoMasivoP9.filas_confirmadas;
            filas_no_confirmadas: varProgresoMasivoP9.filas_no_confirmadas;
            detalle_json: varProgresoMasivoP9.detalle_json;
            tiempos_ms: varProgresoMasivoP9.tiempos_ms
        }
    );;
    IfError(
        ClearCollect(
            colConfirmacionP9;
            ForAll(
                Table(ParseJSON(varProgresoMasivoP9.detalle_json));
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
    Set(varProcesandoConfirmacionP9; false)
)
```

### C · Pantalla `P9_Confirmacion_Masiva` → propiedad **OnVisible** (reemplaza todo)

```
=Set(varProcesandoP9; false);;
Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Set(varProcesandoConfirmacionP9; false);;
Set(varConfirmacionMasivaFinalizadaP9; false);;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varEjecucionMasivaP9; Blank());;
Set(varProgresoMasivoP9; Blank());;
Set(varFallosEstadoP9; 0);;
Set(varMonitorearP9; false);;
Clear(colPrevalidacionP9);;
Clear(colConfirmacionP9);;
Set(varVerObservacionesP9; false);;
ResetForm(frmArchivoP9)
```

### D · Control de adjuntos `attXlsxP9` → propiedades **OnAddFile** y **OnRemoveFile** (la misma fórmula en las dos)

```
=If(
    !Coalesce(varProcesandoConfirmacionP9; false);
    Set(varResultadoP9; Blank());;
    Set(varMsAppP9; Blank());;
    Set(varResultadoConfirmacionP9; Blank());;
    Set(varMsConfirmacionP9; Blank());;
    Set(varEjecucionMasivaP9; Blank());;
    Set(varProgresoMasivoP9; Blank());;
    Set(varFallosEstadoP9; 0);;
    Set(varMonitorearP9; false);;
    Set(varConfirmacionMasivaFinalizadaP9; false);;
    Set(varVerObservacionesP9; false);;
    Clear(colPrevalidacionP9);;
    Clear(colConfirmacionP9)
)
```

### E · `btnPrevalidarP9` → **OnSelect** (tu fórmula real con `IfError … true / false`, más 4 reinicios)

```
=Set(varProcesandoP9; true);;
Set(varResultadoP9; Blank());;
Set(varMsAppP9; Blank());;
Set(varResultadoConfirmacionP9; Blank());;
Set(varMsConfirmacionP9; Blank());;
Set(varEjecucionMasivaP9; Blank());;
Set(varProgresoMasivoP9; Blank());;
Set(varFallosEstadoP9; 0);;
Set(varMonitorearP9; false);;
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

### F · `lblTitularResultadoP9` → **Text** (avance en dos líneas mientras corre; resultado final en dos líneas; conserva el alto 50)

```
=If(
    Coalesce(varProcesandoConfirmacionP9; false);
    "CONFIRMACIÓN EN PROCESO" &
    If(
        IsBlank(varProgresoMasivoP9);
        "";
        " · " & varProgresoMasivoP9.porcentaje & " %"
    ) &
    Char(10) &
    If(
        IsBlank(varProgresoMasivoP9);
        "Iniciando...";
        varProgresoMasivoP9.filas_procesadas &
        " de " &
        varProgresoMasivoP9.filas_totales &
        " procesados · " &
        varProgresoMasivoP9.filas_confirmadas &
        " confirmados · " &
        varProgresoMasivoP9.filas_no_confirmadas &
        " requieren revisión"
    );
    If(
        Coalesce(varProcesandoP9; false);
        "Procesando el archivo (puede tardar unos segundos)...";
        If(
            !IsBlank(varResultadoConfirmacionP9);
            Switch(
                varResultadoConfirmacionP9.resultado;
                "OK";
                "CONFIRMACIÓN COMPLETADA" & Char(10) &
                varResultadoConfirmacionP9.filas_confirmadas &
                " de " &
                varResultadoConfirmacionP9.filas_recibidas &
                " depósitos confirmados.";
                "PARCIAL";
                If(
                    Value(varResultadoConfirmacionP9.filas_confirmadas) = 0;
                    "NO SE CONFIRMÓ NINGÚN DEPÓSITO";
                    "CONFIRMACIÓN COMPLETADA"
                ) & Char(10) &
                varResultadoConfirmacionP9.filas_confirmadas &
                " de " &
                varResultadoConfirmacionP9.filas_recibidas &
                " depósitos confirmados · " &
                varResultadoConfirmacionP9.filas_no_confirmadas &
                " requieren revisión.";
                "NO SE PUDO CONFIRMAR" &
                Char(10) &
                "Vea el mensaje en el resumen."
            );
            If(
                IsBlank(varResultadoP9);
                If(
                    IsEmpty(attXlsxP9.Attachments);
                    "Adjunte un Excel (.xlsx) para empezar.";
                    "Archivo seleccionado. Pulse PREVALIDAR ARCHIVO."
                );
                If(
                    varResultadoP9.resultado = "OK" ||
                    varResultadoP9.resultado = "OBSERVADO";
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

### G · `lblResMensajeP9` → **Text**

```
=If(
    Coalesce(varProcesandoConfirmacionP9; false) && !IsBlank(varProgresoMasivoP9);
    varProgresoMasivoP9.mensaje & " La confirmación continúa en segundo plano.";
    If(
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
                    ": " &
                    mensaje;
                    Char(10)
                )
            )
        )
    )
)
```

### H · `lblResTiempoP9` → **Text** (muestra «En curso» mientras corre)

```
=If(
    Coalesce(varProcesandoConfirmacionP9; false);
    "En curso";
    If(
        IsBlank(Coalesce(varMsConfirmacionP9; varMsAppP9));
        "—";
        Text(
            Round(
                Coalesce(varMsConfirmacionP9; varMsAppP9) / 1000;
                1
            );
            "0,0"
        ) &
        " segundos"
    )
)
```

### I · `lblAvisoPrototipoP9` → **Text**

```
="Relee cada depósito antes de escribir y solo confirma lo que sigue válido · hasta 1999 filas con un clic · sin lotes ni historial."
```

## Lo que NO cambia (déjalo como está en tu app)

- `btnConfirmarMasivamenteP9` → **Text** y **DisplayMode** (ya bloquean mientras corre y después de confirmar) y toda su geometría/estilo
- `btnVerObservacionesP9`, `galObservacionesP9`, `Title1`, `Title1_1`, `Subtitle1`: tras terminar muestran SOLO las filas no confirmadas, igual que en la V1 (`colConfirmacionP9` ahora trae solo esas)
- `lblEstadoP9` (Text y Fill): ya muestran `CONFIRMANDO` mientras corre y `OK` / `PARCIAL` / `ERROR` al terminar
- `btnPrevalidarP9` → **DisplayMode**, `btnVolverMasivaP9`, `btnDescargarPlantillaP9`, `frmArchivoP9`, `dcAdjuntosP9` y los demás rótulos del resumen
- `Main_Screen`: `btnImportacionMasivaP9`, `cmbCuentaP9_1` y sus `Visible` con `mostrarConfirmacion`

## Qué mirar tras pegar

1. **Comprobador de aplicaciones** (estetoscopio): sin errores nuevos. Posibles puntos: `P9_MASIVA_PROTO_ESTADO.Run`, `P9_MASIVA_PROTO_CONFIRMAR.Run`, `JSON(ShowColumns(…))`, `With` dentro de `ForAll`.
   Cualquier error: copia el texto exacto; se ajusta solo esa línea.
2. **Al pulsar CONFIRMAR MASIVAMENTE (N)** debe verse en segundos «CONFIRMACIÓN EN PROCESO · 0 % / 0 de N procesados…», y cada ~15 s el avance. Al terminar: «CONFIRMACIÓN COMPLETADA» y, si hubo
   fallidas, `VER OBSERVACIONES (K)` con solo esas filas.
3. Si Power Apps se cierra durante el proceso, el backend sigue; esta versión NO recupera el seguimiento al volver (queda fuera de alcance): vuelve a PREVALIDAR para ver el estado real.
