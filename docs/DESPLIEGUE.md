# Despliegue (estado al 2026-11-03)

## Servicios en Railway

| Servicio | Rama de origen | Qué hace | Estado |
|---|---|---|---|
| `p0-api` | `experiment/p9-masiva-prototipo` | Normaliza extractos bancarios | En producción de prueba |
| `p10-api` | `deploy/p10-api` | Genera el histórico mensual | En producción de prueba |

- `deploy/p10-api` existe solo para construir `p10-api`: sus `Dockerfile`, `.dockerignore` y `railway.json` de la raíz son los de P10 (copia de `p10/Dockerfile` y `p10/Dockerfile.dockerignore`). Para actualizarlo: fusionar la rama de trabajo y volver a copiar esos dos archivos.
- Deployment vigente de `p10-api`: `72569ef1` (commit `456ca36`). Los commits posteriores de la rama de trabajo solo cambian flujo, ZIP y documentación; el código del servicio es idéntico.

## Flujos de Power Automate (12)

En la Solution `CONTROL DE DEPÓSITOS CBBA` (exportada 1.0.0.1, no administrada) junto con la app de Power Apps.

| Flujo | Paquete en el repositorio |
|---|---|
| `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD` | `P0_CARGA_EXTRACTOS_BANCARIOS_CLOUD_V5.zip` |
| `P8_CARGA_DEPOSITOS_ACTIVOS` | en el tenant corre la V5 (`P8_CARGA_DEPOSITOS_ACTIVOS_V5_TENANT_LISTAS_REALES.zip`) |
| `P8_PROVISIONAR_LISTAS` | `P8_PROVISIONAR_LISTAS_V3_HASH_SHA256.zip` |
| `P9_ASIGNAR_DEPOSITO` | `P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip` |
| `P9_HABILITAR_ESTADO_ASIGNADO`, `P9_PROVISIONAR_REVERSION`, `P9_SOLICITAR_REVERSION`, `P9_RESOLVER_REVERSION`, `P9_EXPIRAR_REVERSIONES`, `P9_RECUPERAR_REVERSION` | un `.zip` con su nombre |
| `P10_SINCRONIZAR_HISTORICO` | `P10_SINCRONIZAR_HISTORICO_V1.zip` · SHA-256 `018e8ebc75cf765e73a281790d911bfa10ba97f027206ea824f5a5c26f0be9a7` (170 acciones) |
| `P10_PROVISIONAR_CONTROL` | `P10_PROVISIONAR_CONTROL_V1.zip` · SHA-256 `7fe0c5347628b3b3b8375417b15a4033930922dd966029dbe15999d2fc1530c7` |

Los paquetes del repositorio traen marcadores en lugar de URL del sitio y token; en el tenant esos valores están completados.

## Datos (fuera del repositorio)

Lista `Depositos_Activos`, `P10_Control` y listas de reversión en SharePoint; `ENTRADA`, `PROCESADOS`, `P10_ESTADO`, `P10_HISTORICO` y `P10_CONFIG` en OneDrive. Los tokens están solo en Railway y en OneDrive (`P10_CONFIG`).

## Power Apps

Pantalla vigente: `p9/reversion/powerapps/Main_Screen.yaml`. Variante sin límite de fechas (provisoria): `docs/powerapps/Main_Screen_SIN_LIMITE_FECHAS.yaml`. Go-live 2027: volver a un candado de fecha `01/01/2027`.
