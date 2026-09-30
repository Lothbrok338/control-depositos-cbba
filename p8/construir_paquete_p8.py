#!/usr/bin/env python3
"""Construye los artefactos versionables e importables del flujo P8.

El ZIP usa como referencia estructural el paquete real
NORMALIZADOR_POWER_AUTOMATE.zip exportado desde Power Automate. No copia sus
identificadores de tenant, usuario ni conexion. Los UUID generados aqui son
identificadores internos y deterministas del paquete, no recursos reales.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
import zipfile
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
P8_DIR = RAIZ / "p8"
ESQUEMA_P7 = RAIZ / "esquema_parse_json_p7.json"
DEFINICION_SALIDA = P8_DIR / "flujo_p8_definition.json"
ESQUEMA_LISTAS_SALIDA = P8_DIR / "esquema_listas_p8.json"
ZIP_SALIDA = RAIZ / "P8_CARGA_DEPOSITOS_ACTIVOS.zip"

NOMBRE_FLUJO = "P8 - CARGA DEPOSITOS ACTIVOS"
API_ID = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
CONEXION = "shared_sharepointonline"
ESTADOS_EJECUCION = ["Succeeded", "Failed", "Skipped", "TimedOut"]


def _uuid(nombre: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p8:{nombre}"))


FLOW_RESOURCE_ID = _uuid("flow-resource")
FLOW_DEFINITION_ID = _uuid("flow-definition")
API_RESOURCE_ID = _uuid("sharepoint-api")
CONNECTION_RESOURCE_ID = _uuid("sharepoint-connection")
TELEMETRY_ID = _uuid("package-telemetry")


def _cargar_adaptador():
    spec = importlib.util.spec_from_file_location("adaptador_m365_p8_fuente", RAIZ / "adaptador_m365.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo leer adaptador_m365.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


try:
    from .definicion import construir_definicion
except ImportError:  # ejecución como script: python p8/construir_paquete_p8.py
    from definicion import construir_definicion


def construir_esquema_listas(columnas_m365) -> dict:
    tipos = {
        "texto": "Texto de una linea",
        "texto_largo": "Varias lineas de texto sin formato",
        "numero": "Numero, 2 decimales",
        "fecha": "Fecha y hora, solo fecha",
    }
    activos = []
    indices = {"CLAVE_TRANSACCION", "BANCO", "FECHA_MOVIMIENTO", "LOTE_CARGA"}
    for _, tecnico, tipo, obligatorio in columnas_m365:
        activos.append(
            {
                "nombre_tecnico": tecnico,
                "tipo": tipos[tipo],
                "obligatoria": obligatorio,
                "indexada": tecnico in indices,
                "valores_unicos": tecnico == "CLAVE_TRANSACCION",
                "origen": "P7",
            }
        )
    activos.extend(
        [
            {"nombre_tecnico": "ESTADO_ASIGNACION", "tipo": "Opcion", "obligatoria": True, "indexada": True, "valores_unicos": False, "valores": ["DISPONIBLE"], "predeterminado": "DISPONIBLE", "permitir_relleno": False, "origen": "P8"},
            {"nombre_tecnico": "ESTUDIANTE", "tipo": "Texto de una linea", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
            {"nombre_tecnico": "CODIGO_ESTUDIANTE", "tipo": "Texto de una linea", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
            {"nombre_tecnico": "SOLICITADO_POR", "tipo": "Texto de una linea", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
            {"nombre_tecnico": "SEDE_ASIGNACION", "tipo": "Texto de una linea", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
            {"nombre_tecnico": "USUARIO_ASIGNACION", "tipo": "Texto de una linea", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
            {"nombre_tecnico": "FECHA_HORA_ASIGNACION", "tipo": "Fecha y hora, incluir hora", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
            {"nombre_tecnico": "OBSERVACION", "tipo": "Varias lineas de texto sin formato", "obligatoria": False, "indexada": False, "valores_unicos": False, "origen": "operativo"},
        ]
    )
    cargas = [
        ("LOTE_ID", "Texto de una linea", True, True, None),
        ("FECHA_HORA_PROCESO", "Fecha y hora, incluir hora", True, True, None),
        ("ARCHIVO_FUENTE", "Texto de una linea", True, False, None),
        ("SHA256", "Texto de una linea", True, False, None),
        ("CANTIDAD_RECIBIDA", "Numero, 0 decimales", True, False, None),
        ("CANTIDAD_VALIDA", "Numero, 0 decimales", True, False, None),
        ("CANTIDAD_NUEVA", "Numero, 0 decimales", True, False, None),
        ("CANTIDAD_YA_EXISTE", "Numero, 0 decimales", True, False, None),
        ("CANTIDAD_ERROR", "Numero, 0 decimales", True, False, None),
        ("ESTADO_LOTE", "Opcion", True, False, ["COMPLETADO", "COMPLETADO_CON_ERRORES", "FALLIDO"]),
        ("MENSAJE_ERROR", "Varias lineas de texto sin formato", False, False, None),
        ("ARCHIVO_JSON", "Texto de una linea", False, False, None),
        ("ID_EJECUCION_FLUJO", "Texto de una linea", False, False, None),
    ]
    return {
        "Depositos_Activos": {
            "title_obligatorio": False,
            "columnas": activos,
            "total_columnas_sin_title": len(activos),
        },
        "Depositos_Cargas": {
            "title_obligatorio": False,
            "columnas": [
                {
                    "nombre_tecnico": nombre,
                    "tipo": tipo,
                    "obligatoria": obligatoria,
                    "indexada": indexada,
                    "valores_unicos": False,
                    **({"valores": valores, "permitir_relleno": False} if valores else {}),
                }
                for nombre, tipo, obligatoria, indexada, valores in cargas
            ],
            "total_columnas_sin_title": len(cargas),
        },
    }


def _envolver_definicion(definicion: dict) -> dict:
    return {
        "name": FLOW_DEFINITION_ID,
        "id": f"/providers/Microsoft.Flow/flows/{FLOW_DEFINITION_ID}",
        "type": "Microsoft.Flow/flows",
        "properties": {
            "apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows",
            "displayName": NOMBRE_FLUJO,
            "definition": definicion,
            "connectionReferences": {
                CONEXION: {
                    "connectionName": "<CONEXION_SHAREPOINT>",
                    "source": "Embedded",
                    "id": API_ID,
                    "tier": "NotSpecified",
                    "apiName": "sharepointonline",
                    "isProcessSimpleApiReferenceConversionAlreadyDone": False,
                }
            },
            "flowFailureAlertSubscribed": False,
            "isManaged": False,
        },
    }


def _archivos_paquete(definicion: dict) -> dict[str, dict]:
    manifest = {
        "schema": "1.0",
        "details": {
            "displayName": NOMBRE_FLUJO,
            "description": "Carga idempotente de artefactos P7 a Depositos_Activos y Depositos_Cargas.",
            "createdTime": "2026-09-30T00:00:00Z",
            "packageTelemetryId": TELEMETRY_ID,
            "creator": "N/A",
            "sourceEnvironment": "",
        },
        "resources": {
            FLOW_RESOURCE_ID: {
                "type": "Microsoft.Flow/flows",
                "suggestedCreationType": "New",
                "creationType": "New, Update",
                "details": {"displayName": NOMBRE_FLUJO},
                "configurableBy": "User",
                "hierarchy": "Root",
                "dependsOn": [API_RESOURCE_ID, CONNECTION_RESOURCE_ID],
            },
            API_RESOURCE_ID: {
                "id": API_ID,
                "name": CONEXION,
                "type": "Microsoft.PowerApps/apis",
                "suggestedCreationType": "Existing",
                "details": {"displayName": "SharePoint"},
                "configurableBy": "System",
                "hierarchy": "Child",
                "dependsOn": [],
            },
            CONNECTION_RESOURCE_ID: {
                "type": "Microsoft.PowerApps/apis/connections",
                "suggestedCreationType": "Existing",
                "creationType": "Existing",
                "details": {"displayName": "<CONEXION_SHAREPOINT>"},
                "configurableBy": "User",
                "hierarchy": "Child",
                "dependsOn": [API_RESOURCE_ID],
            },
        },
    }
    return {
        "manifest.json": manifest,
        "Microsoft.Flow/flows/manifest.json": {
            "packageSchemaVersion": "1.0",
            "flowAssets": {"assetPaths": [FLOW_RESOURCE_ID]},
        },
        f"Microsoft.Flow/flows/{FLOW_RESOURCE_ID}/apisMap.json": {CONEXION: API_RESOURCE_ID},
        f"Microsoft.Flow/flows/{FLOW_RESOURCE_ID}/connectionsMap.json": {
            CONEXION: CONNECTION_RESOURCE_ID
        },
        f"Microsoft.Flow/flows/{FLOW_RESOURCE_ID}/definition.json": _envolver_definicion(definicion),
    }


def escribir_artefactos() -> tuple[Path, Path, Path]:
    adaptador = _cargar_adaptador()
    esquema_p7 = json.loads(ESQUEMA_P7.read_text(encoding="utf-8"))
    definicion = construir_definicion(esquema_p7, adaptador.COLUMNAS_M365)
    esquema_listas = construir_esquema_listas(adaptador.COLUMNAS_M365)

    DEFINICION_SALIDA.write_text(
        json.dumps(definicion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ESQUEMA_LISTAS_SALIDA.write_text(
        json.dumps(esquema_listas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    archivos = _archivos_paquete(definicion)
    with zipfile.ZipFile(ZIP_SALIDA, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for ruta, contenido in archivos.items():
            info = zipfile.ZipInfo(ruta, date_time=(2026, 9, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, json.dumps(contenido, ensure_ascii=False, separators=(",", ":")))
    return DEFINICION_SALIDA, ESQUEMA_LISTAS_SALIDA, ZIP_SALIDA


if __name__ == "__main__":
    for ruta_generada in escribir_artefactos():
        print(ruta_generada.relative_to(RAIZ))
