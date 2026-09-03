# ADR 0002 — Use a Canonical Financial Import Boundary

Status: Accepted

## Context

FinSight begins with Yapı Kredi TLcard PDF statements but is expected to later support Ziraat, other bank PDFs, CSV, XLSX and Gmail attachment ingestion.

Different sources use different fields, layouts, signs, names and statement semantics.

If provider-specific formats enter the core financial model, every new bank would require changes throughout analytics and product code.

## Decision

Every supported financial source must be converted into provider-neutral import structures before entering FinSight Core.

Required conceptual flow:

```text
External Source
    ↓
Statement-Specific Parser
    ↓
ParsedStatement
    ↓
CanonicalTransaction[]
    ↓
FinSight Core
```

Bank-specific logic ends at the parser boundary.

## Consequences

Analytics, transactions and assistant modules must not branch on bank names.

Adding a second bank should primarily require a new parser, new parser fixtures and possibly new normalization rules.

It should not require bank-specific analytics code.

## Naming

Prefer statement-specific adapters such as:

```text
YapiKrediTLCardPDFParser
ZiraatBankkartPDFParser
```

rather than one oversized parser per institution.

## Validation rule

If a second bank cannot be added without changing core analytics for provider-specific reasons, this ADR has been violated or the canonical model is incomplete.
