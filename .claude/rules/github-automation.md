# GitHub Actions automation (Claude worker)

- Task = a GitHub issue labeled `ai-task`, **or** a prompt file pushed to a `task/**` branch (Cowork does this — see `COWORK.md`). The worker runs on a GitHub Actions runner (`.github/workflows/claude.yml`).
- One PR per issue/dispatch, opened by the worker and linked back.
- Rework happens only via explicit `@claude <note>` comments on the issue or PR. No bot-to-bot loops.
- All token-economy rules from `CLAUDE.md` apply on the runner exactly as locally.
- **`.github/workflows/**` changes are LOCAL-only:** the default `GITHUB_TOKEN` cannot push changes under `.github/workflows/**`. Any task touching that path must be run locally by Claude Code (or by the owner), never dispatched through the pipeline.

## Auto-merge for worker PRs

- A worker PR (`claude-task-push` job) whose DoD gate passes merges itself (`gh pr merge --merge --delete-branch`). The `claude-issue` and `claude-comment` paths, and any manually-opened PR, merge only on the owner's word.
- PRs/merges made with `GITHUB_TOKEN` don't trigger other workflows (GitHub anti-recursion), so the DoD gate is computed as a plain-shell step inside `claude-task-push` itself: it runs `scripts/dod.sh` if present; no `dod.sh` = the gate passes trivially. Put ALL project checks (lint, typecheck, tests, build) into `scripts/dod.sh`.
- Gate red: the PR is left open with a `🔴 Проверки не прошли` comment. No merge happens.
- Verification is post-merge: Cowork reads the merged result. Rollback path = revert the merge PR.
- Repo settings required (owner sets once): Actions → General → Workflow permissions → **Read and write** + **Allow GitHub Actions to create and approve pull requests**.

## The `claude-task-push` job does not use `anthropics/claude-code-action@v1`

The action rejects the `push` event ("Unsupported event type: push"), so this job installs `@anthropic-ai/claude-code` and runs `claude -p "<prompt>"` directly, authenticated via `CLAUDE_CODE_OAUTH_TOKEN`, with `gh` (`GH_TOKEN`) for PR creation. The `claude-issue` and `claude-comment` jobs use the action normally.

## Prompt-file naming

- Product prompts: `prompt-NN-*.md` (sequential).
- Infrastructure/process prompts: `prompt-ops-NN-*.md` (independent numbering). Both archive to `prompts/_done/`.
