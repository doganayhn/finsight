# FinSight environment reference

FinSight reads backend settings from environment variables. A root `.env` file is a local-development convenience and must never be committed. Deployment secrets belong in the target platform's secret store. Values beginning with `VITE_` or supplied as `PUBLIC_API_BASE_URL` are compiled into browser code and must never contain secrets.

## Backend and database

| Variable | Classification | Purpose |
| --- | --- | --- |
| `APP_ENV` | Required in production; non-secret | `development`, `test`, or `production`. Production enables strict startup validation. |
| `DATABASE_URL` | Optional alternative; **secret** | Complete SQLAlchemy URL for a standalone backend or migration job. It must use `postgresql+psycopg` and include host and database. When set, it takes precedence over split client fields. |
| `POSTGRES_DB` | Required when `DATABASE_URL` is absent; non-secret | Database name. Defaults to `finsight`. |
| `POSTGRES_USER` | Required when `DATABASE_URL` is absent; non-secret | Database role. Defaults to `finsight`. |
| `POSTGRES_PASSWORD` | Required when `DATABASE_URL` is absent; **secret** | Database password. Production Compose refuses to render without it. |
| `POSTGRES_HOST` | Required when `DATABASE_URL` is absent; non-secret | Client destination. The Compose backend uses `postgres`; a host-run client commonly uses `127.0.0.1`. |
| `POSTGRES_PORT` | Required when `DATABASE_URL` is absent; non-secret | Client destination port. It is `5432` inside the Compose network. |
| `POSTGRES_HOST_PORT` | Local development only; non-secret | Publishes PostgreSQL as `127.0.0.1:55433` by default. Production Compose publishes no database port. |
| `FRONTEND_ORIGINS` | Required in production; non-secret | JSON array of exact browser origins allowed by CORS, for example `["https://app.example.invalid"]`. Production requires HTTPS and rejects wildcards. `CORS_ORIGINS` remains a compatibility alias. |
| `MAX_UPLOAD_BYTES` | Optional; non-secret | Maximum PDF file bytes, default `10485760` (10 MiB), bounded to 100 MiB. |
| `MAX_PDF_PAGES` | Optional; non-secret | Maximum PDF pages, default `50`, bounded to 500. |

Use URL escaping for credentials in `DATABASE_URL`. The split fields avoid hand-escaping reserved characters and are the production Compose default. Do not log either representation.

## Authentication

| Variable | Classification | Purpose |
| --- | --- | --- |
| `AUTH_JWT_SECRET` | Required; **secret** | Signs short-lived access tokens. Use a unique, randomly generated value of at least 32 characters. Production rejects common placeholder markers and low-diversity values. |
| `AUTH_ACCESS_TOKEN_MINUTES` | Optional; non-secret | Access-token lifetime, default `15`, allowed range 5–60 minutes. |
| `AUTH_REFRESH_TOKEN_DAYS` | Optional; non-secret | Refresh-session lifetime, default `30`, allowed range 1–90 days. |
| `AUTH_REFRESH_COOKIE_SECURE` | Required in production; non-secret | Must be `true` in production so browsers send the refresh cookie only over HTTPS. |
| `AUTH_RATE_LIMIT_REQUESTS` | Optional; non-secret | Per-process authentication attempt threshold, default `10`. |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | Optional; non-secret | In-memory limiter window, default `60`. |
| `AUTH_RATE_LIMIT_MAX_KEYS` | Optional; non-secret | Bound for limiter keys, default `2048`. This is basic V1 protection, not a distributed edge limiter. |

## Optional Groq assistant

| Variable | Classification | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | Optional; **secret** | Enables the assistant when present. Core imports, corrections, and analytics work without it. |
| `GROQ_MODEL` | Optional; non-secret | Provider model name, default `openai/gpt-oss-120b`. |
| `ASSISTANT_MAX_MESSAGE_CHARS` | Optional; non-secret | User-message bound, default `4000`. |
| `ASSISTANT_MAX_HISTORY_MESSAGES` | Optional; non-secret | Client-history item bound, default `10`. |
| `ASSISTANT_MAX_HISTORY_CHARS` | Optional; non-secret | Total client-history character bound, default `12000`. |
| `ASSISTANT_MAX_TOOL_ROUNDS` | Optional; non-secret | Tool-loop round bound, default `4`. |
| `ASSISTANT_MAX_TOOL_CALLS` | Optional; non-secret | Total tool-call bound, default `8`. |
| `ASSISTANT_MAX_PROVIDER_CALLS` | Optional; non-secret | Provider-call bound including a grounding repair, default `6`. |
| `ASSISTANT_PROVIDER_TIMEOUT_SECONDS` | Optional; non-secret | Groq request timeout, default `20`. |
| `ASSISTANT_MAX_OUTPUT_TOKENS` | Optional; non-secret | Provider output-token cap, default `700`. |

## Container publication and frontend build

| Variable | Classification | Purpose |
| --- | --- | --- |
| `BACKEND_BIND_ADDRESS` | Optional production template setting; non-secret | Host interface for the API publication. Defaults to `127.0.0.1`; set deliberately when an external ingress must reach it. |
| `BACKEND_PORT` | Optional; non-secret | Published API port, default `8000`. |
| `FRONTEND_BIND_ADDRESS` | Optional production template setting; non-secret | Host interface for the web container. Defaults to `127.0.0.1`. |
| `FRONTEND_PORT` | Optional; non-secret | Development port defaults to `5173`; production template defaults to `8080`. |
| `VITE_API_BASE_URL` | Required frontend build input; public | Browser-visible versioned API URL. Used by local Vite builds. |
| `PUBLIC_API_BASE_URL` | Required by production Compose; public | Passed to `VITE_API_BASE_URL` while building the static frontend. A deployment URL change requires rebuilding the frontend image. |

The production frontend image contains only static output and Nginx. It receives no backend secrets. Terminate TLS at a trusted ingress or load balancer and configure matching HTTPS `FRONTEND_ORIGINS` and `PUBLIC_API_BASE_URL` values.
