from __future__ import annotations

from PyQt6 import QtWidgets

from bg_ocr.config import save_config
from bg_ocr.qt.pickers import _WindowPickerDialog
from bg_ocr.system import list_windows


def _refresh_window_title(self):
    name = self.cfg.get("target_title", "")
    self.setWindowTitle(f"BgOcrClick Qt - {name[:20] if name else 'No window bound'}")


def _refresh_bound_label(self):
    hwnd = self.cfg.get("target_hwnd", 0)
    title = self.cfg.get("target_title", "")
    self._bound.setText(f"Window: [{hwnd}] {title}" if hwnd and title else "No window bound")


def _find_windows(self):
    self._win_list.clear()
    key = self._title_filter.text().strip().lower()
    for hwnd, title in list_windows():
        if key and key not in title.lower():
            continue
        self._win_list.addItem(f"[{hwnd}] {title}")
    self.log(f"Found {self._win_list.count()} windows", "info")


def _bind_selected_window(self, hwnd, title):
    self.cfg["target_hwnd"] = hwnd
    self.cfg["target_title"] = title
    self._title_filter.setText(title)
    self._refresh_monitor_state()
    save_config(self.cfg)
    self.log(f"已绑定：[{hwnd}] {title}", "ok")


def _pick_window_dialog(self):
    dlg = _WindowPickerDialog(self)
    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selected:
        hwnd, title = dlg.selected
        self._bind_selected_window(hwnd, title)


def _bind_window(self):
    row = self._win_list.currentRow()
    if row < 0:
        QtWidgets.QMessageBox.warning(self, "提示", "请先选择窗口")
        return
    key = self._title_filter.text().strip().lower()
    windows = []
    for hwnd, title in list_windows():
        if key and key not in title.lower():
            continue
        windows.append((hwnd, title))
    if row >= len(windows):
        return
    hwnd, title = windows[row]
    self._bind_selected_window(hwnd, title)
