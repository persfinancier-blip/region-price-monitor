#!/bin/sh
# statusLine: ⎇ ветка(+dirty) · модель · каталог
# stdin: JSON от Claude Code (model.display_name, workspace.current_dir, ...)

INPUT=$(cat)

MODEL=$(printf '%s' "$INPUT" | python3 -c "import json,sys;print(json.load(sys.stdin).get('model',{}).get('display_name') or '?')" 2>/dev/null || echo '?')
DIR=$(printf '%s' "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin).get('workspace',{});print(d.get('current_dir') or '')" 2>/dev/null)

BRANCH=$(git -C "${DIR:-.}" branch --show-current 2>/dev/null)
if [ -n "$BRANCH" ]; then
  if [ -n "$(git -C "${DIR:-.}" status --porcelain --untracked-files=no 2>/dev/null | head -1)" ]; then
    GIT="⎇ $BRANCH*"
  else
    GIT="⎇ $BRANCH"
  fi
else
  GIT="no-git"
fi

BASE=$(basename "${DIR:-?}" 2>/dev/null || echo '?')
printf '%s · %s · %s' "$GIT" "$MODEL" "$BASE"
