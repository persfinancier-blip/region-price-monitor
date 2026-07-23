#!/bin/bash
# Container entrypoint: migrate (Postgres backend only), then exec the requested command.
# `depends_on: condition: service_healthy` (compose) already gates on Postgres being up;
# `alembic upgrade head` is idempotent, so re-running it on every start is safe.
# On the local backend (default, ADR-0009) there is no DB to migrate — just make sure
# LOCAL_STATE_DIR exists.
set -euo pipefail

if [ "${STORAGE_BACKEND:-local}" = "postgres" ]; then
    alembic upgrade head
else
    mkdir -p "${LOCAL_STATE_DIR:-data/state}"
fi

exec region-price-monitor "$@"
