FROM python:3.12-slim

# Set environment variables to optimize Python performance and behavior inside Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

# Install system dependencies and create a secure non-privileged user
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 10001 -U -d /app -s /bin/false appuser

# Copy only requirements first to leverage Docker build cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY static/ static/

# Create data directory and set proper permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Switch to the non-privileged user
USER appuser

EXPOSE 5000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Start the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]

