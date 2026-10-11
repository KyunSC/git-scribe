#!/usr/bin/env bash
# Run the backend and frontend dev servers together. Ctrl+C stops both.
#
# The backend port is taken from NEXT_PUBLIC_API_URL (shell, then the root .env),
# so the frontend always calls the backend this script starts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/fastapi-backend"
FRONTEND="$ROOT/frontend"
PY="$BACKEND/.venv/bin/python"
FRONTEND_PORT=3000

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example"
fi

api_url="${NEXT_PUBLIC_API_URL:-$(sed -n 's/^NEXT_PUBLIC_API_URL=//p' "$ROOT/.env" | tail -n 1 | tr -d "\"' \r")}"
api_url="${api_url:-http://localhost:8000}"
backend_port="$(printf '%s' "$api_url" | sed -nE 's#^https?://[^/:]+:([0-9]+).*#\1#p')"
if [[ -z "$backend_port" ]]; then
  echo "NEXT_PUBLIC_API_URL ($api_url) must include a port, e.g. http://localhost:8000" >&2
  exit 1
fi

for port in "$backend_port" "$FRONTEND_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use:" >&2
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2
    if [[ "$port" == "$backend_port" ]]; then
      echo "Stop that process, or point NEXT_PUBLIC_API_URL in .env at a free port." >&2
    fi
    exit 1
  fi
done

if [[ ! -x "$PY" ]]; then
  echo "Missing $PY. Create it with: python3 -m venv fastapi-backend/.venv" >&2
  exit 1
fi
# Always go through `python -m`: the scripts in .venv/bin may have stale shebangs.
if ! "$PY" -c "import fastapi, uvicorn" 2>/dev/null; then
  (cd "$BACKEND" && "$PY" -m pip install -r requirements.txt)
fi
if [[ ! -d "$FRONTEND/node_modules" ]]; then
  (cd "$FRONTEND" && npm install)
fi

pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in ${pids[@]+"${pids[@]}"}; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Job control gives each server its own process group, so cleanup can stop
# their child processes too (uvicorn's reloader worker, next's workers).
set -m
(cd "$BACKEND" && exec "$PY" -m uvicorn main:app --reload --port "$backend_port") &
pids+=($!)
(cd "$FRONTEND" && exec npm run dev -- --port "$FRONTEND_PORT") &
pids+=($!)
set +m

echo "Backend:  http://localhost:$backend_port"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Press Ctrl+C to stop both."

# Stop everything as soon as either server exits.
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do
  sleep 1
done
echo "A server exited; stopping the other." >&2
exit 1
