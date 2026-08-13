#!/usr/bin/env bash
# Проба Ozon в WSL2 — эталонная конфигурация: Camoufox + Xvfb (headless="virtual").
# Это единственный способ повторить проверенную открытую реализацию один в один.
#
# Запуск изнутри WSL:
#     cd /mnt/c/Dev/region-price-monitor/ozon_price_fetch
#     bash run_probe_wsl.sh
#
# Или из Windows двойным кликом по run_probe_wsl.bat

set -u
cd "$(dirname "$0")"

# venv держим в домашней папке Linux, а не на /mnt/c: на виндовом диске
# из WSL ломаются права и симлинки, да и работает это заметно медленнее.
VENV="${HOME}/.cache/ozon-probe-venv"

echo "=== Ozon probe (WSL2 / Xvfb) ==="
echo

if ! grep -qi microsoft /proc/version 2>/dev/null; then
    echo "[i] Похоже, это не WSL, а обычный Linux — тоже подходит."
fi

# ── системные пакеты ────────────────────────────────────────────────
need_apt=()
command -v python3 >/dev/null 2>&1 || need_apt+=(python3)
# Проверять надо ensurepip, а не venv: модуль venv в Ubuntu импортируется всегда,
# а без пакета python3-venv создаётся пустое окружение без pip.
python3 -c "import ensurepip" >/dev/null 2>&1 || need_apt+=(python3-venv)
command -v Xvfb >/dev/null 2>&1 || need_apt+=(xvfb)
# Xvfb без шрифтов и xauth стартует и сразу умирает: "could not open default font 'fixed'"
command -v xauth >/dev/null 2>&1 || need_apt+=(xauth)
dpkg -s xfonts-base >/dev/null 2>&1 || need_apt+=(xfonts-base)
# Firefox из Camoufox тянет за собой GTK и звук
for lib in libgtk-3-0 libasound2t64 libdbus-glib-1-2; do
    dpkg -s "$lib" >/dev/null 2>&1 || need_apt+=("$lib")
done

if [ ${#need_apt[@]} -gt 0 ]; then
    echo "[1/4] Ставлю системные пакеты: ${need_apt[*]}"
    echo "      (нужен sudo — введи пароль от WSL)"
    sudo apt-get update -qq
    # libasound2t64 есть только в свежих Ubuntu; на старых имя другое
    if ! sudo apt-get install -y -qq "${need_apt[@]}" 2>/dev/null; then
        echo "      пробую со старыми именами пакетов ..."
        fallback=("${need_apt[@]/libasound2t64/libasound2}")
        sudo apt-get install -y -qq "${fallback[@]}" || {
            echo "[ERROR] apt не справился. Поставь вручную: xvfb python3-venv libgtk-3-0"
            exit 1
        }
    fi
else
    echo "[1/4] Системные пакеты на месте"
fi

# ── Xvfb: проверяем живьём, а не «файл на месте» ────────────────────
# Каталог сокетов X в WSL часто отсутствует после чистой установки.
if [ ! -d /tmp/.X11-unix ]; then
    sudo mkdir -p /tmp/.X11-unix && sudo chmod 1777 /tmp/.X11-unix
fi

xvfb_log="$(mktemp)"
Xvfb :99 -screen 0 1280x1024x24 >"$xvfb_log" 2>&1 &
xvfb_pid=$!
sleep 2
if kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "      Xvfb стартует нормально"
    kill "$xvfb_pid" 2>/dev/null
    wait "$xvfb_pid" 2>/dev/null
else
    echo
    echo "[ERROR] Xvfb не запускается. Что он говорит на самом деле:"
    echo "----------------------------------------------------------"
    sed 's/^/    /' "$xvfb_log"
    echo "----------------------------------------------------------"
    echo "    Чаще всего лечится так:"
    echo "      sudo apt-get install -y xvfb xauth xfonts-base"
    rm -f "$xvfb_log"
    exit 1
fi
rm -f "$xvfb_log"

# ── venv ────────────────────────────────────────────────────────────
# Годным считается только то окружение, в котором реально есть pip.
venv_ok() {
    [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -m pip --version >/dev/null 2>&1
}

if venv_ok; then
    echo "[2/4] venv на месте"
else
    if [ -d "$VENV" ]; then
        echo "[2/4] venv битый (нет pip) — пересоздаю"
        rm -rf "$VENV"
    else
        echo "[2/4] Создаю venv"
    fi
    mkdir -p "$(dirname "$VENV")"
    python3 -m venv "$VENV" || { echo "[ERROR] venv не создался"; exit 1; }

    if ! venv_ok; then
        echo "      pip не появился — доставляю через ensurepip"
        "$VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
    if ! venv_ok; then
        echo "[ERROR] pip в окружении так и нет."
        echo "        Поставь пакет и запусти снова:  sudo apt-get install -y python3-venv"
        exit 1
    fi
    echo "      готово: $VENV"
fi

PY="$VENV/bin/python"

# ── питоновские зависимости ─────────────────────────────────────────
echo "[3/4] Ставлю зависимости (первый раз это займёт пару минут)"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet curl-cffi "camoufox[geoip]" pyvirtualdisplay || {
    echo "[ERROR] pip не справился"; exit 1;
}

# Никаких флаг-файлов: они врут. `camoufox fetch` сам проверяет, что уже скачано,
# и при актуальной версии отрабатывает мгновенно.
echo "      Проверяю браузер Camoufox (первый раз ~100 МБ)"
if ! "$PY" -m camoufox fetch; then
    echo "[ERROR] браузер Camoufox не скачался."
    echo "        Попробуй вручную:  $PY -m camoufox fetch"
    exit 1
fi

# Убеждаемся, что бинарник действительно на месте, а не «скачался по отчёту».
if ! "$PY" -c "from camoufox.pkgman import installed_verstr; installed_verstr()" >/dev/null 2>&1; then
    echo "      проверка установки не прошла — переустанавливаю принудительно"
    "$PY" -m camoufox remove >/dev/null 2>&1 || true
    "$PY" -m camoufox fetch || { echo "[ERROR] Camoufox поставить не удалось"; exit 1; }
fi
rm -f "$VENV/camoufox_fetched.flag" 2>/dev/null || true

# ── прогон ──────────────────────────────────────────────────────────
# Внутренний "virtual" режим Camoufox идёт через pyvirtualdisplay, и в WSL он
# не договаривается с Xvfb. Поднимаем дисплей снаружи сами и запускаем браузер
# обычным headed-режимом в него — результат тот же, но без чёрного ящика.
if command -v xvfb-run >/dev/null 2>&1; then
    echo "[4/4] Запускаю пробу: настоящий браузер внутри Xvfb (xvfb-run)"
    echo
    xvfb-run -a --server-args="-screen 0 1920x1080x24" \
        "$PY" ozon_session_probe.py --engine camoufox --visible "$@"
    code=$?
else
    echo "[4/4] xvfb-run не найден — пробую внутренний virtual-режим Camoufox"
    echo
    "$PY" ozon_session_probe.py --engine camoufox "$@"
    code=$?
fi

echo
echo "Код возврата: $code"
exit $code
