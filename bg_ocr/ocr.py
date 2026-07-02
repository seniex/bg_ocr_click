from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import threading

HAS_PIL = False
HAS_TESSERACT = False
HAS_PADDLE = True

Image = ImageEnhance = ImageFilter = None
pytesseract = None

try:
    from PIL import Image, ImageEnhance, ImageFilter
    HAS_PIL = True
except ImportError:
    pass

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    pass


class _PaddleJsonEngine:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._exe_path = ""
        self._ready = False

    def start(self, exe_path):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                if exe_path == self._exe_path:
                    return
                self.stop()
            self._exe_path = exe_path
            self._ready = False
            cwd = os.path.dirname(os.path.abspath(exe_path))
            create_no_window = 0x08000000
            self._proc = subprocess.Popen(
                [exe_path],
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                errors="replace",
                creationflags=create_no_window,
            )
            for _ in range(60):
                line = self._proc.stdout.readline()
                if "OCR init completed" in line:
                    self._ready = True
                    return
                if not line:
                    break
            raise RuntimeError("PaddleOCR-json initialization timeout or failure")

    def stop(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
            self._ready = False

    def ocr_image(self, img_pil):
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                raise RuntimeError("PaddleOCR-json process not running")
            buf = io.BytesIO()
            img_pil.convert("RGB").save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            req = json.dumps({"image_base64": b64}, ensure_ascii=True)
            self._proc.stdin.write(req + "\n")
            self._proc.stdin.flush()
            resp = self._proc.stdout.readline()
        if not resp:
            raise RuntimeError("PaddleOCR-json no response")
        obj = json.loads(resp)
        if obj.get("code") != 100:
            return []
        results = []
        for item in (obj.get("data") or []):
            results.append(
                {
                    "text": item.get("text", ""),
                    "box": item.get("box", []),
                    "score": item.get("score", 0.0),
                }
            )
        return results


_paddle_engine = _PaddleJsonEngine()


def get_paddle_engine():
    return _paddle_engine


def _get_paddle_engine():
    return get_paddle_engine()


def preprocess(image, scale=1, contrast=1.5, binarize=True, threshold=128, invert=False):
    try:
        if scale > 1:
            w, h = image.size
            image = image.resize((w * scale, h * scale), Image.LANCZOS)
        image = image.convert("L")
        if invert:
            image = image.point(lambda p: 255 - p)
        if contrast != 1.0:
            image = ImageEnhance.Contrast(image).enhance(contrast)
        image = image.filter(ImageFilter.SHARPEN)
        if binarize:
            t = threshold
            image = image.point(lambda p: 255 if p > t else 0)
        return image
    except Exception:
        return None


def _set_tess(path):
    if path and os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path


def _make_ocr_cfg(psm=6):
    return f"--psm {psm} --oem 3"


def do_ocr_text(img, engine="paddle", lang="chi_sim", tess_path=None, psm=6):
    if engine == "paddle":
        try:
            eng = _get_paddle_engine()
            items = eng.ocr_image(img)
            if not items:
                return None
            return "\n".join(it["text"] for it in items)
        except Exception as e:
            raise RuntimeError(f"PaddleOCR-json recognition failed: {e}") from e
    if not HAS_TESSERACT:
        return None
    try:
        _set_tess(tess_path)
        return pytesseract.image_to_string(img, lang=lang, config=_make_ocr_cfg(psm))
    except Exception:
        return None


def do_ocr_find_pos(img, keywords, engine="paddle", lang="chi_sim", tess_path=None, psm=6):
    if engine == "paddle":
        try:
            eng = _get_paddle_engine()
            items = eng.ocr_image(img)
            for it in items:
                txt = it["text"].lower().strip()
                txt_nsp = txt.replace(" ", "")
                if any(k in txt or k in txt_nsp for k in keywords):
                    box = it["box"]
                    if box and len(box) >= 2:
                        xs = [p[0] for p in box]
                        ys = [p[1] for p in box]
                        return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))
        except Exception:
            pass
        return None

    if not HAS_TESSERACT:
        return None
    try:
        _set_tess(tess_path)
        pos_psm = 6
        d = pytesseract.image_to_data(
            img,
            lang=lang,
            config=_make_ocr_cfg(pos_psm),
            output_type=pytesseract.Output.DICT,
        )
        tokens = [
            (
                d["text"][i].lower().strip(),
                d["left"][i],
                d["top"][i],
                d["width"][i],
                d["height"][i],
            )
            for i in range(len(d["text"]))
            if d["text"][i].strip()
        ]
        if not tokens:
            return None

        for txt, lx, ty, tw, th in tokens:
            if any(k in txt for k in keywords):
                return (lx + tw // 2, ty + th // 2)

        lines = {}
        for txt, lx, ty, tw, th in tokens:
            key = round((ty + th / 2) / 20.0)
            lines.setdefault(key, []).append((txt, lx, ty, tw, th))
        for _, items in sorted(lines.items(), key=lambda kv: kv[0]):
            for n in range(len(items) - 1):
                a, b = items[n], items[n + 1]
                pair = (a[0] + b[0]).replace(" ", "")
                pair_sp = (a[0] + " " + b[0]).replace(" ", "")
                if any(k in pair or k in pair_sp for k in keywords):
                    lx = min(a[1], b[1])
                    ty = min(a[2], b[2])
                    rx = max(a[1] + a[3], b[1] + b[3])
                    by = max(a[2] + a[4], b[2] + b[4])
                    return ((lx + rx) // 2, (ty + by) // 2)
    except Exception:
        return None
    return None
