# FinSight

FinSight is a bank-agnostic personal spending intelligence platform. **Current status: Phase 4 — manual PDF import pipeline, awaiting review.** The API supports persistent previews and atomic confirmation. The web screen remains the Phase 1 connectivity foundation.

## Architecture and stack

- API-first modular monolith: Python, FastAPI, Pydantic Settings, SQLAlchemy 2.x, Psycopg 3, Alembic.
- PostgreSQL stores the canonical financial schema: users, accounts, categories, import batches, transactions, transaction links, merchant aliases, and user merchant rules.
- React, TypeScript, Vite, and Tailwind CSS form the presentation client.
- Docker Compose runs PostgreSQL, backend, and frontend locally.
- pytest and Ruff provide backend checks; TypeScript and Vite verify the frontend.

The frozen engineering contract is in [AGENTS.md](AGENTS.md) and [docs/](docs/). Authentication, categorization behavior, analytics, financial product UI, and AI are not implemented yet. See [PHASE_2_REPORT.md](PHASE_2_REPORT.md) for canonical schema decisions, [PHASE_3_REPORT.md](PHASE_3_REPORT.md) for parser verification, and [PHASE_4_REPORT.md](PHASE_4_REPORT.md) for import acceptance results.

Phases 0–3 are frozen. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for the Git workflow: one final commit per reviewed, explicitly frozen phase; no intermediate commits or force-pushes.

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

Possible transaction duplicates are distinct from exact files. Source IDs match within account, institution, and parser identity. Without comparable stable IDs, matching uses date, exact amount, currency, and whitespace/case-normalized description for comparison only. Identical candidates within the same preview are also flagged. Raw descriptions/merchants are preserved; `merchant_normalized` and `category_id` remain null.

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

Revision `0001` creates the eight domain tables from the empty Phase 1 baseline. Revision `0002` adds import staging and the source period label. `current` should report `0002 (head)` and `check` should report no new operations. Model imports are registered centrally in `app/db/models.py` and loaded by Alembic. Downgrading to `base` deletes the domain tables and their data; use the test suite for safe downgrade/re-upgrade verification in isolated databases.

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
