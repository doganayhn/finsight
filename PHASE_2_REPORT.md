# FinSight Phase 2 — Financial Domain & Database

Date: 2026-09-04

Repository: `C:\Users\doğan\Documents\ChatGPT\finsight`

## 1. Phase 2 Status

**Implemented and verified; awaiting explicit review. Not frozen or committed.** The existing synchronous SQLAlchemy/Psycopg infrastructure now supports the canonical financial schema. All required checks pass on the canonical Docker Python 3.12.14 runtime with PostgreSQL 17.11.

No blocking contradiction with the frozen engineering documents was found. All nine frozen files, including root `AGENTS.md`, match the original documentation ZIP byte-for-byte. `CONTRIBUTING.md` is unchanged.

## 2. Domain Entities Added

| Entity | Model module under `backend/app/modules/` | Purpose |
| --- | --- | --- |
| User | `auth/models.py` | Ownership identity only |
| Account | `accounts/models.py` | Generic financial account/card |
| Category | `categories/models.py` | Shared category catalog |
| ImportBatch | `imports/models.py` | Import-attempt provenance |
| Transaction | `transactions/models.py` | Canonical dated financial movement |
| TransactionLink | `transactions/models.py` | Pairwise financial relationship |
| MerchantAlias | `merchants/models.py` | Global normalization metadata |
| UserMerchantRule | `merchants/models.py` | Persistent user-specific correction metadata |

Added module package files, account/import/transaction enums, shared `db/mixins.py`, `db/types.py`, and `db/models.py`, the initial migration, and three database test/support files. Updated `db/base.py`, `db/session.py`, Alembic `env.py`, test `conftest.py`, pytest configuration in `pyproject.toml`, and README. No dependency declarations or lockfiles changed.

## 3. Tables Created

`users`, `accounts`, `categories`, `import_batches`, `transactions`, `transaction_links`, `merchant_aliases`, and `user_merchant_rules`.

The existing `alembic_version` table records revision `0001`. No category seeds or application financial data were inserted.

## 4. Important Columns

Every entity has a UUID primary key and timezone-aware `created_at`. All except links also have `updated_at`. UUIDs support Python `uuid4()` and database `gen_random_uuid()` defaults. PostgreSQL timestamps use `TIMESTAMPTZ`; application connections and returned system timestamps use UTC. SQLAlchemy updates refresh `updated_at`; direct SQL writers must set it explicitly.

| Table | Key fields and choices |
| --- | --- |
| users | Required unique email, stripped and lowercased by the ORM; database canonical-format check |
| accounts | Owner, generic institution code, display name, account type, explicit currency, optional masked last four, active flag |
| categories | Unique language-independent code, display name, optional parent, `is_system` provenance flag |
| import_batches | Owner/account, separate source and file format, generic institution/statement type, filename/hash, parser name/version, statement dates, currency/totals, four row counters, validation/import status |
| transactions | Owner/account/import, transaction and posting dates, raw description, optional raw/normalized merchant, signed amount/currency, semantic type, category, balance after row, installment fields, category/review provenance, source reference/row |
| transaction_links | Owner, two transaction IDs, link type, optional confidence, confirmation flag, optional allocation amount and currency |
| merchant_aliases | Unique pattern, normalized merchant, optional default category, active flag |
| user_merchant_rules | Owner, merchant key, preferred name, optional category |

Financial dates remain `DATE`. All monetary columns use Python `Decimal` and PostgreSQL `NUMERIC(18,2)`. The shared money type rejects floats, strings, non-finite values, overflow, and values requiring rounding. Database checks also reject non-finite money. Direct SQL still has PostgreSQL's normal numeric coercion behavior; future application writers should use the typed persistence boundary.

Currencies use three uppercase letters without a bank/currency whitelist or FX logic. Import totals require currency when present. Transaction currency is preserved independently of the account's default currency. `balance_after` describes the dated transaction's historical balance, not current funds or available credit. Merchant, category, import reference, and uncertain metadata remain nullable where appropriate.

## 5. Enums Added

| Enum | Values |
| --- | --- |
| AccountType | CHECKING, SAVINGS, CREDIT_CARD, DEBIT_CARD, CASH, OTHER |
| TransactionType | EXPENSE, INCOME, TRANSFER, REFUND, FEE, INTEREST, CARD_PAYMENT, CASH_WITHDRAWAL, UNKNOWN |
| SourceType | MANUAL_UPLOAD, GMAIL |
| FileFormat | PDF, CSV, XLSX |
| ImportStatus | PENDING, PARSED, AWAITING_CONFIRMATION, COMPLETED, FAILED |
| ValidationStatus | PASSED, FAILED, NOT_AVAILABLE, NEEDS_REVIEW |
| CategorySource | USER, MERCHANT_RULE, SYSTEM_RULE, CLASSIFIER, UNKNOWN |
| ReviewStatus | AUTO_CONFIRMED, NEEDS_REVIEW, USER_CONFIRMED |
| LinkType | TRANSFER_PAIR, CARD_PAYMENT_PAIR, REFUND_OF |

Enums persist as VARCHAR with named CHECK constraints, avoiding native PostgreSQL enum lifecycle complexity. Model CHECKs are explicit so Alembic tracks them. Future enum changes require reviewed migrations. Source/format values prepare representation only; they do not implement ingestion.

## 6. Constraints Added

Inspection confirmed **8 primary keys, 14 foreign keys, 8 unique constraints, and 37 CHECK constraints** across the domain tables.

- Composite foreign keys enforce account ownership, import/account/owner consistency, and same-user linked transactions.
- Currency format, finite money, positive installment values, installment index at most count, and positive source row numbers.
- Nonnegative import counters, ordered statement dates, optional 64-character lowercase SHA-256 hex, and explicit currency for totals.
- No self-links; canonical order for symmetric links; unique source/target/type; confidence from zero to one; positive optional allocation with currency paired to amount.
- Unique canonical email, category code, global alias pattern, and per-user merchant key. Category cannot be its own parent.
- Masked identifiers accept only `****1234` format. No full account/card identifier field exists.

No hard transaction uniqueness based on date/amount/description, source row, or source reference. File hashes are nonunique so attempts and failures remain representable. Counter sums and transaction-type sign restrictions are not assumed.

## 7. Indexes Added

**14 deliberate secondary indexes**, beyond the indexes backing primary/unique constraints:

| Table | Indexed columns |
| --- | --- |
| transactions | `(user_id, transaction_date)`, `(account_id, transaction_date)`, `(user_id, merchant_normalized)`, `(account_id, source_transaction_id)`, `category_id`, `import_batch_id` |
| import_batches | `(user_id, account_id, file_hash)`, `account_id` |
| accounts | `user_id` |
| categories | `parent_id` |
| merchant_aliases | `default_category_id` |
| user_merchant_rules | `category_id` |
| transaction_links | `user_id`, `target_transaction_id` |

Composite leading columns serve owner/account queries without redundant standalone indexes. The unique link index also serves source-transaction lookups; the unique user/key index serves user-rule lookups. No speculative global date, merchant, or file-hash indexes were added.

## 8. Relationship / Delete Strategy

- Deleting a user cascades through owned accounts, import batches, transactions, links, and merchant rules. Shared categories and aliases survive.
- Deleting an account removes its imports, transactions, and incident links, while user-level rules remain. Normal account retirement can use `is_active` instead of deletion.
- Deleting a transaction removes its incident links.
- A referenced import batch cannot be deleted independently (`NO ACTION`), preserving transaction provenance. Deleting its account/user can remove the complete dependent graph; both paths were tested.
- Referenced categories and category parents use `RESTRICT`, preserving references until deliberately reassigned/removed.

ORM navigation is available for accounts/users, categories, imports, and link endpoints. Import and link endpoint navigation is read-only to avoid conflicting writes to shared ownership columns. These database constraints prepare integrity; they do not replace future authorization.

## 9. Transaction Link Semantics

`REFUND_OF` points **from refund to original purchase**. Multiple distinct refunds can reference a purchase. `TRANSFER_PAIR` and `CARD_PAYMENT_PAIR` store the lower UUID as source and higher UUID as target; callers must supply this canonical order. A CHECK rejects reverse-order storage and a unique constraint prevents duplicate equivalent links.

Optional `linked_amount` is a positive allocation magnitude with explicit currency, supporting partial refunds. No automatic pairing, per-purchase card-payment fan-out, aggregate allocation validation, or cross-row semantic classification is implemented.

## 10. Installment Modeling Decision

Nullable SMALLINT index/count and a UUID grouping identifier are sufficient. There is no installment-plan table or `INSTALLMENT_GROUP` link type. A six-installment 30,000 TRY example persists the monthly transaction as **-5,000.00 TRY**, verified by test. Original purchase reconstruction is outside this phase.

## 11. Institution Code Modeling Decision

Institution codes are nullable `VARCHAR(100)`, not a closed enum. Accounts and import metadata can represent any provider, including a future one, without adding bank-specific columns or conditionals. Cash accounts need not have an institution.

## 12. Source Data / JSONB Decision

**Omitted.** Explicit import/source/parser fields provide the required provenance without an unrestricted statement-content container. No PDFs, addresses, customer identifiers, full card/account numbers, or real financial fixtures were added. Future parser work can propose narrowly selected provenance with an explicit privacy boundary.

## 13. Redundant user_id Ownership Decision

Accounts, imports, transactions, links, and user merchant rules carry direct ownership. Import/transaction/link ownership is protected by composite foreign keys rather than trusted as an unchecked duplicate. Supporting composite unique constraints make those references valid. This supports scoped queries and future security work without implementing RLS or authentication. Categories and merchant aliases remain shared catalog data.

## 14. Migration Created

`backend/alembic/versions/0001_financial_domain.py` — revision `0001`, parent `None`.

Creates all eight domain tables and their constraints/indexes; downgrade removes them in dependency order. The revision uses SQLAlchemy primitives and literal enum values, with no imports from live application models. Alembic registers the complete model metadata and accepts an explicitly supplied connection for isolated migration tests. Alembic is the authoritative schema mechanism; tests do not use `create_all`.

## 15. Commands Executed

Main implementation and verification commands, from the repository root:

```sh
docker compose exec -T backend alembic current
docker compose exec -T backend alembic revision --autogenerate --rev-id 0001 -m "financial domain"
docker compose up --build -d --wait
docker compose exec -T backend pytest
docker compose exec -T backend python -m pytest
docker compose exec -T backend ruff check .
docker compose exec -T backend ruff format --check .
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T frontend npm run build
docker compose config --quiet
docker compose ps
docker compose port postgres 5432
git status --short
git diff
git diff --cached --stat
git diff --check
git rev-parse HEAD
```

Local Ruff fix/format/check commands used `backend/.venv/Scripts/python -m ruff`. Inline Python inspections verified SQLAlchemy mappings, live PostgreSQL tables/constraints/indexes, host and container connections, UTC, and test-database cleanup. Python SHA-256 comparisons verified all frozen documents against the original ZIP. PowerShell HTTP requests checked health and OpenAPI routes. Read-only Git comparisons checked the frozen documents, workflow, frontend, Compose, Dockerfile, dependency lockfile, and environment example.

## 16. Test Results

**44 passed, 2 existing dependency warnings**, in the rebuilt container on Python 3.12.14: 39 domain cases, 3 health tests, and 2 migration/schema tests. Ruff check and format check pass.

Coverage includes signed exact money, multiple preserved currencies, nullable category/merchant, UUIDs, UTC/naive timestamps, installments, import provenance/defaults/constraints, duplicate candidates, enum validation, ownership rejection, partial refunds, symmetric link order, self-link prevention, user overrides, deletion integrity, schema shape, and migration round trips.

Initial migration drift tests exposed type-generated enum CHECKs that Alembic considered removed. Explicit model CHECKs resolved this. Pytest now explicitly includes the working source path, avoiding a stale installed package when Docker bind mounts change. Both plain `pytest` and `python -m pytest` were verified after the fix.

## 17. Alembic Results

- Existing Phase 1 database upgraded successfully from the empty baseline.
- `current`: **0001 (head)**.
- `check`: **No new upgrade operations detected.**
- Isolated lifecycle test verified empty → head, then two head → base → head round trips, with schema/drift checks and database-generated UUID/timestamp checks.
- Live inspection confirmed eight domain tables and the constraint/index counts above.
- Downgrades ran only in newly generated test databases. All test databases were removed; the development database remains at head.

## 18. Docker/Health Result

Rebuild/start and Compose validation passed. Backend, frontend, and PostgreSQL containers are healthy.

- Backend database destination: **postgres:5432**, verified through settings and a live SQL query.
- Windows host database destination: **127.0.0.1:55433**, verified through the host client and Compose publication.
- PostgreSQL server port: **5432**; application connection timezone: **UTC**.
- Health: **HTTP 200**, `{"status":"ok"}`.
- OpenAPI still exposes only `/api/v1/health`; no financial CRUD endpoints were introduced.
- All service publications remain on localhost.

## 19. Frontend Build Result

`npm run build` passed in the frontend container, including `tsc --noEmit` and Vite 8.2.2 production bundling. All 19 modules built successfully. Frontend source and configuration are unchanged.

## 20. Warnings / Unresolved Questions

No blocking implementation issue or architecture question remains for Phase 2 review.

- Two existing upstream deprecations remain: Starlette TestClient's `httpx` integration and AnyIO's `BlockingPortal` alias. Dependencies were not upgraded to suppress them.
- The Docker image build emitted the existing root-pip warning and a pip update notice. They did not affect the build.
- Python 3.12 remains the canonical supported runtime (`>=3.12,<3.13`); the incidental host Python installation was not used as the acceptance runtime.
- Database tests require PostgreSQL and `CREATEDB` privileges and intentionally fail when unavailable.
- Email normalization treats the entire email as case-insensitive. It is an ownership identifier policy, not complete authentication/email validation.
- Future write services must enforce authorization, link type/currency/allocation consistency, deeper category cycle prevention, and rule precedence. The current phase supplies persistence constraints, not those workflows. Direct SQL updates must maintain `updated_at`.

## 21. Confirmation That No Future-Phase Features Were Implemented

Confirmed: no parser or PDF inspection, upload/import workflow, hashing/deduplication algorithm, categorization execution, analytics, forecast, financial UI, authentication, RLS, AI, Groq, assistant, or other Phase 3+ functionality. Only requested schema preparation and persistence verification were added. Frozen architecture documents were not modified.

## 22. Confirmation That No Commit or Push Was Performed

No staging, commit, push, branch change, or history rewrite was performed. Changes remain uncommitted on `main` for review. HEAD remains the Phase 1 baseline:

`64da32603a2d1a14c7558f65d05bbd7743e778c7`

Phase 2 awaits explicit review and a separate freeze/commit instruction. Phase 3 has not started.
