from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.merchants.models import MerchantAlias, UserMerchantRule


class MerchantRepository:
    def __init__(self, session: Session):
        self.session = session

    def aliases(self):
        return self.session.scalars(select(MerchantAlias).where(MerchantAlias.is_active)).all()

    def user_rules(self, user_id: UUID):
        return self.session.scalars(
            select(UserMerchantRule).where(UserMerchantRule.user_id == user_id)
        ).all()

    def upsert_rule(self, user_id: UUID, key: str, changes: dict):
        # PostgreSQL conflict handling also serializes concurrent corrections to one key.
        statement = insert(UserMerchantRule).values(user_id=user_id, merchant_key=key, **changes)
        self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_user_merchant_rules_user_key",
                set_=changes | {"updated_at": func.clock_timestamp()},
            )
        )
