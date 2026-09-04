"""Scoped queries and locks for import orchestration."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import Account
from app.modules.imports.errors import ImportProblem
from app.modules.imports.models import ImportBatch
from app.modules.imports.staging import ImportTransactionCandidate
from app.modules.transactions.models import Transaction


class ImportRepository:
    def __init__(self, session: Session):
        self.session = session

    def account(self, user_id: UUID, account_id: UUID, *, lock: bool = False) -> Account:
        query = select(Account).where(Account.id == account_id, Account.user_id == user_id)
        if lock:
            query = query.with_for_update()
        account = self.session.scalar(query)
        if account is None:
            raise ImportProblem("account_not_found", 404)
        return account

    def batch(self, user_id: UUID, batch_id: UUID, *, lock: bool = False) -> ImportBatch:
        query = select(ImportBatch).where(
            ImportBatch.id == batch_id, ImportBatch.user_id == user_id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        batch = self.session.scalar(query)
        if batch is None:
            raise ImportProblem("import_not_found", 404)
        return batch

    def candidates(self, batch_id: UUID) -> list[ImportTransactionCandidate]:
        return list(
            self.session.scalars(
                select(ImportTransactionCandidate)
                .where(ImportTransactionCandidate.import_batch_id == batch_id)
                .order_by(ImportTransactionCandidate.source_row_number)
            )
        )

    def imported_count(self, batch_id: UUID) -> int:
        return self.session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.import_batch_id == batch_id)
        )
