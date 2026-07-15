# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/portfolio.db \
    HOME=/data/home \
    XDG_CONFIG_HOME=/data/home/.config \
    TZ=Europe/Moscow

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        git \
        openssh-client \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 portfolio \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /data/home portfolio

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --requirement requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY docs/ ./docs/
COPY docker/ ./docker/
COPY mcp_server.py LICENSE ./
COPY --from=frontend-build /build/frontend/dist ./frontend/dist/

RUN mkdir -p /data/backups /data/home/.config \
    && chmod 0555 /app/docker/git-askpass.sh \
    && chown -R portfolio:portfolio /data

USER portfolio:portfolio

EXPOSE 8000
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=3).read()"]

CMD ["sh", "-c", "python -m app.cli init && exec python -m app.cli serve --host 0.0.0.0 --port 8000"]
