# ==========================================
# Stage 1: Build dependencies
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==========================================
# Stage 2: Production runtime
# ==========================================
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    PORT=8000

# Copy installed wheels from builder
COPY --from=builder /install /usr/local

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

# Copy shared library, backend application, and alembic configuration
COPY shared/ ./shared/
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic/ ./alembic/
COPY backend/app/ ./app/

# Set ownership to appuser
RUN chown -R appuser:appgroup /app

USER appuser:appgroup

EXPOSE 8000

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
