from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Commodity(Base):
    __tablename__ = "commodities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), default="")
    unit: Mapped[str] = mapped_column(String(64), default="")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(160))
    market: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8))
    sector: Mapped[str] = mapped_column(String(96))
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    exposures: Mapped[list["CompanyCommodityExposure"]] = relationship(back_populates="company")


class CompanyCommodityExposure(Base):
    __tablename__ = "company_commodity_exposures"
    __table_args__ = (UniqueConstraint("company_id", "commodity_id", name="uq_company_commodity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"))
    exposure_type: Mapped[str] = mapped_column(String(32))
    exposure_direction: Mapped[str] = mapped_column(String(16))
    exposure_score: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")

    company: Mapped[Company] = relationship(back_populates="exposures")
    commodity: Mapped[Commodity] = relationship()


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(32), unique=True)
    ticker: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(8))


class UserPosition(Base):
    __tablename__ = "user_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_buy_price: Mapped[float] = mapped_column(Float)
    buy_date: Mapped[str] = mapped_column(String(16), default="")
    currency: Mapped[str] = mapped_column(String(8))
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ValuationTarget(Base):
    __tablename__ = "valuation_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(160), default="")
    market: Mapped[str] = mapped_column(String(32), default="US")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    fair_value_price: Mapped[float] = mapped_column(Float)
    buy_price: Mapped[float] = mapped_column(Float)
    alert_buffer_pct: Mapped[float] = mapped_column(Float, default=5.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CandidateSignal(Base):
    __tablename__ = "candidate_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    commodity_code: Mapped[str] = mapped_column(String(64), index=True)
    signal_type: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    event_score: Mapped[float] = mapped_column(Float)
    commodity_move_pct: Mapped[float] = mapped_column(Float)
    stock_return_pct: Mapped[float] = mapped_column(Float)
    benchmark_return_pct: Mapped[float] = mapped_column(Float)
    excess_return_pct: Mapped[float] = mapped_column(Float)
    valuation_score: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float)
    liquidity_score: Mapped[float] = mapped_column(Float)
    momentum_score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertHistory(Base):
    __tablename__ = "alert_history"
    __table_args__ = (UniqueConstraint("alert_key", name="uq_alert_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    commodity_code: Mapped[str] = mapped_column(String(64), index=True)
    signal_type: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    alert_key: Mapped[str] = mapped_column(String(128), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    message: Mapped[str] = mapped_column(Text)


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    error_message: Mapped[str] = mapped_column(Text, default="")
    data_provider_status: Mapped[str] = mapped_column(Text, default="")
