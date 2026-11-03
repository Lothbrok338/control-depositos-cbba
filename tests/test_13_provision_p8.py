"""Pruebas del WDL de provisión real usando el intérprete local y REST simulado."""
import copy
import hashlib
import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from p8.provision.construir import CARPETA, FUENTE, NOMBRE, PLANTILLA, RAIZ, SALIDA, compilar, construir_definicion, generar
from p8.provision.ensayo import SharePointREST, ejecutar


@pytest.fixture
def definicion():
    return construir_definicion(compilar(json.loads(FUENTE.read_text())), hashlib.sha256(FUENTE.read_bytes()).hexdigest())


def resumen(e):
    assert "RESUMEN_FINAL" in e.salidas, e.salidas
    return e.salidas["RESUMEN_FINAL"]


def test_provision_y_reproceso_sin_ninguna_escritura(definicion):
    e, sp = ejecutar(definicion)
    assert resumen(e)["PROVISION_P8"] == "OK", resumen(e)
    assert e.estado_final == "Succeeded"
    assert {n: len(l["fields"])-1 for n,l in sp.listas.items()} == {"Depositos_Activos":34,"Depositos_Cargas":13}
    clave = sp.listas["Depositos_Activos"]["fields"]["CLAVE_TRANSACCION"]
    assert all(clave[n] for n in ("Required","Indexed","EnforceUniqueValues"))
    for l in sp.listas.values():
        assert l["fields"]["Title"]["Required"] is False
        l["items"].append({"Title":"dato previo","ID":1})
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e2, _ = ejecutar(definicion, sp)
    assert resumen(e2)["PROVISION_P8"] == "OK", resumen(e2)
    assert all(c["metodo"] == "GET" for c in sp.llamadas)
    assert sp.listas == antes


@pytest.mark.parametrize("propiedad,valor", [
    ("Required",False),("Indexed",False),("EnforceUniqueValues",False),
    ("TypeAsString","Number"),("Hidden",True),("ReadOnlyField",True),
    ("DefaultValue","otro"),
])
def test_diferencias_no_reparan_ni_destruyen_datos(definicion, propiedad, valor):
    _, sp = ejecutar(definicion)
    sp.listas["Depositos_Activos"]["fields"]["CLAVE_TRANSACCION"][propiedad] = valor
    sp.listas["Depositos_Activos"]["items"] = [{"CLAVE_TRANSACCION":"ya existe"}]
    antes=copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(definicion, sp)
    assert resumen(e)["PROVISION_P8"] == "FAIL"
    assert any(d["campo"]=="CLAVE_TRANSACCION" and d["propiedad"]==propiedad for d in resumen(e)["diferencias"])
    assert sp.listas == antes
    assert not any(c["metodo"]=="POST" for c in sp.llamadas)


@pytest.mark.parametrize("campo,atributo,valor", [
    ("FECHA_MOVIMIENTO","Format","DateTime"),
    ("FECHA_HORA_ASIGNACION","Format","DateOnly"),
    ("IMPORTE","Decimals","0"),("IMPORTE","Percentage","TRUE"),
    ("OBSERVACION","RichText","TRUE"),("OBSERVACION","AppendOnly","TRUE"),
    ("ESTADO_ASIGNACION","FillInChoice","TRUE"),
])
def test_formato_xml_final_se_comprueba(definicion,campo,atributo,valor):
    _, sp=ejecutar(definicion)
    c=sp.listas["Depositos_Activos"]["fields"][campo]
    xml=ET.fromstring(c["SchemaXml"]); xml.set(atributo,valor); c["SchemaXml"]=ET.tostring(xml,encoding="unicode")
    e,_=ejecutar(definicion,sp)
    assert any(d["campo"]==campo and d["propiedad"]==atributo for d in resumen(e)["diferencias"])
    assert e.estado_final=="Failed"


def test_opciones_exactas_y_predeterminado(definicion):
    _,sp=ejecutar(definicion)
    campos=sp.listas["Depositos_Activos"]["fields"]
    c=campos["ESTADO_ASIGNACION"]
    assert c["DefaultValue"]=="DISPONIBLE"
    xml=ET.fromstring(c["SchemaXml"])
    ET.SubElement(xml.find("CHOICES"),"CHOICE").text="OTRA"
    c["SchemaXml"]=ET.tostring(xml,encoding="unicode")
    e,_=ejecutar(definicion,sp)
    assert any(d["campo"]=="ESTADO_ASIGNACION" and d["propiedad"]=="Choices" for d in resumen(e)["diferencias"])


def test_nombre_interno_codificado_no_se_confunde_con_titulo(definicion):
    sp=SharePointREST(); l=sp.nueva_lista("Depositos_Activos")
    l["fields"]["nombre_distinto"]=sp._campo_xml('<Field Name="nombre_distinto" DisplayName="CLAVE_TRANSACCION" Type="Text"/>')
    e,_=ejecutar(definicion,sp)
    assert "CLAVE_TRANSACCION" not in l["fields"]
    assert any(d["campo"]=="CLAVE_TRANSACCION" and d["propiedad"]=="InternalName" for d in resumen(e)["diferencias"])
    assert any(d["propiedad"]=="CANTIDAD_COLUMNAS_TECNICAS" and d["actual"]==33 for d in resumen(e)["diferencias"])


def test_hash_sha256_creacion_tecnica_y_titulo_logico_por_guid(definicion):
    plan = definicion["actions"]["Contrato_compilado"]["inputs"]
    cargas = next(l for l in plan if l["Nombre"] == "Depositos_Cargas")
    campo = next(c for c in cargas["Campos"] if c["Nombre"] == "HASH_SHA256")
    parametros = campo["Crear"]["parameters"]
    xml = ET.fromstring(parametros["SchemaXml"])
    assert {a: xml.get(a) for a in ("Name", "StaticName", "DisplayName")} == {
        "Name": "HASH_SHA256", "StaticName": "HASH_SHA256", "DisplayName": "HASH_SHA256"}
    assert xml.get("ID") is None  # Retirado el intento V2 de forzar SHA256.
    assert parametros["Options"] == 1 | 8
    esperado = {p["propiedad"]: p["esperado"] for p in campo["Propiedades"]}
    assert esperado["InternalName"] == "HASH_SHA256" and esperado["Title"] == "SHA256"
    assert campo["Configurar"]["Title"] == campo["NombreVisible"] == "SHA256"
    _, sp = ejecutar(definicion)
    real = sp.listas["Depositos_Cargas"]["fields"]["HASH_SHA256"]
    assert real["InternalName"] == "HASH_SHA256" and real["Title"] == "SHA256"
    assert ET.fromstring(real["SchemaXml"]).get("DisplayName") == "SHA256"
    cambios = [c for c in sp.llamadas if c["body"] and c["body"].get("Title") == "SHA256"]
    assert len(cambios) == 1
    assert cambios[0]["uri"].endswith("/fields(guid'" + real["Id"] + "')")


def codificar_sha256_observado(lista, campo):
    """Inyecta el nombre interno rechazado en tenant para asegurar FAIL en V3."""
    if lista == "Depositos_Cargas" and campo["InternalName"] == "HASH_SHA256":
        campo["InternalName"] = "_x0053_HA256"
        xml = ET.fromstring(campo["SchemaXml"])
        xml.set("Name", "_x0053_HA256")
        campo["SchemaXml"] = ET.tostring(xml, encoding="unicode")


def comprobar_fallo_sha256(e, nombre_incorrecto="_x0053_HA256"):
    r = resumen(e)
    assert r["PROVISION_P8"] == "FAIL" and e.estado_final == "Failed"
    assert [(l["lista"], l["presentes"]) for l in r["listas"]] == [
        ("Depositos_Activos", 34), ("Depositos_Cargas", 12)]
    assert r["diferencias"] == [
        {"lista": "Depositos_Cargas", "campo": "", "propiedad": "CANTIDAD_COLUMNAS_TECNICAS",
         "esperado": 13, "actual": 12},
        {"lista": "Depositos_Cargas", "campo": nombre_incorrecto, "propiedad": "COLUMNA_ADICIONAL",
         "esperado": "Ninguna columna de usuario fuera del contrato", "actual": "SHA256"},
        {"lista": "Depositos_Cargas", "campo": "HASH_SHA256", "propiedad": "InternalName",
         "esperado": "HASH_SHA256", "actual": "Ausente o no único con ese nombre interno exacto"},
    ]


@pytest.mark.parametrize("con_datos", [False, True])
@pytest.mark.parametrize("nombre_incorrecto", ["_x0053_HA256", "SHA256", "hash_sha256"])
def test_hash_sha256_nombre_incorrecto_preexistente_no_se_migra(definicion, con_datos, nombre_incorrecto):
    _, sp = ejecutar(definicion)
    lista = sp.listas["Depositos_Cargas"]
    campo = lista["fields"].pop("HASH_SHA256")
    campo["InternalName"] = nombre_incorrecto
    xml = ET.fromstring(campo["SchemaXml"])
    xml.set("Name", nombre_incorrecto)
    campo["SchemaXml"] = ET.tostring(xml, encoding="unicode")
    lista["fields"][campo["InternalName"]] = campo
    if con_datos:
        lista["items"] = [{"ID": 1, nombre_incorrecto: "dato previo"}]
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(definicion, sp)
    comprobar_fallo_sha256(e, nombre_incorrecto)
    assert sp.listas == antes
    assert all(c["metodo"] == "GET" for c in sp.llamadas)


def test_hash_sha256_post_200_con_nombre_codificado_no_certifica_exito(definicion):
    sp = SharePointREST()
    sp.al_crear = codificar_sha256_observado
    e, _ = ejecutar(definicion, sp)
    comprobar_fallo_sha256(e)
    assert e.estados["Provisionar_listas"] == "Succeeded"
    # Una respuesta HTTP 200 nunca sustituye a la comprobación del nombre real.
    campo = sp.listas["Depositos_Cargas"]["fields"]["_x0053_HA256"]
    assert campo["Title"] == "SHA256"


@pytest.mark.parametrize("titulo", ["HASH_SHA256", "SHA 256"])
def test_hash_sha256_titulo_visible_inexacto_falla_sin_modificar(definicion, titulo):
    _, sp = ejecutar(definicion)
    sp.listas["Depositos_Cargas"]["fields"]["HASH_SHA256"]["Title"] = titulo
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(definicion, sp)
    assert resumen(e)["PROVISION_P8"] == "FAIL"
    assert {"lista": "Depositos_Cargas", "campo": "HASH_SHA256", "propiedad": "Title",
            "esperado": "SHA256", "actual": titulo} in resumen(e)["diferencias"]
    assert sp.listas == antes and all(c["metodo"] == "GET" for c in sp.llamadas)


def test_sha256_recrear_cargas_conserva_activos_y_es_idempotente(definicion):
    _, sp = ejecutar(definicion)
    sp.listas["Depositos_Activos"]["items"] = [{"ID": 1, "CLAVE_TRANSACCION": "conservar"}]
    activos = copy.deepcopy(sp.listas["Depositos_Activos"])
    # Estado inicial del ensayo tras la eliminación MANUAL autorizada para
    # el piloto vacío. El flujo no realiza esta operación.
    del sp.listas["Depositos_Cargas"]
    sp.llamadas.clear()
    e, _ = ejecutar(definicion, sp)
    assert resumen(e)["PROVISION_P8"] == "OK"
    assert sp.listas["Depositos_Activos"] == activos
    assert not any(c["metodo"] == "POST" and "Depositos_Activos" in c["uri"] for c in sp.llamadas)
    creaciones = [c for c in sp.llamadas if c["accion"] == "Crear_columna"]
    assert len(creaciones) == 13
    solicitud = next(c for c in creaciones if
                     ET.fromstring(c["body"]["parameters"]["SchemaXml"]).get("Name") == "HASH_SHA256")
    xml = ET.fromstring(solicitud["body"]["parameters"]["SchemaXml"])
    campo = sp.listas["Depositos_Cargas"]["fields"]["HASH_SHA256"]
    assert xml.get("Name") == campo["InternalName"] == "HASH_SHA256"
    assert campo["Title"] == "SHA256"
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(definicion, sp)
    assert resumen(e)["PROVISION_P8"] == "OK"
    assert sp.listas == antes
    assert all(c["metodo"] == "GET" for c in sp.llamadas)


def test_lista_parcial_agrega_solo_lo_que_falta_y_conserva_title(definicion):
    _,sp=ejecutar(definicion)
    l=sp.listas['Depositos_Activos']
    del l['fields']['MONEDA']
    l['fields']['Title']['Required']=True
    l['items']=[{'ID':1,'Title':'No borrar este título'}]
    sp.llamadas.clear()
    e,_=ejecutar(definicion,sp)
    assert resumen(e)['PROVISION_P8']=='OK'
    creaciones=[c for c in sp.llamadas if c['accion']=='Crear_columna']
    assert len(creaciones)==1
    assert ET.fromstring(creaciones[0]['body']['parameters']['SchemaXml']).get('Name')=='MONEDA'
    assert l['items']==[{'ID':1,'Title':'No borrar este título'}]
    assert l['fields']['Title']['Required'] is False


def test_columna_adicional_se_reporta_y_conserva(definicion):
    _,sp=ejecutar(definicion)
    l=sp.listas['Depositos_Cargas']
    l['fields']['EXTRA']=sp._campo_xml('<Field Name="EXTRA" Type="Text"/>')
    antes=copy.deepcopy(l)
    e,_=ejecutar(definicion,sp)
    assert any(d['campo']=='EXTRA' and d['propiedad']=='COLUMNA_ADICIONAL' for d in resumen(e)['diferencias'])
    assert l==antes and resumen(e)['PROVISION_P8']=='FAIL'


@pytest.mark.parametrize("accion,estado,http",[
    ("Buscar_lista","Failed",403),("Crear_lista","TimedOut",504),
    ("Crear_columna","Failed",500),("Configurar_columna_nueva","Failed",403),
    ("Exigir_unicidad","Failed",400),("Campos_finales","TimedOut",504),
    ("Leer_lista_final","Failed",404),("Configurar_Title","Failed",403),
])
def test_errores_no_producen_ok_y_siempre_resumen(definicion,accion,estado,http):
    sp=SharePointREST();sp.fallos[accion]=(estado,http)
    e,_=ejecutar(definicion,sp)
    assert resumen(e)["PROVISION_P8"]=="FAIL"
    assert resumen(e)["diferencias"]
    assert e.estado_final=="Failed"
    assert e.eventos.index("RESUMEN_FINAL") < e.eventos.index("Terminar_FAIL")
    assert any(c["accion"]=="Leer_lista_final" for c in sp.llamadas)


def test_exito_post_no_sustituye_a_verificacion_final(definicion):
    sp=SharePointREST()
    def alterar(nombre,lista):
        if nombre=="Depositos_Activos":
            lista["fields"]["CLAVE_TRANSACCION"]["EnforceUniqueValues"]=False
    sp.al_verificar=alterar
    e,_=ejecutar(definicion,sp)
    assert e.estados["Provisionar_listas"]=="Succeeded"
    assert resumen(e)["PROVISION_P8"]=="FAIL"
    assert any(d["propiedad"]=="EnforceUniqueValues" for d in resumen(e)["diferencias"])


def test_schema_xml_invalido_identifica_columna_y_continua(definicion):
    _,sp=ejecutar(definicion)
    sp.listas["Depositos_Activos"]["fields"]["BANCO"]["SchemaXml"]="<xml roto"
    sp.listas["Depositos_Activos"]["fields"]["MONEDA"]["Required"]=False
    e,_=ejecutar(definicion,sp)
    dif=resumen(e)["diferencias"]
    assert any(d["campo"]=="BANCO" and d["propiedad"]=="LECTURA_PROPIEDADES" for d in dif)
    assert any(d["campo"]=="MONEDA" and d["propiedad"]=="Required" for d in dif)
    assert resumen(e)["PROVISION_P8"]=="FAIL"


@pytest.mark.parametrize("etapa",["Campos_antes","Campos_finales"])
def test_paginacion_no_certifica_inventario_parcial(definicion,etapa):
    sp=SharePointREST();sp.paginar.add(etapa)
    e,_=ejecutar(definicion,sp)
    assert resumen(e)["PROVISION_P8"]=="FAIL"
    assert any(d["propiedad"].startswith("PAGINACION") for d in resumen(e)["diferencias"])
    if etapa=="Campos_antes":
        assert not any(c["accion"]=="Crear_columna" for c in sp.llamadas)


@pytest.mark.parametrize("propiedad,valor",[("ContentTypesEnabled",True),("BaseTemplate",101)])
def test_listas_incompatibles_no_se_alteran(definicion,propiedad,valor):
    sp=SharePointREST();l=sp.nueva_lista("Depositos_Activos");l["meta"][propiedad]=valor
    antes=copy.deepcopy(l)
    e,_=ejecutar(definicion,sp)
    assert l==antes
    assert resumen(e)["PROVISION_P8"]=="FAIL"


def test_contrato_unica_fuente():
    s=json.loads(FUENTE.read_text()); s2=copy.deepcopy(s)
    s2["Depositos_Activos"]["columnas"][0]["obligatoria"]=False
    a,b=compilar(s),compilar(s2)
    assert a[0]["Campos"][0]["Propiedades"] != b[0]["Campos"][0]["Propiedades"]
    assert b[0]["Campos"][0]["Configurar"]["Required"] is False
    assert len(a[0]["Campos"])==34 and len(a[1]["Campos"])==13


def test_hash_sha256_mapeo_logico_compartido_desde_contrato():
    from p8 import construir_paquete_p8 as carga
    from p8.validar_p8 import acciones_recursivas

    esquema = json.loads(FUENTE.read_text())
    campo = next(c for c in esquema["Depositos_Cargas"]["columnas"] if c.get("nombre_logico") == "SHA256")
    assert campo["nombre_tecnico"] == "HASH_SHA256" and campo["nombre_visible"] == "SHA256"
    # Cambiar el contrato en memoria debe alimentar ambas capas, sin otros
    # nombres físicos hardcodeados en el provisionador ni en la bitácora.
    campo["nombre_tecnico"] = "HASH_PRUEBA"
    campo["nombre_visible"] = "Huella SHA256"
    p = compilar(esquema)
    compilado = next(c for c in p[1]["Campos"] if c["Nombre"] == "HASH_PRUEBA")
    assert compilado["Configurar"]["Title"] == "Huella SHA256"
    flujo = carga.construir_definicion(json.loads(carga.ESQUEMA_P7.read_text()),
                                       carga._cargar_adaptador().COLUMNAS_M365, esquema)
    params = dict(acciones_recursivas(flujo["actions"]))["Registrar_bitacora_del_lote"]["inputs"]["parameters"]
    assert params["item/HASH_PRUEBA"] == "@variables('varSha256')"
    assert "item/HASH_SHA256" not in params and "item/SHA256" not in params


@pytest.mark.parametrize("nombre_antiguo", [None, "SHA256", "_x0053_HA256"])
def test_provision_y_carga_bitacora_con_esquema_real_simulado(definicion, nombre_antiguo):
    from p8 import construir_paquete_p8 as carga
    from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado, FalloConector
    from p8.validar_p8 import EJEMPLO, acciones_recursivas

    provision, sp = ejecutar(definicion)
    assert resumen(provision)["PROVISION_P8"] == "OK"
    columnas = set(sp.listas["Depositos_Cargas"]["fields"]) - {"Title"}
    assert len(columnas) == 13 and "HASH_SHA256" in columnas and "SHA256" not in columnas
    # P8.5: el flujo de carga V7 escribe además 6 columnas ADITIVAS de certificación, que se crean
    # fuera del contrato del provisionador (p8/esquema_certificacion_p8_5.json).
    adicionales = json.loads((RAIZ / "p8/esquema_certificacion_p8_5.json").read_text())["Depositos_Cargas"]["columnas_nuevas"]
    columnas |= {c["nombre_tecnico"] for c in adicionales}
    assert len(adicionales) == 6 and len(columnas) == 19

    class ConectorConColumnasProvisionadas(SharePointSimulado):
        def ejecutar(self, nombre, parametros):
            if nombre == "Registrar_bitacora_del_lote":
                recibidas = {k.split('/')[1] for k in parametros if k.startswith('item/')}
                if recibidas != columnas:
                    raise FalloConector("Failed", 400)
            return super().ejecutar(nombre, parametros)

    flujo = json.loads(carga.DEFINICION_SALIDA.read_text())
    artefacto = json.loads(EJEMPLO.read_text())
    if nombre_antiguo:
        params = dict(acciones_recursivas(flujo["actions"]))["Registrar_bitacora_del_lote"]["inputs"]["parameters"]
        params['item/' + nombre_antiguo] = params.pop('item/HASH_SHA256')
    primera = ConectorConColumnasProvisionadas(artefacto)
    ejecucion = EnsayoWDL(flujo, primera).ejecutar()
    if nombre_antiguo:
        assert ejecucion.estado_final == "Failed" and primera.bitacoras == []
        return
    segunda = ConectorConColumnasProvisionadas(artefacto, existentes=primera.activos)
    reproceso = EnsayoWDL(flujo, segunda).ejecutar()
    assert ejecucion.estado_final == reproceso.estado_final == "Succeeded"
    assert len(primera.activos) == len(segunda.activos) == 8
    assert len(primera.creaciones) == 8 and segunda.creaciones == []
    for servidor, nuevos, existen in [(primera, 8, 0), (segunda, 0, 8)]:
        b = servidor.bitacoras[0]
        assert b["HASH_SHA256"] == artefacto["sha256_archivo_fuente"]
        assert [b[k] for k in ("CANTIDAD_RECIBIDA", "CANTIDAD_NUEVA", "CANTIDAD_YA_EXISTE", "CANTIDAD_ERROR")] == [8, nuevos, existen, 0]
        assert b["ESTADO_LOTE/Value"] == "COMPLETADO"


def test_paquete_independiente_reproducible_y_grafo_valido(definicion):
    anteriores = [RAIZ/'P8_PROVISIONAR_LISTAS.zip', RAIZ/'P8_PROVISIONAR_LISTAS_V2_SHA256.zip']
    antes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [FUENTE,PLANTILLA,RAIZ/'p8/flujo_p8_definition.json', *anteriores]}
    generar();zip1=SALIDA.read_bytes();generar();assert SALIDA.read_bytes()==zip1
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in antes.items())
    nombres=[]
    def recorrer(acciones,nivel=1):
        assert nivel<=8 or not acciones
        for n,a in acciones.items():
            assert n not in nombres;nombres.append(n)
            assert all(d in acciones for d in a.get("runAfter",{}))
            if a['type']=='OpenApiConnection':
                assert a['inputs']['host']['operationId']=='HttpRequest'
                assert a['inputs']['parameters']['parameters/method'] in ('GET','POST')
            recorrer(a.get('actions',{}),nivel+1);recorrer(a.get('else',{}).get('actions',{}),nivel+1)
    recorrer(definicion['actions']); assert len(nombres)<500
    with zipfile.ZipFile(SALIDA) as z,zipfile.ZipFile(PLANTILLA) as carga:
        assert z.testzip() is None and len(z.namelist())==5
        m=json.loads(z.read('manifest.json'));m0=json.loads(carga.read('manifest.json'))
        assert m['details']['displayName'] == NOMBRE
        recurso = next(r for r in m['resources'].values() if r['type'] == 'Microsoft.Flow/flows')
        assert recurso['details']['displayName'] == NOMBRE
        assert recurso['suggestedCreationType'] == 'New'
        assert not set(m['resources']) & set(m0['resources'])
        flujo=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/definition.json'))))
        assert flujo['properties']['definition']==definicion
        assert SALIDA.name == 'P8_PROVISIONAR_LISTAS_V3_HASH_SHA256.zip'
        assert flujo['properties']['displayName'] == NOMBRE
        for anterior in anteriores:
            with zipfile.ZipFile(anterior) as viejo:
                assert not set(m['resources']) & set(json.loads(viejo.read('manifest.json'))['resources'])
