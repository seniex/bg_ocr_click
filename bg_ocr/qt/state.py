from __future__ import annotations

import time

from PyQt6 import QtCore, QtWidgets

from bg_ocr.action_runtime import _play_sound
from bg_ocr.config import LOG_FILE
from bg_ocr.qt.group_manager import _build_quick_template_cell


def _load_from_cfg(win):
    win._settings_editor.load_settings(win.cfg)
    win._refresh_group_list()
    win._refresh_quick_config()
    win._refresh_dependencies()
    win._refresh_bound_label()
    if win.cfg["groups"]:
        win._group_list.setCurrentRow(0)


def _refresh_group_list(win):
    win._group_list.blockSignals(True)
    win._group_list.clear()
    for i, group in enumerate(win.cfg["groups"]):
        win._group_list.addItem(f"{i + 1}. {group.get('name', f'Group {i + 1}')}")
    win._group_list.blockSignals(False)
    selected = -1
    if 0 <= win._current_index < len(win.cfg["groups"]):
        selected = win.cfg["groups"][win._current_index].get("chain_target", -1)
    win._group_editor.set_chain_options(
        [group.get("name", f"Group {i + 1}") for i, group in enumerate(win.cfg["groups"])],
        win._current_index,
        selected,
    )


def _refresh_quick_config(win):
    groups = win.cfg["groups"]
    win._quick_table.blockSignals(True)
    win._quick_table.setRowCount(len(groups))
    for i, group in enumerate(groups):
        chk = QtWidgets.QTableWidgetItem()
        chk.setCheckState(QtCore.Qt.CheckState.Checked if group.get("enabled", True) else QtCore.Qt.CheckState.Unchecked)
        win._quick_table.setItem(i, 0, chk)

        seq = QtWidgets.QTableWidgetItem(str(group.get("seq", i + 1)))
        win._quick_table.setItem(i, 1, seq)

        name = QtWidgets.QTableWidgetItem(group.get("name", f"Group {i + 1}"))
        win._quick_table.setItem(i, 2, name)

        sink = QtWidgets.QTableWidgetItem()
        sink.setCheckState(
            QtCore.Qt.CheckState.Checked if group.get("sink_after_click", False) else QtCore.Qt.CheckState.Unchecked
        )
        win._quick_table.setItem(i, 3, sink)

        interval = QtWidgets.QTableWidgetItem(str(group.get("interval", 5)))
        win._quick_table.setItem(i, 4, interval)
        _build_quick_template_cell(win, i, group)
    win._quick_table.blockSignals(False)


def _mark_dirty(win):
    if win._loading_group_editor:
        return
    win._group_order_dirty = True


def _run_in_ui(win, fn):
    try:
        fn()
    except Exception as exc:
        win.log(f"UI callback failed: {exc}", "err")


def _append_log(win, msg, tag="info"):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    color = {
        "ok": "#2ecc71",
        "warn": "#f39c12",
        "err": "#e74c3c",
        "info": "#8fc6ff",
    }.get(tag, "#e8eaf0")
    win._log.append(f'<span style="color:{color}">{line}</span>')
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _set_status(win, running):
    win._status.setText("Running" if running else "Stopped")
    win._status_dot.setProperty("running", bool(running))
    win._status_dot.style().unpolish(win._status_dot)
    win._status_dot.style().polish(win._status_dot)
    win._start_btn.setEnabled(not running)
    win._stop_btn.setEnabled(running)


def _play_if(win, event):
    cfg = win.cfg
    if not cfg.get("sound_enabled", False):
        return
    sf = cfg.get("sound_file", "").strip()
    if not sf:
        return
    mapping = {
        "match": "sound_on_match",
        "popup_match": "sound_on_popup_match",
        "no_match": "sound_on_no_match",
    }
    if cfg.get(mapping.get(event, ""), False):
        _play_sound(sf)


def _save_settings(win, save_config_func):
    win._save_current_group()
    win.cfg.update(win._settings_editor.dump_settings())
    if hasattr(win, "_apply_theme"):
        win._apply_theme(win.cfg.get("theme", "default"))
    save_config_func(win.cfg)
    win._apply_hotkeys()
    win._refresh_monitor_state()
    win.log("Settings saved", "ok")
    QtWidgets.QMessageBox.information(win, "Saved", "Settings saved")
