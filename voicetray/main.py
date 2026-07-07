"""VoiceTray process entrypoint."""

from __future__ import annotations


def main() -> int:
    """Run VoiceTray."""
    from .config import load_config
    from .logging_config import configure_logging
    from .single_instance import SingleInstanceLock, default_lock_path

    configure_logging()
    load_config()

    lock = SingleInstanceLock(default_lock_path())
    if not lock.acquire():
        lock.notify_existing_instance("VoiceTray is already running")
        return 1

    try:
        from .app import VoiceTrayApp

        return int(VoiceTrayApp().run())
    finally:
        lock.release()
