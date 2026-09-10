# FinSight Phase 9 Report

## 1. Phase 9 Status

Phase 9 authentication, security, and reliability hardening is implemented and verified. The changes are left unstaged for review.

## 2. Frozen Phase 8 Baseline Commit

Phase 9 started from local `main` at `6f4e63904ff6f6c373db5d939a093a49843f99cd` (`feat: implement Phase 8 grounded Groq assistant`). Local `main` and `origin/main` matched, and the working tree was clean.

## 3. Authentication Architecture

FinSight now uses first-party email/password authentication. The backend creates a short-lived bearer access JWT and a database-backed session represented in the browser by an opaque rotating refresh token. Product endpoints derive identity from the authenticated backend principal.

## 4. Password Hashing

Passwords are hashed with Argon2id through `argon2-cffi`. Passwords must be 12–128 characters; oversized values are rejected during request validation before hashing. The service uses a dummy Argon2 hash for unknown-user login attempts so public failure handling follows the same verification path.

## 5. User Credential Strategy

The existing `users.email` identity remains canonical and is validated and normalized consistently. `users.password_hash` is nullable so pre-existing development users migrate safely without invented credentials. New registrations always receive a valid hash; credentialless legacy users cannot log in.

## 6. AuthSession Persistence

`auth_sessions` stores a UUID session identifier, owning user, SHA-256 refresh-token hash, expiry, optional revocation time, and timestamps. Plaintext refresh tokens, client IP addresses, user agents, and financial data are not stored.

## 7. Database Migration

Alembic revision `0004_authentication` adds nullable `users.password_hash`, `auth_sessions`, its foreign key and indexes. Migration tests cover empty database to head, repeated upgrade, `0003` to `0004`, safe downgrade/re-upgrade, and preservation of existing financial rows.

## 8. Access JWT Design

Access tokens use PyJWT with an explicit `HS256` allowlist. Claims are limited to `sub`, `sid`, `iat`, `exp`, `iss`, and `aud`; issuer is `finsight`, audience is `finsight-api`, and the default lifetime is 15 minutes. Signature, algorithm, expiration, issuer, audience, subject, and session identifier are validated.

## 9. Refresh Token Design

Refresh tokens use `<session_uuid>.<cryptographically-random-secret>`. Only the hash is persisted. The browser receives the token in the `finsight_refresh` HttpOnly cookie with `SameSite=Lax` and an auth-only path; the default lifetime is 30 days.

## 10. Refresh Rotation

Refresh locks the session row, verifies ownership, status, expiry, and hash with constant-time comparison, replaces the stored hash, issues a new access token, and commits atomically. The old refresh token becomes invalid. Concurrent refresh tests prove that exactly one request can rotate a given token.

## 11. Logout / Revocation

Logout revokes the current server-side session and expires the refresh cookie. Because every bearer request checks the referenced active session, access tokens from the logged-out session immediately fail. Logout remains safe and idempotent when the cookie is missing or stale.

## 12. Current User Dependency

The authenticated dependency validates the bearer JWT and then loads the matching non-revoked, non-expired `AuthSession` joined to its `User`. It returns a backend-derived UUID used by existing ownership filters; request payloads and headers cannot select identity.

## 13. Removal of X-Dev-User-ID

The development UUID product path and `VITE_DEV_USER_ID` workflow were removed. `X-Dev-User-ID` cannot authenticate any endpoint and there is no missing-bearer fallback. Remaining source references are explicit negative regression tests or frozen historical material.

## 14. Auth API Endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

Registration and login return the access token and safe user shape while setting the refresh cookie. Refresh accepts its credential only from the cookie. `/auth/me` returns only user ID, email, and creation time.

## 15. Frontend Auth Architecture

`AuthProvider` owns the access token and user in React memory. The typed API client adds the bearer token and always uses `credentials: "include"`. Auth transitions clear TanStack Query state so cached financial data cannot cross user sessions.

## 16. Login UI

`/login` provides labeled email/password fields, a loading state, generic failure copy, and a registration link. It is connected to the backend and contains no development UUID controls or security internals.

## 17. Registration UI

`/register` requests only email, password, and frontend password confirmation. It communicates the 12-character minimum, enforces matching passwords, and does not request profile, bank, or financial credentials.

## 18. Session Restoration / Refresh

On application startup the provider calls `/auth/refresh`; the HttpOnly cookie is sent automatically and a new access token restores the session. For protected calls, simultaneous 401 responses share one in-flight refresh promise, each original call is retried at most once, and failed refresh returns the app to logged-out state.

## 19. Logout UI

The authenticated shell displays the current email safely and exposes `Çıkış yap`. Logout calls the backend, clears the in-memory access token, user, account selection, assistant conversation through unmounting, and the full query cache, then routes to `/login`.

## 20. Account Onboarding

An authenticated user with no accounts sees `İlk hesabını ekle`. The view explains that the record is local to FinSight, does not connect to a bank, and never asks for a bank username or password. It offers provider-neutral canonical account fields with a TLcard-friendly suggestion.

## 21. Account Creation Endpoint

`POST /api/v1/accounts` accepts only `display_name`, optional `institution_code`, canonical `account_type`, and three-letter `currency`. Extra fields are rejected. `user_id` always comes from authentication and cannot be supplied or overridden by the caller.

## 22. Ownership / User Isolation

Accounts, imports, confirmation, history, transactions, corrections, categories, analytics, and assistant calls now use authenticated identity. Cross-user tests cover account, import, transaction, correction, analytics, and assistant boundaries with existence-safe responses.

## 23. Assistant Auth Migration

The assistant receives the current user exclusively from the authenticated backend dependency. Phase 8 request-bound account verification remains intact; `user_id` and account selection are still absent from model-controlled tool schemas, and Groq cannot choose identity.

## 24. CORS / Cookie Security

CORS uses an explicit origin list with credentials enabled and allows the required authorization/content headers. Wildcard origins are rejected. The refresh cookie is HttpOnly, `SameSite=Lax`, path-limited, and required to be Secure in production.

## 25. CSRF / Origin Boundary

Cookie-authenticated refresh and logout use POST and reject an untrusted `Origin`. Financial writes remain bearer-authenticated through `Authorization` rather than cookie authentication. This keeps the V1 boundary explicit without adding a separate CSRF framework.

## 26. Production Configuration Validation

`APP_ENV` is restricted to development, test, or production. Production fails fast for missing, placeholder, short, or low-diversity JWT secrets; insecure refresh cookies; missing, wildcard, non-HTTPS, or duplicate CORS origins. A strong ephemeral configuration initializes successfully. `GROQ_API_KEY` remains optional.

## 27. Security Headers

API responses include `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`.

## 28. Request IDs

Every API response receives a server-generated UUID in `X-Request-ID`. A caller-provided request ID is ignored, preventing untrusted values from entering the log correlation boundary.

## 29. Logging / Privacy

Request logs contain request ID, method, path, status, and duration only. Headers, cookies, tokens, passwords, request bodies, response bodies, financial values, SQL, and connection strings are excluded. Unexpected exception logs contain the exception type and request ID without payload data.

## 30. Generic Error Handling

Invalid login uses the same public error for an unknown email and incorrect password. Validation responses use a stable safe code. Unexpected exceptions return a generic `internal_error` response without stack traces, SQL, filesystem paths, or configuration details.

## 31. Auth Rate Limiting

A bounded, thread-safe, in-process fixed-window limiter protects registration, login, and refresh using `request.client.host`. Stale buckets expire and the ordered store has a hard size limit. It is intentionally single-instance V1 protection and is not described as distributed or proxy-aware enforcement.

## 32. Health / Readiness

Compatibility endpoint `/api/v1/health` remains. `/api/v1/health/live` reports process liveness and `/api/v1/health/ready` verifies database connectivity. Optional Groq availability does not affect readiness, and responses expose no database configuration.

## 33. Database Reliability Changes

The SQLAlchemy engine enables `pool_pre_ping`, a conservative connection timeout, and UTC session timezone configuration. No database proxy, cache, or speculative pool retuning was introduced.

## 34. RLS Decision

PostgreSQL RLS was not added. The current shared application-role model relies on mandatory authenticated ownership filters, while RLS remains a future defense-in-depth option that needs its own connection-role design and migration proof.

## 35. Backend Tests Added

Backend coverage includes all 50 required authentication/security cases, all nine onboarding cases, authenticated ownership migration across existing modules, migration safety, sanitized errors and logs, request IDs and headers, production configuration, rate-limit bounds, refresh races, and a complete disposable authenticated product flow.

## 36. Backend Test Result

`docker compose exec -T backend pytest` collected and passed **360 tests** on Python 3.12.14. Ruff reported `All checks passed!`; Ruff format reported **173 files already formatted**.

## 37. Frontend Tests Added

Frontend auth tests cover routes and guards, payloads and safe errors, memory-only tokens, startup restoration, single and concurrent refresh, one retry, logout cleanup, safe identity display, removal of development identity, onboarding/account creation, and continued Phase 7/8 product behavior.

## 38. Frontend Test Result

`docker compose exec -T frontend npm test -- --run` passed **73 tests in 3 files**, including **31 auth tests**, **28 product tests**, and **14 assistant tests**.

## 39. Alembic Result

`alembic upgrade head` succeeded, `alembic current` returned `0004 (head)`, and `alembic check` returned `No new upgrade operations detected.` Migration regression tests passed with no model drift.

## 40. Frontend Build / Typecheck

`npm run typecheck` passed. The production Vite build transformed 661 modules and completed successfully; generated output was used only for verification and is not tracked.

## 41. Docker / Health Result

`docker compose up -d --build`, `docker compose config --quiet`, and `docker compose ps` succeeded. Backend, frontend, and PostgreSQL were healthy. Health, live, and ready each returned HTTP 200 with `{"status":"ok"}`. The backend reached PostgreSQL at `postgres:5432`; the host publication remained localhost-only at `127.0.0.1:55433`, and the host TCP probe succeeded.

## 42. Synthetic Authenticated Product Flow

The disposable automated flow registered a user, verified `/auth/me`, verified an empty account list, created an owned synthetic account, previewed and confirmed a synthetic TLcard PDF, checked deterministic analytics and transactions, corrected classification, checked assistant status, logged out, confirmed protected access failed, logged in again, verified persistence, and proved a second user could not access the first user's account. A live HTTP smoke additionally verified register, account creation/list, refresh, logout, and immediate session revocation. Disposable database rows were removed.

## 43. Production-Like Config Smoke

Tests verified failure for weak/default JWT secrets, insecure production cookies, missing/unsafe CORS origins, and invalid environment configuration. A proper production-like configuration with an ephemeral non-persisted secret initialized successfully.

## 44. Responsive Verification

Browser inspection covered login, registration, zero-account onboarding, authenticated shell, and logout at 1440 px, 768 px, and 390 px. DOM measurements confirmed zero horizontal overflow and all onboarding controls inside the viewport. Mobile navigation and the logout redirect were exercised. This was browser viewport emulation; no native Safari claim is made.

## 45. Security Pattern Scan

Scans covered development auth headers/config, browser token storage, auth/cookie/password logging, frontend Groq-key exposure, unsafe HTML, dynamic evaluation/execution, unsupported JWT algorithms, hardcoded secrets, placeholder production secrets, and wildcard credentialed CORS. Application code contains no prohibited product path; removed development-auth names remain only in negative regression tests and frozen historical material.

## 46. Dependencies Added / Changed

Backend dependencies added and pinned: `argon2-cffi 25.1.0`, `PyJWT 2.13.0`, and `email-validator 2.3.0`, with locked transitive packages. No dependency upgrades unrelated to Phase 9 and no external identity platform, Redis, or task queue were introduced.

## 47. Files Added / Modified

**Modified (38):** `.env.example`, `README.md`, `docker-compose.yml`; backend API dependencies/router, configuration, model registry, main app, account and assistant routes, auth models, dependency files, and 10 existing test/fixture files; frontend app, seven existing API modules, account context, four product pages, styles, contracts, and two existing test files.

**Added (13 including this report):** `backend/alembic/versions/0004_authentication.py`; auth errors, rate limiter, routes, schemas, security, and service modules; `backend/tests/test_auth.py`; frontend auth API, provider, page, and tests; `PHASE_9_REPORT.md`.

Total Phase 9 review set: **51 files**. The detailed paths are visible in `git status --short`; nothing is staged.

## 48. Privacy / Sensitive Data Verification

No real statement, private transaction history, PII, bank credential, password, JWT, refresh token, JWT secret, API key, or private financial file was added. Tests and browser QA used synthetic identities and the repository's synthetic PDF fixture. The local verification secret was supplied ephemerally to the process and was not written to the repository.

## 49. Warnings / Intentional Limitations

Pytest reports two upstream deprecation warnings from FastAPI/Starlette TestClient integrations. The V1 rate limiter is process-local, legacy users without a password hash cannot log in, and email verification, password recovery, social login, distributed session caching, edge rate limiting, and RLS remain outside Phase 9. Developers must set their own non-placeholder `AUTH_JWT_SECRET`; the local `.env` was not altered automatically.

## 50. Confirmation No Financial Semantics Changed

Parser behavior, canonical signs, Decimal money handling, duplicate and import atomicity rules, categorization precedence, spending policy, currency separation, projection logic, and Phase 8 Groq grounding were not changed. Full financial regression suites passed.

## 51. Confirmation No Phase 10+ Features

No deployment, CI/CD deployment, custom domain, production reverse proxy, monitoring service, email verification/recovery, PWA/native app, new bank parser, CSV/XLSX import, or Gmail ingestion was implemented. Phase 10 has not started.

## 52. Confirmation No Commit / Push

No file was staged, committed, pushed, amended, rebased, or moved to another branch. Local `main` and `origin/main` remain at the frozen Phase 8 baseline commit; all Phase 9 changes are unstaged for review.
