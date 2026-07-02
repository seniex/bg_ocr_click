from __future__ import annotations

import re

HAS_CV2 = False
HAS_NUMPY = False

cv2 = None
np = None

try:
    import cv2
    import numpy as np

    HAS_CV2 = True
    HAS_NUMPY = True
except ImportError:
    try:
        import numpy as np

        HAS_NUMPY = True
    except ImportError:
        pass


def match_keywords(text, keywords):
    if not text or not keywords:
        return False, None
    haystack = text.lower()
    haystack_nsp = haystack.replace(" ", "")
    for keyword in _split_keywords(keywords):
        needle = keyword.lower()
        needle_nsp = needle.replace(" ", "")
        if needle and (needle in haystack or needle_nsp in haystack_nsp):
            return True, needle
    return False, None


def _split_keywords(keywords):
    if isinstance(keywords, (list, tuple)):
        parts = keywords
    else:
        parts = re.split(r"[,;|，；、\r\n]+", str(keywords))
    return [p.strip() for p in parts if str(p).strip()]


def _imread_unicode(path):
    if not HAS_CV2 or not HAS_NUMPY:
        return None
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def match_template(image, template, threshold):
    if not HAS_CV2 or not HAS_NUMPY or image is None or template is None:
        return False, None, 0.0
    src = _pil_to_bgr(image)
    if src is None:
        return False, None, 0.0
    src_gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template
    th, tw = tmpl_gray.shape[:2]
    ih, iw = src_gray.shape[:2]
    if tw <= 0 or th <= 0 or tw > iw or th > ih:
        return False, None, 0.0
    result = cv2.matchTemplate(src_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    pos = (int(max_loc[0] + tw / 2), int(max_loc[1] + th / 2))
    return max_val >= float(threshold), pos, float(max_val)


def match_color(image, target_color, tolerance):
    if not HAS_NUMPY or image is None:
        return False, None
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)
    target = np.array(target_color[:3], dtype=np.int16)
    mask = np.all(np.abs(arr - target) <= int(tolerance), axis=2)
    ys, xs = np.where(mask)
    if xs.size == 0:
        return False, None
    return True, (int(xs.mean()), int(ys.mean()))


def _pil_to_bgr(image):
    if not HAS_CV2 or not HAS_NUMPY:
        return None
    arr = np.asarray(image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
