from __future__ import annotations

import csv
from pathlib import Path

from app.config import ROOT_DIR
from app.providers.base import (
    EventData,
    FundamentalData,
    FundamentalsProvider,
    MarketDataProvider,
    NewsProvider,
    PriceMove,
    StockMove,
)
from app.providers.mock_provider import MockFundamentalsProvider, MockMarketDataProvider, MockNewsProvider


class CsvMarketDataProvider(MarketDataProvider):
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or ROOT_DIR / "data" / "csv"
        self.fallback = MockMarketDataProvider()

    def commodity_moves(self, commodity_codes: list[str]) -> dict[str, PriceMove]:
        path = self.data_dir / "commodity_moves.csv"
        if not path.exists():
            return self.fallback.commodity_moves(commodity_codes)
        rows = _read_csv(path)
        return {
            row["code"]: PriceMove(row["code"], float(row["move_pct"]), float(row.get("momentum_pct", 0)))
            for row in rows
            if row["code"] in commodity_codes
        }

    def stock_moves(self, tickers: list[str], benchmark_by_ticker: dict[str, str]) -> dict[str, StockMove]:
        path = self.data_dir / "stock_moves.csv"
        if not path.exists():
            return self.fallback.stock_moves(tickers, benchmark_by_ticker)
        rows = _read_csv(path)
        return {
            row["ticker"]: StockMove(
                ticker=row["ticker"],
                return_pct=float(row["return_pct"]),
                benchmark_return_pct=float(row["benchmark_return_pct"]),
                volume_ratio=float(row.get("volume_ratio", 1)),
                momentum_pct=float(row.get("momentum_pct", 0)),
                last_price=float(row.get("last_price", 0)),
                week52_high=_optional_float(row.get("week52_high")),
                week52_low=_optional_float(row.get("week52_low")),
            )
            for row in rows
            if row["ticker"] in tickers
        }


class CsvNewsProvider(NewsProvider):
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or ROOT_DIR / "data" / "csv"
        self.fallback = MockNewsProvider()

    def events(self, commodity_codes: list[str]) -> list[EventData]:
        path = self.data_dir / "news_events.csv"
        if not path.exists():
            return self.fallback.events(commodity_codes)
        return [
            EventData(
                commodity_code=row["commodity_code"],
                event_type=row.get("event_type", "unknown"),
                direction=row.get("direction", "bullish"),
                severity=float(row.get("severity", 0)),
                title=row.get("title", ""),
                source=row.get("source", "csv"),
                url=row.get("url", ""),
            )
            for row in _read_csv(path)
            if row["commodity_code"] in commodity_codes
        ]


class CsvFundamentalsProvider(FundamentalsProvider):
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or ROOT_DIR / "data" / "csv"
        self.fallback = MockFundamentalsProvider()

    def fundamentals(self, tickers: list[str]) -> dict[str, FundamentalData]:
        path = self.data_dir / "fundamentals.csv"
        if not path.exists():
            return self.fallback.fundamentals(tickers)
        rows = _read_csv(path)
        return {
            row["ticker"]: FundamentalData(
                ticker=row["ticker"],
                valuation_score=float(row.get("valuation_score", 50)),
                quality_score=float(row.get("quality_score", 50)),
                liquidity_score=float(row.get("liquidity_score", 50)),
                pe=_optional_float(row.get("pe")),
                pb=_optional_float(row.get("pb")),
                ev_ebitda=_optional_float(row.get("ev_ebitda")),
                roe=_optional_float(row.get("roe")),
                operating_margin=_optional_float(row.get("operating_margin")),
                debt_to_equity=_optional_float(row.get("debt_to_equity")),
            )
            for row in rows
            if row["ticker"] in tickers
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
