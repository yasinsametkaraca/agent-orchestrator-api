#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/agent-orchestrator-api"

echo "[before_install] Stopping existing application if running..."
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR"
  if command -v docker compose >/dev/null 2>&1; then
    echo "[before_install] Using 'docker compose' to stop prod stack..."
    docker compose -f docker/docker-compose.prod.yml down || true
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "[before_install] Using 'docker-compose' to stop prod stack..."
    docker-compose -f docker/docker-compose.prod.yml down || true
  else
    echo "[before_install] docker compose not found; skipping container shutdown"
  fi
fi

echo "[before_install] Preparing application directory..."
mkdir -p "$APP_DIR"
