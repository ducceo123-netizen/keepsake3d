#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
command -v node >/dev/null || { echo 'Install Node.js 22.0+ (24 recommended).'; exit 1; }
command -v python3 >/dev/null || { echo 'Install Python 3.11+ (3.14 was used locally).'; exit 1; }
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("Node.js 22+ required by the local tooling."); process.exit(1); }'
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r apps/api/requirements.txt
if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
if [[ ! -f .env ]]; then cp .env.example .env; fi
printf '\nDependencies installed. Set BLENDER_BIN in .env if needed, then run bash scripts/dev.sh.\n'
