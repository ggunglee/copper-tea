from __future__ import annotations

import errno
import os
import time
from pathlib import Path

from app.config import ROOT_DIR, Settings
from app.utils.time import current_run_slot


class RunGuard:
    stale_lock_seconds = 2 * 60 * 60

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state_dir = ROOT_DIR / "data" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state_dir / "run.lock"
        self.last_slot_path = self.state_dir / "last_slot.txt"
        self.lock_fd: int | None = None

    def __enter__(self) -> "RunGuard":
        self._acquire_lock()
        return self

    def _acquire_lock(self) -> None:
        try:
            self.lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.lock_fd, str(os.getpid()).encode("ascii"))
        except FileExistsError as exc:
            if self._clear_stale_lock():
                self.lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.lock_fd, str(os.getpid()).encode("ascii"))
                return
            raise RuntimeError("Another run is already in progress.") from exc

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

    def _clear_stale_lock(self) -> bool:
        if not self.lock_path.exists():
            return False

        pid = self._read_lock_pid()
        lock_age = max(0.0, os.path.getmtime(self.lock_path))
        is_old = (time.time() - lock_age) > self.stale_lock_seconds
        is_stale = pid is None or not self._pid_is_running(pid) or is_old
        if not is_stale:
            return False

        try:
            self.lock_path.unlink()
            return True
        except FileNotFoundError:
            return True

    def _read_lock_pid(self) -> int | None:
        try:
            raw_pid = self.lock_path.read_text(encoding="ascii").strip()
            return int(raw_pid) if raw_pid else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                return False
            if exc.errno == errno.EPERM:
                return True
            return False
        return True
