"""
============================================================
CONTROL DE DEPÓSITOS CBBA — MOTOR GENÉRICO (P3, MODO SOMBRA)
============================================================

Motor dirigido por `registro_bancos.json`: la misma secuencia para todos
los bancos, sin ramas por banco. Detecta el formato y la cuenta, lee la
tabla de movimientos, la mapea a las 26 `COLUMNAS_LISTS` y valida saldos
usando SOLO la configuración del registro.

ESTADO: SOMBRA. Este módulo NUNCA produce salida productiva.
  * La salida productiva (NORMALIZADO.xlsx, LISTS.csv) es exclusivamente
    la del motor legado (`motor_control_depositos_cbba.py`).
  * Este motor corre en paralelo, compara su resultado contra el del
    legado (detección, movimientos normalizados y validación de saldos)
    y REPORTA cada diferencia en `SOMBRA_REPORTE.json` y
    `SOMBRA_DIFERENCIAS.csv`. Una diferencia no altera la producción.
  * Ningún error de este módulo debe detener ni cambiar al motor legado.

Qué reutiliza del legado (solo primitivas sin lógica bancaria, y sin
modificarlas): conversión de números/fechas/horas/códigos, lector de
Excel robusto, búsqueda difusa de columnas y `finalizar_dataframe`
(que fija `COLUMNAS_LISTS` y `CLAVE TRANSACCIÓN`, congeladas).

Qué NO usa del legado (lo reimplementa desde el registro, para que la
comparación tenga sentido): `detectar_formato`, `ENCABEZADOS_ESPERADOS`,
`HOJAS_VALIDAS`, `encontrar_fila_encabezado`, `leer_tabla_movimientos`,
todos los `normalizar_*` y `validar_archivo`.

Agregar una cuenta nueva de un formato ya conocido = una entrada en
`CUENTAS` del registro; cero código (ver `Registro.con_cuenta`).

Uso como módulo (dentro del motor legado, ya integrado):
    from motor_generico import ejecutar_sombra_produccion

Uso como script (compara la carpeta contra el legado, sin escribir
NORMALIZADO.xlsx ni LISTS.csv):
    python motor_generico.py <carpeta_entrada> [<carpeta_reporte>]
============================================================
"""

import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import types
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


VERSION_MOTOR_GENERICO = "P3-sombra-1"

RUTA_REGISTRO_DEFECTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "registro_bancos.json"
)

NOMBRE_REPORTE_JSON = "SOMBRA_REPORTE.json"
NOMBRE_REPORTE_CSV = "SOMBRA_DIFERENCIAS.csv"

# Primitivas del legado que este módulo consume. Sin lógica bancaria.
PRIMITIVAS_LEGADO = (
    "COLUMNAS_LISTS",
    "normalizar_texto",
    "buscar_columna",
    "buscar_columna_opcional",
    "numero",
    "codigo_texto",
    "normalizar_fecha",
    "normalizar_hora",
    "leer_excel_robusto",
    "leer_todas_hojas",
    "finalizar_dataframe",
    "ecuacion_saldo",
    "extraer_nombre_bnb",
)

FILTROS_FECHA = ("PANDAS_DAYFIRST", "NORMALIZAR_FECHA")
MODOS_IMPORTE = ("DEBITO_CREDITO", "SIGNO")
ESTRATEGIAS_DEPOSITANTE = ("VACIO", "COLUMNA", "legacy_bnb")
FUENTES_SALDO_INICIAL = ("RECONSTRUIDO", "CELDA_FIJA", "ETIQUETA", "FILA_ROTULADA")
FUENTES_SALDO_FINAL = ("ULTIMA_FILA", "ETIQUETA", "FILA_ROTULADA")
ROLES_OBLIGATORIOS = (
    "FECHA", "HORA", "DESCRIPCION", "CODIGO_ASIGNACION", "SALDO"
)


# ============================================================
# ACCESO AL MOTOR LEGADO (solo primitivas)
# ============================================================

def namespace_legado(origen):
    """
    Devuelve un objeto con las primitivas del legado. `origen` puede ser
    el módulo del motor legado, un diccionario (p. ej. `globals()`) o un
    namespace. Falla con un mensaje claro si falta alguna primitiva.
    """

    if isinstance(origen, dict):
        origen = types.SimpleNamespace(**origen)

    faltan = [
        p for p in PRIMITIVAS_LEGADO
        if not hasattr(origen, p)
    ]

    if faltan:
        raise RuntimeError(
            "El motor legado no expone las primitivas requeridas: "
            f"{faltan}"
        )

    return origen


def cargar_legado(ruta=None):
    """Carga el motor legado desde su archivo (por defecto, el hermano)."""

    if ruta is None:
        ruta = os.environ.get(
            "MOTOR_PATH",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "motor_control_depositos_cbba.py"
            )
        )

    spec = importlib.util.spec_from_file_location(
        "motor_legado_sombra",
        ruta
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    return modulo


# ============================================================
# REGISTRO
# ============================================================

class RegistroError(ValueError):
    pass


class Registro:
    """Registro de bancos: FORMATOS (estructura) y CUENTAS (instancias)."""

    def __init__(self, datos, ruta=None, sha256=None):
        self.datos = datos
        self.ruta = ruta
        self.sha256 = sha256

    # -- carga --------------------------------------------------

    @classmethod
    def cargar(cls, ruta=None):

        ruta = ruta or RUTA_REGISTRO_DEFECTO

        with open(ruta, "rb") as f:
            crudo = f.read()

        try:
            datos = json.loads(crudo.decode("utf-8"))
        except ValueError as e:
            raise RegistroError(
                f"El registro no es JSON válido ({ruta}): {e}"
            )

        return cls(
            datos,
            ruta=ruta,
            sha256=hashlib.sha256(crudo).hexdigest()
        )

    # -- acceso -------------------------------------------------

    @property
    def version(self):
        return self.datos.get("version_registro", "")

    @property
    def formatos(self):
        return self.datos.get("FORMATOS", {})

    @property
    def cuentas(self):
        return self.datos.get("CUENTAS", [])

    def formato(self, formato_id):
        return self.formatos[formato_id]

    def cuenta(self, cuenta_id):

        for c in self.cuentas:
            if c["id"] == cuenta_id:
                return c

        raise KeyError(f"Cuenta no registrada: {cuenta_id}")

    def cuentas_activas_de(self, formato_id):
        return [
            c for c in self.cuentas
            if c.get("formato") == formato_id
            and c.get("activa", True)
        ]

    def formatos_en_orden(self):
        return sorted(
            self.formatos.items(),
            key=lambda kv: (
                kv[1].get("orden_deteccion", 1000),
                kv[0]
            )
        )

    # -- configuración sin código ------------------------------

    def con_cuenta(self, id, formato, banco, cuenta, moneda, activa=True):
        """
        Devuelve una COPIA del registro con una cuenta nueva. Es la
        operación «agregar una cuenta de un formato conocido»: solo
        configuración, sin lógica bancaria nueva.
        """

        nuevo = copy.deepcopy(self.datos)

        nuevo["CUENTAS"].append({
            "id": id,
            "formato": formato,
            "banco": banco,
            "cuenta": cuenta,
            "moneda": moneda,
            "activa": activa
        })

        reg = Registro(nuevo, ruta=self.ruta)

        problemas = reg.validar()

        if problemas:
            raise RegistroError(
                "La cuenta nueva deja el registro inválido: "
                + "; ".join(problemas)
            )

        return reg

    # -- CAMPO_CANONICO ----------------------------------------

    def campo_canonico(self, formato_id, encabezado_original, normalizar):
        """
        Etiqueta común del encabezado original de un banco (p. ej.
        «Referencia» → REFERENCIA), o "" si el registro no lo conoce.
        `normalizar` es la función de normalización de texto del legado.
        """

        fmt = self.formatos.get(formato_id, {})

        clave = normalizar(encabezado_original)

        for original, canonico in fmt.get("campos_canonicos", {}).items():
            if normalizar(original) == clave:
                return canonico

        return ""

    # -- validación --------------------------------------------

    def validar(self):
        """Devuelve la lista de problemas del registro (vacía = válido)."""

        p = []

        if not self.version:
            p.append("falta version_registro")

        if not isinstance(self.formatos, dict) or not self.formatos:
            p.append("FORMATOS vacío o inválido")

        if not isinstance(self.cuentas, list) or not self.cuentas:
            p.append("CUENTAS vacío o inválido")

        for fid, f in self.formatos.items():
            p.extend(self._validar_formato(fid, f))

        ids = set()
        vistos = {}

        for c in self.cuentas:

            cid = c.get("id", "")

            for k in ("id", "formato", "banco", "cuenta", "moneda"):
                if not str(c.get(k, "")).strip():
                    p.append(f"cuenta {cid or '?'}: falta '{k}'")

            if cid in ids:
                p.append(f"cuenta duplicada: id '{cid}'")
            ids.add(cid)

            fmt = self.formatos.get(c.get("formato"))

            if fmt is None:
                p.append(
                    f"cuenta {cid}: formato inexistente "
                    f"'{c.get('formato')}'"
                )
                continue

            if fmt.get("aceptado", True) is False:
                p.append(
                    f"cuenta {cid}: el formato '{c['formato']}' "
                    "no es un extracto aceptado"
                )

            if c.get("activa", True):

                clave = (
                    c.get("formato"),
                    str(c.get("cuenta", "")).strip()
                )

                if clave in vistos:
                    p.append(
                        f"cuenta {cid}: mismo formato y número de "
                        f"cuenta que {vistos[clave]}"
                    )
                else:
                    vistos[clave] = cid

        # Una cuenta contenida en otra del mismo formato haría la
        # detección ambigua.
        for fid in self.formatos:

            numeros = [
                (c["id"], str(c["cuenta"]).strip())
                for c in self.cuentas_activas_de(fid)
                if str(c.get("cuenta", "")).strip()
            ]

            for i, (id_a, a) in enumerate(numeros):
                for id_b, b in numeros[i + 1:]:
                    if a != b and (a in b or b in a):
                        p.append(
                            f"cuentas {id_a} y {id_b}: un número "
                            "contiene al otro (detección ambigua)"
                        )

        return p

    @staticmethod
    def _validar_formato(fid, f):

        p = []

        def falta(msg):
            p.append(f"formato {fid}: {msg}")

        if not f.get("hojas_aceptadas"):
            falta("sin hojas_aceptadas")

        if f.get("aceptado", True) is False:

            if not f.get("mensaje"):
                falta("formato no aceptado sin 'mensaje'")

            return p

        firma = f.get("firma", {})

        if not (firma.get("todas") or firma.get("alguna")):
            falta("firma vacía (todas/alguna)")

        enc = f.get("encabezados", {})

        if not enc.get("puntaje"):
            falta("encabezados.puntaje vacío")

        minimo = enc.get("puntaje_minimo")

        if not isinstance(minimo, (int, float)) or not 0 < minimo <= 1:
            falta("encabezados.puntaje_minimo debe estar en (0, 1]")

        if f.get("filtro_fecha") not in FILTROS_FECHA:
            falta(f"filtro_fecha debe ser uno de {FILTROS_FECHA}")

        if f.get("sin_columna_fecha") not in ("ERROR", "SIN_MOVIMIENTOS"):
            falta("sin_columna_fecha inválido")

        campos = f.get("campos", {})

        for rol in ROLES_OBLIGATORIOS:

            cfg = campos.get(rol)

            if cfg is None:
                falta(f"falta el campo '{rol}'")
            elif not (cfg.get("alias") or "constante" in cfg):
                falta(f"campo '{rol}' sin alias ni constante")

        for rol, cfg in campos.items():
            if not (cfg.get("alias") or "constante" in cfg):
                falta(f"campo '{rol}' sin alias ni constante")

        imp = f.get("importe", {})

        if imp.get("modo") not in MODOS_IMPORTE:
            falta(f"importe.modo debe ser uno de {MODOS_IMPORTE}")
        elif imp["modo"] == "DEBITO_CREDITO":
            for rol in ("DEBITO", "CREDITO"):
                if rol not in campos:
                    falta(f"importe DEBITO_CREDITO requiere '{rol}'")
        elif imp.get("campo") not in campos:
            falta("importe SIGNO requiere 'campo' existente en campos")

        dep = f.get("depositante", {})

        if dep.get("estrategia") not in ESTRATEGIAS_DEPOSITANTE:
            falta(
                "depositante.estrategia debe ser uno de "
                f"{ESTRATEGIAS_DEPOSITANTE}"
            )
        elif dep["estrategia"] != "VACIO" and dep.get("campo") not in campos:
            falta("depositante.campo no existe en campos")

        info = f.get("info_adicional", {})

        if not isinstance(info.get("separador"), str):
            falta("info_adicional.separador requerido")

        for parte in info.get("partes", []):
            if parte.get("campo") not in campos:
                falta(
                    "info_adicional: campo inexistente "
                    f"'{parte.get('campo')}'"
                )

        for regla in f.get("filas_excluir", []):
            if regla.get("campo") not in campos:
                falta("filas_excluir: campo inexistente")
            if not regla.get("contiene_alguna"):
                falta("filas_excluir: falta contiene_alguna")

        saldo = f.get("saldo", {})

        if saldo.get("orden") not in ("ARCHIVO", "CRONOLOGICO"):
            falta("saldo.orden debe ser ARCHIVO o CRONOLOGICO")

        if saldo.get("inicial", {}).get("fuente") not in FUENTES_SALDO_INICIAL:
            falta(f"saldo.inicial.fuente debe ser uno de {FUENTES_SALDO_INICIAL}")

        if saldo.get("final", {}).get("fuente") not in FUENTES_SALDO_FINAL:
            falta(f"saldo.final.fuente debe ser uno de {FUENTES_SALDO_FINAL}")

        for etapa in ("inicial", "final"):

            cfg = saldo.get(etapa, {})

            if cfg.get("fuente") == "FILA_ROTULADA":

                for k in ("campo_rotulo", "rotulo", "campo_valor"):
                    if not cfg.get(k):
                        falta(f"saldo.{etapa} FILA_ROTULADA sin '{k}'")

                for k in ("campo_rotulo", "campo_valor"):
                    if cfg.get(k) and cfg[k] not in campos:
                        falta(f"saldo.{etapa}.{k} inexistente en campos")

            if cfg.get("fuente") == "CELDA_FIJA":
                if not (cfg.get("fila", 0) >= 1 and cfg.get("columna", 0) >= 1):
                    falta(f"saldo.{etapa} CELDA_FIJA requiere fila/columna >= 1")

            if cfg.get("fuente") == "ETIQUETA" and not cfg.get("etiqueta"):
                falta(f"saldo.{etapa} ETIQUETA sin 'etiqueta'")

        return p


# ============================================================
# RESULTADOS
# ============================================================

@dataclass
class Deteccion:
    estado: str                      # OK | NO_RECONOCIDO | AMBIGUO
    cuenta_id: str = None
    formato_id: str = None
    motivo: str = ""
    candidatos: list = field(default_factory=list)


@dataclass
class ResultadoGenerico:
    deteccion: Deteccion
    df: pd.DataFrame = None
    validacion: dict = None
    identidad: dict = None           # BANCO / CUENTA / MONEDA del registro
    sin_movimientos: bool = False


# ============================================================
# MOTOR GENÉRICO
# ============================================================

class MotorGenerico:
    """Detecta, normaliza y valida usando únicamente el registro."""

    def __init__(self, registro, legado):

        self.registro = registro
        self.L = namespace_legado(legado)

    # -- utilidades ---------------------------------------------

    def _norm(self, valor):
        return self.L.normalizar_texto(valor)

    @staticmethod
    def _hoja_aceptada(hojas, fmt):

        for nombre in fmt.get("hojas_aceptadas", []):
            if nombre in hojas:
                return nombre

        return None

    def _fila_encabezado(self, raw, esperados):
        """
        Fila del encabezado = la de mayor puntaje (primera en empate),
        igual que el criterio del legado, con la lista del registro.
        """

        esperados_norm = [self._norm(e) for e in esperados]

        mejor_fila = None
        mejor_puntaje = -1

        for idx, fila in raw.iterrows():

            texto = self._norm(
                " | ".join(
                    fila.fillna("").astype(str).tolist()
                )
            )

            puntaje = sum(
                1 for e in esperados_norm if e in texto
            )

            if puntaje > mejor_puntaje:
                mejor_fila = idx
                mejor_puntaje = puntaje

        return mejor_fila, mejor_puntaje, len(esperados_norm)

    def _zona_cabecera(self, raw, fila):
        """Texto de la cabecera y el encabezado (nunca los datos)."""

        zona = raw.iloc[: raw.index.get_loc(fila) + 1]

        return self._norm(
            " ".join(
                zona.fillna("").astype(str).values.flatten()
            )
        )

    # -- 1. DETECCIÓN -------------------------------------------

    def detectar(self, ruta, hojas=None):
        """
        Firma → formato → cuenta leída en la cabecera → cuenta registrada.
        Una sola coincidencia = OK. Formato conocido con cuenta no
        registrada = NO_RECONOCIDO con motivo explícito. Más de una
        coincidencia = AMBIGUO.
        """

        if hojas is None:
            hojas = self.L.leer_todas_hojas(ruta)

        candidatos = []
        formatos_reconocidos = []
        rechazos = []

        for fid, fmt in self.registro.formatos_en_orden():

            hoja = self._hoja_aceptada(hojas, fmt)

            if hoja is None:
                continue

            if fmt.get("aceptado", True) is False:
                rechazos.append(fmt["mensaje"])
                continue

            raw = hojas[hoja]

            if raw.empty:
                continue

            fila, puntaje, total = self._fila_encabezado(
                raw,
                fmt["encabezados"]["puntaje"]
            )

            zona = self._zona_cabecera(raw, fila)

            firma = fmt["firma"]

            cumple = True

            if firma.get("todas"):
                cumple = cumple and all(
                    self._norm(s) in zona for s in firma["todas"]
                )

            if firma.get("alguna"):
                cumple = cumple and any(
                    self._norm(s) in zona for s in firma["alguna"]
                )

            if not cumple:
                continue

            if puntaje / total < fmt["encabezados"]["puntaje_minimo"]:
                rechazos.append(
                    f"formato {fid}: encabezado incompleto "
                    f"({puntaje}/{total})"
                )
                continue

            formatos_reconocidos.append(fid)

            for c in self.registro.cuentas_activas_de(fid):

                if self._norm(c["cuenta"]) in zona:
                    candidatos.append(c["id"])

        if len(candidatos) == 1:

            cuenta = self.registro.cuenta(candidatos[0])

            return Deteccion(
                "OK",
                cuenta_id=cuenta["id"],
                formato_id=cuenta["formato"],
                candidatos=list(candidatos)
            )

        if len(candidatos) > 1:

            return Deteccion(
                "AMBIGUO",
                motivo=(
                    "más de una cuenta coincide en la cabecera: "
                    + ", ".join(candidatos)
                ),
                candidatos=list(candidatos)
            )

        if formatos_reconocidos:

            return Deteccion(
                "NO_RECONOCIDO",
                formato_id=formatos_reconocidos[0],
                motivo=(
                    f"formato {', '.join(formatos_reconocidos)} "
                    "reconocido, cuenta no registrada"
                )
            )

        if rechazos:

            return Deteccion(
                "NO_RECONOCIDO",
                motivo="; ".join(rechazos)
            )

        return Deteccion(
            "NO_RECONOCIDO",
            motivo="ninguna firma del registro coincide"
        )

    # -- 2. TABLA DE MOVIMIENTOS ---------------------------------

    def _leer_tabla(self, ruta, fmt, hojas):
        """Devuelve (hoja, raw, fila_encabezado, tabla) del formato."""

        hoja = self._hoja_aceptada(hojas, fmt)

        if hoja is None:
            raise ValueError(
                "El archivo no tiene ninguna de las hojas aceptadas "
                f"{fmt.get('hojas_aceptadas')}: {list(hojas)}"
            )

        raw = hojas[hoja]

        fila, _, _ = self._fila_encabezado(
            raw,
            fmt["encabezados"]["puntaje"]
        )

        tabla = self.L.leer_excel_robusto(
            ruta,
            sheet_name=hoja,
            header=fila
        )

        tabla = tabla.dropna(axis=1, how="all")

        tabla.columns = [
            re.sub(r"\s+", " ", str(c)).strip()
            for c in tabla.columns
        ]

        return hoja, raw, fila, tabla

    def _resolver_columnas(self, tabla, fmt):
        """rol → nombre de columna real (o None). Falla si falta un requerido."""

        cols = {}

        for rol, cfg in fmt["campos"].items():

            if "constante" in cfg:
                cols[rol] = None
                continue

            buscar = (
                self.L.buscar_columna
                if cfg.get("requerido", False)
                else self.L.buscar_columna_opcional
            )

            cols[rol] = buscar(tabla, *cfg["alias"])

        return cols

    # -- 3. NORMALIZACIÓN ---------------------------------------

    def identidad(self, cuenta_id):
        """BANCO / CUENTA / MONEDA del registro (también sin movimientos)."""

        c = self.registro.cuenta(cuenta_id)

        return {
            "BANCO": c["banco"],
            "CUENTA BANCARIA": c["cuenta"],
            "MONEDA": c["moneda"],
            "CUENTA_ID": c["id"],
            "FORMATO_ID": c["formato"]
        }

    def normalizar(
        self,
        ruta,
        cuenta_id,
        lote,
        fecha_carga,
        nombre_origen=None,
        hojas=None
    ):
        """
        Devuelve (df, contexto). `df` tiene las 26 COLUMNAS_LISTS y, para
        un extracto válido sin movimientos, es un DataFrame vacío (igual
        que el legado); su identidad completa va en `contexto`.
        """

        L = self.L

        cuenta = self.registro.cuenta(cuenta_id)
        fmt = self.registro.formato(cuenta["formato"])

        if hojas is None:
            hojas = L.leer_todas_hojas(ruta)

        hoja, raw, fila, tabla = self._leer_tabla(ruta, fmt, hojas)

        contexto = {
            "hoja": hoja,
            "raw": raw,
            "fila_encabezado": fila,
            "tabla": tabla,
            "identidad": self.identidad(cuenta_id),
            "sin_movimientos": False
        }

        campos = fmt["campos"]

        # Columna de fecha: opcional solo si el registro lo declara.
        if (
            fmt["sin_columna_fecha"] == "SIN_MOVIMIENTOS"
            and L.buscar_columna_opcional(
                tabla,
                *campos["FECHA"]["alias"]
            ) is None
        ):

            contexto["sin_movimientos"] = True

            return (
                pd.DataFrame(columns=L.COLUMNAS_LISTS),
                contexto
            )

        cols = self._resolver_columnas(tabla, fmt)

        df = tabla

        # Filas que no son movimientos (p. ej. SALDO INICIAL / AL CIERRE).
        for regla in fmt.get("filas_excluir", []):

            texto = (
                df[cols[regla["campo"]]]
                .fillna("")
                .astype(str)
                .str.upper()
            )

            excluir = pd.Series(False, index=df.index)

            for marca in regla["contiene_alguna"]:
                excluir = excluir | texto.str.contains(
                    marca.upper(),
                    na=False,
                    regex=False
                )

            df = df[~excluir].copy()

        # Solo son movimientos las filas con fecha interpretable.
        cf = cols["FECHA"]

        if fmt["filtro_fecha"] == "NORMALIZAR_FECHA":
            fechas = df[cf].apply(L.normalizar_fecha)
        else:
            fechas = pd.to_datetime(
                df[cf],
                dayfirst=True,
                errors="coerce"
            )

        df = df[fechas.notna()].copy()

        salida = pd.DataFrame(index=df.index)

        salida["BANCO"] = cuenta["banco"]
        salida["CUENTA BANCARIA"] = cuenta["cuenta"]
        salida["MONEDA"] = cuenta["moneda"]

        salida["FECHA MOVIMIENTO"] = df[cf].apply(L.normalizar_fecha)

        salida["HORA MOVIMIENTO"] = (
            df[cols["HORA"]].apply(L.normalizar_hora)
            if cols["HORA"] is not None
            else campos["HORA"].get("constante", "")
        )

        # -- importes -------------------------------------------

        if fmt["importe"]["modo"] == "DEBITO_CREDITO":

            cdeb, ccre = cols["DEBITO"], cols["CREDITO"]

            salida["DÉBITO"] = (
                df[cdeb].apply(L.numero)
                if cdeb is not None
                else np.nan
            )

            salida["CRÉDITO"] = (
                df[ccre].apply(L.numero)
                if ccre is not None
                else np.nan
            )

            salida["IMPORTE"] = (
                salida["CRÉDITO"]
                .fillna(salida["DÉBITO"])
                .abs()
            )

            salida["TIPO MOVIMIENTO"] = np.select(
                [
                    salida["CRÉDITO"].notna(),
                    salida["DÉBITO"].notna()
                ],
                ["CRÉDITO", "DÉBITO"],
                default=""
            )

        else:

            monto = df[cols[fmt["importe"]["campo"]]].apply(L.numero)

            salida["IMPORTE"] = monto.abs()
            salida["CRÉDITO"] = monto.where(monto > 0)
            salida["DÉBITO"] = (-monto).where(monto < 0)

            salida["TIPO MOVIMIENTO"] = np.select(
                [monto > 0, monto < 0],
                ["CRÉDITO", "DÉBITO"],
                default=""
            )

        salida["SALDO"] = df[cols["SALDO"]].apply(L.numero)

        salida["DESCRIPCIÓN"] = (
            df[cols["DESCRIPCION"]].fillna("").astype(str)
        )

        # -- depositante ----------------------------------------

        dep = fmt["depositante"]
        col_dep = cols.get(dep.get("campo"))

        if dep["estrategia"] == "legacy_bnb":
            salida["DEPOSITANTE / ORIGINANTE"] = (
                df[col_dep].apply(L.extraer_nombre_bnb)
            )
        elif dep["estrategia"] == "COLUMNA":
            salida["DEPOSITANTE / ORIGINANTE"] = (
                df[col_dep].fillna("").astype(str)
                if col_dep is not None
                else ""
            )
        else:
            salida["DEPOSITANTE / ORIGINANTE"] = ""

        # -- información adicional ------------------------------

        info_cfg = fmt["info_adicional"]

        partes = []

        for parte in info_cfg["partes"]:

            col = cols.get(parte["campo"])

            if col is None:
                continue

            valor = df[col].fillna("").astype(str)

            if parte.get("etiqueta"):
                valor = parte["etiqueta"] + ": " + valor

            partes.append(valor)

        if partes:

            info = partes[0]

            for parte in partes[1:]:
                info = info + info_cfg["separador"] + parte

            salida["INFORMACIÓN ADICIONAL"] = info

        else:

            salida["INFORMACIÓN ADICIONAL"] = ""

        salida["CÓDIGO DE ASIGNACIÓN"] = (
            df[cols["CODIGO_ASIGNACION"]].apply(L.codigo_texto)
        )

        resultado = L.finalizar_dataframe(
            salida,
            ruta,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen
        )

        return resultado, contexto

    # -- 4. VALIDACIÓN DE SALDOS --------------------------------

    def _saldo_por_etiqueta(self, raw, etiqueta):

        L = self.L

        objetivo = L.normalizar_texto(etiqueta)

        for _, fila in raw.iterrows():

            valores = fila.tolist()

            for posicion, valor in enumerate(valores):

                if objetivo in L.normalizar_texto(valor):

                    for candidato in valores[posicion + 1:]:

                        numero = L.numero(candidato)

                        if pd.notna(numero):
                            return numero

        return np.nan

    def _saldo_fila_rotulada(self, tabla, cols, cfg, ultima):
        """Saldo tomado de una fila rotulada (p. ej. «SALDO INICIAL» de BCP)."""

        rotulo = (
            tabla[cols[cfg["campo_rotulo"]]]
            .fillna("")
            .astype(str)
            .str.upper()
        )

        filas = tabla[
            rotulo.str.contains(
                cfg["rotulo"].upper(),
                na=False,
                regex=False
            )
        ]

        if len(filas) == 0:
            return None

        fila = filas.iloc[ultima][cols[cfg["campo_valor"]]]

        return self.L.numero(fila)

    def validar(self, ruta, cuenta_id, datos, contexto):
        """
        Misma ecuación y tolerancia que el legado; las FUENTES de saldo
        inicial/final vienen del registro.
        """

        L = self.L

        fmt = self.registro.formato(
            self.registro.cuenta(cuenta_id)["formato"]
        )

        cfg = fmt["saldo"]

        datos = datos.copy()

        # Formatos que vienen de más reciente a más antiguo se ordenan
        # cronológicamente solo durante la validación.
        if cfg["orden"] == "CRONOLOGICO" and len(datos) > 0:

            datos["_ORDEN_FECHA"] = pd.to_datetime(
                datos["FECHA MOVIMIENTO"],
                errors="coerce"
            )

            horas_orden = (
                datos["HORA MOVIMIENTO"]
                .fillna("")
                .astype(str)
                .replace("", "00:00:00")
            )

            datos["_ORDEN_HORA"] = pd.to_timedelta(
                horas_orden,
                errors="coerce"
            ).fillna(pd.Timedelta(0))

            datos = (
                datos
                .sort_values(
                    ["_ORDEN_FECHA", "_ORDEN_HORA"],
                    na_position="last"
                )
                .drop(columns=["_ORDEN_FECHA", "_ORDEN_HORA"])
                .reset_index(drop=True)
            )

        creditos = datos["CRÉDITO"].sum(skipna=True)
        debitos = datos["DÉBITO"].sum(skipna=True)

        ini, fin = cfg["inicial"], cfg["final"]

        # Sin movimientos y saldo reconstruido: no hay contra qué validar.
        if ini["fuente"] == "RECONSTRUIDO" and len(datos) == 0:

            return {
                "SALDO INICIAL": np.nan,
                "CRÉDITOS": 0,
                "DÉBITOS": 0,
                "SALDO CALCULADO": np.nan,
                "SALDO FINAL": np.nan,
                "DIFERENCIA": np.nan,
                "ESTADO": "SIN MOVIMIENTOS"
            }

        cols = None

        if "FILA_ROTULADA" in (ini["fuente"], fin["fuente"]):
            cols = self._resolver_columnas(contexto["tabla"], fmt)

        # -- saldo inicial --------------------------------------

        if ini["fuente"] == "RECONSTRUIDO":

            primera = datos.iloc[0]

            primer_credito = (
                L.numero(primera["CRÉDITO"])
                if pd.notna(primera["CRÉDITO"])
                else 0
            )

            primer_debito = (
                L.numero(primera["DÉBITO"])
                if pd.notna(primera["DÉBITO"])
                else 0
            )

            inicial = (
                L.numero(primera["SALDO"])
                - primer_credito
                + primer_debito
            )

        elif ini["fuente"] == "CELDA_FIJA":

            inicial = L.numero(
                contexto["raw"].iloc[
                    ini["fila"] - 1,
                    ini["columna"] - 1
                ]
            )

        elif ini["fuente"] == "ETIQUETA":

            inicial = self._saldo_por_etiqueta(
                contexto["raw"],
                ini["etiqueta"]
            )

        else:

            valor = self._saldo_fila_rotulada(
                contexto["tabla"], cols, ini, 0
            )

            inicial = np.nan if valor is None else valor

        # -- saldo final ----------------------------------------

        def ultima_fila():
            return (
                L.numero(datos.iloc[-1]["SALDO"])
                if len(datos) > 0
                else None
            )

        final = None

        if fin["fuente"] == "ETIQUETA":

            final = self._saldo_por_etiqueta(
                contexto["raw"],
                fin["etiqueta"]
            )

        elif fin["fuente"] == "FILA_ROTULADA":

            final = self._saldo_fila_rotulada(
                contexto["tabla"], cols, fin, -1
            )

        else:

            final = ultima_fila()

        if final is None:

            if fin.get("respaldo") == "INICIAL":
                final = inicial
            elif fin.get("respaldo") == "ULTIMA_FILA":
                final = ultima_fila()

            if final is None:
                final = np.nan

        calculado, diferencia, estado = L.ecuacion_saldo(
            inicial,
            creditos,
            debitos,
            final
        )

        return {
            "SALDO INICIAL": inicial,
            "CRÉDITOS": creditos,
            "DÉBITOS": debitos,
            "SALDO CALCULADO": calculado,
            "SALDO FINAL": final,
            "DIFERENCIA": diferencia,
            "ESTADO": estado
        }

    # -- 5. PROCESO COMPLETO ------------------------------------

    def procesar(
        self,
        ruta,
        lote,
        fecha_carga,
        nombre_origen=None,
        cuenta_id=None
    ):
        """
        Detecta (si no se indica la cuenta), normaliza y valida.
        Lanza la misma clase de excepción que el legado ante un archivo
        que no puede leerse; un archivo no reconocido no lanza: queda en
        `resultado.deteccion`.
        """

        hojas = self.L.leer_todas_hojas(ruta)

        deteccion = (
            self.detectar(ruta, hojas)
            if cuenta_id is None
            else Deteccion(
                "OK",
                cuenta_id=cuenta_id,
                formato_id=self.registro.cuenta(cuenta_id)["formato"]
            )
        )

        if deteccion.estado != "OK":
            return ResultadoGenerico(deteccion=deteccion)

        df, contexto = self.normalizar(
            ruta,
            deteccion.cuenta_id,
            lote,
            fecha_carga,
            nombre_origen=nombre_origen,
            hojas=hojas
        )

        validacion = self.validar(
            ruta,
            deteccion.cuenta_id,
            df,
            contexto
        )

        return ResultadoGenerico(
            deteccion=deteccion,
            df=df,
            validacion=validacion,
            identidad=contexto["identidad"],
            sin_movimientos=contexto["sin_movimientos"]
        )


# ============================================================
# COMPARACIÓN GENÉRICO ↔ LEGADO
# ============================================================

MAX_EJEMPLOS_POR_COLUMNA = 5


def _es_nulo(v):

    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _iguales(a, b):

    if _es_nulo(a) and _es_nulo(b):
        return True

    if _es_nulo(a) != _es_nulo(b):
        return False

    try:
        return bool(a == b)
    except Exception:
        return False


def _familia_dtype(serie):

    d = serie.dtype

    if pd.api.types.is_bool_dtype(d):
        return "bool"

    if pd.api.types.is_numeric_dtype(d):
        return "numero"

    if pd.api.types.is_datetime64_any_dtype(d):
        return "fecha"

    return "texto/objeto"


def comparar_frames(legado, generico):
    """
    Compara dos DataFrames de movimientos (columnas, orden, índice,
    valores y familia de tipo). Devuelve una lista de diferencias, cada
    una {nivel, columna, fila_indice, valor_legado, valor_generico,
    detalle}; vacía = idénticos.
    """

    dif = []

    def agregar(columna, detalle, fila=None, vl=None, vg=None):
        dif.append({
            "nivel": "NORMALIZADO",
            "columna": columna,
            "fila_indice": fila,
            "valor_legado": vl,
            "valor_generico": vg,
            "detalle": detalle
        })

    if list(legado.columns) != list(generico.columns):
        agregar(
            "(columnas)",
            f"columnas u orden distintos: legado={list(legado.columns)} "
            f"generico={list(generico.columns)}"
        )
        return dif

    if len(legado) != len(generico):
        agregar(
            "(filas)",
            f"cantidad de movimientos: legado={len(legado)} "
            f"generico={len(generico)}"
        )
        return dif

    if list(legado.index) != list(generico.index):
        agregar(
            "(indice)",
            "el índice de filas (posición en el archivo) difiere"
        )

    for col in legado.columns:

        if _familia_dtype(legado[col]) != _familia_dtype(generico[col]):

            if len(legado) > 0:
                agregar(
                    col,
                    "familia de tipo distinta: "
                    f"legado={legado[col].dtype} "
                    f"generico={generico[col].dtype}"
                )

        ejemplos = 0
        total = 0

        for idx, a, b in zip(
            legado.index,
            legado[col].tolist(),
            generico[col].tolist()
        ):

            if _iguales(a, b):
                continue

            total += 1

            if ejemplos < MAX_EJEMPLOS_POR_COLUMNA:
                ejemplos += 1
                agregar(col, "valor distinto", idx, a, b)

        if total > ejemplos:
            agregar(
                col,
                f"{total - ejemplos} diferencia(s) más en esta columna "
                f"(total {total})"
            )

    return dif


TOLERANCIA_VALIDACION = 1e-6


def _numerico(v):
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)


def comparar_validacion(legado, generico, tolerancia=TOLERANCIA_VALIDACION):
    """
    Compara las dos validaciones de saldos. Un valor numérico que difiere
    en menos de `tolerancia` (ruido de coma flotante por el orden de
    suma; el motor legado tolera 0.01) NO es una diferencia de negocio:
    queda como OBSERVACION (visible en el informe, sin contar como
    diferencia). Todo lo demás es una diferencia.
    """

    dif = []

    if legado is None or generico is None:
        if legado is not generico:
            dif.append({
                "nivel": "VALIDACION",
                "columna": "(validacion)",
                "fila_indice": None,
                "valor_legado": str(legado),
                "valor_generico": str(generico),
                "detalle": "uno de los dos no produjo validación"
            })
        return dif

    if set(legado) != set(generico):
        dif.append({
            "nivel": "VALIDACION",
            "columna": "(claves)",
            "fila_indice": None,
            "valor_legado": str(sorted(legado)),
            "valor_generico": str(sorted(generico)),
            "detalle": "claves de validación distintas"
        })
        return dif

    for k in list(legado):

        a, b = legado[k], generico[k]

        if _iguales(a, b):
            continue

        if (
            _numerico(a) and _numerico(b)
            and not _es_nulo(a) and not _es_nulo(b)
            and abs(float(a) - float(b)) <= tolerancia
        ):
            dif.append({
                "nivel": "OBSERVACION",
                "columna": k,
                "fila_indice": None,
                "valor_legado": a,
                "valor_generico": b,
                "detalle": (
                    "ruido de coma flotante en la suma "
                    f"(|dif| <= {tolerancia}); no cuenta como diferencia"
                )
            })
            continue

        dif.append({
            "nivel": "VALIDACION",
            "columna": k,
            "fila_indice": None,
            "valor_legado": a,
            "valor_generico": b,
            "detalle": "valor de validación distinto"
        })

    return dif


def comparar_deteccion(formato_legado, deteccion):
    """El formato del legado (p. ej. BNB_MN) contra la cuenta detectada."""

    genericos = deteccion.cuenta_id if deteccion.estado == "OK" else deteccion.estado

    if formato_legado == genericos:
        return []

    return [{
        "nivel": "DETECCION",
        "columna": "(formato/cuenta)",
        "fila_indice": None,
        "valor_legado": formato_legado,
        "valor_generico": genericos,
        "detalle": deteccion.motivo or "detección distinta"
    }]


def _error_a_dict(e):
    return f"{type(e).__name__}: {e}"


def sombra_archivo(
    motor,
    nombre,
    ruta,
    formato_legado,
    lote,
    fecha_carga,
    tabla_legado=None,
    validacion_legado=None,
    error_legado=None
):
    """
    Corre el genérico sobre UN archivo y lo compara con el resultado del
    legado (ya calculado por quien llama). Nunca lanza: todo error del
    genérico queda como diferencia.

    Devuelve {archivo, formato_legado, cuenta_generico, estado,
    movimientos_legado, movimientos_generico, diferencias}.
    """

    r = {
        "archivo": nombre,
        "formato_legado": formato_legado,
        "cuenta_generico": None,
        "estado": "COINCIDE",
        "movimientos_legado": None if tabla_legado is None else len(tabla_legado),
        "movimientos_generico": None,
        "diferencias": [],
        "observaciones": []
    }

    try:

        gen = motor.procesar(
            ruta,
            lote,
            fecha_carga,
            nombre_origen=nombre
        )

    except Exception as e:

        # Ambos fallan con la misma clase de error = coinciden.
        if error_legado is not None and type(e).__name__ == error_legado.split(":")[0]:
            r["detalle"] = f"ambos fallan: {error_legado}"
            return r

        r["estado"] = "DIFIERE"
        r["diferencias"].append({
            "nivel": "ERROR_GENERICO",
            "columna": "",
            "fila_indice": None,
            "valor_legado": error_legado or "OK",
            "valor_generico": _error_a_dict(e),
            "detalle": "el motor genérico lanzó una excepción"
        })
        return r

    r["cuenta_generico"] = (
        gen.deteccion.cuenta_id
        if gen.deteccion.estado == "OK"
        else gen.deteccion.estado
    )

    r["diferencias"].extend(
        comparar_deteccion(formato_legado, gen.deteccion)
    )

    if gen.df is not None:
        r["movimientos_generico"] = len(gen.df)

    if error_legado is not None:

        if gen.df is not None:
            r["diferencias"].append({
                "nivel": "ERROR_LEGADO",
                "columna": "",
                "fila_indice": None,
                "valor_legado": error_legado,
                "valor_generico": "OK",
                "detalle": "el legado falla y el genérico procesa"
            })

    elif gen.df is not None and tabla_legado is not None:

        r["diferencias"].extend(
            comparar_frames(tabla_legado, gen.df)
        )

        r["diferencias"].extend(
            comparar_validacion(validacion_legado, gen.validacion)
        )

    elif gen.df is None and tabla_legado is not None:

        r["diferencias"].append({
            "nivel": "NORMALIZADO",
            "columna": "(archivo)",
            "fila_indice": None,
            "valor_legado": f"{len(tabla_legado)} movimientos",
            "valor_generico": gen.deteccion.estado,
            "detalle": "el genérico no procesó el archivo"
        })

    # Las OBSERVACIONES (ruido de coma flotante) se informan aparte y
    # no cuentan como diferencia.
    r["observaciones"] = [
        d for d in r["diferencias"] if d["nivel"] == "OBSERVACION"
    ]

    r["diferencias"] = [
        d for d in r["diferencias"] if d["nivel"] != "OBSERVACION"
    ]

    if r["diferencias"]:
        r["estado"] = "DIFIERE"

    return r


# ============================================================
# INFORME
# ============================================================

def _jsonable(v):

    if _es_nulo(v):
        return None

    if isinstance(v, (np.integer,)):
        return int(v)

    if isinstance(v, (np.floating,)):
        return float(v)

    if isinstance(v, (int, float, str, bool)):
        return v

    return str(v)


def armar_informe(motor, archivos, lote, extra=None):

    diferencias_total = sum(len(a["diferencias"]) for a in archivos)

    informe = {
        "modo": "SOMBRA",
        "produccion": "motor legado (el motor genérico no produce salida)",
        "version_motor_generico": VERSION_MOTOR_GENERICO,
        "version_registro": motor.registro.version,
        "sha256_registro": motor.registro.sha256,
        "lote": lote,
        "estado": (
            "SIN_DIFERENCIAS" if diferencias_total == 0 else "CON_DIFERENCIAS"
        ),
        "archivos_comparados": len(archivos),
        "archivos_coinciden": sum(a["estado"] == "COINCIDE" for a in archivos),
        "archivos_difieren": sum(a["estado"] == "DIFIERE" for a in archivos),
        "diferencias_total": diferencias_total,
        "observaciones_total": sum(
            len(a.get("observaciones", [])) for a in archivos
        ),
        "archivos": archivos
    }

    if extra:
        informe.update(extra)

    return informe


def escribir_informe(informe, carpeta):
    """
    SOMBRA_REPORTE.json (diferencias + observaciones) y
    SOMBRA_DIFERENCIAS.csv (solo diferencias; vacío = sin diferencias).
    Nunca .xlsx: un .xlsx en la carpeta de salida podría confundirse con
    un extracto en la corrida siguiente (D-20).
    """

    os.makedirs(carpeta, exist_ok=True)

    ruta_json = os.path.join(carpeta, NOMBRE_REPORTE_JSON)
    ruta_csv = os.path.join(carpeta, NOMBRE_REPORTE_CSV)

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(
            informe,
            f,
            ensure_ascii=False,
            indent=1,
            default=_jsonable
        )

    filas = []

    for a in informe["archivos"]:
        for d in a["diferencias"]:
            filas.append({
                "ARCHIVO": a["archivo"],
                "FORMATO LEGADO": a["formato_legado"],
                "CUENTA GENÉRICO": a["cuenta_generico"],
                "NIVEL": d["nivel"],
                "COLUMNA": d["columna"],
                "FILA (ÍNDICE)": d["fila_indice"],
                "VALOR LEGADO": _jsonable(d["valor_legado"]),
                "VALOR GENÉRICO": _jsonable(d["valor_generico"]),
                "DETALLE": d["detalle"]
            })

    columnas = [
        "ARCHIVO", "FORMATO LEGADO", "CUENTA GENÉRICO", "NIVEL",
        "COLUMNA", "FILA (ÍNDICE)", "VALOR LEGADO", "VALOR GENÉRICO",
        "DETALLE"
    ]

    pd.DataFrame(filas, columns=columnas).to_csv(
        ruta_csv,
        index=False,
        encoding="utf-8-sig"
    )

    return ruta_json, ruta_csv


# ============================================================
# INTEGRACIÓN EN PRODUCCIÓN (SOMBRA, NUNCA DETIENE AL LEGADO)
# ============================================================

def ejecutar_sombra_produccion(
    legado,
    mapa_archivos,
    df_deteccion_final,
    tablas,
    df_validacion,
    lote,
    fecha_carga,
    carpeta_reporte,
    ruta_registro=None
):
    """
    Se llama al final de `ejecutar_motor`, cuando la salida productiva ya
    fue escrita. Compara la corrida del legado (detecciones, tablas
    normalizadas y validaciones tal como las produjo) con el motor
    genérico y escribe el informe de diferencias.

    Devuelve un diccionario de estado. NUNCA lanza: cualquier fallo de
    este módulo queda como {"estado": "ERROR", ...} y no afecta al legado.
    """

    try:

        registro = Registro.cargar(
            ruta_registro
            or os.environ.get("CBBA_REGISTRO_BANCOS")
        )

        problemas = registro.validar()

        if problemas:
            return {
                "estado": "ERROR",
                "error": "registro inválido: " + "; ".join(problemas),
                "ruta_reporte": None
            }

        motor = MotorGenerico(registro, legado)

        archivos = []

        validacion_por_archivo = {
            fila["ARCHIVO"]: fila
            for _, fila in df_validacion.iterrows()
        }

        for (_, fila), tabla in zip(df_deteccion_final.iterrows(), tablas):

            nombre = fila["ARCHIVO"]

            v = validacion_por_archivo.get(nombre)

            validacion_legado = (
                None
                if v is None
                else {
                    k: v[k]
                    for k in (
                        "SALDO INICIAL", "CRÉDITOS", "DÉBITOS",
                        "SALDO CALCULADO", "SALDO FINAL", "DIFERENCIA",
                        "ESTADO"
                    )
                }
            )

            archivos.append(
                sombra_archivo(
                    motor,
                    nombre,
                    mapa_archivos[nombre],
                    fila["FORMATO"],
                    lote,
                    fecha_carga,
                    tabla_legado=tabla,
                    validacion_legado=validacion_legado
                )
            )

        informe = armar_informe(motor, archivos, lote)

        ruta_json, ruta_csv = escribir_informe(informe, carpeta_reporte)

        return {
            "estado": informe["estado"],
            "archivos_comparados": informe["archivos_comparados"],
            "archivos_coinciden": informe["archivos_coinciden"],
            "archivos_difieren": informe["archivos_difieren"],
            "diferencias_total": informe["diferencias_total"],
            "observaciones_total": informe["observaciones_total"],
            "ruta_reporte": ruta_json,
            "ruta_diferencias": ruta_csv
        }

    except Exception as e:

        return {
            "estado": "ERROR",
            "error": _error_a_dict(e),
            "ruta_reporte": None
        }


# ============================================================
# COMPARACIÓN AUTÓNOMA DE UNA CARPETA (sin escribir producción)
# ============================================================

def comparar_carpeta(
    carpeta_entrada,
    legado,
    registro=None,
    lote="SOMBRA",
    fecha_carga=None
):
    """
    Corre legado y genérico archivo por archivo y devuelve el informe.
    No escribe NORMALIZADO.xlsx ni LISTS.csv. Útil para pruebas y para
    revisar una carpeta antes de correr el motor completo.
    """

    if fecha_carga is None:
        fecha_carga = pd.Timestamp("2026-01-01 00:00:00")

    registro = registro or Registro.cargar()

    problemas = registro.validar()

    if problemas:
        raise RegistroError("; ".join(problemas))

    motor = MotorGenerico(registro, legado)

    archivos = []

    for nombre, ruta in legado.descubrir_archivos(carpeta_entrada).items():

        formato_legado = None
        tabla = None
        validacion = None
        error = None

        try:

            formato_legado = legado.detectar_formato(ruta)

            if formato_legado == "NO_RECONOCIDO":
                error = None
            else:
                tabla = legado.normalizar_archivo(
                    ruta, formato_legado, lote, fecha_carga,
                    nombre_origen=nombre
                )

                datos = tabla.copy()
                datos["FECHA MOVIMIENTO"] = pd.to_datetime(
                    datos["FECHA MOVIMIENTO"], errors="coerce"
                )

                validacion = legado.validar_archivo(
                    ruta, formato_legado, datos
                )

        except Exception as e:

            error = _error_a_dict(e)

        archivos.append(
            sombra_archivo(
                motor,
                nombre,
                ruta,
                formato_legado,
                lote,
                fecha_carga,
                tabla_legado=tabla,
                validacion_legado=validacion,
                error_legado=error
            )
        )

    return armar_informe(motor, archivos, lote)


# ============================================================
# EJECUCIÓN COMO SCRIPT
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) not in (2, 3):

        print(
            "Uso: python motor_generico.py <carpeta_entrada> "
            "[<carpeta_reporte>]"
        )

        sys.exit(1)

    legado_cli = cargar_legado()

    informe_cli = comparar_carpeta(sys.argv[1], legado_cli)

    print(f"Estado: {informe_cli['estado']}")

    for a in informe_cli["archivos"]:

        print(
            f"  {a['estado']:<8} {a['archivo']}  "
            f"legado={a['formato_legado']}  "
            f"generico={a['cuenta_generico']}  "
            f"dif={len(a['diferencias'])}"
        )

    if len(sys.argv) == 3:

        rutas = escribir_informe(informe_cli, sys.argv[2])

        print("Informe:", *rutas)

    sys.exit(0 if informe_cli["estado"] == "SIN_DIFERENCIAS" else 1)
