from __future__ import annotations

import ctypes
import threading

HAS_WIN32 = False
HAS_PIL = False
HAS_SCREENINFO = False

win32gui = win32ui = win32con = None
Image = ImageGrab = None
screeninfo = None

try:
    import win32gui, win32ui, win32con
    HAS_WIN32 = True
except ImportError:
    pass

try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
except ImportError:
    pass

try:
    import screeninfo
    HAS_SCREENINFO = True
except ImportError:
    pass

_screenshot_lock = threading.Lock()


def _vscreen_offset():
    if HAS_SCREENINFO:
        try:
            m = screeninfo.get_monitors()
            if m:
                return min(x.x for x in m), min(x.y for x in m)
        except Exception:
            pass
    return 0, 0


def _printwindow_full(hwnd):
    hwndDC = saveDC = mfcDC = bmp = None
    try:
        rect = win32gui.GetWindowRect(hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w <= 0 or h <= 0:
            return None
        hwndDC = win32gui.GetWindowDC(hwnd)
        if not hwndDC:
            return None
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(bmp)
        if not ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2):
            return None
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        return Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
    except Exception:
        return None
    finally:
        for obj, fn in [
            (bmp, lambda o: win32gui.DeleteObject(o.GetHandle())),
            (saveDC, lambda o: o.DeleteDC()),
            (mfcDC, lambda o: o.DeleteDC()),
            (hwndDC, lambda o: win32gui.ReleaseDC(hwnd, o)),
        ]:
            if obj:
                try:
                    fn(obj)
                except Exception:
                    pass


def _imagegrab_region(hwnd, region):
    try:
        full = ImageGrab.grab(all_screens=True)
        rect = win32gui.GetWindowRect(hwnd)
        ox, oy = _vscreen_offset()
        x1 = rect[0] + region[0] - ox
        y1 = rect[1] + region[1] - oy
        x2 = rect[0] + region[2] - ox
        y2 = rect[1] + region[3] - oy
        return full.crop((x1, y1, x2, y2))
    except Exception:
        return None


def capture_region(hwnd, region, mode="auto"):
    with _screenshot_lock:
        if mode == "imagegrab":
            img = _imagegrab_region(hwnd, region)
            return img, "imagegrab"

        if mode == "printwindow":
            full = _printwindow_full(hwnd)
            if full is None:
                return None, "printwindow_failed"
            x1 = max(0, int(region[0]))
            y1 = max(0, int(region[1]))
            x2 = min(full.width, int(region[2]))
            y2 = min(full.height, int(region[3]))
            if x2 <= x1 or y2 <= y1:
                return None, "region_invalid"
            return full.crop((x1, y1, x2, y2)), "printwindow"

        img = _imagegrab_region(hwnd, region)
        if img is not None:
            try:
                if img.convert("L").getextrema()[1] > 15:
                    return img, "imagegrab"
            except Exception:
                pass
        full = _printwindow_full(hwnd)
        if full is None:
            return img, "auto(ig_dark)"
        x1 = max(0, int(region[0]))
        y1 = max(0, int(region[1]))
        x2 = min(full.width, int(region[2]))
        y2 = min(full.height, int(region[3]))
        if x2 <= x1 or y2 <= y1:
            return img, "auto(ig_dark)"
        return full.crop((x1, y1, x2, y2)), "auto->pw"


def capture_full_preview(hwnd, cap_mode="printwindow"):
    with _screenshot_lock:
        if cap_mode == "imagegrab":
            try:
                full = ImageGrab.grab(all_screens=True)
                rect = win32gui.GetWindowRect(hwnd)
                ox, oy = _vscreen_offset()
                return full.crop((rect[0] - ox, rect[1] - oy, rect[2] - ox, rect[3] - oy))
            except Exception:
                pass
            return _printwindow_full(hwnd)

        img = _printwindow_full(hwnd)
        if img is not None:
            return img
        try:
            full = ImageGrab.grab(all_screens=True)
            rect = win32gui.GetWindowRect(hwnd)
            ox, oy = _vscreen_offset()
            return full.crop((rect[0] - ox, rect[1] - oy, rect[2] - ox, rect[3] - oy))
        except Exception:
            pass
        return None
