"""Empaqueta una definición WDL como ZIP importable de Power Automate («Importar paquete (heredado)»).

La estructura (manifest.json, Microsoft.Flow/flows/..., apisMap, connectionsMap) replica la de los ZIP P8 que ya se
importaron en el tenant piloto. Los UUID son deterministas (uuid5) y propios de P9; no son recursos reales.
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
API_ID = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
FECHA_ZIP = (2026, 10, 1, 0, 0, 0)


def _uuid(nombre_flujo: str, parte: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p9:{nombre_flujo}:{parte}"))


def archivos_paquete(nombre: str, descripcion: str, definicion: dict) -> dict:
    flujo, definicion_id = _uuid(nombre, "flow-resource"), _uuid(nombre, "flow-definition")
    api, conexion = _uuid(nombre, "sharepoint-api"), _uuid(nombre, "sharepoint-connection")
    manifest = {
        "schema": "1.0",
        "details": {"displayName": nombre, "description": descripcion, "createdTime": "2026-10-01T00:00:00Z",
                    "packageTelemetryId": _uuid(nombre, "package-telemetry"), "creator": "N/A", "sourceEnvironment": ""},
        "resources": {
            flujo: {"type": "Microsoft.Flow/flows", "suggestedCreationType": "New", "creationType": "New, Update",
                    "details": {"displayName": nombre}, "configurableBy": "User", "hierarchy": "Root",
                    "dependsOn": [api, conexion]},
            api: {"id": API_ID, "name": "shared_sharepointonline", "type": "Microsoft.PowerApps/apis",
                  "suggestedCreationType": "Existing", "details": {"displayName": "SharePoint"},
                  "configurableBy": "System", "hierarchy": "Child", "dependsOn": []},
            conexion: {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing",
                       "creationType": "Existing", "details": {"displayName": "<CONEXION_SHAREPOINT>"},
                       "configurableBy": "User", "hierarchy": "Child", "dependsOn": [api]},
        },
    }
    envoltura = {
        "name": definicion_id, "id": f"/providers/Microsoft.Flow/flows/{definicion_id}", "type": "Microsoft.Flow/flows",
        "properties": {
            "apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows", "displayName": nombre,
            "definition": definicion,
            "connectionReferences": {"shared_sharepointonline": {
                "connectionName": "<CONEXION_SHAREPOINT>", "source": "Embedded", "id": API_ID, "tier": "NotSpecified",
                "apiName": "sharepointonline", "isProcessSimpleApiReferenceConversionAlreadyDone": False}},
            "flowFailureAlertSubscribed": False, "isManaged": False},
    }
    base = f"Microsoft.Flow/flows/{flujo}"
    return {
        "manifest.json": manifest,
        "Microsoft.Flow/flows/manifest.json": {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [flujo]}},
        f"{base}/apisMap.json": {"shared_sharepointonline": api},
        f"{base}/connectionsMap.json": {"shared_sharepointonline": conexion},
        f"{base}/definition.json": envoltura,
    }


def escribir_zip(destino: Path, nombre: str, descripcion: str, definicion: dict) -> Path:
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for ruta, contenido in archivos_paquete(nombre, descripcion, definicion).items():
            info = zipfile.ZipInfo(ruta, date_time=FECHA_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, json.dumps(contenido, ensure_ascii=False, separators=(",", ":")))
    return destino
