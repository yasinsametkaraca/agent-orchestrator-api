#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/agent-orchestrator-api"

echo "[before_install] Stopping existing application if running..."
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR"
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose down || true
  fi
fi

echo "[before_install] Preparing application directory..."
mkdir -p "$APP_DIR"
