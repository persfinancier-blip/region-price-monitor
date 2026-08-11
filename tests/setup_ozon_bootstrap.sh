#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PY="parser/core/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[ERROR] VENV_NOT_FOUND"
  echo "Prepare the normal parser venv first."
  exit 1
fi

echo "[INFO] Installing Playwright Python package into parser venv..."
"$PY" -m pip install "playwright>=1.40"

echo "[INFO] Installing Linux system dependencies for Chromium..."
if [[ "$(id -u)" -eq 0 ]]; then
  "$PY" -m playwright install-deps chromium
elif command -v sudo >/dev/null 2>&1; then
  sudo "$PY" -m playwright install-deps chromium
else
  echo "[ERROR] ROOT_OR_SUDO_REQUIRED_FOR_PLAYWRIGHT_DEPS"
  exit 2
fi

echo "[INFO] Installing Playwright Chromium runtime..."
"$PY" -m playwright install chromium

echo "[PASS] OZON_BOOTSTRAP_PLAYWRIGHT_READY"
