from __future__ import annotations

import time

from app.config import Settings, get_settings
from app.services.pipeline import run_pipeline
from app.services.run_guard import RunGuard


def run_scheduler(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    while True:
        try:
            with RunGuard(settings) as guard:
                slot = guard.claim_slot(force=False)
                if slot:
                    run_pipeline(settings)
        except RuntimeError:
            pass
        finally:
            time.sleep(60)
