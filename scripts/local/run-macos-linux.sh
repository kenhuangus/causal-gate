#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${CAUSALGATE_ENV_FILE:-$ROOT_DIR/.causalgate.local.env}"
PORT="${CAUSALGATE_PORT:-8080}"
export CAUSALGATE_PORT="$PORT"

for command_name in docker openssl curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required. Install or start Docker Desktop." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  {
    echo "CAUSALGATE_ATTESTATION_KEY=$(openssl rand -hex 32)"
    echo "CAUSALGATE_GRANT_SIGNING_KEY=$(openssl rand -hex 32)"
    echo "CAUSALGATE_LIVE_ANALYSIS_ENABLED=true"
    echo "CAUSALGATE_LIVE_ANALYSIS_LIMIT=3"
    echo "CAUSALGATE_PORT=$PORT"
    echo "OPENAI_MODEL=gpt-5.6-sol"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Created local runtime secrets in $ENV_FILE"
fi

cd "$ROOT_DIR"
docker compose --env-file "$ENV_FILE" up --build --wait

for _ in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:$PORT/health" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl --fail --silent "http://127.0.0.1:$PORT/health" >/dev/null; then
  echo "CausalGate did not become healthy. Run: docker compose logs causalgate" >&2
  exit 1
fi

URL="http://localhost:$PORT"
echo "CausalGate is ready at $URL"
echo "The deterministic demo needs no API key. Enter a restricted OpenAI project key in the UI only for optional live analysis."

if [[ "${CAUSALGATE_OPEN_BROWSER:-true}" == "true" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
