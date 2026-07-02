from __future__ import annotations

import threading
import time

from bg_ocr.config import LOG_FILE, save_config
from bg_ocr.system import list_windows_by_process


def _start_auto_bind_loop(self):
    if self._auto_bind_thread and self._auto_bind_thread.is_alive():
        return
    self._auto_bind_stop.clear()
    self._auto_bind_thread = threading.Thread(target=self._auto_bind_loop, daemon=True)
    self._auto_bind_thread.start()


def _auto_bind_loop(self):
    while not self._auto_bind_stop.is_set():
        try:
            enabled = self.cfg.get("auto_bind_enabled", False)
            proc = self.cfg.get("auto_bind_process", "").strip()
            if enabled and proc:
                wins = list_windows_by_process(proc)
                if len(wins) == 1:
                    hwnd, title = wins[0]
                    cur_hwnd = self.cfg.get("target_hwnd", 0)
                    if hwnd != cur_hwnd:
                        self.cfg["target_hwnd"] = hwnd
                        self.cfg["target_title"] = title
                        save_config(self.cfg)
                        self.after(0, self._refresh_monitor_state)
                        self.after(
                            0,
                            lambda h=hwnd, t=title: self.log(
                                f"[自动绑定] 已绑定进程 {proc} 的窗口 [{h}] {t}", "ok"
                            ),
                        )
                elif len(wins) > 1:
                    cur_hwnd = self.cfg.get("target_hwnd", 0)
                    if not cur_hwnd:
                        self.after(
                            0,
                            lambda n=len(wins), p=proc: self.log(
                                f"[auto-bind] process {p} has {n} windows; bind manually", "warn"
                            ),
                        )
        except Exception as e:
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] [自动绑定] 异常: {e}\n")
            except Exception:
                pass
        self._auto_bind_stop.wait(3.0)
