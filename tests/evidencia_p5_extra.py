"""Evidencia P5 complementaria a evidencia_ab.py (correr desde tests/):

    python evidencia_p5_extra.py <carpeta_referencia> [<commit_referencia>]

<carpeta_referencia> contiene el motor del checkpoint P4 con sus archivos hermanos (p. ej. `git worktree add
<carpeta> 998158e`). Corre referencia y actual sobre los 12 fixtures con el reloj fijado y compara:
ORIGEN.xlsx celda a celda, la huella de los EXTRACTO_HISTORICO (P3b), movimientos / importes / saldos / claves /
banco-cuenta-moneda por archivo, las 26 columnas y el texto fuente de los componentes congelados. Además corre el
motor actual (a) con TODA la normalización legada inutilizada y (b) con las 13 cuentas renombradas (cuentas nuevas
solo por configuración, desconocidas para el legado) y compara su LISTS.csv byte a byte con la referencia.
"""
import ast, contextlib, copy, hashlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.cwd()))
import pandas as pd
from evidencia_ab import FIJO, celdas, correr
from helpers import COLUMNAS_LISTS_CONTRATO, EXTRACTOS, FIXTURES, FORMATOS_OK, huella_historico

REPO = Path.cwd().parent
ref = Path(sys.argv[1])
commit = sys.argv[2] if len(sys.argv) > 2 else "998158e"
LEGADO = ("normalizar_archivo", "normalizar_bnb", "normalizar_bcp", "normalizar_union", "normalizar_economico",
          "normalizar_bisa", "normalizar_bmsc", "validar_archivo", "leer_tabla_movimientos",
          "encontrar_fila_encabezado", "aplicar_identidad_registro")
fallos = []


def check(nombre, ok, detalle=""):
    print(("IDENTICO  " if ok else "DIFERENTE ") + nombre + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallos.append(nombre)


def hist(origen, lists, out):
    spec = importlib.util.spec_from_file_location("h_" + out.name, REPO / "historico.py")
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    return h.generar_extractos_historicos(str(origen), str(lists), str(out))


def correr_sin_legado(tag, base, registro=None):
    """Motor actual con la normalización legada inutilizada (y referencia en sombra apagada)."""
    spec = importlib.util.spec_from_file_location(f"motor_{tag}", REPO / "motor_control_depositos_cbba.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    usados = []

    def prohibido(nombre):
        def f(*a, **k):
            usados.append(nombre)
            raise AssertionError(f"legado usado: {nombre}")
        return f

    for n in LEGADO:
        setattr(m, n, prohibido(n))
    ent, sal = base / tag / "in", base / tag / "out"
    ent.mkdir(parents=True)
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    entorno = {"CBBA_MOTOR_SOMBRA": "0", **({"CBBA_REGISTRO_BANCOS": str(registro)} if registro else {})}
    viejo = {k: os.environ.get(k) for k in entorno}
    os.environ.update(entorno)
    orig_now = pd.Timestamp.now
    pd.Timestamp.now = classmethod(lambda cls, tz=None: FIJO)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = m.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx"))
    finally:
        pd.Timestamp.now = orig_now
        for k, v in viejo.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return res, sal, usados


def por_archivo(lists):
    d = pd.read_csv(lists, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    out = {}
    for nombre, g in d.groupby("ARCHIVO ORIGEN", sort=True):
        num = lambda c: round(pd.to_numeric(g[c], errors="coerce").fillna(0).sum(), 2)
        out[nombre] = {
            "movimientos": len(g), "importe": num("IMPORTE"), "creditos": num("CRÉDITO"), "debitos": num("DÉBITO"),
            "saldo_primero": g["SALDO"].iloc[0], "saldo_ultimo": g["SALDO"].iloc[-1],
            "sha_saldos": hashlib.sha256("|".join(g["SALDO"]).encode()).hexdigest()[:12],
            "sha_claves": hashlib.sha256("|".join(g["CLAVE TRANSACCIÓN"]).encode()).hexdigest()[:12],
            "identidad": sorted({(b, c, m) for b, c, m in g[["BANCO", "CUENTA BANCARIA", "MONEDA"]].values}),
        }
    return out, list(d.columns)


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    with contextlib.redirect_stdout(io.StringIO()):
        _, sa, _ = correr(ref / "motor_control_depositos_cbba.py", "ref", t)
        rb, sb, _ = correr(REPO / "motor_control_depositos_cbba.py", "act", t)

    print("1) ORIGEN.xlsx E HISTORICO P3b")
    ca, cb = celdas(sa / "ORIGEN.xlsx"), celdas(sb / "ORIGEN.xlsx")
    check("ORIGEN.xlsx (4 hojas, valores+formatos)", ca == cb, str({h: len(ca[h]["celdas"]) for h in ca}))
    ha, hb = hist(sa / "ORIGEN.xlsx", sa / "LISTS.csv", t / "hist_ref"), hist(sb / "ORIGEN.xlsx", sb / "LISTS.csv", t / "hist_act")
    fa = {p.name: huella_historico(p) for p in sorted((t / "hist_ref").iterdir())}
    fb = {p.name: huella_historico(p) for p in sorted((t / "hist_act").iterdir())}
    check(f"EXTRACTO_HISTORICO P3b ({len(fa)} archivos, huella completa)", fa == fb and ha["estado"] == hb["estado"] == "OK",
          f"{ha['estado']} {hb['estado']}; advertencias {len(ha['advertencias'])}/{len(hb['advertencias'])}")

    print("\n2) POR ARCHIVO (LISTS.csv): movimientos, importes, saldos, claves, banco/cuenta/moneda")
    pa, cols_a = por_archivo(sa / "LISTS.csv")
    pb, cols_b = por_archivo(sb / "LISTS.csv")
    check("26 columnas (nombres y orden)", cols_a == cols_b == COLUMNAS_LISTS_CONTRATO, f"{len(cols_b)} columnas")
    check("mismos archivos con movimientos", sorted(pa) == sorted(pb), f"{len(pb)} archivos (BISA_ME: 0 movimientos)")
    for nombre in sorted(pb):
        a, b = pa.get(nombre), pb[nombre]
        check(f"{nombre:<22}", a == b, f"mov={b['movimientos']} importe={b['importe']} cred={b['creditos']} "
              f"deb={b['debitos']} saldo_fin={b['saldo_ultimo']} claves={b['sha_claves']} {b['identidad'][0]}")
    va = pd.read_excel(sa / "NORMALIZADO.xlsx", sheet_name="VALIDACION")
    vb = pd.read_excel(sb / "NORMALIZADO.xlsx", sheet_name="VALIDACION")
    check("validación de saldos (12 archivos, hoja VALIDACION)", va.equals(vb), str(vb["ESTADO"].value_counts().to_dict()))

    print("\n3) REFERENCIA LEGADA EN SOMBRA (motor actual)")
    s = rb["sombra_estado"]
    print("   ", {k: s.get(k) for k in ("estado", "modo", "archivos_comparados", "archivos_coinciden",
                                          "diferencias_total", "observaciones_total")})
    check("referencia legada: 12/12 coinciden, 0 diferencias, 0 observaciones",
          (s["estado"], s["archivos_coinciden"], s["diferencias_total"], s["observaciones_total"]) ==
          ("SIN_DIFERENCIAS", 12, 0, 0))

    print("\n4) PRODUCCION SIN NINGUN NORMALIZADOR LEGADO")
    r0, s0, usados = correr_sin_legado("sin_legado", t)
    check("LISTS.csv (bytes) sin legado = referencia P4", (s0 / "LISTS.csv").read_bytes() == (sa / "LISTS.csv").read_bytes(),
          f"legado llamado: {usados or 'nunca'}")
    c0 = celdas(s0 / "NORMALIZADO.xlsx")
    check("NORMALIZADO.xlsx (4 hojas) sin legado = referencia P4", c0 == celdas(sa / "NORMALIZADO.xlsx"))

    print("\n5) CUENTAS NUEVAS SOLO POR CONFIGURACION (13 ids renombrados *_CFG, sin legado)")
    reg = json.loads((REPO / "registro_bancos.json").read_text(encoding="utf-8"))
    reg = copy.deepcopy(reg)
    for c in reg["CUENTAS"]:
        c["id"] += "_CFG"
    ruta_reg = t / "registro_cfg.json"
    ruta_reg.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    r1, s1, usados = correr_sin_legado("cfg", t, ruta_reg)
    nuevas = [d["CUENTA_NUEVA"] for d in r1["deteccion_estado"]["archivos"].values()]
    print(f"    detección: {sum(nuevas)}/{len(nuevas)} cuentas nuevas para el legado; FORMATO = "
          f"{sorted(r1['df_deteccion_final']['FORMATO'])[:3]}...")
    check("LISTS.csv (bytes) con cuentas nuevas = referencia P4", (s1 / "LISTS.csv").read_bytes() == (sa / "LISTS.csv").read_bytes(),
          f"legado llamado: {usados or 'nunca'}")
    c1, cref = celdas(s1 / "NORMALIZADO.xlsx"), celdas(sa / "NORMALIZADO.xlsx")
    check("NORMALIZADO.xlsx · LISTS con cuentas nuevas", c1["LISTS"] == cref["LISTS"])
    for hoja in ("VALIDACION", "DIAGNOSTICO"):
        sin_formato = lambda c: {k: v for k, v in c[hoja]["celdas"].items() if k[1] != 2}
        check(f"NORMALIZADO.xlsx · {hoja} con cuentas nuevas (salvo la columna FORMATO = id)",
              sin_formato(c1) == sin_formato(cref))
    check("ORIGEN.xlsx generado con cuentas nuevas", r1["origen_estado"]["estado"] == "OK",
          f"movimientos mapeados {r1['origen_estado'].get('movimientos_mapeados')}")

print(f"\n6) COMPONENTES CONGELADOS ({commit} vs. actual, texto fuente del motor):")


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
congelados = ["COLUMNAS_LISTS", "crear_clave", "valor_clave_numero", "finalizar_dataframe",
              "normalizar_bnb", "normalizar_bcp", "normalizar_union", "normalizar_economico", "normalizar_bisa",
              "normalizar_bmsc", "normalizar_archivo", "validar_archivo", "ecuacion_saldo", "HOJAS_VALIDAS",
              "ENCABEZADOS_ESPERADOS", "encontrar_fila_encabezado", "leer_tabla_movimientos", "extraer_nombre_bnb",
              "descubrir_archivos", "numero", "normalizar_fecha", "normalizar_hora", "codigo_texto",
              "normalizar_texto", "buscar_columna", "buscar_columna_opcional", "leer_excel_robusto",
              "leer_todas_hojas", "texto_de_archivo", "modulo_deteccion", "detector_registro", "detectar_extracto",
              "detectar_formato", "aplicar_identidad_registro"]
for k in congelados:
    check(k, a.get(k) == b.get(k))
print("\nCambiados:", sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k in a and k in b))
print("Nuevos   :", sorted(set(b) - set(a)))
print("Quitados :", sorted(set(a) - set(b)))
for f in ["captura_origen.py", "historico.py", "deteccion_registro.py", "NORMALIZADOR_POWER_AUTOMATE.zip"]:
    d = subprocess.run(["git", "diff", "--quiet", commit, "--", str(REPO / f)], cwd=REPO).returncode
    check(f"{f} (git diff vs {commit})", d == 0)
for f in ["motor_generico.py", "registro_bancos.json"]:
    d = subprocess.run(["git", "diff", "--quiet", commit, "--", str(REPO / f)], cwd=REPO).returncode
    print(f"{f}: {'IDENTICO' if d == 0 else 'MODIFICADO (P5)'} (git diff vs {commit})")

print("\nRESULTADO:", "SIN REGRESIONES" if not fallos else f"DIFERENCIAS: {fallos}")
sys.exit(1 if fallos else 0)
