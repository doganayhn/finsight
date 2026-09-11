# FinSight V1 operations

This guide covers a small self-hosted deployment. `docker-compose.prod.yml` is a reproducible template, not a replacement for managed database, TLS, monitoring, or backup services.

## Release and startup

1. Build immutable backend and frontend images from a reviewed revision. Supply the public API URL when the frontend image is built.
2. Provide production variables through a secret manager or protected deployment environment. Do not copy `.env.example` values into production.
3. Apply the forward migration once: `alembic upgrade head`. The production Compose template models this as the one-shot `migrate` service; the backend waits for its successful completion. Application replicas must never each run migrations at startup.
4. Start the API with the production image's fixed invocation: `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 --no-access-log`. Scale containers through the deployment platform only after the migration job succeeds.
5. Serve the compiled React files from the unprivileged Nginx image. Put TLS and any public routing in a trusted ingress.

For the template, after exporting all required variables:

```sh
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

PostgreSQL has no host port in the production template. The published frontend and backend addresses default to localhost so exposure is an explicit deployment choice.

## Health and logs

- `/api/v1/health` is the frozen compatibility response: `{"status":"ok"}`.
- `/api/v1/health/live` verifies that the API process can respond.
- `/api/v1/health/ready` verifies database connectivity. Groq is optional and does not control readiness.
- Container health checks use readiness for the backend and the static root for the frontend.

Use the deployment platform's container logs or `docker compose -f docker-compose.prod.yml logs backend frontend postgres`. FinSight logs request metadata and safe error codes; raw PDF content, transaction descriptions, authorization headers, cookies, and passwords must not be added to logs. Configure retention and access outside the application.

## PostgreSQL backup and restore

Run backups with a restricted database credential supplied interactively or by the secret manager. The examples deliberately contain no password:

```sh
pg_dump --host DB_HOST --username DB_USER --dbname finsight \
  --format=custom --no-owner --file finsight_TIMESTAMP.dump
pg_restore --host RESTORE_HOST --username RESTORE_USER --dbname finsight_restore \
  --clean --if-exists --no-owner finsight_TIMESTAMP.dump
```

Create the restore database separately, restore into an isolated environment, run `alembic current`, and execute the acceptance suite before promoting restored data. Periodically test restores; an untested dump is not a recovery plan. Production backups contain private financial data and authentication records, so encrypt them, restrict access, set retention, and store them outside the application host. Never commit dumps.

## Secret rotation

- Rotate the PostgreSQL password in the database and secret store together, then restart migration/API workloads. Test readiness before returning traffic.
- Rotating `AUTH_JWT_SECRET` immediately invalidates existing access-token signatures. Existing valid refresh sessions can obtain tokens signed with the new secret; revoke or delete active `auth_sessions` as part of the rotation when a full sign-out is required. Expect users to authenticate again after full revocation.
- Rotate `GROQ_API_KEY` only in the backend secret store. Core product features remain available while it is absent; `/api/v1/assistant/status` reports the assistant as disabled.

## Common failures

| Symptom | Check and recovery |
| --- | --- |
| Backend refuses to start | Read the safe validation message. Confirm a strong JWT secret, secure refresh cookie, exact HTTPS frontend origins, and a valid `postgresql+psycopg` database URL or split database fields. |
| Migration service fails | Stop the release, inspect the migration log and database connectivity, and fix forward. Never run an automatic downgrade. |
| Readiness is unavailable | Check PostgreSQL health, credentials, DNS/service name, port, and migration state. Liveness may remain healthy while readiness fails. |
| Browser receives CORS errors | Match the exact HTTPS scheme, host, and port in `FRONTEND_ORIGINS`; do not use a wildcard with credentials. Rebuild when the public API URL changed. |
| Deep links return 404 | Confirm the request reaches the production Nginx image and its SPA fallback, rather than the Vite development server or an incorrectly configured outer proxy. |
| Assistant is disabled | Core V1 is healthy. Configure a valid backend-only `GROQ_API_KEY` if the optional assistant is desired. |
| Login loops or refresh fails | Confirm HTTPS, `Secure` cookie delivery, allowed Origin, system time, database-backed session state, and the current JWT secret. |
| Import fails | Confirm the source is a text-layer Yapı Kredi TLcard PDF within configured byte/page limits. Raw PDFs are temporary and should not be copied into logs. |
