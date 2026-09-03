# FinSight Engineering Instructions

This repository is developed incrementally in numbered phases.

These instructions are the engineering contract for all coding agents working on FinSight.

## Required reading before making changes

Before modifying the repository:

1. Read `AGENTS.md`.
2. Read `docs/ARCHITECTURE.md`.
3. Read `docs/DOMAIN_RULES.md`.
4. Read `docs/IMPORT_ARCHITECTURE.md`.
5. Read `docs/ROADMAP.md`.
6. Read relevant ADRs under `docs/decisions/`.
7. Implement only the phase explicitly requested by the user.

If repository code and these documents conflict, stop and report the conflict before introducing a new architecture.

## Project identity

FinSight is a bank-agnostic personal spending intelligence platform.

The initial implementation uses real Turkish bank statement data, starting with manually uploaded Yapı Kredi TLcard monthly e-statement PDFs.

This starting point must never turn the core architecture into a Yapı Kredi-specific product.

Future data sources may include:

- Ziraat statement PDFs
- other Turkish bank PDFs
- CSV
- XLSX
- Gmail attachment ingestion
- future additional providers

A future native iOS client is planned. The backend must therefore remain API-first and presentation-independent.

## Non-negotiable architecture rules

- Use an API-first modular monolith.
- Do not introduce microservices in V1.
- Do not put financial business logic in React.
- Bank-specific logic must remain inside parser/adapter modules.
- PostgreSQL stores the canonical financial model.
- API routes must be versioned under `/api/v1`.
- Financial calculations must be deterministic and implemented outside the LLM.
- The LLM is never the financial source of truth.
- Do not send raw bank statement PDFs to the LLM.
- Do not allow the LLM to choose or override the authenticated `user_id`.
- Do not implement arbitrary LLM-generated SQL in V1.
- Do not introduce Redis, Celery, Kafka, pgvector, Kubernetes or similar infrastructure without an explicit requirement.
- Prefer clear, testable code over premature abstraction.
- Do not implement future-phase features early.

## Money rules

- Python monetary values: `Decimal`
- PostgreSQL monetary values: `NUMERIC(18,2)` unless a later ADR explicitly changes this.
- Never use binary floating point for authoritative financial amounts.
- Currency must be explicit.
- V1 analytics must not silently aggregate different currencies.

## Canonical transaction sign convention

Amounts are stored from the account's perspective:

- Money entering the account: positive.
- Money leaving the account: negative.

Examples:

- Salary: `+50000.00`
- Grocery purchase: `-1250.00`
- Refund: `+1250.00`
- Outgoing transfer: negative
- Incoming transfer: positive

A parser may receive statements that display expenses as positive numbers. The parser/normalization boundary must convert these into the FinSight canonical sign convention.

## Financial semantics

At minimum, the canonical domain must support the concepts defined in `docs/DOMAIN_RULES.md`.

Important invariants:

- Transfer is not expense.
- Refund is not income.
- Credit-card payment must not cause spending to be counted twice.
- Installment cash-flow impact and original purchase value are different concepts.
- Account balance and available credit are different concepts.
- Statement period and calendar month are different concepts.

## Import rules

Bank-specific parsing must terminate at the canonical import boundary.

Required shape:

```text
Source
  ↓
Parser
  ↓
ParsedStatement
  ↓
CanonicalTransaction[]
  ↓
Validation
  ↓
Normalization
  ↓
Import Preview
  ↓
User Confirmation
  ↓
Persistence
```

The core transaction, analytics and assistant modules must not contain bank-specific conditionals such as:

```python
if bank == "YapiKredi":
    ...
elif bank == "Ziraat":
    ...
```

Bank-specific code belongs inside parser/adapter modules.

## Privacy rules

- Store only data needed by FinSight.
- Do not persist customer name, address, full account number, full card number or unrelated personal information from statement PDFs.
- Raw uploaded financial documents should be temporary by default.
- Keep provenance metadata needed for debugging and idempotency.
- Do not send raw statements or unnecessary transaction-level data to cloud LLM providers.
- Hosted demo environments must not encourage use of real sensitive banking data.

## AI rules

V1 LLM provider: Groq.

The assistant may:

- understand user intent
- choose approved application tools
- extract structured parameters
- explain deterministic backend results

The assistant may not:

- calculate authoritative financial totals itself
- bypass user isolation
- directly access arbitrary database tables
- run arbitrary generated SQL in V1
- receive raw bank statements
- invent financial data when the required source data is unavailable

If the dataset cannot answer a question, the application must say so.

## Engineering workflow

For every phase:

1. Inspect the current repository.
2. Read the required documentation.
3. Provide a concise implementation plan.
4. Implement only the requested phase.
5. Run relevant tests, type checks and build checks.
6. Fix failures caused by the changes.
7. Report:
   - files created/modified
   - architectural decisions made
   - commands executed
   - test/build results
   - unresolved issues
8. Do not claim completion if the relevant checks were not run.

## Change discipline

Do not silently change frozen architecture.

If a requested implementation reveals that a documented architecture decision is invalid:

1. explain the conflict
2. propose the smallest change
3. update or add an ADR only after approval
4. then implement the change

Do not rewrite unrelated modules while completing a phase.

## V1 exclusions

Unless explicitly promoted by a later approved phase, V1 excludes:

- Open Banking
- Gmail automatic ingestion
- CSV/XLSX ingestion
- native iOS
- native Android
- RAG
- arbitrary Text-to-SQL
- multi-agent architecture
- large local LLM hosting
- microservices
- Redis/Celery/Kafka
- advanced ML categorization
- production banking integrations

The architecture must allow these to be added later without rewriting the core.
