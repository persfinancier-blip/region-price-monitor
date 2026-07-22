#!/bin/sh
# DoD gate for region-price-monitor — ALL project checks live here.
# Run by .github/workflows/claude.yml before auto-merge, and locally before a PR.
# Exit 0 = green (auto-merge allowed), non-zero = red (PR stays open).
# Keep it zone-scoped if the project grows: check `git diff --name-only origin/main...HEAD`
# and only run the checks for touched zones.

set -e

# # TBD — команды проверок добавит первый продуктовый промпт
# Examples:
#   python -m ruff check . && python -m mypy app && python -m pytest
#   npm ci && npm run lint && npm run build

echo "DoD gate: no checks configured yet — passing trivially."
exit 0
