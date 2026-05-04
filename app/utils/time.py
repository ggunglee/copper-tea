from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


def is_weekday_now(timezone: str) -> bool:
    return datetime.now(ZoneInfo(timezone)).weekday() < 5


def current_run_slot(timezone: str, run_times: tuple[str, ...], window_minutes: int = 10) -> str | None:
    now = datetime.now(ZoneInfo(timezone))
    if now.weekday() >= 5:
        return None
    current_minutes = now.hour * 60 + now.minute
    for run_time in run_times:
        hh, mm = run_time.split(":")
        target_minutes = int(hh) * 60 + int(mm)
        if 0 <= current_minutes - target_minutes < window_minutes:
            return f"{now:%Y%m%d}:{run_time}"
    return None


def within_run_window(timezone: str, run_times: tuple[str, ...], window_minutes: int = 10) -> bool:
    return current_run_slot(timezone, run_times, window_minutes) is not None
