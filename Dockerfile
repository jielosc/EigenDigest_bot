FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user and data directory
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p /data && chown appuser:appuser /data

USER appuser

ENV DB_PATH=/data/eigendigest.db

CMD ["python", "main.py"]
