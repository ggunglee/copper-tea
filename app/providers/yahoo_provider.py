from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

import requests

from app.providers.base import FundamentalData, FundamentalsProvider, MarketDataProvider, PriceMove, StockMove
from app.providers.mock_provider import MockFundamentalsProvider, MockMarketDataProvider


COMMODITY_SYMBOLS = {
    "copper": "HG=F",
    "natural_gas": "NG=F",
    "crude_oil": "CL=F",
    "gold": "GC=F",
    "silver": "SI=F",
    "aluminum": "ALI=F",
    "steel": "SLX",
    "iron_ore": "TIO=F",
    "coal": "MTF=F",
    "uranium": "URA",
    "lithium": "LIT",
    "nickel": "NICK.L",
    "fertilizer": "MOO",
    "rare_earths": "REMX",
}


class YahooMarketDataProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.fallback = MockMarketDataProvider()

    def commodity_moves(self, commodity_codes: list[str]) -> dict[str, PriceMove]:
        fallback = self.fallback.commodity_moves(commodity_codes)
        result = {}
        for code in commodity_codes:
            symbol = COMMODITY_SYMBOLS.get(code)
            if not symbol:
                result[code] = fallback[code]
                continue
            move = self._move_for_symbol(symbol)
            result[code] = PriceMove(
                code=code,
                move_pct=move[0] if move else fallback[code].move_pct,
                momentum_pct=move[1] if move else fallback[code].momentum_pct,
                ma5=move[6] if move else fallback[code].ma5,
                ma20=move[7] if move else fallback[code].ma20,
            )
        return result

    def stock_moves(self, tickers: list[str], benchmark_by_ticker: dict[str, str]) -> dict[str, StockMove]:
        fallback = self.fallback.stock_moves(tickers, benchmark_by_ticker)
        result = {}
        benchmark_cache: dict[str, tuple[float, float, float, float, float, float, float | None, float | None] | None] = {}
        for ticker in tickers:
            move = self._move_for_symbol(ticker, days=260)
            if not move:
                result[ticker] = fallback[ticker]
                continue
            benchmark = benchmark_by_ticker.get(ticker, "URTH")
            if benchmark not in benchmark_cache:
                benchmark_cache[benchmark] = self._move_for_symbol(benchmark)
            benchmark_move = benchmark_cache[benchmark]
            result[ticker] = StockMove(
                ticker=ticker,
                return_pct=move[0],
                benchmark_return_pct=benchmark_move[0] if benchmark_move else fallback[ticker].benchmark_return_pct,
                volume_ratio=move[3],
                momentum_pct=move[1],
                last_price=move[2],
                week52_high=move[4],
                week52_low=move[5],
                ma5=move[6],
                ma20=move[7],
            )
        return result

    def _move_for_symbol(
        self, symbol: str, days: int = 45
    ) -> tuple[float, float, float, float, float, float, float | None, float | None] | None:
        prices = self._chart(symbol, days=days)
        if len(prices) < 2:
            return None
        last = prices[-1]
        prev = prices[-2]
        first = prices[0]
        if prev["close"] <= 0 or first["close"] <= 0:
            return None
        return_pct = ((last["close"] - prev["close"]) / prev["close"]) * 100
        momentum_pct = ((last["close"] - first["close"]) / first["close"]) * 100
        avg_volume = sum(item["volume"] for item in prices[:-1]) / max(len(prices) - 1, 1)
        volume_ratio = last["volume"] / avg_volume if avg_volume else 1.0
        closes = [item["close"] for item in prices]
        week52_high = max(closes)
        week52_low = min(closes)
        ma5 = _moving_average(closes, 5)
        ma20 = _moving_average(closes, 20)
        return (
            round(return_pct, 2),
            round(momentum_pct, 2),
            round(last["close"], 4),
            round(volume_ratio, 2),
            round(week52_high, 4),
            round(week52_low, 4),
            round(ma5, 4) if ma5 is not None else None,
            round(ma20, 4) if ma20 is not None else None,
        )

    def _chart(self, symbol: str, days: int) -> list[dict[str, float]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days * 2)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        response = self.session.get(
            url,
            params={
                "period1": int(start.timestamp()),
                "period2": int(end.timestamp()),
                "interval": "1d",
                "events": "history",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        adjclose = result["indicators"].get("adjclose", [{}])[0].get("adjclose") or quote.get("close")
        rows = []
        for close, volume in zip(adjclose or [], quote.get("volume") or []):
            if close is None or not isfinite(float(close)):
                continue
            rows.append({"close": float(close), "volume": float(volume or 0)})
        return rows[-days:]


class YahooFundamentalsProvider(FundamentalsProvider):
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.fallback = MockFundamentalsProvider()

    def fundamentals(self, tickers: list[str]) -> dict[str, FundamentalData]:
        fallback = self.fallback.fundamentals(tickers)
        result = {}
        for ticker in tickers:
            data = self._quote_summary(ticker)
            if data is None:
                result[ticker] = fallback[ticker]
                continue
            result[ticker] = FundamentalData(
                ticker=ticker,
                valuation_score=self._valuation_score(data, fallback[ticker].valuation_score),
                quality_score=self._quality_score(data, fallback[ticker].quality_score),
                liquidity_score=self._liquidity_score(data, fallback[ticker].liquidity_score),
                pe=_raw(data, "summaryDetail", "trailingPE"),
                pb=_raw(data, "defaultKeyStatistics", "priceToBook"),
                ev_ebitda=_raw(data, "defaultKeyStatistics", "enterpriseToEbitda"),
                roe=_percent_raw(data, "financialData", "returnOnEquity"),
                operating_margin=_percent_raw(data, "financialData", "operatingMargins"),
                debt_to_equity=_raw(data, "financialData", "debtToEquity"),
            )
        return result

    def _quote_summary(self, ticker: str) -> dict[str, Any] | None:
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
        response = self.session.get(
            url,
            params={"modules": "summaryDetail,defaultKeyStatistics,financialData,price"},
            timeout=20,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()
        results = payload.get("quoteSummary", {}).get("result") or []
        return results[0] if results else None

    def _valuation_score(self, data: dict[str, Any], default: float) -> float:
        pe = _raw(data, "summaryDetail", "trailingPE")
        pb = _raw(data, "defaultKeyStatistics", "priceToBook")
        ev_ebitda = _raw(data, "defaultKeyStatistics", "enterpriseToEbitda")
        scores = []
        if pe and pe > 0:
            scores.append(_inverse_score(pe, good=10, bad=35))
        if pb and pb > 0:
            scores.append(_inverse_score(pb, good=1, bad=5))
        if ev_ebitda and ev_ebitda > 0:
            scores.append(_inverse_score(ev_ebitda, good=6, bad=18))
        return round(sum(scores) / len(scores), 1) if scores else default

    def _quality_score(self, data: dict[str, Any], default: float) -> float:
        roe = _raw(data, "financialData", "returnOnEquity")
        margin = _raw(data, "financialData", "operatingMargins")
        debt_to_equity = _raw(data, "financialData", "debtToEquity")
        scores = []
        if roe is not None:
            scores.append(_linear_score(roe * 100, good=15, bad=0))
        if margin is not None:
            scores.append(_linear_score(margin * 100, good=18, bad=0))
        if debt_to_equity is not None:
            scores.append(_inverse_score(debt_to_equity, good=50, bad=250))
        return round(sum(scores) / len(scores), 1) if scores else default

    def _liquidity_score(self, data: dict[str, Any], default: float) -> float:
        volume = _raw(data, "price", "regularMarketVolume")
        price = _raw(data, "price", "regularMarketPrice")
        if not volume or not price:
            return default
        traded_value = volume * price
        return round(_linear_score(traded_value, good=100_000_000, bad=2_000_000), 1)


def _raw(data: dict[str, Any], module: str, key: str) -> float | None:
    value = data.get(module, {}).get(key)
    if isinstance(value, dict):
        value = value.get("raw")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percent_raw(data: dict[str, Any], module: str, key: str) -> float | None:
    value = _raw(data, module, key)
    return round(value * 100, 2) if value is not None else None


def _moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    sample = values[-window:]
    return sum(sample) / window


def _linear_score(value: float, good: float, bad: float) -> float:
    if good == bad:
        return 50.0
    return max(0.0, min(100.0, ((value - bad) / (good - bad)) * 100))


def _inverse_score(value: float, good: float, bad: float) -> float:
    if good == bad:
        return 50.0
    return max(0.0, min(100.0, ((bad - value) / (bad - good)) * 100))
