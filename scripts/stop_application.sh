#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/agent-orchestrator-api"

if [ -d "$APP_DIR" ]; then
  echo "[stop_application] Stopping containers..."
  cd "$APP_DIR"
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose down || true
  elif command -v docker >/dev/null 2>&1; then
    docker compose down || true
  fi
fi
