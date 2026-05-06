from __future__ import annotations

import hashlib

from app.providers.base import (
    EventData,
    FundamentalData,
    FundamentalsProvider,
    MarketDataProvider,
    NewsProvider,
    PriceMove,
    StockMove,
)


def _stable_float(key: str, low: float, high: float) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    return round(low + (high - low) * raw, 2)


class MockMarketDataProvider(MarketDataProvider):
    def commodity_moves(self, commodity_codes: list[str]) -> dict[str, PriceMove]:
        result = {}
        for code in commodity_codes:
            move = _stable_float(f"commodity:{code}:move", -2.0, 9.0)
            if code in {"copper", "uranium", "natural_gas", "lithium"}:
                move = abs(move) + 2.5
            result[code] = PriceMove(
                code=code,
                move_pct=round(move, 2),
                momentum_pct=_stable_float(f"commodity:{code}:momentum", -4.0, 8.0),
                ma5=None,
                ma20=None,
            )
        return result

    def stock_moves(self, tickers: list[str], benchmark_by_ticker: dict[str, str]) -> dict[str, StockMove]:
        result = {}
        for ticker in tickers:
            stock_return = _stable_float(f"stock:{ticker}:return", -3.0, 4.0)
            benchmark_return = _stable_float(f"bench:{benchmark_by_ticker.get(ticker, 'GLOBAL')}:return", -1.5, 2.0)
            result[ticker] = StockMove(
                ticker=ticker,
                return_pct=stock_return,
                benchmark_return_pct=benchmark_return,
                volume_ratio=_stable_float(f"stock:{ticker}:volume", 0.6, 2.2),
                momentum_pct=_stable_float(f"stock:{ticker}:momentum", -8.0, 14.0),
                last_price=_stable_float(f"stock:{ticker}:price", 10.0, 250000.0),
                week52_high=None,
                week52_low=None,
                ma5=None,
                ma20=None,
            )
        return result


class MockNewsProvider(NewsProvider):
    def events(self, commodity_codes: list[str]) -> list[EventData]:
        events = []
        for code in commodity_codes:
            severity = _stable_float(f"event:{code}:severity", 25.0, 92.0)
            if code in {"copper", "uranium", "natural_gas", "lithium"}:
                severity = max(severity, 72.0)
            if severity >= 55:
                events.append(
                    EventData(
                        commodity_code=code,
                        event_type="supply_disruption",
                        direction="bullish",
                        severity=severity,
                        title=f"{code} supply-demand event detected",
                    )
                )
        return events


class MockFundamentalsProvider(FundamentalsProvider):
    def fundamentals(self, tickers: list[str]) -> dict[str, FundamentalData]:
        result = {}
        for ticker in tickers:
            result[ticker] = FundamentalData(
                ticker=ticker,
                valuation_score=_stable_float(f"fund:{ticker}:valuation", 20.0, 88.0),
                quality_score=_stable_float(f"fund:{ticker}:quality", 30.0, 92.0),
                liquidity_score=_stable_float(f"fund:{ticker}:liquidity", 35.0, 100.0),
                pe=None,
                pb=None,
                ev_ebitda=None,
                roe=None,
                operating_margin=None,
                debt_to_equity=None,
            )
        return result
