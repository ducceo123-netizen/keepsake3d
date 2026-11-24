#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
[[ -x .venv/bin/python ]] || { echo 'Run bash scripts/setup.sh first.'; exit 1; }
[[ -d node_modules ]] || { echo 'Run bash scripts/setup.sh first.'; exit 1; }
if [[ -f .env ]]; then set -a; source .env; set +a; fi
.venv/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
.venv/bin/python - <<'PY'
import time, urllib.request
for attempt in range(50):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=1) as response:
            if response.status == 200: break
    except (OSError, TimeoutError):
        time.sleep(0.2)
else:
    raise SystemExit('API did not become ready on port 8000. Check the log above.')
PY
kill -0 "$API_PID" 2>/dev/null || { echo 'The API process stopped. Is port 8000 already in use?'; exit 1; }
printf '\nOpen http://127.0.0.1:3000. Press Ctrl-C to stop this local session.\n'
npm run dev
