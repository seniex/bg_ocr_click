from __future__ import annotations

import threading


def _current_group_index(win):
    return max(0, win._current_index)


def _current_hwnd(win):
    return win.cfg.get("target_hwnd", 0)


def _after(win, ms, fn, timer_factory=threading.Timer):
    def emit_later():
        try:
            win._bridge.invoke_requested.emit(fn)
        except RuntimeError as exc:
            if "wrapped C/C++ object" not in str(exc):
                raise

    timer_factory(max(0, ms) / 1000.0, emit_later).start()


def _log(win, msg, tag="info"):
    win._bridge.log_requested.emit(msg, tag)
