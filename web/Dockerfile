# syntax=docker/dockerfile:1

# ── Frontend: React + Vite build ────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── Backend: Flask + gunicorn ───────────────────────────────
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY helpers ./helpers
COPY templates ./templates
COPY static ./static
# Outside static/: in k8s static/ is replaced by a PVC mount.
COPY --from=frontend /src/dist ./frontend/dist

EXPOSE 5000

# 2 workers = enough for 2 users; --log-level warning keeps the pod quiet
# sync worker is fine — image resize is CPU-bound not I/O-bound
CMD ["gunicorn", \
     "--workers", "2", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--log-level", "warning", \
     "--access-logfile", "-", \
     "app:app"]
