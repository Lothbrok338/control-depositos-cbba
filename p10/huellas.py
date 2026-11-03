# -*- coding: utf-8 -*-
"""
p10/huellas.py · huellas SHA-256 de lo que NO debe cambiar sin aprobación explícita:

  * P10-A.1 CERRADO Y VALIDADO LOCALMENTE (generador histórico mensual aprobado por Gabriel): su contrato y su generador.
  * El motor y los módulos de P0/P7/P8/P9 que P10-A.2 reutiliza tal cual.

    python -m p10.huellas        # solo si el cambio fue aprobado: reescribe p10/huellas_cerradas.json
"""
import hashlib
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = Path(__file__).resolve().parent / "huellas_cerradas.json"
ARCHIVOS_A1 = ("p10/__init__.py", "p10/contrato.py", "p10/snapshot.py", "p10/generador.py", "p10/validacion.py", "p10/comparar.py",
               "p10/snapshot_simulado.py", "p10/motor_p0.py", "p10/empaque.py")
ARCHIVOS_REUTILIZADOS = ("motor_control_depositos_cbba.py", "motor_generico.py", "deteccion_registro.py", "captura_origen.py",
                         "registro_bancos.json", "adaptador_m365.py", "historico.py", "p0/api.py", "p0/nucleo.py", "p0/sedes.json",
                         "p9/contrato.py", "p9/reversion/contrato.py", "Dockerfile", "railway.json", "requirements-p0.txt")


def calcular():
    sha = lambda r: hashlib.sha256((RAIZ / r).read_bytes()).hexdigest()  # noqa: E731
    return {"a1_cerrado": {r: sha(r) for r in ARCHIVOS_A1}, "reutilizado_sin_cambios": {r: sha(r) for r in ARCHIVOS_REUTILIZADOS}}


if __name__ == "__main__":
    DESTINO.write_text(json.dumps(calcular(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(DESTINO)
