"""Contrato de reversión V2. No contiene identificadores del tenant.

El esquema JSON es la fuente de las columnas; estas constantes fijan los
invariantes del protocolo y no cambian el contrato histórico de confirmación.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID

from p9.contrato import COLUMNAS_MOTOR_26

CARPETA = Path(__file__).resolve().parent
ESQUEMA = CARPETA / "esquema_reversiones.json"
LISTA_DEPOSITOS = "Depositos_Activos"
LISTA_REVERSIONES = "Depositos_Reversiones"
ESTADOS_SOLICITUD = ("PENDIENTE", "APROBADO", "RECHAZADO")
FASES = ("RECIBIDA", "ESPERANDO_APROBACION", "EJECUTANDO_REVERSION",
         "RECUPERACION_REQUERIDA", "FINALIZADA", "EXPIRADA")
RESULTADOS_TECNICOS = ("PENDIENTE", "REVERTIDO", "CONFLICTO", "YA_NO_ASIGNADO",
                       "DEPOSITO_NO_ENCONTRADO", "CLAVE_NO_COINCIDE", "ERROR", "NO_EJECUTADO")
FASES_TERMINALES = ("FINALIZADA", "EXPIRADA")
CAMPOS_LIMPIAR = ("ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR",
                  "SEDE_ASIGNACION", "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "OBSERVACION")
CAMPOS_MOTOR = COLUMNAS_MOTOR_26
CAMPOS_SNAPSHOT = CAMPOS_MOTOR + ("ESTADO_ASIGNACION",) + CAMPOS_LIMPIAR
CAMPOS_ESCRITOS = ("ESTADO_ASIGNACION",) + CAMPOS_LIMPIAR + ("ULTIMA_REVERSION_ID",)
APROBADORES = ("gtorricot@univalle.edu", "lvelasquezs@univalle.edu")
PLAZO_HORAS = 168
MAX_MOTIVO = 4000
INDICES = ("SOLICITUD_UID", "CLAVE_BLOQUEO", "DEPOSITO_ID", "CLAVE_TRANSACCION",
           "FECHA_LIMITE", "ESTADO_SOLICITUD", "FASE_PROCESO")
TIPOS_HISTORIAL = {
    **dict.fromkeys(("SOLICITUD_UID", "LISTA_DEPOSITO_ID", "CLAVE_TRANSACCION", "CLAVE_BLOQUEO", "BANCO",
                     "CUENTA_BANCARIA", "MONEDA", "CODIGO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE",
                     "SOLICITADO_POR", "SEDE_ASIGNACION", "USUARIO_ASIGNACION", "ETAG_SOLICITUD", "SOLICITANTE_ID",
                     "SOLICITANTE_UPN", "APROBACION_ID", "APROBADOR_ID", "APROBADOR_UPN", "ETAG_EJECUCION", "RUN_ID"), "Text"),
    **dict.fromkeys(("DEPOSITO_ID", "IMPORTE"), "Number"),
    **dict.fromkeys(("FECHA_MOVIMIENTO", "FECHA_HORA_ASIGNACION", "FECHA_SOLICITUD", "FECHA_LIMITE", "FECHA_DECISION",
                     "FECHA_EJECUCION_REVERSION", "FECHA_CIERRE"), "DateTime"),
    **dict.fromkeys(("OBSERVACION", "SNAPSHOT_JSON", "MOTIVO_REVERSION", "CONFIG_APROBACION_JSON", "COMENTARIO_APROBADOR",
                     "RESPUESTA_APROBACION_JSON", "ERROR_TECNICO", "BITACORA_TECNICA_JSON"), "Note"),
    **dict.fromkeys(("ESTADO_SOLICITUD", "FASE_PROCESO", "RESULTADO_TECNICO"), "Choice"),
}
REQUERIDOS_HISTORIAL = frozenset((
    "SOLICITUD_UID", "DEPOSITO_ID", "LISTA_DEPOSITO_ID", "CLAVE_TRANSACCION", "CLAVE_BLOQUEO", "BANCO",
    "CUENTA_BANCARIA", "FECHA_MOVIMIENTO", "IMPORTE", "MONEDA", "ETAG_SOLICITUD", "SNAPSHOT_JSON",
    "MOTIVO_REVERSION", "SOLICITANTE_ID", "SOLICITANTE_UPN", "FECHA_SOLICITUD", "FECHA_LIMITE",
    "ESTADO_SOLICITUD", "FASE_PROCESO"))
TRANSICIONES = {
    "RECIBIDA": ("ESPERANDO_APROBACION", "RECUPERACION_REQUERIDA", "EXPIRADA"),
    "ESPERANDO_APROBACION": ("EJECUTANDO_REVERSION", "FINALIZADA", "RECUPERACION_REQUERIDA", "EXPIRADA"),
    "EJECUTANDO_REVERSION": ("FINALIZADA", "RECUPERACION_REQUERIDA"),
    "RECUPERACION_REQUERIDA": ("ESPERANDO_APROBACION", "EJECUTANDO_REVERSION", "FINALIZADA", "EXPIRADA", "RECUPERACION_REQUERIDA"),
    "FINALIZADA": ("FINALIZADA",),
    "EXPIRADA": ("EXPIRADA",),
}


def uuid_canonico(valor: str) -> str:
    """Normaliza UUID; rechaza formas abreviadas, llaves y UUID nulo."""
    if not isinstance(valor, str) or not re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", valor):
        raise ValueError("UUID inválido")
    uid = UUID(valor)
    if uid.int == 0:
        raise ValueError("UUID nulo")
    return str(uid)


def clave_activa(lista_id: str, deposito_id: int) -> str:
    if isinstance(deposito_id, bool) or not isinstance(deposito_id, int) or deposito_id <= 0:
        raise ValueError("DEPOSITO_ID debe ser un entero positivo")
    return f"ACTIVA|{uuid_canonico(lista_id)}|{deposito_id}"


def clave_cerrada(solicitud_uid: str) -> str:
    return f"CERRADA|{uuid_canonico(solicitud_uid)}"


def payload_reversion(solicitud_uid: str) -> dict:
    return {"ESTADO_ASIGNACION": "DISPONIBLE", **{c: None for c in CAMPOS_LIMPIAR},
            "ULTIMA_REVERSION_ID": uuid_canonico(solicitud_uid)}


def cargar_esquema() -> dict:
    esquema = json.loads(ESQUEMA.read_text(encoding="utf-8"))
    validar_esquema(esquema)
    return esquema


def validar_esquema(esquema: dict) -> None:
    if esquema.get("version") != "2.0" or set(esquema) != {"version", LISTA_REVERSIONES, LISTA_DEPOSITOS}:
        raise ValueError("Versión/listas distintas del contrato V2")
    for lista in (LISTA_REVERSIONES, LISTA_DEPOSITOS):
        campos = esquema[lista]["columnas"]
        nombres = [c["nombre_tecnico"] for c in campos]
        if len(set(nombres)) != len(nombres):
            raise ValueError("Nombres de columna repetidos")
        for campo in campos:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", campo["nombre_tecnico"]):
                raise ValueError("Nombre interno no ASCII o demasiado largo")
            if campo["valores_unicos"] and not campo["indexada"]:
                raise ValueError("La unicidad requiere índice")
            if campo["tipo"] == "Note" and (campo["rich_text"] or campo["append_only"]):
                raise ValueError("Bitácora/snapshot deben ser texto íntegro sin anexado automático")
    historial = esquema[LISTA_REVERSIONES]
    columnas = {c["nombre_tecnico"]: c for c in historial["columnas"]}
    if {n: c["tipo"] for n, c in columnas.items()} != TIPOS_HISTORIAL:
        raise ValueError("Columnas o tipos distintos del esquema V2")
    if {n for n, c in columnas.items() if c["obligatoria"]} != REQUERIDOS_HISTORIAL:
        raise ValueError("Obligatoriedad distinta del esquema V2")
    for nombre, campo in columnas.items():
        if campo["tipo"] == "Text" and campo.get("max_length") != 255:
            raise ValueError("Texto V2 requiere capacidad de 255 caracteres")
        if campo["tipo"] == "DateTime" and campo.get("format") != ("DateOnly" if nombre == "FECHA_MOVIMIENTO" else "DateTime"):
            raise ValueError("Formato de fecha distinto del esquema V2")
    if columnas["MOTIVO_REVERSION"].get("max_length_aplicacion") != MAX_MOTIVO:
        raise ValueError("Motivo fuera del límite aprobado")
    if columnas["DEPOSITO_ID"].get("decimals") != 0 or columnas["DEPOSITO_ID"].get("min") != 1:
        raise ValueError("ID debe ser entero positivo")
    if columnas["IMPORTE"].get("decimals") != 2 or columnas["IMPORTE"].get("percentage"):
        raise ValueError("Importe debe conservar dos decimales")
    for nombre, valores in (("ESTADO_SOLICITUD", ESTADOS_SOLICITUD), ("FASE_PROCESO", FASES),
                            ("RESULTADO_TECNICO", RESULTADOS_TECNICOS)):
        campo = columnas[nombre]
        if tuple(campo["valores"]) != valores or campo["permitir_relleno"]:
            raise ValueError(f"Opciones fuera del contrato: {nombre}")
    resultado = columnas["RESULTADO_TECNICO"]
    if resultado["obligatoria"] or resultado.get("predeterminado") is not None:
        raise ValueError("El resultado técnico debe admitir null sin valor predeterminado")
    if set(c for c, v in columnas.items() if v["indexada"]) != set(INDICES):
        raise ValueError("Índices distintos del contrato")
    if not historial["versionado"] or historial["title_obligatorio"]:
        raise ValueError("El historial requiere versionado y Title opcional")
    if set(c for c, v in columnas.items() if v["valores_unicos"]) != {"SOLICITUD_UID", "CLAVE_BLOQUEO"}:
        raise ValueError("Faltan restricciones únicas")
    marcador = esquema[LISTA_DEPOSITOS]["columnas"]
    if len(marcador) != 1 or marcador[0]["nombre_tecnico"] != "ULTIMA_REVERSION_ID":
        raise ValueError("En depósitos solo se incorpora el marcador")
    if marcador[0]["obligatoria"] or marcador[0]["indexada"] or marcador[0].get("predeterminado") is not None:
        raise ValueError("El marcador debe ser opcional, sin índice ni valor inicial")
    if marcador[0]["tipo"] != "Text" or marcador[0].get("max_length") != 255 or marcador[0]["valores_unicos"]:
        raise ValueError("El marcador debe ser Texto 255 sin unicidad")
