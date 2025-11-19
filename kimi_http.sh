#!/usr/bin/env bash
set -euo pipefail

export KIMI_BASE_URL="https://api.moonshot.cn/v1"
export KIMI_API_KEY="sk-nTsoaA6wa8mqaDIXzlKkz24KGnXMwfLhmrKWhfvA6ue5ZDbU"
export KIMI_MODEL_NAME="kimi-k2-thinking"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

: "${KIMI_BASE_URL?Set KIMI_BASE_URL before running kimi_http.sh}"
: "${KIMI_API_KEY?Set KIMI_API_KEY before running kimi_http.sh}"
: "${KIMI_MODEL_NAME:=kimi-for-coding}"

HOST=${KIMI_HTTP_HOST:-0.0.0.0}
PORT=${KIMI_HTTP_PORT:-9000}



exec uv run python -m kimi_http.server --host "$HOST" --port "$PORT"
