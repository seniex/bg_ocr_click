"""Compatibility entry point for the Qt-only BgOcrClick application.

The legacy Tk UI has been removed. This module remains so existing imports and
the historical ``bg_ocr.compat.py`` script path continue to launch the Qt app and
expose shared runtime helpers.
"""

from __future__ import annotations

from bg_ocr.action_runtime import (
    ACTION_DEFAULTS,
    _CLICK_LABELS,
    _CLICK_TYPES,
    _KEY_ACTIONS,
    _KEY_ACTION_LABEL,
    _KEY_ACTION_VALS,
    _KEY_HINTS,
    _POS_LABEL,
    _POS_MODE_LABELS,
    _POS_MODE_VALS,
    _POS_MODES,
    _play_sound,
)
from bg_ocr.capture import HAS_PIL, HAS_SCREENINFO, HAS_WIN32, capture_full_preview, capture_region
from bg_ocr.config import CONFIG_FILE, GROUP_DEFAULT, LOG_FILE as _LOG_FILE, POPUP_TEMPLATE_DEFAULT, load_config, save_config
from bg_ocr.matching import HAS_CV2, HAS_NUMPY, _imread_unicode, match_color, match_keywords, match_template
from bg_ocr.monitor import GroupMonitor
from bg_ocr.mouse import HAS_PYAUTOGUI, click_postmessage, click_quickswitch, exec_action_sequence
from bg_ocr.ocr import HAS_PADDLE, HAS_TESSERACT, do_ocr_find_pos, do_ocr_text, get_paddle_engine, preprocess
from bg_ocr.system import _is_admin, _relaunch_as_admin, list_windows, list_windows_by_process

_paddle_engine = get_paddle_engine()


def main():
    from bg_ocr_qt import main as _qt_main

    return _qt_main()


if __name__ == "__main__":
    main()
