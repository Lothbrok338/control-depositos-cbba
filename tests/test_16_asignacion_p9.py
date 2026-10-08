"""P9 — asignación de depósitos: pruebas locales de los dos flujos, el paquete y las fórmulas Power Fx.

Intérprete WDL local + SharePoint REST simulado (p9/ensayo.py). NO es el runtime Microsoft: no certifica importación,
conectores ni el comportamiento real de If-Match en el tenant. P9 es aditivo: ninguna prueba P6/P7/P8 se modifica.
"""
import copy
import hashlib
import json
import re
import threading
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]  # raíz del repo (helpers.RAIZ es la carpeta tests/)
sys.path.insert(0, str(RAIZ))

from p9 import contrato as C
from p9.asignar import construir as ASIGNAR
from p9.ensayo import EnsayoP9, SharePointP9, asignar, entradas_asignar
from p9.habilitar import construir as HABILITAR
from p9.wdl import contar_acciones, recorrer

pytestmark = pytest.mark.p9

EJEMPLO = RAIZ / "ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json"
DOS_ESTADOS = ("DISPONIBLE", "ASIGNADO")
OPERATIVOS_EN_FILA = ("ESTADO_ASIGNACION", "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION",
                      "USUARIO_ASIGNACION", "FECHA_HORA_ASIGNACION", "OBSERVACION")


# ------------------------------------------------------------------ utilidades
def filas():
    movimientos = json.loads(EJEMPLO.read_text(encoding="utf-8"))["movimientos"]
    return [{**m, "IMPORTE": float(m["IMPORTE"])} for m in movimientos]


def nueva(opciones=DOS_ESTADOS):
    return SharePointP9(filas(), opciones=opciones)


def clave(n):
    return filas()[n - 1]["CLAVE_TRANSACCION"]


def motor26(sp):
    """Las 26 columnas del motor de todos los elementos (para comprobar que P9 no las toca)."""
    return {i: {c: it["campos"].get(c) for c in C.COLUMNAS_MOTOR_26} for i, it in sp.items.items()}


def correr(sp, id_=1, clave_=None, **kw):
    r = asignar(ASIGNAR.construir_definicion(), sp, entradas_asignar(id_, clave_ or clave(id_), **kw))
    assert r.estado_final == "Succeeded", r.estado_final  # el Response SIEMPRE se envía; el flujo no falla hacia la app
    assert tuple(r.respuesta) == C.SALIDAS
    assert r.respuesta["resultado"] in C.RESULTADOS
    return r


def llamadas(sp, metodo=None):
    return [c for c in sp.llamadas if metodo is None or c["metodo"] == metodo]


def merges(sp):
    return [c for c in sp.llamadas if c["cabeceras"].get("x-http-method") == "MERGE"]


def merges_choices(sp):
    return [m for m in merges(sp) if m["cuerpo"] and "Choices" in m["cuerpo"]]


def merges_indices(sp):
    return [m for m in merges(sp) if m["cuerpo"] and "Indexed" in m["cuerpo"]]


# ------------------------------------------------------------------ paquetes
def test_paquetes_reproducibles_y_con_estructura_importable():
    antes = {p: p.read_bytes() for p in (ASIGNAR.ZIP_SALIDA, HABILITAR.ZIP_SALIDA, ASIGNAR.DEFINICION_SALIDA, HABILITAR.DEFINICION_SALIDA)}
    ASIGNAR.generar()
    HABILITAR.generar()
    assert {p: p.read_bytes() for p in antes} == antes
    assert ASIGNAR.ZIP_SALIDA.name == "P9_ASIGNAR_DEPOSITO.zip" and HABILITAR.ZIP_SALIDA.name == "P9_HABILITAR_ESTADO_ASIGNADO.zip"
    ids_vistos = set()
    for ruta, nombre, modulo in ((ASIGNAR.ZIP_SALIDA, "P9_ASIGNAR_DEPOSITO", ASIGNAR), (HABILITAR.ZIP_SALIDA, "P9_HABILITAR_ESTADO_ASIGNADO", HABILITAR)):
        with zipfile.ZipFile(ruta) as z:
            assert z.testzip() is None
            manifest = json.loads(z.read("manifest.json"))
            assert manifest["details"]["displayName"] == nombre
            flujos = [r for r in manifest["resources"].values() if r["type"] == "Microsoft.Flow/flows"]
            assert len(flujos) == 1 and flujos[0]["details"]["displayName"] == nombre and flujos[0]["suggestedCreationType"] == "New"
            definicion = next(n for n in z.namelist() if n.endswith("/definition.json"))
            envoltura = json.loads(z.read(definicion))
            assert envoltura["properties"]["displayName"] == nombre
            assert envoltura["properties"]["definition"] == modulo.construir_definicion()
            assert list(envoltura["properties"]["connectionReferences"]) == ["shared_sharepointonline"]
            assert len(z.namelist()) == 5
            ids_vistos |= set(manifest["resources"])
    # no comparten identificadores entre sí ni con ningún paquete P8 existente
    assert len(ids_vistos) == 6
    for p8 in RAIZ.glob("P8_*.zip"):
        with zipfile.ZipFile(p8) as z:
            assert not ids_vistos & set(json.loads(z.read("manifest.json"))["resources"]), p8.name


def test_el_paquete_de_asignar_no_incluye_el_esquema_p8_ni_reutiliza_el_provisionador():
    fuente = (RAIZ / "p9/habilitar/construir.py").read_text(encoding="utf-8") + (RAIZ / "p9/asignar/construir.py").read_text(encoding="utf-8")
    assert "p8.provision" not in fuente and "esquema_listas_p8" not in fuente


def test_constantes_del_piloto_coinciden_con_p8():
    from p8 import definicion as p8def
    assert C.SITIO_SHAREPOINT == p8def.SITIO_SHAREPOINT
    assert C.LISTA_DEPOSITOS_ACTIVOS_ID == p8def.LISTAS_ID["DEPOSITOS_ACTIVOS"]
    definicion = ASIGNAR.construir_definicion()
    assert definicion["actions"]["PARAM_SITIO_SHAREPOINT"]["inputs"] == C.SITIO_SHAREPOINT
    assert definicion["actions"]["PARAM_LISTA_DEPOSITOS_ACTIVOS"]["inputs"] == C.LISTA_DEPOSITOS_ACTIVOS_ID


@pytest.mark.parametrize("modulo", [ASIGNAR, HABILITAR])
def test_integridad_estructural_de_la_definicion(modulo):
    d = modulo.construir_definicion()
    pares = list(recorrer(d["actions"]))
    assert len({n for n, _ in pares}) == len(pares), "nombres de acción duplicados"

    def dependencias(bloque):
        for nombre, accion in bloque.items():
            assert set(accion.get("runAfter", {})) <= set(bloque), nombre
            dependencias(accion.get("actions", {}))
            dependencias(accion.get("else", {}).get("actions", {}))
    dependencias(d["actions"])
    texto = json.dumps(d)
    assert "result(" not in texto
    # conectores: solo SharePoint estándar «Enviar una solicitud HTTP»; nada premium ni HTTP genérico
    for _, a in pares:
        if a["type"] == "OpenApiConnection":
            host = a["inputs"]["host"]
            assert host["apiId"] == "/providers/Microsoft.PowerApps/apis/shared_sharepointonline" and host["operationId"] == "HttpRequest"
            assert a["inputs"]["retryPolicy"] == {"type": "none"}
        assert a["type"] in {"Compose", "InitializeVariable", "SetVariable", "AppendToArrayVariable", "Scope", "If",
                             "OpenApiConnection", "Response", "Terminate", "Foreach", "Query", "Select"}


def test_flujo_asignar_trigger_entradas_y_respuesta():
    d = ASIGNAR.construir_definicion()
    manual = d["triggers"]["manual"]
    assert manual["type"] == "Request" and manual["kind"] == "Button"
    esquema = manual["inputs"]["schema"]
    assert list(esquema["properties"]) == [c[0] for c in C.ENTRADAS]
    assert [esquema["properties"][c[0]]["title"] for c in C.ENTRADAS] == ["ID SharePoint", "CLAVE_TRANSACCION", "ESTUDIANTE",
        "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "OBSERVACION", "USUARIO_ASIGNACION"]
    assert esquema["properties"]["number"]["type"] == "number"
    assert esquema["required"] == [c[0] for c in C.ENTRADAS if c[3]] and "text_5" not in esquema["required"]  # OBSERVACION opcional
    respuesta = d["actions"]["Responder_a_PowerApps"]
    assert respuesta["type"] == "Response" and respuesta["kind"] == "PowerApp"
    assert tuple(respuesta["inputs"]["body"]) == C.SALIDAS == tuple(respuesta["inputs"]["schema"]["properties"])
    assert set(respuesta["runAfter"]) == {"TRY", "CATCH"} and all(set(v) == {"Succeeded", "Failed", "Skipped", "TimedOut"} for v in respuesta["runAfter"].values())
    assert d["actions"]["CATCH"]["runAfter"] == {"TRY": ["Failed", "TimedOut"]}


def test_flujo_asignar_contrato_de_escritura_y_control_optimista():
    d = ASIGNAR.construir_definicion()
    acciones = dict(recorrer(d["actions"]))
    cuerpo = acciones["Cuerpo_actualizacion"]["inputs"]
    assert set(cuerpo) == set(C.CAMPOS_ESCRITOS) and cuerpo["ESTADO_ASIGNACION"] == "ASIGNADO"
    assert not set(cuerpo) & set(C.COLUMNAS_MOTOR_26), "P9 nunca escribe las 26 columnas del motor"
    assert cuerpo["FECHA_HORA_ASIGNACION"] == "@outputs('Ahora')" and acciones["Ahora"]["inputs"] == "@utcNow()"
    escritura = acciones["Actualizar_deposito"]["inputs"]["parameters"]
    assert escritura["parameters/method"] == "POST"
    assert escritura["parameters/headers"]["X-HTTP-Method"] == "MERGE"
    assert escritura["parameters/headers"]["IF-MATCH"] == "@outputs('ETag')"  # condición = ETag leído; nunca '*'
    assert "'*'" not in json.dumps(escritura) and '"*"' not in json.dumps(escritura)
    assert escritura["parameters/uri"].count("/items(") == 1
    # dos llamadas SharePoint por asignación: GET + MERGE; ninguna otra operación (sin DELETE ni PATCH)
    http = [(n, a["inputs"]["parameters"]["parameters/method"], a["inputs"]["parameters"]["parameters/headers"].get("X-HTTP-Method"))
            for n, a in acciones.items() if a["type"] == "OpenApiConnection"]
    assert http == [("Leer_deposito", "GET", None), ("Actualizar_deposito", "POST", "MERGE")]
    assert "DELETE" not in json.dumps(d) and "PATCH" not in json.dumps(d)
    assert "ASIGNADO" in json.dumps(d) and set(C.ESTADOS) == {"DISPONIBLE", "ASIGNADO"}


# ------------------------------------------------------------------ asignación normal
def test_asignacion_normal():
    sp = nueva()
    antes = copy.deepcopy(sp.items)
    r = correr(sp, 1, observacion="Pago de matrícula")
    assert r.respuesta == {"resultado": "ASIGNADO", "codigo": "ASIGNADO", "mensaje": "Depósito asignado correctamente.",
                           "estado_actual": "ASIGNADO", "asignado_por": "operador@univalle.edu",
                           "fecha_hora_asignacion": "2026-10-01T15:30:00.0000000Z"}
    campos = sp.items[1]["campos"]
    assert campos["ESTADO_ASIGNACION"] == "ASIGNADO"
    assert (campos["ESTUDIANTE"], campos["CODIGO_ESTUDIANTE"], campos["SOLICITADO_POR"], campos["SEDE_ASIGNACION"],
            campos["OBSERVACION"], campos["USUARIO_ASIGNACION"]) == ("Ana Perez", "E-1001", "Mesa de ayuda", "COCHABAMBA",
                                                                    "Pago de matrícula", "operador@univalle.edu")
    assert campos["FECHA_HORA_ASIGNACION"] == "2026-10-01T15:30:00.0000000Z"  # utcNow() del flujo, no de la app
    assert sp.items[1]["version"] == antes[1]["version"] + 1
    # nada más cambió: ni las otras 7 filas ni las 26 columnas de esta
    assert {i: it for i, it in sp.items.items() if i != 1} == {i: it for i, it in antes.items() if i != 1}
    assert {k: v for k, v in campos.items() if k not in OPERATIVOS_EN_FILA} == {k: v for k, v in antes[1]["campos"].items() if k not in OPERATIVOS_EN_FILA}
    # exactamente 2 llamadas SharePoint: GET con ETag y MERGE condicionado a ESE ETag
    assert [c["metodo"] for c in llamadas(sp)] == ["GET", "POST"] and len(merges(sp)) == 1
    assert merges(sp)[0]["cabeceras"]["if-match"] == '"1"'
    assert set(merges(sp)[0]["cuerpo"]) == set(C.CAMPOS_ESCRITOS)
    assert len(r.eventos) == 21


def test_observacion_es_opcional_y_se_recorta_el_texto():
    sp = nueva()
    r = correr(sp, 1, estudiante="  Ana Perez  ", observacion="")
    assert r.respuesta["resultado"] == "ASIGNADO"
    assert sp.items[1]["campos"]["ESTUDIANTE"] == "Ana Perez" and sp.items[1]["campos"]["OBSERVACION"] == ""
    sp = nueva()
    entradas = entradas_asignar(1, clave(1))
    del entradas["text_5"]  # la app puede no enviarla
    assert asignar(ASIGNAR.construir_definicion(), sp, entradas).respuesta["resultado"] == "ASIGNADO"


# ------------------------------------------------------------------ clave incorrecta
@pytest.mark.parametrize("mala", ["", "X" + clave(1), clave(1) + " ", clave(1).lower(), clave(2), clave(1)[:-1]])
def test_clave_incorrecta_no_modifica_nada(mala):
    sp = nueva()
    antes = copy.deepcopy(sp.items)
    r = asignar(ASIGNAR.construir_definicion(), sp, entradas_asignar(1, mala))
    assert r.respuesta["resultado"] == "ERROR"
    assert r.respuesta["codigo"] in ("CLAVE_NO_COINCIDE", "CAMPOS_OBLIGATORIOS")
    assert sp.items == antes and not merges(sp)
    assert len(llamadas(sp)) <= 1


def test_id_de_otro_deposito_con_la_clave_de_este_no_modifica_ninguno():
    sp = nueva()
    antes = copy.deepcopy(sp.items)
    r = correr(sp, 2, clave_=clave(1))
    assert r.respuesta["codigo"] == "CLAVE_NO_COINCIDE"
    assert sp.items == antes


# ------------------------------------------------------------------ ya asignado
def test_ya_asignado_devuelve_no_disponible_y_no_pisa_la_primera_asignacion():
    sp = nueva()
    assert correr(sp, 1, estudiante="Primero", usuario="a@univalle.edu").respuesta["resultado"] == "ASIGNADO"
    despues_primera = copy.deepcopy(sp.items)
    sp.llamadas.clear()
    r = correr(sp, 1, estudiante="Segundo", usuario="b@univalle.edu")
    assert r.respuesta["resultado"] == "NO_DISPONIBLE" and r.respuesta["codigo"] == "NO_DISPONIBLE"
    assert (r.respuesta["estado_actual"], r.respuesta["asignado_por"]) == ("ASIGNADO", "a@univalle.edu")
    assert sp.items == despues_primera  # versión incluida: ni siquiera se intentó escribir
    assert [c["metodo"] for c in llamadas(sp)] == ["GET"] and not merges(sp)


# ------------------------------------------------------------------ concurrencia / ETag
@pytest.mark.parametrize("repeticion", range(15))
def test_dos_intentos_concurrentes_solo_uno_asigna(repeticion):
    sp = nueva()
    sp.barrera = threading.Barrier(2)  # ambos leen el MISMO ETag antes de que cualquiera escriba
    definicion = ASIGNAR.construir_definicion()
    salidas = {}

    def intento(quien):
        e = EnsayoP9(definicion, sp, entradas_asignar(3, clave(3), estudiante=f"Est-{quien}", usuario=f"{quien}@univalle.edu"))
        salidas[quien] = e.ejecutar()

    hilos = [threading.Thread(target=intento, args=(q,)) for q in ("a", "b")]
    [h.start() for h in hilos]
    [h.join(30) for h in hilos]
    assert all(not h.is_alive() for h in hilos)
    resultados = sorted(s.respuesta["resultado"] for s in salidas.values())
    assert resultados == ["ASIGNADO", "CONFLICTO"], resultados
    ganador = next(q for q, s in salidas.items() if s.respuesta["resultado"] == "ASIGNADO")
    perdedor = "b" if ganador == "a" else "a"
    assert sp.items[3]["campos"]["USUARIO_ASIGNACION"] == f"{ganador}@univalle.edu"
    assert sp.items[3]["campos"]["ESTUDIANTE"] == f"Est-{ganador}"
    assert sp.items[3]["version"] == 2  # una sola escritura efectiva
    assert salidas[perdedor].respuesta["codigo"] == "CONFLICTO"
    assert len(merges(sp)) == 2 and {m["cabeceras"]["if-match"] for m in merges(sp)} == {'"1"'}  # los dos con el ETag leído


def test_etag_desactualizado_devuelve_conflicto_y_no_escribe():
    sp = nueva()

    def otro_usuario_edita(id_, etag_recibido):  # entre la lectura y el MERGE, alguien toca el elemento
        sp.items[id_]["campos"]["OBSERVACION"] = "editado a mano"
        sp.items[id_]["version"] += 1
        sp.al_actualizar = None
    sp.al_actualizar = otro_usuario_edita
    r = correr(sp, 1)
    assert r.respuesta["resultado"] == "CONFLICTO" and r.respuesta["codigo"] == "CONFLICTO"
    assert sp.items[1]["campos"]["ESTADO_ASIGNACION"] == "DISPONIBLE" and sp.items[1]["campos"]["ESTUDIANTE"] is None
    assert sp.items[1]["campos"]["OBSERVACION"] == "editado a mano" and sp.items[1]["version"] == 2
    assert merges(sp)[0]["cabeceras"]["if-match"] == '"1"'  # el viejo, que SharePoint rechazó con 412
    assert len(merges(sp)) == 1 and len(llamadas(sp)) == 2  # sin reintentos ni lecturas adicionales


def test_nunca_se_usa_if_match_comodin_en_la_asignacion():
    sp = nueva()
    correr(sp, 1)
    assert all(m["cabeceras"]["if-match"] != "*" for m in merges(sp))


# ------------------------------------------------------------------ campos obligatorios y entradas inválidas
@pytest.mark.parametrize("campo,tecnico", [("estudiante", "ESTUDIANTE"), ("codigo", "CODIGO_ESTUDIANTE"), ("solicitado", "SOLICITADO_POR"),
                                           ("sede", "SEDE_ASIGNACION"), ("usuario", "USUARIO_ASIGNACION")])
@pytest.mark.parametrize("valor", ["", "   ", "\t\n"])
def test_campos_obligatorios_vacios_no_tocan_sharepoint(campo, tecnico, valor):
    sp = nueva()
    antes = copy.deepcopy(sp.items)
    r = correr(sp, 1, **{campo: valor})
    assert r.respuesta["resultado"] == "ERROR" and r.respuesta["codigo"] == "CAMPOS_OBLIGATORIOS", tecnico
    assert sp.llamadas == [] and sp.items == antes  # ni siquiera se lee


def test_campo_obligatorio_ausente_o_nulo_en_el_trigger():
    for omitido in ("text_1", "text_2", "text_3", "text_4", "text_6", "text"):
        sp = nueva()
        entradas = entradas_asignar(1, clave(1))
        entradas[omitido] = None
        r = asignar(ASIGNAR.construir_definicion(), sp, entradas)
        assert r.respuesta["resultado"] == "ERROR" and r.respuesta["codigo"] == "CAMPOS_OBLIGATORIOS" and sp.llamadas == []


@pytest.mark.parametrize("campo", ["estudiante", "codigo", "solicitado", "sede", "usuario"])
def test_texto_de_mas_de_255_caracteres_se_rechaza_antes_de_escribir(campo):
    sp = nueva()
    r = correr(sp, 1, **{campo: "x" * 256})
    assert r.respuesta["codigo"] == "CAMPO_EXCEDE_255" and sp.llamadas == []
    sp = nueva()
    assert correr(sp, 1, **{campo: "x" * 255}).respuesta["resultado"] == "ASIGNADO"


@pytest.mark.parametrize("id_", [0, -3, 1.5, None])
def test_id_invalido(id_):
    sp = nueva()
    r = correr(sp, id_, clave_=clave(1))
    assert r.respuesta["codigo"] == "ID_INVALIDO" and sp.llamadas == []


# ------------------------------------------------------------------ fallos de SharePoint
def test_id_inexistente():
    sp = nueva()
    r = correr(sp, 999, clave_=clave(1))
    assert (r.respuesta["resultado"], r.respuesta["codigo"]) == ("ERROR", "DEPOSITO_NO_ENCONTRADO") and not merges(sp)


@pytest.mark.parametrize("http", [500, 503, 429])
def test_fallo_al_leer(http):
    sp = nueva()
    sp.fallos["Leer_deposito"] = ("Failed", http)
    r = correr(sp, 1)
    assert (r.respuesta["resultado"], r.respuesta["codigo"]) == ("ERROR", "ERROR_LECTURA") and not merges(sp)
    sp = nueva()
    sp.fallos["Leer_deposito"] = ("TimedOut", 0)
    assert correr(sp, 1).respuesta["codigo"] == "ERROR_LECTURA"


@pytest.mark.parametrize("estado,http", [("Failed", 500), ("TimedOut", 0), ("Failed", 400)])
def test_fallo_al_actualizar_no_se_reporta_como_asignado_ni_se_reintenta(estado, http):
    sp = nueva()
    sp.fallos["Actualizar_deposito"] = (estado, http)
    r = correr(sp, 1)
    assert (r.respuesta["resultado"], r.respuesta["codigo"]) == ("ERROR", "ACTUALIZACION_NO_CONFIRMADA")
    assert "verifique" in r.respuesta["mensaje"] and len(merges(sp)) == 1
    assert sp.items[1]["campos"]["ESTADO_ASIGNACION"] == "DISPONIBLE"


def test_sin_etag_no_se_escribe():
    sp = nueva()
    sp.sin_etag = True
    r = correr(sp, 1)
    assert r.respuesta["codigo"] == "SIN_ETAG" and not merges(sp) and sp.items[1]["campos"]["ESTADO_ASIGNACION"] == "DISPONIBLE"


def test_etag_desde_cabecera_si_el_cuerpo_no_lo_trae():
    sp = nueva()
    original = sp._item

    def sin_etag_en_cuerpo(nombre, metodo, id_, seleccion, cabeceras, cuerpo):
        r = original(nombre, metodo, id_, seleccion, cabeceras, cuerpo)
        if metodo == "GET":
            r["body"]["d"]["__metadata"].pop("etag")
        return r
    sp._item = sin_etag_en_cuerpo
    assert correr(sp, 1).respuesta["resultado"] == "ASIGNADO"
    assert merges(sp)[0]["cabeceras"]["if-match"] == '"1"'


def test_estado_asignado_aun_no_habilitado_falla_sin_marcar_asignado():
    """Si P9_HABILITAR_ESTADO_ASIGNADO no se ejecutó, SharePoint rechaza el valor: ERROR y el depósito sigue DISPONIBLE."""
    sp = nueva(opciones=("DISPONIBLE",))
    r = correr(sp, 1)
    assert (r.respuesta["resultado"], r.respuesta["codigo"]) == ("ERROR", "ACTUALIZACION_NO_CONFIRMADA")
    assert sp.items[1]["campos"]["ESTADO_ASIGNACION"] == "DISPONIBLE" and sp.items[1]["version"] == 1


# ------------------------------------------------------------------ las 26 columnas del motor
def test_las_26_columnas_del_motor_no_cambian_con_ninguna_asignacion():
    sp = nueva()
    antes = motor26(sp)
    for i in range(1, 9):
        correr(sp, i, estudiante=f"Estudiante {i}")
    assert motor26(sp) == antes
    assert not set(C.CAMPOS_ESCRITOS) & set(C.COLUMNAS_MOTOR_26)
    assert all(set(m["cuerpo"]) <= set(C.CAMPOS_ESCRITOS) for m in merges(sp))


def test_contrato_de_26_columnas_identico_al_del_adaptador_y_al_motor():
    import adaptador_m365
    from helpers import cargar_motor
    assert len(C.COLUMNAS_MOTOR_26) == 26 and tuple(adaptador_m365.COLUMNAS_TECNICAS) == C.COLUMNAS_MOTOR_26
    assert len(cargar_motor().COLUMNAS_LISTS) == 26 and tuple(adaptador_m365.COLUMNAS_LISTS_P6) == tuple(cargar_motor().COLUMNAS_LISTS)
    esquema = json.loads((RAIZ / "p8/esquema_listas_p8.json").read_text(encoding="utf-8"))["Depositos_Activos"]["columnas"]
    assert [c["nombre_tecnico"] for c in esquema[:26]] == list(C.COLUMNAS_MOTOR_26)
    operativos = {c["nombre_tecnico"] for c in esquema[26:]}
    assert set(C.CAMPOS_ESCRITOS) == operativos  # el flujo escribe exactamente las 8 columnas operativas de P8


# Cambios posteriores al commit base, autorizados de forma explicita (archivo -> SHA-256 del contenido aprobado).
# P0 (2026-10): el control del año del motor deja de estar fijo en 2026 (D-08). Cualquier otro cambio del motor
# vuelve a fallar esta prueba hasta que se autorice aqui con su motivo.
EXCEPCIONES_AUTORIZADAS = {
    "motor_control_depositos_cbba.py": "c614d8518f8495c2a21464ece3b1559d8217813b93166350823615845524500c",
}


def test_archivos_p6_p7_p8_p85_sin_cambios_respecto_al_commit_base():
    """P9 es aditivo: ningún archivo existente en el commit base cambió (huellas congeladas desde ese commit)."""
    huellas = json.loads((RAIZ / "p9/evidencias/huellas_base_p8_5.json").read_text(encoding="utf-8"))
    assert huellas["base_commit"] == "c43585f71aea35e81b4c215f692d498b8e1087be"
    cambiados = []
    for f, h in huellas["archivos"].items():
        datos = (RAIZ / f).read_bytes()
        if f == "ESTADO_PROYECTO.md":
            # Fase B agrega únicamente la referencia documental prevista en I.6.
            # Se sigue verificando el hash de TODO el documento histórico; solo
            # se permite la adenda identificada, sin excluir el archivo del control.
            texto = datos.replace(b"\r\n", b"\n")
            separador = "\n\n## 7. P9 — reversión de confirmación (fase B local)\n".encode("utf-8")
            if separador in texto:
                assert texto.count(separador) == 1
                datos, adenda = texto.split(separador)
                assert b"DOCUMENTACION_P9_REVERSION.md" in adenda and b"DESPLIEGUE_P9_REVERSION.md" in adenda
        calculado = hashlib.sha256(datos).hexdigest()
        if calculado != h and EXCEPCIONES_AUTORIZADAS.get(f) != calculado:
            cambiados.append(f)
    assert cambiados == []
    assert not any(f.startswith("p9/") or f.startswith("P9_") or f.endswith("_P9.md") for f in huellas["archivos"])


# ------------------------------------------------------------------ reproceso P8
def _cargar_p8_y_asignar(n_asignar):
    from p8 import construir_paquete_p8 as paquete
    from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado
    p8 = json.loads(paquete.DEFINICION_SALIDA.read_text(encoding="utf-8"))
    artefacto = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    carga1 = SharePointSimulado(artefacto)
    EnsayoWDL(p8, carga1).ejecutar()
    assert len(carga1.activos) == 8
    # mismas filas, ahora como elementos de SharePoint P9 (el simulador de P8 usa 'ESTADO_ASIGNACION/Value')
    por_id = {}
    sp = SharePointP9([], opciones=DOS_ESTADOS)
    for i, (k, fila) in enumerate(carga1.activos.items(), 1):
        f = {c: v for c, v in fila.items() if c != "ESTADO_ASIGNACION/Value"}
        f["ESTADO_ASIGNACION"] = fila["ESTADO_ASIGNACION/Value"]
        sp.agregar(i, f)
        por_id[i] = k
    for i in range(1, n_asignar + 1):
        assert correr(sp, i, clave_=por_id[i], estudiante=f"Est {i}").respuesta["resultado"] == "ASIGNADO"
    return p8, artefacto, sp, por_id, paquete


def test_reproceso_p8_no_devuelve_asignado_a_disponible():
    from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado
    p8, artefacto, sp, por_id, _ = _cargar_p8_y_asignar(5)
    # el elemento SharePoint P9 pasa a ser lo «ya existente» que ve P8 (con las columnas operativas intactas)
    existentes = {}
    for i, it in sp.items.items():
        fila = {c: v for c, v in it["campos"].items() if c != "ESTADO_ASIGNACION"}
        fila["ESTADO_ASIGNACION/Value"] = it["campos"]["ESTADO_ASIGNACION"]
        existentes[por_id[i]] = fila
    antes = copy.deepcopy(existentes)
    reproceso = SharePointSimulado(artefacto, existentes=existentes)
    EnsayoWDL(p8, reproceso).ejecutar()
    b = reproceso.bitacoras[-1]
    assert (b["CANTIDAD_NUEVA"], b["CANTIDAD_YA_EXISTE"], b["CANTIDAD_ERROR"]) == (0, 8, 0) and b["ESTADO_LOTE/Value"] == "COMPLETADO"
    assert reproceso.activos == antes  # ni un campo de ningún elemento cambió
    asignados = [f for f in reproceso.activos.values() if f["ESTADO_ASIGNACION/Value"] == "ASIGNADO"]
    assert len(asignados) == 5 and all(f["ESTUDIANTE"].startswith("Est ") for f in asignados)
    assert [c[0] for c in reproceso.llamadas].count("Crear_movimiento") == 0  # P8 no escribió nada


def test_p8_solo_puede_crear_y_nunca_actualiza_ni_borra():
    from p8 import construir_paquete_p8 as paquete
    p8 = json.loads(paquete.DEFINICION_SALIDA.read_text(encoding="utf-8"))
    operaciones = {a["inputs"]["host"]["operationId"] for _, a in recorrer(p8["actions"]) if a["type"] == "OpenApiConnection"}
    assert operaciones == {"GetFileContent", "GetItems", "PostItem"}  # sin PatchItem, DeleteItem ni HttpRequest
    escriben_estado = [n for n, a in recorrer(p8["actions"]) if a["type"] == "OpenApiConnection"
                       and "item/ESTADO_ASIGNACION/Value" in a["inputs"]["parameters"]]
    assert escriben_estado == ["Crear_movimiento"]
    assert "MERGE" not in json.dumps(p8) and "DELETE" not in json.dumps(p8)


def test_reproceso_p8_con_clave_ya_asignada_clasifica_ya_existe_sin_tocarla():
    """Carrera de creación: P8 intenta crear una clave que P9 ya asignó → 409 de unicidad → YA_EXISTE, ASIGNADO intacto."""
    from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado
    p8, artefacto, sp, por_id, _ = _cargar_p8_y_asignar(1)
    fila = {c: v for c, v in sp.items[1]["campos"].items() if c != "ESTADO_ASIGNACION"}
    fila["ESTADO_ASIGNACION/Value"] = "ASIGNADO"
    existentes = {por_id[1]: fila}
    antes = copy.deepcopy(existentes)
    reproceso = SharePointSimulado(artefacto, existentes=existentes)
    EnsayoWDL(p8, reproceso).ejecutar()
    assert reproceso.activos[por_id[1]] == antes[por_id[1]]
    assert reproceso.activos[por_id[1]]["ESTADO_ASIGNACION/Value"] == "ASIGNADO"


# ------------------------------------------------------------------ P9_HABILITAR_ESTADO_ASIGNADO
def habilitar(sp):
    e = EnsayoP9(HABILITAR.construir_definicion(), sp).ejecutar()
    return e, e.salidas["RESUMEN_FINAL"]


def test_habilitar_agrega_asignado_y_es_idempotente():
    sp = nueva(opciones=("DISPONIBLE",))
    items = copy.deepcopy(sp.items)
    e, resumen = habilitar(sp)
    assert e.estado_final == "Succeeded" and resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK", resumen
    assert (resumen["accion"], resumen["estado_antes"], resumen["opciones_despues"]) == ("HABILITADO", "POR_HABILITAR", "DISPONIBLE|ASIGNADO")
    assert sp.opciones == ["DISPONIBLE", "ASIGNADO"] and sp.items == items  # no toca ningún elemento
    assert all(not c["uri"].startswith(f"_api/web/lists(guid'{C.LISTA_DEPOSITOS_ACTIVOS_ID}')/items") for c in sp.llamadas)
    assert len(merges_choices(sp)) == 1 and len(merges_indices(sp)) == 3 and len(merges(sp)) == 4
    sp.llamadas.clear()
    e2, resumen2 = habilitar(sp)
    assert resumen2["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK" and resumen2["accion"] == "NINGUNA" and resumen2["estado_antes"] == "YA_HABILITADO"
    assert merges(sp) == [] and all(c["metodo"] == "GET" for c in sp.llamadas)


def test_habilitar_y_luego_asignar_de_extremo_a_extremo():
    sp = nueva(opciones=("DISPONIBLE",))
    assert correr(sp, 1).respuesta["codigo"] == "ACTUALIZACION_NO_CONFIRMADA"  # antes de habilitar
    habilitar(sp)
    assert correr(sp, 1).respuesta["resultado"] == "ASIGNADO"


@pytest.mark.parametrize("opciones", [["DISPONIBLE", "OTRO"], ["DISPONIBLE", "ASIGNADO", "OTRO"], ["ASIGNADO", "DISPONIBLE"], ["ASIGNADO"], ["OTRO"]])
def test_habilitar_no_escribe_ante_opciones_inesperadas(opciones):
    sp = nueva(opciones=opciones)
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL" and e.estado_final == "Failed"
    assert resumen["estado_antes"] == "INESPERADO" and merges_choices(sp) == [] and sp.opciones == opciones
    assert resumen["diferencias"][0]["propiedades"] == "Choices;"


@pytest.mark.parametrize("propiedad,valor,marca", [("Required", False, "Required;"),
                                                   ("DefaultValue", "ASIGNADO", "DefaultValue;"), ("TypeAsString", "Text", "TypeAsString;"),
                                                   ("Hidden", True, "Hidden;")])
def test_habilitar_reporta_propiedades_distintas(propiedad, valor, marca):
    sp = nueva(opciones=DOS_ESTADOS)
    sp.campo_extra[propiedad] = valor
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL" and marca in resumen["diferencias"][0]["propiedades"] and merges_choices(sp) == []


def test_habilitar_falla_si_la_columna_no_existe_o_hay_error_rest():
    sp = nueva()
    sp.fallos["Leer_campo_antes"] = ("Failed", 500)
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL" and e.estado_final == "Failed" and resumen["diferencias"][0]["propiedades"] == "REST_LEER_ANTES"
    sp = nueva(opciones=("DISPONIBLE",))
    sp.fallos["Habilitar_ASIGNADO"] = ("Failed", 403)
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL" and resumen["diferencias"][0]["propiedades"] == "REST_HABILITAR" and sp.opciones == ["DISPONIBLE"]


def test_habilitar_usa_el_patron_rest_de_p8_y_solo_toca_su_campo():
    d = HABILITAR.construir_definicion()
    acciones = dict(recorrer(d["actions"]))
    habilitar_ = acciones["Habilitar_ASIGNADO"]["inputs"]["parameters"]
    assert habilitar_["parameters/method"] == "POST" and habilitar_["parameters/headers"]["X-HTTP-Method"] == "MERGE"
    assert habilitar_["parameters/headers"]["IF-MATCH"] == "*"  # mismo patrón que P8 (cuerpo = definición de una columna)
    assert acciones["Cuerpo_habilitar"]["inputs"]["Choices"]["results"] == ["DISPONIBLE", "ASIGNADO"]
    assert d["triggers"]["manual"]["inputs"]["schema"]["properties"] == {}
    http = [(n, a["inputs"]["parameters"]["parameters/method"]) for n, a in acciones.items() if a["type"] == "OpenApiConnection"]
    assert sorted(n for n, m in http if m == "POST") == ["Crear_indice", "Habilitar_ASIGNADO"]
    assert {m for _, m in http} == {"GET", "POST"}
    assert not any("/items" in json.dumps(a["inputs"]["parameters"]["parameters/uri"]) for a in acciones.values() if a["type"] == "OpenApiConnection")


def test_p8_provision_reportaria_choices_distintas_tras_p9_pero_no_repara():
    """Limitación documentada: re-ejecutar el provisionador P8 tras habilitar ASIGNADO da FAIL en Choices, sin escribir."""
    import hashlib as h
    from p8.provision.construir import FUENTE, compilar, construir_definicion
    from p8.provision.ensayo import ejecutar
    definicion = construir_definicion(compilar(json.loads(FUENTE.read_text())), h.sha256(FUENTE.read_bytes()).hexdigest())
    _, rest = ejecutar(definicion)
    campo = rest.listas["Depositos_Activos"]["fields"]["ESTADO_ASIGNACION"]
    campo["SchemaXml"] = campo["SchemaXml"].replace("<CHOICE>DISPONIBLE</CHOICE>", "<CHOICE>DISPONIBLE</CHOICE><CHOICE>ASIGNADO</CHOICE>")
    rest.llamadas.clear()
    e, _ = ejecutar(definicion, rest)
    resumen = e.salidas["RESUMEN_FINAL"]
    assert resumen["PROVISION_P8"] == "FAIL"
    assert [d["campo"] for d in resumen["diferencias"]] == ["ESTADO_ASIGNACION"] and resumen["diferencias"][0]["propiedad"] == "Choices"
    assert all(c["metodo"] == "GET" for c in rest.llamadas)



# ------------------------------------------------------------------ P9_HABILITAR_ESTADO_ASIGNADO: índices
NUEVOS = [n for n, _ in C.INDICES_NUEVOS]
ANTIGUOS = [n for n, _ in C.INDICES_EXISTENTES]


def sin_items_tocados(sp, items_antes):
    assert sp.items == items_antes, "ningún elemento de Depositos_Activos puede cambiar (ni datos ni versión)"
    assert not [c for c in sp.llamadas if "/items" in c["uri"]], "el provisionador no debe ni leer elementos"


def test_contrato_de_indices_es_el_pedido_y_coincide_con_el_esquema_p8():
    assert ANTIGUOS == ["ESTADO_ASIGNACION", "FECHA_MOVIMIENTO", "BANCO", "LOTE_CARGA"]
    assert NUEVOS == ["CODIGO_ASIGNACION", "IMPORTE", "TIPO_MOVIMIENTO"] and len(C.INDICES) == 7
    esquema = {c["nombre_tecnico"]: c for c in json.loads((RAIZ / "p8/esquema_listas_p8.json").read_text(encoding="utf-8"))["Depositos_Activos"]["columnas"]}
    meta = {"Texto de una linea": "SP.FieldText", "Numero, 2 decimales": "SP.FieldNumber", "Fecha y hora, solo fecha": "SP.FieldDateTime",
            "Opcion": "SP.FieldChoice"}
    for nombre, tipo in C.INDICES:
        assert meta[esquema[nombre]["tipo"]] == tipo, nombre  # el tipo REST es el de la columna real
    assert all(esquema[n]["indexada"] for n in ANTIGUOS) and not any(esquema[n]["indexada"] for n in NUEVOS)  # P8 no los indexó
    assert set(NUEVOS) <= set(C.COLUMNAS_MOTOR_26) and not set(NUEVOS) & set(C.CAMPOS_ESCRITOS)  # columnas del motor: solo se indexan


def test_indices_el_flujo_solo_puede_indexar_nunca_quitar():
    d = HABILITAR.construir_definicion()
    cuerpos = [json.loads(i["cuerpo"]) for i in d["actions"]["PARAM_INDICES"]["inputs"]]
    assert [c["__metadata"]["type"] for c in cuerpos] == [t for _, t in C.INDICES]
    assert all(set(c) == {"__metadata", "Indexed"} and c["Indexed"] is True for c in cuerpos)
    assert [i["nombre"] for i in d["actions"]["PARAM_INDICES"]["inputs"]] == [n for n, _ in C.INDICES] == d["actions"]["PARAM_NOMBRES_INDICES"]["inputs"]
    texto = json.dumps(d)
    assert "\\\"Indexed\\\":false" not in texto and "DELETE" not in texto and "false" not in json.dumps(d["actions"]["PARAM_INDICES"])
    acciones = dict(recorrer(d["actions"]))
    merge = acciones["Crear_indice"]["inputs"]["parameters"]
    assert merge["parameters/headers"]["X-HTTP-Method"] == "MERGE" and merge["parameters/headers"]["IF-MATCH"] == "*"
    assert merge["parameters/body"] == "@items('Aplicar_a_cada_indice')?['cuerpo']"
    assert acciones["Aplicar_a_cada_indice"]["runtimeConfiguration"]["concurrency"]["repetitions"] == 1
    # solo se crea si el campo existe y NO está indexado
    assert acciones["Ya_indexado"]["expression"] == "@equals(first(body('Campo_indice'))?['Indexed'],true)"
    assert list(acciones["Ya_indexado"]["actions"]) == ["Anotar_indice_existente"] and "TRY_INDICE" in acciones["Ya_indexado"]["else"]["actions"]


def test_indices_todos_ya_existen_no_crea_ni_falla():
    sp = SharePointP9(filas(), opciones=DOS_ESTADOS, indexados="P9")
    antes, campos = copy.deepcopy(sp.items), copy.deepcopy(sp.campos)
    e, resumen = habilitar(sp)
    assert e.estado_final == "Succeeded" and resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK", resumen
    assert resumen["indices_creados"] == [] and resumen["indices_ya_existian"] == [n for n, _ in C.INDICES]
    assert resumen["indices_verificados_al_final"] == 7 and resumen["diferencias"] == []
    assert merges(sp) == [] and all(c["metodo"] == "GET" for c in sp.llamadas)  # solo lecturas
    assert sp.campos == campos
    sin_items_tocados(sp, antes)


def test_indices_faltan_los_tres_nuevos_los_crea_y_conserva_los_existentes():
    sp = nueva(opciones=DOS_ESTADOS)  # estado real del piloto: índices de P8 sí, los 3 nuevos no
    assert not set(NUEVOS) & sp.indexados() and set(ANTIGUOS) <= sp.indexados()
    antes, antes_indexados, campos = copy.deepcopy(sp.items), sp.indexados(), set(sp.campos)
    e, resumen = habilitar(sp)
    assert e.estado_final == "Succeeded" and resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK", resumen
    assert resumen["indices_creados"] == NUEVOS and resumen["indices_ya_existian"] == ANTIGUOS
    assert resumen["indices_verificados_al_final"] == 7 and resumen["diferencias"] == []
    assert sp.indexados() == antes_indexados | set(NUEVOS)  # nada se quitó; solo se agregaron 3
    assert [m["cuerpo"] for m in merges_indices(sp)] == [{"__metadata": {"type": t}, "Indexed": True} for _, t in C.INDICES_NUEVOS]
    assert len(merges_indices(sp)) == 3 and merges_choices(sp) == []  # opciones ya estaban: no se reescriben
    assert set(sp.campos) == campos  # no se creó ni borró ninguna columna
    sin_items_tocados(sp, antes)


@pytest.mark.parametrize("falta", ANTIGUOS)
def test_indices_falta_uno_de_los_antiguos_se_crea_sin_tocar_los_demas(falta):
    sp = SharePointP9(filas(), opciones=DOS_ESTADOS, indexados=set(n for n, _ in C.INDICES) - {falta})
    antes, antes_indexados = copy.deepcopy(sp.items), sp.indexados()
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK", resumen
    assert resumen["indices_creados"] == [falta] and len(resumen["indices_ya_existian"]) == 6 and falta not in resumen["indices_ya_existian"]
    assert [m["cuerpo"]["__metadata"]["type"] for m in merges_indices(sp)] == [dict(C.INDICES)[falta]]
    assert sp.indexados() == antes_indexados | {falta} and resumen["indices_verificados_al_final"] == 7
    sin_items_tocados(sp, antes)


def test_indices_faltan_nuevos_y_un_antiguo_a_la_vez():
    sp = nueva(opciones=DOS_ESTADOS)
    sp.campos["BANCO"]["Indexed"] = False
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK" and resumen["indices_creados"] == ["BANCO", *NUEVOS]
    assert {n for n, _ in C.INDICES} <= sp.indexados()


def test_indices_ejecutar_dos_veces_es_idempotente():
    sp = nueva(opciones=("DISPONIBLE",))  # primera vez: habilita ASIGNADO y crea los 3 índices
    antes = copy.deepcopy(sp.items)
    e1, r1 = habilitar(sp)
    assert r1["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK" and r1["accion"] == "HABILITADO" and r1["indices_creados"] == NUEVOS
    estado = (copy.deepcopy(sp.campos), list(sp.opciones))
    sp.llamadas.clear()
    e2, r2 = habilitar(sp)
    assert e2.estado_final == "Succeeded" and r2["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK"
    assert (r2["accion"], r2["indices_creados"], r2["indices_verificados_al_final"]) == ("NINGUNA", [], 7)
    assert r2["indices_ya_existian"] == [n for n, _ in C.INDICES]
    assert merges(sp) == [] and all(c["metodo"] == "GET" for c in sp.llamadas)  # cero escrituras
    assert (sp.campos, sp.opciones) == estado
    sin_items_tocados(sp, antes)


@pytest.mark.parametrize("fallo", [("Failed", 500), ("Failed", 403), ("TimedOut", 0)])
def test_indices_fallo_controlado_al_crear_uno(fallo):
    sp = nueva(opciones=DOS_ESTADOS)
    sp.fallos_indice["IMPORTE"] = fallo
    antes = copy.deepcopy(sp.items)
    e, resumen = habilitar(sp)  # no lanza: el fallo queda reportado
    assert e.estado_final == "Failed" and resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL"
    assert resumen["indices_creados"] == ["CODIGO_ASIGNACION", "TIPO_MOVIMIENTO"]  # el bucle siguió con los demás
    props = {d["propiedades"]: d for d in resumen["diferencias"]}
    assert props["INDICE_NO_CREADO"]["opciones_observadas"] == "IMPORTE" and props["INDICE_NO_CREADO"]["opciones_esperadas"] == f"HTTP {fallo[1]}"
    assert props["INDICE_AUSENTE_O_NO_INDEXADO"]["opciones_observadas"] == "IMPORTE"  # la verificación final lo confirma
    assert resumen["indices_verificados_al_final"] == 6 and "IMPORTE" not in sp.indexados()
    sin_items_tocados(sp, antes)
    # recuperación: al corregir la causa, reejecutar crea solo el que faltaba
    sp.fallos_indice.clear()
    e2, r2 = habilitar(sp)
    assert r2["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK" and r2["indices_creados"] == ["IMPORTE"] and r2["indices_verificados_al_final"] == 7


def test_indices_fallo_al_leer_los_campos_no_escribe_nada():
    sp = nueva(opciones=DOS_ESTADOS)
    sp.fallos["Leer_campos_antes_indices"] = ("Failed", 500)
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL" and resumen["diferencias"][0]["propiedades"] == "REST_INDICES"
    assert merges(sp) == [] and not set(NUEVOS) & sp.indexados()


def test_indices_columna_ausente_falla_sin_crear_columnas():
    sp = nueva(opciones=DOS_ESTADOS)
    del sp.campos["IMPORTE"]
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL"
    assert any(d["propiedades"] == "CAMPO_AUSENTE_O_NO_UNICO" and d["opciones_observadas"] == "IMPORTE" for d in resumen["diferencias"])
    assert "IMPORTE" not in sp.campos and resumen["indices_creados"] == ["CODIGO_ASIGNACION", "TIPO_MOVIMIENTO"]


@pytest.mark.parametrize("accion", ["Leer_campos_antes_indices", "Leer_campos_despues_indices"])
def test_indices_respuesta_paginada_no_se_certifica(accion):
    sp = nueva(opciones=DOS_ESTADOS)
    sp.paginar = {accion}
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "FAIL" and any(d["propiedades"] == "PAGINACION" for d in resumen["diferencias"])
    if accion == "Leer_campos_antes_indices":
        assert merges_indices(sp) == []  # con inventario parcial no se crea nada


def test_indices_no_modifican_items_ni_las_26_columnas_ni_el_estado():
    sp = nueva(opciones=("DISPONIBLE",))
    antes, m26 = copy.deepcopy(sp.items), motor26(sp)
    e, resumen = habilitar(sp)
    assert resumen["P9_HABILITAR_ESTADO_ASIGNADO"] == "OK"
    sin_items_tocados(sp, antes)
    assert motor26(sp) == m26
    assert all(sp.items[i]["campos"]["ESTADO_ASIGNACION"] == "DISPONIBLE" and sp.items[i]["version"] == 1 for i in sp.items)
    assert sp.opciones == ["DISPONIBLE", "ASIGNADO"] and tuple(sp.opciones) == C.ESTADOS  # solo esos dos estados


def test_indices_creados_no_afectan_a_la_asignacion():
    sp = nueva(opciones=("DISPONIBLE",))
    habilitar(sp)
    assert correr(sp, 1).respuesta["resultado"] == "ASIGNADO"
    assert sp.indexados() >= {n for n, _ in C.INDICES}

# ------------------------------------------------------------------ documentación
def test_documentacion_cita_las_cifras_reales():
    doc = (RAIZ / "DOCUMENTACION_P9_POWER_APPS.md").read_text(encoding="utf-8")
    a, h = contar_acciones(ASIGNAR.construir_definicion()["actions"]), contar_acciones(HABILITAR.construir_definicion()["actions"])
    assert f"{a} acciones" in doc and f"{h} acciones" in doc
    for texto in ("P9_ASIGNAR_DEPOSITO_POWERAPPS_V4_2_FIRMA_8_POSICIONALES.zip", "P9_HABILITAR_ESTADO_ASIGNADO.zip",
                  "P9_CONTROL_INGRESOS_FINAL_2M_SIN_CODIGO_ESTUDIANTE.txt", "If-Match", "ETag", "premium"):
        assert texto in doc, texto
