FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_INDEX_URL=https://pypi.org/simple/ \
    PIP_TRUSTED_HOST=pypi.org

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgl1 \
    libsm6 \
    libxrender1 \
    libxext6 \
    ffmpeg \
    libsndfile1 \
    libpq-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir --retry 5 --timeout 60 -r requirements.txt

COPY backend/ backend/
COPY data/dataset-it-profession.csv data/dataset-it-profession.csv
COPY gemma-3-1b-it-Q4_K_M.gguf gemma-3-1b-it-Q4_K_M.gguf

RUN mkdir -p /app/data /app/logs

RUN chown -R nobody:nogroup /app
USER nobody

HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "backend/main.py"]
