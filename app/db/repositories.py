from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AlertHistory,
    Benchmark,
    CandidateSignal,
    Commodity,
    Company,
    CompanyCommodityExposure,
    RunLog,
    UserPosition,
    ValuationTarget,
)


def get_active_commodities(session: Session) -> list[Commodity]:
    return list(session.scalars(select(Commodity).where(Commodity.is_active.is_(True))))


def get_active_companies(session: Session) -> list[Company]:
    return list(session.scalars(select(Company).where(Company.is_active.is_(True))))


def get_active_positions(session: Session) -> list[UserPosition]:
    return list(session.scalars(select(UserPosition).where(UserPosition.is_active.is_(True))))


def get_active_valuation_targets(session: Session) -> list[ValuationTarget]:
    return list(session.scalars(select(ValuationTarget).where(ValuationTarget.is_active.is_(True))))


def get_benchmark_for_market(session: Session, market: str) -> Benchmark | None:
    return session.scalar(select(Benchmark).where(Benchmark.market == market))


def create_run(session: Session) -> RunLog:
    run = RunLog()
    session.add(run)
    session.commit()
    return run


def finish_run(session: Session, run: RunLog, status: str, error: str = "", provider_status: str = "") -> None:
    run.status = status
    run.error_message = error
    run.data_provider_status = provider_status
    run.finished_at = datetime.utcnow()
    session.commit()


def save_signal(session: Session, signal: CandidateSignal) -> None:
    session.add(signal)
    session.commit()


def find_alert(session: Session, alert_key: str) -> AlertHistory | None:
    return session.scalar(select(AlertHistory).where(AlertHistory.alert_key == alert_key))


def latest_alert_for_base(session: Session, base_key: str) -> AlertHistory | None:
    stmt = (
        select(AlertHistory)
        .where(AlertHistory.alert_key.like(f"{base_key}%"))
        .order_by(AlertHistory.sent_at.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def save_alert(session: Session, alert: AlertHistory) -> None:
    session.add(alert)
    session.commit()
