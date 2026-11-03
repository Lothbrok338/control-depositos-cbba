"""Reúne evidencia ya ejecutada y prepara la entrega sin commits ni red."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

from p8.construir_paquete_p8 import RAIZ, ZIP_SALIDA
from p8.validar_p8 import validar


CHECKPOINT = "673754a9b69072e6960bbf0c7ffb0f50dc5d2670"


def git(carpeta, *args):
    return subprocess.check_output(["git", "-C", str(carpeta), *args], text=True).strip()


def escribir_json(ruta, valor):
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def entregar(p7):
    evidencia = RAIZ / "p8/evidencias"
    assert git(p7, "rev-parse", "HEAD") == CHECKPOINT
    assert git(RAIZ, "rev-parse", "HEAD") == CHECKPOINT
    assert not git(p7, "status", "--porcelain"), "El checkout P7 de referencia debe permanecer limpio"
    assert not git(RAIZ, "diff", "--name-only", CHECKPOINT), "Se modificó un archivo de P7/P6"
    resultados = {}
    for etiqueta, carpeta in [("p7", p7), ("p8", RAIZ)]:
        resultados[etiqueta] = json.loads((carpeta / "tests/reports/resultados.json").read_text(encoding="utf-8"))
        escribir_json(evidencia / f"resultados_{etiqueta}.json", resultados[etiqueta])
    conteos = {k: dict(Counter(r["estado"] for r in v)) for k, v in resultados.items()}
    fallos = {k: sorted(r["id"] for r in v if r["estado"] == "FAIL") for k, v in resultados.items()}
    mapa7 = {r["id"]: r["estado"] for r in resultados["p7"]}
    mapa8 = {r["id"]: r["estado"] for r in resultados["p8"]}
    assert all(mapa8.get(k) == v for k, v in mapa7.items()), "Hay un cambio de resultado en las pruebas heredadas"
    nuevas = sorted(set(mapa8) - set(mapa7))
    assert nuevas and all(mapa8[k] == "PASS" for k in nuevas)
    assert fallos["p7"] == fallos["p8"]
    # Los logs se generaron con exactamente la misma invocación en ambas raíces.
    for k in ("p7", "p8"):
        log = (evidencia / f"suite_{k}.log").read_text(encoding="utf-8")
        assert f"{conteos[k]['FAIL']} failed, {conteos[k]['PASS']} passed" in log
    entorno = {
        "python": sys.version, "ejecutable": sys.executable, "plataforma": platform.platform(),
        "dependencias": {n: importlib.metadata.version(n) for n in ("pytest", "pandas", "numpy", "openpyxl", "xlrd", "python-calamine")},
        "comando_ambas_suites": "python -m pytest -q -rxX",
        "directorio_p7": str(p7), "directorio_p8": str(RAIZ), "checkpoint": CHECKPOINT,
        "dependencias_modificadas_durante_correccion": False,
    }
    escribir_json(evidencia / "entorno_comparacion.json", entorno)
    escribir_json(evidencia / "comparacion.json", {"conteos": conteos, "fallos": fallos, "pruebas_nuevas": nuevas, "heredadas_identicas": True})
    ensayo = validar()
    escribir_json(evidencia / "ensayo_piloto.json", ensayo)
    tabla = "\n".join(f"| {k.upper()} | {conteos[k].get('PASS',0)} | {conteos[k].get('SKIP',0)} | {conteos[k].get('XFAIL',0)} | {conteos[k].get('FAIL',0)} |" for k in ("p7", "p8"))
    lista_fallos = "\n".join(f"{n}. `{nombre}`" for n, nombre in enumerate(fallos["p7"], 1))
    versiones = ", ".join(f"{k} {v}" for k, v in entorno["dependencias"].items())
    protegidos = git(RAIZ, "ls-files").splitlines()
    huellas = {p: hashlib.sha256((RAIZ / p).read_bytes()).hexdigest() for p in protegidos}
    for p in protegidos:
        assert hashlib.sha256((p7 / p).read_bytes()).hexdigest() == huellas[p], p
    escribir_json(evidencia / "huellas_archivos_congelados.json", huellas)
    reporte = f'''# Corrección P8 después de auditoría

Estado: correcciones y ensayos locales completados; piloto Microsoft 365 pendiente. Sin commit ni checkpoint P8. HEAD/main y origin/checkpoint-p7 siguen en `{CHECKPOINT}`. Todos los archivos versionados de esa base son idénticos por SHA-256 en ambos árboles.

## 1. Comparación reproducida en el mismo entorno

Se ejecutó exactamente `python -m pytest -q -rxX` desde la raíz de cada checkout, con el mismo ejecutable `{sys.executable}`. P7 se ejecutó aislado en `{p7}` con HEAD detached en el checkpoint, sin archivos P8. P8 se ejecutó desde `{RAIZ}`. No se cambiaron dependencias, tolerancias, pruebas heredadas ni doradas durante la corrección.

Versiones: {versiones}.

| Suite | PASS | SKIP | XFAIL | FAIL |
|---|---:|---:|---:|---:|
{tabla}

Las {len(mapa7)} pruebas heredadas conservan exactamente el mismo resultado individual. Hay {len(nuevas)} pruebas nuevas P8, todas PASS. Los seis fallos se reproducen sin P8; la comparación confirma que no son regresiones introducidas por P8. No demuestra por sí sola qué versión histórica de una dependencia originó las diferencias numéricas.

FAIL exactos, iguales en ambos checkouts:

{lista_fallos}

Las trazas muestran serializaciones de coma flotante como `3807655.560000001` frente a `3807655.56`, y una diferencia máxima `1.862645149230957e-09` frente al umbral existente `1e-9`. Se conservan íntegros motor, tolerancias y doradas.

Evidencia: `p8/evidencias/suite_p7.log`, `suite_p8.log`, `resultados_p7.json`, `resultados_p8.json`, `comparacion.json`, `entorno_comparacion.json` y `huellas_archivos_congelados.json`. Las pruebas conjuntas P7+P8 se ejecutaron además por separado; resultado en `pruebas_p7_p8.log`.

## 2. Correcciones implementadas

| Observación | Resultado |
|---|---|
| Terminación antes de bitácora | `FINALLY` registra el lote; `Finalizar_ejecucion` solo corre tras su éxito. JSON ilegible, contrato inválido y propiedades ausentes tienen ruta FALLIDO comprobada. |
| Trigger/ubicación | SharePoint `GetOnNewFileItems`, nombre `{{FilenameWithExtension}}`, identificación `{{Identifier}}`, exclusión de `{{IsFolder}}`; patrón estricto de archivo. |
| Contenido | `inferContentType = false`; Parse JSON usa `json(base64ToString(body('Obtener_contenido_del_archivo')?['$content']))` con el esquema P7 idéntico. |
| Timeout/reconsulta | Crear Failed/TimedOut dispara reconsulta; presencia → YA_EXISTE, ausencia o reconsulta fallida → ERROR de fila. Continúa el lote. |
| Diagnóstico | JSON con etapa/archivo/mensaje, y fila/CLAVE_TRANSACCION/motivo/código por error; máximo 8 detalles y 8000 caracteres. Sin cuerpos ni `result()`. |
| Preconsulta/fechas | Una consulta exacta indexada por clave antes de crear. No usa límites temporales ni depende de conversión UTC. |
| Fecha testigo | `2026-07-09` se copia intacta y coincide con `20260709`; 9 de julio es el testigo visual exigido en tenant. |
| Piloto ampliado | Cuatro filas existentes de doradas/fixtures, con débito, originante, Ó, espacio, hora vacía y crédito `-640.0`; trazabilidad individual. |

La definición inicial P8 ya evitaba Terminate previo al cierre; esta corrección hace explícita y prueba la terminación posterior a una bitácora confirmada. Se corrigieron también dos nombres internos de acción repetidos; el validador exige ahora nombres únicos y dependencias runAfter dentro de cada ámbito.

## 3. Resultado del ensayo local del flujo generado

Se interpreta el JSON WDL entregado con conectores simulados; no es una ejecución en Power Automate. Las pruebas recorren expresiones, scopes, condiciones, bucles y ejecución posterior. Incluyen propagación conservadora de fallos de acciones hijas para comprobar que un error manejado no degrada todo el lote.

| Ejecución | RECIBIDA | VÁLIDA | NUEVA | YA_EXISTE | ERROR | Claves preconsulta | Intentos crear | Activos finales |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Primera | 8 | 8 | 8 | 0 | 0 | 0 | 8 | 8 |
| Reproceso | 8 | 8 | 0 | 8 | 0 | 8 | 0 | 8 |

Ambas terminan COMPLETADO. Las pruebas con fallos de creación/reconsulta terminan COMPLETADO_CON_ERRORES y procesan las siguientes filas. El segundo conjunto crea 4 movimientos y al reprocesar consulta 4 claves y realiza 0 creaciones.

## 4. Archivos y entrega

Actualizados respecto a la entrega P8 anterior: `DOCUMENTACION_TECNICA_P8.md`, `P8_CARGA_DEPOSITOS_ACTIVOS.zip`, `p8/construir_paquete_p8.py`, `p8/flujo_p8_definition.json`, `p8/validar_p8.py`, `tests/test_12_flujo_p8.py` y el ZIP general.

Nuevos en esta corrección: `p8/definicion.py`, `p8/ensayo_wdl.py`, `p8/preparar_piloto.py`, `p8/entregar_correccion.py`, `p8/piloto_ampliado/`, `p8/evidencias/` y este reporte. El esquema de Lists conserva sus columnas y tipos. Todos los archivos P8 siguen sin commit; no hay cambios en archivos versionados de P7/P6.

El ZIP de flujo mantiene la estructura del paquete exportado real disponible en el repositorio. La integridad y reproducibilidad local están verificadas. Su importación efectiva todavía no está certificada por Microsoft 365. El ZIP general incluye documentación, fuentes, pruebas, evidencia y los insumos congelados de P7 necesarios para reproducirlos; excluye caches.

## 5. Pendientes y límites reales

1. Importar/configurar la conexión, sitio, biblioteca, carpeta y listas reales; comprobar que el diseñador acepta la definición.
2. Confirmar las propiedades del trigger y el sobre binario con inferContentType false. Si se observa JSON interpretado, revisar y cambiar conjuntamente configuración y expresión; no adivinar.
3. Ejecutar piloto 8 + reproceso y comprobar ocho claves preconsultadas, cero intentos de crear, total ocho. Verificar visualmente 9 de julio y extremos.
4. Ejecutar el segundo conjunto + reproceso y verificar signos, texto, espacios y acentos.
5. Ningún flujo puede prometer persistencia si la propia lista de bitácora está inaccesible: en ese caso la ejecución queda fallida y requiere revisión de historial. No se declara éxito ni se oculta el fallo.
6. Las consultas por clave priorizan corrección para el piloto. No se optimizan 4000 movimientos. FECHA_CARGA y D-15 siguen intactos.

P8 queda disponible para revisión antes del piloto. No se ha creado Power Apps ni se ha ejecutado ningún cambio sobre Microsoft 365.
'''
    (RAIZ / "REPORTE_CORRECCION_P8.md").write_text(reporte, encoding="utf-8")
    nombres = ["DOCUMENTACION_TECNICA_P8.md", "REPORTE_CORRECCION_P8.md", ZIP_SALIDA.name,
               "tests/test_12_flujo_p8.py", "adaptador_m365.py", "esquema_parse_json_p7.json",
               "DISENO_LISTA_DEPOSITOS_ACTIVOS.md", "ESPECIFICACION_FLUJO_P7_CARGA_DEPOSITOS_ACTIVOS.md"]
    nombres += [str(p.relative_to(RAIZ)) for carpeta in (RAIZ / "p8", RAIZ / "ejemplos_p7") for p in carpeta.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    nombres = sorted(set(nombres) - {"p8/evidencias/sha256_entregables.json"})
    huellas_entrega = {n: hashlib.sha256((RAIZ / n).read_bytes()).hexdigest() for n in nombres}
    escribir_json(evidencia / "sha256_entregables.json", huellas_entrega)
    nombres = sorted(set(nombres + ["p8/evidencias/sha256_entregables.json"]))
    destino = RAIZ / "ENTREGABLES_P8_CONTROL_DEPOSITOS_CBBA.zip"
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nombre in nombres:
            info = zipfile.ZipInfo(nombre, date_time=(2026, 9, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (RAIZ / nombre).read_bytes())
    with zipfile.ZipFile(destino) as z:
        assert z.testzip() is None
    print(json.dumps({"conteos": conteos, "fallos_iguales": True, "archivos_bundle": len(nombres),
                      "sha256_flujo": hashlib.sha256(ZIP_SALIDA.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--p7", type=Path, required=True)
    entregar(parser.parse_args().p7)
