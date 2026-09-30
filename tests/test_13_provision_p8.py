"""Pruebas del WDL de provisión real usando el intérprete local y REST simulado."""
import copy
import hashlib
import json
import uuid
import zipfile
from xml.etree import ElementTree as ET

import pytest

from p8.provision.construir import CARPETA, FUENTE, PLANTILLA, RAIZ, SALIDA, compilar, construir_definicion, generar
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


def test_sha256_definicion_exige_tres_nombres_exactos_e_identidad_explicita(definicion):
    plan = definicion["actions"]["Contrato_compilado"]["inputs"]
    cargas = next(l for l in plan if l["Nombre"] == "Depositos_Cargas")
    campo = next(c for c in cargas["Campos"] if c["Nombre"] == "SHA256")
    parametros = campo["Crear"]["parameters"]
    xml = ET.fromstring(parametros["SchemaXml"])
    assert {a: xml.get(a) for a in ("Name", "StaticName", "DisplayName")} == {
        "Name": "SHA256", "StaticName": "SHA256", "DisplayName": "SHA256"}
    assert xml.get("ID") == "{" + str(uuid.uuid5(
        uuid.NAMESPACE_URL, "control-depositos-cbba:p8:Depositos_Cargas:SHA256")) + "}"
    assert parametros["Options"] == 1 | 8
    assert {p["propiedad"]: p["esperado"] for p in campo["Propiedades"]}["InternalName"] == "SHA256"
    assert [c["Nombre"] for l in plan for c in l["Campos"]
            if ET.fromstring(c["Crear"]["parameters"]["SchemaXml"]).get("ID")] == ["SHA256"]


def codificar_sha256_observado(lista, campo):
    """Reproduce la respuesta REAL reportada; no modela un bypass hipotético."""
    if lista == "Depositos_Cargas" and campo["InternalName"] == "SHA256":
        campo["InternalName"] = "_x0053_HA256"
        xml = ET.fromstring(campo["SchemaXml"])
        xml.set("Name", "_x0053_HA256")
        campo["SchemaXml"] = ET.tostring(xml, encoding="unicode")


def comprobar_fallo_sha256(e):
    r = resumen(e)
    assert r["PROVISION_P8"] == "FAIL" and e.estado_final == "Failed"
    assert [(l["lista"], l["presentes"]) for l in r["listas"]] == [
        ("Depositos_Activos", 34), ("Depositos_Cargas", 12)]
    assert r["diferencias"] == [
        {"lista": "Depositos_Cargas", "campo": "", "propiedad": "CANTIDAD_COLUMNAS_TECNICAS",
         "esperado": 13, "actual": 12},
        {"lista": "Depositos_Cargas", "campo": "_x0053_HA256", "propiedad": "COLUMNA_ADICIONAL",
         "esperado": "Ninguna columna de usuario fuera del contrato", "actual": "SHA256"},
        {"lista": "Depositos_Cargas", "campo": "SHA256", "propiedad": "InternalName",
         "esperado": "SHA256", "actual": "Ausente o no único con ese nombre interno exacto"},
    ]


@pytest.mark.parametrize("con_datos", [False, True])
def test_sha256_codificado_preexistente_falla_sin_reparar_ni_borrar(definicion, con_datos):
    _, sp = ejecutar(definicion)
    lista = sp.listas["Depositos_Cargas"]
    campo = lista["fields"].pop("SHA256")
    codificar_sha256_observado("Depositos_Cargas", campo)
    lista["fields"][campo["InternalName"]] = campo
    if con_datos:
        lista["items"] = [{"ID": 1, "_x0053_HA256": "dato previo"}]
    antes = copy.deepcopy(sp.listas)
    sp.llamadas.clear()
    e, _ = ejecutar(definicion, sp)
    comprobar_fallo_sha256(e)
    assert sp.listas == antes
    assert all(c["metodo"] == "GET" for c in sp.llamadas)


def test_sha256_post_200_con_nombre_codificado_no_certifica_exito(definicion):
    sp = SharePointREST()
    sp.al_crear = codificar_sha256_observado
    e, _ = ejecutar(definicion, sp)
    comprobar_fallo_sha256(e)
    assert e.estados["Provisionar_listas"] == "Succeeded"
    # Incluso si el servidor ignora la identidad explícita y responde HTTP 200,
    # el verificador sigue rechazando exactamente el defecto del piloto real.
    campo = sp.listas["Depositos_Cargas"]["fields"]["_x0053_HA256"]
    assert ET.fromstring(campo["SchemaXml"]).get("ID")
    assert campo["Title"] == "SHA256"


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
                     ET.fromstring(c["body"]["parameters"]["SchemaXml"]).get("Name") == "SHA256")
    xml = ET.fromstring(solicitud["body"]["parameters"]["SchemaXml"])
    campo = sp.listas["Depositos_Cargas"]["fields"]["SHA256"]
    assert campo["Id"] == str(uuid.UUID(xml.get("ID")))
    assert campo["InternalName"] == campo["Title"] == "SHA256"
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


def test_paquete_independiente_reproducible_y_grafo_valido(definicion):
    antes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [FUENTE,PLANTILLA,RAIZ/'p8/flujo_p8_definition.json']}
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
        assert not set(m['resources']) & set(m0['resources'])
        flujo=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/definition.json'))))
        assert flujo['properties']['definition']==definicion
        assert flujo['properties']['displayName']=='P8_PROVISIONAR_LISTAS'
