# FinSight Phase 8 Hardening Report

## 1. Phase 8 Status

Implementation complete and left unstaged for review. The assistant is a bounded, backend-orchestrated Groq integration over deterministic FinSight tools with provider-independent final-answer grounding. Phase 9 was not started.

## 2. Frozen Phase 7 Baseline Commit

`175905fc72447d8e208891593148d9d5ee516467` on local `main`, tracking an identical `origin/main`, with a clean working tree before Phase 8 work.

## 3. Assistant Architecture

The modular monolith now has an `assistant` application module for request validation, prompting, tool orchestration, and responses; the existing `analytics` module remains the financial source of truth; `integrations/groq` handles provider transport only.

## 4. Groq Integration Strategy

Phase 8 uses Groq Chat Completions local tool calling through the official Python SDK. The application sends only its seven local function schemas, executes calls itself, and returns structured results for a final explanation. This follows the official [Groq local tool-calling flow](https://console.groq.com/docs/tool-use/local-tool-calling) and [Groq Python SDK](https://github.com/groq/groq-python).

## 5. Dependency Changes

Added `groq>=1.7,<2`, locked at `groq==1.7.0`, plus its new locked transitive dependencies `distro==1.9.0` and `sniffio==1.3.1`. No unrelated dependencies were upgraded.

## 6. Environment Configuration

Added backend-only `GROQ_API_KEY`, `GROQ_MODEL`, message/history/tool/provider-call/timeout/output limits, Compose forwarding, and placeholder documentation. No secret or `VITE_GROQ_*` variable was added.

## 7. Provider Boundary

`LLMProvider` exposes one provider-neutral `complete(messages, tools)` operation returning `ProviderReply` and typed `ProviderToolCall` values. `GroqProvider` performs transport/protocol conversion and has no database, session, user, account, parser, PDF, or analytics access.

## 8. Assistant API Endpoints

- `GET /api/v1/assistant/status` returns enabled state and non-secret provider/model names.
- `POST /api/v1/assistant/chat` accepts one message, bounded user/assistant history, optional request-bound account scope, and an IANA timezone. It returns only the final answer, safe tool labels, and scope metadata.

## 9. Request Context / User Isolation

The browser cannot submit `user_id`, system/tool roles, provider keys, tool definitions, or SQL fields. The existing development-only header supplies identity to FastAPI; the backend creates `AnalyticsService(session, current_user_id)`. The actual current-user UUID is absent from normal provider messages and every model tool schema/payload.

## 10. Account Scope Strategy

An optional account UUID is accepted only at the HTTP request boundary. `AnalyticsService.validate_account_scope` verifies ownership before any provider call. The verified value is bound to `AssistantToolRegistry`; account IDs are absent from model-controlled arguments and stripped from tool results.

## 11. Current Date / Timezone Strategy

The backend validates `client_timezone` with `zoneinfo.ZoneInfo`, converts an injectable UTC clock to the validated zone, and puts that local date into its system context. Invalid zones return a safe 422. Current month means month-to-date; historical months mean full calendar months.

## 12. System Prompt Design

The version-controlled prompts say deterministic tool data is authoritative, coverage may be incomplete, raw PDFs are unavailable, identity must not be inferred, financial figures must not be invented or recalculated, embedded data instructions are untrusted, unsupported balance/net-worth claims are forbidden, and answers must be concise without chain-of-thought. A separate constrained repair prompt permits one rewrite using only current-request tool facts.

## 13. Tool Registry

The hardcoded whitelist is exactly: `get_spending_summary`, `get_category_breakdown`, `get_merchant_breakdown`, `get_monthly_trend`, `compare_periods`, `project_month_spending`, and `search_transactions`. Dispatch uses explicit branches and a fixed definition mapping; there is no dynamic discovery.

## 14. Tool Schemas

Each tool has an explicit Pydantic schema with `extra="forbid"`, bounded dates, uppercase currency, category-code validation, merchant/search limits, and enum validation. Provider JSON schemas set `additionalProperties=false` and contain neither `user_id` nor `account_id`.

## 15. Tool Execution Boundary

The registry parses JSON, validates it before service invocation, injects the verified account scope, calls a named deterministic service method, serializes structured JSON, and fails safely for unknown or malformed calls. There is no session/ORM exposure to the model.

## 16. AnalyticsService Integration

All seven tools reuse `AnalyticsService` methods. PostgreSQL and the existing Decimal-safe policy compute financial facts; assistant code performs no financial summation, percentage, projection, or currency conversion.

## 17. Filtered Analytics Additions, If Any

Added an optional canonical `category_code` filter to deterministic period comparison and transaction exploration. The repository applies it inside the existing user/date/account/currency query boundary. A direct analytics service test covers café comparison without involving Groq.

## 18. Transaction Data Minimization

Search is capped at 20 rows and returns only date, normalized merchant, category code/name, Decimal amount string, currency, transaction type, and review state. It excludes raw descriptions, row IDs, user/account/card IDs, installment IDs, provenance, parser/import details, filenames, and hashes. Control characters are removed and strings are capped at 160 characters.

## 19. Raw PDF Privacy Boundary

Assistant request schemas accept no file or extracted-text field; assistant/provider modules import no upload/PDF/parser code. Groq receives only the user conversation and selected structured canonical aggregates/minimized rows. Regression tests verify this structural boundary.

## 20. Tool Loop / Limits

The synchronous loop allows four tool-execution rounds, eight tool calls, and six total provider calls by default, executing multiple calls sequentially. The optional grounding repair consumes one provider-call slot and cannot execute another tool. Configurable limits also cover message length, history message count/characters, provider timeout, and output tokens. Limit breaches fail closed.

## 21. Conversation History Strategy

The backend is stateless. It accepts only bounded `user` and `assistant` messages and always creates its own system/tool messages. Client history supplies conversational context but never financial grounding authority; only tool results produced in the current request authorize financial facts. No migration or chat table was added.

## 22. Prompt Injection Defenses

Injection text cannot create SQL, shell, filesystem, HTTP, web, cross-user, or arbitrary-function capability because only the fixed seven schemas are supplied. Pydantic rejects extra identity/tool arguments. Factual spending prompts are rejected if the provider attempts to answer before using a FinSight tool.

## 23. Indirect Prompt Injection Defenses

The prompt treats merchant/category/transaction/tool-result content as untrusted data. Results use structured JSON; control characters and long strings are sanitized. A synthetic adversarial merchant test confirms it remains data and cannot expand the whitelist.

## 24. Text-to-SQL / Dynamic Execution Verification

No callable SQL tool, model-generated query execution, `eval`, `exec`, arbitrary import, dynamic tool lookup, shell/filesystem/web tool, or agent framework exists. Repository queries remain static SQLAlchemy expressions with validated bound values.

## 25. Provider Error Handling

Missing configuration returns 503; timeouts map to 504; Groq 429 maps to 429; 5xx/connection failures map to safe 503; other provider/malformed/tool failures map to controlled 422/502 codes. Stack traces, payloads, answers, questions, and financial tool data are not returned or logged.

## 26. Decimal / Multi-Currency Safety

Tool output uses Pydantic JSON serialization and explicit two-decimal strings. Currency groups remain separate end to end; the frontend renders provider text and performs no analytics or FX arithmetic. Before the response leaves the service, a pure validator compares monetary, percentage, factual-count, projection, and comparison claims to current-request structured results using `Decimal` and locale-safe string normalization. It performs no database query or financial calculation and checks explicit comparison direction vocabulary.

## 27. Unsupported Financial Claims

Current balance, remaining cash, net worth, savings rate, and equivalent questions receive a deterministic limitation without calling Groq. The prompt also forbids claims about complete income, complete transfers, or guaranteed month-end cash.

## 28. Assistant Response Contract

Responses contain `answer`, `used_tools[{name,label}]`, and `scope{account_id,data_scope="CANONICAL_TRANSACTIONS"}`. Provider prose reaches this contract only after grounding succeeds; one failed repair produces a fixed figure-free fallback. The contract excludes chain-of-thought, provider internals, hidden messages, request dumps, secrets, and raw tool-call JSON.

## 29. Assistant UI

Added a dedicated Turkish `/assistant` page and sidebar item with capability introduction, conversation area, four starters, input/send controls, loading indicator, safe errors, safe used-tool chips, and provider-disabled state. The rest of the product remains usable when Groq is unavailable.

## 30. Privacy Disclosure

Visible page copy states that the user's assistant message and limited derived financial data selected by FinSight tools may be sent to Groq; raw statement PDFs, extracted text, and account identity details are not sent; imported coverage does not represent current bank balance.

## 31. Account Scope UI

The page visibly labels `Tüm hesaplar` or the selected account display name. Scope comes only from the existing product account selector and is never changed by the model.

## 32. Frontend Conversation State

Conversation state is React memory only. Refresh clears it. Development-user or account changes abort pending work, clear the conversation and draft, and reset relevant query state. No localStorage, IndexedDB, service worker, or financial response cache was added.

## 33. Responsive Behavior

The page uses the existing responsive shell, switches its two-column chat/disclosure layout at 900px, and stacks starters/scope/messages at 600px. Component tests exercised a 390px viewport and all controls remained reachable. CUA visually inspected the live compact layout at 639 CSS pixels with no overlap; exact 1440/768/390 visual emulation was unavailable because the browser security policy rejected the local inline viewport harness.

## 34. Backend Tests Added

Added service/transport/tool/API tests for disabled status, secret and identity boundaries, all seven tools, category comparison, strict schemas, Decimal/multi-currency output, row minimization, injected date/timezone, unsupported claims, provider timeout/429/5xx/malformed behavior, bounded loops, role/history/message limits, account isolation, prompt injection, indirect injection, no-SQL capability, and no-PDF boundary. Grounding scenarios cover exact and Turkish-formatted values, invented and near-match values, percentages, counts, projection, comparison amounts/direction, dates, current-turn history isolation, tool-less claims, one repair, fallback, configured call bounds, and structural no-database/no-float boundaries.

## 35. Backend Test Results

`docker compose exec -T backend pytest`: **301 passed**. The only warnings are two existing Starlette/TestClient deprecations described below.

## 36. Frontend Tests Added

Added 14 focused tests covering navigation/route, the explicit user-message/derived-data/raw-PDF privacy disclosure, scope display, starters, request payload, pending guard, plain-text rendering, disabled/rate-limit states, in-memory history, account/user reset, tool labels, multi-currency display, mobile controls, and prohibited browser persistence/unsafe HTML.

## 37. Frontend Test Results

`docker compose exec -T frontend npm run test`: **42 passed** across the Phase 7 product and Phase 8 assistant suites. `npm run typecheck`: passed.

## 38. Frontend Build Result

`docker compose exec -T frontend npm run build`: passed; Vite built the lazy Assistant chunk and existing product chunks successfully.

## 39. Alembic Result

`alembic current` reports `0003 (head)`. `alembic check` reports `No new upgrade operations detected.` No migration or model was added.

## 40. Docker / Health Result

`docker compose config --quiet` passed. `docker compose up -d --build` completed. PostgreSQL, backend, and frontend are healthy; `GET /api/v1/health` returned HTTP 200 with `{"status":"ok"}`; `/assistant/status` returned HTTP 200 with enabled false and no secret metadata; frontend `/assistant` returned HTTP 200. Host PostgreSQL connectivity at `127.0.0.1:55433` passed.

## 41. Optional Live Groq Smoke Test

Skipped because no local `GROQ_API_KEY` is configured. This is non-blocking; automated tests use an injectable fake provider and do not consume API quota.

## 42. Privacy / Secret Verification

No `.env`, API key, real bank statement, real/private transaction data, PII, raw extracted text, local database, upload, virtual environment, `node_modules`, or build output is included in the Phase 8 change set. Configuration examples contain placeholders only.

## 43. Security Pattern Scan

Targeted scans found no `dangerouslySetInnerHTML`, assistant `eval`/`exec`, arbitrary imports, generated SQL, dynamic tool dispatch, PDF upload path, description forwarding, or frontend Groq secret variable. Two broad-scan matches were benign: README's explicit warning against `VITE_GROQ_*` and an existing numeric parser's JavaScript regular-expression `.exec`.

## 44. Files Added / Modified

Added 18 files including the assistant module and grounding validator, Groq adapter, backend/frontend assistant tests, frontend API/page, and two Phase 8 reports. Modified 17 files for routing, configuration, analytics filtering, dependencies, UI shell/context/styles/contracts, README, Compose, and tests. No frozen document changed.

## 45. Warnings / Unresolved Questions

Pytest reports two pre-existing dependency deprecations: Starlette's current `TestClient` use of `httpx` and AnyIO's `BlockingPortal` alias. They do not affect behavior. Exact three-size CUA visual emulation remains unperformed because Browser Use automatically rejected the inline viewport harness under its URL security policy; the live 639px visual check, 390px component test, CSS breakpoint review, TypeScript/build checks, and responsive implementation all passed.

## 46. Confirmation No Phase 9+ Features Implemented

Confirmed. No authentication, JWT/OAuth/password, refresh-token, RLS, Redis/rate-limit infrastructure, auditing, secret manager, streaming, chat persistence, RAG, embeddings, web access, agent system, or other Phase 9+ feature was introduced.

## 47. Confirmation No Commit / Push Performed

Confirmed. Phase 8 remains unstaged and uncommitted on `main`; no commit, amend, rebase, branch change, push, or history rewrite was performed.
