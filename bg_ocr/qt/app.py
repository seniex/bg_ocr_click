from __future__ import annotations

from PyQt6 import QtWidgets

from bg_ocr.capture import HAS_PIL, HAS_WIN32
from bg_ocr.config import DEFAULT_WINDOW_GEOMETRY, parse_window_geometry
from bg_ocr.system import _is_admin, _relaunch_as_admin


def _launch_qt():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if not HAS_WIN32 or not HAS_PIL:
        QtWidgets.QMessageBox.critical(
            None,
            "缺少依赖",
            "缺少 pywin32 或 Pillow，无法启动 Qt 版界面",
        )
        return None
    if not _is_admin():
        ans = QtWidgets.QMessageBox.question(
            None,
            "权限提示",
            "当前非管理员权限。\nPrintWindow 截图在被遮挡时需要管理员权限。\n是否以管理员权限重启？",
        )
        if ans == QtWidgets.QMessageBox.StandardButton.Yes:
            _relaunch_as_admin()

    from bg_ocr_qt import BgOcrQtWindow

    win = BgOcrQtWindow()
    geom = win.cfg.get("window_geometry", DEFAULT_WINDOW_GEOMETRY)
    try:
        w, h = parse_window_geometry(geom)
        win.resize(w, h)
    except Exception:
        pass
    win.show()
    return app.exec()


def main():
    return _launch_qt()
