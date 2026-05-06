from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceMove:
    code: str
    move_pct: float
    momentum_pct: float
    ma5: float | None = None
    ma20: float | None = None


@dataclass(frozen=True)
class StockMove:
    ticker: str
    return_pct: float
    benchmark_return_pct: float
    volume_ratio: float
    momentum_pct: float
    last_price: float
    week52_high: float | None = None
    week52_low: float | None = None
    ma5: float | None = None
    ma20: float | None = None


@dataclass(frozen=True)
class EventData:
    commodity_code: str
    event_type: str
    direction: str
    severity: float
    title: str
    source: str = "mock"
    url: str = ""


@dataclass(frozen=True)
class FundamentalData:
    ticker: str
    valuation_score: float
    quality_score: float
    liquidity_score: float
    pe: float | None = None
    pb: float | None = None
    ev_ebitda: float | None = None
    roe: float | None = None
    operating_margin: float | None = None
    debt_to_equity: float | None = None


class MarketDataProvider:
    def commodity_moves(self, commodity_codes: list[str]) -> dict[str, PriceMove]:
        raise NotImplementedError

    def stock_moves(self, tickers: list[str], benchmark_by_ticker: dict[str, str]) -> dict[str, StockMove]:
        raise NotImplementedError


class NewsProvider:
    def events(self, commodity_codes: list[str]) -> list[EventData]:
        raise NotImplementedError


class FundamentalsProvider:
    def fundamentals(self, tickers: list[str]) -> dict[str, FundamentalData]:
        raise NotImplementedError
