FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.3

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

RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY data/ data/

RUN mkdir -p /app/ /app/data /app/logs

RUN chown -R nobody:nogroup /app
USER nobody

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "backend/main.py"]
