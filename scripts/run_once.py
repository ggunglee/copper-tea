from app.config import get_settings
from app.services.pipeline import run_pipeline
from app.services.run_guard import RunGuard


if __name__ == "__main__":
    settings = get_settings()
    with RunGuard(settings) as guard:
        slot = guard.claim_slot(force=False)
        if slot:
            sent_count = run_pipeline(settings)
            print(f"Run completed. Slot: {slot}. Alerts sent: {sent_count}")
        else:
            print("Skipped: outside run window or already completed for this slot.")
