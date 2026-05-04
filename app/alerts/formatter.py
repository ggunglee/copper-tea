from __future__ import annotations

from app.db.models import CandidateSignal, Company, CompanyCommodityExposure, UserPosition, ValuationTarget


def format_signal(signal: CandidateSignal, company: Company, exposure: CompanyCommodityExposure) -> str:
    label = "매수 후보" if signal.signal_type == "buy" else "매도 점검"
    return "\n".join(
        [
            f"[{label}] {signal.commodity_code} / {company.ticker} {company.company_name}",
            "",
            f"종합 점수: {signal.score:.1f}/100",
            f"원자재 변동: {signal.commodity_move_pct:+.1f}%",
            f"주가 반응: {signal.stock_return_pct:+.1f}%",
            f"시장 대비 움직임: {signal.excess_return_pct:+.1f}%",
            f"원자재 관련도: {_exposure_type_label(exposure.exposure_type)} / "
            f"{_direction_label(exposure.exposure_direction)} / {exposure.exposure_score:.0f}점",
            f"가격 부담: {_score_label(signal.valuation_score)}",
            f"기업 체력: {_score_label(signal.quality_score)}",
            f"거래 유동성: {_score_label(signal.liquidity_score)}",
            "",
            f"이유: {signal.reason}",
        ]
    )


def format_position_watch(signal: CandidateSignal, company: Company | None, position: UserPosition) -> str:
    name = company.company_name if company else position.ticker
    return "\n".join(
        [
            f"[보유종목 가격 점검] {position.ticker} {name}",
            "",
            f"점수: {signal.score:.1f}/100",
            f"오늘 주가 변동: {signal.stock_return_pct:+.1f}%",
            f"시장 대비 움직임: {signal.excess_return_pct:+.1f}%",
            f"평균 매입가 대비: {signal.commodity_move_pct:+.1f}%",
            f"평균 매입가: {position.avg_buy_price:g} {position.currency}",
            "",
            f"이유: {signal.reason}",
        ]
    )


def format_valuation_watch(signal: CandidateSignal, target: ValuationTarget) -> str:
    name = target.company_name or target.ticker
    return "\n".join(
        [
            f"[밸류에이션 매수가 근접] {target.ticker} {name}",
            "",
            f"점수: {signal.score:.1f}/100",
            f"현재가: {signal.stock_return_pct:g} {target.currency}",
            f"목표 매수가: {target.buy_price:g} {target.currency}",
            f"적정가: {target.fair_value_price:g} {target.currency}",
            f"매수가 대비: {signal.commodity_move_pct:+.1f}%",
            f"적정가 대비: {signal.excess_return_pct:+.1f}%",
            "",
            f"이유: {signal.reason}",
        ]
    )


def _score_label(score: float) -> str:
    if score >= 80:
        return "매우 좋음"
    if score >= 65:
        return "좋음"
    if score >= 45:
        return "혼재"
    if score >= 30:
        return "나쁨"
    return "매우 나쁨"


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
        "processor": "가공/제련",
        "royalty": "로열티",
        "midstream": "인프라/운송",
        "diversified": "복합 노출",
    }
    return labels.get(exposure_type, exposure_type)
