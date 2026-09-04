from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import UTCDateTime


class IdentityMixin:
    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())


class TimestampMixin(CreatedAtMixin):
    # SQLAlchemy-managed updates; direct SQL writers must set updated_at explicitly.
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.clock_timestamp()
    )
