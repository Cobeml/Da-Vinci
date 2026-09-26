#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -d node_modules ]]; then
  echo "Run uv sync and npm ci first. See README.md."
  exit 1
fi
mkdir -p runtime
.venv/bin/python -m uvicorn davinci.api:app --host 127.0.0.1 --port 8215 &
api_pid=$!
.venv/bin/python -m davinci.worker --workers 2 &
worker_pid=$!
.venv/bin/python -m scripts.web &
web_pid=$!
trap 'kill "$api_pid" "$worker_pid" "$web_pid" 2>/dev/null || true' EXIT INT TERM
wait -n "$api_pid" "$worker_pid" "$web_pid"
