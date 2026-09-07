# FinSight Phase 6 Report

## 1. Phase 6 Status

Implemented and verified; ready for review, not frozen or committed. Repository: `C:\Users\doğan\Documents\ChatGPT\finsight`. Local main, origin/main, and GitHub remain at frozen Phase 5 commit `db5bd5f7749d0562d8117f95b8f37eb356f4311e`. All Phase 6 changes are unstaged.

## 2. Analytics Architecture

New provider-neutral analytics module: validated query/result schemas, centralized SQL spending policy, owner-scoped repository, reusable service, and thin API routes. PostgreSQL performs ordinary aggregation; the service constructs results, fills zero months, and performs Decimal comparisons/projections. No parser, bank, LLM, or frontend dependency.

## 3. Central Spending Semantics

`analytics/policy.py` is shared by all aggregates. EXPENSE contributes purchase magnitudes; REFUND contributes positive refund amounts. TRANSFER, CARD_PAYMENT, INCOME, INTEREST, and UNKNOWN contribute no consumer spending. Merchant/category labels never override transaction type. NEEDS_REVIEW expenses still count. No classification fields or financial records are modified.

## 4. Gross / Refund / Net Semantics

Gross = sum of EXPENSE magnitudes. Refunds = sum of positive REFUND amounts. Net = gross − refunds, which can be negative. The queried date/account/currency scope determines refund applicability; no transaction-link inference or historical purchase lookup. Category refunds reduce their existing category; unassigned/OTHER refunds remain in OTHER.

## 5. Cash Withdrawal Semantics

Negative CASH_WITHDRAWAL amounts contribute their outflow magnitudes to `cash_withdrawals`, never consumer spending. A spending-like category does not change this treatment.

## 6. Fee Semantics

Negative FEE amounts contribute their outflow magnitudes to `financial_fees`, separately from purchases. Fee categories/merchants do not make them consumer expenses. Positive fee/cash movements are not counted as outflows.

## 7. Period / Calendar Semantics

Explicit `start_date <= transaction_date <= end_date`; no server-local month or statement-period default. Ranges are ordered, limited to 3,661 inclusive days, and dates to 1900–2100. Partial months include only requested dates. A test uses a deliberately unrelated statement-period label to verify calendar-date behavior. Installment 2/6 contributes its canonical 5,000 row amount, not 30,000.

## 8. Multi-Currency Strategy

Every aggregate is grouped by canonical transaction currency; results use sorted `currencies` lists. Optional `currency` selects one uppercase three-letter code. No FX or mixed-currency total. No matching rows without a currency filter yields an empty list; an explicit currency yields zero summary/projection/trend values or an empty breakdown group. Comparison zero-fills missing sides across the currency union.

## 9. Analytics Service Methods

`get_spending_summary`, `get_category_breakdown`, `get_merchant_breakdown`, `get_monthly_trend`, `compare_periods`, `project_month_spending`, and `list_transactions`. They accept validated typed query DTOs and return typed results, independently of HTTP. The service receives an explicit user UUID and database session.

## 10. API Endpoints

All use the existing development-only `X-Dev-User-ID` context:

| GET endpoint | Required inputs |
| --- | --- |
| `/api/v1/analytics/summary` | start_date, end_date |
| `/api/v1/analytics/categories` | start_date, end_date |
| `/api/v1/analytics/merchants` | start_date, end_date |
| `/api/v1/analytics/trend` | start_date, end_date |
| `/api/v1/analytics/compare` | current_start, current_end, previous_start, previous_end |
| `/api/v1/analytics/projection` | year, month, as_of_date |
| `/api/v1/transactions` | start_date, end_date |

All support optional account/currency filtering. Merchant results and transaction pages have bounded limits. Invalid requests return safe 422 errors without input echoes; unavailable accounts return safe 404 errors. Authentication was not added.

## 11. Summary Response

Period and filter metadata, `data_scope=CANONICAL_TRANSACTIONS`, and per-currency gross, refunds, net, financial fees, cash withdrawals, expense count, and refund count. The scope describes observed canonical records, not complete account activity, current balance, income coverage, or net worth.

## 12. Category Breakdown

Per currency/category: ID, code, name, gross/refunds/net, and EXPENSE-plus-REFUND row count. Sort: net descending, category code ascending. Canonical null categories are presented with seeded OTHER without mutating storage. NEEDS_REVIEW rows and negative-net refund buckets remain visible. OTHER explorer filtering includes null categories so supporting rows remain discoverable.

## 13. Merchant Breakdown

Use nonblank normalized merchant, otherwise trimmed raw merchant up to 120 characters, otherwise null/UNKNOWN. Never substitute a large raw description. Group by exact merchant value and identity source (NORMALIZED/RAW/UNKNOWN); no fuzzy relationship inference. Refunds follow their own identity; unknown refunds remain unattributed. Sort: net descending, merchant ascending in PostgreSQL C collation with null last, then identity source. SQL enforces 1–100 results per currency, default 10. Top-N results need not sum to summary totals.

## 14. Monthly Trend

One bucket per intersecting calendar month and discovered/requested currency, including zero months. Date filtering remains inclusive before monthly SQL grouping. First/last partial months are not expanded beyond the requested range. No currency is inferred from account configuration.

## 15. Period Comparison

Explicit current and previous ranges. Both periods aggregate in one SQL statement for a consistent PostgreSQL snapshot. Each currency includes current/previous net, absolute change, direction, percentage, and percentage state. Unequal/overlapping ranges are allowed and compared as supplied; no hidden length normalization.

## 16. Percentage Zero-Division Policy

Positive previous net: `(current − previous) / previous × 100`, rounded to two decimals. Both zero: `0.00/BOTH_ZERO`. Zero previous and nonzero current: `null/PREVIOUS_ZERO`. Negative previous: `null/PREVIOUS_NEGATIVE` to avoid misleading growth percentages. Direction always reflects absolute change. No Infinity or NaN output.

## 17. Transaction Explorer

Filters: inclusive dates, owned account, currency, category, transaction type, review status, and merchant substring. Search uses escaped/bound case-insensitive PostgreSQL matching against normalized merchant, raw merchant, and description; `%`/`_` are literal characters. No fuzzy/full-text infrastructure.

Pagination: limit 1–100 (default 50), offset 0–100000, has_more, at most limit+1 fetched rows. Order: transaction_date DESC, created_at DESC, UUID DESC. Returns canonical IDs/date/description/merchant/amount/type/category/provenance/review/installment fields, excluding source/parser metadata and balance. Category is eager-loaded. Offset pages can shift under concurrent inserts.

## 18. Projection Formula

Observed net uses month start through as_of_date. Basis = max(observed net, 0). Daily rate = basis / inclusive elapsed calendar days. Projection = unrounded daily rate × actual month length. Method: LINEAR_DAILY_RUN_RATE. Output includes observed net, basis, daily display, projection, day counts, and explicit assumptions.

## 19. Projection Edge Cases

as_of_date must belong to the requested month. No later-dated rows, income, balance, fees, or salary enter the spending basis. Leap-year February uses 29 days. Zero spending produces zero projection; negative observed net remains visible while basis/projection are zero. Daily display is rounded independently and never reused in projection arithmetic. This is spending pace, not remaining-money forecasting.

## 20. Account/User Isolation

Every transaction SQL query includes user ownership. Optional account IDs are verified for ownership before querying; missing and another user's account return identical `account_not_found` responses. All seven endpoints have cross-user tests. Category catalog data is shared, while category-filtered financial rows remain owner-scoped. Development identity remains caller-asserted, not production authentication.

## 21. Decimal Serialization

SQL uses NUMERIC; Python results and formulas use Decimal. Money and percentage output are two-decimal strings. Formula calculations use a local precision of 50 and ROUND_HALF_UP for final display. Aggregate expressions cast away the per-row NUMERIC(18,2) bound; a test verifies `19999999999999999.98` without float or overflow.

## 22. SQL Aggregation Strategy

Conditional SUM/COUNT in PostgreSQL; GROUP BY currency/category/month/merchant as appropriate. Merchant top-N uses row_number partitioned by currency. Comparison uses UNION ALL within one statement. No full-history loading/summing in Python. Instrumentation confirms one financial query for summary, category, merchant, comparison, and explorer; account-filtered requests add one ownership query. No per-category or per-row category queries.

Canonical existence is the financial inclusion boundary; analytics do not query staging or join import metadata. Phase 4's atomic persistence makes canonical inserts visible with COMPLETED status. Tests prove preview candidates and skipped duplicates never enter totals.

## 23. Index / Migration Decision

Existing indexes include transactions(user_id, transaction_date), (account_id, transaction_date), and (user_id, merchant_normalized). Bounded owner/date predicates use these existing access paths. No speculative index, schema, view, summary table, cache, or migration added. No canonical model/enum changes.

## 24. Synthetic Acceptance Scenario

Invented core account: expenses 1,000 + 200 + 500 TRY; refund 100; fee 25; cash withdrawal 1,000; transfer 5,000; card payment 3,000; income 10,000, plus excluded unknown/interest rows. Verified gross **1,700**, refunds **100**, net **1,600**, fees **25**, withdrawals **1,000**. Additional fixtures cover another owned TRY account, USD, another user's EUR rows, OTHER/null categories, a 5,000 installment, prior/future months, and zero months. No private financial source was used.

## 25. Tests Added

43 meaningful analytics cases in `backend/tests/test_analytics.py`. Coverage includes the financial scenario, type exclusions, refunds/category attribution, review-needed rows, installments, inclusive calendar dates, currencies/accounts, all endpoint ownership gates, sorting/pagination, escaped search, zero months, comparison directions/edge cases, projection/leap year, large exact amounts, validation, direct service use, bounded query counts, and no new external socket connections during service calls. Synthetic import/correction integration confirms preview exclusion, skipped duplicates, and updated canonical category results. Existing Phase 4/5 tests remain unchanged.

## 26. Test Results

Final Docker pytest: **212 passed, 2 warnings**, Python 3.12.14. Focused analytics suite: **43 passed**. Ruff check passed; Ruff format check passed (130 files including Docker build copies). Full suite includes all Phase 4/5 regressions and existing migration lifecycle tests.

Commands executed:

```sh
docker compose cp backend/tests/. backend:/app/tests
docker compose exec -T backend pytest tests/test_analytics.py
docker compose up --build -d --wait
docker compose exec -T backend pytest
docker compose exec -T backend ruff check .
docker compose exec -T backend ruff format --check .
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T frontend npm run build
docker compose config --quiet
docker compose ps
git status --short
git diff
git diff --check
git diff --cached --stat
git branch -vv
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Host Ruff format/check fixes, a PowerShell HTTP health request, and read-only Python checks of database connectivity, frozen documentation bytes, candidate paths/content, and line endings also ran. No checks failed in the final verification.

## 27. Alembic Results

`0003 (head)`; `alembic check` reports no new upgrade operations. Existing empty-database upgrade/downgrade/re-upgrade tests pass. No isolated test databases remain after the suite.

## 28. Docker / Health Result

Rebuilt and started successfully. Backend, PostgreSQL, and frontend healthy. GET `/api/v1/health`: HTTP 200, `{"status":"ok"}`. PostgreSQL SELECT 1 succeeded. Existing localhost publications and backend `postgres:5432` configuration unchanged. Compose config validation passed.

## 29. Frontend Build Result

Production build passed, including TypeScript `tsc --noEmit` and Vite. Frontend source and configuration remain unchanged; generated output remains ignored. No Phase 7 UI work.

## 30. Dependency Changes

None. Python 3.12 policy and all dependency/lock files remain unchanged. Only existing stdlib, Pydantic, SQLAlchemy, PostgreSQL, and FastAPI functionality is used.

## 31. Files Added/Modified

12 files: 8 added, 4 modified.

Added: `PHASE_6_REPORT.md`; `backend/app/modules/analytics/__init__.py`, `schemas.py`, `policy.py`, `repository.py`, `service.py`, `routes.py`; `backend/tests/test_analytics.py`.

Modified: `README.md`; `backend/app/api/v1/router.py`; `backend/app/main.py`; `backend/app/modules/transactions/routes.py`.

## 32. Privacy Verification

No real PDF, private statement text/history, credentials, financial file, or raw upload was used or added. New fixtures are invented. Path/content review and sensitive-pattern scan passed. Existing environment files, virtualenvs, node_modules, caches, and build output remain ignored. No private descriptions or SQL parameters are logged by new code.

All nine frozen architecture files match the original ZIP byte-for-byte. AGENTS, CONTRIBUTING, frozen docs, earlier reports, frontend, migrations, domain models/enums, parser/classification implementations, dependency files, and infrastructure configuration remain unchanged.

## 33. Warnings / Unresolved Questions

No blocking issue or frozen-architecture contradiction found. Two existing test deprecations remain: Starlette/httpx TestClient and AnyIO BlockingPortal. Docker pip emits its existing root-install warning and update notice; no dependency upgrade was performed.

Intentional limits: incomplete source coverage; explicit bounded date ranges; exact conservative merchant identities; offset-page drift under concurrent writes; unassigned refunds stay unresolved; top-N merchant totals are partial; projection assumes constant daily pace. Analytics consume current canonical semantics rather than repairing signs/types or inferring relationships. No balance/net-worth/income-coverage claims.

## 34. Confirmation No Phase 7+ Features Were Implemented

Confirmed: no dashboard/charts/product UI, assistant/Groq/LLM, embeddings, Text-to-SQL, RAG, authentication, cache, background processing, or new infrastructure. Phase 7 has not started.

## 35. Confirmation No Commit/Push Was Performed

Confirmed: no staging, commit, push, amend, rebase, branch change, or history rewrite. HEAD remains `db5bd5f7749d0562d8117f95b8f37eb356f4311e`; all 12 Phase 6 files remain unstaged/uncommitted for review. Index is empty and whitespace checks pass.
