from __future__ import annotations

import ctypes
import random
import threading
import time

from bg_ocr.config import LOG_FILE as _LOG_FILE

HAS_WIN32 = False
HAS_PYAUTOGUI = False

win32gui = win32api = win32con = None
pyautogui = None

try:
    import win32gui, win32api, win32con
    HAS_WIN32 = True
except ImportError:
    pass

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    pass


def _make_lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def click_postmessage(hwnd, rel_x, rel_y, double=False, right=False):
    try:
        lp = _make_lp(rel_x, rel_y)
        if right:
            win32api.PostMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lp)
            time.sleep(0.05)
            win32api.PostMessage(hwnd, win32con.WM_RBUTTONUP, 0, lp)
            return True, f"后台右键 窗口({rel_x},{rel_y})"
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
        time.sleep(0.05)
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)
        if double:
            time.sleep(0.05)
            win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
            time.sleep(0.05)
            win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)
        return True, f"后台{'双击' if double else '单击'} 窗口({rel_x},{rel_y})"
    except Exception as e:
        return False, str(e)


def _qs_log(msg):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
            _lf.write(f"[{time.strftime('%H:%M:%S')}] [QS] {msg}\n")
    except Exception:
        pass


def _sink_window(hwnd):
    try:
        if not win32gui.IsWindow(hwnd):
            return
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_BOTTOM,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
    except Exception as e:
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
                _lf.write(f"[{time.strftime('%H:%M:%S')}] _sink_window failed: {e}\n")
        except Exception:
            pass


def _restore_fg(saved):
    try:
        if saved and win32gui.IsWindow(saved):
            ctypes.windll.user32.SwitchToThisWindow(saved, True)
    except Exception:
        pass


_quickswitch_lock = threading.Lock()


def click_quickswitch(hwnd, abs_x, abs_y, double=False, sink_after=False, right=False, humanize=True):
    with _quickswitch_lock:
        try:
            saved = win32gui.GetForegroundWindow()
        except Exception:
            saved = None
        _qs_log(f"click_quickswitch enter sink_after={sink_after} saved_hwnd={saved}")
        try:
            if not win32gui.IsWindow(hwnd):
                return False, "窗口不存在"
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            time.sleep(0.15)
        except Exception:
            pass
        try:
            if HAS_PYAUTOGUI:
                if humanize:
                    pyautogui.moveTo(abs_x, abs_y, duration=random.uniform(0.08, 0.18))
                    time.sleep(random.uniform(0.05, 0.10))
                else:
                    pyautogui.moveTo(abs_x, abs_y)
                if right:
                    pyautogui.rightClick(abs_x, abs_y)
                elif double:
                    pyautogui.doubleClick(abs_x, abs_y)
                else:
                    pyautogui.click(abs_x, abs_y)
            else:
                win32api.SetCursorPos((abs_x, abs_y))
                if right:
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, abs_x, abs_y, 0, 0)
                    time.sleep(0.05)
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, abs_x, abs_y, 0, 0)
                else:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, abs_x, abs_y, 0, 0)
                    time.sleep(0.05)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, abs_x, abs_y, 0, 0)
                    if double:
                        time.sleep(0.05)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, abs_x, abs_y, 0, 0)
                        time.sleep(0.05)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, abs_x, abs_y, 0, 0)
            click_desc = "右键" if right else ("双击" if double else "单击")
            msg = f"前台{click_desc} 屏幕({abs_x},{abs_y})"
        except Exception as e:
            if sink_after:
                _sink_window(hwnd)
                _restore_fg(saved)
            return False, str(e)
        time.sleep(0.1)
        if sink_after:
            _qs_log("sink_after=True -> _sink_window + _restore_fg")
            _sink_window(hwnd)
            _restore_fg(saved)
        else:
            _qs_log("sink_after=False -> no restore")
        return True, msg


def _resolve_action_pos(action, match_pos, hwnd, cmode):
    mode = action.get("pos_mode", "match_center")

    if mode == "match_center":
        if match_pos is None:
            return None
        wx, wy = match_pos
    elif mode == "offset":
        if match_pos is None:
            return None
        wx = match_pos[0] + int(action.get("offset_x", 0))
        wy = match_pos[1] + int(action.get("offset_y", 0))
    elif mode == "window":
        wx = int(action.get("abs_x", 0))
        wy = int(action.get("abs_y", 0))
    elif mode == "screen":
        sx = int(action.get("abs_x", 0))
        sy = int(action.get("abs_y", 0))
        return sx, sy, "screen"
    else:
        return None

    if cmode == "quickswitch":
        try:
            rect = win32gui.GetWindowRect(hwnd)
            return wx + rect[0], wy + rect[1], "screen"
        except Exception:
            return wx, wy, "screen"
    return wx, wy, "window"


_FKEY_VK = {
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def exec_action_sequence(actions, match_pos, hwnd, g, log_fn, stop_fn, stop_hotkey=""):
    cmode = g.get("click_mode", "postmessage")
    jitter = g.get("mouse_jitter", True)
    humanize = g.get("mouse_humanize", True)
    sink_flag = g.get("sink_after_click", False)
    _stop_vk = _FKEY_VK.get(stop_hotkey.lower(), 0) if stop_hotkey else 0

    def _should_stop():
        if stop_fn():
            return True
        if _stop_vk:
            try:
                state = ctypes.windll.user32.GetAsyncKeyState(_stop_vk)
                if state & 0x8000:
                    return True
            except Exception:
                pass
        return False

    _qs_saved = None
    _qs_mouse = None

    def _do_sequence():
        for i, action in enumerate(actions):
            if _should_stop():
                return False
            kind = action.get("kind", "mouse")
            pre = float(action.get("pre_delay", 0.0))
            if pre > 0:
                time.sleep(pre)
            if _should_stop():
                return False

            try:
                if kind == "delay":
                    secs = float(action.get("seconds", 0.5))
                    if secs > 0:
                        time.sleep(secs)
                    log_fn(f"[序列{i+1}] 等待 {secs}s", "info")
                    continue

                if kind == "key":
                    key_str = action.get("key", "").strip()
                    act = action.get("action", "press")
                    count = max(1, int(action.get("count", 1)))
                    interval = float(action.get("interval", 0.05))
                    if not key_str:
                        continue
                    keys = [k.strip() for k in key_str.replace("+", " + ").split("+") if k.strip()]
                    for n in range(count):
                        if _should_stop():
                            return False
                        if act == "press":
                            if len(keys) > 1:
                                pyautogui.hotkey(*keys)
                            else:
                                pyautogui.press(keys[0])
                        elif act == "down":
                            for k in keys:
                                pyautogui.keyDown(k)
                        elif act == "up":
                            for k in reversed(keys):
                                pyautogui.keyUp(k)
                        if n < count - 1 and interval > 0:
                            time.sleep(interval)
                    log_fn(f"[序列{i+1}] 键盘 {act} {key_str} x{count}", "info")
                    continue

                if kind == "text":
                    text_val = action.get("text", "")
                    interval = float(action.get("interval", 0.05))
                    if text_val:
                        pyautogui.typewrite(text_val, interval=interval)
                    log_fn(f"[序列{i+1}] 输入文本 len={len(text_val)}", "info")
                    continue

                if kind == "scroll":
                    sx = int(action.get("abs_x", 0))
                    sy = int(action.get("abs_y", 0))
                    direction = action.get("direction", "down")
                    clicks = int(action.get("clicks", 1))
                    interval = float(action.get("interval", 0.1))
                    multiplier = float(action.get("multiplier", 1.0))
                    amount = int(clicks * multiplier)
                    if amount < 1:
                        amount = 1
                    if humanize:
                        pyautogui.moveTo(sx, sy, duration=random.uniform(0.05, 0.12))
                    else:
                        pyautogui.moveTo(sx, sy)
                    scroll_val = amount if direction == "up" else -amount
                    pyautogui.scroll(scroll_val, x=sx, y=sy)
                    log_fn(f"[序列{i+1}] 滚轮 {direction} x{amount} @({sx},{sy})", "info")
                    continue

                if kind == "mouse":
                    click_type = action.get("click_type", "single")
                    count = max(1, int(action.get("count", 1)))
                    interval = float(action.get("interval", 0.1))

                    res = _resolve_action_pos(action, match_pos, hwnd, cmode)
                    if res is None:
                        log_fn(f"[序列{i+1}] 鼠标：无法解析坐标，跳过", "warn")
                        continue
                    ax, ay, coord = res

                    if jitter and click_type not in ("move",):
                        ax += random.randint(-3, 3)
                        ay += random.randint(-3, 3)

                    needs_foreground = (cmode == "quickswitch") or (coord == "screen")

                    if coord == "screen":
                        sax, say = ax, ay
                    else:
                        try:
                            rect = win32gui.GetWindowRect(hwnd)
                            sax, say = ax + rect[0], ay + rect[1]
                        except Exception:
                            sax, say = ax, ay

                    if click_type == "move":
                        if needs_foreground:
                            if humanize:
                                pyautogui.moveTo(sax, say, duration=random.uniform(0.08, 0.18))
                            else:
                                pyautogui.moveTo(sax, say)
                        log_fn(f"[序列{i+1}] 鼠标移动 -> ({sax},{say})", "info")
                        continue

                    if click_type in ("down", "up"):
                        if humanize:
                            pyautogui.moveTo(sax, say, duration=random.uniform(0.05, 0.12))
                        else:
                            pyautogui.moveTo(sax, say)
                        if click_type == "down":
                            pyautogui.mouseDown(x=sax, y=say)
                        else:
                            pyautogui.mouseUp(x=sax, y=say)
                        log_fn(f"[序列{i+1}] 鼠标{click_type} @({sax},{say})", "info")
                        continue

                    double = click_type == "double"
                    right = click_type == "right"

                    if cmode == "postmessage" and coord != "screen":
                        for n in range(count):
                            if _should_stop():
                                return False
                            if right:
                                ok, msg = click_postmessage(hwnd, ax, ay, False, right=True)
                            else:
                                ok, msg = click_postmessage(hwnd, ax, ay, double)
                            log_fn(f"[序列{i+1}] {msg}", "ok" if ok else "err")
                            if n < count - 1 and interval > 0:
                                time.sleep(interval)
                    else:
                        for n in range(count):
                            if _should_stop():
                                return False
                            if humanize:
                                pyautogui.moveTo(sax, say, duration=random.uniform(0.05, 0.12))
                                time.sleep(random.uniform(0.03, 0.06))
                            else:
                                pyautogui.moveTo(sax, say)
                            if right:
                                pyautogui.rightClick(sax, say)
                            elif double:
                                pyautogui.doubleClick(sax, say)
                            else:
                                pyautogui.click(sax, say)
                            click_desc = "右键" if right else ("双击" if double else "单击")
                            log_fn(f"[序列{i+1}] 前台{click_desc} x{n+1} @({sax},{say})", "info")
                            if n < count - 1 and interval > 0:
                                time.sleep(interval)
            except Exception as e:
                log_fn(f"[序列{i+1}] 异常: {e}", "err")
                try:
                    with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
                        import traceback

                        _lf.write(
                            f"[{time.strftime('%H:%M:%S')}] exec_action_sequence 序列{i+1} 异常:\n{traceback.format_exc()}\n"
                        )
                except Exception:
                    pass
        return True

    if cmode == "quickswitch":
        with _quickswitch_lock:
            try:
                _qs_saved = win32gui.GetForegroundWindow()
            except Exception:
                pass
            try:
                _qs_mouse = pyautogui.position()
            except Exception:
                pass
            try:
                ctypes.windll.user32.BlockInput(True)
            except Exception:
                pass
            try:
                if win32gui.IsWindow(hwnd):
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        time.sleep(0.1)
                    ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
                    time.sleep(0.15)
            except Exception:
                pass
            _do_sequence()
            try:
                ctypes.windll.user32.BlockInput(False)
            except Exception:
                pass
            if sink_flag and _qs_saved:
                try:
                    if win32gui.IsWindow(_qs_saved):
                        ctypes.windll.user32.SwitchToThisWindow(_qs_saved, True)
                        time.sleep(0.05)
                except Exception:
                    _restore_fg(_qs_saved)
            if _qs_mouse:
                try:
                    pyautogui.moveTo(_qs_mouse.x, _qs_mouse.y, duration=0)
                except Exception:
                    pass
    else:
        _do_sequence()
