"""
============================================================
CONTROL DE DEPÓSITOS CBBA — MOTOR GENÉRICO (NORMALIZACIÓN PRODUCTIVA)
============================================================

Motor dirigido por `registro_bancos.json`: la misma secuencia para todos
los bancos, sin ramas por banco. Lee la tabla de movimientos, la mapea a
las 26 `COLUMNAS_LISTS` y valida saldos usando SOLO la configuración del
registro.

ESTADO: PRODUCTIVO desde P5; único normalizador desde P6.
  * `motor_control_depositos_cbba.py` identifica cada extracto con
    `deteccion_registro.py` (P4) y lo normaliza y valida con
    `MotorGenerico.normalizar` / `MotorGenerico.validar`. La salida
    productiva (NORMALIZADO.xlsx, LISTS.csv, ORIGEN.xlsx) sale de aquí.
  * P6 retiró los `normalizar_*` / `validar_archivo` legados, la
    comparación en sombra (SOMBRA_REPORTE.json / SOMBRA_DIFERENCIAS.csv),
    la detección propia de P3 (reemplazada por `deteccion_registro.py`) y
    el modo script de comparación.

Qué reutiliza del motor (solo primitivas sin lógica bancaria, y sin
modificarlas): conversión de números/fechas/horas/códigos, lector de
Excel robusto, búsqueda difusa de columnas, `extraer_nombre_bnb`
(estrategia `legacy_bnb`), `ecuacion_saldo` y `finalizar_dataframe`
(que fija `COLUMNAS_LISTS` y `CLAVE TRANSACCIÓN`, congeladas).

La fila de encabezado exige `encabezados.puntaje_minimo` (D-09): nunca se
normaliza una tabla leída desde una fila cualquiera.

Agregar una cuenta nueva de un formato ya conocido = una entrada en
`CUENTAS` del registro; cero código (ver `Registro.con_cuenta`).

Uso (dentro del motor productivo):
    MotorGenerico(Registro.cargar(ruta), primitivas).normalizar(...)
============================================================
"""

import copy
import hashlib
import json
import os
import re
import types

import numpy as np
import pandas as pd


VERSION_MOTOR_GENERICO = "P6-1"

RUTA_REGISTRO_DEFECTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "registro_bancos.json"
)

# Primitivas del motor que este módulo consume. Sin lógica bancaria.
PRIMITIVAS_MOTOR = (
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
# ACCESO A LAS PRIMITIVAS DEL MOTOR
# ============================================================

def namespace_primitivas(origen):
    """
    Devuelve un objeto con las primitivas del motor. `origen` puede ser
    el módulo del motor, un diccionario (p. ej. `globals()`) o un
    namespace. Falla con un mensaje claro si falta alguna primitiva.
    """

    if isinstance(origen, dict):
        origen = types.SimpleNamespace(**origen)

    faltan = [
        p for p in PRIMITIVAS_MOTOR
        if not hasattr(origen, p)
    ]

    if faltan:
        raise RuntimeError(
            "El motor no expone las primitivas requeridas: "
            f"{faltan}"
        )

    return origen


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
        `normalizar` es la función de normalización de texto del motor.
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
# MOTOR GENÉRICO
# ============================================================

class MotorGenerico:
    """Normaliza y valida usando únicamente el registro."""

    def __init__(self, registro, primitivas):

        self.registro = registro
        self.L = namespace_primitivas(primitivas)

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
        mismo criterio que la detección, con la lista del registro.
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

    # -- 1. TABLA DE MOVIMIENTOS ---------------------------------

    def _leer_tabla(self, ruta, fmt, hojas):
        """Devuelve (hoja, raw, fila_encabezado, tabla) del formato."""

        hoja = self._hoja_aceptada(hojas, fmt)

        if hoja is None:
            raise ValueError(
                "El archivo no tiene ninguna de las hojas aceptadas "
                f"{fmt.get('hojas_aceptadas')}: {list(hojas)}"
            )

        raw = hojas[hoja]

        esperados = fmt["encabezados"]["puntaje"]

        fila, puntaje, total = self._fila_encabezado(
            raw,
            esperados
        )

        # D-09: la tabla solo se lee desde un encabezado que cumple el
        # mínimo del registro; nunca desde la «mejor» fila cualquiera.
        if fila is None or puntaje < fmt["encabezados"]["puntaje_minimo"] * total:

            texto = (
                ""
                if fila is None
                else self._norm(
                    " | ".join(raw.loc[fila].fillna("").astype(str).tolist())
                )
            )

            faltan = [e for e in esperados if self._norm(e) not in texto]

            raise ValueError(
                f"hoja '{hoja}': encabezado de la tabla incompleto "
                f"({max(puntaje, 0)}/{total}); faltan: {', '.join(faltan)}"
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

    # -- 2. NORMALIZACIÓN ---------------------------------------

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
        un extracto válido sin movimientos, es un DataFrame vacío; su
        identidad completa va en `contexto`.
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

    # -- 3. VALIDACIÓN DE SALDOS --------------------------------

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
        Ecuación y tolerancia de `ecuacion_saldo` (0.01); las FUENTES de
        saldo inicial/final vienen del registro.
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
