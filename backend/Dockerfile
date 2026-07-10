# Multi-stage Dockerfile with security hardening
FROM python:3.11-alpine AS builder

WORKDIR /build

# Copy requirements and install dependencies in builder stage
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Final stage
FROM python:3.11-alpine

# Create non-root user for running the application
RUN addgroup -g 1000 appuser && \
    adduser -u 1000 -G appuser -s /sbin/nologin -D appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code with proper ownership
COPY --chown=appuser:appuser . .

# Set proper permissions — code is read-only, data dirs are writable
RUN mkdir -p /app/data /app/trailerd /app/online-platform /app/original /app/logs && \
    chown -R appuser:appuser /app/data /app/trailerd /app/online-platform /app/original /app/logs && \
    chmod -R 755 /app/data /app/trailerd /app/online-platform /app/original /app/logs

# Switch to non-root user
USER appuser

# Expose port (inside container, no special privileges needed)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8000/ || exit 1

# Run application (never use reload=True in production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
