#!/usr/bin/env bash
# Local dev bootstrap. Idempotent.
#
# Uses uv (https://docs.astral.sh/uv/) to provision a Python toolchain
# and an editable workspace covering both apps + the shared package, so
# you can run them straight from your IDE / pytest without docker.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Checking prerequisites"
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' is required. Install with:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
for bin in docker helm terraform git; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "WARN: '$bin' not found on PATH. Install before running deploy steps."
  fi
done

echo "==> Provisioning Python 3.12 + workspace venv via uv"
uv python install 3.12
uv sync --all-packages

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  echo "    Edit .env and set OPENAI_API_KEY (or ANTHROPIC_API_KEY) before running."
fi

echo "==> Done."
echo "    Next steps:"
echo "      docker compose up --build       # local Temporal + worker + gateway"
echo "      open http://localhost:8233      # Temporal UI"
