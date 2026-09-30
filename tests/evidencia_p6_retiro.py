"""Evidencia P6 (retiro del legado) — correr desde tests/:

    python evidencia_p6_retiro.py <carpeta_referencia> [<commit_referencia>]

<carpeta_referencia> contiene el checkpoint P5 con sus archivos hermanos (p. ej. `git worktree add <carpeta> 0b182e2`).
Corre referencia (P5) y actual (P6) sobre los 12 fixtures reales con el reloj fijado y compara: LISTS.csv byte a byte,
NORMALIZADO.xlsx y ORIGEN.xlsx celda a celda, EXTRACTO_HISTORICO (P3b), por archivo movimientos / importes / saldos /
claves / banco-cuenta-moneda, las 26 columnas, la validación, el retorno y la consola. Además: (a) corre P6 con SOLO
los 5 archivos productivos en una carpeta aislada, (b) con las 13 cuentas renombradas (solo configuración), (c) busca
en el código productivo cualquier nombre legado, (d) compara el texto fuente de los componentes conservados, (e) git
diff de los archivos que no debían cambiar y (f) tamaño del código antes/después.
"""
import ast, contextlib, copy, hashlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.cwd()))
import pandas as pd
from evidencia_ab import FIJO, celdas
from helpers import COLUMNAS_LISTS_CONTRATO, EXTRACTOS, FIXTURES, FORMATOS_OK, huella_historico

REPO = Path.cwd().parent
ref = Path(sys.argv[1]).resolve()
commit = sys.argv[2] if len(sys.argv) > 2 else "0b182e2"
PRODUCTIVOS = ("motor_control_depositos_cbba.py", "deteccion_registro.py", "motor_generico.py",
               "registro_bancos.json", "captura_origen.py")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_10_retiro_legado_p6 import RETIRADOS, _nombres_de_codigo   # noqa: E402

fallos = []


def check(nombre, ok, detalle=""):
    print(("IDENTICO  " if ok else "DIFERENTE ") + nombre + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallos.append(nombre)


def correr(carpeta, tag, base, entorno=None):
    spec = importlib.util.spec_from_file_location(f"motor_{tag}", carpeta / "motor_control_depositos_cbba.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    ent, sal = base / tag / "in", base / tag / "out"
    ent.mkdir(parents=True)
    for fm in FORMATOS_OK:
        shutil.copy(EXTRACTOS / FIXTURES[fm], ent / FIXTURES[fm])
    entorno = entorno or {}
    viejo = {k: os.environ.get(k) for k in list(entorno) + ["CBBA_REGISTRO_BANCOS"]}
    os.environ.pop("CBBA_REGISTRO_BANCOS", None)
    os.environ.update(entorno)
    orig_now = pd.Timestamp.now
    pd.Timestamp.now = classmethod(lambda cls, tz=None: FIJO)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = m.ejecutar_motor(str(ent), str(sal / "NORMALIZADO.xlsx"))
    finally:
        pd.Timestamp.now = orig_now
        for k, v in viejo.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return m, res, sal, buf.getvalue()


def hist(origen, lists, out):
    spec = importlib.util.spec_from_file_location("h_" + out.name, REPO / "historico.py")
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    return h.generar_extractos_historicos(str(origen), str(lists), str(out))


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


def limpio(texto, carpeta):
    return [x.replace(str(carpeta), "<TMP>") for x in texto.splitlines()
            if x.strip() and "SOMBRA" not in x]


print(f"EVIDENCIA P6 — retiro del legado · referencia: checkpoint P5 = {commit} ({ref})\n")
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    _, ra, sa, oa = correr(ref, "p5", t)
    _, rb, sb, ob = correr(REPO, "p6", t)

    print("A) SALIDAS OPERATIVAS P5 vs P6 (12 fixtures reales, reloj fijo)")
    ba, bb = (sa / "LISTS.csv").read_bytes(), (sb / "LISTS.csv").read_bytes()
    check("LISTS.csv (bytes)", ba == bb, f"{len(bb)} bytes; sha {hashlib.sha256(bb).hexdigest()[:16]}")
    na, nb = celdas(sa / "NORMALIZADO.xlsx"), celdas(sb / "NORMALIZADO.xlsx")
    check("NORMALIZADO.xlsx hojas", list(na) == list(nb), str(list(nb)))
    for h in na:
        check(f"NORMALIZADO.xlsx · {h} (valores+formatos+tablas)", na[h] == nb.get(h), f"{len(na[h]['celdas'])} celdas")
    oa_, ob_ = celdas(sa / "ORIGEN.xlsx"), celdas(sb / "ORIGEN.xlsx")
    check("ORIGEN.xlsx (4 hojas, valores+formatos)", oa_ == ob_, str({h: len(oa_[h]["celdas"]) for h in oa_}))
    ha, hb = hist(sa / "ORIGEN.xlsx", sa / "LISTS.csv", t / "hist_p5"), hist(sb / "ORIGEN.xlsx", sb / "LISTS.csv", t / "hist_p6")
    fa = {p.name: huella_historico(p) for p in sorted((t / "hist_p5").iterdir())}
    fb = {p.name: huella_historico(p) for p in sorted((t / "hist_p6").iterdir())}
    check(f"EXTRACTO_HISTORICO P3b ({len(fb)} archivos, huella completa)", fa == fb and ha["estado"] == hb["estado"] == "OK",
          f"{ha['estado']} {hb['estado']}; advertencias {len(ha['advertencias'])}/{len(hb['advertencias'])}")
    for k in ("df_final", "df_validacion", "resumen", "df_resultado_archivos", "df_deteccion_final"):
        try:
            pd.testing.assert_frame_equal(ra[k], rb[k]); ok = True
        except AssertionError:
            ok = False
        check(f"retorno['{k}']", ok)
    for k in ("ruta_salida", "ruta_lists_csv"):
        check(f"retorno['{k}'] (misma ruta relativa)", Path(ra[k]).name == Path(rb[k]).name)
    check("retorno['origen_estado'] (estado, movimientos mapeados)",
          (ra["origen_estado"]["estado"], ra["origen_estado"].get("movimientos_mapeados")) ==
          (rb["origen_estado"]["estado"], rb["origen_estado"].get("movimientos_mapeados")),
          f"{rb['origen_estado']['estado']} / {rb['origen_estado'].get('movimientos_mapeados')}")
    da = {n: {k: v for k, v in d.items() if k not in ("FORMATO_LEGADO", "CUENTA_NUEVA")}
          for n, d in ra["deteccion_estado"]["archivos"].items()}
    check("retorno['deteccion_estado'] (sin FORMATO_LEGADO / CUENTA_NUEVA retirados)",
          da == rb["deteccion_estado"]["archivos"] and ra["deteccion_estado"]["version_deteccion"] ==
          rb["deteccion_estado"]["version_deteccion"])
    print(f"    claves del retorno retiradas: {sorted(set(ra) - set(rb))} · nuevas: {sorted(set(rb) - set(ra))}")
    check("claves del retorno: solo se retira 'sombra_estado'", set(ra) - set(rb) == {"sombra_estado"} and set(rb) <= set(ra))
    la, lb = limpio(oa, t / "p5"), limpio(ob, t / "p6")
    check("salida de consola (sin la línea de SOMBRA de P5)", la == lb, f"{len(lb)} líneas")
    print("    archivos de salida P5:", sorted(p.name for p in sa.iterdir()))
    print("    archivos de salida P6:", sorted(p.name for p in sb.iterdir()))
    check("archivos de salida P6 = P5 sin SOMBRA_REPORTE.json / SOMBRA_DIFERENCIAS.csv",
          sorted(p.name for p in sb.iterdir()) ==
          sorted(p.name for p in sa.iterdir() if not p.name.startswith("SOMBRA_")))

    print("\nB) POR ARCHIVO (LISTS.csv): movimientos, importes, saldos, claves, banco/cuenta/moneda")
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

    print("\nC) PRODUCCIÓN SIN LEGADO: SOLO LOS 5 ARCHIVOS PRODUCTIVOS EN UNA CARPETA AISLADA (CBBA_MOTOR_SOMBRA=1)")
    prod = t / "solo_productivos"
    prod.mkdir()
    for f in PRODUCTIVOS:
        shutil.copy(REPO / f, prod / f)
    print("    carpeta:", sorted(p.name for p in prod.iterdir()))
    m0, r0, s0, _ = correr(prod, "aislado", t, {"CBBA_MOTOR_SOMBRA": "1"})
    check("LISTS.csv (bytes) aislado = P5", (s0 / "LISTS.csv").read_bytes() == ba)
    check("NORMALIZADO.xlsx (4 hojas) aislado = P5", celdas(s0 / "NORMALIZADO.xlsx") == na)
    check("ORIGEN.xlsx (4 hojas) aislado = P5", celdas(s0 / "ORIGEN.xlsx") == oa_)
    check("salidas aisladas = LISTS.csv, NORMALIZADO.xlsx, ORIGEN.xlsx (CBBA_MOTOR_SOMBRA sin efecto)",
          sorted(p.name for p in s0.iterdir()) == ["LISTS.csv", "NORMALIZADO.xlsx", "ORIGEN.xlsx"])
    check("el motor aislado no expone ningún nombre retirado", not [n for n in RETIRADOS if hasattr(m0, n)])
    for f in ("motor_control_depositos_cbba.py", "deteccion_registro.py", "motor_generico.py", "captura_origen.py"):
        antes = sorted(_nombres_de_codigo(ref / f) & RETIRADOS)
        despues = sorted(_nombres_de_codigo(REPO / f) & RETIRADOS)
        check(f"nombres legados en el código de {f}: P5={len(antes)} → P6={len(despues)}", despues == [],
              ", ".join(despues))
    defs_norm = lambda p: sorted(n.name for n in ast.parse(p.read_text(encoding="utf-8")).body
                                 if isinstance(n, ast.FunctionDef) and n.name.startswith("normalizar_"))
    print("    def normalizar_* en el motor P5:", defs_norm(ref / "motor_control_depositos_cbba.py"))
    print("    def normalizar_* en el motor P6:", defs_norm(REPO / "motor_control_depositos_cbba.py"),
          "(primitivas de texto/fecha/hora + la normalización por registro)")

    print("\nD) CUENTAS NUEVAS SOLO POR CONFIGURACIÓN (13 ids renombrados *_CFG)")
    reg = copy.deepcopy(json.loads((REPO / "registro_bancos.json").read_text(encoding="utf-8")))
    for c in reg["CUENTAS"]:
        c["id"] += "_CFG"
    ruta_reg = t / "registro_cfg.json"
    ruta_reg.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    _, r1, s1, _ = correr(REPO, "cfg", t, {"CBBA_REGISTRO_BANCOS": str(ruta_reg)})
    check("LISTS.csv (bytes) con cuentas nuevas = P5", (s1 / "LISTS.csv").read_bytes() == ba,
          f"FORMATO = {sorted(r1['df_deteccion_final']['FORMATO'])[:2]}...")
    check("ORIGEN.xlsx generado con cuentas nuevas", r1["origen_estado"]["estado"] == "OK",
          f"movimientos mapeados {r1['origen_estado'].get('movimientos_mapeados')}")


print(f"\nE) COMPONENTES CONSERVADOS ({commit} vs. actual)")


def defs(src, sin_doc=False):
    out = {}
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out[n.name] = ast.dump(_sin_docstrings(n)) if sin_doc else ast.get_source_segment(src, n)
        elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            out[n.targets[0].id] = ast.dump(n) if sin_doc else ast.get_source_segment(src, n)
    return out


def _sin_docstrings(nodo):
    nodo = copy.deepcopy(nodo)
    for n in ast.walk(nodo):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(n, clean=False) is not None:
            n.body = n.body[1:] or [ast.Pass()]
    return nodo


def metodos(src, clase):
    c = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == clase)
    return {m.name: ast.dump(_sin_docstrings(m)) for m in c.body if isinstance(m, ast.FunctionDef)}


leer = lambda base, f: (base / f).read_text(encoding="utf-8")
a, b = defs(leer(ref, "motor_control_depositos_cbba.py")), defs(leer(REPO, "motor_control_depositos_cbba.py"))
conservados = ["COLUMNAS_LISTS", "crear_clave", "valor_clave_numero", "finalizar_dataframe", "ecuacion_saldo",
               "extraer_nombre_bnb", "numero", "normalizar_fecha", "normalizar_hora", "codigo_texto", "normalizar_texto",
               "buscar_columna", "buscar_columna_opcional", "leer_excel_robusto", "leer_todas_hojas",
               "descubrir_archivos", "PREFIJOS_SALIDA_SISTEMA", "verificar_dependencias", "modulo_deteccion",
               "detectar_extracto", "detectar_formato", "modulo_generico", "normalizador_registro",
               "normalizar_extracto", "validar_extracto", "contrato_origen_registro"]
for k in conservados:
    check(f"motor · {k} (texto fuente)", a.get(k) == b.get(k))
print("    motor · cambiados:", sorted(k for k in set(a) & set(b) if a[k] != b[k]))
print("    motor · retirados:", sorted(set(a) - set(b)))
print("    motor · nuevos   :", sorted(set(b) - set(a)))
ga, gb = leer(ref, "motor_generico.py"), leer(REPO, "motor_generico.py")
for clase in ("Registro", "MotorGenerico"):
    ma, mb = metodos(ga, clase), metodos(gb, clase)
    iguales = [k for k in mb if ma.get(k) == mb[k]]
    distintos = [k for k in mb if ma.get(k) != mb[k]]
    print(f"    motor_generico · {clase}: retirados {sorted(set(ma) - set(mb))}; distintos {distintos}")
    check(f"motor_generico · {clase}: métodos conservados idénticos (código sin docstrings)",
          set(distintos) <= {"__init__"}, f"{len(iguales)} idénticos")
da_, db_ = defs(ga, True), defs(gb, True)
for k in ("FILTROS_FECHA", "MODOS_IMPORTE", "ESTRATEGIAS_DEPOSITANTE", "FUENTES_SALDO_INICIAL",
          "FUENTES_SALDO_FINAL", "ROLES_OBLIGATORIOS", "RegistroError"):
    check(f"motor_generico · {k}", da_.get(k) == db_.get(k))
print("    motor_generico · retirados:", sorted(set(da_) - set(db_)))
print("    motor_generico · renombrados: PRIMITIVAS_LEGADO → PRIMITIVAS_MOTOR, namespace_legado → namespace_primitivas "
      f"(misma lista: {defs(ga)['PRIMITIVAS_LEGADO'].split('(', 1)[1] == defs(gb)['PRIMITIVAS_MOTOR'].split('(', 1)[1]})")
ma, mb = metodos(leer(ref, "deteccion_registro.py"), "DetectorRegistro"), metodos(leer(REPO, "deteccion_registro.py"), "DetectorRegistro")
print(f"    deteccion_registro · DetectorRegistro: retirados {sorted(set(ma) - set(mb))}; "
      f"distintos {[k for k in mb if ma.get(k) != mb[k]]}")
check("deteccion_registro · métodos de lectura/detección idénticos (salvo el tramo final de detectar)",
      all(ma[k] == mb[k] for k in mb if k not in ("__init__", "cargar", "detectar")))

print("\nF) ARCHIVOS QUE NO DEBÍAN CAMBIAR (git diff vs referencia)")
for f in ["captura_origen.py", "historico.py", "NORMALIZADOR_POWER_AUTOMATE.zip", "tests/golden", "tests/fixtures"]:
    d = subprocess.run(["git", "diff", "--quiet", commit, "--", f], cwd=REPO).returncode
    check(f"{f}", d == 0)
ja = json.loads(leer(ref, "registro_bancos.json")); jb = json.loads(leer(REPO, "registro_bancos.json"))
for j in (ja, jb):
    j.pop("_ayuda")
    for f in j["FORMATOS"].values():
        f.pop("legado", None)
check("registro_bancos.json = P5 salvo _ayuda y los bloques 'legado' retirados", ja == jb,
      f"{len(jb['FORMATOS'])} formatos, {len(jb['CUENTAS'])} cuentas")

print("\nG) TAMAÑO DEL CÓDIGO (líneas / bytes)")
tot_a = tot_b = 0
for f in ("motor_control_depositos_cbba.py", "motor_generico.py", "deteccion_registro.py", "registro_bancos.json",
          "captura_origen.py", "historico.py"):
    la_, lb_ = len(leer(ref, f).splitlines()), len(leer(REPO, f).splitlines())
    ba_, bb_ = (ref / f).stat().st_size, (REPO / f).stat().st_size
    tot_a += la_; tot_b += lb_
    print(f"    {f:<34} {la_:>5} → {lb_:>5} líneas   {ba_:>7} → {bb_:>7} bytes")
print(f"    {'TOTAL':<34} {tot_a:>5} → {tot_b:>5} líneas   ({tot_b - tot_a:+d})")

print("\nRESULTADO:", "SIN REGRESIONES" if not fallos else f"DIFERENCIAS: {fallos}")
sys.exit(1 if fallos else 0)
