#!/bin/sh
# Container entrypoint (DECISIONS.md D-035): migrate -> seed the demo ledger once -> serve.
#
# This file must keep LF line endings (.gitattributes: *.sh text eol=lf).
#
# Entrypoint-only switches (not app settings, so no AM_ prefix):
#   FORWARDED_ALLOW_IPS       addresses whose X-Forwarded-* headers uvicorn trusts
#                             (default 127.0.0.1 = none outside the container)
#   DEMO_SEED_ON_FAILURE      abort (default) | continue
#   DEMO_SEED_RETRY_DELAY     seconds to wait before exiting after a failed seed (default 300)
set -eu

log() {
    printf '[entrypoint] %s\n' "$*"
}

# `docker stop` during the wait below must end the container at once.
trap 'exit 143' TERM INT

cd /app

# Settings are validated here for the first time: a production instance without the demo
# lock or a login stops at this line with the reason (app/config.py).
log "alembic upgrade head"
alembic upgrade head

# Same spellings pydantic accepts for a boolean, so the seed and the app agree.
demo_mode="$(printf '%s' "${AM_DEMO_MODE:-false}" | tr '[:upper:]' '[:lower:]')"
case "$demo_mode" in
    true | 1 | yes | on | y | t) demo_mode=true ;;
    *) demo_mode=false ;;
esac

if [ "$demo_mode" = "true" ]; then
    if [ "${AM_MARKET_PROVIDER:-yfinance}" = "fake" ]; then
        log "WARNING: AM_MARKET_PROVIDER=fake serves synthetic prices. Never publish this instance."
    fi

    count="$(
        python - <<'PY'
from sqlalchemy import func, select

from app.db.models import Transaction
from app.db.session import SessionLocal

with SessionLocal() as db:
    print(db.scalar(select(func.count()).select_from(Transaction)) or 0)
PY
    )"
    # Anything but a plain number means the count itself went wrong: stop instead of
    # mistaking it for "already seeded" and serving an empty demo.
    case "$count" in
        '' | *[!0-9]*)
            log "ERROR: could not count the demo transactions (got: $count)"
            exit 1
            ;;
    esac

    if [ "$count" = "0" ]; then
        # seed.load prices every demo trade at the provider's close on its trade date and
        # inserts all trades in one transaction, so a failure leaves the ledger empty.
        log "demo ledger is empty: python -m seed.load"
        if python -m seed.load; then
            log "demo ledger seeded"
        elif [ "${DEMO_SEED_ON_FAILURE:-abort}" = "continue" ]; then
            log "ERROR: seeding the demo ledger failed (output above)."
            log "DEMO_SEED_ON_FAILURE=continue: serving with an EMPTY ledger. Prices were not"
            log "replaced by synthetic data. Restart the container to try the seed again."
        else
            delay="${DEMO_SEED_RETRY_DELAY:-300}"
            log "ERROR: seeding the demo ledger failed (output above)."
            log "Not serving an empty demo and not falling back to synthetic prices."
            log "Exiting in ${delay}s; the restart policy then tries again. The wait keeps the"
            log "retry loop from hammering the price provider. To serve an empty ledger"
            log "instead, set DEMO_SEED_ON_FAILURE=continue."
            sleep "$delay" &
            wait $!
            exit 1
        fi
    else
        log "demo ledger has $count transactions: seed skipped"
    fi
fi

# One worker, always: the services keep per-process memory caches and background threads.
# The port is only reachable from the compose network and the host's loopback.
log "starting uvicorn (1 worker)"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --no-server-header
