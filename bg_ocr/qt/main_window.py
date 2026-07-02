from __future__ import annotations

from PyQt6 import QtWidgets

from bg_ocr.action_runtime import ACTION_DEFAULTS, _CLICK_TYPES, _KEY_ACTIONS, _KEY_HINTS, _POS_MODES
from bg_ocr.capture import HAS_PIL, HAS_SCREENINFO, HAS_WIN32, capture_full_preview, capture_region
from bg_ocr.config import CONFIG_FILE, GROUP_DEFAULT, load_config, save_config
from bg_ocr.matching import HAS_CV2, HAS_NUMPY
from bg_ocr.qt.auto_bind import _auto_bind_loop, _start_auto_bind_loop
from bg_ocr.qt.bridge import _UiBridge
from bg_ocr.qt.group_ops import (
    _remap_chain_targets_after_delete,
    _remap_chain_targets_after_move,
    _remap_chain_targets_after_reorder,
)
from bg_ocr.qt.group_coordinator import (
    _load_group_editor,
    _on_group_changed,
    _save_current_group,
    _save_group_config,
    _show_group_detail,
)
from bg_ocr.qt.group_manager import _add_group, _delete_group, _move_group, _save_quick_config, _show_quick_group_detail
from bg_ocr.qt.group_factory import _copy_group
from bg_ocr.qt.pickers import _ImagePickerDialog, _ScreenPointPickerDialog, _WindowPickerDialog, _wrap
from bg_ocr.qt.actions import _ActionSequenceDialog
from bg_ocr.qt.group_editor import _GroupEditor
from bg_ocr.qt.hotkeys import _apply_hotkeys, _clear_hotkeys
from bg_ocr.qt.monitor_lifecycle import GroupMonitor, _paddle_engine, _refresh_monitor_state, _start, _stop
from bg_ocr.qt.settings import _SettingsEditor
from bg_ocr.qt.shutdown import _close_event, _on_close
from bg_ocr.qt.state import (
    _append_log,
    _load_from_cfg,
    _mark_dirty,
    _play_if,
    _refresh_group_list,
    _refresh_quick_config,
    _run_in_ui,
    _save_settings,
    _set_status,
)
from bg_ocr.qt.runtime_checks import (
    _missing_match_dependency,
    _missing_runtime_dependency,
    _refresh_dependencies,
    _uses_paddle,
)
from bg_ocr.qt.runtime_adapter import _after, _current_group_index, _current_hwnd, _log
from bg_ocr.qt.tabs import _build_groups_tab, _build_home_tab, _build_settings_tab
from bg_ocr.qt.templates import _PopupTemplateDialog
from bg_ocr.qt.theme import apply_theme
from bg_ocr.qt.value_helpers import _format_color, _format_region, _json_dump, _json_load, _parse_color, _parse_region
from bg_ocr.qt.window_binding import (
    _bind_selected_window,
    _bind_window,
    _find_windows,
    _pick_window_dialog,
    _refresh_bound_label,
    _refresh_window_title,
)
from bg_ocr.qt.window_lifecycle import _initialize_window
from bg_ocr.qt.window_setup import _build_ui
from bg_ocr.mouse import HAS_PYAUTOGUI
from bg_ocr.ocr import HAS_PADDLE, HAS_TESSERACT

class BgOcrQtWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        _initialize_window(self)

    def _build_ui(self):
        return _build_ui(self)

    def _build_home_tab(self):
        return _build_home_tab(self)

    def _build_groups_tab(self):
        return _build_groups_tab(self)

    def _build_settings_tab(self):
        return _build_settings_tab(self)

    def _load_from_cfg(self):
        return _load_from_cfg(self)

    def _refresh_dependencies(self):
        return _refresh_dependencies(self)

    def _refresh_window_title(self):
        return _refresh_window_title(self)

    def _refresh_bound_label(self):
        return _refresh_bound_label(self)

    def _refresh_group_list(self):
        return _refresh_group_list(self)

    def _refresh_quick_config(self):
        return _refresh_quick_config(self)

    def current_group_index(self):
        return _current_group_index(self)

    def current_hwnd(self):
        return _current_hwnd(self)

    def _mark_dirty(self):
        return _mark_dirty(self)

    def _run_in_ui(self, fn):
        return _run_in_ui(self, fn)

    def after(self, ms, fn):
        return _after(self, ms, fn)

    def log(self, msg, tag="info"):
        return _log(self, msg, tag)

    def _append_log(self, msg, tag="info"):
        return _append_log(self, msg, tag)

    def _set_status(self, running):
        return _set_status(self, running)

    def _play_if(self, event):
        return _play_if(self, event)

    def _refresh_monitor_state(self):
        return _refresh_monitor_state(self)

    def _find_windows(self):
        return _find_windows(self)

    def _bind_selected_window(self, hwnd, title):
        return _bind_selected_window(self, hwnd, title)

    def _pick_window_dialog(self):
        return _pick_window_dialog(self)

    def _bind_window(self):
        return _bind_window(self)

    def _load_group_editor(self, index):
        return _load_group_editor(self, index)

    def _on_group_changed(self, index):
        return _on_group_changed(self, index)

    def _show_group_detail(self, index):
        return _show_group_detail(self, index)

    def _save_current_group(self):
        return _save_current_group(self)

    def _save_group_config(self):
        return _save_group_config(self)

    def _add_group(self):
        return _add_group(self, save_config, _copy_group)

    def _delete_group(self):
        return _delete_group(self, save_config)

    def _move_group(self, direction):
        return _move_group(self, direction, save_config)

    def _save_quick_config(self):
        return _save_quick_config(self, save_config)

    def _show_quick_group_detail(self, pos):
        return _show_quick_group_detail(self, pos)

    def _save_settings(self):
        return _save_settings(self, save_config)

    def _apply_theme(self, name=None):
        return apply_theme(self, name or self.cfg.get("theme", "default"))

    def _apply_hotkeys(self):
        return _apply_hotkeys(self)

    def _clear_hotkeys(self):
        return _clear_hotkeys()

    def _uses_paddle(self):
        return _uses_paddle(self)

    def _missing_runtime_dependency(self):
        return _missing_runtime_dependency(self)

    def _missing_match_dependency(self, item, label):
        return _missing_match_dependency(self, item, label)

    def _start(self):
        return _start(self)

    def _stop(self):
        return _stop(self)

    def _start_auto_bind_loop(self):
        return _start_auto_bind_loop(self)

    def _auto_bind_loop(self):
        return _auto_bind_loop(self)

    def closeEvent(self, event):
        return _close_event(self, event)

    def _on_close(self):
        return _on_close(self)



from bg_ocr.qt.app import _launch_qt, main


if __name__ == "__main__":
    main()

