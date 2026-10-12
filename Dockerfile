# =============================================================================
# DeepVision Multi-Stage Production Dockerfile
# Stage 1: Build production React 19 SPA frontend with Vite
# Stage 2: Python 3.11 slim runtime hosting unified Django surveillance core
# =============================================================================

# --- Stage 1: Frontend Build ---
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy npm dependency manifests
COPY frontend/package.json frontend/package-lock.json ./

# Clean install frontend dependencies
RUN npm ci

# Copy frontend source code
COPY frontend/ ./

# Compile production React assets into deepvision_django/static/dist
RUN npm run build


# --- Stage 2: Application Runtime ---
FROM python:3.11-slim AS runtime

# Set core runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPVISION_HOST=0.0.0.0 \
    DEEPVISION_PORT=8000 \
    DJANGO_SETTINGS_MODULE=config.settings

# Install system dependencies required by OpenCV, PyTorch, and Healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch CPU-only build matching verified native baseline
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source and launch utilities
COPY manage.py sitecustomize.py start_deepvision.py .env.example ./
COPY deepvision_django/ ./deepvision_django/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY models/yolo11n.pt ./models/yolo11n.pt

# Copy compiled production React frontend assets from Stage 1
COPY --from=frontend-builder /app/deepvision_django/static/dist/ ./deepvision_django/static/dist/

# Create runtime directories for data persistence
RUN mkdir -p instance models recordings evidence outputs dataset

# Create a non-root system user for secure container execution
RUN groupadd -g 1000 deepvision && \
    useradd -u 1000 -g deepvision -d /app -s /bin/bash deepvision && \
    chown -R deepvision:deepvision /app

USER deepvision

EXPOSE 8000

# Healthcheck targeting the canonical Django API health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/health/ || exit 1

# Launch application via the unified production runner
ENTRYPOINT ["python", "start_deepvision.py"]
