# FinSight

FinSight is a bank-agnostic personal spending intelligence platform. **Current status: Phase 7 — responsive web product UI, awaiting review.** The Turkish interface supports statement import, deterministic spending analytics, transaction exploration, and merchant/category corrections. Financial calculations remain in the backend.

## Architecture and stack

- API-first modular monolith: Python, FastAPI, Pydantic Settings, SQLAlchemy 2.x, Psycopg 3, Alembic.
- PostgreSQL stores the canonical financial schema: users, accounts, categories, import batches, transactions, transaction links, merchant aliases, and user merchant rules.
- React, TypeScript, Vite, and Tailwind CSS form the presentation client.
- Docker Compose runs PostgreSQL, backend, and frontend locally.
- pytest and Ruff provide backend checks; TypeScript and Vite verify the frontend.

The frozen engineering contract is in [AGENTS.md](AGENTS.md) and [docs/](docs/). Authentication and AI are not implemented yet. See [PHASE_2_REPORT.md](PHASE_2_REPORT.md) for canonical schema decisions, [PHASE_3_REPORT.md](PHASE_3_REPORT.md) for parser verification, [PHASE_4_REPORT.md](PHASE_4_REPORT.md) for import acceptance, [PHASE_5_REPORT.md](PHASE_5_REPORT.md) for classification verification, and [PHASE_6_REPORT.md](PHASE_6_REPORT.md) for analytics verification.

Phases 0–6 are frozen. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for the Git workflow: one final commit per reviewed, explicitly frozen phase; no intermediate commits or force-pushes.

## Prerequisites

- Docker Desktop with the Linux engine running and Docker Compose.
- For running outside containers: Python 3.12 and Node.js 22.12+ (Node 24 is used in Docker).
- Ports 5173, 8000, and 55433 available locally, or adjusted in `.env`.

**V1 Python policy:** Python 3.12 is the canonical, recommended, and supported backend runtime. Docker remains on `python:3.12-slim`; `backend/.python-version` selects 3.12 for compatible tools, and `requires-python = ">=3.12,<3.13"` limits package installation to that minor version. A developer's Python 3.14 installation is not the reproducibility target. Use a 3.12 virtual environment or Docker for V1 checks; dependency versions are unchanged.

## Local setup

From the repository root, copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux, use `cp .env.example .env`. Set `POSTGRES_PASSWORD` to your own local development password. `.env` is ignored by Git. Only `VITE_*` variables are exposed to browser code; never put secrets in those variables.

```sh
docker compose up --build
```

Compose waits for PostgreSQL's healthcheck, runs `alembic upgrade head`, then starts the API. The frontend starts after the API is healthy. PostgreSQL data persists in the named `postgres_data` volume. All published ports bind to `127.0.0.1`.

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000> (routes are under `/api/v1`; no root page)
- Health: <http://localhost:8000/api/v1/health> → `{"status":"ok"}`
- API documentation: <http://localhost:8000/api/v1/docs>

The frontend calls the health endpoint from the browser and displays Checking, Online, or Offline. Use **Check connection** to retry. Health is application liveness, not a database readiness check.

PostgreSQL publication and client connection settings have separate roles:

| Setting | Meaning |
| --- | --- |
| `POSTGRES_HOST_PORT=55433` | Compose publishes `127.0.0.1:55433` to container port `5432`. |
| Root `.env`: `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=55433` | Host-run Python/Alembic client destination. Match `POSTGRES_PORT` to `POSTGRES_HOST_PORT`. |
| Backend container: `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432` | Fixed Docker-network client destination, independent of the published host port. |

`POSTGRES_PORT` is only a client destination port; it does not control Docker port publication or PostgreSQL's server listening port. If you change `POSTGRES_HOST_PORT`, also update the host client `POSTGRES_PORT` in `.env`. The backend container always connects to `postgres:5432`. PostgreSQL remains published only on localhost, leaving an existing host database on 5432 untouched.

If you change frontend/backend published ports, also update `VITE_API_BASE_URL` and the JSON list `CORS_ORIGINS`. Database configuration is shared by SQLAlchemy and Alembic; credentials are not duplicated in `alembic.ini`. Database connections use a five-second connection timeout.

Stop with Ctrl+C, or `docker compose down`. Do not add `-v` unless you intend to delete the database volume. Changing database credentials after initial volume creation requires updating the existing database credentials separately.

## Checks in Docker

With services running:

```sh
docker compose exec backend pytest
docker compose exec backend ruff check .
docker compose exec backend ruff format --check .
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend alembic check
docker compose exec frontend npm run build
docker compose ps
docker compose config --quiet
```

After changing dependencies, Dockerfiles, tests, or configuration files, rebuild. Backend application/Alembic files and frontend source files are bind-mounted for development.

Database tests require running PostgreSQL and a local development database role with `CREATEDB` (the Compose development role has it). They create randomly named `finsight_test_<uuid>` databases, apply real Alembic migrations, and drop only those databases afterward. Tests fail if PostgreSQL is unavailable; they do not substitute SQLite or skip database checks. Migration round trips run exclusively in these disposable databases. Do not run the suite with production credentials. To run only the independent liveness tests, use `pytest tests/test_health.py`.

## Parser-only checks and local private inputs

After rebuilding the backend, run the independent parser/extractor tests:

```sh
docker compose exec -T backend pytest tests/test_tlcard_parser.py tests/test_pdf_text.py
```

These tests use independently invented statement text and synthetic PDF bytes constructed in memory with pypdf. No real statement, extracted private text, or PDF fixture is stored in the repository. No OCR or database connection is required for the parser-only suite. The full suite still runs PostgreSQL integration tests.

For a local Python 3.12 environment, the parser can be invoked from `backend` using a private PDF path supplied through `FINSIGHT_PRIVATE_PDF`. Keep the file outside the repository:

```python
import os
from pathlib import Path

from app.modules.imports.parsers.pdf_text import extract_pdf_text
from app.modules.imports.parsers.yapikredi_tlcard import YapiKrediTLCardPDFParser

document = extract_pdf_text(Path(os.environ["FINSIGHT_PRIVATE_PDF"]).read_bytes())
parser = YapiKrediTLCardPDFParser()
statement = parser.parse(document)
validation = parser.validate(statement)
validation.require_passed()
print(validation.status.value, len(statement.transactions))
```

Parsing does not persist anything. Always call `validate` and require a passing result before treating candidates as reconciled. The bank's positive purchase total is compared with the magnitude of qualifying `EXPENSE` rows; canonical purchases remain negative. Cash withdrawals are excluded from purchase reconciliation, and unknown operations fail validation. The statement's month/year label does not assert exact billing boundaries or a complete account ledger. Never log document text, transaction lists, or identity fields.

## Phase 4 manual imports

These endpoints use **caller-supplied development context, not authentication**. Pass `X-Dev-User-ID` with a synthetic local user's UUID. Every operation checks account/batch ownership on the backend; the header itself does not prove identity. Import endpoints are disabled when `APP_ENV` is not `development`. Keep this pre-auth stack local; do not expose it as a multi-user service.

| Endpoint | Behavior |
| --- | --- |
| `POST /api/v1/imports/preview` | Multipart `file` and `account_id`; returns 201 with stored preview candidates |
| `GET /api/v1/imports/{import_batch_id}` | Returns owned preview/status and current possible duplicate matches |
| `POST /api/v1/imports/{import_batch_id}/confirm` | JSON decisions; atomically imports accepted candidates and returns 200 |

User/account creation is intentionally outside this API. Tests create synthetic users and accounts directly in isolated PostgreSQL databases. To exercise the complete workflow without real banking data:

```sh
docker compose exec -T backend pytest tests/test_imports.py
```

For manual API use, substitute your own synthetic local IDs and synthetic PDF path in these examples. The example UUIDs are placeholders and are not automatically seeded:

```sh
curl -X POST http://localhost:8000/api/v1/imports/preview \
  -H "X-Dev-User-ID: 11111111-1111-4111-8111-111111111111" \
  -F "account_id=22222222-2222-4222-8222-222222222222" \
  -F "file=@synthetic.pdf;type=application/pdf"
curl http://localhost:8000/api/v1/imports/BATCH_UUID \
  -H "X-Dev-User-ID: 11111111-1111-4111-8111-111111111111"
curl -X POST http://localhost:8000/api/v1/imports/BATCH_UUID/confirm \
  -H "X-Dev-User-ID: 11111111-1111-4111-8111-111111111111" \
  -H "Content-Type: application/json" -d '{"decisions": {}}'
```

On Windows use `curl.exe` and shell-appropriate continuation/JSON quoting, or Swagger at `/api/v1/docs`.

`MAX_UPLOAD_BYTES` defaults to **10485760 (10 MiB)**, enough for ordinary monthly text-layer statements while bounding uploads. The HTTP body limit allows a further 64 KiB for multipart encoding, checks actual streamed bytes, and works without trusting Content-Length. File content is separately read with a limit-plus-one bound. `MAX_PDF_PAGES` defaults to **50**, checked before page text extraction. PDF MIME, `.pdf` extension, magic, non-empty bytes, and the existing strict text-layer extractor are required. Encrypted/image-only files remain unsupported. Configure both limits through the root environment file; Compose forwards them to the backend.

Raw bytes are hashed with SHA-256, processed in memory, then discarded. Framework-managed upload spools are closed; there is no persistent raw upload folder or database column. The uploaded filename is discarded in favor of the generic `statement.pdf`. Only minimal parsed transaction fields enter staging. Never log preview responses or real transaction descriptions.

Exact file identity is `(user_id, account_id, SHA-256)`. A pending or completed identical file returns **409** with the existing batch ID. Use GET to recover a pending preview. Failed processing attempts retain safe metadata and may be retried. Invalid extension/MIME/header/size requests are rejected before creating a batch; valid-header unsupported or invalid statements can be recorded as FAILED because provider fields are already nullable in Phase 2.

Possible transaction duplicates are distinct from exact files. Source IDs match within account, institution, and parser identity. Without comparable stable IDs, matching uses date, exact amount, currency, and whitespace/case-normalized description for comparison only. Identical candidates within the same preview are also flagged. Raw descriptions/merchants are preserved. Phase 5 enriches canonical rows during confirmation; preview candidates and parser DTOs remain unchanged.

If any candidate has matches, confirmation requires an explicit `import` or `skip` decision for each flagged candidate. For example:

```json
{"decisions": {"33333333-3333-4333-8333-333333333333": "import", "44444444-4444-4444-8444-444444444444": "skip"}}
```

Missing decisions return **409** `duplicate_resolution_required`; GET refreshes matches. Unknown candidate IDs or invalid decisions return **422**. No heuristic match is silently removed. Decisions are only accepted for candidates flagged by confirm-time duplicate detection. Both skip and unnecessary import decisions for non-duplicates return **422** `decision_for_non_duplicate_candidate`; all non-duplicates import automatically. Both strong and heuristic matches require review; an explicit import decision permits retaining a legitimate repeated row.

Confirmation locks the account and then the batch with PostgreSQL `FOR UPDATE`. Account locking serializes different imports into the same account, so confirm-time duplicate checks see preceding commits. Canonical inserts, COMPLETED status, and staging deletion commit together or all roll back. Repeated confirmation of COMPLETED returns the existing status/counts with no additional inserts. Completed responses contain no staging transaction list. Skipping rows does not change the original statement reconciliation totals.

Counter semantics: `total_rows = valid_rows + failed_rows`; `duplicate_rows` is an overlapping subset of valid rows, not an extra addend. Failed reconciliation invalidates the whole parsed candidate set. `imported_rows` counts actual persisted transactions; completed `skipped_duplicate_rows = valid_rows - imported_rows`. Pending GET responses refresh duplicate counts; stored `duplicate_rows` records the preview/confirmation snapshot. Statement totals remain positive qualifying purchase magnitudes, independently of canonical signed amounts and explicit skips.

Revision **0002** adds provider-neutral `import_transaction_candidates` and the nullable `ImportBatch.statement_period` label. Existing canonical Transaction columns are unchanged. Monthly labels never manufacture billing start/end dates. Apply and check:

```sh
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
```

Only downgrade disposable test databases: downgrading to 0001 removes pending staging data and period labels. Successful confirmation deletes staging rows; failed parsing retains none. Abandoned pending previews remain until deliberately cleaned up; automatic expiry and cancellation endpoints are not provided in this phase. No background worker is introduced.

Errors use safe static codes: **413** for limits, **415** for unsupported media/statements, **422** for invalid input/statements, **404** for missing or unowned context, **409** for state/duplicate conflicts, and **500** for safely handled database failures. Error responses omit raw input, filenames, SQL parameters, and validation input echoes.

## Phase 5 classification and corrections

Classification is deterministic Python backed by the existing PostgreSQL catalog, aliases, and user rules. It makes no LLM, ML, fuzzy-matching, or external-service calls. No monetary fields or financial transaction types are changed.

For merchant-eligible transactions, category precedence is **USER > MERCHANT_RULE > SYSTEM_RULE > OTHER/NEEDS_REVIEW**. Merchant name and category resolve independently: a merchant-only user preference wins for the name while the category can fall through. The winning global alias may supply only a name; then category matching continues to system keywords. A category-only user rule can retain the global normalized merchant. Lower layers never overwrite a supplied higher-layer field.

Matching uses NFC Unicode normalization, Turkish casing (`İ/i` and `I/ı` remain distinct pairs), casefolding for other characters, and trimmed/collapsed whitespace. `Ş/Ğ/Ü/Ö/Ç` remain meaningful Unicode. NFC also makes decomposed and composed equivalents match. No arbitrary words are removed. Context is nonblank `merchant_raw`, otherwise `description_raw`; both original fields remain immutable. Duplicate detection retains its separate frozen Phase 4 comparison policy.

Active aliases match normalized **literal substrings**, without database-controlled regex. Longest normalized pattern wins; ties use normalized pattern, original pattern, then UUID ordering, independent of database row order. The small public-brand baseline covers Migros, Starbucks, Amazon, Trendyol, Trendyol Yemek, Getir, and Decathlon. Migros/Getir include both dotted and ASCII-uppercase spellings. Getir supplies normalization only because its services span categories. Aliases are deliberately incomplete and broad public-brand mappings may need a user override.

Static Unicode whole-token keywords are `AKARYAKIT/PETROL → FUEL`, `CAFE/COFFEE/KAHVE → CAFE`, and `MARKET → GROCERIES`. Subwords such as MARKETING do not match. Conflicting category keywords yield unresolved status. An unresolved result has `category_id=OTHER`, `category_source=UNKNOWN`, and `review_status=NEEDS_REVIEW`; it is not a confident classification.

`EXPENSE`, `REFUND`, and `CASH_WITHDRAWAL` can use merchant rules. Refunds keep their financial type and sign; no purchase linking or inherited category lookup is implemented. Cash withdrawals retain their type regardless of category; categorization is not a determination of spending impact. Before merchant rules, semantic guards assign `INCOME → INCOME`, `TRANSFER/CARD_PAYMENT → TRANSFER`, and `FEE → FINANCIAL_FEES`, with `SYSTEM_RULE/AUTO_CONFIRMED` and no fabricated merchant. `INTEREST/UNKNOWN` remain `OTHER/UNKNOWN/NEEDS_REVIEW` because the type alone does not establish a spending category.

Automatic user, merchant, or system category assignments use `AUTO_CONFIRMED`. `CategorySource.USER` denotes a category chosen by a user correction/rule; `MERCHANT_RULE` denotes an alias category; `SYSTEM_RULE` denotes a keyword or semantic-type assignment. `CLASSIFIER` is reserved and unused.

Revision **0003**, `0003_system_categories.py`, seeds 18 stable category codes: GROCERIES, RESTAURANTS, CAFE, FOOD_DELIVERY, TRANSPORTATION, FUEL, SHOPPING, ENTERTAINMENT, SUBSCRIPTIONS, BILLS, HOUSING, HEALTH, EDUCATION, TRAVEL, FINANCIAL_FEES, INCOME, TRANSFER, OTHER. English display labels are separate from codes. Seed IDs are deterministic UUIDv5 values. There are no schema or enum changes and no live application imports in the migration. Upgrade preserves existing rows; a conflicting non-system catalog code fails explicitly. Downgrade to 0002 intentionally **retains all seed data**, edits, and references; re-upgrade does not overwrite them. Test downgrades only in disposable databases. No custom-category CRUD is available.

Both endpoints require the existing development-only `X-Dev-User-ID` UUID header and are disabled outside `APP_ENV=development`. This remains caller-asserted identity, not authentication.

- `GET /api/v1/categories`: read-only system catalog, sorted by code; returns `id`, `code`, `display_name`, `parent_id`.
- `PATCH /api/v1/transactions/{transaction_id}/classification`: corrects one owned transaction. Missing and unowned UUIDs both return the same 404 response.

Correction body (obtain category UUIDs from the catalog):

```json
{
  "preferred_merchant_name": "Demo Coffee",
  "category_id": "CATEGORY_UUID_FROM_CATALOG",
  "persist_as_rule": true
}
```

Provide a non-null category and/or nonblank merchant name (maximum 255 characters). Omitted fields remain unchanged; explicit nulls and unknown fields are rejected. `persist_as_rule` defaults to false. Response fields are `id`, `merchant_normalized`, `category_id`, `category_source`, and `review_status`, without money or raw descriptions. Corrections always set `USER_CONFIRMED`; a category change sets `USER`, while a merchant-only correction preserves existing category provenance. Non-merchant types reject merchant preferences, spending categories, and rule persistence; explicit category corrections can select their semantic category or OTHER.

Persisted rules use `(user_id, merchant_key)`, where `merchant_key = "v1:" + SHA-256(UTF-8 comparison context)`. This is exact normalized-context identity represented by a bounded digest to fit the existing 255-character column without truncating long descriptions. It is not fuzzy matching, encryption, or a source-row identity. A changed location or other meaningful context requires a separate correction. Upsert changes only supplied preferences, preserving earlier omitted rule fields. Only the selected transaction changes; other historical transactions are never bulk rewritten. Future confirmations load that user's current rules once per batch.

Classification runs inside the existing account/batch-locked confirmation transaction, before canonical inserts commit. Classification failure rolls back canonical rows, batch status, and staging cleanup. No raw PDF/text persistence is added. Preview, duplicate resolutions, exact-file idempotency, and repeated-confirm semantics remain unchanged. This phase adds no analytics, product UI, authentication, or AI.

## Phase 6 deterministic analytics

Analytics read committed canonical `Transaction` rows only, using PostgreSQL aggregates and the central `analytics/policy.py`. There is no staging/import-metadata query or parser/bank condition. Canonical existence is the inclusion boundary: Phase 4 creates rows and marks the import COMPLETED atomically. Rows without an import batch also participate. Staging and skipped duplicates never count. Every response identifies `data_scope=CANONICAL_TRANSACTIONS`; these records may represent incomplete financial activity.

All endpoints reuse the development-only `X-Dev-User-ID` header. Every transaction query is owner-scoped. Optional `account_id` requires an owned account; unknown and unowned IDs return identical 404 `account_not_found`. Optional `currency` accepts one uppercase three-letter code. No currency conversion or combined cross-currency total exists.

| GET endpoint | Required inputs | Additional inputs |
| --- | --- | --- |
| `/api/v1/analytics/summary` | `start_date`, `end_date` | `account_id`, `currency` |
| `/api/v1/analytics/categories` | `start_date`, `end_date` | `account_id`, `currency` |
| `/api/v1/analytics/merchants` | `start_date`, `end_date` | `account_id`, `currency`, `limit` (default 10, 1–100 per currency) |
| `/api/v1/analytics/trend` | `start_date`, `end_date` | `account_id`, `currency` |
| `/api/v1/analytics/compare` | `current_start`, `current_end`, `previous_start`, `previous_end` | `account_id`, `currency` |
| `/api/v1/analytics/projection` | `year`, `month`, `as_of_date` | `account_id`, `currency` |
| `/api/v1/transactions` | `start_date`, `end_date` | `account_id`, `currency`, `category_id`, `transaction_type`, `review_status`, `merchant_query`, `limit`, `offset` |

Dates are explicit ISO calendar dates, inclusive on both ends, based on `transaction_date`. No default current month, billing-period interpretation, or server-clock dependency is used. Each range is ordered, limited to 3,661 inclusive days, and bounded to 1900–2100. Invalid inputs return safe 422 `invalid_request`. Comparison periods are explicit and can differ in length or overlap; results describe exactly those requested ranges, without automatic period-length normalization.

**Spending policy:** gross spending sums EXPENSE magnitudes; refunds sum positive REFUND amounts; net spending is gross minus refunds. FEE negative outflows and CASH_WITHDRAWAL negative outflows are separate `financial_fees` and `cash_withdrawals`. TRANSFER, CARD_PAYMENT, INCOME, INTEREST, and UNKNOWN never count as consumer spending. Types drive these rules regardless of category or merchant. NEEDS_REVIEW expenses still count. Installments contribute only their canonical row amount, never amount multiplied by installment count. Analytics does not repair transaction types or infer refund links.

Summary returns `period`, scope/filter metadata, and a `currencies` list sorted by code. Each group contains `gross_spending`, `refunds`, `net_spending`, `financial_fees`, `cash_withdrawals`, `expense_transaction_count`, and `refund_transaction_count`. All money is a two-decimal string. For example, the synthetic core scenario returns:

```json
{
  "currency": "TRY",
  "gross_spending": "1700.00",
  "refunds": "100.00",
  "net_spending": "1600.00",
  "financial_fees": "25.00",
  "cash_withdrawals": "1000.00",
  "expense_transaction_count": 3,
  "refund_transaction_count": 1
}
```

With no matching rows and no currency filter, `currencies=[]`; an explicit currency produces a zero summary/projection or empty breakdown group. Summary/trend currency groups are discovered from all canonical types in the queried range. Breakdown groups include EXPENSE/REFUND only. Comparison uses the union of currencies in either period and zero-fills missing sides. This avoids inferring currency from account configuration when the canonical rows contain another currency.

Category groups expose category ID/code/name, gross/refunds/net, and EXPENSE-plus-REFUND row count. Refunds reduce their currently assigned category only. Null categories are grouped with the seeded OTHER category without changing stored records; unresolved refunds stay in OTHER. Category sorting is net descending, then code ascending. Negative net buckets remain visible. Filtering the transaction explorer by OTHER also includes canonical null categories; the explorer preserves their actual null category value.

Merchant groups prefer nonblank `merchant_normalized`, otherwise a trimmed `merchant_raw` of at most 120 characters, otherwise a structured null/UNKNOWN bucket. They never manufacture a merchant name from `description_raw`. Identities include their source (`NORMALIZED`, `RAW`, `UNKNOWN`); matching is exact and case-sensitive after trimming, with no fuzzy attribution between raw and normalized identities. Refunds follow their own exact merchant identity; unknown identities remain an unattributed bucket. Sorting is net descending, merchant in PostgreSQL C collation ascending (null last), then identity source. Limits are applied per currency in SQL. Top-N merchant results need not sum to the full summary.

Trend returns every intersecting calendar month, including zero months for each discovered/requested currency. First/last partial months include only dates inside the requested range. Comparison returns current/previous net, absolute change, direction, percentage, and `percentage_state`. For a positive previous net, percentage is `(current - previous) / previous * 100`. Both zero → `0.00/BOTH_ZERO`; previous zero with nonzero current → `null/PREVIOUS_ZERO`; previous negative → `null/PREVIOUS_NEGATIVE`. Direction always follows the absolute change. Both periods are aggregated within one SQL statement/snapshot.

Projection uses inclusive elapsed days from the first of the requested month through `as_of_date`, which must belong to that month. Only rows through that date participate. `projection_basis=max(observed_net_spending, 0)`, daily rate is basis / elapsed days, and projected month spending is the unrounded rate × actual calendar days in the month. Leap years are supported. Daily/projected output and percentages round to cents using Decimal ROUND_HALF_UP; the daily display is not reused to calculate the projection. The response includes the method `LINEAR_DAILY_RUN_RATE`, observed net (possibly negative), non-negative basis/projection, day counts, and explicit assumptions. This projects spending pace from incomplete observations; it does not estimate balance, salary, savings, or remaining money.

Transaction explorer pagination uses `limit` (default 50, 1–100), `offset` (0–100000), and `has_more`; SQL fetches at most limit + 1 rows. Order is transaction date DESC, created_at DESC, UUID DESC. Offset pagination can shift between requests when new data arrives. Category is eager-loaded without per-row queries. Merchant search is a bounded, escaped, case-insensitive PostgreSQL substring against normalized/raw merchant and description; `%`/`_` are literal, not caller-controlled wildcards. The response exposes canonical fields, exact decimal amount, category/provenance/review, and installment metadata; it excludes source/parser metadata, raw PDF text, other users' data, and balance fields.

`AnalyticsService` accepts validated query DTOs and returns typed Pydantic results without HTTP. PostgreSQL performs summary/category/merchant/month aggregates; Python performs Decimal comparisons, projections, and zero-bucket construction. Existing user/date, account/date, and user/merchant indexes are retained. No migration, dependency, cache, external service, or frontend source change is added; Alembic remains `0003 (head)`.

## Backend without Docker

Create and activate a Python 3.12 virtual environment inside `backend`. Check an existing environment with `python --version`; an earlier 3.14 environment must be replaced with a fresh 3.12 environment before installing this project:

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --constraint requirements.lock -e ".[dev]"
python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

On macOS/Linux use `python3.12 -m venv .venv` and `source .venv/bin/activate`. Settings load the root `.env`; environment variables take precedence. Health tests do not need a running database or frontend.

From `backend` with the environment active:

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m ruff format .
```

To use the database, start `docker compose up -d postgres` from the root, then run from `backend`:

```sh
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Revision `0001` creates the eight domain tables from the empty Phase 1 baseline. Revision `0002` adds import staging and the source period label. Revision `0003` seeds the category/alias catalog. `current` should report `0003 (head)` and `check` should report no new operations. Model imports are registered centrally in `app/db/models.py` and loaded by Alembic. Downgrading to `base` deletes the domain tables and their data; use the test suite for safe downgrade/re-upgrade verification in isolated databases.

## Frontend without Docker

With the root `.env` configured and the backend running:

```sh
cd frontend
npm ci
npm run dev
npm run typecheck
npm run build
```

Vite reads `VITE_API_BASE_URL` from the root `.env`. Restart Vite after changing it; production builds embed its value at build time. `npm run preview` serves a built bundle locally and is not a production deployment server.

Dependency versions are recorded in `frontend/package-lock.json` and `backend/requirements.lock` (Python constraints). No future module folders or placeholder domain implementations are created before their phases.

## Phase 7 web product

Open `http://localhost:5173` after `docker compose up -d --build` and migrations. The primary routes survive refresh:

- `/overview`: separate currency metrics, category bars, monthly trend, top merchants, explicit period comparison, and a spending-pace projection.
- `/transactions`: bounded server pagination (20 rows), date/account/category/type/review/currency/search filters, and merchant/category correction.
- `/imports`: PDF upload and bounded database-backed history (20 batches).
- `/imports/:id`: persisted preview, reconciliation, duplicate decisions, and completed counts.

Choose the current month, previous month, or custom calendar dates and apply the form. Transaction searches also use **Filtreleri uygula**; typing does not issue a request on each keystroke. Summary cards keep currencies separate; the chart currency selector does not perform FX conversion. Money labels format original decimal strings exactly. Charts only convert values into drawing coordinates. Projection is a backend spending estimate, not remaining money.

### Local development context

This is **development plumbing, not authentication**. Use the existing development-only backend settings documented above. Select an existing user's UUID in **Bağlamı değiştir**, or optionally set `VITE_DEV_USER_ID` in your untracked root `.env` and restart/rebuild Vite. Vite variables are public browser configuration and must never contain credentials. Only this development UUID is stored in sessionStorage; PDF bytes, transaction lists, and import history are not persisted in browser storage. Changing the user clears query caches and the selected account.

The account selector loads owned accounts from `GET /api/v1/accounts` (50 per page). Select a specific account before upload; **Tüm hesaplar** is available for analytics and transactions. No account CRUD or login UI exists.

If no development context exists, this **PowerShell** command creates a disposable synthetic user and empty TRY account in the local development database. It generates a reserved `.invalid` email, no personal identity or financial transactions. Run it only in your local development stack. Save the printed UUID to select the context in the UI.

```powershell
@'
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db import models
from app.db.session import get_engine
from app.modules.auth.models import User
from app.modules.accounts.models import Account
from app.modules.accounts.enums import AccountType

assert get_settings().app_env == "development", "Local development only"
user_id = uuid4()
with Session(get_engine()) as session:
    session.add(User(id=user_id, email=f"demo-{user_id}@example.invalid"))
    session.flush()
    account = Account(user_id=user_id, display_name="Sentetik geliştirme hesabı",
                      institution_code="YAPI_KREDI", account_type=AccountType.DEBIT_CARD,
                      currency="TRY")
    session.add(account)
    session.commit()
    print("Development user UUID:", user_id)
    print("Account UUID:", account.id)
'@ | docker compose exec -T backend python -
```

Upload only a supported Yapı Kredi TLcard PDF. The UI states the default 10 MiB limit; the configured backend limit and parser validation remain authoritative. Preview displays reconciliation and candidates but creates no canonical financial rows. Normal candidates import automatically and have no skip control. Every currently flagged duplicate needs an explicit import/skip decision. Confirm-time conflicts reload the persisted preview. Successful confirmation refreshes transactions, history, and analytics.

Corrections preserve read-only raw descriptions and amounts. The optional future-rule checkbox reuses the frozen backend classification policy; it does not rewrite other historical rows. Successful corrections invalidate all transaction and analytics queries for the active user, and affected pages fetch fresh backend results.

The only Phase 7 backend additions are owned, bounded reads: `GET /api/v1/accounts` and `GET /api/v1/imports` (optional owned `account_id`). Neither exposes account identifiers, file names/hashes, raw PDF text, or customer metadata. No migration was added; Alembic remains `0003 (head)`.

Frontend verification:

```sh
docker compose exec -T frontend npm run test
docker compose exec -T frontend npm run typecheck
docker compose exec -T frontend npm run build
```

Tests use Vitest, jsdom, and Testing Library with synthetic API responses. See [PHASE_7_REPORT.md](PHASE_7_REPORT.md) for browser acceptance, dependency rationale, and verification results. This phase introduces no AI, production authentication, service worker, or offline financial cache.

## Phase 8 safe financial assistant

The `/assistant` product page asks natural-language questions through a backend-only Groq integration. Configure `GROQ_API_KEY` in the untracked root `.env`; optionally set `GROQ_MODEL` and the documented `ASSISTANT_*` limits from `.env.example`. The secret is passed only to the backend container. Never create a `VITE_GROQ_*` variable because every Vite variable is public browser configuration.

`POST /api/v1/assistant/chat` is stateless. It accepts a bounded user/assistant history, a browser IANA timezone, and the optional account selected in the existing development context. The backend validates account ownership before any provider call and injects the current user internally. User IDs and account IDs are absent from Groq tool definitions. `GET /api/v1/assistant/status` reports only whether the feature is enabled plus the non-secret provider/model name.

The model can select only seven hardcoded tools: spending summary, category breakdown, merchant breakdown, monthly trend, period comparison, month projection, and bounded transaction search. Pydantic validates every argument and the existing `AnalyticsService` computes every financial result with Decimal-safe, currency-separated semantics. Category-filtered period comparison is the only additive analytics capability. There is no SQL tool, generated SQL, dynamic dispatch, web tool, or model-side authoritative calculation.

Example questions include:

- `Bu ay ne kadar harcadım?`
- `En çok hangi kategoriye harcadım?`
- `Kafeye geçen aya göre daha fazla mı harcadım?`
- `Son altı ay harcamam nasıl değişti?`
- `Bu hızla ay sonunda ne kadar harcarım?`

Current-month questions mean month-to-date in the validated client timezone; historical months mean complete calendar months. The assistant only knows imported canonical transactions, whose coverage may be incomplete. It cannot determine current balance, net worth, complete income, savings rate, or guaranteed remaining cash.

Aggregate data is preferred. The user's assistant message and limited derived financial data selected by FinSight tools may be sent to Groq to produce an answer. Transaction search sends at most 20 minimized rows with date, normalized merchant, category, amount, currency, type, and review state. Raw descriptions, account/card identifiers, source metadata, uploaded PDF bytes, and extracted PDF text never enter the provider payload. The UI states this boundary explicitly. Conversation state lives only in React memory and clears on refresh or development user/account changes.

Before any provider answer reaches the API response, a provider-independent grounding validator checks user-specific financial amounts, percentages, transaction counts, projections, and unambiguous comparison directions against tool results executed in that same request. Client-supplied history is never grounding authority. Exact Turkish and international display variants are normalized with `Decimal`; unsupported values trigger at most one constrained rewrite call. If that rewrite is still unsupported, malformed, asks for another tool, or fails at the provider, FinSight returns a fixed safe response without financial figures. The validator performs no database access and no financial recalculation.
