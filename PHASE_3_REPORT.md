# FinSight Phase 3 — Yapı Kredi TLcard PDF Parser

Date: 2026-09-04

## 1. Phase 3 Status

**Implemented and verified; awaiting review and explicit FROZEN confirmation.** The first real source now produces provider-neutral, in-memory transaction candidates and parser validation. No database migration or architecture change was needed.

Baseline was clean `main` at `c9f2960a0bc6289ffb1ca04533cb0c0950eba5ac`, matching both `origin/main` and GitHub. That commit remains HEAD.

## 2. Real PDF Access/Privacy Handling

Read the user-supplied PDF from Downloads, outside the repository. Inspected its text-layer structure locally using redacted structural diagnostics. The original PDF was neither modified nor copied into the repository, a fixture directory, or a container filesystem. The Docker smoke test received its bytes through standard input and retained extracted content only in process memory.

No customer identity, address, account/card identifiers, raw document text, or real transaction list appears in this report or fixtures. Diagnostics emitted only structural checks and the permitted aggregate verification results. Real descriptions were also checked locally for accidental reuse in test sources; none were found.

## 3. PDF Library Selected and Reason

**pypdf 6.16.2** is the only added dependency. Its plain text-layer extraction reliably reads this reference, including Turkish text and page boundaries, without OCR or a competing layout library. Initial inspection used the bundled pypdf; final acceptance used the pinned version in Docker. The extraction API is documented in the [official pypdf text extraction guide](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

## 4. Parser Architecture

```text
PDF bytes
  → extract_pdf_text
  → ExtractedDocument / ExtractedPage
  → YapiKrediTLCardPDFParser.parse
  → ParsedStatement / CanonicalTransactionCandidate
  → validate / StatementValidation
```

`StatementParser` is a Protocol with `can_parse`, `parse`, and `validate`. All provider-specific rules remain under `imports/parsers/`. The parser imports shared enums, not ORM entities or database sessions. Parser provenance is `yapikredi_tlcard_pdf`, version `1.0.0`.

## 5. DTOs Added

Frozen dataclasses: `ExtractedPage`, `ExtractedDocument`, `CanonicalTransactionCandidate`, `ParsedStatement`, and `StatementValidation`.

Candidates carry dates, raw descriptions, optional raw merchant, exact amount/currency, transaction type, and one-based row/page provenance. Statements carry generic institution/type, month/year label, reported total, candidates, and parser name/version. There are no customer/address/card/account identity fields, category assignments, normalized merchant fields, or ORM state. Raw text/descriptions and statement transaction collections are excluded from their containing DTO representations.

## 6. Statement Recognition Strategy

Require the combined Yapı Kredi identity, TLcard marker, statement-period label, transaction-table header, and purchase-total label. A generic bank mention alone is rejected. Recognition uses no customer or account identifiers. Known whitespace variations are normalized only for structural recognition, including the observed extraction-induced space in the purchase-total heading.

## 7. Turkish Money Parsing Strategy

Strict Turkish grouping and two decimal places are converted directly to `Decimal`, without float intermediates. Tests cover `1.234,56`, `9.324,79`, `880,00`, small values, and multiple thousands groups. Malformed grouping, foreign separator conventions, unsupported signs, missing/excess decimal places, non-finite values, and canonical precision overflow fail explicitly. There is no production constant for the real statement's expected total.

## 8. Date Parsing Strategy

Parse the observed day + Turkish month name + explicit four-digit year into Python `date`. Invalid dates fail; yearless rows are unsupported rather than guessed. A regression test preserves a December transaction's explicit year alongside January rows.

The source supplies a month/year statement label. The DTO represents it as `YYYY-MM`; exact start/end dates remain `None`. The private smoke test independently checked the period label and all transaction dates against source text without printing them.

## 9. Transaction Table Parsing Strategy

Parse only within recognized transaction-table boundaries. Require complete dated rows and a closing table total. Support repeated headers, page boundaries with repeated headers, optional points, ordinary whitespace differences, and a wrapped description while a dated row is incomplete.

The trailing amount and optional points are parsed separately. Reward/identity sections outside the table are ignored. Page-number footers are recognized; unexpected content inside the table fails rather than being silently discarded. Missing/malformed amounts, ambiguous monetary columns, incomplete rows, conflicting metadata, empty tables, and inconsistent table totals are rejected. Unknown layouts are not silently treated as supported.

## 10. Canonical Sign Handling

Positive source amounts for recognized card purchases become negative canonical amounts. Normal purchase-table rows are `EXPENSE`; explicit cash-withdrawal operation labels can produce `CASH_WITHDRAWAL`. Explicit unsupported/non-purchase operation labels produce `UNKNOWN` and fail validation. This is statement semantics, not merchant/category normalization.

Descriptions retain original case, punctuation, internal spaces, and supported line wrapping. Outer table padding is removed. The parser does not claim complete income, transfers, current balance, net worth, or remaining cash from this spending statement.

## 11. Reported-Total Reconciliation Semantics

The reported purchase total is a positive magnitude. Validation sums `-amount` for qualifying `EXPENSE` candidates, with a separate check that all supported debit rows have negative amounts and TRY currency. Cash withdrawals do not contribute to purchase reconciliation. Unknown or other transaction types cannot validate successfully.

The validator never takes the absolute value of arbitrary income/refund/transfer rows. It returns a structured `FAILED` result for mismatch or invalid semantics. Callers must use `validate(statement)` and `require_passed()` before treating candidates as reconciled. The table footer is checked independently against extracted debit-row magnitudes during parsing.

## 12. Real Reference Smoke-Test Result

| Verification | Result |
| --- | --- |
| Text-layer extraction | Passed; no OCR |
| Statement recognized | Yes |
| Currency | TRY |
| Transaction count | 28 |
| Reported purchase total | 9324.79 |
| Parsed purchase magnitude | 9324.79 |
| Validation | PASSED |
| Period and transaction dates | Verified against source |
| Canonical purchases | Negative Decimal values |
| Database row counts before/after | Unchanged |
| Real descriptions copied into test sources | None |

The expected amount was supplied only to the local smoke-check script, not production parser logic.

## 13. Synthetic Fixtures Added

`backend/tests/fixtures/tlcard_synthetic.txt` is independently authored with invented merchants, dates, amounts, and points. Three purchases reconcile to a synthetic total of 1,340.00 TRY. It includes two pages, repeated headers, a wrapped Turkish description, points, and footer noise.

`backend/tests/pdf_factory.py` constructs synthetic PDF bytes in memory from this text using pypdf, including a Unicode text map. The extraction/parser integration test consumes these bytes end-to-end. No binary fixture or PDF-generation dependency was added. Mismatch and malformed fixtures are derived from this synthetic text during tests.

## 14. Tests Added

**48 new cases:** 40 parser/DTO cases and 8 extraction cases. They cover exact money, malformed values, recognition/rejection, period/dates, signed amounts, description preservation, points, row/page provenance, valid and failed reconciliation, cash exclusion, unknown operations, explicit year boundaries, repeated headers, footer isolation, conflicting metadata, privacy, and absence of database operations.

Extraction tests cover synthetic PDFs, Turkish text, page boundaries, encryption rejection, malformed/empty PDFs, missing text layers, safe exceptions, and both existing and lazily created upstream diagnostic loggers. Database access methods are replaced with failure sentinels in the parser isolation test.

## 15. Test Results

**92 passed, 2 existing upstream warnings** on Docker Python 3.12.14: 44 earlier tests plus 48 Phase 3 cases. Ruff lint and format checks pass. The final private smoke test also passed on pinned pypdf 6.16.2.

Commands executed included:

```sh
docker compose up --build -d --wait
docker compose exec -T backend pytest
docker compose exec -T backend ruff check .
docker compose exec -T backend ruff format --check .
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T frontend npm run build
docker compose config --quiet
docker compose ps
git status --short
git diff
git diff --check
```

Local Ruff formatting was used during development. Additional read-only checks verified the health/OpenAPI endpoints, frozen-file bytes, private source reconciliation, unchanged database counts, test-database cleanup, dependency consistency, and Git state. The private smoke script streams PDF bytes through `docker compose exec -T backend python -c ...`; it emits only the safe summary above.

## 16. Dependency Changes

Added `pypdf>=6.16.2,<7` to `backend/pyproject.toml` and pinned `pypdf==6.16.2` in `backend/requirements.lock`. Existing dependency pins are unchanged. The lockfile uses LF line endings so Git's whitespace check passes. No OCR, cloud service, second PDF parser, or fixture-generation package was introduced. Python 3.12 remains canonical.

## 17. Alembic Result

`current`: **0001 (head)**. `check`: **No new upgrade operations detected.** No new revision or Phase 2 table/model change exists. Existing PostgreSQL migration/domain tests continue to pass.

## 18. Docker/Health Result

Backend rebuilt successfully with the PDF dependency. All three services are healthy. `GET /api/v1/health` returns **HTTP 200** and `{"status":"ok"}`. OpenAPI still contains only the health application route. Compose validation passes; existing localhost port publication is unchanged.

## 19. Frontend Build Result

TypeScript checking and Vite 8.2.2 production build passed, with 19 modules transformed. Frontend source and configuration are unchanged.

## 20. Files Added/Modified

**11 added, 3 modified**, including this report.

Added:

- `backend/app/modules/imports/exceptions.py`
- `backend/app/modules/imports/schemas.py`
- `backend/app/modules/imports/parsers/__init__.py`
- `backend/app/modules/imports/parsers/base.py`
- `backend/app/modules/imports/parsers/pdf_text.py`
- `backend/app/modules/imports/parsers/yapikredi_tlcard.py`
- `backend/tests/fixtures/tlcard_synthetic.txt`
- `backend/tests/pdf_factory.py`
- `backend/tests/test_pdf_text.py`
- `backend/tests/test_tlcard_parser.py`
- `PHASE_3_REPORT.md`

Modified: `README.md`, `backend/pyproject.toml`, and `backend/requirements.lock`.

## 21. Warnings / Unresolved Questions

No blocking architecture contradiction or unresolved acceptance failure remains.

Two existing Starlette/AnyIO deprecation warnings remain; Docker pip installation also emits its root-user warning and update notice. Dependencies were not upgraded to suppress these notices.

Support is deliberately limited to the inspected text-layer TLcard format and tested structural variations. Encrypted/image-only PDFs, yearless dates, unsupported layouts, and ambiguous rows fail safely. Only one real reference statement has been verified; additional real layout variants require separate private regression verification. Upload limits, timeouts, temporary-file lifecycle, and orchestration remain future work.

## 22. Confirmation No PII/Real Statement Was Added to Git

Confirmed. No private PDF, raw extracted text, real transaction history, customer identity, account/card identifier, or secret was added to repository files or Git. Synthetic fixtures were constructed independently. The original file remains outside the repository. All nine frozen engineering documents match the original ZIP byte-for-byte.

## 23. Confirmation No Phase 4+ Features Were Implemented

Confirmed: no uploads, parser registry, import service/preview/confirmation, persistence workflow, hashing/idempotency workflow, duplicate detection, merchant normalization, categorization, analytics, financial UI, authentication, AI, Gmail, CSV/XLSX, or second-bank adapter.

## 24. Confirmation No Commit/Push Was Performed

No staging, commit, push, amendment, rebase, branch change, or history rewrite occurred. The index is empty; Phase 3 changes remain in the working tree for review. Phase 4 has not started.
