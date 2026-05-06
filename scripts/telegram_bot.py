from __future__ import annotations

import time

import requests
from requests import RequestException
from sqlalchemy import select

from app.config import get_settings
from app.db.base import Base
from app.db.models import Benchmark, Commodity, Company, CompanyCommodityExposure, UserPosition, ValuationTarget
from app.db.session import engine, get_session
from app.providers.factory import fundamentals_provider, market_data_provider
from app.services.pipeline import run_pipeline
from app.services.value_estimator import estimate_value_target
from app.utils.names import display_company_name


HELP = """명령어
/positions - 보유종목 목록
/add_position - 보유종목 대화형 등록
/remove_position 티커 - 보유종목 삭제
/watch_buy - 매수 감시 목록
/watch_kr - 한국 매수 감시 목록
/watch_sell - 매도 감시 목록
/add_watch - 감시종목 대화형 등록
/add_watch 티커 / 회사명 / 시장 / 섹터 - 감시종목 한 줄 등록
/add_watch_bulk - 감시종목 여러 줄 등록
/remove_watch 티커 - 감시종목 삭제
/value_targets - 적정가 감시 목록
/add_value 티커 / 회사명 / 시장 / 적정가 / 매수가 / 통화 / 메모
/add_value_bulk - 적정가 감시 여러 줄 등록
/add_value_auto 티커 - PER/PBR 기반 적정가 자동 등록
/estimate_value 티커 - PER/PBR 기반 적정가 계산만 확인
/remove_value 티커 - 적정가 감시 삭제
/run - 즉시 실행
/cancel - 입력 취소
"""

SESSIONS: dict[str, dict] = {}
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
SEND_RETRIES = 3


def main() -> None:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    global CONNECT_TIMEOUT, READ_TIMEOUT, SEND_RETRIES
    CONNECT_TIMEOUT = settings.telegram_connect_timeout
    READ_TIMEOUT = settings.telegram_read_timeout
    SEND_RETRIES = settings.telegram_send_retries
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")
    offset = None
    while True:
        try:
            updates = _get_updates(settings.telegram_bot_token, offset)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = (message.get("text") or "").strip()
                if chat_id != str(settings.telegram_chat_id) or not text:
                    continue
                _send(settings.telegram_bot_token, chat_id, handle_message(chat_id, text))
        except Exception as exc:
            print(f"telegram bot loop failed: {exc}")
            time.sleep(10)
        time.sleep(2)


def handle_message(chat_id: str, text: str) -> str:
    if text == "/cancel":
        SESSIONS.pop(chat_id, None)
        return "입력을 취소했습니다."
    if chat_id in SESSIONS and not text.startswith("/"):
        return _continue_flow(chat_id, text)

    parts = text.split()
    command = parts[0].lower()
    if command in {"/start", "/help"}:
        return HELP
    if command == "/positions":
        return _positions()
    if command == "/add_position":
        if len(parts) >= 5:
            return _save_position(parts[1], parts[2], parts[3], parts[4])
        SESSIONS[chat_id] = {"flow": "add_position", "step": "ticker", "data": {}}
        return "티커를 입력하세요. 예: 005490.KS 또는 FCX"
    if command == "/remove_position":
        if len(parts) < 2:
            return "형식: /remove_position 티커"
        return _remove_position(parts[1])
    if command == "/watch_buy":
        return _watch_buy()
    if command == "/watch_kr":
        return _watch_buy(markets={"KR_KOSPI", "KR_KOSDAQ"})
    if command == "/watch_sell":
        return _watch_sell()
    if command == "/add_watch":
        inline_text = text.removeprefix(parts[0]).strip()
        if inline_text:
            return _save_watch_inline(inline_text)
        SESSIONS[chat_id] = {"flow": "add_watch", "step": "ticker", "data": {}}
        return "감시할 티커를 입력하세요. 예: XOM 또는 005490.KS"
    if command == "/add_watch_bulk":
        inline_text = text.removeprefix(parts[0]).strip()
        if inline_text:
            return _save_watch_bulk(inline_text)
        SESSIONS[chat_id] = {"flow": "add_watch_bulk"}
        return "여러 줄로 입력하세요. 예:\n010120.KS / LS ELECTRIC / KR_KOSPI / electrical_equipment_power_grid"
    if command == "/remove_watch":
        if len(parts) < 2:
            return "형식: /remove_watch 티커"
        return _remove_watch(parts[1])
    if command in {"/remove", "/remove_all"}:
        keyword = text.removeprefix(parts[0]).strip()
        if not keyword:
            return "형식: /remove keyword"
        return _remove_all(keyword)
    if command == "/value_targets":
        return _value_targets()
    if command == "/add_value":
        inline_text = text.removeprefix(parts[0]).strip()
        if inline_text:
            return _save_value_inline(inline_text)
        SESSIONS[chat_id] = {"flow": "add_value_bulk"}
        return "한 줄 이상 입력하세요. 예:\nKO / 코카콜라 / US / 65 / 58 / USD / 배당주"
    if command == "/add_value_bulk":
        inline_text = text.removeprefix(parts[0]).strip()
        if inline_text:
            return _save_value_bulk(inline_text)
        SESSIONS[chat_id] = {"flow": "add_value_bulk"}
        return "여러 줄로 입력하세요. 예:\nKO / 코카콜라 / US / 65 / 58 / USD / 배당주"
    if command == "/add_value_auto":
        if len(parts) < 2:
            return "형식: /add_value_auto 티커"
        return _save_value_auto(text.removeprefix(parts[0]).strip())
    if command == "/estimate_value":
        if len(parts) < 2:
            return "형식: /estimate_value 티커"
        return _estimate_value_text(text.removeprefix(parts[0]).strip(), save=False)
    if command == "/remove_value":
        if len(parts) < 2:
            return "형식: /remove_value 티커"
        return _remove_value(parts[1])
    if command == "/report":
        return _report()
    if command == "/run":
        sent = run_pipeline()
        return f"실행 완료. 알림 {sent}개 발송."
    return "알 수 없는 명령입니다.\n\n" + HELP


def _continue_flow(chat_id: str, text: str) -> str:
    session = SESSIONS[chat_id]
    if session["flow"] == "add_position":
        return _continue_add_position(chat_id, text)
    if session["flow"] == "add_watch":
        return _continue_add_watch(chat_id, text)
    if session["flow"] == "add_watch_bulk":
        response = _save_watch_bulk(text)
        SESSIONS.pop(chat_id, None)
        return response
    if session["flow"] == "add_value_bulk":
        response = _save_value_bulk(text)
        SESSIONS.pop(chat_id, None)
        return response
    SESSIONS.pop(chat_id, None)
    return "입력 상태가 꼬여서 취소했습니다."


def _continue_add_position(chat_id: str, text: str) -> str:
    state = SESSIONS[chat_id]
    data = state["data"]
    step = state["step"]
    if step == "ticker":
        data["ticker"] = text.upper()
        state["step"] = "quantity"
        return "수량을 입력하세요. 예: 70"
    if step == "quantity":
        data["quantity"] = text
        state["step"] = "avg_price"
        return "평균 매입가를 입력하세요. 콤마가 있어도 됩니다. 예: 14932"
    if step == "avg_price":
        data["avg_price"] = text
        state["step"] = "currency"
        return "통화를 입력하세요. 예: KRW 또는 USD"
    if step == "currency":
        response = _save_position(data["ticker"], data["quantity"], data["avg_price"], text.upper())
        SESSIONS.pop(chat_id, None)
        return response
    return "입력 오류입니다. /cancel 후 다시 시도하세요."


def _continue_add_watch(chat_id: str, text: str) -> str:
    state = SESSIONS[chat_id]
    data = state["data"]
    step = state["step"]
    prompts = {
        "ticker": ("ticker", "회사명을 입력하세요. 예: ExxonMobil"),
        "name": ("name", "시장을 입력하세요. 예: US, KR_KOSPI, KR_KOSDAQ"),
        "market": ("market", "거래소를 입력하세요. 예: NYSE, NASDAQ, KRX"),
        "exchange": ("exchange", "국가를 입력하세요. 예: UnitedStates 또는 Korea"),
        "country": ("country", "통화를 입력하세요. 예: USD 또는 KRW"),
        "currency": ("currency", "섹터를 입력하세요. 예: energy, steel, battery_materials"),
        "sector": ("sector", "관련 원자재를 입력하세요. 예: crude_oil, copper, lithium"),
        "commodity": ("commodity", "노출 유형을 입력하세요. 예: producer, consumer, processor, mixedstream"),
        "exposure_type": ("exposure_type", "영향 방향을 입력하세요. positive, negative, mixed, unclear"),
        "direction": ("direction", "관련도 점수를 입력하세요. 0~100"),
    }
    if step in prompts:
        key, prompt = prompts[step]
        data[key] = text
        order = list(prompts.keys())
        next_index = order.index(step) + 1
        if next_index < len(order):
            state["step"] = order[next_index]
            return prompt
        response = _save_watch(data, text)
        SESSIONS.pop(chat_id, None)
        return response
    return "입력 오류입니다. /cancel 후 다시 시도하세요."


def _positions() -> str:
    session = get_session()
    try:
        rows = list(session.scalars(select(UserPosition).where(UserPosition.is_active.is_(True))))
        if not rows:
            return "등록된 보유종목이 없습니다."
        return "\n".join(f"{p.ticker} / {p.quantity:g}주 / 평균 {p.avg_buy_price:g} {p.currency}" for p in rows)
    finally:
        session.close()


def _save_position(ticker: str, quantity: str, avg_price: str, currency: str) -> str:
    ticker = ticker.upper()
    quantity_value = _parse_number(quantity)
    avg_price_value = _parse_number(avg_price)
    session = get_session()
    try:
        position = session.scalar(
            select(UserPosition).where(UserPosition.ticker == ticker, UserPosition.is_active.is_(True))
        )
        if position is None:
            position = UserPosition(
                ticker=ticker,
                quantity=quantity_value,
                avg_buy_price=avg_price_value,
                currency=currency.upper(),
                is_active=True,
            )
            session.add(position)
        else:
            position.quantity = quantity_value
            position.avg_buy_price = avg_price_value
            position.currency = currency.upper()
        session.commit()
        return f"보유종목 저장: {ticker} / {quantity_value:g}주 / 평균 {avg_price_value:g} {currency.upper()}"
    finally:
        session.close()


def _remove_position(ticker: str) -> str:
    ticker = ticker.upper()
    session = get_session()
    try:
        position = session.scalar(
            select(UserPosition).where(UserPosition.ticker == ticker, UserPosition.is_active.is_(True))
        )
        if position is None:
            return f"활성 보유종목 없음: {ticker}\n감시종목을 지우려면 /remove_watch {ticker}"
        position.is_active = False
        session.commit()
        return f"보유종목 삭제: {ticker}"
    finally:
        session.close()


def _watch_buy(markets: set[str] | None = None) -> str:
    session = get_session()
    try:
        query = select(Company).where(Company.is_active.is_(True))
        if markets:
            query = query.where(Company.market.in_(markets))
        rows = list(session.scalars(query.order_by(Company.ticker)))
        if not rows:
            return "매수 감시 종목이 없습니다. seed를 다시 넣어야 할 수 있습니다: python scripts/seed_db.py"
        return "\n".join(f"{c.ticker} / {display_company_name(c.ticker, c.company_name)} / {c.market} / {c.sector}" for c in rows)
    finally:
        session.close()


def _watch_sell() -> str:
    return _positions()


def _save_watch(data: dict, score_text: str) -> str:
    ticker = data["ticker"].upper()
    score = _parse_number(score_text)
    session = get_session()
    try:
        commodity = session.scalar(select(Commodity).where(Commodity.code == data["commodity"]))
        if commodity is None:
            return f"등록되지 않은 원자재: {data['commodity']}"
        company = session.scalar(select(Company).where(Company.ticker == ticker))
        if company is None:
            company = Company(
                ticker=ticker,
                company_name=data["name"].replace("_", " "),
                market=data["market"],
                exchange=data["exchange"],
                country=data["country"].replace("_", " "),
                currency=data["currency"].upper(),
                sector=data["sector"],
                risk_level="medium",
                is_active=True,
            )
            session.add(company)
            session.flush()
        exposure = session.scalar(
            select(CompanyCommodityExposure).where(
                CompanyCommodityExposure.company_id == company.id,
                CompanyCommodityExposure.commodity_id == commodity.id,
            )
        )
        if exposure is None:
            exposure = CompanyCommodityExposure(
                company_id=company.id,
                commodity_id=commodity.id,
                exposure_type=data["exposure_type"],
                exposure_direction=data["direction"],
                exposure_score=score,
            )
            session.add(exposure)
        else:
            exposure.exposure_type = data["exposure_type"]
            exposure.exposure_direction = data["direction"]
            exposure.exposure_score = score
        session.commit()
        return f"매수 감시 저장: {ticker} / {data['commodity']}"
    finally:
        session.close()


def _save_watch_inline(text: str) -> str:
    try:
        row = _parse_watch_line(text)
    except ValueError as exc:
        return str(exc)
    return _upsert_watch_company(row)


def _save_watch_bulk(text: str) -> str:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    if not rows:
        return "등록할 줄이 없습니다."

    saved = []
    failed = []
    for line in rows:
        try:
            row = _parse_watch_line(line)
            saved.append(_upsert_watch_company(row))
        except Exception as exc:
            failed.append(f"{line} -> {exc}")

    parts = [f"일괄 등록 완료: {len(saved)}개"]
    if saved:
        parts.extend(saved)
    if failed:
        parts.append("")
        parts.append(f"실패: {len(failed)}개")
        parts.extend(failed)
    return "\n".join(parts)


def _remove_watch(ticker: str) -> str:
    ticker = ticker.upper()
    session = get_session()
    try:
        company = session.scalar(select(Company).where(Company.ticker == ticker, Company.is_active.is_(True)))
        if company is None:
            return f"활성 감시종목 없음: {ticker}"
        company.is_active = False
        session.commit()
        return f"감시종목 삭제: {ticker}"
    finally:
        session.close()


def _remove_all(keyword: str) -> str:
    Base.metadata.create_all(bind=engine)
    keyword = keyword.strip()
    pattern = f"%{keyword}%"
    session = get_session()
    try:
        companies = list(
            session.scalars(
                select(Company).where(Company.ticker.ilike(pattern) | Company.company_name.ilike(pattern))
            )
        )
        targets = list(
            session.scalars(
                select(ValuationTarget).where(
                    ValuationTarget.ticker.ilike(pattern) | ValuationTarget.company_name.ilike(pattern)
                )
            )
        )

        matched: dict[str, str] = {}
        for company in companies:
            matched[company.ticker.upper()] = display_company_name(company.ticker, company.company_name)
        for target in targets:
            matched.setdefault(target.ticker.upper(), display_company_name(target.ticker, target.company_name or target.ticker))

        if not matched:
            return f"검색 결과가 없습니다: {keyword}"

        tickers = sorted(matched)
        for position in session.scalars(select(UserPosition).where(UserPosition.ticker.in_(tickers))):
            position.is_active = False
        for company in session.scalars(select(Company).where(Company.ticker.in_(tickers))):
            company.is_active = False
        for target in session.scalars(select(ValuationTarget).where(ValuationTarget.ticker.in_(tickers))):
            target.is_active = False

        session.commit()
        deleted = ", ".join(f"{matched[ticker]} ({ticker})" for ticker in tickers)
        return f"✅ 다음 종목들이 모든 리스트에서 삭제(비활성화)되었습니다: {deleted}"
    finally:
        session.close()


def _parse_watch_line(text: str) -> dict:
    payload = text.strip()
    if payload.startswith("/add_watch"):
        payload = payload.removeprefix("/add_watch").strip()
    parts = [part.strip() for part in payload.split("/") if part.strip()]
    if len(parts) < 4:
        raise ValueError("형식: /add_watch 티커 / 회사명 / 시장 / 섹터")
    ticker, name, market, sector = parts[:4]
    exchange, country, currency = _market_defaults(market)
    return {
        "ticker": ticker.upper(),
        "name": name,
        "market": market.upper(),
        "exchange": exchange,
        "country": country,
        "currency": currency,
        "sector": sector,
    }


def _market_defaults(market: str) -> tuple[str, str, str]:
    market = market.upper()
    if market in {"KR_KOSPI", "KR_KOSDAQ"}:
        return "KRX", "Korea", "KRW"
    return "US", "United States", "USD"


def _upsert_watch_company(row: dict) -> str:
    session = get_session()
    try:
        company = session.scalar(select(Company).where(Company.ticker == row["ticker"]))
        if company is None:
            company = Company(
                ticker=row["ticker"],
                company_name=row["name"],
                market=row["market"],
                exchange=row["exchange"],
                country=row["country"],
                currency=row["currency"],
                sector=row["sector"],
                risk_level="medium",
                notes="Added from Telegram watchlist command.",
                is_active=True,
            )
            session.add(company)
            session.flush()
        else:
            company.company_name = row["name"]
            company.market = row["market"]
            company.exchange = row["exchange"]
            company.country = row["country"]
            company.currency = row["currency"]
            company.sector = row["sector"]
            company.is_active = True

        for code, exposure_type, direction, score in _infer_exposures(row["sector"]):
            commodity = session.scalar(select(Commodity).where(Commodity.code == code))
            if commodity is None:
                continue
            exposure = session.scalar(
                select(CompanyCommodityExposure).where(
                    CompanyCommodityExposure.company_id == company.id,
                    CompanyCommodityExposure.commodity_id == commodity.id,
                )
            )
            if exposure is None:
                exposure = CompanyCommodityExposure(
                    company_id=company.id,
                    commodity_id=commodity.id,
                    exposure_type=exposure_type,
                    exposure_direction=direction,
                    exposure_score=score,
                )
                session.add(exposure)
            else:
                exposure.exposure_type = exposure_type
                exposure.exposure_direction = direction
                exposure.exposure_score = score

        session.commit()
        display_name = display_company_name(row["ticker"], row["name"])
        if row["market"] in {"KR_KOSPI", "KR_KOSDAQ"}:
            company.company_name = display_name
        return f"감시 저장: {row['ticker']} / {display_name} / {row['sector']}"
    finally:
        session.close()


def _infer_exposures(sector: str) -> list[tuple[str, str, str, float]]:
    sector = sector.lower()
    if "refining" in sector or "energy_battery" in sector:
        return [
            ("crude_oil", "processor", "mixed", 65),
            ("lithium", "processor", "mixed", 45),
            ("nickel", "processor", "mixed", 35),
        ]
    if "copper" in sector or "electrical" in sector or "power_grid" in sector:
        return [
            ("copper", "consumer", "negative", 55),
            ("steel", "consumer", "negative", 30),
        ]
    return [("copper", "processor", "mixed", 35)]


def _value_targets() -> str:
    Base.metadata.create_all(bind=engine)
    session = get_session()
    try:
        rows = list(
            session.scalars(
                select(ValuationTarget).where(ValuationTarget.is_active.is_(True)).order_by(ValuationTarget.ticker)
            )
        )
        if not rows:
            return "등록된 적정가 감시 종목이 없습니다."
        return "\n".join(
            f"{row.ticker} / {display_company_name(row.ticker, row.company_name or row.ticker)} / 적정 {row.fair_value_price:g} / "
            f"매수 {row.buy_price:g} {row.currency} / 버퍼 {row.alert_buffer_pct:g}%"
            for row in rows
        )
    finally:
        session.close()


def _save_value_inline(text: str) -> str:
    try:
        row = _parse_value_line(text)
    except ValueError as exc:
        return str(exc)
    return _upsert_value_target(row)


def _save_value_bulk(text: str) -> str:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    if not rows:
        return "등록할 줄이 없습니다."

    saved = []
    failed = []
    for line in rows:
        try:
            row = _parse_value_line(line)
            saved.append(_upsert_value_target(row))
        except Exception as exc:
            failed.append(f"{line} -> {exc}")

    parts = [f"적정가 감시 등록 완료: {len(saved)}개"]
    if saved:
        parts.extend(saved)
    if failed:
        parts.append("")
        parts.append(f"실패: {len(failed)}개")
        parts.extend(failed)
    return "\n".join(parts)


def _save_value_auto(text: str) -> str:
    return _estimate_value_text(text, save=True)


def _estimate_value_text(text: str, save: bool) -> str:
    try:
        estimate = _estimate_value_from_text(text)
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"적정가 계산 실패: {exc}"

    lines = [
        f"{estimate.ticker} / {display_company_name(estimate.ticker, estimate.company_name)}",
        f"현재가: {estimate.current_price:g} {estimate.currency}",
        f"자동 적정가: {estimate.fair_value_price:g} {estimate.currency}",
        f"자동 매수가: {estimate.buy_price:g} {estimate.currency}",
        f"기준: {estimate.notes}",
    ]
    if save:
        saved = _upsert_value_target(
            {
                "ticker": estimate.ticker,
                "company_name": estimate.company_name,
                "market": estimate.market,
                "fair_value_price": estimate.fair_value_price,
                "buy_price": estimate.buy_price,
                "currency": estimate.currency,
                "notes": estimate.notes,
                "alert_buffer_pct": 5.0,
            }
        )
        lines.append(saved)
    return "\n".join(lines)


def _estimate_value_from_text(text: str):
    parts = [part.strip() for part in text.split("/") if part.strip()]
    if not parts:
        raise ValueError("형식: /add_value_auto 티커")
    ticker = parts[0].upper()
    company_name = parts[1] if len(parts) >= 2 else ""
    market = parts[2].upper() if len(parts) >= 3 else ""
    notes = parts[3] if len(parts) >= 4 else ""

    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    session = get_session()
    try:
        company = session.scalar(select(Company).where(Company.ticker == ticker))
        if company and not company_name:
            company_name = display_company_name(company.ticker, company.company_name)
        if company and not market:
            market = company.market
        benchmark_by_ticker = {ticker: "URTH"}
        if market:
            benchmark_by_ticker[ticker] = "^KS11" if market == "KR_KOSPI" else "^KQ11" if market == "KR_KOSDAQ" else "URTH"
        stock = market_data_provider(settings).stock_moves([ticker], benchmark_by_ticker).get(ticker)
        fund = fundamentals_provider(settings).fundamentals([ticker]).get(ticker)
        if stock is None or not stock.last_price or fund is None:
            raise ValueError(f"가격/재무 데이터를 가져오지 못했습니다: {ticker}")
        return estimate_value_target(
            settings=settings,
            ticker=ticker,
            stock=stock,
            fund=fund,
            company=company,
            company_name=company_name,
            market=market,
            notes=notes,
        )
    finally:
        session.close()


def _remove_value(ticker: str) -> str:
    Base.metadata.create_all(bind=engine)
    ticker = ticker.upper()
    session = get_session()
    try:
        target = session.scalar(
            select(ValuationTarget).where(ValuationTarget.ticker == ticker, ValuationTarget.is_active.is_(True))
        )
        if target is None:
            return f"활성 적정가 감시 없음: {ticker}"
        target.is_active = False
        session.commit()
        return f"적정가 감시 삭제: {ticker}"
    finally:
        session.close()


def _report() -> str:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    session = get_session()
    try:
        companies = list(session.scalars(select(Company).where(Company.is_active.is_(True)).order_by(Company.ticker)))
        if not companies:
            return "활성 워치리스트 종목이 없습니다."

        benchmarks = {row.market: row.ticker for row in session.scalars(select(Benchmark))}
        benchmark_by_ticker = {
            company.ticker: benchmarks.get(company.market, "URTH")
            for company in companies
        }
        commodity_codes = sorted({exposure.commodity.code for company in companies for exposure in company.exposures})
        tickers = [company.ticker for company in companies]

        market = market_data_provider(settings)
        stock_moves = market.stock_moves(tickers, benchmark_by_ticker)
        commodity_moves = market.commodity_moves(commodity_codes) if commodity_codes else {}

        lines = ["📊 Copper Tea report"]
        for company in companies:
            stock = stock_moves.get(company.ticker)
            if stock is None:
                lines.append(f"{company.ticker} / {display_company_name(company.ticker, company.company_name)}: price data unavailable")
                continue

            excess = stock.return_pct - stock.benchmark_return_pct
            exposure = _top_report_exposure(company, commodity_moves)
            ma_label = _ma_label(stock.ma5, stock.ma20)
            lines.append(
                f"{company.ticker} / {display_company_name(company.ticker, company.company_name)}: "
                f"excess {excess:+.1f}% | stock mom {stock.momentum_pct:+.1f}% | "
                f"{exposure} | {ma_label}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"리포트 생성 실패: {exc}"
    finally:
        session.close()


def _top_report_exposure(company: Company, commodity_moves: dict) -> str:
    ranked = []
    for exposure in company.exposures:
        move = commodity_moves.get(exposure.commodity.code)
        if move is None:
            continue
        rank = exposure.exposure_score * (abs(move.momentum_pct) + abs(move.move_pct))
        ranked.append((rank, exposure.commodity.code, move))
    if not ranked:
        return "commodity n/a"
    _, code, move = max(ranked, key=lambda item: item[0])
    ma_label = _ma_label(move.ma5, move.ma20)
    return f"{code} mom {move.momentum_pct:+.1f}% ({ma_label})"


def _ma_label(ma5: float | None, ma20: float | None) -> str:
    if ma5 is None or ma20 is None:
        return "MA n/a"
    if ma5 >= ma20:
        return "MA5>MA20"
    return "MA5<MA20"


def _parse_value_line(text: str) -> dict:
    payload = text.strip()
    if payload.startswith("/add_value"):
        payload = payload.removeprefix("/add_value").strip()
    parts = [part.strip() for part in payload.split("/") if part.strip()]
    if len(parts) < 6:
        raise ValueError("형식: /add_value 티커 / 회사명 / 시장 / 적정가 / 매수가 / 통화 / 메모")
    ticker, name, market, fair_value, buy_price, currency = parts[:6]
    notes = parts[6] if len(parts) >= 7 else ""
    alert_buffer_pct = _parse_number(parts[7]) if len(parts) >= 8 else 5.0
    return {
        "ticker": ticker.upper(),
        "company_name": name,
        "market": market.upper(),
        "fair_value_price": _parse_number(fair_value),
        "buy_price": _parse_number(buy_price),
        "currency": currency.upper(),
        "notes": notes,
        "alert_buffer_pct": alert_buffer_pct,
    }


def _upsert_value_target(row: dict) -> str:
    Base.metadata.create_all(bind=engine)
    session = get_session()
    try:
        target = session.scalar(select(ValuationTarget).where(ValuationTarget.ticker == row["ticker"]))
        if target is None:
            target = ValuationTarget(**row, is_active=True)
            session.add(target)
        else:
            for key, value in row.items():
                setattr(target, key, value)
            target.is_active = True
        session.commit()
        return (
            f"적정가 감시 저장: {row['ticker']} / {display_company_name(row['ticker'], row['company_name'])} / "
            f"적정 {row['fair_value_price']:g} / 매수 {row['buy_price']:g} {row['currency']}"
        )
    finally:
        session.close()


def _parse_number(value: str) -> float:
    return float(value.replace(",", "").strip())


def _get_updates(token: str, offset: int | None) -> list[dict]:
    params = {"timeout": 25}
    if offset is not None:
        params["offset"] = offset
    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params=params,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT + 10),
    )
    response.raise_for_status()
    return response.json().get("result", [])


def _send(token: str, chat_id: str, text: str) -> None:
    last_error: RequestException | None = None
    for attempt in range(1, SEND_RETRIES + 1):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            response.raise_for_status()
            return
        except RequestException as exc:
            last_error = exc
            if attempt < SEND_RETRIES:
                time.sleep(min(2 * attempt, 8))
    raise RuntimeError(f"Telegram send failed after {SEND_RETRIES} attempts: {last_error}")


if __name__ == "__main__":
    main()
