# Commits and PRs

- [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
- One PR = one vertical slice. Cross-cutting fixes get their own `chore:` PR.
- Work only on branches off `main` (`feat/<subject>`, `chore/...`, `docs/...`, `task/...`); the `protect-main` hook blocks direct edits to `main`.
- Merge only via a PR; direct `git push origin main` is forbidden for agents. Force-push is forbidden (`deny` in settings); adding/changing remotes requires the owner's explicit instruction.
- Direct push to `main` — human (owner) only.

## Push and responsibility

- Cowork inspects the repo via the GitHub MCP (read-only) and pushes ONLY prompt files to `task/**` branches (see `COWORK.md`).
- Product-code writes (commit/branch/PR/merge) — the GitHub Actions worker or Claude Code locally.
