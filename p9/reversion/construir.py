"""Genera definiciones y cinco ZIP; no se conecta al tenant.

Sin argumentos, entrega configuración pendiente, sin GUID reales inventados.
Después de provisionar: --config configuracion.json --salida carpeta_nueva.
Las copias configuradas se escriben solo en esa carpeta; no sobrescriben los
JSON genéricos versionados ni sus ZIP. También se conservan los flags separados.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from p9.reversion import flujos
from p9.reversion.contrato import uuid_canonico
from p9.reversion.paquete import RAIZ, escribir_zip
from p9.reversion.provisionar import construir_definicion as provisionar
from p9.reversion.wdl import walk

CARPETA = Path(__file__).resolve().parent
COMPONENTES = {
    "solicitar": ("P9_SOLICITAR_REVERSION", flujos.construir_solicitar, ("shared_sharepointonline", "shared_office365users")),
    "resolver": ("P9_RESOLVER_REVERSION", flujos.construir_resolver, ("shared_sharepointonline", "shared_approvals")),
    "expirar": ("P9_EXPIRAR_REVERSIONES", flujos.construir_expirar, ("shared_sharepointonline",)),
    "recuperar": ("P9_RECUPERAR_REVERSION", flujos.construir_recuperar, ("shared_sharepointonline", "shared_office365users", "shared_approvals")),
    "provisionar": ("P9_PROVISIONAR_REVERSION", provisionar, ("shared_sharepointonline",)),
}


def validar_definicion(doc):
    nodes = list(walk(doc["actions"]))
    names = [name for name, _ in nodes]
    if len(nodes) > 500 or len(names) != len(set(names)):
        raise ValueError("La definición supera 500 acciones o repite nombres")
    if any(len(name) > 80 for name in names):
        raise ValueError("Nombre de acción mayor que 80 caracteres")

    def scopes(actions, depth=0, in_loop=False):
        if depth >= 8 and actions:
            raise ValueError("Anidación superior a ocho niveles")
        for name, node in actions.items():
            if any(dep not in actions for dep in node.get("runAfter", {})):
                raise ValueError("runAfter fuera de su ámbito: " + name)
            if in_loop and node["type"] == "Terminate":
                raise ValueError("Terminate dentro de un bucle: " + name)
            scopes(node.get("actions", {}), depth + 1, in_loop or node["type"] in ("Until", "Foreach"))
            scopes(node.get("else", {}).get("actions", {}), depth + 1, in_loop)
            params = node.get("inputs", {}).get("parameters", {}) if isinstance(node.get("inputs"), dict) else {}
            headers = params.get("parameters/headers", {})
            if headers.get("IF-MATCH") == "*":
                raise ValueError("If-Match comodín prohibido")
            if headers.get("X-HTTP-Method") == "MERGE" and node["inputs"].get("retryPolicy") != {"type": "none"}:
                raise ValueError("MERGE con reintento automático")
    scopes(doc["actions"])
    return len(nodes)


def validar_sitio(sitio):
    if not isinstance(sitio, str) or any(char.isspace() or ord(char) < 32 for char in sitio):
        raise ValueError("Sitio SharePoint inválido")
    parsed = urlsplit(sitio)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.sharepoint\.com", parsed.hostname or "")
            or parsed.query or parsed.fragment or any(part == ".." for part in parsed.path.split("/"))):
        raise ValueError("El sitio debe ser una URL HTTPS de SharePoint sin credenciales, consulta ni fragmento")
    return sitio.rstrip("/")


def validar_aprobadores(values):
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise ValueError("aprobadores debe contener dos UPN distintos")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[^\s@;]+@[^\s@;]+\.[^\s@;]+", value):
            raise ValueError("Cada aprobador debe ser un UPN sin espacios ni separadores")
        normalized.append(value.lower())
    if len(set(normalized)) != 2:
        raise ValueError("Los dos aprobadores deben ser distintos")
    return normalized


def cargar_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    required = {"sitio_sharepoint", "lista_reversiones_id", "responsables_recuperacion_ids"}
    if not isinstance(config, dict) or not required <= config.keys() or set(config) - required - {"aprobadores"}:
        raise ValueError("El JSON requiere sitio_sharepoint, lista_reversiones_id, responsables_recuperacion_ids; aprobadores es opcional")
    result = dict(config)
    result["sitio_sharepoint"] = validar_sitio(config["sitio_sharepoint"])
    result["lista_reversiones_id"] = uuid_canonico(config["lista_reversiones_id"])
    ids = config["responsables_recuperacion_ids"]
    if not isinstance(ids, list) or not ids:
        raise ValueError("responsables_recuperacion_ids debe ser una lista no vacía de IDs Entra verificados")
    result["responsables_recuperacion_ids"] = [uuid_canonico(value) for value in ids]
    if len(set(result["responsables_recuperacion_ids"])) != len(ids):
        raise ValueError("Los responsables de recuperación no deben repetirse")
    if "aprobadores" in config:
        result["aprobadores"] = validar_aprobadores(config["aprobadores"])
    return result


def generar(sitio=None, lista_reversiones_id=None, responsables=(), salida=None, aprobadores=None):
    if sitio is not None:
        sitio = validar_sitio(sitio)
    if lista_reversiones_id is not None:
        lista_reversiones_id = uuid_canonico(lista_reversiones_id)
    responsables = [uuid_canonico(value) for value in responsables]
    if len(set(responsables)) != len(responsables):
        raise ValueError("Los responsables de recuperación no deben repetirse")
    if aprobadores is not None:
        aprobadores = validar_aprobadores(aprobadores)
    configured = sitio is not None or lista_reversiones_id is not None or bool(responsables) or aprobadores is not None
    if configured and salida is None:
        raise ValueError("La configuración requiere --salida para conservar intactos los artefactos genéricos")
    destino = Path(salida).resolve() if salida else RAIZ
    if configured and destino in (RAIZ.resolve(), CARPETA.resolve()):
        raise ValueError("Las copias configuradas requieren una carpeta distinta de la raíz y de p9/reversion")
    destino.mkdir(parents=True, exist_ok=True)
    definitions_dir = destino if salida else CARPETA
    resumen = []
    for key, (nombre, build, connections) in COMPONENTES.items():
        doc = build()
        if sitio:
            # Provisionar conserva su sitio como entrada manual. Las cuatro
            # definiciones operativas reciben la copia de configuración validada.
            if key != "provisionar" and "PARAM_SITIO_SHAREPOINT" in doc["actions"]:
                doc["actions"]["PARAM_SITIO_SHAREPOINT"]["inputs"] = sitio.rstrip("/")
            for trigger in doc["triggers"].values():
                if "dataset" in trigger.get("inputs", {}).get("parameters", {}):
                    trigger["inputs"]["parameters"]["dataset"] = sitio.rstrip("/")
        if key == "resolver" and lista_reversiones_id:
            doc["parameters"]["LISTA_REVERSIONES_ID"]["defaultValue"] = lista_reversiones_id
        if key == "resolver" and aprobadores is not None:
            doc["actions"]["PARAM_APROBADORES"]["inputs"] = ";".join(aprobadores)
        if key == "recuperar":
            doc["actions"]["PARAM_RESPONSABLES_RECUPERACION"]["inputs"] = responsables
        count = validar_definicion(doc)
        definition_file = definitions_dir / f"flujo_{key}_definition.json"
        content = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not definition_file.exists() or definition_file.read_bytes() != content:
            definition_file.write_bytes(content)
        package = destino / (nombre + ".zip")
        escribir_zip(package, nombre, doc, connections)
        resumen.append({"flujo": nombre, "acciones": count, "definicion": str(definition_file), "paquete": str(package)})
    return resumen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="JSON de configuración verificada del tenant; requiere --salida")
    parser.add_argument("--sitio")
    parser.add_argument("--lista-reversiones-id")
    parser.add_argument("--responsable-id", action="append", default=[])
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    if args.config:
        if args.sitio is not None or args.lista_reversiones_id is not None or args.responsable_id:
            parser.error("--config no se combina con --sitio, --lista-reversiones-id o --responsable-id")
        if args.salida is None:
            parser.error("--config requiere --salida")
        values = cargar_config(args.config)
        rows = generar(values["sitio_sharepoint"], values["lista_reversiones_id"],
            values["responsables_recuperacion_ids"], args.salida, values.get("aprobadores"))
    else:
        rows = generar(args.sitio, args.lista_reversiones_id, args.responsable_id, args.salida)
    for row in rows:
        print(f"{row['flujo']}: {row['acciones']} acciones; {row['paquete']}")


if __name__ == "__main__":
    main()
