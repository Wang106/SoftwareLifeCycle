#!/bin/sh
set -eu

# The alembic console script runs outside /app, so include the application
# directory before it imports app.core.config from alembic/env.py.
export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"

case "${INTRANET_PILOT:-false}" in
  1|true|TRUE|yes|YES)
    case "${SEED_ON_STARTUP:-false}" in
      1|true|TRUE|yes|YES)
        echo "INTRANET_PILOT refuses SEED_ON_STARTUP" >&2
        exit 1
        ;;
    esac
    case "${SEED_ZFI_DEMO:-false}" in
      1|true|TRUE|yes|YES)
        echo "INTRANET_PILOT refuses SEED_ZFI_DEMO" >&2
        exit 1
        ;;
    esac
    case "${AUTH_MODE:-disabled}" in
      oidc) ;;
      *)
        echo "INTRANET_PILOT requires AUTH_MODE=oidc" >&2
        exit 1
        ;;
    esac
    ;;
esac

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
