# Armar la pantalla `P9_Confirmacion_Masiva` en Power Apps Studio (camino directo)

**Trabaja en una COPIA de la app P9** (Guardar como → `P9_PRUEBA_MASIVA`). No publiques sobre la app productiva. Procedimiento de pegado = el que ya usaste con `COMPROBANTE PDF`: controles hijos pegados con clic derecho → Pegar, y las fórmulas de pantalla escritas a mano después.

Antes: crea el vehículo de adjuntos y la carpeta temporal (`sharepoint/INSTRUCCIONES_VEHICULO.md`) e importa el flujo (`flows/INSTRUCCIONES_FLUJO.md`).

> **Separadores regionales.** El YAML se pega siempre en sintaxis canónica (comas). Si tu barra de fórmulas usa `;` como separador de argumentos, la fórmula que escribes a mano abajo se adapta cambiando comas de argumentos por `;` y el `;` entre sentencias por `;;`.

**Qué ya no existe:** lista de lotes, estados `PENDIENTE`/`PROCESANDO`, temporizador, sondeo y `SubmitForm`. La app llama al flujo, espera su respuesta y la muestra.

## Pasos

1. **Datos.** *Datos → Agregar datos → SharePoint* → sitio P9 → lista `P9_MASIVA_PROTO_ADJUNTO` (solo existe para alojar el control de adjuntos; la app **nunca** escribe en ella). Luego *Power Automate → Agregar flujo* → `P9_MASIVA_PROTO_PREVALIDAR`.
2. **Pantalla.** *Insertar → Nueva pantalla → En blanco*. Renómbrala `P9_Confirmacion_Masiva`.
3. **Formulario (único control manual).** *Insertar → Formularios → Editar*. Propiedades:
   - Nombre: `frmArchivoP9` · `DataSource` = `P9_MASIVA_PROTO_ADJUNTO` · `DefaultMode` = `FormMode.New` · `Item` = (vacío)
   - `X` = 30 · `Y` = 215 · `Width` = 540 · `Height` = 140
   - *Editar campos*: quita todo y deja **solo «Datos adjuntos»**.
   - Selecciona el control de adjuntos de esa tarjeta, renómbralo **`attXlsxP9`** y pon `MaxAttachments` = `1`, `MaxAttachmentSize` = `10` (MB, valor elegido por comodidad; no es un límite de la plataforma).
   - **No escribas `OnSuccess` ni uses `SubmitForm`/`Patch`:** el formulario solo sirve para elegir el archivo y `attXlsxP9.Attachments` lo guarda en la app.
4. **Pegar los controles.** Abre `P9_Confirmacion_Masiva_CONTROLES_PEGAR.yaml`, copia **todo** → en Studio selecciona la pantalla → clic derecho → **Pegar**. Quedan 30 controles dentro de `cntImportacionMasivaP9`. `frmArchivoP9` y `attXlsxP9` ya existían, por eso las fórmulas se resuelven. Si ya había un control con el mismo nombre, Studio añade `_1` y las fórmulas dejan de resolverse: bórralo antes de pegar.
5. **`OnVisible` de la pantalla** (barra de fórmulas con la pantalla seleccionada):

   ```
   Set(varProcesandoP9, false);
   Set(varResultadoP9, Blank());
   Set(varMsAppP9, Blank());
   Set(varUrlPlantillaP9, "https://univalleedu-my.sharepoint.com/personal/gtorricot_univalle_edu/Documents/P9_MASIVA_PROTO/Plantilla_Confirmacion_Masiva_P9.xlsx?download=1");
   ResetForm(frmArchivoP9)
   ```
6. **Botón en Main_Screen.** Sigue `BOTON_MAIN_SCREEN.txt` (un único control nuevo).
7. **Comprobador de aplicaciones.** Revisa que no haya errores nuevos. Si marca error en `P9_MASIVA_PROTO_PREVALIDAR.Run(...)`, abre el flujo en el panel de Power Automate y comprueba qué firma espera (ver «Si algo no coincide»).
8. **Probar** (F5 desde `Main_Screen`): botón IMPORTACIÓN MASIVA → adjuntar → PREVALIDAR ARCHIVO. La pantalla muestra «PROCESANDO» hasta que el flujo responde.
9. **Prueba de humo, cinco archivos** (están en `xlsx/`):
   `Ejemplo_Confirmacion_Masiva_P9.xlsx` → COMPLETADO, 3 filas · `Plantilla_Confirmacion_Masiva_P9.xlsx` (vacía) → ERROR/ARCHIVO_VACIO · `03_SIN_TABLA.xlsx` → ERROR/TABLA_NO_ENCONTRADA · `05_ENCABEZADO_CAMBIADO.xlsx` → ERROR/ESTRUCTURA_INVALIDA · `04_TABLA_NOMBRE_DISTINTO.xlsx` → ERROR/TABLA_NO_ENCONTRADA.
10. **Mediciones:** `MEDICION_TENANT.md`.

## Qué NO se toca

`btnConfirmarDepositoP9_1`, `galDepositosP9_1`, filtros, selector de banco, REVERSIÓN PENDIENTE, `COMPROBANTE PDF`, `P9_ASIGNAR_DEPOSITO`. La pantalla nueva no usa `Depositos_Activos`.

## Si algo no coincide

- **PREVALIDAR queda deshabilitado aunque haya archivo** → el control de adjuntos no se llama `attXlsxP9`, o el archivo no termina en `.xlsx`.
- **`.Run(...)` marca error de argumentos** → este prototipo supone que la entrada de tipo archivo del flujo se pasa como un registro `{name, contentBytes}`. Si Studio pide otra forma (por ejemplo `.Run(archivo)` con el registro ya armado o un texto en base64), ajusta **solo** esa llamada en `btnPrevalidarP9.OnSelect`; el flujo no cambia salvo su entrada. Es la primera cosa que hay que comprobar en el tenant.
- **Resultado `FLUJO_SIN_RESPUESTA`** → la app no obtuvo respuesta del flujo (error de llamada o tiempo de espera). El texto exacto va en el mensaje: anótalo en `MEDICION_TENANT.md`.
- **El archivo adjunto no aparece / el control de adjuntos no deja elegir** → revisa que la lista `P9_MASIVA_PROTO_ADJUNTO` tenga datos adjuntos habilitados (`sharepoint/INSTRUCCIONES_VEHICULO.md`).
- **DESCARGAR PLANTILLA abre la página de SharePoint en vez de descargar** → falta el archivo en `Documents/P9_MASIVA_PROTO/` o el permiso; quita `?download=1` y prueba de nuevo.
