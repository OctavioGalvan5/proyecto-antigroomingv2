# syntax=docker/dockerfile:1.7
# Imagen slim con Python 3.11 (el proyecto usa type hints modernos).
FROM python:3.11-slim

# Buenas prácticas de Python en containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema: libpq para psycopg2 en runtime, build tools solo durante instalación.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiamos requirements primero para aprovechar cache de layers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ya no necesitamos las build tools después de instalar los paquetes
RUN apt-get purge -y gcc && apt-get autoremove -y

# Copiamos el resto del proyecto
COPY . .

# Usuario no-root para el runtime
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Healthcheck simple: la raíz responde con redirect (302) cuando la app está viva.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys;\
r=urllib.request.urlopen('http://localhost:5000/', timeout=3);\
sys.exit(0 if r.status in (200,302) else 1)" || exit 1

# `main:create_app()` es el factory. Gunicorn lo invoca para armar la app.
# 2 workers alcanzan para v0.1; ajustar según carga.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--worker-tmp-dir", "/dev/shm", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "main:create_app()"]
