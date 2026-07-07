"""Crash guard hooks for logging unexpected exceptions without exiting."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from types import TracebackType

logger = logging.getLogger(__name__)

CRASH_NOTIFICATION = "VoiceTray hit an error — log saved"


class CrashGuard:
    def __init__(self, *, notify: Callable[[str], None] | None = None):
        self.notify = notify

    def handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
        *,
        thread_name: str | None = None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        suffix = f" in thread {thread_name}" if thread_name else ""
        logger.error(
            "Unhandled VoiceTray exception%s",
            suffix,
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        self._notify()

    def excepthook(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.handle_exception(exc_type, exc_value, exc_traceback)

    def threading_excepthook(self, args) -> None:
        thread = getattr(args, "thread", None)
        self.handle_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            thread_name=getattr(thread, "name", None),
        )

    def _notify(self) -> None:
        if self.notify is None:
            return
        try:
            self.notify(CRASH_NOTIFICATION)
        except Exception:
            logger.debug("Could not dispatch crash notification", exc_info=True)


def install_crash_guard(*, notify: Callable[[str], None] | None = None) -> CrashGuard:
    guard = CrashGuard(notify=notify)
    sys.excepthook = guard.excepthook
    threading.excepthook = guard.threading_excepthook
    return guard
