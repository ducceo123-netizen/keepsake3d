#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
[[ -x .venv/bin/python ]] || { echo 'Run bash scripts/setup.sh first.'; exit 1; }
if [[ -f .env ]]; then set -a; source .env; set +a; fi
.venv/bin/python -m pytest tests/api tests/pipeline -q
npm run typecheck
npm run check:design
printf '\nCore checks passed. For browser checks, run npm run test:e2e with the local app available.\n'
