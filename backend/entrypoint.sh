#!/bin/sh
set -eu

# The alembic console script runs outside /app, so include the application
# directory before it imports app.core.config from alembic/env.py.
export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"

alembic upgrade head

case "${SEED_ON_STARTUP:-false}" in
  1|true|TRUE|yes|YES)
    python -m app.seed
    ;;
esac

# Reviewed Excel sample family. Explicitly opt-in on a read-only test environment.
case "${SEED_ZFI_DEMO:-false}" in
  1|true|TRUE|yes|YES)
    test "${READ_ONLY_MODE:-false}" = true || { echo 'ZFI import requires READ_ONLY_MODE=true'; exit 1; }
    python -m app.seed_zfi_demo --sample-only
    ;;
esac

exec uvicorn app.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  --log-level "${LOG_LEVEL:-info}"
