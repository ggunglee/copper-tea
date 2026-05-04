from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.db.models import Company
from app.providers.base import FundamentalData, StockMove


@dataclass(frozen=True)
class ValueEstimate:
    ticker: str
    company_name: str
    market: str
    currency: str
    current_price: float
    fair_value_price: float
    buy_price: float
    notes: str


def estimate_value_target(
    settings: Settings,
    ticker: str,
    stock: StockMove,
    fund: FundamentalData,
    company: Company | None = None,
    company_name: str = "",
    market: str = "",
    currency: str = "",
    notes: str = "",
) -> ValueEstimate:
    ticker = ticker.upper()
    market = market or (company.market if company else _infer_market(ticker))
    currency = currency or (company.currency if company else _infer_currency(ticker))
    company_name = company_name or (company.company_name if company else ticker)
    sector = company.sector if company else ""
    target_pe, target_pb = _target_multiples(market, sector, notes)

    fair_values = []
    reason_parts = []
    if fund.pe and fund.pe > 0:
        eps = stock.last_price / fund.pe
        pe_value = eps * target_pe
        fair_values.append((pe_value, 0.65))
        reason_parts.append(f"PER {fund.pe:.1f}->목표 {target_pe:g}")
    if fund.pb and fund.pb > 0:
        target_pb = _roe_adjusted_pb(target_pb, fund.roe)
        bps = stock.last_price / fund.pb
        pb_value = bps * target_pb
        fair_values.append((pb_value, 0.35))
        reason_parts.append(f"PBR {fund.pb:.1f}->목표 {target_pb:g}")

    if fair_values:
        total_weight = sum(weight for _, weight in fair_values)
        fair_value = sum(value * weight for value, weight in fair_values) / total_weight
    else:
        fair_value = stock.last_price * 0.9
        reason_parts.append("PER/PBR 부족, 현재가 10% 할인 기준")

    fair_value = _round_price(fair_value, currency)
    buy_price = _round_price(fair_value * 0.9, currency)
    merged_notes = "; ".join(part for part in [notes, ", ".join(reason_parts)] if part)
    return ValueEstimate(
        ticker=ticker,
        company_name=company_name,
        market=market,
        currency=currency,
        current_price=stock.last_price,
        fair_value_price=fair_value,
        buy_price=buy_price,
        notes=merged_notes,
    )


def _infer_market(ticker: str) -> str:
    if ticker.endswith(".KS"):
        return "KR_KOSPI"
    if ticker.endswith(".KQ"):
        return "KR_KOSDAQ"
    return "US"


def _infer_currency(ticker: str) -> str:
    if ticker.endswith((".KS", ".KQ")):
        return "KRW"
    return "USD"


def _target_multiples(market: str, sector: str, notes: str) -> tuple[float, float]:
    text = f"{market} {sector} {notes}".lower()
    if "energy" in text or "refining" in text or "oil" in text:
        return 11.0, 1.6
    if "steel" in text or "mining" in text or "metals" in text or "aluminum" in text:
        return 10.0, 1.1
    if "utility" in text or "dividend" in text or "staple" in text:
        return 17.0, 2.5
    if "battery" in text or "electrical" in text or "power_grid" in text:
        return 18.0, 2.2
    if market.startswith("KR_"):
        return 12.0, 1.3
    return 16.0, 2.4


def _roe_adjusted_pb(target_pb: float, roe: float | None) -> float:
    if roe is None:
        return target_pb
    if roe >= 20:
        return round(target_pb * 1.25, 2)
    if roe >= 12:
        return round(target_pb * 1.1, 2)
    if roe < 5:
        return round(target_pb * 0.75, 2)
    return target_pb


def _round_price(value: float, currency: str) -> float:
    if currency == "KRW":
        if value >= 100000:
            return round(value / 1000) * 1000
        return round(value / 100) * 100
    if value >= 100:
        return round(value, 1)
    return round(value, 2)
