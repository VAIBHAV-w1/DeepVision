# =============================================================================
# DeepVision 4.0 Multi-Stage Production Dockerfile
# Stage 1: Build production React 19 SPA frontend with Vite
# Stage 2: Python 3.11 slim runtime hosting unified Django + YOLO26s ONNX engine
# =============================================================================

# --- Stage 1: Frontend Build ---
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- Stage 2: Application Runtime ---
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENVINO_TELEMETRY=0 \
    DEEPVISION_HOST=0.0.0.0 \
    DEEPVISION_PORT=8000 \
    DJANGO_SETTINGS_MODULE=config.settings

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY manage.py sitecustomize.py start_deepvision.py .env.example ./
COPY deepvision_django/ ./deepvision_django/
COPY scripts/ ./scripts/
COPY docs/ ./docs/

# Fetch official Ultralytics v8.4.0 YOLO26s & YOLO26n ONNX weights and verify exact SHA-256 digests
RUN mkdir -p models instance/ov_cache && \
    curl -fL --retry 3 --retry-all-errors \
      "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s.onnx" \
      -o models/yolo26s.onnx && \
    curl -fL --retry 3 --retry-all-errors \
      "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.onnx" \
      -o models/yolo26n.onnx && \
    echo "d26b65c432111eb95798cd2320603d4d75627605dbec6c6b7f98c499a80e7321  models/yolo26s.onnx" | sha256sum -c - && \
    echo "2e947b787d9e787b93a16772a5f55b1d4d8c4d86f53146149c5d6a642442d6f7  models/yolo26n.onnx" | sha256sum -c -

COPY --from=frontend-builder /app/deepvision_django/static/dist/ ./deepvision_django/static/dist/

RUN mkdir -p instance recordings evidence outputs dataset && \
    groupadd -g 1000 deepvision && \
    useradd -u 1000 -g deepvision -d /app -s /bin/bash deepvision && \
    chown -R deepvision:deepvision /app

USER deepvision

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-${DEEPVISION_PORT:-8000}}/api/health/ || exit 1

ENTRYPOINT ["python", "start_deepvision.py"]
