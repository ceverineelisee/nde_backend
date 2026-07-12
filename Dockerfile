# Etape 1: Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Installer les dépendances système POUR LE BUILD
# (build-essential et libpq-dev sont requis pour compiler psycopg depuis les sources)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
# Cette étape force la reconstruction et nous montre ce qui est installé
RUN echo "--- PAQUETS INSTALLÉS DANS LE BUILDER ---" && pip freeze
# ---------------------------------------------------

# Etape 2: Production stage
FROM python:3.12-slim

WORKDIR /app

# Installer SEULEMENT les dépendances runtime
# (postgresql-client est utile pour pg_isready dans l'entrypoint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root
RUN useradd -m -u 1000 django && \
    mkdir -p /app/media /app/staticfiles && \
    chown -R django:django /app

# Copier les packages Python depuis le builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copier le code de l'application
COPY --chown=django:django . .
# S'assurer que le script d'entrypoint a les permissions d'exécution
# (important même si le volume bind mount écrase les permissions)
RUN chmod +x /app/docker-entrypoint.sh

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# Changer vers l'utilisateur non-root
USER django

# Exposer le port (pour la communication interne à Docker)
EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]