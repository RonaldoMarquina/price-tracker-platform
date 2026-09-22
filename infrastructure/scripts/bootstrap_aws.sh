#!/usr/bin/env bash
# ==============================================================================
# Price Tracker Platform - Bootstrap Script (Phase 1)
# ==============================================================================
# This script provisions:
# 1. Private S3 Bucket for Terraform Remote State (with versioning, SSE, use_lockfile)
# 2. Immutable ECR Repositories with vulnerability scanning (backend & worker)
# 3. AWS Secrets Manager Secret shell for INTERNAL_API_KEY (value set securely out-of-band)
# 4. AWS Budgets ($5.00 USD with alerts at $1, $3, $5)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_DIR="${SCRIPT_DIR}/../terraform/bootstrap"
AWS_PROFILE="${AWS_PROFILE:-price-tracker-demo}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=== Price Tracker Platform - AWS Bootstrap ==="
echo "AWS Profile: ${AWS_PROFILE}"
echo "AWS Region:  ${AWS_REGION}"

# 1. Verify Authentication
echo "[1/4] Verificando identidad de sesión AWS..."
aws sts get-caller-identity --profile "${AWS_PROFILE}" --region "${AWS_REGION}" > /dev/null
echo "✓ Sesión activa y autenticada."

# 2. Apply Bootstrap Terraform
echo "[2/4] Aprovisionando estado remoto S3, ECR, Secret shell y Budget..."
docker run --rm \
  -v "${BOOTSTRAP_DIR}:/infra" \
  -w /infra \
  -v "${HOME}/.aws:/root/.aws:ro" \
  -e "AWS_PROFILE=${AWS_PROFILE}" \
  -e "AWS_REGION=${AWS_REGION}" \
  hashicorp/terraform:latest init

docker run --rm \
  -v "${BOOTSTRAP_DIR}:/infra" \
  -w /infra \
  -v "${HOME}/.aws:/root/.aws:ro" \
  -e "AWS_PROFILE=${AWS_PROFILE}" \
  -e "AWS_REGION=${AWS_REGION}" \
  hashicorp/terraform:latest apply -auto-approve

# 3. Extract Outputs
STATE_BUCKET=$(docker run --rm -v "${BOOTSTRAP_DIR}:/infra" -w /infra hashicorp/terraform:latest output -raw state_bucket_name)
BACKEND_ECR=$(docker run --rm -v "${BOOTSTRAP_DIR}:/infra" -w /infra hashicorp/terraform:latest output -raw backend_repository_url)
WORKER_ECR=$(docker run --rm -v "${BOOTSTRAP_DIR}:/infra" -w /infra hashicorp/terraform:latest output -raw worker_repository_url)
SECRET_NAME=$(docker run --rm -v "${BOOTSTRAP_DIR}:/infra" -w /infra hashicorp/terraform:latest output -raw internal_api_key_secret_name)
SECRET_ARN=$(docker run --rm -v "${BOOTSTRAP_DIR}:/infra" -w /infra hashicorp/terraform:latest output -raw internal_api_key_secret_arn)

echo "✓ Recursos base creados:"
echo "  - S3 State Bucket: ${STATE_BUCKET}"
echo "  - ECR Backend:     ${BACKEND_ECR}"
echo "  - ECR Worker:      ${WORKER_ECR}"
echo "  - Secret Name:     ${SECRET_NAME}"

# 4. Populate Secret Securely Out-of-Band (if not yet populated)
echo "[3/4] Configuración del secreto INTERNAL_API_KEY..."
CURRENT_SECRET=$(aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --profile "${AWS_PROFILE}" --region "${AWS_REGION}" --query 'LastChangedDate' --output text 2>/dev/null || echo "None")

if [ "${CURRENT_SECRET}" = "None" ] || [ -z "${CURRENT_SECRET}" ]; then
  echo "Generando token seguro de 32 caracteres para INTERNAL_API_KEY..."
  GENERATED_KEY=$(openssl rand -hex 16)
  aws secretsmanager put-secret-value \
    --secret-id "${SECRET_NAME}" \
    --secret-string "${GENERATED_KEY}" \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" > /dev/null
  unset GENERATED_KEY
  echo "✓ INTERNAL_API_KEY almacenado en AWS Secrets Manager (sin exposición en logs ni código)."
else
  echo "✓ El secreto ${SECRET_NAME} ya contiene un valor asignado."
fi

echo "[4/4] Bootstrap completado exitosamente."
echo "Próximo paso: compilar y empujar imágenes Docker con el commit SHA inmutable."
