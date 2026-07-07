"""Single-instance process guard for VoiceTray."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


LOCK_FILE_NAME = "voicetray.lock"
SECOND_LAUNCH_FILE_NAME = "second-launch.json"


def default_lock_path(local_appdata: str | os.PathLike[str] | None = None) -> Path:
    base = Path(local_appdata) if local_appdata is not None else _default_local_appdata()
    return base / "VoiceTray" / LOCK_FILE_NAME


class SingleInstanceLock:
    """Atomic lockfile that prevents multiple tray instances."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else default_lock_path()
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._remove_if_stale():
                    continue
                return False

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._lock_payload(), f)
                f.write("\n")
            self._acquired = True
            return True

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            if self._lock_pid() == os.getpid():
                self.path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def notify_existing_instance(self, message: str) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        notification_path = self.path.parent / SECOND_LAUNCH_FILE_NAME
        payload = {
            "message": message,
            "pid": os.getpid(),
            "created_at": time.time(),
            "lock_path": str(self.path),
        }
        notification_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return notification_path

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.release()

    def _remove_if_stale(self) -> bool:
        pid = self._lock_pid()
        if pid is not None and _pid_is_running(pid):
            return False
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def _lock_pid(self) -> int | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        pid = raw.get("pid")
        return pid if isinstance(pid, int) else None

    @staticmethod
    def _lock_payload() -> dict[str, Any]:
        return {"pid": os.getpid(), "created_at": time.time()}


def consume_existing_instance_notification(
    lock_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    """Read and delete a pending second-launch notification request."""

    path = Path(lock_path) if lock_path is not None else default_lock_path()
    notification_path = path.parent / SECOND_LAUNCH_FILE_NAME
    try:
        raw = json.loads(notification_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        notification_path.unlink(missing_ok=True)
    except OSError:
        pass
    return raw if isinstance(raw, dict) else None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _default_local_appdata() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"
