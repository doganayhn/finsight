# FinSight — Phase 1 Hardening Report

Repository: `C:\Users\doğan\Documents\ChatGPT\finsight`

This report records the completed Phase 1 foundation cleanup and its verification results.

## 1. Existing Port Configuration

Routing was already correct: the backend container connected to `postgres:5432`. The ambiguity was that `POSTGRES_PORT` also controlled host port publication.

## 2. Changes Made

- Added `POSTGRES_HOST_PORT=55433` specifically for Compose port publication.
- Kept `POSTGRES_PORT` exclusively as the client's destination port: `55433` for host-run Python/Alembic and explicitly `5432` for the backend container.
- Updated `docker-compose.yml`, `.env.example`, the ignored local `.env`, and `README.md`.
- Added `backend/.python-version` containing `3.12` and updated the Python constraint in `backend/pyproject.toml`.
- No dependency versions were changed.

## 3. Python Runtime Policy

**Python 3.12 is the canonical, recommended, and supported backend runtime for V1.**

The project now declares `requires-python = ">=3.12,<3.13"`. Docker remains on `python:3.12-slim`; the verified container runtime was Python **3.12.14**. README explicitly documents this policy.

The existing host Python 3.14 virtual environment was left intact. It was used for host connectivity/Alembic checks, but canonical backend tests ran in the Python 3.12 container. New project installations require Python 3.12.

## 4. Commands Executed

From the repository root:

```powershell
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 120
docker compose exec -T backend python --version
docker compose exec -T backend pytest
docker compose exec -T backend ruff check .
docker compose exec -T backend ruff format --check .
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini current
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini check
Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/health'
docker compose ps
```

From `frontend`:

```powershell
npm run build
```

Additional verification inspected the resolved Compose configuration, queried PostgreSQL from both the host and backend container, checked server port/table metadata, and compared all frozen documents with their original ZIP entries using SHA-256.

## 5. Test and Build Results

| Check | Result |
| --- | --- |
| Backend pytest on Python 3.12.14 | 3 passed; 2 upstream deprecation warnings |
| Ruff lint | Passed |
| Ruff format check | Passed |
| Frontend TypeScript and production build | Passed |
| Docker Compose configuration validation | Passed |
| Docker image build and startup | Passed; all three services healthy |
| Alembic current/check, host and container | Passed; no new upgrade operations |
| PostgreSQL connectivity, host and container | Passed |
| Backend health endpoint | HTTP 200, `{"status":"ok"}` |
| Frozen-document integrity | All 9 files match the original ZIP |

## 6. Final Docker and Database Connectivity

| Connection | Verified destination |
| --- | --- |
| Backend container → PostgreSQL | `postgres:5432` |
| Windows host → PostgreSQL | `127.0.0.1:55433` → container port `5432` |
| Frontend | <http://localhost:5173> |
| Backend health | <http://localhost:8000/api/v1/health> |

Both database connections successfully executed `SELECT 1`. The server reported port `5432`. Only the `alembic_version` bookkeeping table exists; there are no domain tables.

PostgreSQL remains published exclusively on localhost. All three containers were left healthy and running at the end of verification.

## 7. Unresolved Warnings

- Starlette's TestClient integration emits a deprecation warning for `httpx` in favor of `httpx2`.
- Starlette's use of the `anyio.abc.BlockingPortal` alias emits a deprecation warning.
- The Docker build emitted pip's standard root-user warning and a package-manager update notice.

Warnings were not suppressed. No verification failures remain, and no dependency upgrades were performed.

## 8. Phase 1 Freeze Readiness

**Phase 1 is ready to freeze.**

- **A:** The backend container connects to `postgres:5432`.
- **B:** Host PostgreSQL access uses `127.0.0.1:55433` in the current local environment.
- **C:** No Phase 2 functionality, domain models, or future features were introduced.
- **D:** `AGENTS.md` and all frozen architecture documents remain byte-identical to the original ZIP.

Phase 2 has not started.
