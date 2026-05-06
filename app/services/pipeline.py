from __future__ import annotations

from datetime import datetime
from statistics import median
import traceback
from zoneinfo import ZoneInfo

from app.alerts.formatter import format_position_watch, format_signal, format_valuation_watch
from app.db.base import Base
from app.alerts.telegram import TelegramClient
from app.config import Settings, get_settings
from app.db.models import AlertHistory, CandidateSignal
from app.db.repositories import (
    create_run,
    finish_run,
    get_active_commodities,
    get_active_companies,
    get_active_positions,
    get_active_valuation_targets,
    get_benchmark_for_market,
    save_alert,
    save_signal,
)
from app.db.session import engine, get_session
from app.providers.factory import fundamentals_provider, market_data_provider, news_provider
from app.scoring.score import ScoreInput, buy_score, sell_score
from app.services.dedup_service import DedupService


STRUCTURAL_EVENT_KEYWORDS = {
    "ban",
    "blockade",
    "closure",
    "conflict",
    "curb",
    "cut",
    "disruption",
    "embargo",
    "export control",
    "export restriction",
    "import control",
    "inventory",
    "mine",
    "policy",
    "quota",
    "sanction",
    "shortage",
    "strike",
    "supply",
    "tariff",
    "war",
}

TEMPORARY_EVENT_KEYWORDS = {
    "forecast",
    "profit taking",
    "technical",
    "weather forecast",
}


def run_pipeline(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    Base.metadata.create_all(bind=engine)
    session = get_session()
    run = create_run(session)
    sent_count = 0
    try:
        commodities = get_active_commodities(session)
        companies = get_active_companies(session)
        positions = {position.ticker: position for position in get_active_positions(session)}
        valuation_targets = get_active_valuation_targets(session)

        commodity_codes = [item.code for item in commodities]
        tickers = sorted({item.ticker for item in companies} | {item.ticker for item in valuation_targets})
        benchmark_by_ticker = {}
        for company in companies:
            benchmark = get_benchmark_for_market(session, company.market)
            benchmark_by_ticker[company.ticker] = benchmark.ticker if benchmark else "GLOBAL"
        for target in valuation_targets:
            if target.ticker not in benchmark_by_ticker:
                benchmark = get_benchmark_for_market(session, target.market)
                benchmark_by_ticker[target.ticker] = benchmark.ticker if benchmark else "URTH"

        market_provider = market_data_provider(settings)
        news = news_provider(settings)
        fundamentals = fundamentals_provider(settings)

        commodity_moves = market_provider.commodity_moves(commodity_codes)
        stock_moves = market_provider.stock_moves(tickers, benchmark_by_ticker)
        fundamental_data = fundamentals.fundamentals(tickers)
        sector_valuation = _sector_valuation_labels(companies, fundamental_data)
        event_by_commodity = {
            event.commodity_code: event
            for event in sorted(news.events(commodity_codes), key=lambda item: item.severity)
        }

        telegram = TelegramClient(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            connect_timeout=settings.telegram_connect_timeout,
            read_timeout=settings.telegram_read_timeout,
            retries=settings.telegram_send_retries,
        )
        dedup = DedupService(settings)

        for company in companies:
            stock = stock_moves.get(company.ticker)
            fund = fundamental_data.get(company.ticker)
            if stock is None or fund is None:
                continue
            for exposure in company.exposures:
                commodity = exposure.commodity
                event = event_by_commodity.get(commodity.code)
                commodity_move = commodity_moves.get(commodity.code)
                if event is None or commodity_move is None:
                    continue
                if not _is_actionable_commodity_signal(settings, commodity_move, event):
                    continue

                score_input = ScoreInput(
                    event_score=event.severity,
                    commodity_move_pct=commodity_move.move_pct,
                    exposure_score=exposure.exposure_score,
                    exposure_direction=exposure.exposure_direction,
                    stock_return_pct=stock.return_pct,
                    benchmark_return_pct=stock.benchmark_return_pct,
                    valuation_score=fund.valuation_score,
                    quality_score=fund.quality_score,
                    liquidity_score=fund.liquidity_score,
                    stock_momentum_pct=stock.momentum_pct,
                    commodity_momentum_pct=commodity_move.momentum_pct,
                    risk_level=company.risk_level,
                    last_price=stock.last_price,
                    week52_high=stock.week52_high,
                    stock_ma5=stock.ma5,
                    stock_ma20=stock.ma20,
                    commodity_ma5=commodity_move.ma5,
                    commodity_ma20=commodity_move.ma20,
                )

                peer_label = sector_valuation.get(company.ticker, "비교 부족")
                detail_lines = [
                    *_commodity_signal_lines(commodity_move, event),
                    *_detail_lines(stock, fund, peer_label),
                    *_evidence_lines(event),
                ]

                buy_value, _ = buy_score(score_input)
                buy_reason = _join_reason_lines([_buy_reason_head(score_input), *detail_lines])
                if buy_value >= settings.min_buy_score and fund.quality_score >= 25 and fund.liquidity_score >= 25:
                    sent_count += _record_and_alert(
                        session, settings, telegram, dedup, run.id, company, exposure, commodity.code, "buy",
                        buy_value, score_input, buy_reason
                    )

                position = positions.get(company.ticker)
                if position and stock.last_price:
                    position_return = ((stock.last_price - position.avg_buy_price) / position.avg_buy_price) * 100
                    sell_input = ScoreInput(**{**score_input.__dict__, "position_return_pct": position_return})
                    sell_value, _ = sell_score(sell_input)
                    sell_reason = _join_reason_lines([_sell_reason_head(sell_input), *detail_lines])
                    if sell_value >= settings.min_sell_score:
                        sent_count += _record_and_alert(
                            session, settings, telegram, dedup, run.id, company, exposure, commodity.code, "sell",
                            sell_value, sell_input, sell_reason
                        )

        company_by_ticker = {company.ticker: company for company in companies}
        for position in positions.values():
            company = company_by_ticker.get(position.ticker)
            if company is None:
                continue
            stock = stock_moves.get(position.ticker)
            if stock is None or not stock.last_price:
                continue
            position_return = ((stock.last_price - position.avg_buy_price) / position.avg_buy_price) * 100
            if (
                abs(position_return) >= settings.position_watch_return_pct
                or abs(stock.return_pct) >= settings.position_watch_daily_pct
            ):
                sent_count += _record_position_watch(
                    session=session,
                    settings=settings,
                    telegram=telegram,
                    dedup=dedup,
                    run_id=run.id,
                    company=company,
                    position=position,
                    stock=stock,
                    position_return=position_return,
                    commodity_moves=commodity_moves,
                    event_by_commodity=event_by_commodity,
                )

        company_by_ticker = {company.ticker: company for company in companies}
        for target in valuation_targets:
            stock = stock_moves.get(target.ticker)
            fund = fundamental_data.get(target.ticker)
            if stock is None or not stock.last_price or fund is None:
                continue
            sent_count += _record_valuation_watch(
                session=session,
                telegram=telegram,
                dedup=dedup,
                run_id=run.id,
                target=target,
                company=company_by_ticker.get(target.ticker),
                stock=stock,
                fund=fund,
            )

        finish_run(session, run, "success", provider_status="ok")
        if sent_count == 0 and settings.telegram_notify_run_summary:
            _send_or_raise(settings, telegram, _format_zero_alert_summary(settings, len(companies), len(valuation_targets)))
        return sent_count
    except Exception as exc:
        finish_run(session, run, "failed", error=f"{exc}\n{traceback.format_exc()}")
        raise
    finally:
        session.close()


def _record_and_alert(
    session,
    settings: Settings,
    telegram: TelegramClient,
    dedup: DedupService,
    run_id: int,
    company,
    exposure,
    commodity_code: str,
    signal_type: str,
    score: float,
    score_input: ScoreInput,
    reason: str,
) -> int:
    excess = score_input.stock_return_pct - score_input.benchmark_return_pct
    signal = CandidateSignal(
        run_id=run_id,
        ticker=company.ticker,
        commodity_code=commodity_code,
        signal_type=signal_type,
        score=score,
        event_score=score_input.event_score,
        commodity_move_pct=score_input.commodity_move_pct,
        stock_return_pct=score_input.stock_return_pct,
        benchmark_return_pct=score_input.benchmark_return_pct,
        excess_return_pct=excess,
        valuation_score=score_input.valuation_score,
        quality_score=score_input.quality_score,
        liquidity_score=score_input.liquidity_score,
        momentum_score=score_input.stock_momentum_pct,
        reason=reason,
    )
    save_signal(session, signal)
    signal.current_price = score_input.last_price

    if not dedup.should_alert(session, signal_type, company.ticker, commodity_code, score):
        return 0

    message = format_signal(signal, company, exposure)
    if not _send_or_raise(settings, telegram, message):
        return 0
    save_alert(
        session,
        AlertHistory(
            run_id=run_id,
            ticker=company.ticker,
            commodity_code=commodity_code,
            signal_type=signal_type,
            score=score,
            alert_key=dedup.alert_key(signal_type, company.ticker, commodity_code, score),
            message=message,
        ),
    )
    return 1


def _record_position_watch(
    session,
    settings: Settings,
    telegram: TelegramClient,
    dedup: DedupService,
    run_id: int,
    company,
    position,
    stock,
    position_return: float,
    commodity_moves,
    event_by_commodity,
) -> int:
    excess = stock.return_pct - stock.benchmark_return_pct
    score = min(100, max(abs(position_return) * 4, abs(stock.return_pct) * 18))
    reason = _join_reason_lines(
        [
            *_position_summary_lines(stock, position_return),
            f"오늘 주가 {stock.return_pct:+.1f}%",
            f"시장 대비 {excess:+.1f}%",
            f"내 수익률 {position_return:+.1f}%",
            *_price_lines(stock),
            *_position_commodity_lines(company, commodity_moves, event_by_commodity),
        ]
    )
    signal = CandidateSignal(
        run_id=run_id,
        ticker=position.ticker,
        commodity_code="portfolio",
        signal_type="position",
        score=round(score, 1),
        event_score=0,
        commodity_move_pct=position_return,
        stock_return_pct=stock.return_pct,
        benchmark_return_pct=stock.benchmark_return_pct,
        excess_return_pct=excess,
        valuation_score=0,
        quality_score=0,
        liquidity_score=0,
        momentum_score=stock.momentum_pct,
        reason=reason,
    )
    save_signal(session, signal)
    signal.current_price = stock.last_price

    if not dedup.should_alert(session, "position", position.ticker, "portfolio", signal.score):
        return 0

    message = format_position_watch(signal, company, position)
    if not _send_or_raise(settings, telegram, message):
        return 0
    save_alert(
        session,
        AlertHistory(
            run_id=run_id,
            ticker=position.ticker,
            commodity_code="portfolio",
            signal_type="position",
            score=signal.score,
            alert_key=dedup.alert_key("position", position.ticker, "portfolio", signal.score),
            message=message,
        ),
    )
    return 1


def _record_valuation_watch(
    session,
    telegram: TelegramClient,
    dedup: DedupService,
    run_id: int,
    target,
    company,
    stock,
    fund,
) -> int:
    buy_gap = ((stock.last_price - target.buy_price) / target.buy_price) * 100
    fair_gap = ((stock.last_price - target.fair_value_price) / target.fair_value_price) * 100
    if buy_gap > target.alert_buffer_pct:
        return 0

    score = min(100, max(45, (target.alert_buffer_pct - buy_gap) * 10 + fund.valuation_score * 0.45))
    multiples = []
    if fund.pe is not None:
        multiples.append(f"PER {fund.pe:.1f}")
    if fund.pb is not None:
        multiples.append(f"PBR {fund.pb:.1f}")
    if fund.roe is not None:
        multiples.append(f"ROE {fund.roe:.1f}%")
    reason_lines = [
        f"현재가가 목표 매수가 기준 {buy_gap:+.1f}% 위치입니다.",
        f"적정가 기준으로는 {fair_gap:+.1f}% 위치입니다.",
    ]
    if multiples:
        reason_lines.append("현재 지표: " + ", ".join(multiples))
    if target.notes:
        reason_lines.append(f"기준 메모: {target.notes}")
    if company:
        reason_lines.append(f"기존 감시 섹터: {company.sector}")

    signal = CandidateSignal(
        run_id=run_id,
        ticker=target.ticker,
        commodity_code="valuation",
        signal_type="value",
        score=round(score, 1),
        event_score=0,
        commodity_move_pct=buy_gap,
        stock_return_pct=stock.last_price,
        benchmark_return_pct=target.buy_price,
        excess_return_pct=fair_gap,
        valuation_score=fund.valuation_score,
        quality_score=fund.quality_score,
        liquidity_score=fund.liquidity_score,
        momentum_score=stock.momentum_pct,
        reason=_join_reason_lines(reason_lines),
    )
    save_signal(session, signal)
    signal.current_price = stock.last_price

    if not dedup.should_alert(session, "value", target.ticker, "valuation", signal.score):
        return 0
    message = format_valuation_watch(signal, target)
    if not _send_or_raise(settings, telegram, message):
        return 0
    save_alert(
        session,
        AlertHistory(
            run_id=run_id,
            ticker=target.ticker,
            commodity_code="valuation",
            signal_type="value",
            score=signal.score,
            alert_key=dedup.alert_key("value", target.ticker, "valuation", signal.score),
            message=message,
        ),
    )
    return 1


def _send_or_raise(settings: Settings, telegram: TelegramClient, message: str) -> bool:
    sent = telegram.send(message)
    if not sent and settings.telegram_fail_on_send_error and telegram.enabled:
        raise RuntimeError("Telegram send failed. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    return sent


def _format_zero_alert_summary(settings: Settings, company_count: int, valuation_count: int) -> str:
    now = datetime.now(ZoneInfo(settings.app_timezone)).strftime("%Y-%m-%d %H:%M")
    return "\n".join(
        [
            "[Copper Tea 점검 완료]",
            "",
            f"기준 시각: {now} {settings.app_timezone}",
            "신규 알림: 없음",
            f"활성 워치리스트: {company_count}개",
            f"밸류에이션 감시: {valuation_count}개",
            f"매수 기준: {settings.min_buy_score:g}",
            f"매도 기준: {settings.min_sell_score:g}",
        ]
    )


def _buy_reason_head(score_input: ScoreInput) -> str:
    direction = "급등" if score_input.commodity_move_pct >= 0 else "급락"
    if score_input.exposure_direction == "negative":
        return f"원자재 {direction}이 비용 구조에 유리한 방향이라 후보로 검토합니다."
    if score_input.exposure_direction == "mixed":
        return f"원자재 {direction}의 영향이 혼재되어 있어 추가 확인이 필요합니다."
    return f"원자재 {direction} 신호 대비 주가 반응이 아직 제한적입니다."


def _sell_reason_head(score_input: ScoreInput) -> str:
    lines = []
    if score_input.commodity_momentum_pct < 0:
        lines.append("관련 원자재 모멘텀 약화.")
    if score_input.valuation_score < 35:
        lines.append("가격 부담 확대.")
    if not lines:
        lines.append("보유 수익과 시장 대비 움직임 점검.")
    return " ".join(lines)


def _position_summary_lines(stock, position_return: float) -> list[str]:
    if stock.return_pct >= 5:
        summary = "요약: 오늘 급등."
    elif stock.return_pct <= -5:
        summary = "요약: 오늘 급락."
    elif position_return >= 15:
        summary = "요약: 수익권 확대."
    elif position_return <= -10:
        summary = "요약: 손실 확대."
    else:
        summary = "요약: 보유종목 변동 점검."

    if _near_52w_high(stock):
        summary += " 현재 52주 고점 부근."
    elif _near_52w_low(stock):
        summary += " 현재 52주 저점 부근."

    point = "점검 포인트: "
    if stock.return_pct >= 5 or _near_52w_high(stock):
        point += "단기 과열 여부와 차익실현 기준 확인."
    elif stock.return_pct <= -5:
        point += "하락 배경과 손절/추가매수 기준 확인."
    else:
        point += "보유 지속 기준 확인."
    return [summary, point]


def _position_commodity_lines(company, commodity_moves, event_by_commodity) -> list[str]:
    ranked = []
    for exposure in company.exposures:
        code = exposure.commodity.code
        move = commodity_moves.get(code)
        event = event_by_commodity.get(code)
        move_pct = move.move_pct if move else 0.0
        event_score = event.severity if event else 0.0
        rank_score = exposure.exposure_score * (abs(move_pct) + event_score / 10)
        ranked.append((rank_score, exposure, move_pct, event))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return []

    lines = []
    top = ranked[0]
    _, exposure, move_pct, event = top
    lines.append(
        "가능한 원자재 배경: "
        f"{exposure.commodity.code} {move_pct:+.1f}%, "
        f"{_exposure_type_label(exposure.exposure_type)} / {_direction_label(exposure.exposure_direction)}"
    )
    if event:
        lines.extend(_evidence_lines(event))

    other = ranked[1:3]
    if other:
        parts = [
            f"{item[1].commodity.code}({_direction_label(item[1].exposure_direction)})"
            for item in other
        ]
        lines.append("기타 노출: " + ", ".join(parts))
    return lines


def _detail_lines(stock, fund, peer_label: str) -> list[str]:
    lines = [*_price_lines(stock)]
    multiples = []
    if fund.pe is not None:
        multiples.append(f"PER {fund.pe:.1f}")
    if fund.pb is not None:
        multiples.append(f"PBR {fund.pb:.1f}")
    if fund.ev_ebitda is not None:
        multiples.append(f"EV/EBITDA {fund.ev_ebitda:.1f}")
    if fund.roe is not None:
        multiples.append(f"ROE {fund.roe:.1f}%")
    if multiples:
        lines.append("주요 지표: " + ", ".join(multiples))
    lines.append(f"PER/PBR 동종업계 {peer_label}")
    return lines


def _evidence_lines(event) -> list[str]:
    if event.source == "mock":
        return []

    titles = list(event.evidence_titles or ())
    urls = list(event.evidence_urls or ())
    if not titles and event.title:
        titles = [event.title]
        urls = [event.url]
    if not titles:
        return []

    lines = ["근거: 가격 변동의 원인으로 단정하지 않고, 같은 기간 확인된 관련 뉴스입니다."]
    for index, title in enumerate(titles[:3], start=1):
        url = urls[index - 1] if index - 1 < len(urls) else ""
        if url:
            lines.append(f"근거 뉴스 {index}: {title} / {url}")
        else:
            lines.append(f"근거 뉴스 {index}: {title}")
    return lines


def _price_lines(stock) -> list[str]:
    lines = []
    if stock.last_price:
        lines.append(f"현재가 {stock.last_price:g}")
    if stock.last_price and stock.week52_high and stock.week52_high > 0:
        below_high = ((stock.last_price - stock.week52_high) / stock.week52_high) * 100
        lines.append(f"52주 고점 대비 {below_high:+.1f}%")
    if stock.last_price and stock.week52_low and stock.week52_low > 0:
        above_low = ((stock.last_price - stock.week52_low) / stock.week52_low) * 100
        lines.append(f"52주 저점 대비 {above_low:+.1f}%")
    return lines


def _near_52w_high(stock) -> bool:
    if not stock.last_price or not stock.week52_high:
        return False
    return stock.last_price >= stock.week52_high * 0.97


def _near_52w_low(stock) -> bool:
    if not stock.last_price or not stock.week52_low:
        return False
    return stock.last_price <= stock.week52_low * 1.10


def _direction_label(direction: str) -> str:
    return {
        "positive": "수혜 가능성 높음",
        "mixed": "영향 혼재",
        "negative": "비용 부담 가능성 높음",
        "unclear": "방향 불명확",
    }.get(direction, direction)


def _exposure_type_label(exposure_type: str) -> str:
    return {
        "producer": "생산자",
        "consumer": "소비자",
        "inventory_holder": "재고 보유",
        "processor": "가공/제련",
        "royalty": "로열티",
        "midstream": "인프라/운송",
        "diversified": "복합 노출",
    }.get(exposure_type, exposure_type)


def _join_reason_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _is_actionable_commodity_signal(settings: Settings, move, event) -> bool:
    daily_shock = abs(move.move_pct) >= settings.commodity_shock_daily_pct
    same_direction_trend = (
        abs(move.momentum_pct) >= settings.commodity_trend_momentum_pct
        and move.move_pct * move.momentum_pct > 0
    )
    structural_event = event.severity >= settings.commodity_structural_event_score and _has_structural_event(event)
    return daily_shock and (same_direction_trend or structural_event)


def _has_structural_event(event) -> bool:
    text = f"{event.event_type} {event.title}".lower()
    if any(word in text for word in TEMPORARY_EVENT_KEYWORDS):
        return False
    return any(word in text for word in STRUCTURAL_EVENT_KEYWORDS)


def _commodity_signal_lines(move, event) -> list[str]:
    direction = "급등" if move.move_pct >= 0 else "급락"
    lines = [
        f"원자재 신호: {direction} {move.move_pct:+.1f}%, 추세 {move.momentum_pct:+.1f}%",
    ]
    if event.source != "mock" and event.title:
        lines.append(f"구조적 배경: {event.title}")
    return lines


def _sector_valuation_labels(companies, fundamental_data) -> dict[str, str]:
    scores_by_sector: dict[str, list[float]] = {}
    for company in companies:
        fund = fundamental_data.get(company.ticker)
        if fund is None:
            continue
        scores_by_sector.setdefault(company.sector, []).append(fund.valuation_score)

    medians = {
        sector: median(scores)
        for sector, scores in scores_by_sector.items()
        if len(scores) >= 2
    }

    labels = {}
    for company in companies:
        fund = fundamental_data.get(company.ticker)
        sector_median = medians.get(company.sector)
        if fund is None or sector_median is None:
            labels[company.ticker] = "비교 부족"
            continue
        diff = fund.valuation_score - sector_median
        if diff >= 10:
            labels[company.ticker] = "저평가"
        elif diff <= -10:
            labels[company.ticker] = "고평가"
        else:
            labels[company.ticker] = "비슷"
    return labels
