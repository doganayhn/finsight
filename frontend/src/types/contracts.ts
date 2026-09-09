export type Money = string;
export type TransactionType =
  | "EXPENSE"
  | "REFUND"
  | "TRANSFER"
  | "CARD_PAYMENT"
  | "INCOME"
  | "FEE"
  | "CASH_WITHDRAWAL"
  | "INTEREST"
  | "UNKNOWN";
export type ReviewStatus = "NEEDS_REVIEW" | "AUTO_CONFIRMED" | "USER_CONFIRMED";
export interface Account {
  id: string;
  display_name: string;
  institution_code: string | null;
  account_type: string;
  currency: string;
  is_active: boolean;
}
export interface Category {
  id: string;
  code: string;
  display_name: string;
  parent_id?: string | null;
}
export interface Page {
  limit: number;
  offset: number;
  has_more: boolean;
}
export interface Scope {
  account_id: string | null;
  currency_filter: string | null;
  data_scope: "CANONICAL_TRANSACTIONS";
}
export interface AssistantHistoryMessage {
  role: "user" | "assistant";
  content: string;
}
export interface AssistantStatus {
  enabled: boolean;
  provider: "Groq";
  model: string;
}
export interface AssistantResponse {
  answer: string;
  used_tools: { name: string; label: string }[];
  scope: {
    account_id: string | null;
    data_scope: "CANONICAL_TRANSACTIONS";
  };
}
export interface Period {
  start_date: string;
  end_date: string;
}
export interface Metrics {
  gross_spending: Money;
  refunds: Money;
  net_spending: Money;
  financial_fees: Money;
  cash_withdrawals: Money;
  expense_transaction_count: number;
  refund_transaction_count: number;
}
export interface Summary extends Scope {
  period: Period;
  currencies: (Metrics & { currency: string })[];
}
export interface Breakdown {
  gross_spending: Money;
  refunds: Money;
  net_spending: Money;
  transaction_count: number;
}
export interface CategoryBucket extends Breakdown {
  category_id: string;
  category_code: string;
  category_name: string;
}
export interface CategoryAnalytics extends Scope {
  period: Period;
  currencies: { currency: string; categories: CategoryBucket[] }[];
}
export interface MerchantBucket extends Breakdown {
  merchant: string | null;
  identity_source: "NORMALIZED" | "RAW" | "UNKNOWN";
}
export interface MerchantAnalytics extends Scope {
  period: Period;
  limit_per_currency: number;
  currencies: { currency: string; merchants: MerchantBucket[] }[];
}
export interface Trend extends Scope {
  period: Period;
  currencies: { currency: string; months: (Metrics & { month: string })[] }[];
}
export interface Comparison extends Scope {
  current_period: Period;
  previous_period: Period;
  currencies: {
    currency: string;
    current_net_spending: Money;
    previous_net_spending: Money;
    absolute_change: Money;
    percentage_change: Money | null;
    percentage_state:
      "DEFINED" | "BOTH_ZERO" | "PREVIOUS_ZERO" | "PREVIOUS_NEGATIVE";
    direction: "INCREASE" | "DECREASE" | "UNCHANGED";
  }[];
}
export interface Projection extends Scope {
  month: string;
  as_of_date: string;
  elapsed_days: number;
  days_in_month: number;
  method: "LINEAR_DAILY_RUN_RATE";
  assumptions: string[];
  currencies: {
    currency: string;
    observed_net_spending: Money;
    projection_basis: Money;
    average_daily_spending: Money;
    projected_month_spending: Money;
  }[];
}
export interface Transaction {
  id: string;
  account_id: string;
  transaction_date: string;
  posted_date: string | null;
  description_raw: string;
  merchant_normalized: string | null;
  amount: Money;
  currency: string;
  transaction_type: TransactionType;
  category: Category | null;
  category_source: string;
  review_status: ReviewStatus;
  installment_index: number | null;
  installment_count: number | null;
  installment_plan_id: string | null;
}
export interface TransactionPage extends Page, Scope {
  period: Period;
  transactions: Transaction[];
}
export interface Correction {
  preferred_merchant_name?: string;
  category_id?: string;
  persist_as_rule: boolean;
}
export interface CorrectionResult {
  id: string;
  merchant_normalized: string | null;
  category_id: string | null;
  category_source: string;
  review_status: ReviewStatus;
}
export type ImportStatus =
  "PENDING" | "PARSED" | "AWAITING_CONFIRMATION" | "COMPLETED" | "FAILED";
export type ValidationStatus =
  "PASSED" | "FAILED" | "NOT_AVAILABLE" | "NEEDS_REVIEW";
export interface Candidate {
  id: string;
  transaction_date: string;
  posted_date: string | null;
  description_raw: string;
  merchant_raw: string | null;
  amount: Money;
  currency: string;
  transaction_type: TransactionType;
  source_transaction_id: string | null;
  source_row_number: number;
  source_page_number: number | null;
  duplicate_matches: { kind: string; matched_id: string }[];
}
export interface ImportPreview {
  import_batch_id: string;
  status: ImportStatus;
  institution_code: string | null;
  statement_type: string | null;
  currency: string | null;
  statement_period: string | null;
  parser: { name: string | null; version: string | null };
  reported_total: Money | null;
  parsed_total: Money | null;
  validation_status: ValidationStatus;
  counts: {
    total_rows: number;
    valid_rows: number;
    failed_rows: number;
    duplicate_rows: number;
    imported_rows: number;
    skipped_duplicate_rows: number;
  };
  transactions: Candidate[];
}
export interface ImportHistoryItem {
  id: string;
  account_id: string;
  created_at: string;
  institution_code: string | null;
  statement_type: string | null;
  statement_period: string | null;
  currency: string | null;
  import_status: ImportStatus;
  validation_status: ValidationStatus;
  reported_total: Money | null;
  parsed_total: Money | null;
  total_rows: number;
}
export type Decisions = Record<string, "import" | "skip">;
