#!/bin/sh
# PreToolUse(Edit|Write|NotebookEdit|Bash): блокирует запись в main — правки файлов
# (Edit/Write/NotebookEdit) и git-запись через Bash (commit/merge/push).
# Per CONTRIBUTING: работа только в фиче-ветках. Блокировка = exit 2, причина в stderr.

INPUT=$(cat)

BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null) || exit 0
[ "$BRANCH" = "main" ] || exit 0

PROJ=$(printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}" | tr '\\' '/' | tr '[:upper:]' '[:lower:]')

FILE=$(printf '%s' "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);t=d.get('tool_input',{});print(t.get('file_path') or t.get('notebook_path') or '')" 2>/dev/null) || exit 0

if [ -n "$FILE" ]; then
  NORM=$(printf '%s' "$FILE" | tr '\\' '/' | tr '[:upper:]' '[:lower:]')
  case "$NORM" in
    "$PROJ"/*)
      echo "Правки на ветке main запрещены (CONTRIBUTING: trunk-based, только фиче-ветки). Создай ветку: git checkout -b feat/<веха>-<суть> (или chore/..., docs/...) и повтори правку." >&2
      exit 2
      ;;
    *) exit 0 ;;
  esac
fi

# Bash-путь: ловим git-запись (commit/merge/push) прямо на main.
CMD=$(printf '%s' "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);t=d.get('tool_input',{});print(t.get('command') or '')" 2>/dev/null) || exit 0
[ -z "$CMD" ] && exit 0

# Активный merge (разрешение конфликтов) — легитимно, не блокировать.
[ -f "${CLAUDE_PROJECT_DIR:-.}/.git/MERGE_HEAD" ] && exit 0

case "$CMD" in
  *git\ commit*|*git\ merge*|*git\ push*)
    echo "Git-запись (commit/merge/push) на main через Bash запрещена (CONTRIBUTING: trunk-based, только фиче-ветки, слияние через PR). Создай ветку: git checkout -b feat/<веха>-<суть> (или chore/..., docs/...)." >&2
    exit 2
    ;;
  *) exit 0 ;;
esac
