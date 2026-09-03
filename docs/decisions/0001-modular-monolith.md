# ADR 0001 — Use an API-First Modular Monolith

Status: Accepted

## Context

FinSight is initially developed by a single developer and must support a React web client, future SwiftUI iOS client, bank statement imports, financial analytics and AI-assisted querying.

The project needs clean domain boundaries, but it does not currently need distributed deployment.

## Decision

Use a single FastAPI backend organized as a modular monolith.

Expose stable versioned REST APIs under:

```text
/api/v1/*
```

The React application is a client of this API. Future iOS applications will use the same API.

## Reasons

- simpler local development
- lower operational complexity
- easier debugging
- easier transaction management
- appropriate scale for a single developer
- domain boundaries can still remain explicit
- modules can be extracted later only if a real scaling reason appears

## Rejected alternative

Microservices in V1.

Reasons for rejection:

- unnecessary network boundaries
- duplicated infrastructure
- deployment complexity
- distributed data consistency problems
- little benefit for the current scale

## Consequences

The codebase must actively preserve module boundaries.

A modular monolith is not permission to create one global service layer with tightly coupled modules.
