#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${CAUSALGATE_ENV_FILE:-$ROOT_DIR/.causalgate.local.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No local CausalGate environment was found at $ENV_FILE" >&2
  exit 1
fi

cd "$ROOT_DIR"
if [[ "${1:-}" == "--remove-data" ]]; then
  docker compose --env-file "$ENV_FILE" down --volumes
  echo "CausalGate stopped and its local Docker volume was removed."
else
  docker compose --env-file "$ENV_FILE" down
  echo "CausalGate stopped. Local demo data was preserved."
fi
