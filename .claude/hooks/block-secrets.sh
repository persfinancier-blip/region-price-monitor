#!/bin/sh
# PreToolUse(Edit|Write): блокирует запись секретов.
# 1) запись в .env-файлы (кроме *.example) и файлы ключей;
# 2) содержимое с сигнатурами реальных токенов (Anthropic, AWS, GitHub, Slack, приватные ключи).
# Блокировка = exit 2, причина в stderr.

INPUT=$(cat)

VERDICT=$(printf '%s' "$INPUT" | python3 -c "
import json, re, sys
d = json.load(sys.stdin)
t = d.get('tool_input', {})
path = str(t.get('file_path') or '').replace('\\\\', '/').lower()
name = path.rsplit('/', 1)[-1]

if (name == '.env' or name.startswith('.env.') or name.endswith('.env')) and 'example' not in name:
    print('ENVFILE'); sys.exit()
if re.search(r'(credentials|secret)[^/]*\.(json|ya?ml|toml|txt)$', name) or name.endswith('-auth.json'):
    print('KEYFILE'); sys.exit()

content = ' '.join(str(t.get(k) or '') for k in ('content', 'new_string'))
patterns = [
    r'sk-ant-[A-Za-z0-9_-]{20,}',
    r'sk-[A-Za-z0-9]{40,}',
    r'AKIA[0-9A-Z]{16}',
    r'ghp_[A-Za-z0-9]{36}',
    r'github_pat_[A-Za-z0-9_]{22,}',
    r'xox[bap]-[A-Za-z0-9-]{10,}',
    r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
]
for p in patterns:
    if re.search(p, content):
        print('TOKEN'); sys.exit()
print('OK')
" 2>/dev/null) || exit 0

case "$VERDICT" in
  ENVFILE) echo "Запись в .env-файл заблокирована хуком block-secrets: секреты не пишем через агента. Правь .env руками; для шаблона используй .env.example." >&2; exit 2 ;;
  KEYFILE) echo "Запись файла ключей/креденшалов заблокирована хуком block-secrets. Секреты не должны попадать в рабочее дерево репозитория." >&2; exit 2 ;;
  TOKEN)   echo "В записываемом содержимом обнаружена сигнатура реального токена/ключа — запись заблокирована хуком block-secrets. Используй переменные окружения (например \${GITHUB_TOKEN}), не литералы." >&2; exit 2 ;;
esac
exit 0
