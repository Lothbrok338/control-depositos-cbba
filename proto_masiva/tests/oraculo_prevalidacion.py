"""ORÁCULO independiente de la prevalidación real: las mismas reglas, escritas en Python puro (Decimal, regex, diccionarios).

NO comparte código con `flows/prevalidacion.py` (que las expresa en WDL con split/replace/Select): sirve para cruzar resultados
fila a fila en escenarios aleatorios y detectar cualquier divergencia entre la regla escrita y la expresión generada.

Reglas (PREVALIDACION_REAL.md):
  universo  = TIPO_MOVIMIENTO == "CRÉDITO" y  hoy-2 meses <= FECHA_MOVIMIENTO <= hoy   (misma ventana que galDepositosP9_1)
  clave     = BANCO + CUENTA_BANCARIA + CODIGO_ASIGNACION + IMPORTE   (texto con trim, en minúsculas; IMPORTE como centavos enteros)
  orden     = FILA_INCOMPLETA > IMPORTE_INVALIDO > MONEDA_INVALIDA > DUPLICADO_ARCHIVO > NO_ENCONTRADO > ASIGNACION_AMBIGUA
              > MONEDA_NO_COINCIDE > NO_DISPONIBLE > VALIDO
"""
from __future__ import annotations

import calendar
import re
from collections import Counter
from datetime import date
from decimal import Decimal

OBLIGATORIAS = ("BANCO", "CUENTA_BANCARIA", "CODIGO_ASIGNACION", "IMPORTE", "MONEDA", "ESTUDIANTE", "SOLICITADO_POR", "SEDE")
ENCABEZADOS = OBLIGATORIAS[:5] + ("ESTUDIANTE", "SOLICITADO_POR", "SEDE", "OBSERVACION")


def texto(valor):
    """Como el flujo: sin valor = vacío; los números llegan como su representación en texto (JSON)."""
    if valor is None:
        return ""
    return str(valor).strip()


def centavos(importe_txt):
    """None si el texto no es un importe válido: dígitos con punto decimal opcional y 1-2 decimales, ≤ 15 caracteres, > 0."""
    if not re.fullmatch(r"\d+(\.\d{1,2})?", importe_txt) or len(importe_txt) > 15:
        return None
    c = int(Decimal(importe_txt) * 100)
    return c if c > 0 else None


def hace_dos_meses(hoy: date) -> date:
    mes0 = hoy.year * 12 + hoy.month - 1 - 2
    año, mes = divmod(mes0, 12)
    return date(año, mes + 1, min(hoy.day, calendar.monthrange(año, mes + 1)[1]))


def prevalidar(filas, depositos, hoy: date, fila_encabezado=5):
    """filas: lista de dicts por ENCABEZADO (None = fila totalmente en blanco, que se ignora pero cuenta para la posición)."""
    desde = hace_dos_meses(hoy)
    universo = [d for d in depositos if d["TIPO_MOVIMIENTO"] == "CRÉDITO" and desde <= date.fromisoformat(d["FECHA_MOVIMIENTO"][:10]) <= hoy]
    por_clave = {}
    for d in universo:
        c = centavos(texto(d["IMPORTE"]))
        if c is None:
            continue
        k = (str(d["BANCO"]).strip().lower(), str(d["CUENTA_BANCARIA"]).strip().lower(),
             str(d["CODIGO_ASIGNACION"]).strip().lower(), c)
        por_clave.setdefault(k, []).append(d)

    normalizadas = []
    for pos, f in enumerate(filas, 1):
        t = {h: texto((f or {}).get(h)) for h in ENCABEZADOS}
        t["MONEDA"] = t["MONEDA"].upper()
        if all(v == "" for v in t.values()):
            continue
        c = centavos(t["IMPORTE"])
        clave = None
        if t["BANCO"] and t["CUENTA_BANCARIA"] and t["CODIGO_ASIGNACION"] and c is not None:
            clave = (t["BANCO"].lower(), t["CUENTA_BANCARIA"].lower(), t["CODIGO_ASIGNACION"].lower(), c)
        normalizadas.append((pos, t, c, clave))
    repetidas = Counter(k for _, _, _, k in normalizadas if k)

    salida = []
    for pos, t, c, clave in normalizadas:
        encontrados = por_clave.get(clave, []) if clave else []
        dep = encontrados[0] if len(encontrados) == 1 else None
        if any(t[h] == "" for h in OBLIGATORIAS):
            r = "FILA_INCOMPLETA"
        elif c is None:
            r = "IMPORTE_INVALIDO"
        elif t["MONEDA"] not in ("BOB", "USD"):
            r = "MONEDA_INVALIDA"
        elif repetidas[clave] > 1:
            r = "DUPLICADO_ARCHIVO"
        elif not encontrados:
            r = "NO_ENCONTRADO"
        elif len(encontrados) > 1:
            r = "ASIGNACION_AMBIGUA"
        elif str(dep["MONEDA"]).strip().upper() != t["MONEDA"]:
            r = "MONEDA_NO_COINCIDE"
        elif str(dep["ESTADO_ASIGNACION"]).strip() != "DISPONIBLE":
            r = "NO_DISPONIBLE"
        else:
            r = "VALIDO"
        conoce = r in ("VALIDO", "MONEDA_NO_COINCIDE", "NO_DISPONIBLE")
        salida.append({"fila_tabla": pos, "fila_excel": pos + fila_encabezado, "resultado": r, "coincidencias": len(encontrados),
                       "deposito_id": dep["Id"] if conoce else None,
                       "estado_actual": str(dep["ESTADO_ASIGNACION"]).strip() if conoce else ""})
    return salida
