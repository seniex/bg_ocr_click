from __future__ import annotations

import json
from typing import Any


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _json_load(text: str, default: Any):
    text = (text or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def _parse_region(text: str):
    value = _json_load(text, None)
    if isinstance(value, list) and len(value) == 4:
        try:
            return [int(value[0]), int(value[1]), int(value[2]), int(value[3])]
        except Exception:
            return None
    return None


def _format_region(region):
    if not region:
        return ""
    try:
        return _json_dump([int(region[0]), int(region[1]), int(region[2]), int(region[3])])
    except Exception:
        return ""


def _parse_color(text: str):
    if not text.strip():
        return [255, 0, 0]
    text = text.strip().replace("RGB", "").replace("rgb", "").replace("(", "").replace(")", "")
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) != 3:
        return [255, 0, 0]
    try:
        return [max(0, min(255, int(parts[0]))), max(0, min(255, int(parts[1]))), max(0, min(255, int(parts[2])))]
    except Exception:
        return [255, 0, 0]


def _format_color(color):
    try:
        return f"{int(color[0])},{int(color[1])},{int(color[2])}"
    except Exception:
        return "255,0,0"
