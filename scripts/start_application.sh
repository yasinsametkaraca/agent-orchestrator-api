#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/agent-orchestrator-api"

echo "[start_application] Changing to app directory..."
cd "$APP_DIR"

echo "[start_application] Logging into ECR..."
AWS_REGION="${AWS_REGION:-eu-central-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
if [ -n "$AWS_ACCOUNT_ID" ]; then
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
fi

echo "[start_application] Starting containers..."
docker-compose -f docker/docker-compose.yml up -d api worker
