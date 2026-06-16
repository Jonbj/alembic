FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first to avoid pulling the GPU variant
RUN pip install --no-cache-dir \
    torch==2.6.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/

ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"
