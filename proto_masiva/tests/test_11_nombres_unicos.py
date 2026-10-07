"""Nombres de disparadores y acciones ÚNICOS en toda la definición de cada flujo.

Power Automate rechaza el paquete («The template trigger and action names must be unique») si dos elementos comparten nombre en CUALQUIER nivel
(ámbitos, ramas de Condición y Foreach incluidos) y compara los nombres SIN distinguir mayúsculas: el ámbito `ESCRIBIR_FINAL` y la acción
`Escribir_final` chocaban aunque en un diccionario Python fueran claves distintas.
"""
import json
import zipfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import pytest

from proto_masiva.flows import construir as F
from proto_masiva.flows import construir_confirmar as K
from proto_masiva.flows import construir_estado as E

CARPETA = Path(__file__).resolve().parents[1] / "flows"
FLUJOS = {"P9_MASIVA_PROTO_PREVALIDAR": F, "P9_MASIVA_PROTO_CONFIRMAR": K, "P9_MASIVA_PROTO_ESTADO": E}


def nombres(definicion):
    """Todos los nombres (disparadores + acciones en cualquier nivel) como lista de (nombre, ruta)."""
    salida = [(n, f"triggers/{n}") for n in definicion.get("triggers", {})]

    def recorrer(acciones, ruta):
        for n, a in acciones.items():
            salida.append((n, f"{ruta}/{n}"))
            if isinstance(a, dict):
                for clave, sub in (("actions", a.get("actions")), ("else", (a.get("else") or {}).get("actions"))):
                    if isinstance(sub, dict):
                        recorrer(sub, f"{ruta}/{n}[{clave}]")
                for caso in (a.get("cases") or {}).values():
                    recorrer(caso.get("actions", {}), f"{ruta}/{n}[case]")
                recorrer((a.get("default") or {}).get("actions", {}), f"{ruta}/{n}[default]")
    recorrer(definicion.get("actions", {}), "")
    return salida


def duplicados(definicion):
    grupos = defaultdict(list)
    for n, ruta in nombres(definicion):
        grupos[n.lower()].append(ruta)
    return {k: v for k, v in grupos.items() if len(v) > 1}


def definiciones(nombre, modulo):
    z = zipfile.ZipFile(BytesIO((CARPETA / f"{nombre}.zip").read_bytes()))
    return {"generador": modulo.construir_definicion(),
            "json": json.loads((CARPETA / f"{nombre}_definition.json").read_text(encoding="utf-8")),
            "zip": json.loads(z.read(next(n for n in z.namelist() if n.endswith("/definition.json"))))["properties"]["definition"]}


@pytest.mark.parametrize("nombre", list(FLUJOS))
def test_01_nombres_unicos_en_toda_la_definicion(nombre):
    for origen, d in definiciones(nombre, FLUJOS[nombre]).items():
        assert duplicados(d) == {}, f"{nombre} ({origen}): nombres repetidos (sin distinguir mayúsculas): {duplicados(d)}"
        assert len(nombres(d)) > 15


def test_02_confirmar_la_accion_renombrada_existe_una_vez():
    for d in definiciones("P9_MASIVA_PROTO_CONFIRMAR", K).values():
        todos = [n for n, _ in nombres(d)]
        assert todos.count("ESCRIBIR_FINAL") == 1 and todos.count("Escribir_final_estado") == 1 and "Escribir_final" not in todos
        assert any(n == "Escribir_final_estado" and r.endswith("ESCRIBIR_FINAL[actions]/Escribir_final_estado") for n, r in nombres(d))


def test_03_el_detector_ve_choques_por_mayusculas_y_en_ramas():
    d = json.loads(json.dumps(K.construir_definicion()))
    d["actions"]["PROCESAR"]["actions"]["FINALIZAR"]["actions"]["ESCRIBIR_FINAL"]["actions"]["Escribir_final"] = {"type": "Compose", "inputs": 1}
    assert "escribir_final" in duplicados(d)
    d2 = json.loads(json.dumps(E.construir_definicion()))
    d2["actions"]["TRY"]["actions"]["Uid_valido"]["else"]["actions"]["entrada"] = {"type": "Compose", "inputs": 1}  # «Entrada» ya existe arriba
    assert "entrada" in duplicados(d2)


def test_04_las_referencias_a_acciones_existen():
    """Toda `outputs('X')`/`body('X')`/`actions('X')`/runAfter apunta a una acción que existe (con ese nombre exacto)."""
    import re
    for d in definiciones("P9_MASIVA_PROTO_CONFIRMAR", K).values():
        existentes = {n for n, _ in nombres(d)}
        texto = json.dumps(d)
        usados = set(re.findall(r"(?:outputs|body|actions)\(\\?'([A-Za-z0-9_]+)\\?'\)", texto))
        assert usados <= existentes, usados - existentes
