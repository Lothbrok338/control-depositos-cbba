# P0 · Automatización de la entrada de extractos

**Resumen.** Gabriel deja extractos bancarios en `ENTRADA`; un orquestador pequeño ejecuta el motor y P7 que ya existían, deja el JSON en `CARGA_EXTRACTOS_BANCARIOS` (la carpeta que debe escuchar el flujo P8 V5) y mueve el extracto a `PROCESADOS/AAAA/MM_MES` (o a `ERROR/AAAA/MM_MES` con el motivo). P0 **no** cambia el motor bancario, P7 ni P8 (salvo el control del año, ver §8).

```
Documents/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA/<extracto>.xls|xlsx      ← único paso manual de Gabriel (ENTRADA es plana)
   │  (python -m p0, un archivo a la vez)
   ├─ motor_control_depositos_cbba.py   detecta banco/cuenta/moneda, normaliza, valida saldos  → LISTS.csv
   ├─ adaptador_m365.py (P7)            LISTS.csv → DEPOSITOS_ACTIVOS__P7-<hash>.json
   ├─ copia del JSON a  CARGA_EXTRACTOS_BANCARIOS/  (la carpeta que escucha P8)
   │      └─ P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES  → Depositos_Activos + Depositos_Cargas
   └─ el extracto original pasa a  PROCESADOS/AAAA/MM_MES/   (si algo falló: ERROR/AAAA/MM_MES/ + <archivo>.error.json)
```

## 1. Qué hace Gabriel

1. Descargar uno o varios extractos bancarios **vírgenes** (sin renombrar ni abrir y guardar).
2. Copiarlos a `Documents/CONTROL_DEPOSITOS/P0_EXTRACTOS/ENTRADA`.
3. Nada más. Unos minutos después el extracto aparece en `PROCESADOS/AAAA/MM_MES` o `ERROR/AAAA/MM_MES`.

Si quiere confirmar la carga: en la lista `Depositos_Cargas` aparece un registro por lote (`LOTE_ID` y `ARCHIVO_JSON` están en el archivo `<extracto>.p0.json` de `PROCESADOS`).

## 1b. Estructura de carpetas

```
CONTROL_DEPOSITOS/P0_EXTRACTOS/
├── ENTRADA/                       plana: solo se dejan ahí los .xls/.xlsx (las subcarpetas se ignoran)
├── PROCESADOS/AAAA/MM_MES/        p. ej. PROCESADOS/2026/10_OCTUBRE/
├── ERROR/AAAA/MM_MES/             el original y su <archivo>.error.json, juntos
└── CARGA_EXTRACTOS_BANCARIOS/     los DEPOSITOS_ACTIVOS__*.json (sin subcarpetas); la escucha P8
```

`MM_MES`: 01_ENERO, 02_FEBRERO, 03_MARZO, 04_ABRIL, 05_MAYO, 06_JUNIO, 07_JULIO, 08_AGOSTO, 09_SEPTIEMBRE, 10_OCTUBRE, 11_NOVIEMBRE, 12_DICIEMBRE (fijos, no dependen del idioma del equipo). El año y el mes son los de la **fecha en que P0 procesa el archivo** (no la de los movimientos). P0 crea `AAAA` y `MM_MES` solo cuando va a guardar algo ahí; nunca por adelantado. Un nombre repetido en la misma carpeta no se pisa (se añade `__AAAAMMDD_HHMMSS`).

## 2. Dónde corre Python (decisión)

**Decisión para esta fase: local, en el equipo que ya sincroniza el OneDrive `Documents` (PC o mini-servidor de la sede), sin n8n ni Railway.** Confianza ≈ 70 %.

| Criterio | A · Local (elegida) | B · Servicio cloud Python | C · Otra (Power Automate, Azure Functions…) |
|---|---|---|---|
| Acceso a la carpeta | El cliente de OneDrive ya la sincroniza: cero credenciales nuevas. | Requiere registrar una aplicación en Entra ID del tenant de la universidad, permisos de Graph (`Files.ReadWrite…`/`Sites.Selected`, normalmente con consentimiento de administrador) y código nuevo de descarga/subida/mover por Graph, más suscripciones o *polling*. La ENTRADA hoy está en un OneDrive personal. No hay nada de esto validado en el repo. | Power Automate **no ejecuta Python**; llamar a un servicio exige conector HTTP (licencia premium, no verificada). |
| Código nuevo | ~500 líneas (este orquestador). | El mismo núcleo + adaptador de almacenamiento Graph + alojamiento + secretos. | Igual que B, más el flujo. |
| Coste / mantenimiento | Ninguno extra; hay que mantener Python y el repo en ese equipo. | Hosting, secretos, renovación de suscripciones, monitoreo. | Licencias y dos sistemas que mantener. |
| Equipo encendido | **Sí hace falta** (limitación real). Mitigación: un equipo de sede siempre encendido. | No. | No. |
| Varias sedes | Un equipo con el mismo repositorio por sede (misma versión del motor); cuentas por sede en configuración. | Un solo despliegue central (mejor a escala nacional). | — |
| Aprovecha lo ya validado | **Sí:** el JSON aparece en la carpeta de SharePoint que V5 ya escucha. | No (hay que replicar ese comportamiento). | No. |

Por qué no cloud ahora: añadiría una integración de identidad y de almacenamiento que hoy no existe ni se puede validar desde el repositorio, para automatizar un tramo que con el cliente de OneDrive cabe en un script. **El diseño no ata el sistema a un PC:** el núcleo (`Orquestador`) solo ve carpetas; el mismo código puede ejecutarse más adelante en un contenedor con la carpeta montada o sustituyendo únicamente las funciones de lectura/mover/publicar por Graph. Cuando se piense en despliegue nacional con muchas sedes, la comparación se rehace con datos reales de sedes y del tenant.

Disparador: **un solo mecanismo** — el propio orquestador consulta `ENTRADA` cada 60 s (`--intervalo`). Solo procesa archivos «estables» (sin cambios en los últimos 30 s, `--estable`) para no leer un archivo mientras se copia o se sincroniza.

## 3. Puesta en marcha (una vez, por equipo)

1. Python 3.10+ y `pip install pandas numpy xlrd openpyxl python-calamine`.
2. El repositorio en una carpeta local (misma rama/versión que el resto de sedes).
3. Comprobar la ruta local sincronizada de `Documents` de OneDrive (por ejemplo `C:\Users\<usuario>\OneDrive - <organización>\Documents`) y que existe `<Documents>\CONTROL_DEPOSITOS\P0_EXTRACTOS` (si no existe, P0 se detiene con un error en vez de crear un árbol falso por una ruta mal escrita). P0 crea las carpetas base que falten (`ENTRADA`, `PROCESADOS`, `ERROR`, `CARGA_EXTRACTOS_BANCARIOS`), nunca años ni meses por adelantado.
4. **Apuntar el flujo P8 V5 a la carpeta nueva** (cambio en el tenant, ver §7).
5. Probar un ciclo:

```
cd <repositorio>
python -m p0 --sede CBBA --documentos "<ruta local de Documents>" --una-vez
```

6. Dejarlo en marcha (opción simple en Windows): Programador de tareas → *Crear tarea* → desencadenador «Al iniciar sesión» → acción `python -m p0 --sede CBBA --documentos "<ruta>"` con «Iniciar en» = carpeta del repositorio. Sin `--una-vez` queda en bucle.

**Reiniciar:** cerrar la ventana/tarea y volver a lanzarla. Si dice «ya hay otra instancia de P0», borrar `p0.lock` de la carpeta de trabajo (por defecto `%TEMP%\cbba_p0\CBBA\`; se reemplaza solo si tiene más de 2 h). Registro de actividad: `p0.log` en esa carpeta. Opciones: `--trabajo`, `--intervalo`, `--estable`, `--raiz`, `--carga`; variable `CBBA_DOCUMENTOS` equivale a `--documentos`.

## 4. Qué significa PROCESADOS y ERROR

* **PROCESADOS** — el extracto se normalizó, P7 generó un JSON válido y **el JSON se copió completo (se comprueba su SHA-256) a `CARGA_EXTRACTOS_BANCARIOS`**. El extracto se mueve a `PROCESADOS/AAAA/MM_MES` *después* de eso, nunca antes. Junto a él queda `<archivo>.p0.json` (sede, fecha, hash del extracto, movimientos, `lote_id`, nombre del JSON). **PROCESADOS no significa que SharePoint ya cargó los movimientos:** esa carga la hace P8 en el siguiente minuto y deja su resultado en `Depositos_Cargas`.
  * Un extracto válido **sin movimientos** (p. ej. BISA ME vacía) también va a PROCESADOS, sin JSON (no hay nada que cargar; se anota en `advertencia`).
* **ERROR** — el extracto se mueve a `ERROR/AAAA/MM_MES` y se escribe `<archivo>.error.json` con `nombre_archivo`, `fecha_hora`, `etapa`, `codigo_error`, `mensaje` (y, si aplica, un extracto del registro del motor). No se publica nada. Para reintentar: corregir la causa y copiar de nuevo el archivo (no es necesario borrar el `.error.json`).

| `codigo_error` | Etapa | Significado |
|---|---|---|
| `EXTENSION_NO_SOPORTADA`, `ARCHIVO_VACIO` | ARCHIVO | No es .xls/.xlsx o tiene 0 bytes |
| `ARCHIVO_ILEGIBLE` | DETECCION | Corrupto o no es un Excel real |
| `SIN_FORMATO`, `NO_RECONOCIDO`, `RECHAZADO`, `ENCABEZADO_INCOMPLETO`, `SIN_CUENTA`, `AMBIGUO` | DETECCION | No coincide con ningún formato bancario del registro (p. ej. el reporte «Últimos 12 movimientos» de Unión) |
| `CUENTA_NO_REGISTRADA` | DETECCION | El formato se reconoce pero la cuenta de la cabecera no está en el registro de la sede (una entrada nueva en `CUENTAS` lo resuelve) |
| `SALDOS_NO_CUADRAN`, `AUDITORIA_ESTRUCTURAL`, `ANIO_FUERA_DE_RANGO`, `NORMALIZACION_FALLIDA`, `FALLO_MOTOR` | MOTOR | El motor bloqueó la exportación (mensaje con el detalle) |
| `ARCHIVO_EXCLUIDO_POR_NOMBRE` | MOTOR | El nombre contiene `NORMALIZADO` o parece una salida del sistema (el motor lo ignora); renombrar el original |
| `P7_CONTRATO`, `P7_FILAS_INVALIDAS` | P7 | Contrato de 26 columnas roto, o P7 marcó filas inválidas (no se carga un extracto incompleto) |
| `CARPETA_CARGA_NO_EXISTE`, `PUBLICACION_FALLIDA`, `COPIA_INCOMPLETA` | PUBLICACION | No se pudo entregar el JSON a `CARGA_EXTRACTOS_BANCARIOS` |
| `ERROR_INESPERADO` | la etapa en curso | Excepción no prevista; el detalle está en `p0.log` |

Si el original no se puede mover (p. ej. está abierto en Excel), el JSON ya publicado no se vuelve a generar en cada ciclo; el archivo queda en `ENTRADA` con una advertencia en `p0.log` y se reintenta al reiniciar P0 (P8 evita duplicados de todos modos).

Archivos transitorios (`~$…`, `.tmp`, `.crdownload`, ocultos, `desktop.ini`) y subcarpetas se ignoran y quedan donde están.

## 5. Archivo por archivo

Cada extracto se procesa **solo**, con su propia corrida del motor: un archivo malo no impide procesar los demás y no hay *rollback* global (BNB → PROCESADOS, BISA → PROCESADOS, BCP → ERROR, UNION → PROCESADOS). El motor sigue sin aceptar dos extractos de la misma cuenta en una misma corrida, pero P0 ya no se lo pide.

## 6. Si se repite un extracto

P0 no inventa otra estrategia de idempotencia: el mismo extracto (o dos extractos que se solapan) genera un JSON más y **P8 evita duplicados con `CLAVE_TRANSACCION`** (consulta previa por clave + valores únicos en la lista); el lote queda con `CANTIDAD_NUEVA` = 0 y `CANTIDAD_YA_EXISTE` = movimientos. Un mismo nombre de archivo ya presente en `PROCESADOS` no se pisa (se añade `__AAAAMMDD_HHMMSS`). Dentro de **un** extracto, dos filas con la misma clave sí son error (`AUDITORIA_ESTRUCTURAL`), como antes.

## 7. Dónde termina el JSON y cómo llega a Depositos_Activos

Termina en `CONTROL_DEPOSITOS/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS` (carpeta de `Documents` de OneDrive de `…/personal/gtorricot_univalle_edu`; ruta de SharePoint `/Documents/CONTROL_DEPOSITOS/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS`). OneDrive sube el archivo, el flujo `P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES` (disparador «Cuando se crea un archivo (solo propiedades)» cada minuto, solo `DEPOSITOS_ACTIVOS__*.json`) lo detecta, consulta cada clave, crea solo los movimientos nuevos y escribe el lote en `Depositos_Cargas`. El archivo se copia **ya con su nombre final** (no se usa temporal + renombrar, porque un archivo renombrado podría no disparar «archivo nuevo»). Los JSON se quedan en esa carpeta como historial; P0 no los borra.

**P8 no se modificó en el repositorio, pero hoy el flujo V5 desplegado escucha `/Documents/P8_PILOTO`. Hay que apuntarlo a la carpeta nueva (paso manual, una vez):** Power Automate → flujo V5 → editar → disparador *Cuando se crea un archivo (solo propiedades)* → *Carpeta* → elegir `/Documents/CONTROL_DEPOSITOS/P0_EXTRACTOS/CARGA_EXTRACTOS_BANCARIOS` (el sitio y la biblioteca no cambian) → guardar. Mientras no se haga, P0 deja los JSON en la carpeta nueva y **nada los carga**. (El zip versionado de V5 sigue con `/Documents/P8_PILOTO`; no se regeneró.)

## 8. Año ya no fijo en 2026

El control del paso 6 del motor protegía contra fechas mal leídas (año de 2 dígitos, texto ilegible), no contra «otro año de trabajo». Regla actual (`anios_fuera_de_rango`): cada año de los movimientos debe estar en **[`ANIO_MINIMO_DATOS` (2026, primer año de operación; no vence), año de la fecha del equipo]**. Por eso 2027, 2028… son válidos cuando el equipo ya está en ese año, y un extracto que cruza diciembre/enero también. Un año anterior a 2026 o posterior al del equipo (p. ej. 2062 por un mal parseo, o un equipo con la fecha atrasada) bloquea con un mensaje que nombra el rango, los años y la fecha del equipo. Si el equipo tiene la fecha mal puesta, todos los extractos irán a `ERROR` con `ANIO_FUERA_DE_RANGO`.

## 9. Varias sedes con un solo motor

Un solo `motor_control_depositos_cbba.py`, un solo orquestador, formatos comunes en `registro_bancos.json`. Lo que cambia por sede está en `p0/sedes.json`: `carpeta_p0`, `carpeta_carga` (relativa a `carpeta_p0`), `cuentas` (`"TODAS"` o lista de ids del registro base) y `cuentas_adicionales` (JSON con entradas de `CUENTAS` propias de la sede). P0 genera el registro efectivo de la sede (formatos comunes + sus cuentas) y lo usa solo en esa corrida; **CBBA usa `registro_bancos.json` tal cual**. Una sede nueva = una entrada en `sedes.json` + (si hace falta) su archivo de cuentas + su equipo/carpetas + su flujo P8 o carpeta. Una cuenta de otra sede presentada en la sede equivocada sale como `CUENTA_NO_REGISTRADA`. Pendiente (no hecho): flujo P8 por sede y un registro de cuentas fuera de `registro_bancos.json` cuando sean muchas.

## 10. Lo que NO se validó (honestidad)

* Todo lo que depende de Microsoft 365 / OneDrive: que el flujo V5 ya apunte a la carpeta nueva, que el cliente de OneDrive suba el JSON y que V5 se dispare con un archivo copiado localmente. Primera prueba real sugerida: un extracto pequeño (p. ej. `bcp_me_1.xls`, 8 movimientos) con V5 activo; esperar 1–2 minutos; revisar `Depositos_Cargas`.
* Las pruebas usan el flujo V5 con SharePoint **simulado** (`p8/ensayo_wdl.py`), no el tenant.
* **P8.5 / `control_origen` queda fuera:** no está desplegado (V7 no se importó en el tenant) y exigiría cambiar el flujo; no es necesario para cargar. Se puede añadir después como etapa opcional.
* `FECHA DE CARGA` sigue siendo la hora local de la máquina del motor (defecto D-15, sin cambios).
* Los flujos antiguos (`NORMALIZAR EXTRACTOS DIARIOS CBBA` y `PROCESAR.txt`) no se usan ni se tocaron.

## 11. Archivos de P0 y pruebas

`p0/orquestador.py` (núcleo y línea de comandos), `p0/sedes.json`, `p0/__main__.py`; cambio en el motor: `motor_control_depositos_cbba.py` (control del año); pruebas: `tests/test_33_anio_dinamico_p0.py` y `tests/test_34_orquestador_p0.py` (`pytest -m p0`).
