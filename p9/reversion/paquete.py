"""Paquetes heredados reproducibles; identificadores UUID5 solo de recursos ZIP."""
from __future__ import annotations
import json
import io
import uuid
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FECHA_ZIP = (2026, 10, 3, 0, 0, 0)
CONEXIONES = {
    "shared_sharepointonline": ("SharePoint", "Embedded"),
    "shared_office365users": ("Office 365 Users", "Invoker"),
    "shared_approvals": ("Standard approvals", "Embedded"),
}


def _uuid(nombre, parte):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"control-depositos-cbba:p9:reversion:v2:{nombre}:{parte}"))


def archivos_paquete(nombre, definition, conexiones):
    flow = _uuid(nombre, "resource")
    internal = _uuid(nombre, "definition")
    resources, references, apis, connections = {}, {}, {}, {}
    dependencies = []
    for key in conexiones:
        title, source = CONEXIONES[key]
        api_id = f"/providers/Microsoft.PowerApps/apis/{key}"
        api_resource, conn_resource = _uuid(nombre, key + ":api"), _uuid(nombre, key + ":connection")
        dependencies += [api_resource, conn_resource]
        resources[api_resource] = {"id": api_id, "name": key, "type": "Microsoft.PowerApps/apis",
            "suggestedCreationType": "Existing", "details": {"displayName": title},
            "configurableBy": "System", "hierarchy": "Child", "dependsOn": []}
        resources[conn_resource] = {"type": "Microsoft.PowerApps/apis/connections", "suggestedCreationType": "Existing",
            "creationType": "Existing", "details": {"displayName": f"<CONEXION_{key.upper()}>"},
            "configurableBy": "User", "hierarchy": "Child", "dependsOn": [api_resource]}
        references[key] = {"connectionName": f"<CONEXION_{key.upper()}>", "source": source,
            "id": api_id, "tier": "NotSpecified", "apiName": key.removeprefix("shared_"),
            "isProcessSimpleApiReferenceConversionAlreadyDone": False}
        apis[key], connections[key] = api_resource, conn_resource
    resources[flow] = {"type": "Microsoft.Flow/flows", "suggestedCreationType": "New", "creationType": "New, Update",
        "details": {"displayName": nombre}, "configurableBy": "User", "hierarchy": "Root", "dependsOn": dependencies}
    wrapper = {"name": internal, "id": f"/providers/Microsoft.Flow/flows/{internal}", "type": "Microsoft.Flow/flows",
        "properties": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_logicflows", "displayName": nombre,
            "definition": definition, "connectionReferences": references,
            "flowFailureAlertSubscribed": False, "isManaged": False}}
    base = f"Microsoft.Flow/flows/{flow}"
    return {
        "manifest.json": {"schema": "1.0", "details": {"displayName": nombre,
            "description": "Reversión V2 con snapshot, exclusión única, ETag y recuperación manual auditada.",
            "createdTime": "2026-10-03T00:00:00Z", "packageTelemetryId": _uuid(nombre, "telemetry"),
            "creator": "N/A", "sourceEnvironment": ""}, "resources": resources},
        "Microsoft.Flow/flows/manifest.json": {"packageSchemaVersion": "1.0", "flowAssets": {"assetPaths": [flow]}},
        f"{base}/definition.json": wrapper, f"{base}/apisMap.json": apis, f"{base}/connectionsMap.json": connections}


def escribir_zip(destino, nombre, definition, conexiones):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in archivos_paquete(nombre, definition, conexiones).items():
            info = zipfile.ZipInfo(path, date_time=FECHA_ZIP)
            info.create_system = 3
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    path = Path(destino)
    data = buffer.getvalue()
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
    return path
