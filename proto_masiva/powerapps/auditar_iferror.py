"""Auditoría de compatibilidad de tipos en `IfError(...)` de las fórmulas del YAML (sintaxis canónica: `,` argumentos, `;` sentencias).

Por qué existe: Power Apps Studio rechazó en el tenant `IfError(ClearCollect(...); Notify(...))` por tipos incompatibles (una rama devuelve una TABLA y
la otra un booleano). La corrección aceptada por Studio hace que **todas** las ramas de **cada** `IfError` terminen en un literal booleano:

    IfError(ClearCollect(...);; true,  Notify(...);; false)

Regla que se comprueba: en cada `IfError` con al menos dos argumentos, la ÚLTIMA sentencia de CADA argumento es `true` o `false`.

    python proto_masiva/powerapps/auditar_iferror.py [archivo.pa.yaml]     (sale con código 1 si hay incompatibilidades)

Segunda comprobación (mismo CLI): `ShowColumns` con los nombres de columna SIN comillas. Power Apps Studio del tenant rechazó
`ShowColumns(tabla; "fila_excel"; …)` y aceptó `ShowColumns(tabla; fila_excel; …)`: ninguna fórmula de la pantalla debe volver a generar
nombres de columna entre comillas en un `ShowColumns`.
"""
import sys
from pathlib import Path

import yaml

CARPETA = Path(__file__).resolve().parent
ABRE, CIERRA = "([{", ")]}"


def _sin_texto_mascara(formula: str) -> str:
    """Misma longitud que la fórmula, con el contenido de los textos entre comillas reemplazado por espacios (respeta `\"\"` escapado)."""
    salida, en_texto, i = [], False, 0
    while i < len(formula):
        c = formula[i]
        if c == '"':
            if en_texto and formula[i + 1:i + 2] == '"':
                salida.append("  ")
                i += 2
                continue
            en_texto = not en_texto
            salida.append('"')
        else:
            salida.append(" " if en_texto else c)
        i += 1
    return "".join(salida)


def _separar(texto: str, mascara: str, separador: str) -> list:
    """Parte `texto` por `separador` solo en el nivel 0 de paréntesis/llaves/corchetes."""
    partes, nivel, inicio = [], 0, 0
    for i, c in enumerate(mascara):
        if c in ABRE:
            nivel += 1
        elif c in CIERRA:
            nivel -= 1
        elif c == separador and nivel == 0:
            partes.append(texto[inicio:i])
            inicio = i + 1
    partes.append(texto[inicio:])
    return partes


def llamadas_iferror(formula: str) -> list:
    """Lista de `[argumento, ...]` (texto) de cada `IfError(...)`, anidados incluidos."""
    mascara = _sin_texto_mascara(formula)
    llamadas, desde = [], 0
    while True:
        i = mascara.find("IfError(", desde)
        if i < 0:
            return llamadas
        if i > 0 and (mascara[i - 1].isalnum() or mascara[i - 1] == "_"):
            desde = i + 1
            continue
        ini, nivel, j = i + len("IfError("), 1, i + len("IfError(")
        while nivel and j < len(mascara):
            nivel += mascara[j] in ABRE
            nivel -= mascara[j] in CIERRA
            j += 1
        cuerpo, cuerpo_m = formula[ini:j - 1], mascara[ini:j - 1]
        llamadas.append(_separar(cuerpo, cuerpo_m, ","))
        desde = ini


def ultima_sentencia(argumento: str) -> str:
    sentencias = [s.strip() for s in _separar(argumento, _sin_texto_mascara(argumento), ";")]
    return next((s for s in reversed(sentencias) if s), "")


def incompatibilidades(formula: str) -> list:
    """Cada hallazgo: (índice de IfError, índice de argumento, última sentencia). Vacío = todas las ramas son booleanas literales."""
    hallazgos = []
    for n, args in enumerate(llamadas_iferror(formula)):
        if len(args) < 2:
            continue
        for k, arg in enumerate(args):
            ultima = ultima_sentencia(arg)
            if ultima not in ("true", "false"):
                hallazgos.append((n, k, ultima[:80]))
    return hallazgos


def showcolumns_con_comillas(formula: str, sep: str = ",") -> list:
    """Nombres de columna escritos entre comillas en algún `ShowColumns(tabla, col1, col2, …)` de la fórmula (vacío = todos sin comillas)."""
    mascara, malos, desde = _sin_texto_mascara(formula), [], 0
    while True:
        i = mascara.find("ShowColumns(", desde)
        if i < 0:
            return malos
        if i > 0 and (mascara[i - 1].isalnum() or mascara[i - 1] == "_"):
            desde = i + 1
            continue
        ini, nivel, j = i + len("ShowColumns("), 1, i + len("ShowColumns(")
        while nivel and j < len(mascara):
            nivel += mascara[j] in ABRE
            nivel -= mascara[j] in CIERRA
            j += 1
        args = _separar(formula[ini:j - 1], mascara[ini:j - 1], sep)
        malos += [a.strip() for a in args[1:] if a.strip().startswith('"')]
        desde = ini


def formulas_del_yaml(ruta: Path):
    doc = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    for nombre_pantalla, pantalla in doc["Screens"].items():
        for prop, valor in (pantalla.get("Properties") or {}).items():
            yield f"{nombre_pantalla}.{prop}", str(valor)

        def recorrer(hijos):
            for h in hijos:
                (nombre, c), = h.items()
                for prop, valor in (c.get("Properties") or {}).items():
                    yield f"{nombre}.{prop}", str(valor)
                yield from recorrer(c.get("Children") or [])
        yield from recorrer(pantalla.get("Children") or [])


def auditar(ruta: Path) -> list:
    """[(donde, hallazgos)] solo de las fórmulas con IfError incompatible."""
    return [(donde, h) for donde, f in formulas_del_yaml(ruta) if (h := incompatibilidades(f))]


if __name__ == "__main__":
    archivo = Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA / "P9_Confirmacion_Masiva.pa.yaml"
    total = sum(len(llamadas_iferror(f)) for _, f in formulas_del_yaml(archivo))
    malos = auditar(archivo)
    print(f"{archivo.name}: {total} IfError auditados, {len(malos)} fórmula(s) con ramas no booleanas")
    for donde, hallazgos in malos:
        for n, k, ultima in hallazgos:
            print(f"  ✗ {donde}: IfError #{n} argumento {k} termina en «{ultima}»")
    con_comillas = [(donde, c) for donde, f in formulas_del_yaml(archivo) if (c := showcolumns_con_comillas(f))]
    print(f"{archivo.name}: {sum(f.count('ShowColumns(') for _, f in formulas_del_yaml(archivo))} ShowColumns auditados, {len(con_comillas)} fórmula(s) con columnas entre comillas")
    for donde, cols in con_comillas:
        print(f"  ✗ {donde}: {', '.join(cols)}")
    sys.exit(1 if (malos or con_comillas) else 0)
