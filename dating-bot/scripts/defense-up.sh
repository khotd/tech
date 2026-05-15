#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo "Создай .env из .env.example и укажи BOT_TOKEN"
  exit 1
fi
docker compose up -d --build
echo "Готово: http://127.0.0.1:8000/health"
