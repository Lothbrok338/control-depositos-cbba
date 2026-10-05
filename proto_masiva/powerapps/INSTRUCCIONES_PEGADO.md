# Armar la pantalla `P9_Confirmacion_Masiva` en Power Apps Studio

**Trabaja en una COPIA de la app P9** (Guardar como → `P9_PRUEBA_MASIVA`). No publiques sobre la app productiva. Procedimiento de pegado = el que ya usaste con `COMPROBANTE PDF`: controles hijos pegados con clic derecho → Pegar, y las fórmulas de pantalla escritas a mano después.

Antes: crea la lista (`sharepoint/INSTRUCCIONES_LISTA.md`) e importa el flujo (`flows/INSTRUCCIONES_FLUJO.md`).

> **Separadores regionales.** El YAML se pega siempre en sintaxis canónica (comas). Las fórmulas que escribes a mano abajo también están en canónica: si tu barra de fórmulas usa `;` como separador de argumentos, cambia las comas de argumentos por `;` y el `;` entre sentencias por `;;`.

## Pasos

1. **Datos.** *Datos → Agregar datos → SharePoint* → sitio P9 → lista `P9_MASIVA_PROTO_LOTES` → Conectar. (No se agrega ningún flujo a la app: el flujo se dispara solo.)
2. **Pantalla.** *Insertar → Nueva pantalla → En blanco*. Renómbrala `P9_Confirmacion_Masiva`.
3. **Formulario (control manual 1 de 2).** *Insertar → Formularios → Editar*. Propiedades:
   - Nombre: `frmLoteP9` · `DataSource` = `P9_MASIVA_PROTO_LOTES` · `DefaultMode` = `FormMode.New` · `Item` = (vacío)
   - `X` = 30 · `Y` = 215 · `Width` = 540 · `Height` = 140
   - *Editar campos*: quita todo (Title, etc.) y deja **solo «Datos adjuntos»**.
   - Selecciona el control de adjuntos de esa tarjeta, renómbralo **`attXlsxP9`** y pon `MaxAttachments` = `1`, `MaxAttachmentSize` = `5` (MB).
   - `OnSuccess`:
     ```
     IfError(
         Set(varLoteP9, Patch(P9_MASIVA_PROTO_LOTES, frmLoteP9.LastSubmit, {Title: varUidP9, LOTE_UID: varUidP9, ESTADO: "CARGADO", ARCHIVO_NOMBRE: varNombreP9, MENSAJE: "Archivo cargado. En cola para prevalidar.", FILAS_LEIDAS: 0, FECHA_CREACION: Now()}));
         Set(varLoteP9, Patch(P9_MASIVA_PROTO_LOTES, varLoteP9, {ESTADO: "PENDIENTE"}));
         Set(varLoteVivoP9, varLoteP9);
         Set(varTicksP9, 0);
         Set(varSondeoP9, true),
         Notify("El archivo se cargó pero no se pudo poner en cola. Pulse PREVALIDAR de nuevo.", NotificationType.Error)
     );
     Set(varSubiendoP9, false);
     ResetForm(frmLoteP9)
     ```
   - `OnFailure`: `Set(varSubiendoP9, false); Notify("No se pudo crear el lote: " & frmLoteP9.Error, NotificationType.Error)`
4. **Temporizador (control manual 2 de 2).** *Insertar → Entrada → Temporizador*. Nombre `tmrSondeoP9` · `Duration` = `5000` · `Repeats` = `true` · `AutoStart` = `false` · `Visible` = `false` · `Start` = `Coalesce(varSondeoP9, false)` · `OnTimerEnd`:
   ```
   Set(varTicksP9, Coalesce(varTicksP9, 0) + 1);
   IfError(
       Refresh(P9_MASIVA_PROTO_LOTES);
       Set(varLoteVivoP9, LookUp(P9_MASIVA_PROTO_LOTES, ID = varLoteP9.ID)),
       Notify("No se pudo consultar el estado del lote.", NotificationType.Warning)
   );
   If(
       Coalesce(varLoteVivoP9.ESTADO, "") = "COMPLETADO" || Coalesce(varLoteVivoP9.ESTADO, "") = "ERROR" || varTicksP9 >= 72,
       Set(varSondeoP9, false)
   )
   ```
   (5 s × 72 = 6 min máximo de sondeo; el disparador de SharePoint puede tardar ~1 min en arrancar, ver `RESULTADO_PROTOTIPO.md`.)
5. **Pegar los controles.** Abre `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml`, copia **todo** → en Studio selecciona la pantalla → clic derecho → **Pegar**. Los demás controles son hijos de `cntImportacionMasivaP9`. Los 3 controles manuales (`frmLoteP9`, `attXlsxP9`, `tmrSondeoP9`) ya existían, por eso las fórmulas se resuelven. Si ya había un control con el mismo nombre, Studio añade `_1` y las fórmulas dejan de resolverse: bórralo antes de pegar.
6. **Fórmulas de la pantalla** (barra de fórmulas con la pantalla seleccionada):
   - `OnVisible`:
     ```
     Set(varLoteP9, Blank());
     Set(varLoteVivoP9, Blank());
     Set(varSondeoP9, false);
     Set(varTicksP9, 0);
     Set(varSubiendoP9, false);
     Set(varUrlPlantillaP9, "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu/Documents/P9_MASIVA_PROTO/Plantilla_Confirmacion_Masiva_P9.xlsx?download=1");
     ResetForm(frmLoteP9)
     ```
   - `OnHidden`: `Set(varSondeoP9, false)`
7. **Botón en Main_Screen.** Sigue `BOTON_MAIN_SCREEN.txt` (un único control nuevo).
8. **Comprobador de aplicaciones.** Revisa que no haya errores nuevos en `P9_Confirmacion_Masiva` ni en `Main_Screen`. Verifica en el árbol que `frmLoteP9`, `tmrSondeoP9` y `cntImportacionMasivaP9` sean hijos directos de la pantalla.
9. **Probar** (F5 desde `Main_Screen`; el botón navega con `Navigate(P9_Confirmacion_Masiva, ScreenTransition.Fade)`).
10. **Prueba de humo, cinco archivos** (están en `xlsx/` y en `RESULTADO_PROTOTIPO.md` con el resultado esperado):
    `Plantilla_Confirmacion_Masiva_P9.xlsx` → COMPLETADO, 3 filas · `…_VACIA.xlsx` → ERROR/ARCHIVO_VACIO · `03_SIN_TABLA.xlsx` → ERROR/TABLA_NO_ENCONTRADA · `05_ENCABEZADO_CAMBIADO.xlsx` → ERROR/ESTRUCTURA_INVALIDA · `04_TABLA_NOMBRE_DISTINTO.xlsx` → ERROR/TABLA_NO_ENCONTRADA.

## Qué NO se toca

`btnConfirmarDepositoP9_1`, `galDepositosP9_1`, filtros, selector de banco, REVERSIÓN PENDIENTE, `COMPROBANTE PDF`, `P9_ASIGNAR_DEPOSITO`. La pantalla nueva no usa `Depositos_Activos`.

## Si algo no coincide

- El botón PREVALIDAR queda deshabilitado aunque haya archivo → el nombre del control de adjuntos no es `attXlsxP9`, o el archivo no termina en `.xlsx`.
- El lote se queda en `CARGADO` → falló el segundo `Patch` de `OnSuccess` (revisa que `ESTADO` sea columna de **texto**).
- El lote se queda en `PENDIENTE` más de ~3 min → el flujo está apagado o su disparador no apunta a la lista (ver `INSTRUCCIONES_FLUJO.md`, punto 1).
- DESCARGAR PLANTILLA abre la página de SharePoint en vez de descargar → el archivo no está en `Documents/P9_MASIVA_PROTO` o falta permiso; quita `?download=1` y prueba de nuevo.
