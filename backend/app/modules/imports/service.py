"""Synchronous import workflow. Parsers never receive a database session."""

import hashlib
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.imports.api_schemas import ImportPreview
from app.modules.imports.enums import FileFormat, ImportStatus, SourceType, ValidationStatus
from app.modules.imports.errors import ImportProblem
from app.modules.imports.exceptions import (
    PDFTextExtractionError,
    StatementParseError,
    UnsupportedStatementError,
)
from app.modules.imports.models import ImportBatch
from app.modules.imports.parsers.pdf_text import extract_pdf_text
from app.modules.imports.parsers.registry import ParserRegistry
from app.modules.imports.repository import ImportRepository
from app.modules.imports.staging import ImportTransactionCandidate
from app.modules.transactions.enums import CategorySource, ReviewStatus
from app.modules.transactions.models import Transaction

CANDIDATE_FIELDS = (
    "transaction_date",
    "posted_date",
    "description_raw",
    "merchant_raw",
    "amount",
    "currency",
    "transaction_type",
    "source_transaction_id",
    "source_row_number",
    "source_page_number",
)


def comparison_key(description: str) -> str:
    """Duplicate comparison only; never written into merchant_normalized."""
    return " ".join(description.casefold().split())


def heuristic_key(row):
    return (row.transaction_date, row.amount, row.currency, comparison_key(row.description_raw))


class ImportService:
    def __init__(
        self, session: Session, settings: Settings, registry: ParserRegistry | None = None
    ):
        self.session = session
        self.repo = ImportRepository(session)
        self.settings = settings
        self.registry = registry or ParserRegistry()

    def preview(self, user_id: UUID, account_id: UUID, data: bytes, filename: str, mime: str):
        if not data:
            raise ImportProblem("empty_file", 422)
        if len(data) > self.settings.max_upload_bytes:
            raise ImportProblem("file_too_large", 413)
        if not filename.lower().endswith(".pdf") or mime.lower() != "application/pdf":
            raise ImportProblem("pdf_required", 415)
        if not data.startswith(b"%PDF-"):
            raise ImportProblem("invalid_pdf_header", 415)
        file_hash = hashlib.sha256(data).hexdigest()
        problem = None
        with self.session.begin():
            # Shared lock order for preview/confirm: account, then import batch.
            # This serializes different imports into the same account, not just double confirms.
            account = self.repo.account(user_id, account_id, lock=True)
            existing = self.session.scalar(
                select(ImportBatch).where(
                    ImportBatch.user_id == user_id,
                    ImportBatch.account_id == account_id,
                    ImportBatch.file_hash == file_hash,
                    ImportBatch.import_status != ImportStatus.FAILED,
                )
            )
            if existing:
                raise ImportProblem("file_already_imported_or_pending", 409, existing.id)
            batch = ImportBatch(
                user_id=user_id,
                account_id=account_id,
                source_type=SourceType.MANUAL_UPLOAD,
                file_format=FileFormat.PDF,
                file_hash=file_hash,
                # Uploaded filenames can contain PII: retain a safe generic basename only.
                original_filename="statement.pdf",
                import_status=ImportStatus.PENDING,
            )
            self.session.add(batch)
            self.session.flush()
            try:
                document = extract_pdf_text(data, max_pages=self.settings.max_pdf_pages)
                parser = self.registry.resolve(document)
                statement = parser.parse(document)
                batch.import_status = ImportStatus.PARSED
                batch.institution_code = statement.institution_code
                batch.statement_type = statement.statement_type
                batch.parser_name = statement.parser_name
                batch.parser_version = statement.parser_version
                batch.statement_period = statement.statement_period
                batch.statement_period_start = statement.statement_period_start
                batch.statement_period_end = statement.statement_period_end
                batch.currency = statement.currency
                batch.reported_total = statement.reported_total
                validation = parser.validate(statement)
                batch.parsed_total = validation.parsed_purchase_magnitude
                batch.validation_status = validation.status
                batch.total_rows = len(statement.transactions)
                if validation.status != ValidationStatus.PASSED:
                    raise ImportProblem("statement_validation_failed", 422)
                if account.currency != statement.currency:
                    raise ImportProblem("account_currency_mismatch", 422)
                batch.valid_rows = batch.total_rows
                for row in statement.transactions:
                    self.session.add(
                        ImportTransactionCandidate(
                            import_batch_id=batch.id,
                            **{field: getattr(row, field) for field in CANDIDATE_FIELDS},
                        )
                    )
                self.session.flush()
                candidates = self.repo.candidates(batch.id)
                matches = self.duplicates(batch, candidates)
                batch.duplicate_rows = sum(bool(value) for value in matches.values())
                batch.import_status = ImportStatus.AWAITING_CONFIRMATION
                result = self.response(batch, candidates, matches)
            except (
                PDFTextExtractionError,
                StatementParseError,
                UnsupportedStatementError,
                ImportProblem,
            ) as exc:
                batch.import_status = ImportStatus.FAILED
                batch.validation_status = ValidationStatus.FAILED
                batch.valid_rows = 0
                batch.failed_rows = batch.total_rows
                code = exc.code if isinstance(exc, ImportProblem) else "invalid_statement"
                status = exc.status if isinstance(exc, ImportProblem) else 422
                problem = ImportProblem(code, status, batch.id)
        # Commit only safe failure metadata; raising inside begin() would discard the audit.
        if problem:
            raise problem
        return result

    def duplicates(self, batch, candidates):
        matches = {row.id: [] for row in candidates}
        if not candidates:
            return matches
        # Narrow by account and dates/source IDs before comparison. No cross-user matches.
        source_ids = [row.source_transaction_id for row in candidates if row.source_transaction_id]
        rows = self.session.execute(
            select(Transaction, ImportBatch.institution_code, ImportBatch.parser_name)
            .outerjoin(ImportBatch, Transaction.import_batch_id == ImportBatch.id)
            .where(
                Transaction.user_id == batch.user_id,
                Transaction.account_id == batch.account_id,
                or_(
                    Transaction.transaction_date.in_([c.transaction_date for c in candidates]),
                    Transaction.source_transaction_id.in_(source_ids),
                ),
            )
        ).all()
        for candidate in candidates:
            for transaction, institution, parser_name in rows:
                same_source = (institution, parser_name) == (
                    batch.institution_code,
                    batch.parser_name,
                )
                if (
                    candidate.source_transaction_id
                    and transaction.source_transaction_id
                    and same_source
                ):
                    kind = (
                        "source_id"
                        if candidate.source_transaction_id == transaction.source_transaction_id
                        else None
                    )
                else:
                    kind = (
                        "heuristic"
                        if heuristic_key(candidate) == heuristic_key(transaction)
                        else None
                    )
                if kind:
                    matches[candidate.id].append({"kind": kind, "matched_id": transaction.id})
            for other in candidates:
                if other.id == candidate.id:
                    continue
                if candidate.source_transaction_id and other.source_transaction_id:
                    kind = (
                        "candidate_source_id"
                        if candidate.source_transaction_id == other.source_transaction_id
                        else None
                    )
                else:
                    kind = (
                        "candidate_heuristic"
                        if heuristic_key(candidate) == heuristic_key(other)
                        else None
                    )
                if kind:
                    matches[candidate.id].append({"kind": kind, "matched_id": other.id})
        return matches

    def response(self, batch, candidates, matches):
        imported = self.repo.imported_count(batch.id)
        duplicate_count = (
            sum(bool(m) for m in matches.values()) if candidates else batch.duplicate_rows
        )
        return ImportPreview(
            import_batch_id=batch.id,
            status=batch.import_status,
            institution_code=batch.institution_code,
            statement_type=batch.statement_type,
            currency=batch.currency,
            statement_period=batch.statement_period,
            parser={"name": batch.parser_name, "version": batch.parser_version},
            reported_total=batch.reported_total,
            parsed_total=batch.parsed_total,
            validation_status=batch.validation_status,
            counts={
                "total_rows": batch.total_rows,
                "valid_rows": batch.valid_rows,
                "failed_rows": batch.failed_rows,
                "duplicate_rows": duplicate_count,
                "imported_rows": imported,
                "skipped_duplicate_rows": batch.valid_rows - imported
                if batch.import_status == ImportStatus.COMPLETED
                else 0,
            },
            transactions=[
                {field: getattr(row, field) for field in ("id", *CANDIDATE_FIELDS)}
                | {"duplicate_matches": matches[row.id]}
                for row in candidates
            ],
        )

    def get(self, user_id: UUID, batch_id: UUID):
        with self.session.begin():
            batch = self.repo.batch(user_id, batch_id)
            # Keep status and staging rows consistent if confirmation is concurrent.
            self.repo.account(user_id, batch.account_id, lock=True)
            batch = self.repo.batch(user_id, batch_id, lock=True)
            candidates = self.repo.candidates(batch.id)
            return self.response(batch, candidates, self.duplicates(batch, candidates))

    def confirm(self, user_id: UUID, batch_id: UUID, decisions: dict[UUID, str]):
        with self.session.begin():
            batch = self.repo.batch(user_id, batch_id)
            account = self.repo.account(user_id, batch.account_id, lock=True)
            batch = self.repo.batch(user_id, batch_id, lock=True)
            if batch.import_status == ImportStatus.COMPLETED:
                return self.response(batch, [], {})
            if account.currency != batch.currency:
                raise ImportProblem("account_currency_mismatch", 409, batch.id)
            if (
                batch.import_status != ImportStatus.AWAITING_CONFIRMATION
                or batch.validation_status != ValidationStatus.PASSED
            ):
                raise ImportProblem("import_not_confirmable", 409, batch.id)
            completed = self.session.scalar(
                select(ImportBatch.id).where(
                    ImportBatch.user_id == user_id,
                    ImportBatch.account_id == batch.account_id,
                    ImportBatch.file_hash == batch.file_hash,
                    ImportBatch.id != batch.id,
                    ImportBatch.import_status == ImportStatus.COMPLETED,
                )
            )
            if completed:
                raise ImportProblem("file_already_imported", 409, completed)
            candidates = self.repo.candidates(batch.id)
            if not candidates or len(candidates) != batch.valid_rows:
                raise ImportProblem("incomplete_preview", 409, batch.id)
            if set(decisions) - {row.id for row in candidates} or any(
                decision not in {"import", "skip"} for decision in decisions.values()
            ):
                raise ImportProblem("invalid_candidate_decisions", 422, batch.id)
            matches = self.duplicates(batch, candidates)
            duplicate_ids = {candidate_id for candidate_id, value in matches.items() if value}
            # Decisions apply only to current matches, never stale preview flags or ordinary rows.
            if set(decisions) - duplicate_ids:
                raise ImportProblem("decision_for_non_duplicate_candidate", 422, batch.id)
            if duplicate_ids - set(decisions):
                raise ImportProblem("duplicate_resolution_required", 409, batch.id)
            batch.duplicate_rows = len(duplicate_ids)
            for row in candidates:
                if decisions.get(row.id) == "skip":
                    continue
                fields = {
                    field: getattr(row, field)
                    for field in CANDIDATE_FIELDS
                    if field != "source_page_number"
                }
                self.session.add(
                    Transaction(
                        user_id=user_id,
                        account_id=batch.account_id,
                        import_batch_id=batch.id,
                        **fields,
                        category_source=CategorySource.UNKNOWN,
                        review_status=ReviewStatus.NEEDS_REVIEW,
                    )
                )
            self.session.flush()
            self.session.execute(
                delete(ImportTransactionCandidate).where(
                    ImportTransactionCandidate.import_batch_id == batch.id
                )
            )
            batch.import_status = ImportStatus.COMPLETED
            self.session.flush()
            return self.response(batch, [], {})
