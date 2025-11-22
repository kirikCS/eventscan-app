# Use Python 3.10 for better ML package compatibility
FROM python:3.10-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.3

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

# Install Python dependencies (with retries for network issues)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ backend/
COPY data/ data/
COPY gemma-3-1b-it-Q4_K_M.gguf


# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set permissions
RUN chown -R nobody:nogroup /app
USER nobody

# Command to run the bot
CMD ["python", "backend/main.py"]
