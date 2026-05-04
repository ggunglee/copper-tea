from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.repositories import latest_alert_for_base


class DedupService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def alert_key(self, signal_type: str, ticker: str, commodity_code: str, score: float) -> str:
        today = datetime.now(ZoneInfo(self.settings.app_timezone)).strftime("%Y%m%d")
        bucket = int(score // self.settings.dedup_score_delta)
        return f"{today}:{signal_type}:{ticker}:{commodity_code}:b{bucket}"

    def should_alert(self, session: Session, signal_type: str, ticker: str, commodity_code: str, score: float) -> bool:
        today = datetime.now(ZoneInfo(self.settings.app_timezone)).strftime("%Y%m%d")
        base = f"{today}:{signal_type}:{ticker}:{commodity_code}:"
        previous = latest_alert_for_base(session, base)
        if previous is None:
            return True
        return abs(score - previous.score) >= self.settings.dedup_score_delta

