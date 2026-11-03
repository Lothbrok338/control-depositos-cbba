"""Ejemplos de lo que devuelven P9_MASIVA_PROTO_CONFIRMAR (respuesta TEMPRANA) y P9_MASIVA_PROTO_ESTADO, GENERADOS ejecutando los flujos contra el SharePoint simulado.

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
from simulador_confirmacion import TenantConfirmacion, confirmar, consultar_estado, deposito, fila_validada  # noqa: E402

DESTINO = RAIZ / "proto_masiva" / "flows" / "ejemplos_respuesta_confirmacion"


def _ej(escenario, r, tenant=None):
    """r = Ejecucion. `respuesta_temprana` = lo que recibe Power Apps al pulsar; `estado_final` = el archivo temporal; `consulta_estado` = P9_MASIVA_PROTO_ESTADO."""
    salida = {"escenario": escenario, "respuesta_temprana": r.aceptacion}
    if r.nombre_archivo:
        salida["estado_final"] = r.estado
        salida["consulta_estado"] = consultar_estado(tenant or r.tenant, r.uid)
    return salida


def ejemplos():
    deps = [deposito(i, codigo=f"C{i}", importe=100.0 + i) for i in range(1, 4)]
    t = TenantConfirmacion(deps)
    s = {"01_OK_todas_confirmadas.json": _ej("3 filas VALIDO que siguen siendo válidas: las 3 se confirman; el detalle final queda vacío", confirmar([fila_validada(d) for d in deps], t))}
    t, filas = T.escenario_mixto()
    s["02_PARCIAL_los_5_resultados_no_confirmados.json"] = _ej(
        "6 filas: 1 CONFIRMADO + NO_DISPONIBLE + CONFLICTO (412) + CONFLICTO_DATOS + NO_ENCONTRADO + ERROR_FILA. Lo confirmado NO se revierte y NO se lista: solo las 5 no confirmadas",
        confirmar(filas, t))
    t = TenantConfirmacion([deposito(1, estado="ASIGNADO")])
    s["03_NINGUNA_confirmada.json"] = _ej("el único depósito fue asignado por otro usuario entre PREVALIDAR y CONFIRMAR", confirmar([fila_validada(deposito(1))], t))
    s["04_ERROR_ENTRADA_INVALIDA.json"] = _ej("detalle_json no es un arreglo JSON: respuesta temprana de ERROR, no se crea estado ni se toca SharePoint",
                                              confirmar(None, TenantConfirmacion(), texto="no es json"))
    s["05_ERROR_LOTE_EXCEDE_LIMITE.json"] = _ej(
        "7 filas con un máximo por llamada de 5: se rechaza la llamada completa, sin confirmar nada",
        confirmar([fila_validada(deposito(i, codigo=f"C{i}")) for i in range(1, 8)], TenantConfirmacion(), definicion=K.construir_definicion(max_por_llamada=5)))
    # estado INTERMEDIO: 60 filas, el estado se actualiza cada 25; se consulta la versión con 50 procesadas
    deps = [deposito(i, codigo=f"C{i}", importe=10.0 + i) for i in range(1, 61)]
    t = TenantConfirmacion(deps)
    t.carreras[7] = {"DESCRIPCION": "otro usuario"}
    r = confirmar([fila_validada(d) for d in deps], t)
    intermedio = next(v for v in r.versiones if v["filas_procesadas"] == 50)
    t.archivos[r.nombre_archivo]["contenido"] = json.dumps(intermedio, ensure_ascii=False)
    s["06_ESTADO_intermedio_50_de_60_procesados.json"] = {
        "escenario": "60 filas válidas; Power Apps consulta mientras el flujo sigue procesando (50 de 60). El detalle de no confirmadas llega solo al terminar",
        "respuesta_temprana": r.aceptacion, "estado_en_curso": intermedio, "consulta_estado": consultar_estado(t, r.uid)}
    return s


def escribir():
    DESTINO.mkdir(parents=True, exist_ok=True)
    for viejo in DESTINO.glob("*.json"):
        viejo.unlink()
    for nombre, contenido in ejemplos().items():
        (DESTINO / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sorted(DESTINO.glob("*.json"))


if __name__ == "__main__":
    for r in escribir():
        print(r.relative_to(RAIZ))
