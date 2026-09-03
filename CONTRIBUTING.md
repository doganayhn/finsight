# FinSight Git Workflow

Follow this policy together with `AGENTS.md` and the frozen engineering documents.

## Phase commits

Do not commit during phase implementation. Small fixes, experiments, individual files, and intermediate states remain uncommitted until the entire phase is complete.

Before a phase commit:

1. Finish only the requested phase.
2. Run the relevant tests, lint, format checks, builds, and infrastructure checks.
3. Produce the phase report and obtain user/reviewer review.
4. Wait for the user to explicitly declare the phase **FROZEN**.
5. Inspect `git status`, unstaged and staged diffs, and ignored files. Review every staged path and its contents for secrets and personal financial data.
6. Create one coherent Conventional Commit for that frozen phase.
7. Push to `origin/main` only after the checks pass and remote history is safe.

Phase 0 and Phase 1 are explicitly frozen. Their initial commits are:

- `docs: freeze FinSight architecture` — only `AGENTS.md` and the frozen documents under `docs/`.
- `feat: complete Phase 1 project foundation` — the completed, hardened foundation and its reports/workflow files.

Starting with Phase 2, normally create exactly one final commit per frozen phase. Never push an unfrozen phase or start the next phase without explicit authorization.

## History and identity

- Primary branch: `main`.
- Remote: `https://github.com/doganayhn/finsight.git`.
- Never force-push, reset remote history, or rewrite public history without an explicit user request.
- If remote history conflicts, stop and report the conflict before changing history.
- Use the user's existing Git identity. Do not invent or change their email, or change global identity settings to make a commit succeed. If identity is missing, stop and report it.

## Files that must never enter history

Never stage or commit `.env`, other private environment files, API keys, passwords, private keys, real bank statements, personal financial data, temporary uploads, local database files, virtual environments, `node_modules`, generated builds, or IDE/system junk.

`.env.example` may contain documented placeholders only. The ignore rules block common financial-document formats and private storage directories. They are defense in depth: inspect the staged contents even when `.gitignore` appears correct.

Sanitized or synthetic fixtures may be added in a later authorized phase only after explicit content review. Any narrowly scoped ignore exception must preserve protection for real personal banking data. Never force-add a real statement.

## Phase 1 verification commands

From the repository root, with Docker services running:

```sh
docker compose exec -T backend pytest
docker compose exec -T backend ruff check .
docker compose exec -T backend ruff format --check .
docker compose config --quiet
git status --short
git diff
git diff --cached
```

From `frontend`, run `npm run build`. Verify that the frozen documents are intact, the staged files contain no private data, and no later-phase functionality was introduced before committing.
