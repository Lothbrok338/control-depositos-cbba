"""
============================================================
CONTROL DE DEPÓSITOS CBBA — DETECCIÓN PRODUCTIVA POR REGISTRO (P4)
============================================================

Identifica banco, cuenta, moneda y formato de un extracto usando SOLO
`registro_bancos.json` (FORMATOS + CUENTAS). Es la detección que usa el
motor productivo (`motor_control_depositos_cbba.py`) desde P4.

Qué hace (la misma secuencia para todos los bancos, sin ramas por banco):
  1. Para cada FORMATO (en `orden_deteccion`) busca una de sus
     `hojas_aceptadas`. Un formato con `aceptado: false` presente en el
     archivo (p. ej. Unión «Últimos 12 movimientos») lo rechaza con su
     `mensaje`.
  2. Fila de encabezado = la de mayor puntaje con `encabezados.puntaje`
     (primera en empate, mismo criterio que la normalización). La `firma` se busca solo en
     la cabecera y en esa fila, nunca en los movimientos.
  3. Encabezado por debajo de `puntaje_minimo` → error con la lista de
     encabezados que faltan (no se elige un formato «parecido»).
  4. La cuenta se lee SOLO en la zona de cabecera (filas anteriores al
     encabezado de la tabla) y SOLO en la celda que sigue a una etiqueta de
     `deteccion.etiquetas_cuenta` («Cuenta:», «Nro de Cuenta:», …). Nunca se
     buscan números dentro de glosas, adicionales u originantes.
  5. La cuenta leída debe ser UNA y estar registrada en CUENTAS para ese
     formato. Cero, varias, o una no registrada → error explícito.
  6. Más de un formato que cumple firma y encabezado → AMBIGUO (error).

Qué NO hace: normalizar. La normalización (P5) la hace `motor_generico.py`
con la cuenta, la hoja y la fila de encabezado que devuelve esta detección.
P6 retiró el cruce con los normalizadores legados (`HOJAS_VALIDAS`,
`ENCABEZADOS_ESPERADOS`, `legado.plantilla_por_hoja`, `formato_legado`).

Agregar una cuenta de un formato conocido = una entrada en `CUENTAS`,
cero código.
============================================================
"""

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field


VERSION_DETECCION = "P4-1"

RUTA_REGISTRO_DEFECTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "registro_bancos.json"
)

# Un único registro para detección y normalización.
VARIABLE_REGISTRO = "CBBA_REGISTRO_BANCOS"

NO_RECONOCIDO = "NO_RECONOCIDO"

# Estados posibles de una detección.
OK = "OK"
RECHAZADO = "RECHAZADO"                        # formato explícitamente no aceptado
ENCABEZADO_INCOMPLETO = "ENCABEZADO_INCOMPLETO"
SIN_CUENTA = "SIN_CUENTA"                      # formato reconocido, sin cuenta en la cabecera
CUENTA_NO_REGISTRADA = "CUENTA_NO_REGISTRADA"
AMBIGUO = "AMBIGUO"
SIN_FORMATO = "SIN_FORMATO"                    # ninguna firma coincide

# Un número de cuenta tiene al menos estos dígitos (descarta «(Bs)», «M/N», etc.).
MIN_DIGITOS_CUENTA = 4


class RegistroDeteccionError(ValueError):
    """El registro no existe, no es JSON o no sirve para detectar."""


# ============================================================
# REGISTRO
# ============================================================

def ruta_registro(ruta=None):
    return ruta or os.environ.get(VARIABLE_REGISTRO) or RUTA_REGISTRO_DEFECTO


def clave_cuenta(texto):
    """Número de cuenta comparable: solo dígitos, sin ceros a la izquierda."""
    return re.sub(r"\D", "", str(texto)).lstrip("0")


def validar_registro_deteccion(datos):
    """Problemas del registro para DETECTAR (lista vacía = válido)."""

    p = []

    formatos = datos.get("FORMATOS")
    cuentas = datos.get("CUENTAS")

    if not isinstance(formatos, dict) or not formatos:
        return ["FORMATOS vacío o inválido"]

    if not isinstance(cuentas, list) or not cuentas:
        return ["CUENTAS vacío o inválido"]

    for fid, f in formatos.items():

        def falta(msg, fid=fid):
            p.append(f"formato {fid}: {msg}")

        if not f.get("hojas_aceptadas"):
            falta("sin hojas_aceptadas")

        if f.get("aceptado", True) is False:
            if not f.get("mensaje"):
                falta("formato no aceptado sin 'mensaje'")
            continue

        firma = f.get("firma", {})
        if not (firma.get("todas") or firma.get("alguna")):
            falta("firma vacía (todas/alguna)")

        enc = f.get("encabezados", {})
        if not enc.get("puntaje"):
            falta("encabezados.puntaje vacío")

        minimo = enc.get("puntaje_minimo")
        if not isinstance(minimo, (int, float)) or not 0 < minimo <= 1:
            falta("encabezados.puntaje_minimo debe estar en (0, 1]")

        det = f.get("deteccion", {})
        if not det.get("etiquetas_cuenta"):
            falta("deteccion.etiquetas_cuenta vacío (la cuenta debe leerse en la cabecera)")

        for regla in det.get("cabecera_prohibida", []):
            if not regla.get("contiene") or not regla.get("mensaje"):
                falta("deteccion.cabecera_prohibida requiere 'contiene' y 'mensaje'")

    ids = set()
    vistos = {}

    for c in cuentas:

        cid = c.get("id", "")

        for k in ("id", "formato", "banco", "cuenta", "moneda"):
            if not str(c.get(k, "")).strip():
                p.append(f"cuenta {cid or '?'}: falta '{k}'")

        if cid in ids:
            p.append(f"cuenta duplicada: id '{cid}'")
        ids.add(cid)

        f = formatos.get(c.get("formato"))

        if f is None:
            p.append(f"cuenta {cid}: formato inexistente '{c.get('formato')}'")
            continue

        if f.get("aceptado", True) is False:
            p.append(
                f"cuenta {cid}: el formato '{c['formato']}' no es un extracto aceptado"
            )
            continue

        if len(clave_cuenta(c.get("cuenta", ""))) < MIN_DIGITOS_CUENTA:
            p.append(f"cuenta {cid}: número de cuenta sin dígitos suficientes")

        if not c.get("activa", True):
            continue

        clave = clave_cuenta(c.get("cuenta", ""))

        if clave in vistos:
            p.append(
                f"cuenta {cid}: mismo número de cuenta que {vistos[clave]}"
            )
        else:
            vistos[clave] = cid

    return p


# ============================================================
# RESULTADO
# ============================================================

@dataclass
class ResultadoDeteccion:
    estado: str
    motivo: str = ""
    cuenta_id: str = None           # id de CUENTAS (columna FORMATO de VALIDACION)
    formato_id: str = None          # id de FORMATOS
    banco: str = None
    cuenta: str = None
    moneda: str = None
    hoja: str = None
    fila_encabezado: int = None     # índice 0 dentro de la hoja
    cuenta_leida: str = None        # texto de la celda de la cabecera
    candidatos: list = field(default_factory=list)
    observaciones: list = field(default_factory=list)

    @property
    def ok(self):
        return self.estado == OK

    @property
    def formato_motor(self):
        """Lo que devolvía `detectar_formato`: id de cuenta o NO_RECONOCIDO."""
        return self.cuenta_id if self.ok else NO_RECONOCIDO

    def como_dict(self):
        return {
            "ESTADO": self.estado,
            "MOTIVO": self.motivo,
            "CUENTA_ID": self.cuenta_id,
            "FORMATO_REGISTRO": self.formato_id,
            "BANCO": self.banco,
            "CUENTA": self.cuenta,
            "MONEDA": self.moneda,
            "HOJA": self.hoja,
            "FILA_ENCABEZADO": (
                None if self.fila_encabezado is None
                else int(self.fila_encabezado) + 1
            ),
            "CUENTA_LEIDA": self.cuenta_leida,
            "CANDIDATOS": list(self.candidatos),
            "OBSERVACIONES": list(self.observaciones),
        }


# ============================================================
# DETECTOR
# ============================================================

class DetectorRegistro:
    """
    `normalizar_texto` y `leer_todas_hojas` son las primitivas del motor
    (mismo criterio de texto y mismo lector robusto que la normalización).
    """

    def __init__(self, datos, normalizar_texto, leer_todas_hojas,
                 ruta=None, sha256=None):

        self.datos = datos
        self._norm = normalizar_texto
        self._leer = leer_todas_hojas
        self.ruta = ruta
        self.sha256 = sha256

        problemas = validar_registro_deteccion(datos)

        if problemas:
            raise RegistroDeteccionError(
                f"registro de bancos inválido ({ruta or 'en memoria'}): "
                + "; ".join(problemas)
            )

    @classmethod
    def cargar(cls, normalizar_texto, leer_todas_hojas, ruta=None):

        ruta = ruta_registro(ruta)

        try:
            with open(ruta, "rb") as f:
                crudo = f.read()
        except OSError as e:
            raise RegistroDeteccionError(
                f"no se pudo leer el registro de bancos '{ruta}': {e}"
            )

        try:
            datos = json.loads(crudo.decode("utf-8"))
        except ValueError as e:
            raise RegistroDeteccionError(
                f"el registro de bancos no es JSON válido ({ruta}): {e}"
            )

        return cls(
            datos, normalizar_texto, leer_todas_hojas, ruta=ruta,
            sha256=hashlib.sha256(crudo).hexdigest()
        )

    # -- acceso ---------------------------------------------------

    @property
    def version(self):
        return self.datos.get("version_deteccion", "")

    def formatos_en_orden(self):
        return sorted(
            self.datos["FORMATOS"].items(),
            key=lambda kv: (kv[1].get("orden_deteccion", 1000), kv[0])
        )

    def cuentas_activas_de(self, formato_id):
        return [
            c for c in self.datos["CUENTAS"]
            if c.get("formato") == formato_id and c.get("activa", True)
        ]

    def cuenta(self, cuenta_id):
        for c in self.datos["CUENTAS"]:
            if c["id"] == cuenta_id:
                return c
        raise KeyError(f"Cuenta no registrada: {cuenta_id}")

    # -- utilidades -----------------------------------------------

    @staticmethod
    def _texto_celda(valor):
        if valor is None:
            return ""
        if isinstance(valor, float):
            if math.isnan(valor):
                return ""
            if valor.is_integer():
                return str(int(valor))
        return str(valor)

    def _texto_filas(self, raw, hasta):
        """Texto normalizado de las filas [0, hasta) — nunca los datos."""
        zona = raw.iloc[:hasta]
        return self._norm(
            " ".join(
                self._texto_celda(v)
                for v in zona.values.flatten()
            )
        )

    def _fila_encabezado(self, raw, esperados):
        """Mayor puntaje, primera fila en empate."""

        esperados_norm = [self._norm(e) for e in esperados]

        mejor_fila, mejor_puntaje, mejor_texto = None, -1, ""

        for pos in range(len(raw)):

            texto = self._norm(
                " | ".join(
                    self._texto_celda(v) for v in raw.iloc[pos].tolist()
                )
            )

            puntaje = sum(1 for e in esperados_norm if e in texto)

            if puntaje > mejor_puntaje:
                mejor_fila, mejor_puntaje, mejor_texto = pos, puntaje, texto

        faltan = [
            e for e, en in zip(esperados, esperados_norm)
            if en not in mejor_texto
        ]

        return mejor_fila, mejor_puntaje, len(esperados_norm), faltan

    def _leer_cuentas(self, raw, fila_encabezado, etiquetas):
        """
        Celdas de cuenta de la cabecera: el valor que sigue (misma fila, a la
        derecha) a una etiqueta exacta, o el resto de la celda «ETIQUETA: n».
        """

        etiquetas = [self._norm(e).rstrip(":").strip() for e in etiquetas]
        hallazgos = []

        for pos in range(fila_encabezado):

            valores = raw.iloc[pos].tolist()

            for j, v in enumerate(valores):

                t = self._norm(self._texto_celda(v))

                if not t:
                    continue

                base = t.rstrip(":").strip()
                valor = None

                if base in etiquetas:
                    for w in valores[j + 1:]:
                        if self._norm(self._texto_celda(w)):
                            valor = self._texto_celda(w).strip()
                            break
                else:
                    for e in etiquetas:
                        if t.startswith(e + ":") and t[len(e) + 1:].strip():
                            valor = self._texto_celda(v).split(":", 1)[1].strip()
                            break

                if valor is not None:
                    hallazgos.append((pos, j, valor))

        return hallazgos

    @staticmethod
    def _numeros(texto):
        return [
            clave_cuenta(t)
            for t in re.findall(r"[0-9][0-9\-]*[0-9]", texto)
            if len(clave_cuenta(t)) >= MIN_DIGITOS_CUENTA
        ]

    # -- detección ------------------------------------------------

    def detectar(self, ruta, hojas=None):

        if hojas is None:
            hojas = self._leer(ruta)

        rechazos = []
        incompletos = []
        reconocidos = []            # (fid, fmt, hoja, raw, fila)

        for fid, fmt in self.formatos_en_orden():

            hoja = next(
                (h for h in fmt.get("hojas_aceptadas", []) if h in hojas),
                None
            )

            if hoja is None:
                continue

            if fmt.get("aceptado", True) is False:
                rechazos.append(f"{fmt['mensaje']} (hoja '{hoja}')")
                continue

            raw = hojas[hoja]

            if raw.empty:
                continue

            fila, puntaje, total, faltan = self._fila_encabezado(
                raw, fmt["encabezados"]["puntaje"]
            )

            zona_firma = self._texto_filas(raw, fila + 1)
            firma = fmt["firma"]

            if firma.get("todas") and not all(
                self._norm(s) in zona_firma for s in firma["todas"]
            ):
                continue

            if firma.get("alguna") and not any(
                self._norm(s) in zona_firma for s in firma["alguna"]
            ):
                continue

            if puntaje < fmt["encabezados"]["puntaje_minimo"] * total:
                incompletos.append(
                    f"formato {fid}: encabezado incompleto en la hoja "
                    f"'{hoja}' ({puntaje}/{total}); faltan: "
                    + ", ".join(faltan)
                )
                continue

            cabecera = self._texto_filas(raw, fila)
            prohibida = next(
                (
                    r for r in fmt.get("deteccion", {}).get("cabecera_prohibida", [])
                    if self._norm(r["contiene"]) in cabecera
                ),
                None
            )

            if prohibida is not None:
                rechazos.append(f"formato {fid}: {prohibida['mensaje']}")
                continue

            reconocidos.append((fid, fmt, hoja, raw, fila))

        if len(reconocidos) > 1:
            return ResultadoDeteccion(
                AMBIGUO,
                motivo=(
                    "la cabecera cumple firma y encabezado de más de un "
                    "formato: " + ", ".join(
                        f"{r[0]} (hoja '{r[2]}')" for r in reconocidos
                    )
                ),
                candidatos=[r[0] for r in reconocidos],
            )

        if not reconocidos:

            if incompletos:
                return ResultadoDeteccion(
                    ENCABEZADO_INCOMPLETO, motivo="; ".join(incompletos)
                )

            if rechazos:
                return ResultadoDeteccion(
                    RECHAZADO, motivo="; ".join(rechazos)
                )

            return ResultadoDeteccion(
                SIN_FORMATO,
                motivo=(
                    "ninguna firma de encabezado del registro coincide "
                    f"(hojas del archivo: {list(hojas)})"
                ),
            )

        fid, fmt, hoja, raw, fila = reconocidos[0]
        observaciones = incompletos + rechazos

        base = dict(
            formato_id=fid, hoja=hoja, fila_encabezado=fila,
            observaciones=observaciones
        )

        etiquetas = fmt["deteccion"]["etiquetas_cuenta"]
        hallazgos = self._leer_cuentas(raw, fila, etiquetas)

        if not hallazgos:
            return ResultadoDeteccion(
                SIN_CUENTA,
                motivo=(
                    f"formato {fid} reconocido, pero la cabecera de la hoja "
                    f"'{hoja}' no trae el número de cuenta (etiquetas "
                    f"esperadas: {etiquetas})"
                ),
                **base
            )

        leidos = []
        for _, _, valor in hallazgos:
            for n in self._numeros(valor):
                if n not in leidos:
                    leidos.append(n)

        texto_leido = " | ".join(v for _, _, v in hallazgos)
        base["cuenta_leida"] = texto_leido

        if not leidos:
            return ResultadoDeteccion(
                SIN_CUENTA,
                motivo=(
                    f"formato {fid} reconocido, pero la celda de cuenta de la "
                    f"cabecera no contiene un número de cuenta: '{texto_leido}'"
                ),
                **base
            )

        registradas = {
            clave_cuenta(c["cuenta"]): c for c in self.cuentas_activas_de(fid)
        }

        coinciden = [registradas[n]["id"] for n in leidos if n in registradas]

        if len(leidos) > 1:
            return ResultadoDeteccion(
                AMBIGUO,
                motivo=(
                    f"la cabecera ({fid}) trae más de un número de cuenta: "
                    f"'{texto_leido}'"
                    + (
                        f"; registradas: {', '.join(coinciden)}"
                        if coinciden else ""
                    )
                ),
                candidatos=coinciden,
                **base
            )

        if not coinciden:

            otras = [
                c["id"] for c in self.datos["CUENTAS"]
                if clave_cuenta(c["cuenta"]) == leidos[0]
            ]

            return ResultadoDeteccion(
                CUENTA_NO_REGISTRADA,
                motivo=(
                    f"formato {fid} reconocido, pero la cuenta '{texto_leido}' "
                    "de la cabecera no está registrada para ese formato"
                    + (
                        f" (sí figura como {', '.join(otras)} de otro formato)"
                        if otras else
                        ": agregarla en CUENTAS de registro_bancos.json"
                    )
                ),
                **base
            )

        cuenta = self.cuenta(coinciden[0])

        return ResultadoDeteccion(
            OK,
            cuenta_id=cuenta["id"],
            banco=cuenta["banco"],
            cuenta=cuenta["cuenta"],
            moneda=cuenta["moneda"],
            candidatos=coinciden,
            **base
        )
