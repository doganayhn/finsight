# ADR 0004 — Start With Real Yapı Kredi PDF Data

Status: Accepted

## Context

FinSight needs a realistic first financial data source.

Direct banking APIs/Open Banking are not appropriate for the initial portfolio implementation because they introduce access, contractual, regulatory and operational dependencies.

Synthetic/mock banking APIs would prove integration mechanics but not prove that FinSight can handle real Turkish financial statement data.

A real Yapı Kredi TLcard monthly e-statement is available as a repeatable monthly source.

## Decision

V1 begins with manually uploaded Yapı Kredi TLcard PDF statements.

The first import adapter is:

```text
YapiKrediTLCardPDFParser
```

The product remains bank-agnostic through the canonical import boundary.

## Reasons

- real Turkish financial data format
- repeatable monthly source
- no dependency on banking API access
- meaningful parser/normalization problems
- strong portfolio evidence
- immediate validation against statement totals

## Consequences

V1 product claims are limited to what this statement source actually supports.

The initial statement is primarily a spending/card activity source and must not be treated as a complete account ledger.

Questions requiring complete income, balance or transfer history must be bounded or rejected when the imported data cannot support them.

## Future

Planned extensions:

- second real bank PDF adapter
- CSV/XLSX
- Gmail attachment ingestion

These extensions must reuse the existing import core.
