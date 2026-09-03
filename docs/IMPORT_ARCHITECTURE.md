# FinSight Import Architecture

Status: **Frozen baseline for V1**

This document defines how external financial data enters FinSight.

## 1. V1 data source

The first supported real-world source is:

> Yapı Kredi TLcard monthly e-statement PDF.

The user manually uploads the PDF using the web application.

This choice exists because the project should begin with real financial statement data rather than synthetic mock bank APIs.

It does not mean that FinSight Core is a Yapı Kredi-specific system.

## 2. V1 product boundary

The initial Yapı Kredi TLcard e-statement is a card-spending source, not a complete account-ledger source.

Therefore V1 is primarily a **spending intelligence platform** rather than a complete personal financial aggregation product.

## 3. Source, format and parser are separate concepts

### Source

How FinSight received the data:

```text
MANUAL_UPLOAD
GMAIL
```

### File format

```text
PDF
CSV
XLSX
```

### Parser

How a particular financial document is understood:

```text
YAPIKREDI_TLCARD_PDF
ZIRAAT_BANKKART_PDF
GENERIC_CSV
GENERIC_XLSX
```

These concepts must not be collapsed into one enum.

## 4. Core V1 flow

```text
Manual PDF Upload
        ↓
File Validation
        ↓
Document/Text Extraction
        ↓
Parser Registry
        ↓
YapiKrediTLCardPDFParser
        ↓
ParsedStatement
        ↓
CanonicalTransaction[]
        ↓
Statement Validation
        ↓
Merchant Normalization
        ↓
Category Assignment
        ↓
Duplicate Detection
        ↓
Import Preview
        ↓
User Confirmation
        ↓
Database Commit
```

## 5. Parser contract

Conceptual interface:

```python
class StatementParser(Protocol):
    def can_parse(self, document) -> bool:
        ...

    def parse(self, document) -> ParsedStatement:
        ...

    def validate(self, statement: ParsedStatement) -> StatementValidation:
        ...
```

A parser:

- recognizes its statement type
- extracts provider-specific fields
- converts values into canonical structures
- provides parser-specific validation evidence

A parser must not:

- write directly to PostgreSQL
- perform analytics
- call the LLM
- contain UI logic

## 6. Parser naming

Prefer statement-specific parser names.

Good:

```text
YapiKrediTLCardPDFParser
ZiraatBankkartPDFParser
```

Future examples:

```text
YapiKrediCreditCardPDFParser
YapiKrediAccountStatementPDFParser
```

Avoid assuming one parser can safely parse every document produced by an institution.

## 7. Parser registry

The import layer should support a registry or equivalent selection mechanism.

Conceptually:

```python
parsers = [
    YapiKrediTLCardPDFParser(),
]
```

Future:

```python
parsers = [
    YapiKrediTLCardPDFParser(),
    ZiraatBankkartPDFParser(),
    GenericCSVParser(),
    GenericXLSXParser(),
]
```

If no parser confidently matches, the import should fail cleanly or enter a user-assisted flow.

Do not silently parse with the wrong parser.

## 8. ParsedStatement

Parsers produce a provider-neutral statement object.

Conceptual example:

```python
ParsedStatement(
    institution="YAPI_KREDI",
    statement_type="TLCARD",
    statement_period="2026-08",
    currency="TRY",
    reported_total=Decimal("9324.79"),
    transactions=[...],
)
```

This is an import-domain DTO, not a persistence model.

## 9. CanonicalTransaction

Each parsed financial row becomes a canonical transaction candidate.

Conceptual example:

```python
CanonicalTransaction(
    transaction_date=date(2026, 8, 12),
    description_raw="TRENDYOL YEMEK ISTANBUL TR",
    amount=Decimal("-880.00"),
    currency="TRY",
)
```

Later stages may add merchant normalization, category, semantic type, review status, source reference and installment metadata.

Bank-specific fields must not become required fields in the canonical model.

## 10. Signed amount normalization

FinSight canonical convention:

```text
expense → negative
refund  → positive
income  → positive
outgoing transfer → negative
```

The parser/normalization boundary must enforce the canonical convention before persistence.

## 11. Statement total validation

When the statement reports an authoritative purchase total, the parser should expose it.

After transaction extraction:

```text
reported_total
vs.
sum(parsed qualifying transactions)
```

should be checked.

Possible statuses:

```text
PASSED
FAILED
NOT_AVAILABLE
NEEDS_REVIEW
```

A failed validation should not be silently committed as a successful import.

## 12. Import preview

Parsed data must not immediately become permanent transaction records.

Required flow:

```text
Upload
  ↓
Parse
  ↓
Validate
  ↓
Preview
  ↓
Confirm
  ↓
Commit
```

Preview should expose:

- detected institution/statement type
- statement period
- transaction count
- reported total
- parsed total
- validation status
- duplicate candidates
- rows needing review

## 13. Import batch

Every import attempt should be represented by an import batch or equivalent audit record.

Expected conceptual fields:

```text
id
user_id
account_id

source_type
file_format
institution
statement_type

original_filename
file_hash

parser_name
parser_version

statement_period
reported_total
parsed_total

total_rows
valid_rows
duplicate_rows
failed_rows

validation_status
import_status

created_at
```

Exact schema is finalized in the database phase.

## 14. File-level idempotency

Compute a cryptographic hash such as SHA-256 for the uploaded file.

If the same user/account already successfully imported the exact same file, report that before creating duplicate financial records.

## 15. Transaction-level duplicate detection

Preferred identifier:

```text
source_transaction_id
```

when the source provides one.

Otherwise, create duplicate candidates using multiple signals such as account, transaction date, amount, normalized description and balance-after when available.

Do not rely primarily on row number for cross-import identity.

Persist source row number for provenance/debugging.

## 16. Parser provenance

Import batches must capture:

```text
parser_name
parser_version
```

Example:

```text
parser_name = yapikredi_tlcard_pdf
parser_version = 1.0.0
```

## 17. Turkish locale parsing

The import layer must be designed for Turkish banking formats.

Expected amount variations:

```text
1.234,56
1,234.56
₺1.234,56
(1.234,56)
```

Expected date variations:

```text
03.09.2026
03/09/2026
2026-09-03
3 Eylül 2026
```

Future CSV concerns may include comma/semicolon delimiters and UTF-8/Windows-1254 encodings.

Locale-specific parsing utilities must remain separate from analytics.

## 18. Upload security

V1 manual uploads should enforce limits.

Initial policy may include:

- PDF only in the Yapı Kredi PDF phase
- explicit MIME/extension checks
- file size limit
- processing timeout
- safe temporary storage
- no arbitrary executable formats

Future CSV/XLSX phases should add separate validation.

Do not support macro-enabled Excel files unless explicitly required.

## 19. Raw file lifecycle

Preferred V1 behavior:

```text
Upload
  ↓
Temporary Storage
  ↓
Parse
  ↓
Validate
  ↓
Commit/Reject
  ↓
Delete Raw File
```

FinSight should retain import metadata and canonical data, not unnecessary full statement PDFs.

## 20. Data minimization

The parser should not persist unnecessary personal information such as:

- full customer name when not required
- address
- customer number
- full account number
- full card number

Only the minimum financial/account metadata needed by the product should survive the import boundary.

## 21. Merchant normalization is not parser responsibility

Parser may emit:

```text
IYZICO *AMAZON.COM...
```

A shared merchant service may later normalize it to:

```text
Amazon
```

Merchant normalization must not be duplicated separately inside every bank parser.

## 22. Gmail future extension

Future Gmail support should operate as an ingestion connector.

Correct:

```text
Gmail
  ↓
Relevant email
  ↓
PDF attachment
  ↓
existing parser registry
  ↓
YapiKrediTLCardPDFParser
```

Gmail must reuse the import core.

## 23. CSV/XLSX future extension

Future structured imports should also produce the same canonical boundary:

```text
CSV
 ↓
GenericCSVParser
 ↓
CanonicalTransaction[]
```

```text
XLSX
 ↓
GenericXLSXParser
 ↓
CanonicalTransaction[]
```

No changes should be required in analytics solely because a new source format is introduced.

## 24. Adding Ziraat

Adding Ziraat should mean primarily adding a new statement parser.

```text
Ziraat PDF
   ↓
ZiraatBankkartPDFParser
   ↓
ParsedStatement
   ↓
CanonicalTransaction[]
```

If adding Ziraat requires bank-specific branches inside analytics, transactions or assistant services, the canonical boundary has failed and should be corrected.

## 25. V1 import acceptance principle

The first complete import vertical slice is:

```text
Real Yapı Kredi TLcard PDF
        ↓
Detected correctly
        ↓
ParsedStatement
        ↓
CanonicalTransaction[]
        ↓
Reported total validation
        ↓
Preview
        ↓
Confirmed import
        ↓
PostgreSQL
```

No AI is required to prove the import engine works.
