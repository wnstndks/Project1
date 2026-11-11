# Asset Manager: one image with the built frontend and the FastAPI backend (DECISIONS.md D-035).
#
#   docker build -t asset-manager-demo:local .          (from the repository root)
#
# The image holds code only: no .env, no database, no model artifacts (.dockerignore
# allow-lists the build context and the COPY lines below name every folder). Settings come
# from the environment (deploy/docker-compose.yml). Without them the app refuses to start:
# AM_ENV=production needs either AM_DEMO_MODE=true or a login.

# Pinned versions. Change them on purpose, rebuild, and re-run the smoke checks.
# Python 3.11 is what backend/.python-version, local development and CI run; on 3.12 uv.lock
# resolves a different numpy, which no test has exercised.
ARG NODE_IMAGE=node:24.22.2-bookworm-slim
ARG PYTHON_IMAGE=python:3.11.18-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1

# ---- 1. Frontend: npm ci -> tsc -b && vite build -> /build/dist ------------------------------
# The build needs nothing from the backend: the API types (src/api/schema.d.ts) are committed.
FROM ${NODE_IMAGE} AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. uv binary (COPY --from cannot expand a build argument, so it gets a stage) ----------
FROM ${UV_IMAGE} AS uv

# ---- 3. Backend dependencies into /opt/venv -------------------------------------------------
# Only the lock files are copied first, so this layer is rebuilt when dependencies change and
# not on every code edit. --no-default-groups leaves out dev (pytest, ruff), ml (lightgbm,
# transformers) and lstm (torch).
FROM ${PYTHON_IMAGE} AS backend-deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-install-project

# ---- 4. Runtime -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# HOME and the cache folder point at /tmp: the root filesystem is mounted read-only in
# compose, and libraries that keep a small cache (yfinance) write there.
# AM_ENV=production is baked in so that a bare `docker run` of this image fails closed.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    AM_ENV=production \
    AM_STATIC_DIR=/app/static \
    AM_DATABASE_URL=sqlite:////data/asset_manager.db \
    AM_ARTIFACTS_DIR=/data/artifacts

# Unprivileged user. /app stays owned by root (the process cannot change its own code);
# /data is the only folder it may write, and the named volume inherits this ownership.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --home-dir /tmp --no-create-home --no-log-init \
        --shell /usr/sbin/nologin app \
    && mkdir -p /app /data \
    && chown 10001:10001 /data

WORKDIR /app
COPY --from=backend-deps /opt/venv /opt/venv
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/seed ./seed
COPY backend/scripts ./scripts
COPY --from=frontend /build/dist ./static

# A Windows checkout may hand over CRLF line endings, which break `#!/bin/sh`: strip them.
# Bytecode is compiled here because nothing can be written next to the code at run time.
RUN sed -i 's/\r$//' scripts/entrypoint.sh \
    && chmod 0555 scripts/entrypoint.sh \
    && PYTHONDONTWRITEBYTECODE= python -m compileall -q app seed scripts alembic

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000

# No curl in the slim image: ask /api/health with the standard library. The request's Host
# header is 127.0.0.1, so AM_ALLOWED_HOSTS has to keep "127.0.0.1".
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --start-interval=5s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
