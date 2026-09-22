# ==========================================
# Stage 1: Build dependencies
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY worker/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==========================================
# Stage 2: Production runtime
# ==========================================
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app"

# Copy installed wheels from builder
COPY --from=builder /install /usr/local

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

# Copy shared library and worker application
COPY shared/ ./shared/
COPY worker/app/ ./app/

# Set ownership to appuser
RUN chown -R appuser:appgroup /app

USER appuser:appgroup

STOPSIGNAL SIGTERM

CMD ["python", "-m", "app.main"]
