from __future__ import annotations

import threading

from app.config import get_settings
from app.scheduler import run_scheduler
from scripts.telegram_bot import main as run_telegram_bot


if __name__ == "__main__":
    settings = get_settings()
    scheduler_thread = threading.Thread(target=run_scheduler, args=(settings,), daemon=True)
    scheduler_thread.start()
    run_telegram_bot()
