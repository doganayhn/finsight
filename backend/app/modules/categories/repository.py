from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category


class CategoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def catalog(self):
        return self.session.scalars(
            select(Category).where(Category.is_system).order_by(Category.code)
        ).all()

    def by_code(self, code: str):
        return self.session.scalar(
            select(Category).where(Category.is_system, Category.code == code)
        )
