from __future__ import annotations

import argparse
import threading

from app.config import get_settings
from app.scheduler import run_scheduler
from app.services.pipeline import run_pipeline
from app.services.run_guard import RunGuard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run-once", "scheduler", "service"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if args.command == "scheduler":
        run_scheduler(settings)
        return
    if args.command == "service":
        from scripts.telegram_bot import main as run_telegram_bot

        threading.Thread(target=run_scheduler, args=(settings,), daemon=True).start()
        run_telegram_bot()
        return

    with RunGuard(settings) as guard:
        slot = guard.claim_slot(force=args.force)
        if slot:
            sent_count = run_pipeline(settings)
            print(f"Run completed. Slot: {slot}. Alerts sent: {sent_count}")
        else:
            print("Skipped: outside run window or already completed for this slot.")


if __name__ == "__main__":
    main()
