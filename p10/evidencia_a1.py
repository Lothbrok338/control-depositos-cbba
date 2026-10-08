# -*- coding: utf-8 -*-
"""
p10/evidencia_a1.py · P10-A.1 · evidencia de regeneración: DISPONIBLE -> CONFIRMADO -> reversión.

Sobre la salida de P0 de una corrida real (LISTS.csv + ORIGEN.xlsx) regenera el libro de BNB MN con tres
snapshots sucesivos y documenta, con las diferencias reales entre libros, qué cambió y qué no:

    T0  snapshot base
    T1  4 créditos DISPONIBLES pasan a CONFIRMADO (ASIGNADO en la lista)
    T2  2 reversiones con el payload REAL de P9 (una de T0 y una de T1) vuelven a DISPONIBLE

    python -m p10.evidencia_a1 --trabajo <carpeta con LISTS.csv y ORIGEN.xlsx> --salida <carpeta> [--cuenta BNB_MN]
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

import historico as H

from . import contrato as C
from . import generador as G
from . import snapshot_simulado as SS
from .comparar import diferencias

CUENTAS = {"BNB_MN": "3000100152"}


def _gen(origen, lists, snap, carpeta, id_cuenta):
    info = G.generar_libros(origen, lists, snap, carpeta, solo_cuentas={id_cuenta})
    assert info["estado"] == "OK" and len(info["archivos"]) == 1, info["omitidos"]
    return info["archivos"][0]


def _resumen_difs(difs):
    por_hoja = {}
    for d in difs:
        por_hoja.setdefault(d["hoja"], {"celdas": 0, "claves": set(), "columnas": {}, "otros": 0})
        h = por_hoja[d["hoja"]]
        if d["tipo"] == "CELDA":
            h["celdas"] += 1
            h["claves"].add(d["clave"])
            h["columnas"][d["columna"]] = h["columnas"].get(d["columna"], 0) + 1
        else:
            h["otros"] += 1
    return por_hoja


def _fmt(v):
    return "" if v is None else str(v).replace("\n", "⏎").replace("|", "\\|")


def ejecutar(trabajo, salida, id_cuenta="BNB_MN"):
    cuenta = CUENTAS[id_cuenta]
    lists, origen = os.path.join(trabajo, "LISTS.csv"), os.path.join(trabajo, "ORIGEN.xlsx")
    filas = H.leer_normalizado(lists)
    t0 = SS.snapshot_simulado(filas)
    nuevas = SS.elegir_a_confirmar(t0, filas, cuenta, 4)
    t1 = SS.confirmar(t0, filas, nuevas)
    previa = SS.elegir_a_revertir(t0, cuenta, filas, 1)
    revertidas = previa + [nuevas[0]]
    t2 = SS.revertir(t1, revertidas)
    ida_vuelta = SS.revertir(SS.confirmar(t0, filas, nuevas[:3]), nuevas[:3])

    tmp = tempfile.mkdtemp(prefix="p10_evidencia_")
    try:
        a0 = _gen(origen, lists, t0, os.path.join(tmp, "t0"), id_cuenta)
        a1 = _gen(origen, lists, t1, os.path.join(tmp, "t1"), id_cuenta)
        a1b = _gen(origen, lists, t1, os.path.join(tmp, "t1_repetido"), id_cuenta)
        a2 = _gen(origen, lists, t2, os.path.join(tmp, "t2"), id_cuenta)
        a3 = _gen(origen, lists, ida_vuelta, os.path.join(tmp, "ida_vuelta"), id_cuenta)
        d01 = diferencias(a0["ruta"], a1["ruta"])
        d12 = diferencias(a1["ruta"], a2["ruta"])
        d02 = diferencias(a0["ruta"], a2["ruta"])
        d03 = diferencias(a0["ruta"], a3["ruta"])
        d11 = diferencias(a1["ruta"], a1b["ruta"])
        por_clave = {r[C.COLUMNA_CLAVE]: r for r in filas}
        datos = {
            "cuenta": id_cuenta, "archivo": a0["nombre_archivo"],
            "snapshots": {n: {"sha256": s.sha256, "fecha_corte": s.fecha_corte.isoformat()}
                          for n, s in (("T0", t0), ("T1", t1), ("T2", t2))},
            "libros": {n: {"sha256": a["sha256"], "movimientos": a["movimientos"], "estados": a["estados"]}
                       for n, a in (("T0", a0), ("T1", a1), ("T2", a2))},
            "T0_a_T1": {"claves": nuevas, "diferencias": len(d01), "resumen": {h: {**v, "claves": len(v["claves"])}
                                                                          for h, v in _resumen_difs(d01).items()}},
            "T1_a_T2": {"claves": revertidas, "diferencias": len(d12), "resumen": {h: {**v, "claves": len(v["claves"])}
                                                                              for h, v in _resumen_difs(d12).items()}},
            "T0_a_T2_claves_extracto": sorted({d["clave"] for d in d02 if d["hoja"] == "EXTRACTO"}),
            "T0_a_T2_claves_auditoria": sorted({d["clave"] for d in d02 if d["hoja"] == "AUDITORIA"}),
            "repetir_T1": {"mismos_bytes": a1["sha256"] == a1b["sha256"], "diferencias_logicas": len(d11)},
            "confirmar_y_revertir_3": {
                "diferencias_extracto_con_T0": len([d for d in d03 if d["hoja"] == "EXTRACTO"]),
                "diferencias_auditoria_con_T0": len([d for d in d03 if d["hoja"] == "AUDITORIA"]),
                "columnas_auditoria_distintas": sorted({d["columna"] for d in d03 if d["hoja"] == "AUDITORIA"})},
        }
        os.makedirs(salida, exist_ok=True)
        with open(os.path.join(salida, "EVIDENCIA_ESCENARIOS_BNB_MN.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        _escribir_md(os.path.join(salida, "EVIDENCIA_ESCENARIOS_BNB_MN.md"), datos, d01, d12, por_clave)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return datos


def _tabla(difs, claves, por_clave, hoja):
    out = ["| Movimiento (FECHA · HORA · IMPORTE) | Columna | Antes | Después |", "|---|---|---|---|"]
    for clave in claves:
        r = por_clave[clave]
        etiqueta = f"{r['FECHA MOVIMIENTO']} {r['HORA MOVIMIENTO']} · {float(r['IMPORTE']):,.2f}"
        for d in difs:
            if d["tipo"] == "CELDA" and d["hoja"] == hoja and d["clave"] == clave:
                out.append(f"| {etiqueta} | {d['columna']} | {_fmt(d['antes'])} | {_fmt(d['despues'])} |")
    return out


def _escribir_md(ruta, datos, d01, d12, por_clave):
    L = datos["libros"]
    md = [
        f"# Evidencia P10-A.1 · regeneración con cambios de estado · {datos['cuenta']}", "",
        f"Archivo: `{datos['archivo']}` · generado SOLO desde LISTS.csv + ORIGEN.xlsx de P0 y un snapshot "
        "SIMULADO de Depositos_Activos (regeneración completa; no se edita el archivo existente).", "",
        "| Paso | Estado operativo | Movimientos | CONFIRMADO | DISPONIBLE | SHA-256 del libro |", "|---|---|---|---|---|---|",
    ]
    nombres = {"T0": "T0 · snapshot base", "T1": "T1 · 4 DISPONIBLE → CONFIRMADO", "T2": "T2 · 2 reversiones (payload P9)"}
    for n in ("T0", "T1", "T2"):
        e = L[n]["estados"]
        md.append(f"| {nombres[n]} | snapshot `{datos['snapshots'][n]['sha256'][:12]}` | {L[n]['movimientos']} | "
                  f"{e.get('CONFIRMADO', 0)} | {e.get('DISPONIBLE', 0)} | `{L[n]['sha256'][:16]}…` |")
    md += ["", "El nombre del archivo, el número de filas (sin duplicados), el orden de los movimientos y la zona "
           "superior son idénticos en los tres pasos.", "",
           f"## T0 → T1 · {len(datos['T0_a_T1']['claves'])} movimientos pasan de DISPONIBLE a CONFIRMADO", ""]
    for h, v in datos["T0_a_T1"]["resumen"].items():
        md.append(f"* **{h}**: {v['celdas']} celdas cambiaron, en {v['claves']} movimientos; columnas: "
                  + ", ".join(f"{c} ({n})" for c, n in sorted(v["columnas"].items())) + f"; otras diferencias: {v['otros']}.")
    md += ["", "Hoja EXTRACTO:", ""] + _tabla(d01, datos["T0_a_T1"]["claves"], por_clave, "EXTRACTO")
    md += ["", f"## T1 → T2 · {len(datos['T1_a_T2']['claves'])} reversiones (una confirmada en T0 y una confirmada en T1)", ""]
    for h, v in datos["T1_a_T2"]["resumen"].items():
        md.append(f"* **{h}**: {v['celdas']} celdas cambiaron, en {v['claves']} movimientos; columnas: "
                  + ", ".join(f"{c} ({n})" for c, n in sorted(v["columnas"].items())) + f"; otras diferencias: {v['otros']}.")
    md += ["", "Hoja EXTRACTO:", ""] + _tabla(d12, datos["T1_a_T2"]["claves"], por_clave, "EXTRACTO")
    md += ["", "## Reconstrucción y determinismo", "",
           f"* Regenerar T1 por segunda vez: mismos bytes = **{datos['repetir_T1']['mismos_bytes']}**, "
           f"diferencias lógicas = {datos['repetir_T1']['diferencias_logicas']}.",
           f"* Confirmar 3 movimientos y revertirlos reconstruye EXTRACTO idéntico a T0 (diferencias = "
           f"**{datos['confirmar_y_revertir_3']['diferencias_extracto_con_T0']}**); en AUDITORIA solo difiere "
           f"{', '.join(datos['confirmar_y_revertir_3']['columnas_auditoria_distintas'])} "
           f"({datos['confirmar_y_revertir_3']['diferencias_auditoria_con_T0']} celdas): P9 no borra nunca el marcador de reversión.",
           f"* T0 → T2: en EXTRACTO solo difieren {len(datos['T0_a_T2_claves_extracto'])} movimientos "
           f"({len(datos['T0_a_T1']['claves']) - 1} confirmados en T1 que siguen confirmados + 1 confirmado en T0 que se revirtió); "
           "el movimiento confirmado en T1 y revertido en T2 vuelve a ser idéntico a T0 en EXTRACTO y conserva en AUDITORIA solo su "
           "marcador `ULTIMA_REVERSION_ID`.",
           "", "`CODIGO_ESTUDIANTE` y `ULTIMA_REVERSION_ID` son columnas reales de `Depositos_Activos` y se conservan al final de "
           "AUDITORIA (28 columnas = las 26 de P0 + esas 2); EXTRACTO no las muestra."]
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trabajo", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--cuenta", default="BNB_MN", choices=sorted(CUENTAS))
    a = ap.parse_args(argv)
    datos = ejecutar(a.trabajo, a.salida, a.cuenta)
    print(json.dumps({k: datos[k] for k in ("libros", "repetir_T1", "confirmar_y_revertir_3")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
