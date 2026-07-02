from __future__ import annotations

from bg_ocr.capture import HAS_PIL, HAS_SCREENINFO, HAS_WIN32
from bg_ocr.matching import HAS_CV2, HAS_NUMPY
from bg_ocr.mouse import HAS_PYAUTOGUI
from bg_ocr.ocr import HAS_PADDLE, HAS_TESSERACT
from bg_ocr.system import _is_admin


def _refresh_dependencies(window):
    lines = [
        f"pywin32: {'OK' if HAS_WIN32 else 'missing'}",
        f"Pillow: {'OK' if HAS_PIL else 'missing'}",
        f"PaddleOCR: {'OK' if HAS_PADDLE else 'missing'}",
        f"pytesseract: {'OK' if HAS_TESSERACT else 'missing'}",
        f"opencv-python: {'OK' if HAS_CV2 else 'missing'}",
        f"numpy: {'OK' if HAS_NUMPY else 'missing'}",
        f"pyautogui: {'OK' if HAS_PYAUTOGUI else 'missing'}",
        f"screeninfo: {'OK' if HAS_SCREENINFO else 'missing'}",
        f"admin: {'yes' if _is_admin() else 'no'}",
    ]
    window._dep_box.setPlainText("\n".join(lines))


def _uses_paddle(window):
    for g in window.cfg["groups"]:
        if not g.get("enabled", True):
            continue
        if g.get("type", "ocr") == "ocr" and g.get("ocr_engine", "paddle") == "paddle":
            return True
        for tmpl in g.get("popup_templates", []):
            if tmpl.get("type", "ocr") == "ocr" and tmpl.get("ocr_engine", "paddle") == "paddle":
                return True
    return False


def _missing_runtime_dependency(window):
    for g_index, g in enumerate(window.cfg["groups"], start=1):
        if not g.get("enabled", True):
            continue
        missing = window._missing_match_dependency(g, f"group {g_index}")
        if missing:
            return missing
        missing = _missing_action_dependency(g, f"group {g_index}")
        if missing:
            return missing
        if g.get("popup_enabled") and g.get("popup_title_kw", "").strip():
            for t_index, tmpl in enumerate(g.get("popup_templates", []), start=1):
                missing = window._missing_match_dependency(tmpl, f"group {g_index} popup {t_index}")
                if missing:
                    return missing
                missing = _missing_action_dependency(tmpl, f"group {g_index} popup {t_index}")
                if missing:
                    return missing
    return None


def _missing_match_dependency(_window, item, label):
    kind = item.get("type", "ocr")
    if kind == "ocr":
        engine = item.get("ocr_engine", "paddle")
        if engine == "paddle" and not HAS_PADDLE:
            return f"{label} uses PaddleOCR, please install paddlepaddle/paddleocr"
        if engine == "tesseract" and not HAS_TESSERACT:
            return f"{label} uses Tesseract, please install pytesseract"
    elif kind == "image" and (not HAS_CV2 or not HAS_NUMPY):
        return f"{label} uses image template matching, please install opencv-python and numpy"
    elif kind == "color" and not HAS_NUMPY:
        return f"{label} uses color matching, please install numpy"
    return None


def _legacy_mouse_action(item):
    target = item.get("click_target", "keyword")
    if not target:
        target = "window" if item.get("custom_click", False) else "keyword"
    pos_mode = {
        "keyword": "match_center",
        "window": "window",
        "screen": "screen",
    }.get(target, "match_center")
    return {
        "kind": "mouse",
        "pos_mode": pos_mode,
        "click_type": item.get("click_type", "single"),
    }


def _actions_for_dependency_check(item):
    actions = item.get("actions") or []
    if actions:
        return actions
    return [_legacy_mouse_action(item)]


def _action_needs_pyautogui(action, item):
    kind = action.get("kind", "mouse")
    if kind in {"key", "text", "scroll"}:
        return True
    if kind != "mouse":
        return False

    if item.get("click_mode", "postmessage") == "quickswitch":
        return True
    if action.get("pos_mode", "match_center") == "screen":
        return True
    return action.get("click_type", "single") in {"down", "up"}


def _missing_action_dependency(item, label):
    if HAS_PYAUTOGUI:
        return None
    for index, action in enumerate(_actions_for_dependency_check(item), start=1):
        if _action_needs_pyautogui(action, item):
            return f"{label} action {index} uses pyautogui-driven input, please install pyautogui"
    return None
