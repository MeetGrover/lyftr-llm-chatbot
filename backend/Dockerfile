# Multi-stage Dockerfile for FastAPI Backend

# Stage 1: Build wheels
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Minimal runtime
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY . /app

# Ensure SQLite data directory exists
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
