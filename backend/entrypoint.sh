#!/bin/sh
set -eu

alembic upgrade head

case "${SEED_ON_STARTUP:-false}" in
  1|true|TRUE|yes|YES)
    python -m app.seed
    ;;
esac

exec uvicorn app.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  --log-level "${LOG_LEVEL:-info}"
