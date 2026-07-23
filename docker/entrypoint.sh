#!/bin/bash
# Container entrypoint: apply migrations, then exec the requested command.
# `depends_on: condition: service_healthy` (compose) already gates on Postgres being up;
# `alembic upgrade head` is idempotent, so re-running it on every start is safe.
set -euo pipefail

alembic upgrade head
exec region-price-monitor "$@"
