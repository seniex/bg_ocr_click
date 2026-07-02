from __future__ import annotations

import os

from PyQt6 import QtWidgets

from bg_ocr.config import save_config
from bg_ocr.monitor import GroupMonitor
from bg_ocr.ocr import get_paddle_engine

_paddle_engine = get_paddle_engine()


def _refresh_monitor_state(win):
    win._refresh_bound_label()
    win._refresh_window_title()
    win._refresh_group_list()
    win._refresh_quick_config()
    win._refresh_dependencies()


def _start(win):
    if win._running:
        return
    win._save_current_group()
    win.cfg.update(win._settings_editor.dump_settings())
    save_config(win.cfg)
    if not win.cfg.get("target_hwnd"):
        QtWidgets.QMessageBox.warning(win, "Warning", "Select a target window before starting")
        return
    enabled = [g for g in win.cfg["groups"] if g.get("enabled", True)]
    if not enabled:
        QtWidgets.QMessageBox.warning(win, "Tip", "No enabled groups")
        return
    missing = win._missing_runtime_dependency()
    if missing:
        QtWidgets.QMessageBox.warning(win, "Missing dependency", missing)
        return
    if win._uses_paddle():
        exe = win.cfg.get("paddle_exe_path", "").strip()
        if not exe or not os.path.exists(exe):
            QtWidgets.QMessageBox.warning(win, "Warning", "Select PaddleOCR-json.exe first")
            return
        try:
            win.log("Starting PaddleOCR-json server...", "info")
            _paddle_engine.start(exe)
            win.log("PaddleOCR-json server started", "ok")
        except Exception as e:
            QtWidgets.QMessageBox.critical(win, "PaddleOCR startup failed", str(e))
            return
    win._running = True
    win.monitors = [GroupMonitor(win, i) for i in range(len(win.cfg["groups"]))]
    for i, group in enumerate(win.cfg["groups"]):
        if group.get("enabled", True):
            win.monitors[i].start()
    win._set_status(True)
    win.log(f"Started {len(enabled)} enabled groups", "ok")


def _stop(win):
    if not win._running and not win.monitors:
        return
    win._running = False
    for monitor in win.monitors:
        monitor.stop()
    win.monitors.clear()
    try:
        _paddle_engine.stop()
    except Exception:
        pass
    win._set_status(False)
    win.log("Stopped", "warn")
