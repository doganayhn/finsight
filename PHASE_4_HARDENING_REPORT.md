# Phase 4 Confirmation Hardening Report

## 1. Previous behavior

Any candidate could receive an explicit skip decision, allowing valid non-duplicate statement rows to be omitted.

## 2. Corrected confirmation behavior

All valid non-duplicates import automatically. Only current duplicate candidates accept import/skip decisions. Both skip and unnecessary import decisions for non-duplicates return safe HTTP 422 `decision_for_non_duplicate_candidate`.

## 3. Confirm-time duplicate decisions

Existing account/batch locks remain. Duplicate detection reruns inside the transaction before validating decisions. Every current duplicate requires a decision (missing resolution: 409). Unknown batch candidate IDs remain invalid (422). Newly appearing duplicates require resolution; disappearing flags invalidate stale decisions. Completed batches retain their existing idempotent no-write response.

## 4. Counter/response semantics

Renamed `skipped_rows` to `skipped_duplicate_rows`. Completed `valid_rows = imported_rows + skipped_duplicate_rows`; only explicitly skipped current duplicates can contribute to the skipped count. `duplicate_rows` records all confirm-time flagged candidates, including those explicitly imported. Pending/failed skipped counts are zero. No database column was added. Reported/parsed totals retain source statement reconciliation semantics.

## 5. Tests added/changed

Six new cases (three tests parametrized for import and skip) verify non-duplicate decision rejection, mixed normal/duplicate batches, and disappearing duplicate flags. They verify safe 422 errors, staging retention, no partial canonical inserts, automatic normal-row import, explicit duplicate import/skip, counters, unchanged reconciliation totals, and repeated confirmation. Existing tests cover newly discovered duplicates, unknown IDs, rollback, and concurrent confirmation; all remain passing. Counter assertions use the new response name.

## 6. Full test result

`docker compose exec -T backend pytest`: **124 passed**, including 31 import cases. Two existing Starlette/httpx and AnyIO deprecation warnings remain. Both `ruff check .` and `ruff format --check .` passed (96 files formatted in the image).

## 7. Alembic result

`alembic current`: **0002 (head)**. `alembic check`: **No new upgrade operations detected.** Existing migration tests pass. No migration was added or edited for this correction.

## 8. Docker, health, frontend

`docker compose up --build -d --wait` succeeded; all three containers are healthy. `docker compose config --quiet` passed. GET `/api/v1/health` returned HTTP 200 and `{"status":"ok"}`. `docker compose exec -T frontend npm run build` passed TypeScript and Vite checks. Existing localhost port publication is unchanged.

## 9. Files modified

- `backend/app/modules/imports/service.py`: restrict decisions to current duplicate IDs.
- `backend/app/modules/imports/api_schemas.py`: explicit skipped-duplicate counter.
- `backend/tests/test_imports.py`: regression cases and counter assertions.
- `README.md`: corrected confirmation/counter contract and current Alembic head guidance.
- `PHASE_4_REPORT.md`: corrected semantics and updated verification counts.
- Added this `PHASE_4_HARDENING_REPORT.md`.

## 10. Schema/domain scope

No schema or domain expansion. Existing migration files, staging model, ImportBatch model, and canonical Transaction model were unchanged during hardening. Lock ordering, atomic rollback, and parser boundaries remain intact.

## 11. Sensitive data

Only synthetic test data was used for this correction. The real PDF remains outside the repository; it was neither imported nor copied for hardening. No sensitive data was added. Frozen engineering documents remain byte-identical to the original ZIP. Git whitespace checks pass.

## 12. Phase scope

No Phase 5+ work, merchant normalization, categorization, editing/deletion API, analytics, UI, or authentication was added.

## 13. Git status

No staging, commit, push, branch change, or history rewrite occurred. The index is empty. HEAD remains frozen Phase 3 `f265ab1b4e099e6fb5bd78b0c0709b689037598b`; all Phase 4 work remains uncommitted for review.
