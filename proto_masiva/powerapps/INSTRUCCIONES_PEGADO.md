# Armar la pantalla `P9_Confirmacion_Masiva` en Power Apps Studio (camino directo)

> **FUENTE DE VERDAD (checkpoint «sync tenant»):** `tenant/P9_Confirmacion_Masiva.pa.yaml` y `tenant/Main_Screen.pa.yaml` son el export REAL de `P9_PRUEBA_MASIVA`. Esta guía describe cómo se armó la pantalla; si algo difiere, manda el export (ver `../SYNC_TENANT_UI.md`).

> **Estado (2026-10-06):** esta pantalla ya se armó y se probó en el tenant, en la copia **`P9_PRUEBA_MASIVA`**, con el `Ejemplo_Confirmacion_Masiva_P9.xlsx` (COMPLETADO, 3 filas). Detalle de lo validado, lo observado sin resolver y lo pendiente: `../ESTADO_CHECKPOINT_TENANT.md`. El botón de `Main_Screen` ya se agregó y probó a mano en esa copia (paso 6).

> **Prevalidación real (NO validada en tenant):** cuando actualices el flujo (`flows/ACTUALIZAR_FLUJO_PREVALIDACION.md`) hay que cambiar **5 fórmulas** de esta pantalla (registro de error, colores de estado, titular, filas leídas, aviso del pie y la colección `colPrevalidacionP9`). Están listas, en tu sintaxis regional, en `PREVALIDACION_POWERFX.md`. Los pasos de abajo describen la pantalla ya validada en el tenant (flujo estructural).

**Trabaja siempre en una COPIA de la app P9** (Guardar como → `P9_PRUEBA_MASIVA`). No publiques sobre la app productiva. Procedimiento de pegado = el que ya usaste con `COMPROBANTE PDF`: controles hijos pegados con clic derecho → Pegar, y las fórmulas de pantalla escritas a mano después.

Antes: crea el vehículo de adjuntos y la carpeta temporal (`sharepoint/INSTRUCCIONES_VEHICULO.md`) e importa el flujo (`flows/INSTRUCCIONES_FLUJO.md`).

> **Separadores regionales.** El YAML se pega siempre en sintaxis canónica (comas). Si tu barra de fórmulas usa `;` como separador de argumentos (es el caso de la configuración regional de Gabriel), la fórmula que escribes a mano abajo se adapta cambiando comas de argumentos por `;` y el `;` entre sentencias por `;;`.

**Qué ya no existe:** lista de lotes, estados `PENDIENTE`/`PROCESANDO`, temporizador, sondeo y `SubmitForm`. La app llama al flujo, espera su respuesta y la muestra.

## Pasos

1. **Datos.** *Datos → Agregar datos → SharePoint* → sitio P9 → lista `P9_MASIVA_PROTO_ADJUNTO` (solo existe para alojar el control de adjuntos; la app **nunca** escribe en ella). Luego *Power Automate → Agregar flujo* → `P9_MASIVA_PROTO_PREVALIDAR`.
2. **Pantalla.** *Insertar → Nueva pantalla → En blanco*. Renómbrala `P9_Confirmacion_Masiva`.
3. **Formulario (único control manual).** *Insertar → Formularios → Editar*. Propiedades:
   - Nombre: `frmArchivoP9` · `DataSource` = `P9_MASIVA_PROTO_ADJUNTO` · `DefaultMode` = `FormMode.New` · `Item` = (vacío)
   - `X` = 30 · `Y` = 215 · `Width` = 540 · `Height` = 140
   - *Editar campos*: quita todo y deja **solo «Datos adjuntos»** (la tarjeta queda como `dcAdjuntosP9`, con `Update` = `attXlsxP9.Attachments`).
   - Selecciona el control de adjuntos de esa tarjeta, renómbralo **`attXlsxP9`** y pon `MaxAttachments` = `1`, `MaxAttachmentSize` = `10` (MB, valor elegido por comodidad; no es un límite de la plataforma).
   - **No escribas `OnSuccess` ni uses `SubmitForm`/`Patch`:** el formulario solo sirve para elegir el archivo y `attXlsxP9.Attachments` lo guarda en la app.
4. **Pegar los controles.** Abre `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml`, copia **todo** → en Studio selecciona la pantalla → clic derecho → **Pegar**. Quedan 30 controles dentro de `cntImportacionMasivaP9`. `frmArchivoP9` y `attXlsxP9` ya existían, por eso las fórmulas se resuelven. Si ya había un control con el mismo nombre, Studio añade `_1` y las fórmulas dejan de resolverse: bórralo antes de pegar. **No pegues `P9_Confirmacion_Masiva.pa.yaml` como pantalla completa.**
5. **`OnVisible` de la pantalla** (barra de fórmulas con la pantalla seleccionada; ya no hay variable de URL de plantilla):

   ```
   Set(varProcesandoP9, false);
   Set(varResultadoP9, Blank());
   Set(varMsAppP9, Blank());
   Clear(colPrevalidacionP9);
   Set(varVerObservacionesP9, false);
   Set(varConfirmarMasivaVisible, false);
   ResetForm(frmArchivoP9)
   ```
   (Es el `OnVisible` REAL del tenant, tal cual. `varConfirmarMasivaVisible` es del segundo modal descartado: se retira en la integración de la confirmación, ver `CONFIRMACION_POWERFX.md`.)
6. **Botón en Main_Screen (agregado y probado manualmente en `P9_PRUEBA_MASIVA`; navegación ida y vuelta validada).** Referencia: `BOTON_MAIN_SCREEN.txt` (un único control nuevo). `Main_Screen` de producción no se toca.
7. **Comprobador de aplicaciones.** Revisa que no haya errores nuevos. La llamada `P9_MASIVA_PROTO_PREVALIDAR.Run({name: archivoP9.Name, contentBytes: archivoP9.Value})` **ya está validada en el tenant** y no hay que cambiarla.
8. **Probar** (F5): adjuntar → PREVALIDAR ARCHIVO. La pantalla muestra «PROCESANDO» hasta que el flujo responde.
9. **Prueba de humo** (archivos en `xlsx/`):
   - **Validada en tenant:** `Ejemplo_Confirmacion_Masiva_P9.xlsx` → COMPLETADO, 3 filas.
   - **Pendientes (no probadas en tenant):** `Plantilla_Confirmacion_Masiva_P9.xlsx` (vacía) → ERROR/ARCHIVO_VACIO · `03_SIN_TABLA.xlsx` → ERROR/TABLA_NO_ENCONTRADA · `05_ENCABEZADO_CAMBIADO.xlsx` → ERROR/ESTRUCTURA_INVALIDA · `04_TABLA_NOMBRE_DISTINTO.xlsx` → ERROR/TABLA_NO_ENCONTRADA.
10. **Mediciones:** `MEDICION_TENANT.md` (pendientes).

## DESCARGAR PLANTILLA

`btnDescargarPlantillaP9` ejecuta `Launch("<URL de descarga por UniqueId>")` con la URL **escrita en el propio botón**: ya no se usa ninguna variable ni ruta de carpeta. La URL es `download.aspx?UniqueId=84b7ef88-43aa-43d2-8d1c-0f0b682dafbd` sobre el sitio personal `https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu` (`/_layouts/15/`). Pegada en el navegador, **descarga físicamente** `Plantilla_Confirmacion_Masiva_P9.xlsx` (validado en tenant); el clic del botón dentro de la app no se ha registrado como probado.

- No usar `Download()`, `?download=1`, rutas de carpeta supuestas ni el enlace compartido de OneDrive: el enlace compartido abre Excel y no descarga, y las rutas sin la carpeta `Documents` anidada devuelven «no existe».
- El UniqueId pertenece al archivo actual. Para actualizar la plantilla usa *Reemplazar* o sube una **nueva versión** del mismo archivo; si lo borras y lo recreas, el UniqueId cambia y hay que actualizar la URL del botón (y el YAML).
- El archivo vive en `/personal/gtorricot_univalle_edu/Documents/Documents/P9_MASIVA_PROTO/`: la carpeta anidada está documentada en `../ESTADO_CHECKPOINT_TENANT.md`.

## Qué NO se toca

`btnConfirmarDepositoP9_1`, `galDepositosP9_1`, filtros, selector de banco, REVERSIÓN PENDIENTE, `COMPROBANTE PDF`, `P9_ASIGNAR_DEPOSITO`. La pantalla nueva no usa `Depositos_Activos`.

## Si algo no coincide

- **PREVALIDAR queda deshabilitado aunque haya archivo** → el control de adjuntos no se llama `attXlsxP9`, o el archivo no termina en `.xlsx`.
- **`.Run(...)` marca error de argumentos** → en el tenant la firma que funciona recibe un registro `{name, contentBytes}`. Si Studio muestra otra, comprueba que el flujo tenga **una** entrada de tipo Archivo llamada `file` y que quitaste y volviste a agregar el flujo a la app.
- **Resultado `FLUJO_SIN_RESPUESTA`** → la app no obtuvo respuesta del flujo (error de llamada o tiempo de espera). El texto exacto va en el mensaje: anótalo en `MEDICION_TENANT.md`.
- **El archivo adjunto no aparece / el control de adjuntos no deja elegir** → revisa que la lista `P9_MASIVA_PROTO_ADJUNTO` tenga datos adjuntos habilitados (`sharepoint/INSTRUCCIONES_VEHICULO.md`).
- **DESCARGAR PLANTILLA abre Excel o muestra «Archivo no encontrado»** → la URL no corresponde al archivo actual (UniqueId cambiado por borrar y recrear) o el usuario no tiene permiso de lectura sobre el archivo.
- **Copia temporal:** los labels «Copia temporal» están ocultos (`Visible = false`) porque el borrado de la copia devuelve HTTP 423 y se acepta que queden `TMP_*.xlsx` en la carpeta temporal.
