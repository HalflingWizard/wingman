#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required")
PY

python3 -m venv .venv
.venv/bin/python -m pip install -qqq --upgrade pip
.venv/bin/python -m pip install -qqq -e '.[dev]'
if [[ ! -e .env ]]; then
    cp .env.example .env
fi
mkdir -p data logs
echo "Installation complete. Edit .env, then run 'source .venv/bin/activate' and 'wingman start'."
