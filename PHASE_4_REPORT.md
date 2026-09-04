# FinSight Phase 4 — Manual Statement Import Pipeline

Date: 2026-09-04

## 1. Phase 4 Status

Implemented and verified; ready for review, not yet frozen. The repository started clean on `main` at `f265ab1b4e099e6fb5bd78b0c0709b689037598b`, matching `origin/main` and GitHub. That remains HEAD. No frozen architecture document or canonical Transaction column changed.

## 2. Import API Endpoints

- `POST /api/v1/imports/preview`: multipart `file` and `account_id`; 201 preview.
- `GET /api/v1/imports/{import_batch_id}`: owned preview/status and refreshed duplicate hints.
- `POST /api/v1/imports/{import_batch_id}/confirm`: JSON decisions; 200 completed result.

Health remains at `/api/v1/health`. No account CRUD or financial frontend was added.

## 3. User/Account Context Strategy Before Authentication

`X-Dev-User-ID` is an explicitly caller-asserted UUID, **not authentication**. The backend verifies account and batch ownership for every operation. Unowned/missing objects return 404 without disclosing their existence. Import routes are disabled outside `APP_ENV=development`. This plumbing is only for local development; authentication remains future work.

## 4. Upload Validation

Require non-empty content, `.pdf`, `application/pdf`, `%PDF-` magic, and successful strict text-layer extraction. `MAX_UPLOAD_BYTES=10485760` defaults to 10 MiB, balancing ordinary monthly statements with bounded uploads. The ASGI body limit adds 64 KiB for multipart overhead and checks streamed bytes, including requests without Content-Length. File reading separately stops at limit plus one. `MAX_PDF_PAGES=50` is checked before text extraction. Both limits are environment-configurable. Encrypted/image-only PDFs remain unsupported.

## 5. Raw File Lifecycle

Framework upload spool → bounded memory → exact-byte hash → extraction/parsing → discard. Uploads close normally, including error paths. No persistent raw upload directory, PDF database column, or full extracted text is created. Submitted filenames are discarded; `original_filename` stores the generic `statement.pdf` to avoid retaining PII in filenames.

## 6. SHA-256 / File Idempotency

Lowercase 64-character SHA-256 hashes exact uploaded bytes. Under an account lock, pending or completed matches on `(user_id, account_id, file_hash)` return 409 with the existing batch ID. Pending previews are recovered through GET. FAILED attempts do not block retry; a test verifies the same file can succeed after an earlier processing failure. Confirmation rechecks completed-file conflicts.

## 7. Parser Registry

`ParserRegistry.resolve` selects exactly one registered parser. Zero matches produce `unsupported_statement` (415); multiple matches produce `ambiguous_statement_parser` (422). Only the existing TLcard parser is registered. ImportService contains no bank-selection conditionals. Parsers and DTOs remain independent of SQLAlchemy/persistence.

## 8. ImportBatch State Transitions

Normal orchestration assigns PENDING → PARSED → AWAITING_CONFIRMATION, then a later confirmation commits COMPLETED. Intermediate PENDING/PARSED assignments occur inside the preview transaction. Recognized validation failures, unsupported documents, and extraction failures retain a FAILED batch with safe metadata and no candidates. Basic file/header/size errors precede batch creation. Existing nullable provider fields already permit unsupported-attempt records; no financial nullability was weakened.

## 9. Preview Staging Design

`import_transaction_candidates` persists provider-neutral candidate UUIDs, batch FK, dates, raw transaction description/merchant, Decimal amount, currency, semantic type, optional source ID, row/page provenance, and creation timestamp. Unconfirmed candidates never enter canonical transactions. The parser DTO gained an optional source ID for future source-aware duplicate checks; no additional parser was implemented.

## 10. Migration Added

Revision `0002_import_staging.py`, following 0001, creates staging and adds nullable `ImportBatch.statement_period` (source label). This additive import metadata preserves the monthly label without inventing exact billing dates. Canonical Transaction and all other Phase 2 table structures are unchanged. Downgrade removes staging and the new period-label column; it is tested only in disposable databases.

## 11. Preview Response Design

Typed responses include batch state, provider/type, currency, source period label, parser provenance, validation, reconciliation totals, counters, candidate UUIDs, and duplicate match IDs/kinds. Pydantic serializes Decimal amounts as strings. GET works in a later request against database-backed staging. Completed responses return status/counts and no staging transaction list.

Counter semantics: total = valid + failed; duplicate is an overlapping subset of valid, not an additive bucket. Failed reconciliation rejects the entire parsed set. Imported counts actual canonical rows; completed skipped_duplicate_rows = valid − imported (only explicitly skipped duplicates). GET refreshes duplicate hints/counts; persisted duplicate_rows records the preview/confirmation snapshot. Reported and parsed totals remain positive qualifying purchase magnitudes, even after explicit skips.

## 12. Duplicate Detection Strategy

Stable source IDs compare within account, institution, and parser identity. Without comparable stable IDs, exact date/amount/currency and whitespace/case-normalized raw descriptions produce heuristic matches. Candidate-to-candidate matches within one preview are also flagged. Comparisons never rewrite stored descriptions or populate merchant_normalized. Queries are scoped by user/account and narrowed by candidate dates/source IDs.

## 13. Duplicate Resolution Strategy

Confirmation accepts `{"decisions": {"candidate-uuid": "import" or "skip"}}`. Every currently flagged candidate needs an explicit decision; otherwise 409 `duplicate_resolution_required`. Unknown IDs or invalid decisions return 422. Strong and heuristic signals require review; neither silently discards rows. Users can explicitly retain legitimate repetitions. Decisions for unflagged candidates (including unnecessary import decisions) return 422 `decision_for_non_duplicate_candidate`. All non-duplicates import automatically. Decisions are validated against the duplicate set recomputed under the confirmation locks, including flags that have appeared or disappeared since preview.

## 14. Confirmation Transaction / Locking

Acquire account then batch `FOR UPDATE`, refresh state, recheck ownership/currency/file duplicates and transaction matches, insert accepted canonical rows, delete staging, and mark COMPLETED in one SQLAlchemy transaction. Account locking serializes different imports into the same account, closing the cross-batch duplicate-check race. GET uses the same lock order to return consistent state/candidates during concurrent confirmation. Failure injection after canonical inserts proves cleanup/status/rows all roll back.

## 15. Confirmation Idempotency

A repeated confirmation of COMPLETED returns the existing completed result without new inserts. Concurrent double-confirm tests use separate PostgreSQL sessions; both return completion with exactly one set of canonical rows. Concurrent different-batch confirmation forces the later request to resolve newly visible duplicates.

## 16. Staging Cleanup

Successful confirmation deletes all batch staging rows in the same transaction as canonical persistence. Failed parsing/validation retains no transaction content. A failed confirmation retains its usable preview for retry. Abandoned pending previews currently require deliberate cleanup; no automatic expiry or cancellation endpoint was added.

## 17. Real Private PDF Preview Smoke Test

Passed through the running local HTTP preview endpoint. Only permitted aggregates are reported:

| Check | Result |
| --- | --- |
| Transaction count | 28 |
| Reported total | 9324.79 |
| Parsed total | 9324.79 |
| Validation | PASSED |

Hash, parser resolution, pending batch, and staging were verified locally. No confirmation request was sent. The test used a unique synthetic user/account, then deleted that context and its preview/candidates in a finally block. Before/after database counts matched; canonical transactions were unchanged. The private PDF remained outside the repository and was not copied into a container file.

## 18. Synthetic End-to-End Import Result

The independently authored Phase 3 fixture completed POST preview → stored staging → GET → POST confirm → COMPLETED. Three canonical rows exactly match synthetic candidate dates, descriptions, merchants, signs, amounts, and currency. Category and normalized merchant remain null; defaults are UNKNOWN / NEEDS_REVIEW. Staging is removed. Repeated confirmation preserves row count; exact re-upload conflicts. All test records are cleaned up.

## 19. Tests Added

31 import test cases cover registry ambiguity/rejection, upload validation/limits, SHA-256, context ownership, persistent preview/provenance/totals, invalid statements/retries, source-ID and heuristic matching, internal duplicates, explicit decisions, confirm-time recheck, canonical defaults, idempotency, spool closure/privacy, account isolation, and transaction rollback. Six hardening cases cover rejecting non-duplicate decisions, mixed normal/duplicate completion, and disappearing duplicate flags for both import and skip. Real PostgreSQL concurrency tests cover double confirmation, competing batches, and competing identical previews. One additional migration test covers 0001 → 0002 with existing data preserved, downgrade, re-upgrade, and drift. Existing migration tests now expect the staging table and revision 0002.

## 20. Test Results

**124 passed, 2 existing upstream deprecation warnings** on Docker Python 3.12.14. Ruff lint passed; Ruff format check reports 96 files already formatted in the image. An initial synthetic test construction incorrectly flattened page boundaries; the test was corrected to preserve the fixture's pages, then the full suite passed. No unresolved test failure remains.

## 21. Alembic Results

`upgrade head` passed. `current`: **0002 (head)**. `check`: **No new upgrade operations detected.** Verified empty database → head, 0001 with existing data → 0002, 0002 → 0001 → head, and full downgrade/re-upgrade. Canonical Transaction column/constraint tests still pass.

## 22. Docker / Health Result

Rebuilt with the added multipart dependency. All three containers are healthy; Compose configuration validates. Health returns HTTP 200 with `{"status":"ok"}`. Backend still connects to `postgres:5432`; host PostgreSQL publication remains `127.0.0.1:55433`. All published ports remain localhost-only.

## 23. Frontend Build Result

TypeScript and Vite production build passed (19 modules). Frontend source/configuration is unchanged; generated output is ignored.

## 24. Dependencies Added/Changed

Added only `python-multipart>=0.0.32,<0.1`, pinned to **0.0.32**. Existing pins, pypdf, and Python 3.12 policy are unchanged. Request bounding uses the already-pinned Starlette middleware. References: [python-multipart release](https://pypi.org/project/python-multipart/0.0.32/), [Starlette body-limit middleware](https://www.starlette.io/middleware/).

## 25. Files Added/Modified

**11 added, 13 modified (24 total), including this report and the hardening report.**

Added:

- `PHASE_4_REPORT.md`
- `PHASE_4_HARDENING_REPORT.md`
- `backend/alembic/versions/0002_import_staging.py`
- `backend/app/modules/imports/api_schemas.py`
- `backend/app/modules/imports/errors.py`
- `backend/app/modules/imports/parsers/registry.py`
- `backend/app/modules/imports/repository.py`
- `backend/app/modules/imports/routes.py`
- `backend/app/modules/imports/service.py`
- `backend/app/modules/imports/staging.py`
- `backend/tests/test_imports.py`

Modified: `.env.example`, `README.md`, `docker-compose.yml`, backend `pyproject.toml`, `requirements.lock`, `app/api/v1/router.py`, `app/core/config.py`, `app/db/models.py`, `app/main.py`, `app/modules/imports/models.py`, `app/modules/imports/parsers/pdf_text.py`, `app/modules/imports/schemas.py`, and `tests/test_migrations.py`.

## 26. Privacy / Sensitive Data Verification

No private PDF, extracted document text, copied real transaction descriptions/history, customer details, account/card identifiers, or secrets were added to repository files. Tests use invented data and in-memory synthetic PDFs. Real source descriptions were checked locally against changed files without printing them. Existing private environment/venv/build/cache directories remain ignored. All nine frozen engineering files remain byte-identical to the original ZIP. The canonical Transaction model and revision 0001 remain unchanged.

## 27. Warnings / Unresolved Questions

No blocking architecture conflict or acceptance failure remains. Existing Starlette TestClient/httpx and AnyIO BlockingPortal deprecation warnings persist; Docker pip also reports its standard root-user/update notices. No unrelated upgrade was made to suppress them. This synchronous local workflow has upload/page bounds but no hard CPU timeout for PDF parsing. Pending previews have no automatic expiration. Pre-auth context is deliberately unsuitable for hosted multi-user use. These limits are documented; no authentication, background infrastructure, or future-phase features were added.

Verification commands included:

```sh
docker compose up --build -d --wait
docker compose exec -T backend pytest
docker compose exec -T backend ruff check .
docker compose exec -T backend ruff format --check .
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T frontend npm run build
docker compose config --quiet
docker compose ps
git status --short
git diff
git diff --check
git diff --cached --quiet
```

Also performed local health/OpenAPI checks, private HTTP preview plus cleanup, frozen-file and private-description comparisons, and baseline/ref checks. Local Ruff formatting and copying synthetic test sources into the running container were used during iteration; final checks ran in the rebuilt image.

## 28. Confirmation No Phase 5+ Features Were Implemented

Confirmed. No merchant normalization engine, category rules/seeds, analytics, financial UI, authentication, AI, alternate bank/format adapter, cloud storage, or background processing was introduced. Comparison-only whitespace/case folding does not populate canonical normalized merchant fields.

## 29. Confirmation No Commit/Push Was Performed

Confirmed: no staging, commit, push, amendment, rebase, branch change, or history rewrite. The index remains empty. Phase 4 changes remain uncommitted for review on main, with HEAD/origin/main still at frozen Phase 3. Phase 5 has not started.
