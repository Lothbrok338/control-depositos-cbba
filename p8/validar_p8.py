"""Inspección del paquete y ensayo del WDL, sin conexión a Microsoft 365."""
import json
import zipfile
from pathlib import Path
from p8 import construir_paquete_p8 as paquete
from p8.ensayo_wdl import EnsayoWDL, SharePointSimulado

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLO = RAIZ / "ejemplos_p7/m365/DEPOSITOS_ACTIVOS__P7-3af418fcadd6.json"


def acciones_recursivas(acciones):
    for nombre, accion in acciones.items():
        yield nombre, accion
        yield from acciones_recursivas(accion.get("actions", {}))
        yield from acciones_recursivas(accion.get("else", {}).get("actions", {}))


def resumen(sp):
    return {**{k: v for k, v in sp.bitacoras[-1].items() if k.startswith("CANTIDAD_") or k == "ESTADO_LOTE/Value"},
            "coincidencias_preconsulta": sp.coincidencias_preconsulta, "intentos_crear": len(sp.creaciones),
            "elementos_finales": len(sp.activos)}


def validar():
    definicion = json.loads(paquete.DEFINICION_SALIDA.read_text(encoding="utf-8"))
    esquema = json.loads(paquete.ESQUEMA_P7.read_text(encoding="utf-8"))
    pares = list(acciones_recursivas(definicion["actions"]))
    acciones = dict(pares)
    assert len(acciones) == len(pares), "Nombres de acciones duplicados"
    def comprobar_dependencias(bloque):
        for nombre, accion in bloque.items():
            assert set(accion.get('runAfter', {})) <= set(bloque), nombre
            comprobar_dependencias(accion.get('actions', {}))
            comprobar_dependencias(accion.get('else', {}).get('actions', {}))
    comprobar_dependencias(definicion['actions'])
    assert acciones["Analizar_JSON"]["inputs"]["schema"] == esquema
    assert acciones["Obtener_contenido_del_archivo"]["inputs"]["parameters"]["inferContentType"] is False
    assert "result(" not in json.dumps(definicion)
    columnas = paquete._cargar_adaptador().COLUMNAS_TECNICAS
    mapeadas = {k[5:] for k in acciones["Crear_movimiento"]["inputs"]["parameters"] if k.startswith("item/")}
    assert mapeadas == set(columnas) | {"ESTADO_ASIGNACION/Value"}
    assert definicion["actions"]["Finalizar_ejecucion"]["runAfter"] == {"FINALLY": ["Succeeded"]}
    with zipfile.ZipFile(paquete.ZIP_SALIDA) as z:
        assert set(z.namelist()) == set(paquete._archivos_paquete(definicion))
        envuelta = json.loads(z.read(f"Microsoft.Flow/flows/{paquete.FLOW_RESOURCE_ID}/definition.json"))
        assert envuelta["properties"]["definition"] == definicion
        assert envuelta["properties"]["displayName"] == paquete.NOMBRE_FLUJO
        assert "sharepoint.com/sites/" not in str(envuelta)
    artefacto = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    primera = SharePointSimulado(artefacto)
    EnsayoWDL(definicion, primera).ejecutar()
    segunda = SharePointSimulado(artefacto, existentes=primera.activos)
    EnsayoWDL(definicion, segunda).ejecutar()
    assert len(primera.creaciones) == 8 and len(primera.activos) == 8
    assert segunda.coincidencias_preconsulta == 8 and len(segunda.creaciones) == 0 and len(segunda.activos) == 8
    return {"flujo": paquete.NOMBRE_FLUJO, "tipo_de_evidencia": "Ensayo local del WDL; no ejecución Microsoft",
            "primera_ejecucion": resumen(primera), "segunda_ejecucion": resumen(segunda)}


if __name__ == "__main__":
    print(json.dumps(validar(), ensure_ascii=False, indent=2))
