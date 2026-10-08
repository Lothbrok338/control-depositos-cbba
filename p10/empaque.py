# -*- coding: utf-8 -*-
"""
p10/empaque.py · P10-A.1 · ZIP determinista de los libros generados (para revisión visual).

Mismo contenido -> mismos bytes (marcas de tiempo fijas, orden alfabético, sin atributos del sistema),
de modo que el SHA-256 del ZIP identifica el conjunto de archivos y no la hora a la que se empaquetó.
"""
import hashlib
import os
import zipfile


def crear_zip(rutas, ruta_zip):
    """ZIP con los archivos `rutas` (solo el nombre base, orden alfabético). Devuelve su SHA-256."""
    rutas = sorted(rutas, key=lambda r: os.path.basename(r))
    nombres = [os.path.basename(r) for r in rutas]
    if len(set(nombres)) != len(nombres):
        raise ValueError("nombres de archivo repetidos en el ZIP")
    os.makedirs(os.path.dirname(os.path.abspath(ruta_zip)), exist_ok=True)
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for ruta in rutas:
            zi = zipfile.ZipInfo(os.path.basename(ruta), date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3
            zi.external_attr = 0o644 << 16
            with open(ruta, "rb") as f:
                z.writestr(zi, f.read())
    h = hashlib.sha256()
    with open(ruta_zip, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()
