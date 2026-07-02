from __future__ import annotations

import threading

from PyQt6 import QtCore

from bg_ocr.config import load_config
from bg_ocr.qt.bridge import _UiBridge


def _initialize_window(
    win,
    load_config_func=load_config,
    bridge_factory=_UiBridge,
    event_factory=threading.Event,
    timer_single_shot=QtCore.QTimer.singleShot,
):
    win.cfg = load_config_func()
    win.monitors = []
    win._running = False
    win._bridge = bridge_factory()
    win._bridge.log_requested.connect(win._append_log)
    win._bridge.invoke_requested.connect(win._run_in_ui)
    win._bridge.status_requested.connect(win._set_status)
    win._auto_bind_stop = event_factory()
    win._auto_bind_thread = None
    win._group_order_dirty = False
    win._loading_group_editor = False
    win._current_index = 0
    win._build_ui()
    win._apply_theme(win.cfg.get("theme", "default"))
    win._load_from_cfg()
    win._start_auto_bind_loop()
    if win.cfg.get("start_on_launch", True):
        timer_single_shot(150, win._start)
    timer_single_shot(250, win._apply_hotkeys)
    win._refresh_window_title()
