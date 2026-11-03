# Fórmulas exactas — solicitud de reversión P9

Referencia histórica de la extensión inicial de fase B. La pantalla vigente es `Main_Screen.yaml`; no reconstruirla desde estos fragmentos. El último YAML conserva sus nombres/sufijos, columnas y modal en la raíz. Consultar `FUENTES_DE_VERDAD.md` antes de pegar controles.

Artefacto local de fase B. Las pruebas estáticas no certifican Power Apps Studio ni conexiones del tenant.

### Instalación en una copia de la app

1. Conectar el flujo `P9_SOLICITAR_REVERSION` después de importarlo y configurar su conexión Office 365 Users como **Provided by run-only user**. SharePoint usa la conexión de servicio. La identidad se obtiene en el servidor.
2. En `SOLICITAR_REVERSION_PEGAR.yaml`, pegar primero `overlayReversionP9` y `cntSolicitarReversionP9` como últimos hijos de `cntControlDepositosP9`; el modal queda por encima de VER.
3. Pegar únicamente `btnSolicitarReversionP9` dentro de `cntConfirmarDepositoP9`, después de sus controles actuales. Ocupa X=`Parent.Width - 195`, Y=470, ancho 175, alto 42: el espacio del botón de confirmación, que está oculto al ver un depósito ASIGNADO. No se mueve ningún control previo.
4. Como alternativa, usar `P9_CONTROL_INGRESOS_CON_REVERSION.txt`, que contiene la base completa más esos controles. No pegar ambas alternativas en la misma pantalla.
5. Activar/verificar el manejo de errores de fórmulas que utiliza `IfError`; comprobar los dos caminos y las conversiones `ParseJSON` en Studio. El layout sigue siendo para la pantalla de escritorio de P9; el modal requiere al menos 690 píxeles de alto en su contenedor.

### Contrato y estados

`P9_SOLICITAR_REVERSION.Run(operacion, deposito_id, clave, etag_esperado, motivo, solicitud_uid)` recibe seis argumentos posicionales; CONSULTAR envía los tres últimos como cadenas vacías. No recibe correo ni identidad libre.

La respuesta contiene once campos de texto: `resultado`, `codigo`, `mensaje`, `solicitud_id`, `solicitud_uid`, `snapshot_json`, `etag`, `estado_solicitud`, `fase_proceso`, `resultado_tecnico` y `fecha_limite`. CONSULTAR devuelve `LISTO`, snapshot plano con estado como texto y ETag opaco. La UI convierte explícitamente sus campos dinámicos a texto/número. El snapshot íntegro autoritativo lo guarda el flujo.

ENVIAR devuelve `ENVIADA` solo al confirmar la creación; `EXISTENTE` para el mismo UID; `PENDIENTE_EXISTENTE` cuando otro UID mantiene el bloqueo; `CONFLICTO` cuando la validación de versión rechaza el envío; `ERROR` más un código en los demás casos. El backend debe resolver el UID existente **antes** de volver a validar la versión: una respuesta perdida debe poder recuperarse incluso después de ejecutar la reversión.

El texto de envío no afirma que ya se revirtió. Solo `resultado_tecnico = REVERTIDO` permite mostrar REVERTIDO. APROBADO, CONFLICTO, ERROR, YA_NO_ASIGNADO, NO_EJECUTADO y RECUPERACION_REQUERIDA conservan su significado. EXPIRADA se muestra como «EXPIRADA · SIN DECISIÓN · NO EJECUTADA»; el mensaje autoritativo del flujo puede indicar «VENCIDA — CIERRE PENDIENTE» mientras sigue activo el bloqueo.

Antes del envío se muestra el plazo de 168 horas; después, la fecha UTC que devolvió el servidor. El reloj del dispositivo no autoriza la ejecución ni libera una solicitud. Este modal muestra la respuesta de consulta/envío; el historial sigue siendo la fuente del resultado posterior de Approval y no se añade sondeo automático.

### Doble clic, cancelación y respuesta perdida

Al consultar una confirmación se crea un UID. Mientras se ejecuta una llamada se deshabilitan ambos botones. Al empezar ENVIAR se congelan UID, ID, clave, ETag y motivo. Un fallo de transporte, ERROR genérico o respuesta desconocida conserva ese conjunto y ofrece REINTENTAR MISMO ENVÍO. CANCELAR cierra el modal; no cancela una solicitud creada ni borra un envío incierto. Al abrirlo otra vez, incluso desde otro depósito, se recupera ese envío incierto antes de permitir uno nuevo. La incertidumbre nunca renueva el ETag.

Los datos se conservan durante la sesión de la app. Si se cierra/reinicia la app durante un envío incierto, consultar el historial por UID/usuario antes de repetir; la unicidad del backend sigue impidiendo dos solicitudes activas, pero no debe tratarse como confirmación de un envío cuyo resultado aún se desconoce. Guardar el identificador visible cuando se requiera revisión operativa.

Tras resolver la aprobación, usar el botón ACTUALIZAR existente para consultar los depósitos. No se modifica el registro seleccionado, la lógica de confirmación, los filtros o el comprobante. Un comprobante ya abierto conserva su vista. Una copia PDF previamente generada conserva su contenido.

### Formato de fórmulas

Los YAML usan comas entre argumentos y `;` entre acciones. Cada sección siguiente incluye la fórmula canónica sin el `=` de YAML; cuando difiere se añade la versión regional con `;` y `;;`. La conversión conserva cadenas e identificadores. Las pruebas comparan cada bloque con el YAML y su conversión. Se documentan todas las propiedades, incluidas medidas y estilos, para evitar referencias manuales incompletas.

## overlayReversionP9.Fill

```powerfx
RGBA(0, 0, 0, 0.55)
```

Con separadores regionales:

```powerfx
RGBA(0; 0; 0; 0.55)
```

## overlayReversionP9.Height

```powerfx
Parent.Height
```

## overlayReversionP9.Visible

```powerfx
Coalesce(varP9RevVisible, false)
```

Con separadores regionales:

```powerfx
Coalesce(varP9RevVisible; false)
```

## overlayReversionP9.Width

```powerfx
Parent.Width
```

## overlayReversionP9.X

```powerfx
0
```

## overlayReversionP9.Y

```powerfx
0
```

## cntSolicitarReversionP9.DropShadow

```powerfx
DropShadow.None
```

## cntSolicitarReversionP9.Fill

```powerfx
RGBA(255, 255, 255, 1)
```

Con separadores regionales:

```powerfx
RGBA(255; 255; 255; 1)
```

## cntSolicitarReversionP9.Height

```powerfx
650
```

## cntSolicitarReversionP9.RadiusBottomLeft

```powerfx
12
```

## cntSolicitarReversionP9.RadiusBottomRight

```powerfx
12
```

## cntSolicitarReversionP9.RadiusTopLeft

```powerfx
12
```

## cntSolicitarReversionP9.RadiusTopRight

```powerfx
12
```

## cntSolicitarReversionP9.Visible

```powerfx
Coalesce(varP9RevVisible, false)
```

Con separadores regionales:

```powerfx
Coalesce(varP9RevVisible; false)
```

## cntSolicitarReversionP9.Width

```powerfx
Min(900, Parent.Width - 60)
```

Con separadores regionales:

```powerfx
Min(900; Parent.Width - 60)
```

## cntSolicitarReversionP9.X

```powerfx
(Parent.Width - Self.Width) / 2
```

## cntSolicitarReversionP9.Y

```powerfx
(Parent.Height - Self.Height) / 2
```

## rectCabeceraReversionP9.BorderStyle

```powerfx
BorderStyle.None
```

## rectCabeceraReversionP9.Fill

```powerfx
RGBA(123, 22, 50, 1)
```

Con separadores regionales:

```powerfx
RGBA(123; 22; 50; 1)
```

## rectCabeceraReversionP9.Height

```powerfx
62
```

## rectCabeceraReversionP9.Width

```powerfx
Parent.Width
```

## rectCabeceraReversionP9.X

```powerfx
0
```

## rectCabeceraReversionP9.Y

```powerfx
0
```

## lblTituloReversionP9.Color

```powerfx
RGBA(255, 255, 255, 1)
```

Con separadores regionales:

```powerfx
RGBA(255; 255; 255; 1)
```

## lblTituloReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblTituloReversionP9.Height

```powerfx
38
```

## lblTituloReversionP9.Size

```powerfx
17
```

## lblTituloReversionP9.Text

```powerfx
"SOLICITAR REVERSIÓN"
```

## lblTituloReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblTituloReversionP9.X

```powerfx
24
```

## lblTituloReversionP9.Y

```powerfx
12
```

## lblTituloReversionP9.FontWeight

```powerfx
FontWeight.Bold
```

## lblDepositoReversionP9.Color

```powerfx
RGBA(52, 55, 58, 1)
```

Con separadores regionales:

```powerfx
RGBA(52; 55; 58; 1)
```

## lblDepositoReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblDepositoReversionP9.Height

```powerfx
80
```

## lblDepositoReversionP9.Size

```powerfx
10
```

## lblDepositoReversionP9.Text

```powerfx
"CÓDIGO: " & Coalesce(varP9RevSnapshot.CODIGO_ASIGNACION, "—")
& Char(10) & "BANCO: " & Coalesce(varP9RevSnapshot.BANCO, "—")
& Char(10) & "CUENTA: " & Coalesce(varP9RevSnapshot.CUENTA_BANCARIA, "—")
& "     IMPORTE: " & varP9RevSnapshot.MONEDA & " " & Text(varP9RevSnapshot.IMPORTE, "#,##0.00", "es-ES")
```

Con separadores regionales:

```powerfx
"CÓDIGO: " & Coalesce(varP9RevSnapshot.CODIGO_ASIGNACION; "—")
& Char(10) & "BANCO: " & Coalesce(varP9RevSnapshot.BANCO; "—")
& Char(10) & "CUENTA: " & Coalesce(varP9RevSnapshot.CUENTA_BANCARIA; "—")
& "     IMPORTE: " & varP9RevSnapshot.MONEDA & " " & Text(varP9RevSnapshot.IMPORTE; "#,##0.00"; "es-ES")
```

## lblDepositoReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblDepositoReversionP9.X

```powerfx
24
```

## lblDepositoReversionP9.Y

```powerfx
76
```

## lblAsignacionReversionP9.Color

```powerfx
RGBA(52, 55, 58, 1)
```

Con separadores regionales:

```powerfx
RGBA(52; 55; 58; 1)
```

## lblAsignacionReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblAsignacionReversionP9.Height

```powerfx
80
```

## lblAsignacionReversionP9.Size

```powerfx
10
```

## lblAsignacionReversionP9.Text

```powerfx
"ESTUDIANTE: " & Coalesce(varP9RevSnapshot.ESTUDIANTE, "—")
& Char(10) & "CONFIRMADO POR: " & Coalesce(varP9RevSnapshot.USUARIO_ASIGNACION, "—")
& Char(10) & "FECHA DE CONFIRMACIÓN (UTC): " & Coalesce(varP9RevSnapshot.FECHA_HORA_ASIGNACION, "—")
```

Con separadores regionales:

```powerfx
"ESTUDIANTE: " & Coalesce(varP9RevSnapshot.ESTUDIANTE; "—")
& Char(10) & "CONFIRMADO POR: " & Coalesce(varP9RevSnapshot.USUARIO_ASIGNACION; "—")
& Char(10) & "FECHA DE CONFIRMACIÓN (UTC): " & Coalesce(varP9RevSnapshot.FECHA_HORA_ASIGNACION; "—")
```

## lblAsignacionReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblAsignacionReversionP9.X

```powerfx
24
```

## lblAsignacionReversionP9.Y

```powerfx
164
```

## lblMotivoReversionP9.Color

```powerfx
RGBA(52, 55, 58, 1)
```

Con separadores regionales:

```powerfx
RGBA(52; 55; 58; 1)
```

## lblMotivoReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblMotivoReversionP9.Height

```powerfx
22
```

## lblMotivoReversionP9.Size

```powerfx
9
```

## lblMotivoReversionP9.Text

```powerfx
"MOTIVO DE REVERSIÓN * (máximo 4.000 caracteres)"
```

## lblMotivoReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblMotivoReversionP9.X

```powerfx
24
```

## lblMotivoReversionP9.Y

```powerfx
258
```

## lblMotivoReversionP9.FontWeight

```powerfx
FontWeight.Semibold
```

## txtMotivoReversionP9.BorderColor

```powerfx
RGBA(217, 218, 221, 1)
```

Con separadores regionales:

```powerfx
RGBA(217; 218; 221; 1)
```

## txtMotivoReversionP9.Default

```powerfx
Coalesce(varP9RevMotivo, "")
```

Con separadores regionales:

```powerfx
Coalesce(varP9RevMotivo; "")
```

## txtMotivoReversionP9.DisplayMode

```powerfx
If(Coalesce(varP9RevCargando, false) || Coalesce(varP9RevEnvioIncierto, false) || Coalesce(varP9RevAceptada, false), DisplayMode.View, DisplayMode.Edit)
```

Con separadores regionales:

```powerfx
If(Coalesce(varP9RevCargando; false) || Coalesce(varP9RevEnvioIncierto; false) || Coalesce(varP9RevAceptada; false); DisplayMode.View; DisplayMode.Edit)
```

## txtMotivoReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## txtMotivoReversionP9.Height

```powerfx
100
```

## txtMotivoReversionP9.HintText

```powerfx
"Explica por qué se debe revertir la confirmación"
```

## txtMotivoReversionP9.MaxLength

```powerfx
4000
```

## txtMotivoReversionP9.Mode

```powerfx
TextMode.MultiLine
```

## txtMotivoReversionP9.OnChange

```powerfx
Set(varP9RevMotivo, Self.Text)
```

Con separadores regionales:

```powerfx
Set(varP9RevMotivo; Self.Text)
```

## txtMotivoReversionP9.Reset

```powerfx
!Coalesce(varP9RevVisible, false)
```

Con separadores regionales:

```powerfx
!Coalesce(varP9RevVisible; false)
```

## txtMotivoReversionP9.Size

```powerfx
10
```

## txtMotivoReversionP9.Width

```powerfx
Parent.Width - 48
```

## txtMotivoReversionP9.X

```powerfx
24
```

## txtMotivoReversionP9.Y

```powerfx
286
```

## lblPlazoReversionP9.Color

```powerfx
RGBA(52, 55, 58, 1)
```

Con separadores regionales:

```powerfx
RGBA(52; 55; 58; 1)
```

## lblPlazoReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblPlazoReversionP9.Height

```powerfx
42
```

## lblPlazoReversionP9.Size

```powerfx
9
```

## lblPlazoReversionP9.Text

```powerfx
If(
    IsBlank(varP9RevFechaLimite),
    "Plazo de decisión: 168 horas desde la creación de la solicitud.",
    "Fecha límite de decisión (UTC): " & varP9RevFechaLimite
) & Char(10) & "Las respuestas posteriores al plazo no ejecutan la reversión."
```

Con separadores regionales:

```powerfx
If(
    IsBlank(varP9RevFechaLimite);
    "Plazo de decisión: 168 horas desde la creación de la solicitud.";
    "Fecha límite de decisión (UTC): " & varP9RevFechaLimite
) & Char(10) & "Las respuestas posteriores al plazo no ejecutan la reversión."
```

## lblPlazoReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblPlazoReversionP9.X

```powerfx
24
```

## lblPlazoReversionP9.Y

```powerfx
398
```

## lblResultadoReversionP9.Color

```powerfx
RGBA(94, 16, 38, 1)
```

Con separadores regionales:

```powerfx
RGBA(94; 16; 38; 1)
```

## lblResultadoReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblResultadoReversionP9.Height

```powerfx
94
```

## lblResultadoReversionP9.Size

```powerfx
9
```

## lblResultadoReversionP9.Text

```powerfx
If(
    varP9RevFase = "EXPIRADA",
    "EXPIRADA · SIN DECISIÓN · NO EJECUTADA",
    varP9RevResultadoTecnico = "REVERTIDO",
    "REVERTIDO · ID " & varP9RevSolicitudID,
    varP9RevFase = "RECUPERACION_REQUERIDA",
    "RESULTADO PENDIENTE DE VERIFICACIÓN · ID " & varP9RevSolicitudID,
    !IsBlank(varP9RevSolicitudID),
    Coalesce(varP9RevDecision, "PENDIENTE") & " · " & Coalesce(varP9RevFase, "RECIBIDA") & " · " & Coalesce(varP9RevResultadoTecnico, "PENDIENTE"),
    ""
) & If(!IsBlank(varP9RevSolicitudID) || varP9RevFase = "EXPIRADA", Char(10), "") & varP9RevMensaje
```

Con separadores regionales:

```powerfx
If(
    varP9RevFase = "EXPIRADA";
    "EXPIRADA · SIN DECISIÓN · NO EJECUTADA";
    varP9RevResultadoTecnico = "REVERTIDO";
    "REVERTIDO · ID " & varP9RevSolicitudID;
    varP9RevFase = "RECUPERACION_REQUERIDA";
    "RESULTADO PENDIENTE DE VERIFICACIÓN · ID " & varP9RevSolicitudID;
    !IsBlank(varP9RevSolicitudID);
    Coalesce(varP9RevDecision; "PENDIENTE") & " · " & Coalesce(varP9RevFase; "RECIBIDA") & " · " & Coalesce(varP9RevResultadoTecnico; "PENDIENTE");
    ""
) & If(!IsBlank(varP9RevSolicitudID) || varP9RevFase = "EXPIRADA"; Char(10); "") & varP9RevMensaje
```

## lblResultadoReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblResultadoReversionP9.X

```powerfx
24
```

## lblResultadoReversionP9.Y

```powerfx
448
```

## btnCancelarReversionP9.BorderColor

```powerfx
RGBA(98, 102, 106, 1)
```

Con separadores regionales:

```powerfx
RGBA(98; 102; 106; 1)
```

## btnCancelarReversionP9.BorderThickness

```powerfx
1
```

## btnCancelarReversionP9.Color

```powerfx
RGBA(52, 55, 58, 1)
```

Con separadores regionales:

```powerfx
RGBA(52; 55; 58; 1)
```

## btnCancelarReversionP9.DisplayMode

```powerfx
If(Coalesce(varP9RevCargando, false), DisplayMode.Disabled, DisplayMode.Edit)
```

Con separadores regionales:

```powerfx
If(Coalesce(varP9RevCargando; false); DisplayMode.Disabled; DisplayMode.Edit)
```

## btnCancelarReversionP9.Fill

```powerfx
RGBA(255, 255, 255, 1)
```

Con separadores regionales:

```powerfx
RGBA(255; 255; 255; 1)
```

## btnCancelarReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## btnCancelarReversionP9.Height

```powerfx
42
```

## btnCancelarReversionP9.OnSelect

```powerfx
Set(varP9RevVisible, false)
```

Con separadores regionales:

```powerfx
Set(varP9RevVisible; false)
```

## btnCancelarReversionP9.Size

```powerfx
9
```

## btnCancelarReversionP9.Text

```powerfx
"CANCELAR"
```

## btnCancelarReversionP9.Width

```powerfx
125
```

## btnCancelarReversionP9.X

```powerfx
24
```

## btnCancelarReversionP9.Y

```powerfx
560
```

## btnEnviarReversionP9.BorderStyle

```powerfx
BorderStyle.None
```

## btnEnviarReversionP9.Color

```powerfx
RGBA(255, 255, 255, 1)
```

Con separadores regionales:

```powerfx
RGBA(255; 255; 255; 1)
```

## btnEnviarReversionP9.DisplayMode

```powerfx
If(
    Coalesce(varP9RevCargando, false) ||
    Coalesce(varP9RevAceptada, false) ||
    !Coalesce(varP9RevValida, false) ||
    IsBlank(varP9RevUID) || IsBlank(varP9RevETag) ||
    IsBlank(Trim(txtMotivoReversionP9.Text)) || Len(Trim(txtMotivoReversionP9.Text)) > 4000,
    DisplayMode.Disabled,
    DisplayMode.Edit
)
```

Con separadores regionales:

```powerfx
If(
    Coalesce(varP9RevCargando; false) ||
    Coalesce(varP9RevAceptada; false) ||
    !Coalesce(varP9RevValida; false) ||
    IsBlank(varP9RevUID) || IsBlank(varP9RevETag) ||
    IsBlank(Trim(txtMotivoReversionP9.Text)) || Len(Trim(txtMotivoReversionP9.Text)) > 4000;
    DisplayMode.Disabled;
    DisplayMode.Edit
)
```

## btnEnviarReversionP9.Fill

```powerfx
RGBA(123, 22, 50, 1)
```

Con separadores regionales:

```powerfx
RGBA(123; 22; 50; 1)
```

## btnEnviarReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## btnEnviarReversionP9.FontWeight

```powerfx
FontWeight.Bold
```

## btnEnviarReversionP9.Height

```powerfx
42
```

## btnEnviarReversionP9.OnSelect

```powerfx
If(
    !Coalesce(varP9RevValida, false) ||
    Coalesce(varP9RevCargando, false) ||
    Coalesce(varP9RevAceptada, false) ||
    IsBlank(varP9RevUID) ||
    IsBlank(varP9RevETag) ||
    IsBlank(Trim(txtMotivoReversionP9.Text)) ||
    Len(Trim(txtMotivoReversionP9.Text)) > 4000,
    Notify("Completa un motivo de hasta 4.000 caracteres y consulta una confirmación vigente.", NotificationType.Warning),
    If(
        !Coalesce(varP9RevEnvioIncierto, false),
        Set(varP9RevMotivoEnvio, Trim(txtMotivoReversionP9.Text));
        Set(varP9RevMotivo, varP9RevMotivoEnvio);
        Set(varP9RevEnvioIncierto, true)
    );
    Set(varP9RevCargando, true);
    IfError(
        Set(
            varP9RevRespuesta,
            P9_SOLICITAR_REVERSION.Run(
                "ENVIAR",
                varP9RevSnapshot.ID,
                varP9RevSnapshot.CLAVE_TRANSACCION,
                varP9RevETag,
                varP9RevMotivoEnvio,
                varP9RevUID
            )
        );
        If(
            (varP9RevRespuesta.resultado = "ENVIADA" || varP9RevRespuesta.resultado = "EXISTENTE" || varP9RevRespuesta.resultado = "PENDIENTE_EXISTENTE") &&
            (IsBlank(varP9RevRespuesta.solicitud_id) || Value(varP9RevRespuesta.solicitud_id) <= 0 ||
                ((varP9RevRespuesta.resultado = "ENVIADA" || varP9RevRespuesta.resultado = "EXISTENTE") && varP9RevRespuesta.solicitud_uid <> varP9RevUID)),
            Set(varP9RevMensaje, "La respuesta no identifica de forma completa la solicitud. Reintenta el mismo envío para verificarla."),
        Switch(
            varP9RevRespuesta.resultado,
            "ENVIADA",
                Set(varP9RevSolicitudID, varP9RevRespuesta.solicitud_id);
                Set(varP9RevFechaLimite, varP9RevRespuesta.fecha_limite);
                Set(varP9RevDecision, varP9RevRespuesta.estado_solicitud);
                Set(varP9RevFase, varP9RevRespuesta.fase_proceso);
                Set(varP9RevResultadoTecnico, varP9RevRespuesta.resultado_tecnico);
                Set(varP9RevAceptada, true);
                Set(varP9RevEnvioIncierto, false);
                Set(varP9RevMensaje, "SOLICITUD DE REVERSIÓN ENVIADA · ID " & varP9RevSolicitudID & ". La decisión y el resultado se muestran por separado.");
                Notify("SOLICITUD DE REVERSIÓN ENVIADA · ID " & varP9RevSolicitudID, NotificationType.Success),
            "EXISTENTE",
                Set(varP9RevSolicitudID, varP9RevRespuesta.solicitud_id);
                Set(varP9RevFechaLimite, varP9RevRespuesta.fecha_limite);
                Set(varP9RevDecision, varP9RevRespuesta.estado_solicitud);
                Set(varP9RevFase, varP9RevRespuesta.fase_proceso);
                Set(varP9RevResultadoTecnico, varP9RevRespuesta.resultado_tecnico);
                Set(varP9RevAceptada, true);
                Set(varP9RevEnvioIncierto, false);
                Set(varP9RevMensaje, "Se recuperó la solicitud existente · ID " & varP9RevSolicitudID & ". " & varP9RevRespuesta.mensaje),
            "PENDIENTE_EXISTENTE",
                Set(varP9RevSolicitudID, varP9RevRespuesta.solicitud_id);
                Set(varP9RevFechaLimite, varP9RevRespuesta.fecha_limite);
                Set(varP9RevDecision, varP9RevRespuesta.estado_solicitud);
                Set(varP9RevFase, varP9RevRespuesta.fase_proceso);
                Set(varP9RevResultadoTecnico, varP9RevRespuesta.resultado_tecnico);
                Set(varP9RevAceptada, true);
                Set(varP9RevEnvioIncierto, false);
                Set(varP9RevMensaje, "Ya existe una solicitud activa · ID " & varP9RevSolicitudID & ". " & varP9RevRespuesta.mensaje),
            "CONFLICTO",
                Set(varP9RevValida, false);
                Set(varP9RevEnvioIncierto, false);
                Set(varP9RevMensaje, "CONFLICTO: cambió la versión del depósito. Cierra este modal y vuelve a abrir VER para consultar los datos actuales."),
            Set(varP9RevMensaje, "No se confirmó la creación. " & Coalesce(varP9RevRespuesta.mensaje, "Reintenta el mismo envío.") & " (" & Coalesce(varP9RevRespuesta.codigo, "SIN_CODIGO") & "). Se conservan el identificador, la versión y el motivo.")
        ));
        true,
        Set(varP9RevMensaje, "No se recibió una respuesta concluyente. Reintenta el mismo envío para recuperar su resultado. Se conservan el identificador, la versión y el motivo.");
        Notify("Envío pendiente de verificar. No crees otra solicitud; usa REINTENTAR MISMO ENVÍO.", NotificationType.Warning);
        false
    );
    Set(varP9RevCargando, false)
)
```

Con separadores regionales:

```powerfx
If(
    !Coalesce(varP9RevValida; false) ||
    Coalesce(varP9RevCargando; false) ||
    Coalesce(varP9RevAceptada; false) ||
    IsBlank(varP9RevUID) ||
    IsBlank(varP9RevETag) ||
    IsBlank(Trim(txtMotivoReversionP9.Text)) ||
    Len(Trim(txtMotivoReversionP9.Text)) > 4000;
    Notify("Completa un motivo de hasta 4.000 caracteres y consulta una confirmación vigente."; NotificationType.Warning);
    If(
        !Coalesce(varP9RevEnvioIncierto; false);
        Set(varP9RevMotivoEnvio; Trim(txtMotivoReversionP9.Text));;
        Set(varP9RevMotivo; varP9RevMotivoEnvio);;
        Set(varP9RevEnvioIncierto; true)
    );;
    Set(varP9RevCargando; true);;
    IfError(
        Set(
            varP9RevRespuesta;
            P9_SOLICITAR_REVERSION.Run(
                "ENVIAR";
                varP9RevSnapshot.ID;
                varP9RevSnapshot.CLAVE_TRANSACCION;
                varP9RevETag;
                varP9RevMotivoEnvio;
                varP9RevUID
            )
        );;
        If(
            (varP9RevRespuesta.resultado = "ENVIADA" || varP9RevRespuesta.resultado = "EXISTENTE" || varP9RevRespuesta.resultado = "PENDIENTE_EXISTENTE") &&
            (IsBlank(varP9RevRespuesta.solicitud_id) || Value(varP9RevRespuesta.solicitud_id) <= 0 ||
                ((varP9RevRespuesta.resultado = "ENVIADA" || varP9RevRespuesta.resultado = "EXISTENTE") && varP9RevRespuesta.solicitud_uid <> varP9RevUID));
            Set(varP9RevMensaje; "La respuesta no identifica de forma completa la solicitud. Reintenta el mismo envío para verificarla.");
        Switch(
            varP9RevRespuesta.resultado;
            "ENVIADA";
                Set(varP9RevSolicitudID; varP9RevRespuesta.solicitud_id);;
                Set(varP9RevFechaLimite; varP9RevRespuesta.fecha_limite);;
                Set(varP9RevDecision; varP9RevRespuesta.estado_solicitud);;
                Set(varP9RevFase; varP9RevRespuesta.fase_proceso);;
                Set(varP9RevResultadoTecnico; varP9RevRespuesta.resultado_tecnico);;
                Set(varP9RevAceptada; true);;
                Set(varP9RevEnvioIncierto; false);;
                Set(varP9RevMensaje; "SOLICITUD DE REVERSIÓN ENVIADA · ID " & varP9RevSolicitudID & ". La decisión y el resultado se muestran por separado.");;
                Notify("SOLICITUD DE REVERSIÓN ENVIADA · ID " & varP9RevSolicitudID; NotificationType.Success);
            "EXISTENTE";
                Set(varP9RevSolicitudID; varP9RevRespuesta.solicitud_id);;
                Set(varP9RevFechaLimite; varP9RevRespuesta.fecha_limite);;
                Set(varP9RevDecision; varP9RevRespuesta.estado_solicitud);;
                Set(varP9RevFase; varP9RevRespuesta.fase_proceso);;
                Set(varP9RevResultadoTecnico; varP9RevRespuesta.resultado_tecnico);;
                Set(varP9RevAceptada; true);;
                Set(varP9RevEnvioIncierto; false);;
                Set(varP9RevMensaje; "Se recuperó la solicitud existente · ID " & varP9RevSolicitudID & ". " & varP9RevRespuesta.mensaje);
            "PENDIENTE_EXISTENTE";
                Set(varP9RevSolicitudID; varP9RevRespuesta.solicitud_id);;
                Set(varP9RevFechaLimite; varP9RevRespuesta.fecha_limite);;
                Set(varP9RevDecision; varP9RevRespuesta.estado_solicitud);;
                Set(varP9RevFase; varP9RevRespuesta.fase_proceso);;
                Set(varP9RevResultadoTecnico; varP9RevRespuesta.resultado_tecnico);;
                Set(varP9RevAceptada; true);;
                Set(varP9RevEnvioIncierto; false);;
                Set(varP9RevMensaje; "Ya existe una solicitud activa · ID " & varP9RevSolicitudID & ". " & varP9RevRespuesta.mensaje);
            "CONFLICTO";
                Set(varP9RevValida; false);;
                Set(varP9RevEnvioIncierto; false);;
                Set(varP9RevMensaje; "CONFLICTO: cambió la versión del depósito. Cierra este modal y vuelve a abrir VER para consultar los datos actuales.");
            Set(varP9RevMensaje; "No se confirmó la creación. " & Coalesce(varP9RevRespuesta.mensaje; "Reintenta el mismo envío.") & " (" & Coalesce(varP9RevRespuesta.codigo; "SIN_CODIGO") & "). Se conservan el identificador, la versión y el motivo.")
        ));;
        true;
        Set(varP9RevMensaje; "No se recibió una respuesta concluyente. Reintenta el mismo envío para recuperar su resultado. Se conservan el identificador, la versión y el motivo.");;
        Notify("Envío pendiente de verificar. No crees otra solicitud; usa REINTENTAR MISMO ENVÍO."; NotificationType.Warning);;
        false
    );;
    Set(varP9RevCargando; false)
)
```

## btnEnviarReversionP9.Size

```powerfx
8
```

## btnEnviarReversionP9.Text

```powerfx
If(Coalesce(varP9RevCargando, false), "PROCESANDO…", Coalesce(varP9RevEnvioIncierto, false), "REINTENTAR MISMO ENVÍO", "ENVIAR SOLICITUD")
```

Con separadores regionales:

```powerfx
If(Coalesce(varP9RevCargando; false); "PROCESANDO…"; Coalesce(varP9RevEnvioIncierto; false); "REINTENTAR MISMO ENVÍO"; "ENVIAR SOLICITUD")
```

## btnEnviarReversionP9.Width

```powerfx
250
```

## btnEnviarReversionP9.X

```powerfx
Parent.Width - 274
```

## btnEnviarReversionP9.Y

```powerfx
560
```

## lblUIDReversionP9.Color

```powerfx
RGBA(52, 55, 58, 1)
```

Con separadores regionales:

```powerfx
RGBA(52; 55; 58; 1)
```

## lblUIDReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## lblUIDReversionP9.Height

```powerfx
20
```

## lblUIDReversionP9.Size

```powerfx
7
```

## lblUIDReversionP9.Text

```powerfx
"Identificador del envío: " & Coalesce(varP9RevUID, "—")
```

Con separadores regionales:

```powerfx
"Identificador del envío: " & Coalesce(varP9RevUID; "—")
```

## lblUIDReversionP9.Width

```powerfx
Parent.Width - 48
```

## lblUIDReversionP9.X

```powerfx
24
```

## lblUIDReversionP9.Y

```powerfx
614
```

## btnSolicitarReversionP9.BorderStyle

```powerfx
BorderStyle.None
```

## btnSolicitarReversionP9.Color

```powerfx
RGBA(255, 255, 255, 1)
```

Con separadores regionales:

```powerfx
RGBA(255; 255; 255; 1)
```

## btnSolicitarReversionP9.DisplayMode

```powerfx
If(Coalesce(varP9RevCargando, false), DisplayMode.Disabled, DisplayMode.Edit)
```

Con separadores regionales:

```powerfx
If(Coalesce(varP9RevCargando; false); DisplayMode.Disabled; DisplayMode.Edit)
```

## btnSolicitarReversionP9.Fill

```powerfx
RGBA(123, 22, 50, 1)
```

Con separadores regionales:

```powerfx
RGBA(123; 22; 50; 1)
```

## btnSolicitarReversionP9.Font

```powerfx
Font.'Segoe UI'
```

## btnSolicitarReversionP9.FontWeight

```powerfx
FontWeight.Bold
```

## btnSolicitarReversionP9.Height

```powerfx
42
```

## btnSolicitarReversionP9.OnSelect

```powerfx
If(
    Coalesce(varP9RevEnvioIncierto, false),
    Set(varP9RevVisible, true);
    Notify("Hay un envío pendiente de verificar. Reintenta con el mismo identificador y motivo.", NotificationType.Warning),
    Set(varP9RevCargando, true);
    Set(varP9RevVisible, false);
    Set(varP9RevValida, false);
    Set(varP9RevAceptada, false);
    Set(varP9RevSnapshot, Blank());
    Set(varP9RevUID, Blank());
    Set(varP9RevSolicitudID, Blank());
    Set(varP9RevFechaLimite, Blank());
    Set(varP9RevDecision, Blank());
    Set(varP9RevFase, Blank());
    Set(varP9RevResultadoTecnico, Blank());
    Set(varP9RevMotivo, "");
    Set(varP9RevMotivoEnvio, "");
    IfError(
        Set(
            varP9RevRespuesta,
            P9_SOLICITAR_REVERSION.Run(
                "CONSULTAR",
                varDepositoSeleccionado.ID,
                varDepositoSeleccionado.CLAVE_TRANSACCION,
                "",
                "",
                ""
            )
        );
        If(
            varP9RevRespuesta.resultado = "LISTO" || varP9RevRespuesta.resultado = "PENDIENTE_EXISTENTE",
            With(
                {s: ParseJSON(varP9RevRespuesta.snapshot_json)},
                Set(
                    varP9RevSnapshot,
                    {
                        ID: Value(s.ID),
                        CLAVE_TRANSACCION: Text(s.CLAVE_TRANSACCION),
                        ESTADO_ASIGNACION: Text(s.ESTADO_ASIGNACION),
                        CODIGO_ASIGNACION: Text(s.CODIGO_ASIGNACION),
                        BANCO: Text(s.BANCO),
                        CUENTA_BANCARIA: Text(s.CUENTA_BANCARIA),
                        IMPORTE: Value(s.IMPORTE),
                        MONEDA: Text(s.MONEDA),
                        ESTUDIANTE: Text(s.ESTUDIANTE),
                        USUARIO_ASIGNACION: Text(s.USUARIO_ASIGNACION),
                        FECHA_HORA_ASIGNACION: Text(s.FECHA_HORA_ASIGNACION)
                    }
                )
            );
            If(
                varP9RevRespuesta.resultado = "PENDIENTE_EXISTENTE",
                If(
                    IsBlank(varP9RevRespuesta.solicitud_id) || IsBlank(varP9RevRespuesta.solicitud_uid),
                    Notify("No se recibió la identificación completa de la solicitud activa. Vuelve a consultar.", NotificationType.Warning),
                    Set(varP9RevUID, varP9RevRespuesta.solicitud_uid);
                    Set(varP9RevSolicitudID, varP9RevRespuesta.solicitud_id);
                    Set(varP9RevFechaLimite, varP9RevRespuesta.fecha_limite);
                    Set(varP9RevDecision, varP9RevRespuesta.estado_solicitud);
                    Set(varP9RevFase, varP9RevRespuesta.fase_proceso);
                    Set(varP9RevResultadoTecnico, varP9RevRespuesta.resultado_tecnico);
                    Set(varP9RevAceptada, true);
                    Set(varP9RevMensaje, "Solicitud activa · ID " & varP9RevSolicitudID & ". " & varP9RevRespuesta.mensaje);
                    Set(varP9RevVisible, true)
                ),
            If(
                IsBlank(varP9RevSnapshot.ID) ||
                varP9RevSnapshot.ID <> varDepositoSeleccionado.ID ||
                varP9RevSnapshot.CLAVE_TRANSACCION <> varDepositoSeleccionado.CLAVE_TRANSACCION ||
                varP9RevSnapshot.ESTADO_ASIGNACION <> "ASIGNADO" ||
                IsBlank(varP9RevRespuesta.etag),
                Notify("No se recibió una confirmación vigente con su versión. Vuelve a abrir VER.", NotificationType.Warning),
                Set(varP9RevETag, varP9RevRespuesta.etag);
                Set(varP9RevUID, Lower(Text(GUID())));
                Set(varP9RevValida, true);
                Set(varP9RevMensaje, "Completa el motivo. El depósito se modificará únicamente si la solicitud es aprobada y su versión sigue vigente.");
                Set(varP9RevVisible, true)
            )),
            Notify(
                Coalesce(varP9RevRespuesta.mensaje, "No se puede solicitar la reversión de este depósito.") & " (" & Coalesce(varP9RevRespuesta.codigo, "SIN_CODIGO") & ")",
                NotificationType.Warning
            )
        );
        true,
        Set(varP9RevValida, false);
        Set(varP9RevVisible, false);
        Notify("No se pudo consultar la confirmación. No se envió ninguna solicitud desde este modal.", NotificationType.Error);
        false
    );
    Set(varP9RevCargando, false)
)
```

Con separadores regionales:

```powerfx
If(
    Coalesce(varP9RevEnvioIncierto; false);
    Set(varP9RevVisible; true);;
    Notify("Hay un envío pendiente de verificar. Reintenta con el mismo identificador y motivo."; NotificationType.Warning);
    Set(varP9RevCargando; true);;
    Set(varP9RevVisible; false);;
    Set(varP9RevValida; false);;
    Set(varP9RevAceptada; false);;
    Set(varP9RevSnapshot; Blank());;
    Set(varP9RevUID; Blank());;
    Set(varP9RevSolicitudID; Blank());;
    Set(varP9RevFechaLimite; Blank());;
    Set(varP9RevDecision; Blank());;
    Set(varP9RevFase; Blank());;
    Set(varP9RevResultadoTecnico; Blank());;
    Set(varP9RevMotivo; "");;
    Set(varP9RevMotivoEnvio; "");;
    IfError(
        Set(
            varP9RevRespuesta;
            P9_SOLICITAR_REVERSION.Run(
                "CONSULTAR";
                varDepositoSeleccionado.ID;
                varDepositoSeleccionado.CLAVE_TRANSACCION;
                "";
                "";
                ""
            )
        );;
        If(
            varP9RevRespuesta.resultado = "LISTO" || varP9RevRespuesta.resultado = "PENDIENTE_EXISTENTE";
            With(
                {s: ParseJSON(varP9RevRespuesta.snapshot_json)};
                Set(
                    varP9RevSnapshot;
                    {
                        ID: Value(s.ID);
                        CLAVE_TRANSACCION: Text(s.CLAVE_TRANSACCION);
                        ESTADO_ASIGNACION: Text(s.ESTADO_ASIGNACION);
                        CODIGO_ASIGNACION: Text(s.CODIGO_ASIGNACION);
                        BANCO: Text(s.BANCO);
                        CUENTA_BANCARIA: Text(s.CUENTA_BANCARIA);
                        IMPORTE: Value(s.IMPORTE);
                        MONEDA: Text(s.MONEDA);
                        ESTUDIANTE: Text(s.ESTUDIANTE);
                        USUARIO_ASIGNACION: Text(s.USUARIO_ASIGNACION);
                        FECHA_HORA_ASIGNACION: Text(s.FECHA_HORA_ASIGNACION)
                    }
                )
            );;
            If(
                varP9RevRespuesta.resultado = "PENDIENTE_EXISTENTE";
                If(
                    IsBlank(varP9RevRespuesta.solicitud_id) || IsBlank(varP9RevRespuesta.solicitud_uid);
                    Notify("No se recibió la identificación completa de la solicitud activa. Vuelve a consultar."; NotificationType.Warning);
                    Set(varP9RevUID; varP9RevRespuesta.solicitud_uid);;
                    Set(varP9RevSolicitudID; varP9RevRespuesta.solicitud_id);;
                    Set(varP9RevFechaLimite; varP9RevRespuesta.fecha_limite);;
                    Set(varP9RevDecision; varP9RevRespuesta.estado_solicitud);;
                    Set(varP9RevFase; varP9RevRespuesta.fase_proceso);;
                    Set(varP9RevResultadoTecnico; varP9RevRespuesta.resultado_tecnico);;
                    Set(varP9RevAceptada; true);;
                    Set(varP9RevMensaje; "Solicitud activa · ID " & varP9RevSolicitudID & ". " & varP9RevRespuesta.mensaje);;
                    Set(varP9RevVisible; true)
                );
            If(
                IsBlank(varP9RevSnapshot.ID) ||
                varP9RevSnapshot.ID <> varDepositoSeleccionado.ID ||
                varP9RevSnapshot.CLAVE_TRANSACCION <> varDepositoSeleccionado.CLAVE_TRANSACCION ||
                varP9RevSnapshot.ESTADO_ASIGNACION <> "ASIGNADO" ||
                IsBlank(varP9RevRespuesta.etag);
                Notify("No se recibió una confirmación vigente con su versión. Vuelve a abrir VER."; NotificationType.Warning);
                Set(varP9RevETag; varP9RevRespuesta.etag);;
                Set(varP9RevUID; Lower(Text(GUID())));;
                Set(varP9RevValida; true);;
                Set(varP9RevMensaje; "Completa el motivo. El depósito se modificará únicamente si la solicitud es aprobada y su versión sigue vigente.");;
                Set(varP9RevVisible; true)
            ));
            Notify(
                Coalesce(varP9RevRespuesta.mensaje; "No se puede solicitar la reversión de este depósito.") & " (" & Coalesce(varP9RevRespuesta.codigo; "SIN_CODIGO") & ")";
                NotificationType.Warning
            )
        );;
        true;
        Set(varP9RevValida; false);;
        Set(varP9RevVisible; false);;
        Notify("No se pudo consultar la confirmación. No se envió ninguna solicitud desde este modal."; NotificationType.Error);;
        false
    );;
    Set(varP9RevCargando; false)
)
```

## btnSolicitarReversionP9.Size

```powerfx
8
```

## btnSolicitarReversionP9.Text

```powerfx
"SOLICITAR REVERSIÓN"
```

## btnSolicitarReversionP9.Tooltip

```powerfx
"Solicitar la reversión de esta confirmación mediante aprobación"
```

## btnSolicitarReversionP9.Visible

```powerfx
!IsBlank(varDepositoSeleccionado.ID) && varDepositoSeleccionado.ESTADO_ASIGNACION.Value = "ASIGNADO"
```

## btnSolicitarReversionP9.Width

```powerfx
175
```

## btnSolicitarReversionP9.X

```powerfx
Parent.Width - 195
```

## btnSolicitarReversionP9.Y

```powerfx
470
```
