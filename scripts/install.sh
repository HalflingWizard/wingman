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
    if [[ -e .env.example ]]; then
        cp .env.example .env
    else
        cat > .env <<'EOF'
WINGMAN_DATABASE_URL=sqlite:///./wingman.db
WINGMAN_WEB_HOST=127.0.0.1
WINGMAN_WEB_PORT=8080
WINGMAN_TELEGRAM_BOT_TOKEN=
WINGMAN_TELEGRAM_OWNER_ID=
WINGMAN_OPENAI_API_KEY=
WINGMAN_OPENAI_MAIN_MODEL=gpt-4o-mini
WINGMAN_USER_NAME=
WINGMAN_PRIMARY_PERSON_NAME=
WINGMAN_TIMEZONE=UTC
EOF
    fi
fi
mkdir -p data logs
echo "Installation complete. Edit .env, then run 'source .venv/bin/activate' and 'wingman start'."
