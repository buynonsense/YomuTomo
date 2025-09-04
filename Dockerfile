# syntax=docker/dockerfile:1
# Multi-stage (optional future) single-stage simple production image for FastAPI app

ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS runtime

# Prevent prompts / speed up installs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for building some wheels (e.g. pyaudio needs portaudio)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better layer caching
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application source
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 3434

# Environment (override OPENAI_API_KEY at runtime: -e OPENAI_API_KEY=sk-xxx)
ENV OPENAI_API_KEY="" \
    OPENAI_MODEL="gpt-5-mini"

# Default command (no reload in container; mount source + override CMD for dev if needed)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3434"]

# For development (example):
# docker build -t yomu-dev --build-arg PYTHON_VERSION=3.11 .
# docker run -it --rm -p 8000:8000 -e OPENAI_API_KEY=your_key -v %cd%:/app yomu-dev \
#   uvicorn app:app --host 0.0.0.0 --port 3434 --reload
