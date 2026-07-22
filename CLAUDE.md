# region-price-monitor

Есть задача: по заданному списку товаров в вб и озон парсить цены из разных регионов рф: т.е. надо парсить маркетплейсы еще и подключаясь через региональные прокси. строго на питоне. список берем в постгрисе и результаты пишем в постгрис. сможешь такое наколдовать?
чтобы устойчиво прошивало защиту маркетплейсов и каждый день или несколько раз в день делало замеры

Zone rules live in `.claude/rules/` (commits, github-automation); this file is pointers only.

## Commands

```bash
# TBD — команды проверок добавит первый продуктовый промпт
```

The same checks run in CI as the DoD gate (`scripts/dod.sh`) — all green before a PR.

## Sources of truth

1. `docs/TZ.md` — what we are building and why (product requirements).
2. `docs/adr/` — implementation decisions (create as needed).

## Process

- Branch off `main` (`feat/<subject>`, `fix/...`, `chore/...`, `docs/...`); direct edits to `main` are blocked by a hook. Conventional Commits.
- Merge only via a PR; force-push is forbidden.
- End of every pass: an entry in `docs/DEVLOG.md`, tasks in `BACKLOG.md`.
- Secrets are NEVER committed; `.env` is gitignored, use `.env.example` for shape.

## Token economy

- **Model — Sonnet** (pinned in `.claude/settings.json`); above Sonnet only on the owner's explicit instruction.
- **Minimal read scope:** file → folder → module; never scan the whole repo.
- **Reports stay short:** conclusions and actions; don't recount code or file contents.
- Guardrails are enforced by `.claude/settings.json` — do not weaken them without the owner's instruction.

## Language

- Code, comments, commits, operational files (`.claude/**`, `CLAUDE.md`, `COWORK.md`, prompts) — English.
- Docs for the owner (`docs/**`, `README.md`, `BACKLOG.md`), user-facing UI text, chat with the owner — Russian.
