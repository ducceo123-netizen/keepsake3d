#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
if [[ ! -x .venv/bin/python || ! -d node_modules ]]; then
  bash scripts/setup.sh
fi
exec bash scripts/dev.sh
