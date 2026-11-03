# P10-A.2 · servicio de histórico (SEGUNDO servicio de Railway, separado de p0-api). Sin estado: sin volúmenes ni base de datos.
# Variable obligatoria en Railway: P10_API_TOKEN (secreto; NO va en la imagen ni en el repositorio).
# En Railway: Settings > Build > Dockerfile Path = p10/Dockerfile ; Settings > Config-as-code = /p10/railway.json
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ="<-04>4" \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements-p0.txt .
RUN pip install -r requirements-p0.txt

# Mismo motor y mismo registro que P0 (no se copia ni se reescribe nada): p10 los importa tal cual.
COPY motor_control_depositos_cbba.py motor_generico.py deteccion_registro.py captura_origen.py registro_bancos.json adaptador_m365.py historico.py ./
COPY p0/ ./p0/
COPY p9/__init__.py p9/contrato.py ./p9/
COPY p9/reversion/contrato.py ./p9/reversion/
COPY p10/__init__.py p10/api.py p10/contrato.py p10/estado.py p10/generador.py p10/plan.py p10/sharepoint.py p10/sincronizacion.py p10/snapshot.py p10/validacion.py ./p10/

RUN useradd --system --no-create-home p10
USER p10

# Un solo proceso: el motor de P0 cambia variables de entorno y stdout por corrida (una a la vez).
CMD ["sh", "-c", "exec uvicorn p10.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
