# Use Python 3.10 for better ML package compatibility
FROM python:3.10-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_INDEX_URL=https://pypi.org/simple/ \
    PIP_TRUSTED_HOST=pypi.org \
    PIP_RETRY=5 \
    PIP_TIMEOUT=60

# Install system dependencies
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

# Set working directory
WORKDIR /app

# Copy dependency files
COPY requirements.txt .

# Install Python dependencies with proper retry configuration
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir --timeout 60 -r requirements.txt

# Copy application code
COPY backend/ backend/
COPY data/dataset-it-profession.csv data/dataset-it-profession.csv
COPY gemma-3-1b-it-Q4_K_M.gguf gemma-3-1b-it-Q4_K_M.gguf

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set permissions
RUN chown -R nobody:nogroup /app
USER nobody

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Command to run the bot
CMD ["python", "backend/main.py"]
