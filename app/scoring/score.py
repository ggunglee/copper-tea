from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreInput:
    event_score: float
    commodity_move_pct: float
    exposure_score: float
    exposure_direction: str
    stock_return_pct: float
    benchmark_return_pct: float
    valuation_score: float
    quality_score: float
    liquidity_score: float
    stock_momentum_pct: float
    commodity_momentum_pct: float
    risk_level: str
    position_return_pct: float | None = None


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def buy_score(data: ScoreInput) -> tuple[float, str]:
    excess_return = data.stock_return_pct - data.benchmark_return_pct
    commodity_direction = 1 if data.commodity_move_pct >= 0 else -1
    exposure_alignment = {
        "positive": commodity_direction,
        "negative": -commodity_direction,
        "mixed": 0.65,
        "unclear": 0.25,
    }.get(data.exposure_direction, 0.2)
    direction_multiplier = {
        "positive": 1.0,
        "mixed": 0.7,
        "unclear": 0.35,
        "negative": -0.75,
    }.get(data.exposure_direction, 0.25)
    if exposure_alignment > 0:
        direction_multiplier = abs(direction_multiplier)

    if exposure_alignment <= 0:
        return 0, "Exposure direction is not aligned with the commodity price shock."

    commodity_move_score = clamp(abs(data.commodity_move_pct) * 12)
    underreaction_score = clamp((3.0 - excess_return) * 16 + abs(data.commodity_move_pct) * 5)
    exposure_adjusted = clamp(data.exposure_score * direction_multiplier)
    trend_follow_score = clamp(55 + abs(data.commodity_momentum_pct) * 5)
    momentum_score = clamp(70 - max(data.stock_momentum_pct - 8, 0) * 5)
    risk_penalty = {"low": 0, "medium": 5, "high": 14}.get(data.risk_level, 8)

    score = (
        data.event_score * 0.18
        + commodity_move_score * 0.20
        + exposure_adjusted * 0.20
        + underreaction_score * 0.20
        + data.valuation_score * 0.08
        + data.quality_score * 0.07
        + data.liquidity_score * 0.03
        + trend_follow_score * 0.02
        + momentum_score * 0.02
        - risk_penalty
    )
    if data.exposure_direction == "mixed":
        reason = "원자재 이벤트와 사업 연관성은 있지만, 매출과 원가 영향이 섞일 수 있어 확인이 필요합니다."
    else:
        reason = "원자재 이벤트 강도와 기업 노출도에 비해 주가 반응이 아직 제한적으로 보입니다."
    if data.stock_momentum_pct > 12:
        reason += " 다만 최근 주가 모멘텀이 이미 강해 과열 여부를 함께 봐야 합니다."
    return round(clamp(score), 1), reason


def sell_score(data: ScoreInput) -> tuple[float, str]:
    if data.position_return_pct is None:
        return 0, "No active position."

    excess_return = data.stock_return_pct - data.benchmark_return_pct
    profit_score = clamp(data.position_return_pct * 3.0)
    overreaction_score = clamp((excess_return - 4.0) * 12 + max(data.stock_momentum_pct, 0) * 2)
    valuation_heat_score = clamp(100 - data.valuation_score)
    weakening_commodity_score = clamp((-data.commodity_momentum_pct) * 14 + 40)
    weakening_news_score = clamp(80 - data.event_score)
    risk_reward_score = clamp(data.position_return_pct * 1.5 + valuation_heat_score * 0.6)

    score = (
        profit_score * 0.25
        + overreaction_score * 0.20
        + valuation_heat_score * 0.15
        + weakening_commodity_score * 0.15
        + weakening_news_score * 0.10
        + risk_reward_score * 0.15
    )
    reason = "보유 수익, 시장 대비 움직임, 가격 부담, 원자재 모멘텀 약화를 함께 고려한 점검 신호입니다."
    if valuation_heat_score >= 70:
        reason += " 특히 가격 부담이 커진 편입니다."
    if data.commodity_momentum_pct < 0:
        reason += " 관련 원자재 모멘텀도 약해졌습니다."
    return round(clamp(score), 1), reason
