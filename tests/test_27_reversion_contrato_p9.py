"""Contrato V2 y ejecución del WDL de provisión contra REST local simulado.

No certifica el tenant. Se reutiliza únicamente el intérprete de provisión P8;
el adaptador local añade Id/versionado y comprueba que nunca se escriban items.
"""
import copy
import hashlib
import json
import re
import uuid
import zipfile
from xml.etree import ElementTree as ET

import pytest

from p8.provision.ensayo import EnsayoProvision, SharePointREST
from p9.reversion import contrato as C
from p9.reversion.provisionar import compilar, construir_definicion
from p9.wdl import recorrer


NOMBRES_V2 = {
    "SOLICITUD_UID", "DEPOSITO_ID", "LISTA_DEPOSITO_ID", "CLAVE_TRANSACCION", "CLAVE_BLOQUEO",
    "BANCO", "CUENTA_BANCARIA", "FECHA_MOVIMIENTO", "IMPORTE", "MONEDA", "CODIGO_ASIGNACION",
    "ESTUDIANTE", "CODIGO_ESTUDIANTE", "SOLICITADO_POR", "SEDE_ASIGNACION", "USUARIO_ASIGNACION",
    "FECHA_HORA_ASIGNACION", "OBSERVACION", "ETAG_SOLICITUD", "SNAPSHOT_JSON", "MOTIVO_REVERSION",
    "SOLICITANTE_ID", "SOLICITANTE_UPN", "FECHA_SOLICITUD", "FECHA_LIMITE", "ESTADO_SOLICITUD",
    "FASE_PROCESO", "RESULTADO_TECNICO", "CONFIG_APROBACION_JSON", "APROBACION_ID", "APROBADOR_ID",
    "APROBADOR_UPN", "FECHA_DECISION", "COMENTARIO_APROBADOR", "RESPUESTA_APROBACION_JSON",
    "FECHA_EJECUCION_REVERSION", "ETAG_EJECUCION", "ERROR_TECNICO", "FECHA_CIERRE", "RUN_ID",
    "BITACORA_TECNICA_JSON",
}
UID = "72bed3bd-a30e-47f9-b226-2c06cbd2f573"
LISTA = "d5e64a21-680a-4d07-8e9d-5a5a2c788f94"


class RESTReversion(SharePointREST):
    def nueva_lista(self, nombre):
        lista = super().nueva_lista(nombre)
        lista["meta"].update(Id=str(uuid.uuid5(uuid.NAMESPACE_URL, "mock:" + nombre)), EnableVersioning=True)
        return lista

    def ejecutar(self, nombre, parametros):
        headers = parametros["parameters/headers"]
        assert all(v != "*" for k, v in headers.items() if k.lower() == "if-match")
        assert "/items" not in parametros["parameters/uri"].lower()
        if parametros["parameters/method"] == "POST" and headers.get("X-HTTP-Method") == "MERGE":
            assert "/fields" in parametros["parameters/uri"]
        return super().ejecutar(nombre, parametros)


class EnsayoReversion(EnsayoProvision):
    def _nodo(self, nodo):
        if nodo[0] == "funcion" and nodo[1] == "result":
            nombre = self._nodo(nodo[2][0])
            return [{"name": nombre, "status": self.estados.get(nombre)}]
        return super()._nodo(nodo)


def ejecutar(sp=None):
    sp = sp or RESTReversion()
    if C.LISTA_DEPOSITOS not in sp.listas:
        lista = sp.nueva_lista(C.LISTA_DEPOSITOS)
        lista["fields"]["CAMPO_MOTOR_PREEXISTENTE"] = sp._campo_xml('<Field Name="CAMPO_MOTOR_PREEXISTENTE" Type="Text"/>')
        lista["items"] = [{"ID": 7, "CAMPO_MOTOR_PREEXISTENTE": "conservar"}]
    return EnsayoReversion(construir_definicion(), sp).ejecutar(), sp


def resumen(ensayo):
    return ensayo.salidas["RESUMEN_FINAL"]


def test_esquema_completo_v2_y_marker_opcional():
    esquema = C.cargar_esquema()
    campos = {c["nombre_tecnico"]: c for c in esquema[C.LISTA_REVERSIONES]["columnas"]}
    assert set(campos) == NOMBRES_V2
    assert len(campos) == 41
    assert all(campos[n]["obligatoria"] and campos[n]["valores_unicos"] and campos[n]["indexada"] for n in ("SOLICITUD_UID", "CLAVE_BLOQUEO"))
    assert campos["IMPORTE"]["decimals"] == 2 and "min" not in campos["IMPORTE"]
    assert campos["DEPOSITO_ID"]["decimals"] == 0 and campos["DEPOSITO_ID"]["min"] == 1
    assert campos["OBSERVACION"]["tipo"] == "Note" and "max_length" not in campos["OBSERVACION"]
    assert campos["MOTIVO_REVERSION"]["max_length_aplicacion"] == 4000
    assert campos["FECHA_MOVIMIENTO"]["format"] == "DateOnly"
    assert all(campos[n]["format"] == "DateTime" for n in ("FECHA_SOLICITUD", "FECHA_LIMITE", "FECHA_CIERRE"))
    assert len(C.FASES) == 6 and len(C.RESULTADOS_TECNICOS) == 8
    assert set(C.ESTADOS_SOLICITUD) == {"PENDIENTE", "APROBADO", "RECHAZADO"}
    assert C.PLAZO_HORAS == 168 and len(C.CAMPOS_SNAPSHOT) == 34
    assert len(set(C.CAMPOS_SNAPSHOT)) == 34
    marcador = esquema[C.LISTA_DEPOSITOS]["columnas"][0]
    assert marcador["nombre_tecnico"] == "ULTIMA_REVERSION_ID"
    assert not marcador["obligatoria"] and not marcador["indexada"] and "predeterminado" not in marcador


def test_payload_exacto_no_toca_datos_del_motor_y_claves_canonicas():
    payload = C.payload_reversion(UID.upper())
    assert set(payload) == set(C.CAMPOS_ESCRITOS) and len(payload) == 9
    assert all(payload[k] is None for k in C.CAMPOS_LIMPIAR)
    assert payload["ESTADO_ASIGNACION"] == "DISPONIBLE" and payload["ULTIMA_REVERSION_ID"] == UID
    assert not set(C.CAMPOS_MOTOR) & set(payload)
    assert C.clave_activa(LISTA.upper(), 7) == "ACTIVA|" + LISTA + "|7"
    assert C.clave_cerrada(UID.upper()) == "CERRADA|" + UID


@pytest.mark.parametrize("cambio", ["quitar", "tipo", "requerido", "max_length", "opciones"])
def test_validador_rechaza_contrato_debilitado(cambio):
    esquema = C.cargar_esquema()
    campos = esquema[C.LISTA_REVERSIONES]["columnas"]
    if cambio == "quitar":
        campos[:] = [c for c in campos if c["nombre_tecnico"] != "OBSERVACION"]
    elif cambio == "tipo":
        next(c for c in campos if c["nombre_tecnico"] == "OBSERVACION")["tipo"] = "Text"
    elif cambio == "requerido":
        next(c for c in campos if c["nombre_tecnico"] == "ETAG_SOLICITUD")["obligatoria"] = False
    elif cambio == "max_length":
        next(c for c in campos if c["nombre_tecnico"] == "CUENTA_BANCARIA")["max_length"] = 30
    else:
        next(c for c in campos if c["nombre_tecnico"] == "RESULTADO_TECNICO")["valores"].append("OTRO")
    with pytest.raises(ValueError):
        C.validar_esquema(esquema)


@pytest.mark.parametrize("uid", ["", "x", "{" + UID + "}", "00000000-0000-0000-0000-000000000000", UID.replace("-", "")])
def test_uid_invalido(uid):
    with pytest.raises(ValueError):
        C.payload_reversion(uid)


@pytest.mark.parametrize("identificador", [0, -1, "7", 7.5, True])
def test_id_invalido(identificador):
    with pytest.raises(ValueError):
        C.clave_activa(LISTA, identificador)


def test_compilacion_crea_nombre_ascii_y_titulo_despues_por_guid():
    plan = compilar()
    assert [p["Nombre"] for p in plan] == [C.LISTA_DEPOSITOS, C.LISTA_REVERSIONES]
    assert plan[0]["PermitirCrear"] is False and plan[1]["PermitirCrear"] is True
    for lista in plan:
        for campo in lista["Campos"]:
            xml = ET.fromstring(campo["Crear"]["parameters"]["SchemaXml"])
            assert xml.get("Name") == xml.get("StaticName") == xml.get("DisplayName") == campo["Nombre"]
            assert xml.get("ID") is None
            assert campo["Configurar"]["Title"] == campo["NombreVisible"]


def test_provision_y_reproceso_sin_modificar_items_o_campos_previos():
    e, sp = ejecutar()
    assert e.estado_final == "Succeeded", resumen(e)
    assert resumen(e)["PROVISION_P9_REVERSION"] == "OK"
    assert len(sp.listas[C.LISTA_REVERSIONES]["fields"]) == 42
    assert sp.listas[C.LISTA_REVERSIONES]["fields"]["Title"]["Required"] is False
    assert set(sp.listas[C.LISTA_DEPOSITOS]["fields"]) == {"Title", "CAMPO_MOTOR_PREEXISTENTE", "ULTIMA_REVERSION_ID"}
    assert len(resumen(e)["listas"]) == 2 and all(uuid.UUID(l["id"]) for l in resumen(e)["listas"])
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(sp)
    assert e.estado_final == "Succeeded", resumen(e)
    assert sp.listas == antes and all(c["metodo"] == "GET" for c in sp.llamadas)


@pytest.mark.parametrize("propiedad,valor", [("Required", False), ("Indexed", False), ("EnforceUniqueValues", False),
                                           ("TypeAsString", "Number"), ("Title", "Distinto"), ("Hidden", True)])
def test_diferencias_de_esquema_fallan_sin_reparar_datos(propiedad, valor):
    _, sp = ejecutar()
    sp.listas[C.LISTA_REVERSIONES]["fields"]["SOLICITUD_UID"][propiedad] = valor
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(sp)
    assert e.estado_final == "Failed" and resumen(e)["PROVISION_P9_REVERSION"] == "FAIL"
    assert any(d["campo"] == "SOLICITUD_UID" and d["propiedad"] == propiedad for d in resumen(e)["diferencias"])
    assert sp.listas == antes and all(c["metodo"] == "GET" for c in sp.llamadas)


@pytest.mark.parametrize("campo,atributo,valor", [("OBSERVACION", "RichText", "TRUE"), ("BITACORA_TECNICA_JSON", "AppendOnly", "TRUE"),
                                                ("IMPORTE", "Decimals", "0"), ("CUENTA_BANCARIA", "MaxLength", "30"),
                                                ("FECHA_SOLICITUD", "Format", "DateOnly"), ("FASE_PROCESO", "FillInChoice", "TRUE")])
def test_schema_xml_real_verificado(campo, atributo, valor):
    _, sp = ejecutar()
    c = sp.listas[C.LISTA_REVERSIONES]["fields"][campo]
    xml = ET.fromstring(c["SchemaXml"])
    xml.set(atributo, valor)
    c["SchemaXml"] = ET.tostring(xml, encoding="unicode")
    e, _ = ejecutar(sp)
    assert e.estado_final == "Failed"
    assert any(d["campo"] == campo and d["propiedad"] == atributo for d in resumen(e)["diferencias"])


def test_versionado_y_guid_reales_obligatorios():
    _, sp = ejecutar()
    sp.listas[C.LISTA_REVERSIONES]["meta"]["EnableVersioning"] = False
    sp.listas[C.LISTA_DEPOSITOS]["meta"]["Id"] = None
    e, _ = ejecutar(sp)
    assert e.estado_final == "Failed"
    assert sum(d["propiedad"] == "CONFIGURACION_LISTA" for d in resumen(e)["diferencias"]) >= 2


@pytest.mark.parametrize("accion", ["Buscar_lista", "Crear_lista", "Crear_columna", "Configurar_columna_nueva", "Exigir_unicidad", "Campos_finales"])
def test_fallos_rest_no_certifican(accion):
    sp = RESTReversion()
    sp.fallos[accion] = ("Failed", 403)
    e, _ = ejecutar(sp)
    assert e.estado_final == "Failed"
    assert resumen(e)["diferencias"]


@pytest.mark.parametrize("etapa", ["Campos_antes", "Campos_finales"])
def test_inventario_parcial_no_certifica(etapa):
    sp = RESTReversion()
    sp.paginar.add(etapa)
    e, _ = ejecutar(sp)
    assert e.estado_final == "Failed" and any(d["propiedad"].startswith("PAGINACION") for d in resumen(e)["diferencias"])
    if etapa == "Campos_antes":
        assert not any(c["accion"] == "Crear_columna" for c in sp.llamadas)


def test_no_crea_lista_depositos_ausente():
    sp = RESTReversion()
    e = EnsayoReversion(construir_definicion(), sp).ejecutar()
    assert e.estado_final == "Failed"
    assert C.LISTA_DEPOSITOS not in sp.listas


def test_titulo_ambiguo_no_provisiona_ninguna_columna():
    class Duplicada(RESTReversion):
        def ejecutar(self, nombre, parametros):
            respuesta = super().ejecutar(nombre, parametros)
            if nombre == "Buscar_lista":
                respuesta["body"]["value"] = respuesta["body"]["value"] * 2
            return respuesta
    _, base = ejecutar()
    sp = Duplicada()
    sp.listas = copy.deepcopy(base.listas)
    del sp.listas[C.LISTA_DEPOSITOS]["fields"]["ULTIMA_REVERSION_ID"]
    antes = copy.deepcopy(sp.listas)
    e, _ = ejecutar(sp)
    assert e.estado_final == "Failed"
    assert sp.listas == antes and all(c["metodo"] == "GET" for c in sp.llamadas)


def test_grafo_desplegable_y_sin_identificadores_del_tenant():
    definicion = construir_definicion()
    nombres = []
    def verificar(acciones, nivel=1):
        assert not acciones or nivel <= 8
        for nombre, accion in acciones.items():
            assert nombre not in nombres
            nombres.append(nombre)
            assert set(accion.get("runAfter", {})) <= set(acciones)
            verificar(accion.get("actions", {}), nivel + 1)
            verificar(accion.get("else", {}).get("actions", {}), nivel + 1)
    verificar(definicion["actions"])
    assert len(nombres) < 500
    texto = json.dumps(definicion)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", texto, re.I)
    for _, accion in recorrer(definicion["actions"]):
        if accion["type"] == "OpenApiConnection":
            assert accion["inputs"]["retryPolicy"] == {"type": "none"}
            assert accion["inputs"]["parameters"]["dataset"] == "@outputs('PARAM_SITIO_SHAREPOINT')"
    assert "getbytitle('Depositos_Activos')" in texto and "getbytitle('Depositos_Reversiones')" in texto


def test_referencia_historica_exacta_cinco_json():
    carpeta = C.CARPETA / "referencia"
    zpath = carpeta / "reversiondeposito_20261003015909.zip"
    assert hashlib.sha256(zpath.read_bytes()).hexdigest() == "2573ab90a37bee65491e1dde6a1b99f0ed64e8ed20cf07283c4417597e83ecad"
    with zipfile.ZipFile(zpath) as z:
        assert len(z.namelist()) == 5
        for nombre in z.namelist():
            assert (carpeta / "extraido" / nombre).read_bytes() == z.read(nombre)
            json.loads(z.read(nombre))


def definicion_minima():
    from p9.reversion.wdl import compose, definition, init, seq
    return definition({}, seq(INIT=init("valor", "string", ""), A=compose(1), B=compose("@outputs('A')")))


@pytest.mark.parametrize("nombre", ["solicitar", "resolver", "expirar", "recuperar", "provisionar"])
def test_validacion_estatica_cinco_flujos_y_sobres_sin_escribir_archivos(nombre):
    from p9.reversion import flujos
    from p9.reversion.paquete import archivos_paquete
    from p9.reversion.validar import validar_definicion, validar_paquete
    doc = construir_definicion() if nombre == "provisionar" else getattr(flujos, "construir_" + nombre)()
    titulo = "P9_" + nombre.upper() + ("_REVERSIONES" if nombre == "expirar" else "_REVERSION")
    result = validar_definicion(doc, titulo)
    assert result["resultado"] == "OK" and result["acciones"] <= 500 and result["profundidad"] <= 8
    paquete = archivos_paquete(titulo, doc, result["conexiones"])
    assert validar_paquete(paquete, titulo)["resultado"] == "OK"


@pytest.mark.parametrize("problema", ["missing", "forward", "parallel", "runAfter", "cycle", "syntax", "trailing", "function", "variable", "self_set", "set_unknown", "init_nested", "parameter", "guid", "sede"])
def test_estatico_rechaza_mutaciones_de_referencias_y_expresiones(problema):
    from p9.reversion.validar import validar_definicion
    doc = definicion_minima()
    acciones = doc["actions"]
    if problema == "missing":
        acciones["B"]["inputs"] = "@outputs('INEXISTENTE')"
    elif problema == "forward":
        acciones["A"]["inputs"] = "@outputs('B')"
    elif problema == "parallel":
        acciones["B"]["runAfter"] = {"INIT": ["Succeeded"]}
    elif problema == "runAfter":
        acciones["B"]["runAfter"] = {"INEXISTENTE": ["Succeeded"]}
    elif problema == "cycle":
        acciones["A"]["runAfter"] = {"B": ["Succeeded"]}
    elif problema == "syntax":
        acciones["B"]["inputs"] = "@add(1,2);"
    elif problema == "trailing":
        acciones["B"]["inputs"] = "@add(1,2) outputs('A')"
    elif problema == "function":
        acciones["B"]["inputs"] = "@funcion_inventada(1)"
    elif problema == "variable":
        acciones["B"]["inputs"] = "@variables('nunca_inicializada')"
    elif problema in ("self_set", "set_unknown"):
        acciones["B"].update(type="SetVariable", inputs={"name": "valor" if problema == "self_set" else "desconocida",
            "value": "@concat(variables('valor'),'x')"})
    elif problema == "init_nested":
        acciones["C"] = {"type": "Scope", "actions": {"INIT_OTRA": {"type": "InitializeVariable", "inputs": {"variables": [{"name": "otra", "type": "string", "value": ""}]}}}}
    elif problema == "parameter":
        doc["triggers"] = {"manual": {"type": "Request", "inputs": "@parameters('NO_EXISTE')"}}
    elif problema == "guid":
        acciones["B"]["inputs"] = LISTA
    elif problema == "sede":
        acciones["B"]["inputs"] = {"SEDE_ASIGNACION": "COCHABAMBA"}
    with pytest.raises(ValueError):
        validar_definicion(doc)


@pytest.mark.parametrize("problema", ["depth", "count", "terminate_foreach", "terminate_until", "items_scope"])
def test_estatico_rechaza_limites_y_bucles(problema):
    from p9.reversion.validar import validar_definicion
    doc = definicion_minima()
    if problema == "depth":
        nodo = {"type": "Compose", "inputs": 0}
        for i in range(8):
            nodo = {"type": "Scope", "actions": {f"N{i}": nodo}}
        doc["actions"]["DEEP"] = nodo
    elif problema == "count":
        doc["actions"].update({f"N{i}": {"type": "Compose", "inputs": i} for i in range(500)})
    elif problema == "items_scope":
        doc["actions"]["B"]["inputs"] = "@items('UN_BUCLE_AJENO')"
    else:
        doc["actions"]["BUCLE"] = {"type": "Foreach" if problema.endswith("foreach") else "Until", "actions": {
            "TERMINAR": {"type": "Terminate", "inputs": {"runStatus": "Succeeded"}}}}
    with pytest.raises(ValueError):
        validar_definicion(doc)


@pytest.mark.parametrize("problema", ["wildcard", "wildcard_expression", "retry", "sin_etag", "nuevo_etag", "campo_motor", "limpieza", "marcador", "marcador_previo", "sin_merge", "conexion", "lista_antigua", "top_codigo"])
def test_estatico_rechaza_mutaciones_de_escritura_y_conector(problema):
    from p9.reversion.flujos import construir_resolver, construir_solicitar
    from p9.reversion.validar import validar_definicion
    from p9.reversion.wdl import walk
    doc = construir_solicitar() if problema == "marcador_previo" else construir_resolver()
    acciones = dict(walk(doc["actions"]))
    if problema == "marcador_previo":
        acciones["CREAR_SOLICITUD"]["inputs"]["parameters"]["parameters/body"]["ULTIMA_REVERSION_ID"] = "valor_indebido"
    else:
        merge = next(a for n, a in acciones.items() if n.endswith("_MERGE_DEPOSITO"))
        params = merge["inputs"]["parameters"]
        if problema == "wildcard":
            params["parameters/headers"]["IF-MATCH"] = "*"
        elif problema == "wildcard_expression":
            params["parameters/headers"]["IF-MATCH"] = "@concat('*','')"
        elif problema == "retry":
            merge["inputs"]["retryPolicy"] = {"type": "exponential", "count": 2, "interval": "PT5S"}
        elif problema == "sin_etag":
            del params["parameters/headers"]["IF-MATCH"]
        elif problema == "nuevo_etag":
            params["parameters/headers"]["IF-MATCH"] = "@body('GET_LISTA_DEPOSITOS')?['ETag']"
        elif problema == "campo_motor":
            params["parameters/body"]["CODIGO_ASIGNACION"] = None
        elif problema == "limpieza":
            params["parameters/body"]["ESTUDIANTE"] = "sin_limpiar"
        elif problema == "marcador":
            params["parameters/body"]["ULTIMA_REVERSION_ID"] = "no_uid"
        elif problema == "sin_merge":
            del params["parameters/headers"]["X-HTTP-Method"]
        elif problema == "conexion":
            merge["inputs"]["host"]["connectionName"] = "conexion_antigua"
        elif problema == "lista_antigua":
            acciones["GET_LISTA_DEPOSITOS"]["inputs"]["parameters"]["parameters/uri"] = "_api/web/lists/GetByTitle('Depositos_Legacy')"
        elif problema == "top_codigo":
            nodo = acciones["GET_LISTA_DEPOSITOS"]
            nodo["inputs"]["parameters"]["parameters/uri"] = "_api/web/lists/GetByTitle('Depositos_Activos')/items?$filter=CODIGO_ASIGNACION eq 'X'&$top=1"
    with pytest.raises(ValueError):
        validar_definicion(doc)


@pytest.mark.parametrize("problema", ["invoker", "missing_map", "old_connection", "resource", "asset", "dependency"])
def test_estatico_rechaza_paquete_con_conexiones_incorrectas(problema):
    from p9.reversion.flujos import construir_solicitar
    from p9.reversion.paquete import archivos_paquete
    from p9.reversion.validar import validar_paquete
    archivos = archivos_paquete("P9_SOLICITAR_REVERSION", construir_solicitar(), ["shared_sharepointonline", "shared_office365users"])
    path = next(p for p in archivos if p.endswith("/definition.json"))
    props = archivos[path]["properties"]
    base = path.rsplit("/", 1)[0]
    if problema == "invoker":
        props["connectionReferences"]["shared_office365users"]["source"] = "Embedded"
    elif problema == "missing_map":
        del archivos[base + "/connectionsMap.json"]["shared_office365users"]
    elif problema == "old_connection":
        props["connectionReferences"]["shared_sharepointonline"]["connectionName"] = "dd10d97b18344b84b76cb6c7ff89805d"
    elif problema == "resource":
        archivos["manifest.json"]["resources"][UID] = {"type": "Microsoft.PowerApps/apis/connections"}
    elif problema == "asset":
        archivos["Microsoft.Flow/flows/manifest.json"]["flowAssets"]["assetPaths"] = [UID]
    elif problema == "dependency":
        next(v for v in archivos["manifest.json"]["resources"].values() if v["type"] == "Microsoft.Flow/flows")["dependsOn"] = []
    with pytest.raises(ValueError):
        validar_paquete(archivos)


def huellas_genericos():
    """Lee únicamente los diez artefactos genéricos que no deben sobrescribirse."""
    from p9.reversion.construir import CARPETA, COMPONENTES, RAIZ
    paths = [CARPETA / f"flujo_{key}_definition.json" for key in COMPONENTES]
    paths += [RAIZ / (nombre + ".zip") for nombre, _, _ in COMPONENTES.values()]
    assert all(path.is_file() for path in paths)
    return {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def definicion_del_zip(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None and len(archive.namelist()) == 5
        definition = next(p for p in archive.namelist() if p.endswith("/definition.json"))
        return json.loads(archive.read(definition))["properties"]["definition"]


def config_de_ensayo():
    return {"sitio_sharepoint": "https://tenantfixture.sharepoint.com/sites/ensayo/",
            "lista_reversiones_id": LISTA.upper(),
            "responsables_recuperacion_ids": [UID.upper()],
            "aprobadores": ["GTORRICOT@UNIVALLE.EDU", "LVELASQUEZS@UNIVALLE.EDU"]}


def test_constructor_aislado_sincroniza_json_zip_y_es_reproducible(tmp_path):
    from p9.reversion.construir import COMPONENTES, generar
    from p9.reversion.validar import validar_paquete
    antes = huellas_genericos()
    result = generar(salida=tmp_path)
    assert len(result) == 5 and len(list(tmp_path.iterdir())) == 10
    primera = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    for key, (nombre, build, _) in COMPONENTES.items():
        definition = tmp_path / f"flujo_{key}_definition.json"
        package = tmp_path / (nombre + ".zip")
        doc = json.loads(definition.read_text(encoding="utf-8"))
        assert doc == build() == definicion_del_zip(package)
        assert validar_paquete(package, nombre)["resultado"] == "OK"
    generar(salida=tmp_path)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == primera
    assert huellas_genericos() == antes


def test_constructor_configurado_solo_escribe_copias_aisladas(tmp_path):
    from p9.reversion.construir import COMPONENTES, cargar_config, generar, validar_definicion
    antes = huellas_genericos()
    cfg = tmp_path / "configuracion_fixture.json"
    cfg.write_text(json.dumps(config_de_ensayo()), encoding="utf-8")
    values = cargar_config(cfg)
    assert values["lista_reversiones_id"] == LISTA
    assert values["responsables_recuperacion_ids"] == [UID]
    assert values["sitio_sharepoint"] == "https://tenantfixture.sharepoint.com/sites/ensayo"
    assert values["aprobadores"] == list(C.APROBADORES)
    destino = tmp_path / "configurados"
    rows = generar(values["sitio_sharepoint"], values["lista_reversiones_id"],
                   values["responsables_recuperacion_ids"], destino, values["aprobadores"])
    assert len(rows) == 5 and len(list(destino.iterdir())) == 10
    for key, (nombre, build, _) in COMPONENTES.items():
        doc = json.loads((destino / f"flujo_{key}_definition.json").read_text(encoding="utf-8"))
        assert doc == definicion_del_zip(destino / (nombre + ".zip"))
        assert validar_definicion(doc) <= 500
        if key == "provisionar":
            assert doc == build()  # Mantiene entrada manual del sitio.
        else:
            assert doc["actions"]["PARAM_SITIO_SHAREPOINT"]["inputs"] == values["sitio_sharepoint"]
        if key == "resolver":
            assert doc["parameters"]["LISTA_REVERSIONES_ID"]["defaultValue"] == LISTA
            assert doc["triggers"]["Cuando_se_crea_solicitud"]["inputs"]["parameters"]["dataset"] == values["sitio_sharepoint"]
            assert doc["actions"]["PARAM_APROBADORES"]["inputs"] == ";".join(C.APROBADORES)
        if key == "recuperar":
            assert doc["actions"]["PARAM_RESPONSABLES_RECUPERACION"]["inputs"] == [UID]
    assert huellas_genericos() == antes


@pytest.mark.parametrize("cambio", [
    {"sitio_sharepoint": "http://tenantfixture.sharepoint.com/sites/ensayo"},
    {"sitio_sharepoint": "https://tenantfixture.sharepoint.com.evil.invalid/sites/ensayo"},
    {"sitio_sharepoint": "https://tenantfixture.sharepoint.com@evil.invalid/sites/ensayo"},
    {"sitio_sharepoint": "https://tenantfixture.sharepoint.com/sites/../otro"},
    {"sitio_sharepoint": "https://tenantfixture.sharepoint.com/sites/ensayo?destino=otro"},
    {"lista_reversiones_id": "GUID-no-verificado"},
    {"lista_reversiones_id": "00000000-0000-0000-0000-000000000000"},
    {"lista_reversiones_id": LISTA.replace("-", "")},
    {"responsables_recuperacion_ids": []},
    {"responsables_recuperacion_ids": ["operador@univalle.edu"]},
    {"responsables_recuperacion_ids": [UID, UID.upper()]},
    {"clave_no_admitida": "valor"},
    {"aprobadores": ["uno@univalle.edu", "UNO@univalle.edu"]},
])
def test_cargar_config_rechaza_sitios_suplantados_ids_y_claves_invalidas(tmp_path, cambio):
    from p9.reversion.construir import cargar_config
    cfg = tmp_path / "configuracion_invalida.json"
    cfg.write_text(json.dumps({**config_de_ensayo(), **cambio}), encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_config(cfg)


@pytest.mark.parametrize("destino", ["ausente", "raiz", "modulo"])
def test_constructor_configurado_exige_salida_independiente_sin_escribir(destino):
    from p9.reversion.construir import CARPETA, RAIZ, generar
    antes = huellas_genericos()
    salida = {"ausente": None, "raiz": RAIZ, "modulo": CARPETA}[destino]
    with pytest.raises(ValueError):
        generar(sitio="https://tenantfixture.sharepoint.com/sites/ensayo", lista_reversiones_id=LISTA,
                responsables=[UID], salida=salida)
    assert huellas_genericos() == antes


@pytest.mark.parametrize("key", ["solicitar", "resolver", "expirar", "recuperar", "provisionar"])
def test_artefactos_persistidos_json_zip_builder_sincronizados_solo_lectura(key):
    from p9.reversion.construir import CARPETA, COMPONENTES, RAIZ
    from p9.reversion.validar import validar_definicion, validar_paquete
    nombre, build, _ = COMPONENTES[key]
    path = CARPETA / f"flujo_{key}_definition.json"
    package = RAIZ / (nombre + ".zip")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc == build() == definicion_del_zip(package)
    assert validar_definicion(doc, nombre)["resultado"] == "OK"
    assert validar_paquete(package, nombre)["resultado"] == "OK"
