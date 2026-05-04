from __future__ import annotations

import os
from pathlib import Path

from app.config import ROOT_DIR, Settings
from app.utils.time import current_run_slot


class RunGuard:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state_dir = ROOT_DIR / "data" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state_dir / "run.lock"
        self.last_slot_path = self.state_dir / "last_slot.txt"
        self.lock_fd: int | None = None

    def __enter__(self) -> "RunGuard":
        try:
            self.lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.lock_fd, str(os.getpid()).encode("ascii"))
        except FileExistsError as exc:
            raise RuntimeError("Another run is already in progress.") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.lock_fd is not None:
            os.close(self.lock_fd)
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def claim_slot(self, force: bool = False) -> str | None:
        if force:
            return "force"
        slot = current_run_slot(self.settings.app_timezone, self.settings.run_times)
        if slot is None:
            return None
        last_slot = self.last_slot_path.read_text(encoding="utf-8").strip() if self.last_slot_path.exists() else ""
        if last_slot == slot:
            return None
        self.last_slot_path.write_text(slot, encoding="utf-8")
        return slot

