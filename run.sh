#!/usr/bin/env bash
set -e
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
set -a && source .env && set +a
python -m app.cli init
exec python -m app.cli serve --host 127.0.0.1 --port 8000
