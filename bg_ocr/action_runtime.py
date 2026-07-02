from __future__ import annotations

import os
import threading


def _play_sound(sound_file):
    """Play a sound asynchronously without blocking the UI thread."""
    if not sound_file or not os.path.exists(sound_file):
        return

    def _do():
        try:
            import ctypes as _ct

            _ct.windll.winmm.PlaySoundW(sound_file, None, 0x0001 | 0x0002)
        except Exception:
            try:
                import subprocess as _sp

                _sp.Popen(
                    ["wmplayer", "/play", "/close", sound_file],
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    creationflags=0x08000000,
                )
            except Exception:
                pass

    threading.Thread(target=_do, daemon=True).start()


ACTION_DEFAULTS = {
    "mouse": {
        "kind": "mouse",
        "pre_delay": 0.0,
        "pos_mode": "match_center",
        "offset_x": 0,
        "offset_y": 0,
        "abs_x": 0,
        "abs_y": 0,
        "click_type": "single",
        "count": 1,
        "interval": 0.1,
    },
    "key": {"kind": "key", "key": "", "action": "press", "count": 1, "interval": 0.05},
    "text": {"kind": "text", "text": "", "interval": 0.05},
    "delay": {"kind": "delay", "seconds": 0.5},
    "scroll": {
        "kind": "scroll",
        "abs_x": 0,
        "abs_y": 0,
        "direction": "down",
        "clicks": 1,
        "interval": 0.1,
        "multiplier": 1.0,
    },
}

_POS_MODES = [
    ("match_center", "识别位置(中心点)"),
    ("offset", "识别位置+偏移"),
    ("window", "窗口相对坐标"),
    ("screen", "屏幕固定坐标"),
]
_POS_MODE_LABELS = [v for _, v in _POS_MODES]
_POS_MODE_VALS = {v: k for k, v in _POS_MODES}
_POS_LABEL = {k: v for k, v in _POS_MODES}

_CLICK_TYPES = ["single", "double", "right", "down", "up", "move"]
_CLICK_LABELS = {
    "single": "单击",
    "double": "双击",
    "right": "右键",
    "down": "按下",
    "up": "弹起",
    "move": "移动",
}

_KEY_ACTIONS = [("press", "按键"), ("down", "按下"), ("up", "弹起")]
_KEY_ACTION_LABEL = {k: v for k, v in _KEY_ACTIONS}
_KEY_ACTION_VALS = {v: k for k, v in _KEY_ACTIONS}

_KEY_HINTS = [
    "ctrl+c",
    "ctrl+v",
    "ctrl+a",
    "ctrl+z",
    "ctrl+s",
    "enter",
    "space",
    "esc",
    "tab",
    "backspace",
    "delete",
    "shift",
    "ctrl",
    "alt",
    "win",
    "f1",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f11",
    "f12",
    "up",
    "down",
    "left",
    "right",
    "numpad0",
    "numpad1",
    "numpad2",
    "numpad3",
    "numpad4",
    "numpad5",
    "numpad6",
    "numpad7",
    "numpad8",
    "numpad9",
    "ctrl+shift+f5",
    "win+r",
    "alt+f4",
]
