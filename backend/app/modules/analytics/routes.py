from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.modules.analytics.schemas import (
    CategoryResult,
    CompareQuery,
    CompareResult,
    MerchantQuery,
    MerchantResult,
    PeriodQuery,
    ProjectionQuery,
    ProjectionResult,
    SummaryResult,
    TrendResult,
)
from app.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def analytics_service(user_id: UserContext, session: Annotated[Session, Depends(get_session)]):
    return AnalyticsService(session, user_id)


Service = Annotated[AnalyticsService, Depends(analytics_service)]


@router.get("/summary", response_model=SummaryResult)
def summary(query: Annotated[PeriodQuery, Query()], service: Service):
    return service.get_spending_summary(query)


@router.get("/categories", response_model=CategoryResult)
def categories(query: Annotated[PeriodQuery, Query()], service: Service):
    return service.get_category_breakdown(query)


@router.get("/merchants", response_model=MerchantResult)
def merchants(query: Annotated[MerchantQuery, Query()], service: Service):
    return service.get_merchant_breakdown(query)


@router.get("/trend", response_model=TrendResult)
def trend(query: Annotated[PeriodQuery, Query()], service: Service):
    return service.get_monthly_trend(query)


@router.get("/compare", response_model=CompareResult)
def compare(query: Annotated[CompareQuery, Query()], service: Service):
    return service.compare_periods(query)


@router.get("/projection", response_model=ProjectionResult)
def projection(query: Annotated[ProjectionQuery, Query()], service: Service):
    return service.project_month_spending(query)
