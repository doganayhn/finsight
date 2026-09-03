# ADR 0003 — The LLM Is Not the Financial Source of Truth

Status: Accepted

## Context

FinSight includes a natural-language assistant.

Large language models are useful for intent understanding, natural language, tool selection and explanation.

They are not appropriate as the authoritative system for exact financial calculations or user-data authorization.

## Decision

Authoritative financial results are produced by deterministic backend services and database queries.

The LLM may:

- parse user intent
- choose from approved tools
- provide structured parameters
- explain deterministic results

The LLM may not:

- calculate official totals
- calculate authoritative percentages
- choose the authenticated user identity
- bypass account ownership
- receive raw statement PDFs
- execute arbitrary SQL in V1

## V1 provider

Groq is the first cloud LLM provider.

The assistant uses an `LLMProvider` abstraction so the rest of the system does not depend directly on Groq.

## V1 interaction pattern

```text
User Question
    ↓
Groq
    ↓
Structured Tool Request
    ↓
Backend Tool / Analytics Service
    ↓
PostgreSQL
    ↓
Structured Result
    ↓
Response
```

## Rejected V1 approach

Arbitrary Text-to-SQL.

Reason: the security and correctness cost is unnecessary for V1 when approved analytics tools can cover the target product experience.

Text-to-SQL may be reconsidered later with a separate security review.
