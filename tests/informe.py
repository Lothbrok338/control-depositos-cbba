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
 "D-06": ("motor_generico.py · filtro_fecha del registro (P5; antes normalizar_*)", "Usar el mismo parser (normalizar_fecha) para FILTRAR filas y para el valor final, como ya hace normalizar_economico."),
 "D-07": ("motor_generico.py · MotorGenerico.normalizar (P5; antes normalizar_*)", "Contar filas descartadas por fecha; si alguna tiene importe/saldo, lanzar ValueError (pies de pagina 'Total ...' siguen permitidos)."),
 "D-08": ("motor · ejecutar_motor (paso 6)", "CORREGIDO EN P0: el control del año acepta [ANIO_MINIMO_DATOS, año de la fecha del equipo] (anios_fuera_de_rango) en vez del 2026 fijo."),
 "D-09": ("motor_generico.py · MotorGenerico._leer_tabla (P5)", "CORREGIDO EN P5: la normalizacion productiva exige encabezados.puntaje_minimo del registro y lanza ValueError con los encabezados que faltan (la deteccion ya lo exigia desde P4). La primitiva legada encontrar_fila_encabezado se retiro en P6."),
 "D-10": ("deteccion_registro.py (P4)", "CORREGIDO EN P4: la cuenta se lee solo en la celda rotulada de la cabecera (filas previas al encabezado) y debe ser UNA cuenta registrada."),
 "D-11": ("deteccion_registro.py (P4)", "CORREGIDO EN P4: BMSC exige la cuenta 1000872489 registrada en la cabecera; otra cuenta = CUENTA_NO_REGISTRADA."),
 "D-12": ("motor_generico.py · MotorGenerico.normalizar (P5)", "CORREGIDO EN P5: BANCO / CUENTA BANCARIA / MONEDA salen de la entrada de CUENTAS del registro; la normalizacion productiva no tiene ramas por cuenta. Los normalizar_* legados (y sus 'else') se retiraron en P6."),
 "D-13": ("motor · ejecutar_motor (inicio y paso 10-11)", "Eliminar/mover salidas previas al iniciar y escribir a temporal + renombrar al terminar."),
 "D-14": ("motor · bloque __main__ / ejecutar_motor", "sys.stdout.reconfigure(encoding='utf-8') (o quitar emojis) antes del primer print."),
 "D-15": ("motor · ejecutar_motor (CONFIGURAR LOTE)", "Usar hora de America/La_Paz en fecha_carga y lote."),
 "D-16b": ("motor_generico.py · MotorGenerico._leer_tabla / normalizar (P5)", "Un UNION_ME sin movimientos debe devolver 0 filas y estado SIN MOVIMIENTOS (mismo cambio que D-16); confirmar con el archivo real vacío."),
 "D-16": ("motor_generico.py · MotorGenerico._leer_tabla / normalizar (P5)", "Si el encabezado existe pero no hay filas, devolver DataFrame vacio con COLUMNAS_LISTS y estado SIN MOVIMIENTOS (patron ya usado por BISA)."),
 "D-17": ("motor_generico.py · MotorGenerico._leer_tabla (P5)", "No eliminar columnas vacias ANTES de buscar las requeridas (o tratarlas como presentes y vacias)."),
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
L = ["# Informe de pruebas del normalizador (Fase 2 + P1/P2: captura y preservación de origen + P3: motor genérico en sombra + P3b: EXTRACTO_HISTORICO + P4: detección por registro + P5: normalización por registro + P6: retiro del legado)\n"]
CORREGIDOS_P4 = {"test_cuenta_dentro_de_glosa_no_cambia_la_deteccion": ("D-10", "Cuenta", "un BNB_CLINICA cuya glosa menciona la cuenta BNB_MN ya NO se clasifica como BNB_MN"),
                 "test_bmsc_con_otra_cuenta_no_se_acepta": ("D-11", "Cuenta", "un BMSC con otra cuenta ya NO se acepta con la cuenta fija 1000872489")}
CORREGIDOS_P5 = {"test_encabezado_sin_coincidencias_debe_fallar": ("D-09", "Encabezado", "sin encabezado reconocible la normalizacion productiva lanza ValueError (antes leia desde una fila cualquiera)"),
                 "test_encabezado_parcial_tambien_falla_y_dice_que_falta": ("D-09", "Encabezado", "encabezado parcial (3/7) = ValueError con los encabezados que faltan"),
                 "test_formato_union_nuevo_no_hereda_cuenta_ajena": ("D-12", "Cuenta Nueva", "una cuenta UNION nueva recibe su cuenta y moneda del registro, nunca las de UNION_ME")}
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
L.append("\n**Desde P5 la matriz corre sobre la RUTA PRODUCTIVA (detección por registro + motor genérico).** UNION_ME se normaliza con `UNION_FECHAS_V1` (misma configuración que UNION_MN, identidad propia del registro): proxy sintético PASS; lo que depende de movimientos reales sigue SKIP.\n")
L.append("\n**Estructura UNION_ME = confirmada por código legado (`HOJAS_VALIDAS`, `ENCABEZADOS_ESPERADOS`, `detectar_formato`, `normalizar_union` del motor original; desde P6 solo en `registro_bancos.json`) + captura real; comportamiento con movimientos = pendiente de fixture real.** UNION_ME es un formato válido (`UNION_FECHAS_V1`, hoja `ExtractoMovimientosFechas`, cuenta 20000003224544, columnas "
         "`Fecha Movimiento | AG | Descripción | Nro Documento | Monto | Saldo | Nro de verificasion`). `Nro de verificasion` proviene de la captura real; no entra a las 26 columnas (va a ORIGEN.xlsx y al EXTRACTO_HISTORICO). La muestra real está vacía y "
         "aún no está en el repositorio (`fixtures/extractos/union_me_vacio.xls`): sus pruebas estructurales se activan al colocarla. "
         "El reporte «Últimos 12 Movimientos» quedó como fixture **negativo** (`fixtures/negativos/`).\n")
L.append("## 2. Contrato, lote completo y UNION_ME (estructura)\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
grp = {}
for r in res:
    base = r["id"].split("[")[0]
    fn = base.split("/")[-1]
    n = fn.split("::")[-1]
    if fn.startswith(("test_06", "test_07", "test_08", "test_09", "test_10")):
        continue
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
L.append("\n## 2c. Registro de bancos + motor genérico (P3-P6, `test_06_registro_generico.py`)\n")
L.append("Desde P6 el motor genérico es la única normalización; el comparador con el legado y la sombra se retiraron (antes `test_06_sombra_p3.py`).\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
g6 = {}
for r in res:
    fn = r["id"].split("/")[-1]
    if fn.startswith("test_06"):
        g6.setdefault(fn.split("[")[0].split("::")[-1], []).append(r["estado"])
for n, est in g6.items():
    L.append(f"| `{n}` | {len(est)} | " + ("PASS" if all(e == "PASS" for e in est) else "/".join(f"{e}×{est.count(e)}" for e in sorted(set(est)))) + " |")
L.append("\n## 2d. Capa 4 EXTRACTO_HISTORICO (P3b, `test_07_historico_p3b.py`)\n")
L.append("Un Excel por banco/cuenta/mes para Contabilidad/Ingresos, construido solo con ORIGEN.xlsx + NORMALIZADO + registro; el motor no cambia.\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
g7 = {}
for r in res:
    fn = r["id"].split("/")[-1]
    if fn.startswith("test_07"):
        g7.setdefault(fn.split("[")[0].split("::")[-1], []).append(r["estado"])
for n, est in g7.items():
    L.append(f"| `{n}` | {len(est)} | " + ("PASS" if all(e == "PASS" for e in est) else "/".join(f"{e}×{est.count(e)}" for e in sorted(set(est)))) + " |")
L.append("\n## 2e. Detección productiva por registro (P4, `test_08_deteccion_p4.py`)\n")
L.append("Banco, cuenta, moneda y formato salen de `registro_bancos.json` (`deteccion_registro.py`).\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
g8 = {}
for r in res:
    fn = r["id"].split("/")[-1]
    if fn.startswith("test_08"):
        g8.setdefault(fn.split("[")[0].split("::")[-1], []).append(r["estado"])
for n, est in g8.items():
    L.append(f"| `{n}` | {len(est)} | " + ("PASS" if all(e == "PASS" for e in est) else "/".join(f"{e}×{est.count(e)}" for e in sorted(set(est)))) + " |")
L.append("\n## 2f. Normalización productiva por registro (P5, `test_09_normalizacion_p5.py`)\n")
L.append("archivo → detección por registro → normalización genérica (`motor_generico.py` + `registro_bancos.json`) → salida productiva. Desde P6 la referencia legada es la congelada (doradas + manifest del motor original).\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
g9 = {}
for r in res:
    fn = r["id"].split("/")[-1]
    if fn.startswith("test_09"):
        g9.setdefault(fn.split("[")[0].split("::")[-1], []).append(r["estado"])
for n, est in g9.items():
    L.append(f"| `{n}` | {len(est)} | " + ("PASS" if all(e == "PASS" for e in est) else "/".join(f"{e}×{est.count(e)}" for e in sorted(set(est)))) + " |")
L.append("\n## 2g. Retiro del legado (P6, `test_10_retiro_legado_p6.py`)\n")
L.append("Ningún componente productivo define ni nombra la normalización legada; producción aislada con solo los 5 archivos productivos = doradas; sin sombra.\n")
L.append("| Prueba | Casos | Estado |\n|---|---|---|")
g10 = {}
for r in res:
    fn = r["id"].split("/")[-1]
    if fn.startswith("test_10"):
        g10.setdefault(fn.split("[")[0].split("::")[-1], []).append(r["estado"])
for n, est in g10.items():
    L.append(f"| `{n}` | {len(est)} | " + ("PASS" if all(e == "PASS" for e in est) else "/".join(f"{e}×{est.count(e)}" for e in sorted(set(est)))) + " |")
L.append("\n## 3. Defectos reales confirmados (fallan hoy; deben pasar tras corregir)\n")
L.append("| Código | Estado hoy | Defecto demostrado | Cambio necesario (archivo · función) |\n|---|---|---|---|")
for r in res:
    if r["id"].split("/")[-1].startswith("test_04"):
        m = re.match(r"(D-\d+b?)\s+([A-ZÑÁÉÍÓÚ ]+):\s*(.*)", r["motivo"])
        nombre = r["id"].split("::")[-1]
        corregidos = {**CORREGIDOS_P4, **CORREGIDOS_P5}
        if not m and nombre not in corregidos:
            continue
        cod, area, txt = (m.group(1), m.group(2), m.group(3)) if m else corregidos[nombre]
        donde, cambio = CAMBIOS.get(cod, ("", ""))
        fase = "P4" if nombre in CORREGIDOS_P4 else "P5"
        estado = {"XFAIL": "FALLA (defecto vigente)", "XPASS": "YA CORREGIDO",
                  "PASS": f"CORREGIDO EN {fase} (PASS)" if nombre in corregidos else "PASS"}.get(r["estado"], r["estado"])
        L.append(f"| {cod} {area.title()} | {estado} | {txt} | `{donde}` — {cambio} |")
(RAIZ / "reports" / "INFORME_PRUEBAS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
