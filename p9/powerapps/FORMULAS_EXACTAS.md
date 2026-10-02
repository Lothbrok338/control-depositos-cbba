# Fórmulas exactas — P9 / comprobante

Extraídas de `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`, `COMPROBANTE_PDF.pa.yaml` y del frontend P9, que son los archivos validados a mano en el tenant. No incluyen el `=` inicial del formato YAML. `tests/test_26_comprobante_cuenta_tc_p9.py` comprueba que cada bloque de este archivo coincide con su YAML (y su variante regional con la conversión mecánica), de modo que no puede quedar desfasado.

La variante canónica usa comas entre argumentos y `;` entre acciones. Para una barra de fórmulas con separadores españoles se incluye la variante con `;` y `;;` cuando difiere. Las cadenas, incluido `"#,##0.00"` y las expresiones regulares de `IsMatch`, se conservan. Los YAML completos usan la variante de la base validada: Studio convierte los separadores al pegar.

Las variantes regionales se generan por conversión mecánica. Las dos que el usuario escribió a mano en Studio y validó en el tenant son `OnVisible` y `OnHidden` de `'COMPROBANTE PDF'`.

Las coordenadas y medidas (X, Y, Width, Height) de todos los controles del comprobante son números fijos; no se repiten aquí y se leen directamente de `COMPROBANTE_PDF_CONTROLES_PEGAR_FINAL.yaml`.

## btnAbrirComprobanteP9.Visible

```powerfx
ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO"
```

## btnAbrirComprobanteP9.DisplayMode

```powerfx
If(Coalesce(varP9ComprobanteCargando, false), DisplayMode.Disabled, DisplayMode.Edit)
```

Con separadores regionales:

```powerfx
If(Coalesce(varP9ComprobanteCargando; false); DisplayMode.Disabled; DisplayMode.Edit)
```

## btnAbrirComprobanteP9.OnSelect

```powerfx
Set(varP9ComprobanteID, ThisItem.ID);
Set(varP9Comprobante, Blank());
Set(varP9ComprobanteCargando, true);
IfError(
    Refresh(Depositos_Activos),
    Set(varP9Comprobante, Blank());
    Set(varP9ComprobanteID, Blank());
    Notify("No se pudo consultar SharePoint. Vuelve a intentar abrir el comprobante.", NotificationType.Warning);
    false,
    IfError(
        With(
            {registroP9: LookUp(Depositos_Activos, ID = varP9ComprobanteID)},
            If(
                IsBlank(registroP9.ID) || registroP9.ESTADO_ASIGNACION.Value <> "ASIGNADO",
                Set(varP9ComprobanteID, Blank());
                Notify("El ingreso no existe o ya no está CONFIRMADO. No se puede abrir el comprobante.", NotificationType.Warning);
                false,
                Set(varP9Comprobante, registroP9);
                Navigate('COMPROBANTE PDF', ScreenTransition.None)
            )
        ),
        Set(varP9Comprobante, Blank());
        Set(varP9ComprobanteID, Blank());
        Notify("No se pudo leer el ingreso desde SharePoint. Vuelve a intentarlo.", NotificationType.Warning);
        false
    )
);
Set(varP9ComprobanteCargando, false)
```

Con separadores regionales:

```powerfx
Set(varP9ComprobanteID; ThisItem.ID);;
Set(varP9Comprobante; Blank());;
Set(varP9ComprobanteCargando; true);;
IfError(
    Refresh(Depositos_Activos);
    Set(varP9Comprobante; Blank());;
    Set(varP9ComprobanteID; Blank());;
    Notify("No se pudo consultar SharePoint. Vuelve a intentar abrir el comprobante."; NotificationType.Warning);;
    false;
    IfError(
        With(
            {registroP9: LookUp(Depositos_Activos; ID = varP9ComprobanteID)};
            If(
                IsBlank(registroP9.ID) || registroP9.ESTADO_ASIGNACION.Value <> "ASIGNADO";
                Set(varP9ComprobanteID; Blank());;
                Notify("El ingreso no existe o ya no está CONFIRMADO. No se puede abrir el comprobante."; NotificationType.Warning);;
                false;
                Set(varP9Comprobante; registroP9);;
                Navigate('COMPROBANTE PDF'; ScreenTransition.None)
            )
        );
        Set(varP9Comprobante; Blank());;
        Set(varP9ComprobanteID; Blank());;
        Notify("No se pudo leer el ingreso desde SharePoint. Vuelve a intentarlo."; NotificationType.Warning);;
        false
    )
);;
Set(varP9ComprobanteCargando; false)
```

## btnAsignarP9.Height

```powerfx
If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO", 28, 32)
```

Con separadores regionales:

```powerfx
If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO"; 28; 32)
```

## btnAsignarP9.Y

```powerfx
If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO", 6, 22)
```

Con separadores regionales:

```powerfx
If(ThisItem.ESTADO_ASIGNACION.Value = "ASIGNADO"; 6; 22)
```

## 'COMPROBANTE PDF'.Width

```powerfx
816
```

## 'COMPROBANTE PDF'.Height

```powerfx
1056
```

## 'COMPROBANTE PDF'.OnVisible

```powerfx
Reset(txtTipoCambioPDF);
If(
    IsBlank(varP9ComprobanteID) || IsBlank(varP9Comprobante.ID) ||
    varP9Comprobante.ID <> varP9ComprobanteID ||
    varP9Comprobante.ESTADO_ASIGNACION.Value <> "ASIGNADO",
    Set(varP9Comprobante, Blank());
    Set(varP9ComprobanteID, Blank());
    Notify("No hay un ingreso CONFIRMADO para mostrar. Abre el comprobante desde P9.", NotificationType.Warning);
    Back()
)
```

Con separadores regionales:

```powerfx
Reset(txtTipoCambioPDF);;
If(
    IsBlank(varP9ComprobanteID) || IsBlank(varP9Comprobante.ID) ||
    varP9Comprobante.ID <> varP9ComprobanteID ||
    varP9Comprobante.ESTADO_ASIGNACION.Value <> "ASIGNADO";
    Set(varP9Comprobante; Blank());;
    Set(varP9ComprobanteID; Blank());;
    Notify("No hay un ingreso CONFIRMADO para mostrar. Abre el comprobante desde P9."; NotificationType.Warning);;
    Back()
)
```

## 'COMPROBANTE PDF'.OnHidden

```powerfx
Reset(txtTipoCambioPDF);
Set(varP9Comprobante, Blank());
Set(varP9ComprobanteID, Blank())
```

Con separadores regionales:

```powerfx
Reset(txtTipoCambioPDF);;
Set(varP9Comprobante; Blank());;
Set(varP9ComprobanteID; Blank())
```

## cntComprobantePDF.Visible

```powerfx
!IsBlank(varP9ComprobanteID) && !IsBlank(varP9Comprobante.ID) && varP9Comprobante.ID = varP9ComprobanteID && varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO"
```

## btnImprimirPDF.OnSelect

```powerfx
Print()
```

## btnImprimirPDF.Visible

```powerfx
Not('COMPROBANTE PDF'.Printing) && !IsBlank(varP9ComprobanteID) && !IsBlank(varP9Comprobante.ID) && varP9Comprobante.ID = varP9ComprobanteID && varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO"
```

## btnImprimirPDF.DisplayMode

```powerfx
If(
    !IsBlank(varP9ComprobanteID) && !IsBlank(varP9Comprobante.ID) && varP9Comprobante.ID = varP9ComprobanteID && varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO" &&
    With(
        {
            descTexto: Coalesce(varP9Comprobante.DESCRIPCION, ""),
            obsTexto: Coalesce(varP9Comprobante.OBSERVACION, "")
        },
        Len(Coalesce(varP9Comprobante.CODIGO_ASIGNACION, "")) <= 26 &&
        Len(Coalesce(varP9Comprobante.BANCO, "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.CUENTA_BANCARIA, "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.HORA_MOVIMIENTO, "")) <= 35 &&
        Len(Coalesce(varP9Comprobante.ESTUDIANTE, "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SOLICITADO_POR, "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SEDE_ASIGNACION, "")) <= 48 &&
        Len(Coalesce(varP9Comprobante.USUARIO_ASIGNACION, "")) <= 50 &&
        RoundUp(Len(descTexto) / 62, 0) + Len(descTexto) - Len(Substitute(descTexto, Char(10), "")) <= 5 &&
        RoundUp(Len(obsTexto) / 64, 0) + Len(obsTexto) - Len(Substitute(obsTexto, Char(10), "")) <= 5
    ) &&
    (
        varP9Comprobante.MONEDA <> "USD" ||
        With(
            {
                tcValor: With(
                    {tcTexto: Trim(txtTipoCambioPDF.Text)},
                    If(
                        IsMatch(tcTexto, "^[0-9]+$") || IsMatch(tcTexto, "^[0-9]+[.,][0-9]+$"),
                        Value(Substitute(tcTexto, ",", "."), "en-US")
                    )
                )
            },
            !IsBlank(tcValor) && tcValor > 0
        )
    ),
    DisplayMode.Edit,
    DisplayMode.Disabled
)
```

Con separadores regionales:

```powerfx
If(
    !IsBlank(varP9ComprobanteID) && !IsBlank(varP9Comprobante.ID) && varP9Comprobante.ID = varP9ComprobanteID && varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO" &&
    With(
        {
            descTexto: Coalesce(varP9Comprobante.DESCRIPCION; "");
            obsTexto: Coalesce(varP9Comprobante.OBSERVACION; "")
        };
        Len(Coalesce(varP9Comprobante.CODIGO_ASIGNACION; "")) <= 26 &&
        Len(Coalesce(varP9Comprobante.BANCO; "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.CUENTA_BANCARIA; "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.HORA_MOVIMIENTO; "")) <= 35 &&
        Len(Coalesce(varP9Comprobante.ESTUDIANTE; "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SOLICITADO_POR; "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SEDE_ASIGNACION; "")) <= 48 &&
        Len(Coalesce(varP9Comprobante.USUARIO_ASIGNACION; "")) <= 50 &&
        RoundUp(Len(descTexto) / 62; 0) + Len(descTexto) - Len(Substitute(descTexto; Char(10); "")) <= 5 &&
        RoundUp(Len(obsTexto) / 64; 0) + Len(obsTexto) - Len(Substitute(obsTexto; Char(10); "")) <= 5
    ) &&
    (
        varP9Comprobante.MONEDA <> "USD" ||
        With(
            {
                tcValor: With(
                    {tcTexto: Trim(txtTipoCambioPDF.Text)};
                    If(
                        IsMatch(tcTexto; "^[0-9]+$") || IsMatch(tcTexto; "^[0-9]+[.,][0-9]+$");
                        Value(Substitute(tcTexto; ","; "."); "en-US")
                    )
                )
            };
            !IsBlank(tcValor) && tcValor > 0
        )
    );
    DisplayMode.Edit;
    DisplayMode.Disabled
)
```

## btnVolverPDF.OnSelect

```powerfx
Back()
```

## btnVolverPDF.Visible

```powerfx
Not('COMPROBANTE PDF'.Printing)
```

## lblLimiteImpresionPDF.Visible

```powerfx
Not('COMPROBANTE PDF'.Printing) && !IsBlank(varP9ComprobanteID) && !IsBlank(varP9Comprobante.ID) && varP9Comprobante.ID = varP9ComprobanteID && varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO" &&
!(
    With(
        {
            descTexto: Coalesce(varP9Comprobante.DESCRIPCION, ""),
            obsTexto: Coalesce(varP9Comprobante.OBSERVACION, "")
        },
        Len(Coalesce(varP9Comprobante.CODIGO_ASIGNACION, "")) <= 26 &&
        Len(Coalesce(varP9Comprobante.BANCO, "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.CUENTA_BANCARIA, "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.HORA_MOVIMIENTO, "")) <= 35 &&
        Len(Coalesce(varP9Comprobante.ESTUDIANTE, "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SOLICITADO_POR, "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SEDE_ASIGNACION, "")) <= 48 &&
        Len(Coalesce(varP9Comprobante.USUARIO_ASIGNACION, "")) <= 50 &&
        RoundUp(Len(descTexto) / 62, 0) + Len(descTexto) - Len(Substitute(descTexto, Char(10), "")) <= 5 &&
        RoundUp(Len(obsTexto) / 64, 0) + Len(obsTexto) - Len(Substitute(obsTexto, Char(10), "")) <= 5
    )
)
```

Con separadores regionales:

```powerfx
Not('COMPROBANTE PDF'.Printing) && !IsBlank(varP9ComprobanteID) && !IsBlank(varP9Comprobante.ID) && varP9Comprobante.ID = varP9ComprobanteID && varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO" &&
!(
    With(
        {
            descTexto: Coalesce(varP9Comprobante.DESCRIPCION; "");
            obsTexto: Coalesce(varP9Comprobante.OBSERVACION; "")
        };
        Len(Coalesce(varP9Comprobante.CODIGO_ASIGNACION; "")) <= 26 &&
        Len(Coalesce(varP9Comprobante.BANCO; "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.CUENTA_BANCARIA; "")) <= 28 &&
        Len(Coalesce(varP9Comprobante.HORA_MOVIMIENTO; "")) <= 35 &&
        Len(Coalesce(varP9Comprobante.ESTUDIANTE; "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SOLICITADO_POR; "")) <= 51 &&
        Len(Coalesce(varP9Comprobante.SEDE_ASIGNACION; "")) <= 48 &&
        Len(Coalesce(varP9Comprobante.USUARIO_ASIGNACION; "")) <= 50 &&
        RoundUp(Len(descTexto) / 62; 0) + Len(descTexto) - Len(Substitute(descTexto; Char(10); "")) <= 5 &&
        RoundUp(Len(obsTexto) / 64; 0) + Len(obsTexto) - Len(Substitute(obsTexto; Char(10); "")) <= 5
    )
)
```

## lblLimiteImpresionPDF.Text

```powerfx
"El contenido supera el espacio de una página A4. La impresión está deshabilitada para evitar un documento incompleto."
```

## lblCodigoValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.CODIGO_ASIGNACION, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.CODIGO_ASIGNACION; "—")
```

## lblBancoValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.BANCO, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.BANCO; "—")
```

## lblCuentaValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.CUENTA_BANCARIA, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.CUENTA_BANCARIA; "—")
```

## lblFechaMovValorPDF.Text

```powerfx
If(IsBlank(varP9Comprobante.FECHA_MOVIMIENTO), "—", Text(varP9Comprobante.FECHA_MOVIMIENTO, "dd/mm/yyyy", "es-ES"))
& " · " & Coalesce(varP9Comprobante.HORA_MOVIMIENTO, "—")
```

Con separadores regionales:

```powerfx
If(IsBlank(varP9Comprobante.FECHA_MOVIMIENTO); "—"; Text(varP9Comprobante.FECHA_MOVIMIENTO; "dd/mm/yyyy"; "es-ES"))
& " · " & Coalesce(varP9Comprobante.HORA_MOVIMIENTO; "—")
```

## lblImporteValorPDF.Text

```powerfx
If(
    IsBlank(varP9Comprobante.IMPORTE),
    "—",
    If(IsBlank(varP9Comprobante.MONEDA), "", varP9Comprobante.MONEDA & " ")
    & Text(varP9Comprobante.IMPORTE, "#,##0.00", "es-ES")
)
```

Con separadores regionales:

```powerfx
If(
    IsBlank(varP9Comprobante.IMPORTE);
    "—";
    If(IsBlank(varP9Comprobante.MONEDA); ""; varP9Comprobante.MONEDA & " ")
    & Text(varP9Comprobante.IMPORTE; "#,##0.00"; "es-ES")
)
```

## lblEstadoValorPDF.Text

```powerfx
If(varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO", "CONFIRMADO", "")
```

Con separadores regionales:

```powerfx
If(varP9Comprobante.ESTADO_ASIGNACION.Value = "ASIGNADO"; "CONFIRMADO"; "")
```

## lblCuentaContableValorPDF.Text

```powerfx
With(
    {cuentaNormalizada: Substitute(Substitute(Substitute(Coalesce(varP9Comprobante.CUENTA_BANCARIA, ""), "-", ""), " ", ""), ".", "")},
    Switch(
        cuentaNormalizada,
        "3000100152", "110103012",
        "3000100705", "110103022",
        "696870039", "110103032",
        "0696870039", "110103032",
        "3015005684397", "110103042",
        "13224552", "110103052",
        "3041210569", "110103062",
        "4010879042", "110103072",
        "3400041236", "110104012",
        "696872023", "110104022",
        "0696872023", "110104022",
        "3015005425271", "110104032",
        "23224544", "110104042",
        "3051446946", "110103722",
        "0696876517", "110105112",
        "696876517", "110105112",
        "3501936692", "110103712",
        "10000003224552", "110103052",
        "20000003224544", "110104042",
        "1000872489", "110103072",
        "SIN MAPEO"
    )
)
```

Con separadores regionales:

```powerfx
With(
    {cuentaNormalizada: Substitute(Substitute(Substitute(Coalesce(varP9Comprobante.CUENTA_BANCARIA; ""); "-"; ""); " "; ""); "."; "")};
    Switch(
        cuentaNormalizada;
        "3000100152"; "110103012";
        "3000100705"; "110103022";
        "696870039"; "110103032";
        "0696870039"; "110103032";
        "3015005684397"; "110103042";
        "13224552"; "110103052";
        "3041210569"; "110103062";
        "4010879042"; "110103072";
        "3400041236"; "110104012";
        "696872023"; "110104022";
        "0696872023"; "110104022";
        "3015005425271"; "110104032";
        "23224544"; "110104042";
        "3051446946"; "110103722";
        "0696876517"; "110105112";
        "696876517"; "110105112";
        "3501936692"; "110103712";
        "10000003224552"; "110103052";
        "20000003224544"; "110104042";
        "1000872489"; "110103072";
        "SIN MAPEO"
    )
)
```

## lblTipoCambioTituloPDF.Visible

```powerfx
varP9Comprobante.MONEDA = "USD"
```

## txtTipoCambioPDF.Visible

```powerfx
varP9Comprobante.MONEDA = "USD" && Not('COMPROBANTE PDF'.Printing)
```

## lblTipoCambioValorPDF.Visible

```powerfx
varP9Comprobante.MONEDA = "USD" && 'COMPROBANTE PDF'.Printing
```

## lblTipoCambioValorPDF.Text

```powerfx
With(
    {
        tcValor: With(
            {tcTexto: Trim(txtTipoCambioPDF.Text)},
            If(
                IsMatch(tcTexto, "^[0-9]+$") || IsMatch(tcTexto, "^[0-9]+[.,][0-9]+$"),
                Value(Substitute(tcTexto, ",", "."), "en-US")
            )
        )
    },
    If(!IsBlank(tcValor) && tcValor > 0, Text(tcValor, "0.00####", "es-ES"), "—")
)
```

Con separadores regionales:

```powerfx
With(
    {
        tcValor: With(
            {tcTexto: Trim(txtTipoCambioPDF.Text)};
            If(
                IsMatch(tcTexto; "^[0-9]+$") || IsMatch(tcTexto; "^[0-9]+[.,][0-9]+$");
                Value(Substitute(tcTexto; ","; "."); "en-US")
            )
        )
    };
    If(!IsBlank(tcValor) && tcValor > 0; Text(tcValor; "0.00####"; "es-ES"); "—")
)
```

## lblEquivalenteTituloPDF.Visible

```powerfx
varP9Comprobante.MONEDA = "USD"
```

## lblEquivalenteValorPDF.Visible

```powerfx
varP9Comprobante.MONEDA = "USD"
```

## lblEquivalenteValorPDF.Text

```powerfx
With(
    {
        tcValor: With(
            {tcTexto: Trim(txtTipoCambioPDF.Text)},
            If(
                IsMatch(tcTexto, "^[0-9]+$") || IsMatch(tcTexto, "^[0-9]+[.,][0-9]+$"),
                Value(Substitute(tcTexto, ",", "."), "en-US")
            )
        )
    },
    If(
        IsBlank(varP9Comprobante.IMPORTE),
        "—",
        !IsBlank(tcValor) && tcValor > 0,
        "Bs " & Text(varP9Comprobante.IMPORTE * tcValor, "#,##0.00", "es-ES"),
        IsBlank(Trim(txtTipoCambioPDF.Text)),
        "Ingrese TC",
        "TC no válido"
    )
)
```

Con separadores regionales:

```powerfx
With(
    {
        tcValor: With(
            {tcTexto: Trim(txtTipoCambioPDF.Text)};
            If(
                IsMatch(tcTexto; "^[0-9]+$") || IsMatch(tcTexto; "^[0-9]+[.,][0-9]+$");
                Value(Substitute(tcTexto; ","; "."); "en-US")
            )
        )
    };
    If(
        IsBlank(varP9Comprobante.IMPORTE);
        "—";
        !IsBlank(tcValor) && tcValor > 0;
        "Bs " & Text(varP9Comprobante.IMPORTE * tcValor; "#,##0.00"; "es-ES");
        IsBlank(Trim(txtTipoCambioPDF.Text));
        "Ingrese TC";
        "TC no válido"
    )
)
```

## lblEstudianteValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.ESTUDIANTE, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.ESTUDIANTE; "—")
```

## lblSolicitadoValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.SOLICITADO_POR, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.SOLICITADO_POR; "—")
```

## lblSedeValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.SEDE_ASIGNACION, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.SEDE_ASIGNACION; "—")
```

## lblConfirmadoValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.USUARIO_ASIGNACION, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.USUARIO_ASIGNACION; "—")
```

## lblFechaConfirmValorPDF.Text

```powerfx
If(IsBlank(varP9Comprobante.FECHA_HORA_ASIGNACION), "—", Text(varP9Comprobante.FECHA_HORA_ASIGNACION, "dd/mm/yyyy hh:mm:ss", "es-ES"))
```

Con separadores regionales:

```powerfx
If(IsBlank(varP9Comprobante.FECHA_HORA_ASIGNACION); "—"; Text(varP9Comprobante.FECHA_HORA_ASIGNACION; "dd/mm/yyyy hh:mm:ss"; "es-ES"))
```

## lblObsValorPDF.Text

```powerfx
If(IsBlank(TrimEnds(Coalesce(varP9Comprobante.OBSERVACION, ""))), "Sin observación", varP9Comprobante.OBSERVACION)
```

Con separadores regionales:

```powerfx
If(IsBlank(TrimEnds(Coalesce(varP9Comprobante.OBSERVACION; ""))); "Sin observación"; varP9Comprobante.OBSERVACION)
```

## lblMonedaValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.MONEDA, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.MONEDA; "—")
```

## lblDescripcionValorPDF.Text

```powerfx
Coalesce(varP9Comprobante.DESCRIPCION, "—")
```

Con separadores regionales:

```powerfx
Coalesce(varP9Comprobante.DESCRIPCION; "—")
```
