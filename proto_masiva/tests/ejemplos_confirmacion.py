"""Ejemplos de la RESPUESTA de P9_MASIVA_PROTO_CONFIRMAR, GENERADOS ejecutando el flujo contra el SharePoint simulado.

    python proto_masiva/tests/ejemplos_confirmacion.py    ->  proto_masiva/flows/ejemplos_respuesta_confirmacion/*.json

`test_08` comprueba que los archivos versionados son exactamente esta salida (no se desfasan del flujo).
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for ruta in (RAIZ, Path(__file__).resolve().parent):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

import test_08_confirmacion_masiva as T  # noqa: E402
from proto_masiva.flows import construir_confirmar as K  # noqa: E402
from simulador_confirmacion import TenantConfirmacion, confirmar, deposito, fila_validada  # noqa: E402

DESTINO = RAIZ / "proto_masiva" / "flows" / "ejemplos_respuesta_confirmacion"


def _ej(escenario, respuesta):
    return {"escenario": escenario, "respuesta": respuesta, "detalle_json_expandido": json.loads(respuesta["detalle_json"])}


def ejemplos():
    deps = [deposito(i, codigo=f"C{i}", importe=100.0 + i) for i in range(1, 4)]
    t = TenantConfirmacion(deps)
    s = {"01_OK_todas_confirmadas.json": _ej("3 filas VALIDO que siguen siendo válidas: las 3 se confirman", confirmar([fila_validada(d) for d in deps], t))}
    t, filas = T.escenario_mixto()
    s["02_PARCIAL_los_6_resultados.json"] = _ej(
        "6 filas: CONFIRMADO + NO_DISPONIBLE + CONFLICTO (412) + CONFLICTO_DATOS + NO_ENCONTRADO + ERROR_FILA. Lo confirmado NO se revierte", confirmar(filas, t))
    t = TenantConfirmacion([deposito(1, estado="ASIGNADO")])
    s["03_PARCIAL_ninguna_confirmada.json"] = _ej("el único depósito fue asignado por otro usuario entre PREVALIDAR y CONFIRMAR",
                                                 confirmar([fila_validada(deposito(1))], t))
    s["04_ERROR_ENTRADA_INVALIDA.json"] = _ej("detalle_json no es un arreglo JSON: no se toca SharePoint", confirmar(None, TenantConfirmacion(), texto="no es json"))
    s["05_ERROR_LOTE_EXCEDE_LIMITE.json"] = _ej(
        "7 filas con un máximo por llamada de 5: se rechaza la llamada completa, sin confirmar nada",
        confirmar([fila_validada(deposito(i, codigo=f"C{i}")) for i in range(1, 8)], TenantConfirmacion(), definicion=K.construir_definicion(max_por_llamada=5)))
    return s


def escribir():
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in ejemplos().items():
        (DESTINO / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sorted(DESTINO.glob("*.json"))


if __name__ == "__main__":
    for r in escribir():
        print(r.relative_to(RAIZ))
