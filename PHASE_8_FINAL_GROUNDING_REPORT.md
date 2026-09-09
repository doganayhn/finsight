# FinSight Phase 8 Final-Grounding Hardening Report

## 1. Previous Residual Hallucination Risk

A provider could previously call a correct deterministic tool and still introduce an unsupported financial figure in its final prose. That response would have reached the API unchanged.

## 2. Final Answer Grounding Architecture

Added a provider-independent validator in the assistant module after the final provider response and before `AssistantChatResponse`. Groq transport remains unchanged and contains no grounding logic.

## 3. Authoritative Fact Source

The service retains sanitized structured JSON from tools executed in the current request. Only those results and validated local/tool date context authorize financial claims; the public response contract is unchanged.

## 4. Numeric Normalization Strategy

Money claims are parsed from strings with `Decimal`. Equivalent forms such as `9324.79`, `9.324,79`, `₺9.324,79`, `9.324,79 TL`, and `9.324,79 TRY` compare exactly. Rounding, nearby values, and unsupported sums fail.

## 5. Percentage Grounding

Explicit `%`, `yüzde`, `percent`, and rate wording must match an exact current-result `percentage_change` value.

## 6. Projection Grounding

Projection prose may use only monetary values already present in the current projection result. The validator never recomputes or extrapolates a projection.

## 7. Comparison Direction Grounding

For an unambiguous current-result direction, the validator rejects the opposite Turkish/English increase, decrease, or unchanged vocabulary.

## 8. Current-Turn vs History Authority

Client-provided history remains conversational context only. Tests prove an old history amount cannot authorize a response and a conflicting current tool result takes precedence.

## 9. Repair / Fail-Closed Behavior

An ungrounded answer receives at most one constrained rewrite request using the same tool messages. The repair consumes `ASSISTANT_MAX_PROVIDER_CALLS`, cannot execute another tool, and is validated again. Exhausted bounds, provider failure, malformed output, a tool request, or a second grounding failure returns a fixed figure-free Turkish fallback.

## 10. Tool-less Response Safety

Product help without financial figures remains available. The existing factual-tool guard remains active, and the grounding validator rejects a user-specific monetary claim when no current tool result exists.

## 11. Privacy Disclosure Change

The Turkish UI now states that the user's assistant message and limited derived financial data may be sent to Groq. It separately states that raw statement PDFs, extracted PDF text, and account identity details are not sent. README matches this behavior.

## 12. Backend Tests Added/Changed

Added 31 grounding scenarios covering exact and locale-formatted money, near/invented values, percentages, factual counts, projection, comparison values/direction, ordinary dates and day counts, history isolation, tool-less behavior, repair success/failure/bounds, no derived sums, and structural database/analytics/binary-number isolation. Existing assistant injection and tool-boundary tests remain active.

## 13. Backend Test Result

`docker compose exec -T backend pytest`: **301 passed**, with two existing dependency deprecation warnings. `ruff check .` and `ruff format --check .` passed.

## 14. Frontend Test Result

`docker compose exec -T frontend npm run test`: **42 passed**, including the three-part privacy disclosure assertion.

## 15. Build / Typecheck Result

`npm run typecheck` passed. `npm run build` passed with 658 modules transformed.

## 16. Alembic Result

`alembic current` reports `0003 (head)`. `alembic check` reports no new upgrade operations.

## 17. Docker / Health Result

`docker compose config --quiet` and `docker compose up -d --build` passed. PostgreSQL, backend, and frontend are healthy. Health returned HTTP 200 with `{"status":"ok"}`; assistant status returned HTTP 200 with the feature disabled because no local Groq key is configured. PostgreSQL connectivity returned `1`.

## 18. Security Regression Scan

Generated model tool schemas contain no `user_id` or `account_id`. The whitelist still has seven tools with explicit dispatch and no SQL capability. Assistant/provider scans found no PDF/upload access, generated SQL, browser secret, unsafe HTML, or persistence; minimized transaction results still strip `description_raw`. No live Groq quota was used.

## 19. Files Modified

Hardening added `backend/app/modules/assistant/grounding.py`, `backend/tests/test_assistant_grounding.py`, and this report. It updated assistant orchestration/prompts, backend limits, `.env.example`, Compose, README, the visible assistant disclosure/test, and the main Phase 8 report.

## 20. Confirmation No Database/Domain Expansion

Confirmed. No migration, ORM/domain model, analytics calculation, canonical financial rule, provider, or public API contract was added or changed by this hardening.

## 21. Confirmation No Sensitive Data Added

Confirmed. Sensitive-file and changed-content scans found no real statement, personal financial data, PII, secret, credential, raw extracted statement text, local database, upload, virtual environment, dependency directory, or build artifact in the change set.

## 22. Confirmation No Phase 9+ Work

Confirmed. No production authentication, token/session system, RLS, rate-limit infrastructure, audit platform, chat persistence, RAG, embeddings, streaming, or other Phase 9 feature was introduced.

## 23. Confirmation No Commit/Push

Confirmed. All Phase 8 work remains unstaged and uncommitted on `main`; no commit, push, amend, rebase, or history rewrite was performed.
