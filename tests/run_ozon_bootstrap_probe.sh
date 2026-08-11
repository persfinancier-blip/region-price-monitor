#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PY="parser/core/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[ERROR] VENV_NOT_FOUND"
  exit 1
fi

export PYTHONPATH="$PWD/parser/core:$PWD/tools"
"$PY" tools/probe_ozon_zero_human_bootstrap.py
