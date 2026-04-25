FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Directorios de runtime y permisos al script de arranque
RUN mkdir -p /app/media /app/celerybeat /var/log \
    && chmod +x /app/start.sh

EXPOSE 8000

# start.sh lanza migraciones + celery worker + celery beat + uvicorn
CMD ["bash", "/app/start.sh"]
