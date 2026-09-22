# ==========================================
# Stage 1: Build static assets
# ==========================================
FROM node:20-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ==========================================
# Stage 2: Exportable artifact container
# ==========================================
FROM alpine:3.20 AS export

WORKDIR /dist

COPY --from=builder /app/dist /dist

# Container holds compiled static assets ready for S3 sync
CMD ["ls", "-la", "/dist"]
