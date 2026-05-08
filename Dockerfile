# ============================================================
# Dockerfile for Multi-Agent AI Sales Platform
# Builds both the Next.js frontend and FastAPI backend
# ============================================================

# ── Frontend Build Stage ─────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
# We need to set a dummy API URL for the build to pass if required
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
RUN npm run build

# ── Backend Production Stage ─────────────────────────────────
FROM python:3.11-slim AS backend

WORKDIR /app

# Install system dependencies required for psycopg3, audio processing, etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/
# Ensure the upload directory exists
RUN mkdir -p /app/backend/uploads/audio

# Expose backend port
EXPOSE 8000

# Set environment variables for production
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

# Start Uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
