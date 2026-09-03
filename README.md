# FinSight

FinSight is a bank-agnostic personal spending intelligence platform. **Current status: Phase 1 — project foundation.** This phase provides a running API, database infrastructure, and a minimal web screen that checks backend connectivity.

## Architecture and stack

- API-first modular monolith: Python, FastAPI, Pydantic Settings, SQLAlchemy 2.x, Psycopg 3, Alembic.
- PostgreSQL is the future canonical financial store. No domain tables exist yet.
- React, TypeScript, Vite, and Tailwind CSS form the presentation client.
- Docker Compose runs PostgreSQL, backend, and frontend locally.
- pytest and Ruff provide backend checks; TypeScript and Vite verify the frontend.

The frozen engineering contract is in [AGENTS.md](AGENTS.md) and [docs/](docs/). Financial models, imports, authentication, analytics, and AI are intentionally not implemented yet.

Phase 1 is frozen. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for the Git workflow: one final commit per reviewed, explicitly frozen phase; no intermediate commits or force-pushes.

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
docker compose exec backend alembic current
docker compose exec backend alembic check
docker compose exec frontend npm run build
docker compose ps
```

After changing dependencies, Dockerfiles, tests, or configuration files, rebuild. Backend application/Alembic files and frontend source files are bind-mounted for development.

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

There are no revisions or domain tables in Phase 1. `current` therefore prints no revision, and `check` should report no new operations. Phase 2 will register model imports in `alembic/env.py` before generating migrations.

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
