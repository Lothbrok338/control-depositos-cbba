"""Selecciona filas existentes; usa P7 sin modificarlo ni ejecutar el motor."""
import csv
import hashlib
import io
import json
from p8.construir_paquete_p8 import _cargar_adaptador, RAIZ

DESTINO = RAIZ / "p8/piloto_ampliado"
FUENTE = RAIZ / "tests/golden/LOTE_12_LISTS.csv"


def preparar():
    ad = _cargar_adaptador()
    with FUENTE.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    criterios = {
        "DEBITO_NO_VACIO": lambda r: bool(r["DÉBITO"]),
        "ORIGINANTE": lambda r: bool(r["DEPOSITANTE / ORIGINANTE"]),
        "CLAVE_CON_O_Y_ESPACIO": lambda r: "Ó" in r["CLAVE TRANSACCIÓN"] and " " in r["CLAVE TRANSACCIÓN"],
        "HORA_VACIA": lambda r: not r["HORA MOVIMIENTO"],
        "NUMERO_NEGATIVO": lambda r: any(r[c] and float(r[c]) < 0 for c in ("IMPORTE", "DÉBITO", "CRÉDITO", "SALDO")),
    }
    indices = sorted({next(i for i, r in enumerate(filas) if criterio(r)) for criterio in criterios.values()})
    s = io.StringIO(newline="")
    escritor = csv.DictWriter(s, fieldnames=ad.COLUMNAS_CSV, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows([filas[i] for i in indices])
    contenido = s.getvalue().encode("utf-8-sig")
    sha = hashlib.sha256(contenido).hexdigest()
    movimientos = [{tecnico: filas[i][origen] for origen, tecnico, _, _ in ad.COLUMNAS_M365} for i in indices]
    for m in movimientos:
        if ad.validar_movimiento(m):
            raise ValueError(ad.validar_movimiento(m))
    DESTINO.mkdir(exist_ok=True)
    (DESTINO / "LISTS_PILOTO_AMPLIADO.csv").write_bytes(contenido)
    nombre = f"DEPOSITOS_ACTIVOS__{ad.identificador_lote(sha)}.json"
    (DESTINO / nombre).write_bytes(ad.serializar_artefacto(ad.identificador_lote(sha), "LISTS_PILOTO_AMPLIADO.csv", sha, movimientos, []))
    trazabilidad = {
        "fuente": str(FUENTE.relative_to(RAIZ)), "sha256_fuente": hashlib.sha256(FUENTE.read_bytes()).hexdigest(),
        "checkpoint": "673754a9b69072e6960bbf0c7ffb0f50dc5d2670", "artefacto": nombre,
        "filas": [{"fila_piloto": n, "fila_datos_dorada": i + 1, "fixture": filas[i]["ARCHIVO ORIGEN"],
                   "CLAVE_TRANSACCION": filas[i]["CLAVE TRANSACCIÓN"],
                   "cobertura": [c for c, criterio in criterios.items() if criterio(filas[i])],
                   "negativos": {c: filas[i][c] for c in ("IMPORTE", "DÉBITO", "CRÉDITO", "SALDO") if filas[i][c] and float(filas[i][c]) < 0}}
                  for n, i in enumerate(indices, 1)],
    }
    (DESTINO / "TRAZABILIDAD.json").write_text(json.dumps(trazabilidad, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trazabilidad


if __name__ == "__main__":
    print(json.dumps(preparar(), ensure_ascii=False, indent=2))
