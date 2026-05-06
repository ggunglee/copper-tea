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
    last_price: float | None = None
    week52_high: float | None = None
    stock_ma5: float | None = None
    stock_ma20: float | None = None
    commodity_ma5: float | None = None
    commodity_ma20: float | None = None


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

    commodity_move_score = clamp(max(data.commodity_move_pct, 0) * 14)
    commodity_trend_score = clamp(max(data.commodity_momentum_pct, 0) * 12)
    ma_confirmation_score = 55.0
    if data.commodity_ma5 is not None and data.commodity_ma20 is not None:
        ma_confirmation_score = 85.0 if data.commodity_ma5 >= data.commodity_ma20 else 35.0

    underreaction_score = clamp((2.5 - excess_return) * 20 + max(data.commodity_move_pct, 0) * 8)
    if data.commodity_momentum_pct > 0 and excess_return <= 0:
        underreaction_score = clamp(underreaction_score + 25)
    elif data.commodity_momentum_pct > 0 and excess_return <= 1.5:
        underreaction_score = clamp(underreaction_score + 12)

    exposure_adjusted = clamp(data.exposure_score * direction_multiplier)
    trend_follow_score = clamp(45 + max(data.commodity_momentum_pct, 0) * 8)
    momentum_score = clamp(70 - max(data.stock_momentum_pct - 8, 0) * 5)
    if data.stock_ma5 is not None and data.stock_ma20 is not None and data.stock_ma5 < data.stock_ma20:
        momentum_score = clamp(momentum_score + 8)
    risk_penalty = {"low": 0, "medium": 5, "high": 14}.get(data.risk_level, 8)

    score = (
        data.event_score * 0.18
        + commodity_move_score * 0.17
        + commodity_trend_score * 0.10
        + exposure_adjusted * 0.17
        + underreaction_score * 0.27
        + data.valuation_score * 0.08
        + data.quality_score * 0.07
        + data.liquidity_score * 0.03
        + trend_follow_score * 0.02
        + momentum_score * 0.02
        + ma_confirmation_score * 0.04
        - risk_penalty
    )
    if data.commodity_momentum_pct <= 0:
        score *= 0.65

    reason = "Commodity momentum and stock-benchmark divergence are being scored together."
    if data.commodity_momentum_pct > 0 and excess_return <= 0:
        reason += " Commodity momentum is positive while the stock is lagging its benchmark, so divergence is elevated."
    if data.stock_momentum_pct > 12:
        reason += " Stock momentum is already hot, so chase risk is higher."
    return round(clamp(score), 1), reason


def sell_score(data: ScoreInput) -> tuple[float, str]:
    if data.position_return_pct is None:
        return 0, "No active position."

    excess_return = data.stock_return_pct - data.benchmark_return_pct
    drawdown_pct = 0.0
    if data.last_price and data.week52_high and data.week52_high > 0:
        drawdown_pct = max(0.0, ((data.week52_high - data.last_price) / data.week52_high) * 100)

    profit_score = clamp(data.position_return_pct * 3.0)
    overreaction_score = clamp((excess_return - 4.0) * 12 + max(data.stock_momentum_pct, 0) * 2)
    valuation_heat_score = clamp(100 - data.valuation_score)
    weakening_commodity_score = clamp((-data.commodity_momentum_pct) * 14 + 40)
    weakening_news_score = clamp(80 - data.event_score)
    risk_reward_score = clamp(data.position_return_pct * 1.5 + valuation_heat_score * 0.6)
    trailing_stop_score = clamp((drawdown_pct - 4.0) * 13 + max(data.position_return_pct - 8.0, 0) * 2.5)

    ma_break_score = 0.0
    if data.stock_ma5 is not None and data.stock_ma20 is not None and data.stock_ma5 < data.stock_ma20:
        ma_break_score += 35
    if data.commodity_ma5 is not None and data.commodity_ma20 is not None and data.commodity_ma5 < data.commodity_ma20:
        ma_break_score += 35
    ma_break_score = clamp(ma_break_score)

    score = (
        profit_score * 0.18
        + overreaction_score * 0.14
        + valuation_heat_score * 0.12
        + weakening_commodity_score * 0.18
        + weakening_news_score * 0.10
        + risk_reward_score * 0.12
        + trailing_stop_score * 0.18
        + ma_break_score * 0.08
    )
    if data.position_return_pct >= 10 and (drawdown_pct >= 6 or data.commodity_momentum_pct <= -3):
        score = max(score, 72)
    if data.position_return_pct >= 18 and (drawdown_pct >= 4 or data.commodity_momentum_pct <= 0):
        score = max(score, 78)

    reason = "Position profit, divergence heat, commodity slowdown, and trailing-stop pressure are being scored together."
    if drawdown_pct >= 4:
        reason += f" Trailing stop pressure is active after a {drawdown_pct:.1f}% pullback from the recent high."
    if valuation_heat_score >= 70:
        reason += " Valuation is stretched."
    if data.commodity_momentum_pct < 0:
        reason += " Related commodity momentum has weakened."
    return round(clamp(score), 1), reason
