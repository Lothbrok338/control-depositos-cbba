# Fórmulas exactas — P9 / comprobante

Extraídas de los YAML entregados. No incluyen el `=` inicial del formato YAML.

La variante canónica usa comas entre argumentos y `;` entre acciones. Para una barra de fórmulas con separadores españoles se incluye la variante con `;` y `;;`. Las cadenas, incluido `"#,##0.00"`, se conservan. Los YAML completos ya usan la variante de la base validada.

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
794
```

## 'COMPROBANTE PDF'.Height

```powerfx
1123
```

## 'COMPROBANTE PDF'.OnVisible

```powerfx
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
Set(varP9Comprobante, Blank());
Set(varP9ComprobanteID, Blank())
```

Con separadores regionales:

```powerfx
Set(varP9Comprobante; Blank());;
Set(varP9ComprobanteID; Blank())
```

## cntComprobantePDF.Height

```powerfx
lblFirmaPDF.Y + lblFirmaPDF.Height + 16
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
If(cntComprobantePDF.Visible && cntComprobantePDF.Y + cntComprobantePDF.Height <= Parent.Height - 24, DisplayMode.Edit, DisplayMode.Disabled)
```

Con separadores regionales:

```powerfx
If(cntComprobantePDF.Visible && cntComprobantePDF.Y + cntComprobantePDF.Height <= Parent.Height - 24; DisplayMode.Edit; DisplayMode.Disabled)
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
Not('COMPROBANTE PDF'.Printing) && cntComprobantePDF.Visible && cntComprobantePDF.Y + cntComprobantePDF.Height > Parent.Height - 24
```

## lblLimiteImpresionPDF.Text

```powerfx
"El comprobante supera una página A4. La impresión está deshabilitada para evitar un documento incompleto."
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
