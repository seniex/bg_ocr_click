from __future__ import annotations

from importlib import resources
import os

THEMES = ("default", "modern")
THEME_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "themes")


def resolve_theme_name(name):
    text = str(name or "").strip().lower()
    return text if text in THEMES else "default"


def theme_path(name):
    return os.path.join(THEME_DIR, f"{resolve_theme_name(name)}.qss")


def _read_theme_file(resolved):
    try:
        with open(os.path.join(THEME_DIR, f"{resolved}.qss"), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _read_theme_resource(resolved):
    try:
        return resources.files("themes").joinpath(f"{resolved}.qss").read_text(encoding="utf-8")
    except (AttributeError, ModuleNotFoundError, OSError, ValueError):
        return None


def load_theme(name):
    resolved = resolve_theme_name(name)
    content = _read_theme_file(resolved)
    if content is not None:
        return content
    content = _read_theme_resource(resolved)
    if content is not None:
        return content
    if resolved != "default":
        return load_theme("default")
    return ""


def apply_theme(widget, name):
    resolved = resolve_theme_name(name)
    widget.setStyleSheet(load_theme(resolved))
    return resolved
