# FinSight Development Roadmap

Status: **Frozen phase plan for V1**

The project is implemented incrementally.

A later phase must not begin until the current phase has been tested and reviewed.

Coding agents must not implement future phases early.

## Phase 0 — Documentation Freeze

Goal: create and agree on the engineering source-of-truth documents.

Required documents:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DOMAIN_RULES.md`
- `docs/IMPORT_ARCHITECTURE.md`
- `docs/ROADMAP.md`
- ADRs under `docs/decisions/`

Completion criteria:

- architecture contradictions resolved
- V1 scope frozen
- future features clearly marked as future

## Phase 1 — Project Foundation

Goal: create the development environment and base monorepo.

Implement:

- FastAPI backend
- React + TypeScript + Vite frontend
- Tailwind CSS
- PostgreSQL
- Docker / Docker Compose
- configuration through environment variables
- Alembic baseline
- pytest baseline
- `/api/v1/health`
- minimal frontend showing backend connectivity
- base repository structure

Do not implement financial models, PDF parsing, AI, authentication or analytics.

Acceptance:

```text
docker compose up --build
```

starts PostgreSQL, FastAPI and React.

`GET /api/v1/health` returns HTTP 200 with:

```json
{
  "status": "ok"
}
```

## Phase 2 — Financial Domain and Database

Goal: create the core canonical persistence model.

Expected entities:

- users
- accounts
- import_batches
- transactions
- categories
- merchant_aliases
- user_merchant_rules
- transaction_links

AI conversation tables may be deferred until the assistant phase if cleaner.

Implement domain enums and constraints based on `DOMAIN_RULES.md`.

Important concerns:

- Decimal / NUMERIC money
- explicit currency
- canonical signed amounts
- transaction semantic type
- installment metadata
- category provenance/review status
- parser provenance
- transaction links
- timestamps/timezone policy
- migrations
- model/repository tests

Do not implement the Yapı Kredi parser yet.

## Phase 3 — Yapı Kredi TLcard PDF Parser

Goal: parse the first real Turkish statement source.

Input:

```text
Yapı Kredi TLcard monthly e-statement PDF
```

Implement:

- safe PDF text extraction
- statement recognition
- statement period extraction
- reported purchase total extraction
- transaction row extraction
- Turkish date parsing
- Turkish money parsing
- `ParsedStatement`
- `CanonicalTransaction` candidates
- parser name/version
- parser-specific validation
- sanitized/synthetic test fixtures modeled on the real format

Critical acceptance:

```text
reported_total == parsed qualifying transaction total
```

for known valid fixtures.

Do not persist transactions directly from the parser.

## Phase 4 — Import Pipeline

Goal: create the complete upload-to-database workflow.

Implement:

- upload endpoint
- file validation
- temporary storage/lifecycle
- file hash
- parser registry
- import batch creation
- parse
- validate
- duplicate detection
- preview
- confirm
- commit
- failure/review states
- relevant tests

Expected flow:

```text
Upload
  ↓
Detected Yapı Kredi TLcard
  ↓
Preview
  ↓
Validation
  ↓
Confirm
  ↓
Imported
```

## Phase 5 — Merchant Normalization and Categories

Goal: turn raw transaction descriptions into useful spending semantics.

Implement:

- category seed data
- merchant alias rules
- deterministic normalization
- Turkish merchant examples
- user-specific merchant/category override
- review status
- category provenance
- correction persistence

Initial precedence:

```text
User override
    ↓
Merchant alias
    ↓
Deterministic rules
    ↓
Needs review / Other
```

Do not use LLM-per-transaction categorization or advanced ML yet.

## Phase 6 — Analytics Engine

Goal: produce authoritative spending analytics without AI.

Implement backend services/endpoints for:

- period total spending
- category breakdown
- merchant breakdown
- top merchants
- transaction search/filtering
- period comparison
- monthly trend
- simple spending projection
- explicit handling of unsupported/incomplete-data questions
- multi-currency-safe result behavior

Important:

- analytics use canonical transactions
- transfers/refunds/card payments follow domain rules
- no authoritative calculation in frontend
- no LLM dependency

The system must produce correct results even if AI is disabled.

## Phase 7 — Web Product UI

Goal: build the real user-facing web experience.

Implement:

- responsive layout
- import flow UI
- import preview
- account/source context
- dashboard
- spending cards
- category breakdown
- merchant breakdown
- trend charts
- transaction explorer
- review/correction UI
- mobile-friendly behavior for iPhone Safari

Business logic remains in backend.

## Phase 8 — Groq AI Assistant

Goal: add natural-language financial querying on top of approved deterministic tools.

Implement:

- `LLMProvider` abstraction
- `GroqProvider`
- structured output / tool selection
- approved assistant tools
- assistant service
- assistant API
- conversation UI
- bounded answers for incomplete datasets
- minimal necessary data sent to Groq
- no raw statement PDF sent to Groq

Expected flow:

```text
User question
    ↓
Groq
    ↓
Structured tool request
    ↓
Backend analytics tool
    ↓
Deterministic result
    ↓
Answer
```

Explicitly excluded:

- arbitrary Text-to-SQL
- RAG
- multi-agent systems

## Phase 9 — Security and Reliability

Goal: harden the application before treating V1 as complete.

Implement/review:

- authentication
- authorization
- user-scoped repositories/services
- account ownership checks
- secret handling
- upload limits
- invalid/malicious files
- duplicate/idempotency tests
- cross-user access tests
- prompt injection/adversarial tool tests
- data deletion behavior
- raw upload cleanup
- error handling
- logging without leaking sensitive financial data

Evaluate PostgreSQL RLS as defense-in-depth if it fits cleanly.

## Phase 10 — Product Polish, Evaluation and Deployment

Goal: prepare a portfolio-quality V1.

Implement:

- complete responsive polish
- iPhone Safari testing
- empty/loading/error states
- realistic sanitized demo data
- backend test suite cleanup
- frontend type/build checks
- AI evaluation set
- import/parser regression fixtures
- architecture documentation
- README
- screenshots/demo material
- deployment configuration
- hosted-demo privacy warning

V1 is frozen after this phase.

## V1.1 — Second Bank Adapter

Preferred first extension:

```text
Ziraat Bankkart PDF
```

Goal: prove that the canonical architecture supports a second real Turkish bank format.

Add:

```text
ZiraatBankkartPDFParser
```

Core analytics should require no Ziraat-specific branches.

## V1.2 — CSV / XLSX

Add structured import providers:

- Generic CSV
- Generic XLSX

Both must produce the existing canonical import model.

Potential work:

- delimiter detection
- encoding support
- column mapping
- manual mapping UI
- structured import validation

## V2 — Gmail Attachment Ingestion

Goal: automate the manual V1 workflow.

Expected flow:

```text
Gmail
  ↓
Relevant statement email
  ↓
Attachment
  ↓
Existing parser registry
```

Gmail must not duplicate parsing logic.

## Future

Possible later work:

- more bank statement adapters
- richer account-ledger sources
- balance snapshots
- advanced recurring-payment detection
- small ML transaction classifier
- local LLM/Ollama provider
- native SwiftUI iOS app
- Open Banking if access/regulatory conditions make sense
- RAG only if document-question use cases genuinely emerge
- guarded ad-hoc querying only after security justification

None of these are V1 requirements.
