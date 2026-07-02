from __future__ import annotations

from bg_ocr.config import save_config


def _close_event(win, event):
    _on_close(win)
    event.accept()


def _on_close(win):
    win._stop()
    win._save_current_group()
    try:
        win.cfg.update(win._settings_editor.dump_settings())
    except Exception:
        pass
    if hasattr(win, "_auto_bind_stop"):
        win._auto_bind_stop.set()
    win._clear_hotkeys()
    win.cfg["window_geometry"] = f"{win.width()}x{win.height()}"
    save_config(win.cfg)
