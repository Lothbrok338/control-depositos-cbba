# Export REAL del tenant, V1 funcional (solo lectura)

`P9_Confirmacion_Masiva.pa.yaml` y `Main_Screen.pa.yaml` son copias **verbatim** de `Src/` del `.msapp` de **`P9_PRUEBA_MASIVA`** exportado DESPUÉS de integrar y probar
la confirmación masiva (sha256 del `.msapp`: `3a90a83cb31bf20a218893b7bd96c7050c3de98cd1c4e5ded75c6195f8400645`). **No se editan a mano**: se reemplazan al volver a exportar.

- `../tenant/` = export ANTERIOR (prevalidación validada, confirmación sin integrar; sha256 `666b7f611ec44c55f4ce096ff7cc5b3dcb23ef4877a6baacec38ad5ea1da0630`). Se conserva como línea base.
- `../P9_Confirmacion_Masiva.pa.yaml` = copia idéntica de este `tenant_v1` (fuente única de generadores y tests).
- `Main_Screen.pa.yaml` de este export es byte a byte el de `../tenant/`.

Evidencia y matriz de validación: `../../VALIDACION_TENANT_V1.md`.
