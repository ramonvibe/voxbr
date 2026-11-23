#!/usr/bin/env bash
# Sobe tudo para desenvolvimento: Postgres, API (:8000), worker de voz e painel (:3000). Ctrl+C derruba tudo.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d db
trap 'kill 0' EXIT
.venv/bin/uvicorn apps.api.main:app --port 8000 &
.venv/bin/python apps/agent/main.py dev &
(cd apps/web && pnpm dev) &
wait
