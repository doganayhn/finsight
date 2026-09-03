# FinSight Architecture

Status: **Frozen baseline for V1**

This document defines the high-level software architecture of FinSight.

## 1. Product definition

FinSight is a bank-agnostic personal spending intelligence platform.

It imports financial statement data, converts provider-specific records into a canonical financial model, analyzes spending deterministically, and provides a natural-language assistant on top of approved analytics tools.

V1 focuses on **spending intelligence**, not complete personal financial position.

The first supported real-world source is:

> Yapı Kredi TLcard monthly e-statement PDF, manually uploaded through the web application.

This is an implementation starting point only. FinSight Core must remain independent from Yapı Kredi and from PDF as a format.

## 2. Architectural goals

FinSight should be:

- API-first
- modular
- bank-agnostic
- deterministic for financial calculations
- privacy-aware
- testable
- ready for future iOS consumption
- extensible to new statement formats and ingestion sources

The application should not become distributed before there is a real operational reason.

## 3. Architectural style

V1 uses a **modular monolith**.

```text
                CLIENTS

        React Web Application
                 │
          Future SwiftUI iOS
                 │
                 ▼
             REST / JSON
             /api/v1/*
                 │
                 ▼
        ┌───────────────────┐
        │      FastAPI      │
        │ Modular Monolith  │
        └─────────┬─────────┘
                  │
      ┌───────────┼────────────┐
      │           │            │
      ▼           ▼            ▼
   Imports    Financial     Assistant
              Domain
      │           │            │
      │       Analytics       Groq
      │           │            │
      └───────────┼────────────┘
                  ▼
              PostgreSQL
```

Microservices are intentionally excluded from V1.

See: `docs/decisions/0001-modular-monolith.md`.

## 4. Technology stack

### Backend

- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic
- PostgreSQL
- Alembic
- pytest

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- Recharts when charts are introduced

### AI

- Groq API in V1
- provider abstraction maintained for possible future providers

### Infrastructure

- Docker
- Docker Compose

## 5. Main backend modules

Expected modular structure:

```text
backend/app/

core/
db/
shared/

modules/
    auth/
    accounts/
    imports/
    transactions/
    merchants/
    categories/
    analytics/
    forecast/
    assistant/
```

Modules may contain their own schemas, services, repositories, routes, tests and domain helpers.

Avoid a large global `services.py` or `utils.py` containing unrelated logic.

## 6. Core data flow

```text
Financial Data Source
        │
        ▼
Import Gateway
        │
        ▼
Parser Registry
        │
        ▼
Statement-Specific Parser
        │
        ▼
ParsedStatement
        │
        ▼
CanonicalTransaction[]
        │
        ├──────────────┐
        ▼              ▼
   Validation     Normalization
        │              │
        └───────┬──────┘
                ▼
          Import Preview
                │
        User Confirmation
                │
                ▼
           PostgreSQL
                │
      ┌─────────┴──────────┐
      ▼                    ▼
Analytics Engine      AI Assistant
      │                    │
      └─────────┬──────────┘
                ▼
             Client
```

## 7. Canonical boundary

Provider-specific data must not propagate into FinSight Core.

Example:

```text
Yapı Kredi PDF
      ↓
YapiKrediTLCardPDFParser
      ↓
ParsedStatement
      ↓
CanonicalTransaction[]
```

A future source:

```text
Ziraat PDF
      ↓
ZiraatBankkartPDFParser
      ↓
ParsedStatement
      ↓
CanonicalTransaction[]
```

From the canonical boundary onward, analytics code must not care which bank produced the data.

See: `docs/decisions/0002-canonical-financial-boundary.md`.

## 8. Future ingestion architecture

The system separates **source**, **file format**, and **parser**.

### Source

How data reached FinSight:

- `MANUAL_UPLOAD`
- `GMAIL`
- future providers

### File format

- `PDF`
- `CSV`
- `XLSX`

### Parser

- `YAPIKREDI_TLCARD_PDF`
- future `ZIRAAT_BANKKART_PDF`
- future `GENERIC_CSV`
- future `GENERIC_XLSX`

This distinction allows future Gmail support to reuse an existing parser:

```text
Gmail
  ↓
PDF attachment
  ↓
YapiKrediTLCardPDFParser
  ↓
CanonicalTransaction[]
```

Gmail is an ingestion source, not a financial parser.

## 9. Persistence principles

PostgreSQL is the canonical system of record.

Core V1 entities are expected to include:

- users
- accounts
- import_batches
- transactions
- categories
- merchant_aliases
- user_merchant_rules
- transaction_links
- conversations
- messages

Exact schema is implemented in the database phase and must remain consistent with `docs/DOMAIN_RULES.md`.

## 10. Transaction linking

Pairwise transaction relationships must not be represented only by booleans.

A `transaction_links` concept is planned for relationships such as:

- `TRANSFER_PAIR`
- `CARD_PAYMENT_PAIR`
- `REFUND_OF`

Installment grouping should not be forced into the same pairwise link model.

Installments use their own nullable plan/group metadata.

## 11. Installments

The architecture must preserve the distinction between monthly cash-flow impact and original purchase value.

Example:

```text
Original purchase: 30,000 TRY
Installments: 6
Monthly statement cash-flow impact: 5,000 TRY
```

Monthly spending analytics must not replace each installment with the original 30,000 TRY purchase value.

## 12. Analytics architecture

All authoritative financial calculations belong in the backend.

Examples:

- monthly spending
- merchant spending
- category breakdown
- period comparison
- net spending
- simple spending projection

The frontend renders results.

The LLM interprets and explains results.

The LLM does not calculate official figures.

## 13. AI architecture

V1 uses Groq through a provider abstraction.

```text
AssistantService
      │
      ▼
LLMProvider
      │
      ▼
GroqProvider
```

Preferred V1 pattern:

```text
User Question
     ↓
Groq
     ↓
Structured Intent / Tool Selection
     ↓
Approved Backend Tool
     ↓
Analytics Service
     ↓
PostgreSQL
     ↓
Structured Result
     ↓
Natural-language Response
```

Arbitrary Text-to-SQL is excluded from V1.

See: `docs/decisions/0003-llm-is-not-financial-truth.md`.

## 14. Frontend architecture

React is a presentation client.

React must not own:

- transaction normalization
- category totals
- financial projections
- currency aggregation rules
- transfer/refund semantics
- authoritative period comparison logic

The backend exposes stable versioned APIs.

This allows future SwiftUI clients to consume the same backend.

## 15. API conventions

All public V1 application routes use:

```text
/api/v1/*
```

Examples:

```text
/api/v1/health
/api/v1/imports
/api/v1/accounts
/api/v1/transactions
/api/v1/analytics
/api/v1/assistant
```

## 16. Security architecture

V1 must include:

- authenticated user context before multi-user financial data is exposed
- user-scoped repository/service access
- upload validation
- secret management through environment variables
- no API keys in browser code
- no raw statements sent to Groq
- privacy-oriented raw file handling
- adversarial tests for AI tool scope

PostgreSQL Row Level Security may be added as defense-in-depth, but application-layer user scoping remains mandatory.

## 17. iOS readiness

The backend must not assume a browser client.

Business logic remains server-side.

Future iOS architecture:

```text
SwiftUI
   ↓
REST API
   ↓
FastAPI
   ↓
FinSight Core
```

## 18. Explicit V1 non-goals

V1 is not:

- an Open Banking client
- a complete bank account aggregator
- a payment initiation system
- a credit scoring system
- a financial advisor
- a native mobile app
- a RAG system
- a Text-to-SQL demo
- a microservice platform

V1 is a real-data spending intelligence product with a clean path to future expansion.
