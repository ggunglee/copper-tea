from __future__ import annotations

import re

from app.db.models import CandidateSignal, Company, CompanyCommodityExposure, UserPosition, ValuationTarget
from app.utils.names import display_company_name


def format_signal(signal: CandidateSignal, company: Company, exposure: CompanyCommodityExposure) -> str:
    label = "매수 후보" if signal.signal_type == "buy" else "매도 점검"
    lines = [
        f"[{label}] {signal.commodity_code} / {company.ticker} {display_company_name(company.ticker, company.company_name)}",
        "",
    ]
    price_line = _price_line(signal, company.currency)
    if price_line:
        lines.append(price_line)
    lines.extend(
        [
            f"원자재 변동: {signal.commodity_move_pct:+.1f}%",
            f"주가 반응: {signal.stock_return_pct:+.1f}%",
            f"시장 대비 괴리: {signal.excess_return_pct:+.1f}%",
            f"가격부담: {_valuation_label(signal.valuation_score)}",
            f"원자재 관련도: {_exposure_type_label(exposure.exposure_type)} / "
            f"{_direction_label(exposure.exposure_direction)}",
            "",
            f"이유: {signal.reason}",
        ]
    )
    return "\n".join(lines)


def format_position_watch(signal: CandidateSignal, company: Company | None, position: UserPosition) -> str:
    name = display_company_name(position.ticker, company.company_name if company else position.ticker)
    lines = [
        f"[보유종목 가격 점검] {position.ticker} {name}",
        "",
    ]
    price_line = _price_line(signal, position.currency)
    if price_line:
        lines.append(price_line)
    lines.extend(
        [
            f"오늘 주가 변동: {signal.stock_return_pct:+.1f}%",
            f"시장 대비 괴리: {signal.excess_return_pct:+.1f}%",
            f"평균 매입가 대비: {signal.commodity_move_pct:+.1f}%",
            f"평균 매입가: {position.avg_buy_price:g} {position.currency}",
            "",
            f"이유: {signal.reason}",
        ]
    )
    return "\n".join(lines)


def format_valuation_watch(signal: CandidateSignal, target: ValuationTarget) -> str:
    name = display_company_name(target.ticker, target.company_name or target.ticker)
    return "\n".join(
        [
            f"[밸류에이션 매수가 근접] {target.ticker} {name}",
            "",
            f"현재가/종가: {signal.stock_return_pct:g} {target.currency}",
            f"목표 매수가: {target.buy_price:g} {target.currency}",
            f"적정가: {target.fair_value_price:g} {target.currency}",
            f"가격부담: {_valuation_label(signal.valuation_score)}",
            f"매수가 대비: {signal.commodity_move_pct:+.1f}%",
            f"적정가 대비: {signal.excess_return_pct:+.1f}%",
            "",
            f"이유: {signal.reason}",
        ]
    )


def _valuation_label(score: float) -> str:
    if score >= 65:
        return "좋음"
    if score >= 45:
        return "보통"
    return "부담"


def _price_line(signal: CandidateSignal, currency: str) -> str:
    price = _current_price(signal)
    if price is None:
        return ""
    return f"현재가/종가: {price:g} {currency}"


def _current_price(signal: CandidateSignal) -> float | None:
    current_price = getattr(signal, "current_price", None)
    if current_price is not None:
        return float(current_price)
    if signal.signal_type == "value":
        return signal.stock_return_pct
    match = re.search(r"현재가\s+([0-9][0-9,]*(?:\.[0-9]+)?)", signal.reason)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _direction_label(direction: str) -> str:
    labels = {
        "positive": "수혜 가능성 높음",
        "mixed": "영향 혼재",
        "negative": "비용 부담 가능성 높음",
        "unclear": "방향 불명확",
    }
    return labels.get(direction, direction)


def _exposure_type_label(exposure_type: str) -> str:
    labels = {
        "producer": "생산자",
        "consumer": "소비자",
        "inventory_holder": "재고 보유",
        "processor": "가공/정련",
        "royalty": "로열티",
        "midstream": "인프라/운송",
        "diversified": "복합 노출",
    }
    return labels.get(exposure_type, exposure_type)
