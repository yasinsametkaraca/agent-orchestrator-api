#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/agent-orchestrator-api"

# Resolve the target ECR registry from the configured images or AWS account.
# This keeps the login logic DRY and avoids hard-coded registry URLs.
resolve_ecr_registry() {
  if [ -n "${API_IMAGE:-}" ]; then
    echo "${API_IMAGE%%/*}"
  elif [ -n "${WORKER_IMAGE:-}" ]; then
    echo "${WORKER_IMAGE%%/*}"
  elif [ -n "${AWS_ACCOUNT_ID:-}" ]; then
    echo "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  else
    echo ""
  fi
}

echo "[start_application] Changing to app directory..."
cd "$APP_DIR"

ENVIRONMENT="${ENVIRONMENT:-prod}"
AWS_REGION="${AWS_REGION:-eu-central-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"

echo "[start_application] Environment: $ENVIRONMENT (region=${AWS_REGION})"

SSM_PREFIX="/agent-orchestrator-api/${ENVIRONMENT}"
SSM_ENV_FILE=".env"

echo "[start_application] Fetching configuration from SSM: prefix=${SSM_PREFIX}"
rm -f "$SSM_ENV_FILE"
touch "$SSM_ENV_FILE"

# Always expose ENVIRONMENT explicitly
echo "ENVIRONMENT=${ENVIRONMENT}" >> "$SSM_ENV_FILE"

aws ssm get-parameters-by-path \
  --path "$SSM_PREFIX" \
  --with-decryption \
  --recursive \
  --query "Parameters[*].{Name:Name,Value:Value}" \
  --output text |
while read -r name value; do
  key="$(basename "$name")"
  # Defensive check: skip empty keys
  if [ -z "$key" ]; then
    echo "[start_application] Skipping empty SSM key for name=${name}"
    continue
  fi
  echo "${key}=${value}" >> "$SSM_ENV_FILE"
done

echo "[start_application] Rendered $(wc -l < "$SSM_ENV_FILE") environment variables into ${SSM_ENV_FILE}"

echo "[start_application] Loading environment variables from ${SSM_ENV_FILE}..."
set +u
set -a
source "$SSM_ENV_FILE"
set +a
set -u

# After loading .env we have API_IMAGE / WORKER_IMAGE / AWS_ACCOUNT_ID from SSM.
# Resolve the ECR registry and log in once, before pulling images.
ECR_REGISTRY="$(resolve_ecr_registry)"
if [ -n "$ECR_REGISTRY" ]; then
  # Derive AWS_ACCOUNT_ID from the registry host if it was not explicitly set.
  if [ -z "$AWS_ACCOUNT_ID" ]; then
    AWS_ACCOUNT_ID="$(echo "$ECR_REGISTRY" | cut -d'.' -f1 || true)"
  fi
  echo "[start_application] Logging into ECR registry: ${ECR_REGISTRY} (account_id=${AWS_ACCOUNT_ID:-unknown})..."
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
else
  echo "[start_application] WARNING: Could not resolve ECR registry host; skipping ECR login. Image pulls may fail."
fi

if [ -n "${API_IMAGE:-}" ]; then
  echo "[start_application] Pulling API image: ${API_IMAGE}"
  docker pull "${API_IMAGE}"
else
  echo "[start_application] WARNING: API_IMAGE is not set; docker compose will fail if image is missing."
fi

if [ -n "${WORKER_IMAGE:-}" ]; then
  echo "[start_application] Pulling Worker image: ${WORKER_IMAGE}"
  docker pull "${WORKER_IMAGE}"
else
  echo "[start_application] WARNING: WORKER_IMAGE is not set; docker compose will fail if image is missing."
fi

echo "[start_application] Starting containers with docker compose (prod stack)..."
if command -v docker compose >/dev/null 2>&1; then
  docker compose -f docker/docker-compose.prod.yml up -d api worker
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose -f docker/docker-compose.prod.yml up -d api worker
else
  echo "[start_application] ERROR: docker compose executable not found"
  exit 1
fi
