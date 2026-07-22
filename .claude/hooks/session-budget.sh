#!/bin/sh
# UserPromptSubmit: предупреждает, когда транскрипт сессии раздулся (> 1.5 MB).
# Owner burns the 5h limit fast; раннее предупреждение — чтобы закрыть сессию
# командой /clear, а не тащить раздутый контекст дальше. Никогда не блокирует.

INPUT=$(cat)

TRANSCRIPT=$(printf '%s' "$INPUT" | python3 -c "import json,sys;print(json.load(sys.stdin).get('transcript_path') or '')" 2>/dev/null) || exit 0
[ -z "$TRANSCRIPT" ] && exit 0
[ -f "$TRANSCRIPT" ] || exit 0

SIZE=$(wc -c < "$TRANSCRIPT" 2>/dev/null | tr -d ' ')
[ -z "$SIZE" ] && exit 0

THRESHOLD=1572864

if [ "$SIZE" -gt "$THRESHOLD" ] 2>/dev/null; then
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "SESSION BUDGET WARNING: this session'"'"'s transcript exceeds 1.5 MB. Finish the current step only, then tell the owner (in Russian, first line of your reply): «Сессия раздулась — закрой её: /clear и новый kickoff». Do not start new work in this session."}}'
fi

exit 0
