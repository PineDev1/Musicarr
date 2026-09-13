# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
WORKDIR /app/frontend
RUN npm ci
COPY frontend/ ./
RUN mkdir -p /app/backend/static && npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MUSICARR_DATA_DIR=/config \
    MUSICARR_MUSIC_DIR=/music \
    MUSICARR_HOST=0.0.0.0 \
    MUSICARR_PORT=8787

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/run.py .
COPY --from=frontend /app/backend/static ./static

RUN mkdir -p /config /music

EXPOSE 8787
VOLUME ["/config", "/music"]

CMD ["python", "run.py"]
