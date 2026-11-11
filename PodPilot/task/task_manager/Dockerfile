# Builder stage: build wheels once, copy only what we need to runtime
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for building wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create a virtualenv to copy as a single directory
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install deps first for better layer caching
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

# Runtime stage: minimal image with venv + app code, run as non-root
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Security: create a non-root user
RUN adduser --disabled-password --gecos "" app \
    && chown -R app:app /app

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Defaults (can be overridden at runtime)
ENV DJANGO_SETTINGS_MODULE=task_manager.settings \
    STATIC_ROOT=/app/staticfiles

# Copy source files
COPY . .
RUN mkdir -p "${STATIC_ROOT}" && chown -R app:app "${STATIC_ROOT}"

USER app

EXPOSE 8000

CMD ["gunicorn", "task_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
