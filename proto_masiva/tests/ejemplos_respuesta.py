"""Ejemplos de la RESPUESTA del flujo (contrato real), GENERADOS ejecutando el flujo contra el tenant simulado.

    python proto_masiva/tests/ejemplos_respuesta.py    ->  proto_masiva/flows/ejemplos_respuesta/*.json

Así los ejemplos de la documentación no pueden desfasarse del flujo: `test_07` comprueba que los archivos versionados son exactamente
esta salida. Son respuestas de una SIMULACIÓN (tiempos del reloj simulado, no del tenant).
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for ruta in (RAIZ, Path(__file__).resolve().parent):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

import test_07_prevalidacion_real as T  # noqa: E402
from simulador import TenantSimulado, deposito, procesar  # noqa: E402

DESTINO = RAIZ / "proto_masiva" / "flows" / "ejemplos_respuesta"
XLSX = RAIZ / "proto_masiva" / "xlsx"


def _ejemplo(escenario, respuesta):
    return {"escenario": escenario, "respuesta": respuesta, "detalle_json_expandido": json.loads(respuesta["detalle_json"])}


def ejemplos():
    deps = [deposito(101, "BNB", "3000100152", "A-001", 1000.0), deposito(102, "BCP", "301-5005684-3-97", "A-002", 250.5, moneda="USD"),
            deposito(103, "BISA", "0696870039", "001234", 500.0)]
    filas = [T.fila("BNB", "3000100152", "A-001", 1000.0), T.fila("BCP", "301-5005684-3-97", "A-002", 250.5, "USD"),
             T.fila("BISA", "0696870039", "001234", 500.0)]
    salida = {"01_OK_todas_validas.json": _ejemplo("3 filas, cada una con su depósito DISPONIBLE (incluye CUENTA y CÓDIGO con ceros iniciales)",
                                                  T.corre(filas, deps)[1])}
    mixtas, deps_mixtas = T.escenario_completo()
    salida["02_OBSERVADO_los_9_estados.json"] = _ejemplo(
        "10 filas que ejercitan los 9 resultados posibles (VALIDO + 8 observaciones). Resultado global OBSERVADO, no ERROR",
        T.corre(mixtas, deps_mixtas)[1])
    t, e = procesar("Plantilla_Confirmacion_Masiva_P9.xlsx", (XLSX / "Plantilla_Confirmacion_Masiva_P9.xlsx").read_bytes(),
                    tenant=TenantSimulado(depositos=deps))
    salida["03_ERROR_ARCHIVO_VACIO.json"] = _ejemplo("la plantilla vacía: error controlado, no se consulta Depositos_Activos", e.respuesta)
    t = TenantSimulado(depositos=deps)
    t.fallos["depositos"] = ("Failed", 500)
    salida["04_ERROR_ERROR_SHAREPOINT.json"] = _ejemplo("SharePoint responde 500 al leer Depositos_Activos: error técnico, sin detalle por fila",
                                                       T.corre(filas, None, tenant=t)[1])
    salida["05_ERROR_DEPOSITOS_DEMASIADOS.json"] = _ejemplo(
        "SharePoint indica que hay más depósitos que el tope de lectura: se avisa en vez de marcar NO_ENCONTRADO por error",
        T.corre(filas, deps, tope=2)[1])
    return salida


def escribir():
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in ejemplos().items():
        (DESTINO / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sorted(DESTINO.glob("*.json"))


if __name__ == "__main__":
    for ruta in escribir():
        print(ruta.relative_to(RAIZ))
