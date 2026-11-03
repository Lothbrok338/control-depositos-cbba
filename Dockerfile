# P0 · API sin estado para Railway. Sin volúmenes, base de datos ni almacenamiento persistente.
# Variable obligatoria en Railway: P0_API_TOKEN (secreto; NO va en la imagen ni en el repositorio).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ="<-04>4" \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements-p0.txt .
RUN pip install -r requirements-p0.txt

COPY motor_control_depositos_cbba.py motor_generico.py deteccion_registro.py captura_origen.py registro_bancos.json adaptador_m365.py ./
COPY p0/ ./p0/

RUN useradd --system --no-create-home p0
USER p0

# Railway define PORT. Un solo proceso: el motor cambia variables de entorno y stdout por corrida (una a la vez).
CMD ["sh", "-c", "exec uvicorn p0.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
