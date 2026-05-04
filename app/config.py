from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_TIMES = (
    "08:30,09:30,10:30,11:30,12:30,13:30,14:30,15:30,"
    "16:30,17:30,18:30,19:30,20:30,21:30,22:30,23:30"
)


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_timezone: str
    run_times: tuple[str, ...]
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    price_provider: str
    news_provider: str
    fundamentals_provider: str
    min_buy_score: float
    min_sell_score: float
    position_watch_return_pct: float
    position_watch_daily_pct: float
    dedup_score_delta: float
    commodity_shock_daily_pct: float
    commodity_trend_momentum_pct: float
    commodity_structural_event_score: float
    telegram_connect_timeout: float
    telegram_read_timeout: float
    telegram_send_retries: int


def get_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    run_times = tuple(
        item.strip()
        for item in os.getenv("RUN_TIMES", DEFAULT_RUN_TIMES).split(",")
        if item.strip()
    )
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/app.sqlite3"),
        app_timezone=os.getenv("APP_TIMEZONE", "Asia/Seoul"),
        run_times=run_times,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        price_provider=os.getenv("PRICE_PROVIDER", "mock"),
        news_provider=os.getenv("NEWS_PROVIDER", "mock"),
        fundamentals_provider=os.getenv("FUNDAMENTALS_PROVIDER", "mock"),
        min_buy_score=float(os.getenv("MIN_BUY_SCORE", "65")),
        min_sell_score=float(os.getenv("MIN_SELL_SCORE", "65")),
        position_watch_return_pct=float(os.getenv("POSITION_WATCH_RETURN_PCT", "10")),
        position_watch_daily_pct=float(os.getenv("POSITION_WATCH_DAILY_PCT", "3")),
        dedup_score_delta=float(os.getenv("DEDUP_SCORE_DELTA", "10")),
        commodity_shock_daily_pct=float(os.getenv("COMMODITY_SHOCK_DAILY_PCT", "3")),
        commodity_trend_momentum_pct=float(os.getenv("COMMODITY_TREND_MOMENTUM_PCT", "7")),
        commodity_structural_event_score=float(os.getenv("COMMODITY_STRUCTURAL_EVENT_SCORE", "65")),
        telegram_connect_timeout=float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "10")),
        telegram_read_timeout=float(os.getenv("TELEGRAM_READ_TIMEOUT", "30")),
        telegram_send_retries=int(os.getenv("TELEGRAM_SEND_RETRIES", "3")),
    )
