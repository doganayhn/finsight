# FinSight Phase 5 Report

## 1. Phase 5 Status

Implemented and verified; ready for review, not frozen or committed. Repository: `C:\Users\doğan\Documents\ChatGPT\finsight`. Baseline/local HEAD/GitHub main remain `9f35da2717d64ae45746bebbe6348506d2ac0d92`. All work is unstaged.

## 2. Classification Architecture

Provider-neutral `ClassificationService` coordinates category and merchant repositories and static rules. A structured `ClassificationResult` holds merchant, category, provenance, review status, and safe internal rule metadata. Only its four canonical classification fields are applied. No parser, canonical model, enum, money, or transaction-type changes.

## 3. Comparison-Key Strategy

NFC Unicode normalization, deterministic Turkish casing plus casefolding, trim, and whitespace collapse. Matching context is nonblank `merchant_raw`, otherwise `description_raw`. No arbitrary word deletion, fuzzy matching, or raw-field replacement. Phase 4 duplicate comparison remains unchanged.

## 4. Turkish Unicode Handling

`İ/i` and `I/ı` are distinct case pairs. `Ş/Ğ/Ü/Ö/Ç` retain their Unicode meaning. Composed/decomposed equivalents match through NFC. Tests exercise these characters, casing, whitespace, and idempotence on Docker Python 3.12.14. Public Migros/Getir seeds explicitly cover dotted and ASCII-uppercase variants.

## 5. Category Catalog

18 stable codes with separate English labels: GROCERIES, RESTAURANTS, CAFE, FOOD_DELIVERY, TRANSPORTATION, FUEL, SHOPPING, ENTERTAINMENT, SUBSCRIPTIONS, BILLS, HOUSING, HEALTH, EDUCATION, TRAVEL, FINANCIAL_FEES, INCOME, TRANSFER, OTHER. No custom-category management or localization framework.

## 6. Migration Added

`backend/alembic/versions/0003_system_categories.py`, revision `0003`, follows `0002`. Data only, deterministic UUIDv5 seed IDs, no live application imports. Upgrade inserts missing codes/patterns and preserves existing rows; a non-system category-code collision fails explicitly. Downgrade intentionally retains catalog/alias data, edits, and business references. Re-upgrade is idempotent. No schema changes were necessary.

## 7. Global Merchant Alias Strategy

Existing active `MerchantAlias` rows use normalized literal substring matching. Nine seed patterns cover seven public brands: Migros, Starbucks, Amazon, Trendyol, Trendyol Yemek, Getir, Decathlon. Getir is normalization-only; its category can fall through. Seeds were not derived from private statements.

## 8. Alias Specificity / Tie-Break Strategy

Sort by descending normalized-pattern length, then normalized pattern, original pattern, and UUID. The first matching alias wins. TRENDYOL YEMEK beats TRENDYOL. Tests reverse repository ordering, exercise equivalent normalized patterns, ignore inactive aliases, and verify that regex-looking patterns are literal.

## 9. System Keyword Rules

Static Unicode whole-token matching: AKARYAKIT/PETROL → FUEL; CAFE/COFFEE/KAHVE → CAFE; MARKET → GROCERIES. Embedded words such as MARKETING do not match. Signals for multiple categories fall back to unresolved. No database-controlled regex.

## 10. Classification Precedence

After transaction-type eligibility guards: USER > MERCHANT_RULE > SYSTEM_RULE > fallback. Merchant and category preferences resolve independently; lower layers may fill an absent field but never overwrite a supplied higher-precedence field. A normalization-only alias falls through to keywords, not a less-specific alias category.

## 11. CategorySource Semantics

USER: direct user category choice or stored user rule. MERCHANT_RULE: global alias category. SYSTEM_RULE: keyword or semantic-type category. UNKNOWN: unresolved. CLASSIFIER remains reserved and unused. Merchant-only direct correction retains existing category provenance.

## 12. ReviewStatus Semantics

Direct correction: USER_CONFIRMED. Automatic user/alias/system category: AUTO_CONFIRMED. Unresolved automatic category: NEEDS_REVIEW. A user explicitly selecting OTHER remains an intentional user choice, distinct from automatic fallback.

## 13. OTHER / Unresolved Strategy

Automatic fallback consistently assigns OTHER + UNKNOWN + NEEDS_REVIEW. A recognized merchant without a reliable category may retain its normalized name while remaining reviewable. No confident category is inferred from an unmatched description.

## 14. UserMerchantRule Matching Strategy

Rules are scoped by `(user_id, merchant_key)`. The key is `v1:` plus SHA-256 of the UTF-8 normalized context. This represents exact context identity within the existing VARCHAR(255), avoiding truncation and duplicate storage of long raw descriptions. It is neither encryption nor fuzzy identity resolution. Meaningful context changes, including location changes, require another correction. Partial upserts preserve omitted existing rule preferences.

## 15. User Correction API

`PATCH /api/v1/transactions/{transaction_id}/classification` accepts `preferred_merchant_name`, `category_id`, and `persist_as_rule` (default false). At least one non-null correction is required; blank/overlong names, unknown fields, and invalid catalog IDs are rejected. Missing/unowned transaction IDs both return identical 404 responses.

The transaction is owner-scoped and locked; correction and optional conflict-safe PostgreSQL rule upsert commit atomically. Raw fields and financial semantics remain unchanged. Only the selected transaction changes; future imports can apply the rule. Response contains only classification fields and ID. PATCH is enabled in existing CORS settings.

## 16. Category Read API

`GET /api/v1/categories` returns the read-only system catalog, sorted by code: `id`, `code`, `display_name`, `parent_id`. Both new endpoints reuse the extracted development-only `X-Dev-User-ID` context and reject use outside development. No authentication or category CRUD was added.

## 17. Import Confirmation Integration

Confirmation loads catalog/aliases/current-user rules once per batch inside its existing account/batch-locked transaction. Each new canonical transaction receives classification before commit. Parser DTOs and preview staging remain unchanged. Classification failure rolls back rows, batch status, and staging deletion. A test forces failure after an earlier canonical insert has been flushed and verifies full rollback and successful retry.

## 18. Transaction-Type Safety

EXPENSE, REFUND, and CASH_WITHDRAWAL are merchant-rule eligible; their financial types/signs remain intact. No refund linking or spending-impact calculation is performed. INCOME maps to INCOME; TRANSFER/CARD_PAYMENT to TRANSFER; FEE to FINANCIAL_FEES. These type-derived assignments use SYSTEM_RULE/AUTO_CONFIRMED and no fabricated merchant. INTEREST/UNKNOWN remain unresolved.

Non-merchant types bypass all merchant layers, including user rules. Their correction API rejects merchant names, rule persistence, and incompatible spending categories; explicit category corrections may use their semantic category or OTHER.

## 19. User Isolation

Rules are selected only for the current user. Corrections query transaction UUID and owner together. Existing import account/batch ownership remains intact. Cross-user correction and later-import isolation tests pass. The development identity is caller-asserted, not production authentication.

## 20. Synthetic Acceptance Scenario

An invented DEMO STORE import begins as OTHER/NEEDS_REVIEW. Its owner corrects it to Demo Coffee/CAFE with rule persistence. A later matching import receives Demo Coffee/CAFE/USER/AUTO_CONFIRMED. Another user's identical description remains unresolved. A subsequent partial rule update preserves the preferred merchant and does not rewrite previously imported transactions.

## 21. Tests Added

45 additional cases: 34 comparison/classification cases, 10 API/import integration cases, and one catalog migration lifecycle case. Shared existing account/API fixtures moved to conftest. Tests cover Unicode, literal specificity, precedence, partial preferences, uncertainty, semantic guards, ownership, correction persistence, future imports, rollback after flush, catalog contracts, and migration reference/edit preservation. Pure classification is exercised with new outbound socket connections blocked; there are no external-client calls in the implementation. Existing Phase 4 duplicate, idempotency, locking, and rollback regressions remain in the suite.

## 22. Test Results

Final Docker run: **169 passed, 2 warnings**, Python 3.12.14. Ruff check passed; Ruff format check passed (117 files, including Docker build copies). One intermediate failure was a synthetic date-replacement error that correctly triggered exact-file idempotency; the fixture transformation was corrected and the final full suite passed.

Commands executed during implementation/verification:

```sh
docker compose cp backend/tests/. backend:/app/tests
docker compose exec -T backend pytest tests/test_classification_api.py
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
git status --ignored --short
git diff
git diff --check
git diff --cached --stat
git rev-parse HEAD
git branch -vv
git ls-remote origin refs/heads/main
```

Host Ruff formatting/lint fixes were also run. PowerShell `Invoke-WebRequest` verified health. Read-only Python checks verified catalog/connectivity, frozen-package bytes, paths, and sensitive-content patterns. No command staged, committed, or pushed changes.

## 23. Alembic Results

Upgrade/current/check passed: **0003 (head)**, no new upgrade operations. Tests cover empty database → head, repeated base rebuilds in disposable databases, 0002 → 0003, downgrade to 0002, and re-upgrade while retaining synthetic transactions, user rules, custom catalog data, category-label edits, and disabled aliases. Existing canonical columns remain unchanged. Live catalog: 18 system categories, 9 active aliases. No isolated test databases remain.

## 24. Docker / Health Result

Rebuild/start completed; PostgreSQL, backend, and frontend are healthy. `GET http://127.0.0.1:8000/api/v1/health` returned HTTP 200 and `{"status":"ok"}`. Backend connects to `postgres:5432`; SQL connectivity check returned 1. PostgreSQL remains published only at `127.0.0.1:55433 → 5432`. Compose config validation passed.

## 25. Frontend Build Result

`npm run build` passed, including TypeScript `tsc --noEmit` and Vite production build. No frontend source or product UI changes. Build artifacts remain excluded from Git.

## 26. Dependency Changes

None. Requirements, lockfiles, and Python runtime policy are unchanged. Normalization uses Python stdlib; persistence/API code uses the existing stack.

## 27. Files Added/Modified

22 files: 13 added, 9 modified.

Added:

- `PHASE_5_REPORT.md`
- `backend/alembic/versions/0003_system_categories.py`
- `backend/app/api/dependencies.py`
- `backend/app/modules/categories/repository.py`
- `backend/app/modules/categories/routes.py`
- `backend/app/modules/categories/rules.py`
- `backend/app/modules/categories/service.py`
- `backend/app/modules/merchants/normalization.py`
- `backend/app/modules/merchants/repository.py`
- `backend/app/modules/transactions/classification.py`
- `backend/app/modules/transactions/routes.py`
- `backend/tests/test_classification.py`
- `backend/tests/test_classification_api.py`

Modified:

- `README.md`
- `backend/app/api/v1/router.py`
- `backend/app/main.py`
- `backend/app/modules/imports/routes.py`
- `backend/app/modules/imports/service.py`
- `backend/tests/conftest.py`
- `backend/tests/test_domain.py`
- `backend/tests/test_imports.py`
- `backend/tests/test_migrations.py`

## 28. Privacy Verification

The real bank PDF was not used, copied, or imported for Phase 5. Tests use invented existing fixtures and public-brand examples. Changed/new files were reviewed and scanned; no real statements, private transaction history, credentials, keys, databases, temporary uploads, or generated artifacts were introduced. Existing local environment, virtualenv, caches, node_modules, and build output remain ignored and unstaged. Raw PDF/text storage and private-description logging were not added.

All nine frozen architecture files match the original documentation ZIP byte-for-byte and have no Git diff. CONTRIBUTING, canonical models/enums, parser implementation/DTOs, dependency files, and infrastructure configuration remain unchanged.

## 29. Warnings / Unresolved Questions

No blocking failures or architecture contradictions found. Two pre-existing test-library deprecations remain: Starlette's httpx TestClient integration and AnyIO's BlockingPortal alias. Docker pip also emits its standard root-install warning and update notice; dependencies were not upgraded.

Intentional limits: small alias catalog; literal aliases may need user correction; exact context rules do not generalize across changed text; Turkic I pairs remain distinct; unknown/conflicting descriptions require review; no rule-management or historical bulk-reclassification endpoint. Seed downgrade retains data intentionally. Authentication remains deferred as requested.

## 30. Confirmation No Phase 6+ Features Were Implemented

Confirmed: no analytics, aggregations, forecasts, product UI, LLM/ML, embeddings, authentication, or additional infrastructure. Phase 6 has not started.

## 31. Confirmation No Commit/Push Was Performed

Confirmed: no staging, commit, push, amend, rebase, branch change, or history rewrite. Main still tracks origin/main at the frozen Phase 4 hash. All 22 Phase 5 files remain unstaged/uncommitted for review; the index is empty and `git diff --check` is clean.
