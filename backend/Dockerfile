FROM python:3.12-slim

# System dependencies (curl for healthcheck, libglib for opencv-headless)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser

WORKDIR /app

# Install Python dependencies from lock file
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy application code
COPY app/ ./app/

# Create data directories with correct ownership
RUN mkdir -p /app/data/uploads /app/data/previews /app/data/results && \
    chown -R appuser:appuser /app/data

# Expose port
EXPOSE 8000

# Switch to non-root user
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with explicit single worker (in-memory stores break with >1 worker)
# --timeout-keep-alive 30 protects against slowloris attacks
# --limit-concurrency 20 prevents overload
# --log-config used for structured JSON logging
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--timeout-keep-alive", "30", \
     "--limit-concurrency", "20", \
     "--log-level", "info"]
