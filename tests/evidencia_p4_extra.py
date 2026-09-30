"""Evidencia P4 complementaria a evidencia_ab.py (correr desde tests/):

    python evidencia_p4_extra.py <carpeta_referencia>

<carpeta_referencia> contiene motor_control_depositos_cbba.py, captura_origen.py, motor_generico.py y
registro_bancos.json de la referencia (p. ej. `git show 9a3eae8:<archivo>`). Compara ORIGEN.xlsx celda a celda,
la huella de los EXTRACTO_HISTORICO (P3b) generados desde cada corrida, y el texto fuente de los componentes
congelados del motor; informa si captura_origen.py / historico.py / motor_generico.py cambiaron (git diff).
"""
import ast, contextlib, importlib.util, io, subprocess, sys, tempfile, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.cwd()))
from evidencia_ab import correr, celdas
from helpers import huella_historico
REPO = Path.cwd().parent
ref = Path(sys.argv[1])

def hist(origen, lists, out):
    spec = importlib.util.spec_from_file_location("h_" + out.name, REPO / "historico.py")
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    return h.generar_extractos_historicos(str(origen), str(lists), str(out))

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    with contextlib.redirect_stdout(io.StringIO()):
        _, sa, _ = correr(ref / "motor_control_depositos_cbba.py", "ref", t)
        _, sb, _ = correr(REPO / "motor_control_depositos_cbba.py", "act", t)
    ca, cb = celdas(sa / "ORIGEN.xlsx"), celdas(sb / "ORIGEN.xlsx")
    print(("IDENTICO  " if ca == cb else "DIFERENTE ") + "ORIGEN.xlsx (4 hojas, valores+formatos)", {h: len(ca[h]["celdas"]) for h in ca})
    ha, hb = hist(sa / "ORIGEN.xlsx", sa / "LISTS.csv", t / "hist_ref"), hist(sb / "ORIGEN.xlsx", sb / "LISTS.csv", t / "hist_act")
    fa = {p.name: huella_historico(p) for p in sorted((t / "hist_ref").iterdir())}
    fb = {p.name: huella_historico(p) for p in sorted((t / "hist_act").iterdir())}
    print(("IDENTICO  " if fa == fb else "DIFERENTE ") + f"EXTRACTO_HISTORICO P3b ({len(fa)} archivos, huella completa)", ha["estado"], hb["estado"])

print("\nCOMPONENTES CONGELADOS (main 9a3eae8 vs. actual, texto fuente):")
def defs(src):
    arbol = ast.parse(src); out = {}
    for n in arbol.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out[n.name] = ast.get_source_segment(src, n)
        elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            out[n.targets[0].id] = ast.get_source_segment(src, n)
    return out
a = defs((ref / "motor_control_depositos_cbba.py").read_text(encoding="utf-8"))
b = defs((REPO / "motor_control_depositos_cbba.py").read_text(encoding="utf-8"))
congelados = ["COLUMNAS_LISTS", "HOJAS_VALIDAS", "ENCABEZADOS_ESPERADOS", "crear_clave", "valor_clave_numero",
              "finalizar_dataframe", "normalizar_bnb", "normalizar_bcp", "normalizar_union", "normalizar_economico",
              "normalizar_bisa", "normalizar_bmsc", "normalizar_archivo", "validar_archivo", "ecuacion_saldo",
              "encontrar_fila_encabezado", "leer_tabla_movimientos", "extraer_nombre_bnb", "descubrir_archivos",
              "numero", "normalizar_fecha", "normalizar_hora", "codigo_texto", "normalizar_texto",
              "leer_excel_robusto", "leer_todas_hojas", "texto_de_archivo"]
for k in congelados:
    print(("IDENTICO  " if a.get(k) == b.get(k) else "DIFERENTE ") + k)
print("\nCambiados:", sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k in a and k in b))
print("Nuevos   :", sorted(set(b) - set(a)))
print("Quitados :", sorted(set(a) - set(b)))
for f in ["captura_origen.py", "historico.py", "motor_generico.py", "NORMALIZADOR_POWER_AUTOMATE.zip"]:
    d = subprocess.run(["git", "diff", "--quiet", "9a3eae8", "--", str(REPO / f)], cwd=REPO).returncode
    print(f"{f}: {'IDENTICO' if d == 0 else 'MODIFICADO'} (git diff vs 9a3eae8)")
