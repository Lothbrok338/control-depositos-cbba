"""Genera reports/INFORME_PRUEBAS.md a partir de reports/resultados.json (salida de pytest)."""
import json
import re
from pathlib import Path
from helpers import FIXTURES, RAIZ

res = json.loads((RAIZ / "reports" / "resultados.json").read_text(encoding="utf-8"))

CAMBIOS = {  # codigo -> (archivo/funcion, cambio minimo necesario)
 "D-01": ("motor · numero()", "Tratar 'N,NNN' (grupos de 3 tras la coma, sin punto) como miles; conservar '1234,5' como decimal."),
 "D-02": ("motor · numero()", "Aceptar negativo entre parentesis y signo '-' final."),
 "D-03": ("motor · numero()", "Separador repetido (1.234.567 / 1,234,567) = miles."),
 "D-04": ("motor · normalizar_fecha()", "Si el texto es ISO (AAAA-MM-DD) parsear sin dayfirst; dayfirst solo para dd/mm/aaaa."),
 "D-05": ("motor · normalizar_hora()", "Convertir float 0<=x<1 (fraccion de dia de Excel) a HH:MM:SS."),
 "D-06": ("motor · normalizar_bnb/bcp/union/bisa/bmsc", "Usar el mismo parser (normalizar_fecha) para FILTRAR filas y para el valor final, como ya hace normalizar_economico."),
 "D-07": ("motor · normalizar_*", "Contar filas descartadas por fecha; si alguna tiene importe/saldo, lanzar ValueError (pies de pagina 'Total ...' siguen permitidos)."),
 "D-08": ("motor · ejecutar_motor (paso 6)", "Reemplazar 2026 fijo por año parametrizable (p. ej. derivado de FECHA A PROCESAR) sin bloquear enero 2027."),
 "D-09": ("motor · encontrar_fila_encabezado / leer_tabla_movimientos", "Exigir puntaje minimo (p. ej. 100% o umbral fijo) y lanzar ValueError con el formato y las filas inspeccionadas."),
 "D-10": ("motor · detectar_formato", "Buscar la cuenta solo en la zona de cabecera (filas previas al encabezado) y exigir UNA sola cuenta conocida."),
 "D-11": ("motor · detectar_formato (rama BMSC)", "Verificar 1000872489 en cabecera (aparece en fila 7 col F del extracto real) o devolver NO_RECONOCIDO."),
 "D-12": ("motor · normalizar_union/bcp/bisa/economico/bnb", "Reemplazar los 'else' implicitos por un diccionario CUENTAS[formato] que falle si el formato no esta registrado."),
 "D-13": ("motor · ejecutar_motor (inicio y paso 10-11)", "Eliminar/mover salidas previas al iniciar y escribir a temporal + renombrar al terminar."),
 "D-14": ("motor · bloque __main__ / ejecutar_motor", "sys.stdout.reconfigure(encoding='utf-8') (o quitar emojis) antes del primer print."),
 "D-15": ("motor · ejecutar_motor (CONFIGURAR LOTE)", "Usar hora de America/La_Paz en fecha_carga y lote."),
 "D-16b": ("motor · leer_tabla_movimientos / normalizar_union", "Un UNION_ME sin movimientos debe devolver 0 filas y estado SIN MOVIMIENTOS (mismo cambio que D-16); confirmar con el archivo real vacío."),
 "D-16": ("motor · leer_tabla_movimientos / normalizar_*", "Si el encabezado existe pero no hay filas, devolver DataFrame vacio con COLUMNAS_LISTS y estado SIN MOVIMIENTOS (patron ya usado por BISA)."),
 "D-17": ("motor · leer_tabla_movimientos", "No eliminar columnas vacias ANTES de buscar las requeridas (o tratarlas como presentes y vacias)."),
}
NOMBRES_GRUPO = {
 "test_deteccion_formato": "Detección", "test_hoja_y_encabezado_reales": "Hoja+encab.",
 "test_contrato_banco_cuenta_moneda": "Banco/cuenta/moneda", "test_igual_a_referencia_dorada": "= Dorada",
 "test_conteo_movimientos_oraculo_independiente": "Conteo (oráculo)", "test_saldo_encadenado_fila_a_fila": "Cadena saldos",
 "test_validacion_de_saldos_ok": "Validación saldos", "test_integridad_estructural": "Integridad",
 "test_clave_consistente_con_columnas": "Clave", "test_cuenta_real_aparece_en_cabecera_y_es_unica": "Cuenta en cabecera",
}
ORDEN = list(NOMBRES_GRUPO)
matriz = {fm: {} for fm in FIXTURES}
for r in res:
    m = re.match(r".*::(test_\w+)\[(\w+)\]$", r["id"])
    if m and m.group(1) in NOMBRES_GRUPO and m.group(2) in matriz:
        matriz[m.group(2)][m.group(1)] = r
def celda(r):
    if r is None: return "—"
    return {"PASS": "PASS", "FAIL": "**FAIL**", "SKIP": "SKIP", "XFAIL": "XFAIL", "XPASS": "XPASS"}[r["estado"]]
L = ["# Informe de pruebas del normalizador (Fase 2 + P1/P2: captura y preservación de origen)\n"]
tot = {}
for r in res: tot[r["estado"]] = tot.get(r["estado"], 0) + 1
L.append("Resumen: " + ", ".join(f"{k}={v}" for k, v in sorted(tot.items())) + "\n")
L.append("## 1. Regresión por banco/formato (extractos reales)\n")
L.append("| Formato | Archivo | " + " | ".join(NOMBRES_GRUPO[g] for g in ORDEN) + " | Resultado |")
L.append("|---|---|" + "---|" * (len(ORDEN) + 1))
for fm, fila in matriz.items():
    est = [fila.get(g) for g in ORDEN]
    ok = all(e is None or e["estado"] in ("PASS", "SKIP") for e in est)
    L.append(f"| {fm} | {FIXTURES[fm]} | " + " | ".join(celda(e) for e in est) + f" | {'**PASS**' if ok else '**FAIL**'} |")
L.append("| UNION_ME (`UNION_FECHAS_V1`) | *sin extracto real en el repo* | PASS (proxy sintético) | PENDIENTE archivo real | — | — | — | — | — | — | — | — | **ESTRUCTURA: CONFIRMADA (código legado + captura real) · ARCHIVO REAL VACÍO: pendiente · MOVIMIENTOS: REQUIERE MUESTRA REAL CON MOVIMIENTOS** |")
L.append("\n**Estructura UNION_ME = confirmada por código legado (`HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `detectar_formato`, `normalizar_union`) + captura real; comportamiento con movimientos = pendiente de fixture real.** UNION_ME es un formato válido (`UNION_FECHAS_V1`, hoja `ExtractoMovimientosFechas`, cuenta 20000003224544, columnas "
         "`Fecha Movimiento | AG | Descripción | Nro Documento | Monto | Saldo | Nro de verificasion`). `Nro de verificasion` proviene de la captura real; el motor legado no la lee (se pierde) y no entra a las 26 columnas. La muestra real está vacía y "
         "aún no está en el repositorio (`fixtures/extractos/union_me_vacio.xls`): sus pruebas estructurales se activan al colocarla. "
         "El reporte «Últimos 12 Movimientos» quedó como fixture **negativo** (`fixtures/negativos/`).\n")
L.append("## 2. Contrato, lote completo y UNION_ME (estructura)\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
grp = {}
for r in res:
    base = r["id"].split("[")[0]
    fn = base.split("/")[-1]
    n = fn.split("::")[-1]
    if fn.startswith(("test_01", "test_03")) or "union" in n or "bisa_me_sin" in n or "totales_pie" in n:
        grp.setdefault(fn, []).append(r["estado"])
for fn, est in grp.items():
    resumen = "PASS" if all(e == "PASS" for e in est) else ("XFAIL" if all(e == "XFAIL" for e in est) else "/".join(sorted(set(est))))
    L.append(f"| `{fn}` | {len(est)} | {resumen} |")
L.append("\n## 2b. Preservación de origen (P2, `test_05_preservacion.py`)\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
g5 = {}
for r in res:
    fn = r["id"].split("/")[-1]
    if fn.startswith("test_05"):
        g5.setdefault(fn.split("[")[0].split("::")[-1], []).append(r["estado"])
for n, est in g5.items():
    L.append(f"| `{n}` | {len(est)} | " + ("PASS" if all(e == "PASS" for e in est) else "/".join(f"{e}×{est.count(e)}" for e in sorted(set(est)))) + " |")
L.append("\n## 3. Defectos reales confirmados (fallan hoy; deben pasar tras corregir)\n")
L.append("| Código | Estado hoy | Defecto demostrado | Cambio necesario (archivo · función) |\n|---|---|---|---|")
for r in res:
    if r["id"].split("/")[-1].startswith("test_04"):
        m = re.match(r"(D-\d+b?)\s+([A-ZÑÁÉÍÓÚ ]+):\s*(.*)", r["motivo"])
        cod, area, txt = (m.group(1), m.group(2), m.group(3)) if m else ("?", "", r["motivo"])
        donde, cambio = CAMBIOS.get(cod, ("", ""))
        estado = {"XFAIL": "FALLA (defecto vigente)", "XPASS": "YA CORREGIDO", "PASS": "PASS"}.get(r["estado"], r["estado"])
        L.append(f"| {cod} {area.title()} | {estado} | {txt} | `{donde}` — {cambio} |")
(RAIZ / "reports" / "INFORME_PRUEBAS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
