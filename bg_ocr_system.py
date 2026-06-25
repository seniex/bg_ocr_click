from __future__ import annotations

import ctypes

HAS_WIN32 = False
win32gui = win32process = None

try:
    import win32gui, win32process
    HAS_WIN32 = True
except ImportError:
    pass


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin():
    import os
    import sys

    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
    except Exception:
        pass
    sys.exit(0)


def list_windows():
    results = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if t.strip():
                results.append((h, t))

    win32gui.EnumWindows(cb, None)
    return results


def list_windows_by_process(proc_name):
    if not HAS_WIN32:
        return []
    proc_name_lower = proc_name.strip().lower()
    if not proc_name_lower:
        return []

    pid_set = set()
    try:
        import psutil

        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and p.info["name"].lower() == proc_name_lower:
                    pid_set.add(p.info["pid"])
            except Exception:
                pass
    except ImportError:
        try:
            def _pid_cb(h, _):
                if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).strip():
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(h)
                        import ctypes as _ct

                        PROCESS_QUERY_LIMITED = 0x1000
                        hp = _ct.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
                        if hp:
                            buf = _ct.create_unicode_buffer(260)
                            _ct.windll.psapi.GetModuleFileNameExW(hp, None, buf, 260)
                            _ct.windll.kernel32.CloseHandle(hp)
                            if buf.value.lower().endswith(proc_name_lower):
                                pid_set.add(pid)
                    except Exception:
                        pass

            win32gui.EnumWindows(_pid_cb, None)
        except Exception:
            pass

    if not pid_set:
        return []

    results = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if t.strip():
                try:
                    _, pid = win32process.GetWindowThreadProcessId(h)
                    if pid in pid_set:
                        results.append((h, t))
                except Exception:
                    pass

    win32gui.EnumWindows(cb, None)
    return results
