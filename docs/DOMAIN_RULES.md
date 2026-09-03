# FinSight Financial Domain Rules

Status: **Frozen baseline for V1**

This document defines financial invariants that implementation code must preserve.

## 1. Money is exact

Authoritative monetary calculations must not use binary floating point.

Python:

```python
Decimal
```

PostgreSQL:

```sql
NUMERIC(18,2)
```

## 2. Currency is explicit

Every monetary transaction must have a currency.

Initial expected currencies may include TRY, USD and EUR. V1 primarily targets TRY.

Different currencies must never be silently added together.

Incorrect:

```text
10,000 TRY + 300 USD = 10,300
```

Correct behavior without FX conversion:

```json
{
  "TRY": "10000.00",
  "USD": "300.00"
}
```

Currency conversion is outside V1 unless explicitly added later.

## 3. Canonical amount sign convention

The canonical amount is stored from the account's perspective.

Positive means money enters the account. Negative means money leaves the account.

Examples:

```text
Salary               +50,000.00
Migros                 -1,250.00
Refund                 +1,250.00
Outgoing transfer      -5,000.00
Incoming transfer      +5,000.00
```

A statement may visually display purchases as positive values. Statement parsers must convert them into the canonical FinSight convention.

## 4. Transaction semantic types

The V1 domain must be able to represent at least:

```text
EXPENSE
INCOME
TRANSFER
REFUND
FEE
INTEREST
CARD_PAYMENT
CASH_WITHDRAWAL
UNKNOWN
```

Uncertain classification should become `UNKNOWN` or `NEEDS_REVIEW`, not an invented confident category.

## 5. Transfer is not expense

Example:

```text
Yapı Kredi account     -5,000 TRY
Ziraat account         +5,000 TRY
```

If these represent the user's own account-to-account transfer:

```text
Expense impact = 0
Income impact  = 0
```

The records may be linked using `TRANSFER_PAIR`.

## 6. Credit-card payment must not double count spending

Example credit-card purchases:

```text
Migros       1,000
Trendyol     2,000
Restaurant   5,000
```

Actual spending is 8,000 TRY.

A later checking-account payment of the credit-card bill is not another 8,000 TRY of consumer spending.

The settlement/payment must be classified separately, for example as `CARD_PAYMENT` and optionally linked using `CARD_PAYMENT_PAIR`.

Do not pair one credit-card payment individually with every purchase item.

## 7. Refund is not ordinary income

Example:

```text
Purchase       -1,500 TRY
Refund         +1,500 TRY
```

The refund is not salary or new income. It reverses previous spending.

A refund may be linked to a purchase using `REFUND_OF`.

Partial refunds must remain representable.

## 8. Installments: cash flow and purchase value are different

Example:

```text
Original purchase: 30,000 TRY
Installment count: 6
Monthly installment: 5,000 TRY
```

For monthly cash-flow/spending analysis:

```text
September impact = 5,000 TRY
October impact   = 5,000 TRY
```

For purchase-level analysis:

```text
Original purchase value = 30,000 TRY
```

The system must not replace each monthly installment with the full original purchase value.

Planned nullable metadata may include:

```text
installment_index
installment_count
installment_plan_id
```

Installment grouping is not the same relational shape as a pairwise transfer/refund link.

## 9. Statement period is not calendar month

A bank statement may cover a billing cycle that does not match the calendar month.

Example:

```text
12 August – 11 September
```

Therefore distinguish transaction-date analytics from statement/billing-period analytics.

V1 spending analytics should default to transaction-date/calendar-period logic unless an endpoint explicitly states otherwise.

## 10. Credit limit is not balance

Credit-card available limit is not liquid money.

Do not include available credit in cash balance, net cash, liquid funds or savings.

## 11. Balance requires an as-of date

A balance extracted from a historical statement is not necessarily the user's current balance.

If balance data is introduced, it must be associated with an `as_of` date/time or statement date.

Future design may use `balance_snapshots`.

## 12. Raw data is preserved conceptually, but privacy is minimized

Important provenance may include:

- import batch
- source transaction/reference id if available
- source row number
- parser name
- parser version
- selected raw source fields

However, customer address, full account number, full card number and unrelated personal fields must not be persisted unless genuinely required.

A constrained `source_data` JSONB field may be used for parser provenance if approved during schema implementation.

## 13. Duplicate detection is probabilistic when source IDs are unavailable

Preferred transaction identity is the source/bank transaction reference ID.

If no source ID exists, use careful duplicate candidate logic with signals such as:

- account
- transaction date
- amount
- normalized description
- balance after transaction if available

Do not use `source_row_number` as the main cross-import identity because row positions may change.

## 14. File-level idempotency

Each import file should have a cryptographic file hash.

If the exact same file has already been successfully imported for the user/account, the system should detect this before re-importing.

File-level idempotency does not replace transaction-level duplicate detection.

## 15. Category provenance

Category assignment should remain explainable.

Potential category sources:

```text
USER
MERCHANT_RULE
SYSTEM_RULE
CLASSIFIER
UNKNOWN
```

Potential review states:

```text
AUTO_CONFIRMED
NEEDS_REVIEW
USER_CONFIRMED
```

## 16. Categorization precedence

Preferred order:

```text
User override
    ↓
Known merchant rule
    ↓
Deterministic keyword/rule layer
    ↓
Future small classifier
    ↓
Needs review / Other
```

V1 must not call the LLM once per transaction.

## 17. Analytics source of truth

Financial calculations belong to backend analytics code and/or application-authored SQL.

The LLM does not authoritatively calculate totals, percentages, period differences, savings, category shares or projections.

## 18. Incomplete data must produce bounded answers

The initial Yapı Kredi TLcard e-statement does not represent every movement of the linked bank account.

With that source alone, the system may answer questions such as:

- total observed card spending
- merchant/category breakdown
- spending trend
- simple projected spending

It must not claim to know:

- complete salary/income
- all transfers
- exact current bank balance
- complete net worth
- guaranteed month-end remaining cash

If data is insufficient, say so explicitly.

## 19. Simple forecast semantics

V1 may forecast **spending**, not full financial position.

Valid example:

```text
At this pace, approximately how much will I spend by month end?
```

Unsupported without sufficient sources:

```text
How much money will I have left at month end?
```

Forecasts must state assumptions.

## 20. User corrections are first-class data

If a user corrects category, merchant normalization or transaction semantic type, that correction must not disappear on the next import.

User-specific overrides should take precedence over global defaults where appropriate.

## 21. The LLM cannot override domain rules

No prompt or model output may redefine amount sign rules, user scope, transfer semantics, refund semantics or authoritative calculations.
