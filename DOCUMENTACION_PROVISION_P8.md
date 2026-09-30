# P8_PROVISIONAR_LISTAS

Flujo manual e independiente para crear y verificar las listas de SharePoint de P8 sin crear columnas a mano. Su única fuente de nombres, tipos, obligatoriedad, índices, unicidad, opciones y predeterminados es `p8/esquema_listas_p8.json`. El contrato se compila y queda incluido dentro del flujo: no hay que subir ese JSON a SharePoint ni configurar una carpeta.

Estado de entrega: ZIP generado sobre la plantilla real ya utilizada para P8. Comprobaciones locales disponibles en `p8/provision/evidencia_validacion.json`. La aceptación de la importación y las llamadas REST requieren probarse en un tenant real. No se ha ejecutado la provisión contra Microsoft 365.

## Uso: importar, conectar, indicar sitio y ejecutar

1. Power Automate → **Mis flujos → Importar → Importar paquete heredado**. Seleccionar `P8_PROVISIONAR_LISTAS.zip` y **Crear como nuevo**.
2. Seleccionar o autenticar una conexión **SharePoint** con los permisos indicados más abajo. Es una conexión estándar, sin HTTP premium, aplicación de Azure ni secreto adicional.
3. Abrir el flujo importado `P8_PROVISIONAR_LISTAS` y pulsar **Ejecutar**. En el único campo **Sitio SharePoint**, introducir la URL completa del sitio real. Todas las acciones REST usan esa entrada; no hay que sustituir URLs en cada acción.
4. Ejecutar una vez y abrir **RESUMEN_FINAL** en el historial. Debe mostrar `PROVISION_P8 = OK`, las dos listas verificadas, 34/34 y 13/13 columnas técnicas, y `diferencias: []`.

No hay que crear listas, columnas, índices, opciones ni restricciones manualmente. El flujo de carga P8 existente sigue siendo independiente; este paquete no lo configura ni lo modifica.

Para comprobar idempotencia puede ejecutarse de nuevo sobre el mismo sitio. Si ambas listas coinciden, la segunda ejecución hace únicamente lecturas REST: cero creaciones de listas/columnas y cero actualizaciones. No se borran ni reemplazan elementos de las listas.

## Fuente única y paquete independiente

El generador `p8/provision/construir.py` lee directamente el contrato existente. Rechaza tipos desconocidos, nombres técnicos inválidos, duplicados y cantidades inconsistentes. No vuelve a calcular el contrato desde el motor ni desde el adaptador P7.

| Lista | Columnas técnicas | Campos automáticos de SharePoint |
|---|---:|---|
| Depositos_Activos | 34 | Excluidos del conteo del contrato |
| Depositos_Cargas | 13 | Excluidos del conteo del contrato |

`Title`, `ID`, `Created`, `Modified` y otros campos de sistema no forman parte de las 34/13 columnas. `Title` se conserva y se configura `Required = false` según `title_obligatorio` del contrato. No se borra su contenido, se renombra ni se oculta. La excepción explícita de actualizar `Title` es necesaria para que la carga P8 pueda omitirlo.

Los artefactos generados son:

- `P8_PROVISIONAR_LISTAS.zip`: segundo flujo importable.
- `p8/provision/flujo_provision_definition.json`: definición WDL que contiene el plan derivado del contrato.
- `p8/provision/plan_provision.json`: solicitudes y expectativas compiladas, con ruta y SHA-256 de la fuente.
- `p8/provision/construir.py`: generador reproducible.
- `p8/provision/ensayo.py` y `tests/test_13_provision_p8.py`: ejecución local del WDL con REST simulado.
- `p8/provision/evidencia_validacion.json` y `pruebas_provision.log`: resultados de validación.

La estructura del ZIP se deriva de `P8_CARGA_DEPOSITOS_ACTIVOS.zip`, basado a su vez en `NORMALIZADOR_POWER_AUTOMATE.zip`, una exportación real disponible en el repositorio. Los identificadores de recursos del paquete son nuevos y deterministas; no coinciden con los del flujo de carga y no identifican recursos reales del tenant. La conexión se asigna durante la importación. No hay IDs, sitios, credenciales ni rutas de entrada reales inventados.

## Diseño e idempotencia

El trigger manual y todos los bucles tienen concurrencia 1. La provisión se realiza por lista y la verificación final se realiza en una segunda pasada independiente, aunque haya fallado alguna creación.

1. Buscar la lista por su título exacto. Crear una lista genérica, plantilla 100, únicamente si la consulta no encuentra ninguna. Un error 403/500 no se interpreta como ausencia.
2. Comprobar que sea una lista genérica, visible, y con `ContentTypesEnabled = false`. Una biblioteca o una lista con tipos de contenido personalizados se reporta incompatible y no se altera. Esto evita declarar compatible una lista donde requisitos heredados de tipos de contenido puedan impedir la carga.
3. Leer el inventario de campos. Si la respuesta indica paginación, no crear columnas a partir de una página incompleta y reportar `FAIL`.
4. Liberar `Title` de obligatoriedad si todavía lo requiere.
5. Para cada columna del contrato, detectar coincidencias tanto por `InternalName` como por título, incluyendo colisiones de mayúsculas/minúsculas. Si existe alguna coincidencia, no recrear ni actualizar esa columna: la segunda pasada decidirá si coincide exactamente.
6. Si falta, crearla con `createfieldasxml`. `Name`, `StaticName` y `DisplayName` reciben el mismo nombre técnico. `Options = 9` combina `AddToDefaultContentType (1)` y `AddFieldInternalNameHint (8)`. La pista de nombre no se considera garantía: la verificación posterior exige el nombre interno exacto.
7. Sobre el **GUID devuelto por esa creación**, configurar `Required`, `Indexed` y `DefaultValue`. Solo para la columna que exige unicidad, activar después `EnforceUniqueValues = true`. No se actualiza por un nombre que pudiera pertenecer a otra columna creada concurrentemente.
8. Volver a leer las listas y sus campos; comparar todas las propiedades y emitir el resultado.

Para `CLAVE_TRANSACCION` la secuencia efectiva es: crear Text requerido → habilitar índice → activar unicidad. La lectura final debe confirmar simultáneamente `Required = true`, `Indexed = true` y `EnforceUniqueValues = true`.

Una columna preexistente con configuración distinta produce `FAIL` y un detalle por propiedad. No se fuerza un cambio de tipo, se vacían datos, se elimina una columna ni se desactiva un índice existente. Si una ejecución parcial deja un campo sin configurar, el siguiente intento lo identifica como preexistente y reporta la diferencia; no lo repara automáticamente. La corrección de un conflicto requiere una decisión explícita y separada, no crear columnas manualmente como parte del caso normal.

## Tipos y configuración

| Tipo del contrato | SharePoint / SchemaXml | Verificación específica |
|---|---|---|
| Texto de una linea | Text, longitud estándar 255 | TypeAsString = Text |
| Varias lineas de texto sin formato | Note, RichText = FALSE, AppendOnly = FALSE | Ambos booleanos false |
| Fecha y hora, solo fecha | DateTime, Format = DateOnly | Formato DateOnly |
| Fecha y hora, incluir hora | DateTime, Format = DateTime | Formato DateTime |
| Numero, 2 decimales | Number, Decimals = 2, Percentage = FALSE | 2 decimales y sin porcentaje |
| Numero, 0 decimales | Number, Decimals = 0, Percentage = FALSE | 0 decimales y sin porcentaje |
| Opcion | Choice, CHOICES y FillInChoice tomados del contrato | Opciones exactas, orden y relleno |

Se comprueba también en **cada** columna: `InternalName`, `TypeAsString`, `Required`, `Indexed`, `EnforceUniqueValues`, `Hidden`, `ReadOnlyField` y `DefaultValue`. Las columnas técnicas deben ser visibles y escribibles para que el flujo de carga las use.

`ESTADO_ASIGNACION` recibe el único valor `DISPONIBLE` y su predeterminado `DISPONIBLE`. `ESTADO_LOTE` recibe exactamente `COMPLETADO`, `COMPLETADO_CON_ERRORES`, `FALLIDO`, sin predeterminado añadido. Donde el contrato no indica predeterminado, se deja sin él y se verifica vacío; no se inventan valores operativos.

Las propiedades específicas se extraen de `SchemaXml` mediante `xml()` y `xpath()`. No se compara el XML como texto, pues SharePoint puede reordenar atributos. Para los booleanos XML, atributo ausente equivale al valor por defecto false; `DefaultValue = null` y cadena vacía significan ausencia de predeterminado. Fechas y decimales requieren el valor explícito esperado.

El conteo técnico se hace por pertenencia al conjunto de nombres exactos del contrato. Además se reportan columnas de usuario adicionales visibles, escribibles y no derivadas de tipos base. Los campos de sistema, ocultos o de solo lectura ajenos al contrato se conservan y se excluyen de ese conteo. Todas las columnas del contrato se verifican aunque se hayan ocultado o marcado de solo lectura; esos cambios son diferencias.

## Endpoints REST

Todos son relativos al sitio introducido por el usuario y usan **Send an HTTP request to SharePoint**, operación `HttpRequest`. No se usa un conector HTTP genérico.

| Método | URI relativa | Finalidad |
|---|---|---|
| GET | `_api/web/lists?$select=Title,BaseTemplate,ContentTypesEnabled,Hidden&$filter=Title eq '<lista>'&$top=2` | Comprobar existencia antes de crear |
| POST | `_api/web/lists` | Crear lista genérica ausente |
| GET | `_api/web/lists/getbytitle('<lista>')?$select=Title,BaseTemplate,ContentTypesEnabled,Hidden` | Comprobar lista y releer al final |
| GET | `_api/web/lists/getbytitle('<lista>')/fields?$select=...&$top=5000` | Inventario inicial y final de campos |
| POST | `_api/web/lists/getbytitle('<lista>')/fields/createfieldasxml` | Crear campo ausente con nombre técnico |
| POST + MERGE | `_api/web/lists/getbytitle('<lista>')/fields(guid'<GUID devuelto por crear>')` | Configurar únicamente el nuevo campo y, después del índice, la unicidad |
| GET | `_api/web/lists/getbytitle('<lista>')/fields/getbyinternalnameortitle('Title')?$select=InternalName,Required` | Comprobar Title |
| POST + MERGE | `_api/web/lists/getbytitle('<lista>')/fields/getbyinternalnameortitle('Title')` | Dejar Title no obligatorio cuando sea necesario |

El `$select` de campos contiene `InternalName,Title,TypeAsString,Required,Indexed,EnforceUniqueValues,DefaultValue,SchemaXml,Hidden,ReadOnlyField,FromBaseType`.

Las lecturas solicitan `Accept: application/json;odata=nometadata`; las colecciones se leen de `body.value`. Los cuerpos de escritura son JSON serializado, `Content-Type: application/json;odata=verbose`, con `__metadata` del tipo REST correspondiente. Para actualizaciones se envían `X-HTTP-Method: MERGE` e `IF-MATCH: *`. No hay DELETE ni llamadas a `/items`. El conector administra autenticación y digest.

## Verificación, resultado y errores

`RESUMEN_FINAL` se crea **antes** de cualquier acción Terminar. Solo devuelve `OK` si ambas listas terminaron la verificación, no se registró ninguna diferencia y el ámbito de verificación terminó correctamente.

Ejemplo de resultado sin diferencias:

```json
{
  "PROVISION_P8": "OK",
  "resultado": "PROVISION_P8 = OK",
  "listas": [
    {"lista": "Depositos_Activos", "esperadas": 34, "presentes": 34, "verificacion_columnas": "Succeeded"},
    {"lista": "Depositos_Cargas", "esperadas": 13, "presentes": 13, "verificacion_columnas": "Succeeded"}
  ],
  "diferencias": []
}
```

Una diferencia incluye `lista`, `campo`, `propiedad`, `esperado` y `actual`. Los errores REST indican etapa/acción, estado y código HTTP disponibles, sin copiar credenciales, cabeceras, elementos de lista ni `result()` completo. Si el XML de una columna no puede leerse, se identifica esa columna y se continúa comprobando las demás.

El resumen también contiene SHA-256 de la fuente y el identificador de ejecución. Queda en la salida de **RESUMEN_FINAL** del historial de Power Automate; no se crea una tercera lista ni se mezclan registros de provisión con `Depositos_Cargas`. `OK` termina la ejecución como correcta; `FAIL` la termina como fallida después de producir el resumen.

Los errores y timeouts de creación no se interpretan como existencia. Se registran y la verificación final vuelve a consultar SharePoint. Una respuesta POST exitosa nunca basta para declarar el contrato correcto. Un error transitorio puede producir `FAIL` aunque la escritura haya llegado al servidor; el reproceso vuelve a verificar el estado real.

## Permisos necesarios

La identidad de la conexión necesita acceso al sitio y permiso **Administrar listas / Manage Lists**, tanto para crear las listas como para agregar/configurar campos e índices. También necesita lectura de listas y de sus metadatos. Un nivel estándar **Editar** suele incluir estos permisos, siempre que la organización no lo haya personalizado y que no haya permisos únicos restrictivos en una lista existente. El nivel **Contribuir** por sí solo no basta para administrar columnas.

No se necesita ser administrador global de Microsoft 365. Un propietario del sitio puede validar los permisos efectivos. Las políticas de DLP y acceso condicional del tenant deben permitir el conector SharePoint. El flujo no modifica permisos ni intenta elevar privilegios.

## Pruebas y límites

Regenerar desde la raíz del repositorio:

```bash
python -m p8.provision.construir
python -m pytest -q tests/test_12_flujo_p8.py tests/test_13_provision_p8.py
```

Las pruebas ejecutan la definición WDL generada con REST simulado. Cubren creación 34/13, segundo intento sin escrituras, listas parciales, conservación de elementos, diferencias en tipos/obligatoriedad/índices/unicidad/predeterminados, fechas/decimales/texto sin formato/Choice, colisiones de nombre, campos adicionales, 403/404/500/timeout, XML inválido y lectura final independiente. También validan grafo, límite de ocho niveles, nombres de acción únicos, recursos de paquete distintos y reproducibilidad del ZIP.

Pendientes del tenant: aceptar la importación, confirmar el funcionamiento del conector y los permisos, ejecutar sobre un sitio piloto y repetir para comprobar cero POST. Se ha reutilizado una estructura de exportación real, pero las pruebas locales no certifican la importación ni reproducen todas las reglas internas de SharePoint.

No hay transacción global ni rollback: una interrupción puede dejar listas o columnas ya creadas. Se conservan para diagnóstico y reproceso. La ejecución manual puede cancelarse; un corte del propio servicio puede impedir el resumen, por lo que no se declara una garantía de ejecución frente a indisponibilidad total.

La compatibilidad prevista es SharePoint Online, listas genéricas sin tipos de contenido personalizados. Se consulta hasta 5000 campos y se falla expresamente si hay paginación; no se certifica una respuesta incompleta. No se optimiza para provisiones masivas ni para ediciones concurrentes de administradores durante el piloto.

P6/P7, motor, doradas, esquema fuente, ZIP/JSON del flujo de carga y su documentación permanecen sin cambios. No se ha hecho commit, push, merge a main ni checkpoint de esta provisión.

Referencias:

- [Conector SharePoint: Send an HTTP request to SharePoint](https://learn.microsoft.com/en-us/connectors/sharepointonline/#send-an-http-request-to-sharepoint)
- [REST: listas y elementos](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-lists-and-list-items-with-rest)
- [Esquema XML Field](https://learn.microsoft.com/en-us/sharepoint/dev/schema/field-element-field)
- [FieldCollection.AddFieldAsXml y AddFieldOptions](https://learn.microsoft.com/en-us/previous-versions/office/sharepoint-csom/ee542202(v=office.15))
