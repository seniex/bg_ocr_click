from __future__ import annotations

import copy
import json
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "bg_ocr_click.json")
LOG_DIR = os.path.join(BASE_DIR, "log")
SCRIPT_NAME = "bg_ocr_click"
LOG_FILE = os.path.join(LOG_DIR, f"{SCRIPT_NAME}_{time.strftime('%Y%m%d_%H%M%S')}.log")
os.makedirs(LOG_DIR, exist_ok=True)

DEFAULT_WINDOW_GEOMETRY = "1180x860"


GROUP_DEFAULT = {
    "name": "监控组",
    "enabled": True,
    "type": "ocr",
    "region": None,
    "keywords": "",
    "language": "chi_sim",
    "ocr_engine": "paddle",
    "ocr_psm": 6,
    "ocr_scale": 1,
    "ocr_binarize": True,
    "ocr_threshold": 128,
    "ocr_contrast": 1.5,
    "ocr_invert": False,
    "template_path": None,
    "threshold": 80,
    "target_color": [255, 0, 0],
    "tolerance": 10,
    "click_mode": "postmessage",
    "sink_after_click": False,
    "mouse_jitter": True,
    "mouse_humanize": True,
    "actions": [],
    "click_type": "single",
    "click_target": "keyword",
    "custom_x": 0,
    "custom_y": 0,
    "interval": 5,
    "pause": 10,
    "debug_save": False,
    "capture_mode": "global",
    "chain_enabled": False,
    "chain_target": -1,
    "chain_wait": 2,
    "popup_only_mode": False,
    "popup_enabled": False,
    "popup_title_kw": "",
    "popup_wait_appear": 5,
    "popup_wait_close": 10,
    "popup_total_timeout": 120,
    "popup_no_match_action": "continue",
    "popup_templates": [],
}


POPUP_TEMPLATE_DEFAULT = {
    "name": "弹窗模板",
    "type": "ocr",
    "keywords": "",
    "language": "chi_sim",
    "ocr_engine": "paddle",
    "ocr_psm": 6,
    "ocr_scale": 2,
    "ocr_binarize": True,
    "ocr_threshold": 128,
    "ocr_contrast": 1.5,
    "ocr_invert": False,
    "template_path": None,
    "threshold": 80,
    "target_color": [255, 0, 0],
    "tolerance": 10,
    "click_mode": "postmessage",
    "mouse_jitter": True,
    "mouse_humanize": True,
    "actions": [],
    "after_click_wait": 1,
    "click_type": "single",
    "click_target": "keyword",
    "custom_x": 0,
    "custom_y": 0,
    "match_empty_ocr": False,
    "size_cond_enabled": False,
    "size_cond_w_op": ">",
    "size_cond_w_val": 0,
    "size_cond_h_op": ">",
    "size_cond_h_val": 0,
    "size_cond_logic": "and",
    "region": None,
    "config_hwnd": 0,
    "config_title": "",
    "after_match_stop_flow": False,
    "after_match_stop_all": False,
    "after_match_sound_file": "",
}


def _ensure_dirs() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def parse_window_geometry(value):
    width, height = [int(x) for x in str(value).lower().split("x", 1)]
    return width, height


def load_config():
    _ensure_dirs()
    default = {
        "target_hwnd": 0,
        "target_title": "",
        "window_geometry": DEFAULT_WINDOW_GEOMETRY,
        "capture_mode": "printwindow",
        "theme": "default",
        "tesseract_path": r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        "paddle_exe_path": "",
        "sound_enabled": False,
        "sound_file": "",
        "sound_on_match": True,
        "sound_on_popup_match": False,
        "sound_on_no_match": True,
        "start_on_launch": True,
        "auto_bind_enabled": False,
        "auto_bind_process": "",
        "hotkey_start": "",
        "hotkey_stop": "",
        "groups": [],
    }
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            default.update(data)
    except Exception:
        pass

    fixed = []
    for g in default["groups"]:
        merged = copy.deepcopy(GROUP_DEFAULT)
        merged.update(g)
        fixed.append(merged)
    default["groups"] = fixed
    return default


def save_config(cfg):
    _ensure_dirs()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"save config failed: {e}")
