# FinSight Phase 7 — Web Product UI Report

## 1. Phase 7 Status

Phase 7 is complete and ready for review. FinSight now has a coherent Turkish, responsive web product over the frozen Phase 0–6 backend. All Phase 7 changes remain uncommitted and unstaged.

## 2. Product Information Architecture

The product has three primary areas: **Genel bakış**, **İşlemler**, and **Hesap özetleri**. Their flow is account context → statement preview/confirmation → canonical analytics → transaction inspection/correction. Completed imports and saved classification rules reconnect those areas through authoritative server refetches.

## 3. Frontend Technical Architecture

React remains a presentation client. Typed API modules own HTTP contracts, TanStack Query owns server state, React Router owns durable routes, a small shared component set owns common states and controls, and presentation helpers format money/dates/category labels. Financial totals, duplicate semantics, classification precedence, comparisons, and projections remain backend responsibilities.

## 4. Dependencies Added

- `react-router-dom 7.18.3`: refresh-safe product routes and navigation.
- `@tanstack/react-query 5.102.8`: request lifecycle, scoped caches, invalidation, and one retry for transient network failures.
- `recharts 3.10.1`: accessible monthly trend rendering from backend buckets. The overview route is lazy-loaded, leaving the initial production chunk below the Vite warning threshold.
- `vitest 4.1.11`, `jsdom 29.1.1`, and Testing Library packages: focused component, accessibility-state, request, and interaction tests.

Exact versions are locked. No large component framework, Redux, or extra backend dependency was added.

## 5. Routing

Routes are `/overview`, `/transactions`, `/imports`, and `/imports/:id`, with `/` redirecting to `/overview` and a Turkish not-found view. Import batch IDs live in the URL, so persisted preview/completed views survive refresh.

## 6. Application Shell

Desktop uses a fixed-width left navigation and content workspace. Tablet/mobile use a compact header and expandable navigation. The shell includes a skip link, current-route state, development label, selected account, backend health state, and retry action. No assistant navigation was added.

## 7. Development User/Account Context

The UI explicitly labels `X-Dev-User-ID` as local development plumbing, not authentication. The UUID may come from `VITE_DEV_USER_ID` or the context form. Only that UUID is retained in session storage. Changing it cancels requests, clears the query cache, resets account/pagination state, and remounts route content. Owned accounts come from the new bounded account endpoint; no login or account CRUD was created.

## 8. Overview Page

The overview calls all six frozen Phase 6 analytics contracts and supports current month, previous month, and custom inclusive calendar dates. Requests occur on explicit apply actions. An independent as-of-date control refreshes the projection.

## 9. Spending Metric Presentation

Each backend currency group shows net spending, gross spending, refunds, financial fees, cash withdrawals, and expense/refund counts. Fees and cash withdrawals stay separate. Labels describe net as gross minus refunds; the UI never presents a misleading combined expense total.

## 10. Multi-Currency UI

TRY and USD were exercised together. Summary and comparison cards render separate currency groups. Category, merchant, and trend panels use an explicit currency selector. No mixed-currency sum, exchange rate, or implied comparability exists.

## 11. Category Visualization

A readable horizontal list/bar visualization shows exact backend net values, including negative categories and `OTHER`/Diğer. The bars use numeric conversion only for drawing length; exact decimal strings remain the labels and authority.

## 12. Trend Visualization

Recharts renders the backend's monthly buckets. A six-month range displayed all backend buckets, including zero months, at tablet and mobile widths. The chart exposes expandable exact text values and separates currencies through the selector.

## 13. Merchant Visualization

The first five backend-ranked merchants render with rank, transaction count, exact net amount, and an explicit note that top five does not equal the complete summary. Unknown merchants have a safe Turkish label. Empty merchant groups have a dedicated message.

## 14. Period Comparison UI

The selected and preceding equal-length ranges are explicit. Current, previous, absolute change, direction, and percentage are displayed directly from the backend. `PREVIOUS_ZERO`, `PREVIOUS_NEGATIVE`, and `BOTH_ZERO` are covered without `Infinity`, `NaN`, or invented percentages.

## 15. Projection UI

Projection displays observed net spending, elapsed/month days, backend average daily spending, and projected month spending. Copy labels it as an estimate based on constant spending pace and explicitly says it is not balance or remaining money.

## 16. Import Flow UI

The real flow is account selection → PDF picker → upload/preview → reconciliation → candidate review → duplicate choices → confirmation → completed actions. The picker states Yapı Kredi TLcard PDF support and the default 10 MiB limit while preserving backend validation authority. File state is cleared after submission and is never written to browser storage.

## 17. Duplicate Resolution UI

Only candidates currently flagged by the backend receive **İçe aktar**/**Atla** radios. Normal candidates display **Otomatik eklenecek** and cannot be skipped. Confirmation stays disabled until every current duplicate has a decision. Confirm-time duplicate changes clear stale decisions and refetch the persisted preview.

## 18. Confirmation UI

A synchronous guard plus disabled pending controls prevents double submission. Completed state uses backend imported/skipped counts and removes candidate controls. Successful confirmation invalidates import history, transactions, and analytics.

## 19. Import History

The Imports page reads bounded, reverse-chronological database history, 20 rows per request, with previous/next navigation. It shows only safe metadata and routes to known batch details. No local-storage history or completed candidate reconstruction exists.

## 20. Transactions Explorer

The explorer renders canonical rows only. Desktop uses a structured five-column layout; mobile collapses each record into a readable card. Each row shows date, normalized/unknown merchant, immutable raw description, type, category, review state, amount/currency, and explicit Giriş/Çıkış/Sıfır tutar text.

## 21. Filters / Pagination

Date, account, category, transaction type, review status, currency, and bounded merchant/description search map directly to backend parameters. Search waits for **Filtreleri uygula** rather than refetching per keystroke. Pagination requests 20 rows and uses backend `has_more`; a real next-page transition from records 1–20 to 21–34 was verified.

## 22. Classification Correction UI

A native modal dialog exposes normalized merchant and category edits while presenting raw description and amount read-only. `NEEDS_REVIEW` is visible in the list. The optional checkbox sends `persist_as_rule=true`. Cancellation sends no PATCH and no success message. A successful correction displays backend-refetched state; it never edits provenance.

## 23. Server-State / Refetch Strategy

Query keys include user, endpoint kind, account, filters, and offsets. Filter drafts do not affect queries until applied. Successful imports/corrections invalidate their affected authoritative queries. Context changes cancel active reads and clear all prior-user cache data. Ordinary API errors are not retried; one retry is allowed only for a transient browser `TypeError` network failure.

## 24. Money / Date Formatting

Money remains a string through the API and business flow. A string formatter preserves signs and cents even above `Number.MAX_SAFE_INTEGER`, using Turkish separators and an explicit currency. `Number` is used only for SVG/chart coordinates. ISO dates are formatted in UTC-safe Turkish labels; calendar shortcut and equal-length preceding-range functions have deterministic tests.

## 25. Error Handling

HTTP and known domain codes map to safe Turkish messages. Raw server details, PDF content, and parser errors are never printed. Network, 403, 404, conflict, oversize, unsupported-file, and validation states have retry or recovery paths. A known-batch conflict can link back to the existing import.

## 26. Empty / Loading States

Reusable skeletons have `role=status`; empty overview, transaction, import-history, category, merchant, and projection states avoid invented data and offer useful navigation where appropriate. Pending upload/confirmation/correction controls communicate progress and prevent repeats.

## 27. Accessibility

Implemented landmarks, one `h1` per page, semantic tables/lists/cards, labeled fields, explicit button names, status/alert regions, keyboard-native dialog escape/focus behavior, a skip link, visible focus, 42 px minimum controls, chart text equivalents, reduced-motion handling, and color-independent transaction direction labels.

## 28. Responsive Behavior

The running Docker app was inspected at 1440×1000, 768×1024, and 390×844. Overview cards/charts, import preview and duplicate decisions, transaction rows/filters, navigation, and correction dialog remained usable with no horizontal page overflow (`scrollWidth <= innerWidth`). Mobile charts retained labels and exact text disclosure. These checks used desktop-browser viewport emulation; native iPhone Safari was not claimed.

## 29. Backend Endpoints Added, If Any

- `GET /api/v1/accounts`: current development user's accounts; limit 1–100 (default 50), offset 0–100000; safe account display fields only.
- `GET /api/v1/imports`: current user's import metadata; optional owned account filter; limit 1–100 (default 20), offset 0–100000.

Both enforce development context, owner scope, indistinguishable missing/foreign account handling, stable bounded ordering, and explicit selected columns. Neither exposes masked/full identifiers, filename/hash, parser internals, candidates, descriptions, or raw document material. No schema/model/migration changed.

## 30. Backend Test Results

`docker compose exec -T backend pytest`: **226 passed**, including 14 new account/import-history ownership, pagination, bounds, safe-contract, and development-context cases. `ruff check .`: passed. `ruff format --check .`: 135 files already formatted. `alembic current`: `0003 (head)`. `alembic check`: no new upgrade operations.

## 31. Frontend Tests

`docker compose exec -T frontend npm run test`: **28 passed** in one suite. Coverage includes exact large decimals, deterministic calendar ranges, custom apply behavior, multi-currency metrics, chart/presentation states, all percentage states, loading/empty/errors, upload clearing, reconciliation, normal/duplicate candidates, validation blocking, completed counts, double-confirm protection, conflict refetch, backend filters/offsets, correction payload/provenance/invalidation/cancel behavior, user cache isolation, health retry, and mobile-navigation state.

## 32. Frontend Build Result

`npm run build` runs TypeScript `tsc --noEmit` and Vite production build. It passed. The generated chunks were approximately 296 kB initial JavaScript and 325 kB lazy overview JavaScript (about 93 kB and 96 kB gzip), with no chunk-size warning. Build output remains ignored/untracked.

## 33. Docker / Health Result

`docker compose config --quiet` passed. `docker compose up -d --build` rebuilt both application images. PostgreSQL, backend, and frontend became healthy. `GET http://127.0.0.1:8000/api/v1/health` returned HTTP 200 with `{"status":"ok"}`. The frontend was reachable at `http://localhost:5173`. PostgreSQL remained localhost-only at `127.0.0.1:55433 → 5432`.

## 34. Synthetic End-to-End Product Flow

A disposable synthetic user with TRY and USD accounts was used. The browser displayed separate currency analytics, uploaded a synthetic TLcard PDF, reconciled `1,340.00 TRY`, showed three normal candidates without skip controls, and confirmed three canonical rows. A byte-distinct statement with the same three transactions exposed three duplicate decisions, blocked confirmation until all were resolved, then reported zero imported/three skipped. The explorer found the imported row, saved merchant/category correction plus a future rule, and overview refetch moved the exact amount into the updated category/merchant aggregates. A later-date synthetic statement imported three new rows; its matching merchant automatically inherited the saved normalized merchant and category while preserving the raw description. The disposable database user, two accounts, 58 total synthetic transactions, three import batches, and cascading rules/staging data were deleted after verification; the user row count was confirmed as zero.

## 35. Privacy Verification

Only generated synthetic descriptions, reserved `.invalid` identity data, and disposable UUIDs were used. The user's real PDF was not opened, uploaded, copied, logged, screenshotted, or persisted. Repository scans found no `.env`, credentials, personal identity, real statements, private financial data, local databases, temporary uploads, or account/card identifiers in Phase 7 changes. Test contracts use synthetic sentinels specifically to verify that private filename/hash fields are absent.

## 36. Files Added / Modified

There are **29 added or modified files**. Modified: `.env.example`, `README.md`, `backend/app/api/v1/router.py`, `docker-compose.yml`, `frontend/index.html`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/App.tsx`, `frontend/src/api/client.ts`, and `frontend/src/styles.css`.

Added: `backend/app/modules/accounts/routes.py`, `backend/app/modules/imports/history.py`, `backend/tests/test_product_reads.py`, five typed frontend API modules, shared UI components, development context hook, Overview/Transactions/Imports pages, contract types, presentation helpers, Vitest setup/configuration and product tests, plus this report.

## 37. Warnings / Unresolved Questions

The backend test run reports two upstream deprecation warnings from Starlette TestClient/httpx and AnyIO's `BlockingPortal` alias; they do not affect behavior and no dependency upgrade was introduced solely to silence them. Browser acceptance used responsive emulation rather than native Safari. Synthetic PDF helper artifacts were created only outside the repository; automated shell cleanup of that external directory was blocked by the host policy, so `C:\codex\phase7-synthetic-acceptance` may be removed manually if still present. No functional Phase 7 blocker remains.

## 38. Confirmation No Phase 8+ Features Implemented

Confirmed. There is no Groq/LLM integration, assistant/chat UI, tool calling, natural-language query, Text-to-SQL, RAG, embeddings, authentication/JWT/OAuth, service worker, offline financial cache, or background infrastructure.

## 39. Confirmation No Commit / Push Performed

Confirmed. Branch remains `main`, tracking `origin/main`; local HEAD and the live remote remain the frozen Phase 6 commit `646632dbf757cdb052e083ef3cba1ab563ba644f`. There are no staged changes. No commit, push, amend, rebase, branch change, or history rewrite was performed.
