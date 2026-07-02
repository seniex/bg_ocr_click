from __future__ import annotations


def _clear_hotkeys():
    try:
        import keyboard as _kb

        _kb.unhook_all_hotkeys()
    except Exception:
        pass


def _apply_hotkeys(self):
    try:
        import keyboard as _kb

        _clear_hotkeys()
        hk_s = self.cfg.get("hotkey_start", "")
        hk_t = self.cfg.get("hotkey_stop", "")
        if hk_s:
            _kb.add_hotkey(hk_s, lambda: self.after(0, self._start))
        if hk_t:
            _kb.add_hotkey(hk_t, lambda: self.after(0, self._stop))
        if hk_s or hk_t:
            self.log(f"Hotkeys registered start={hk_s.upper() or 'none'} stop={hk_t.upper() or 'none'}", "ok")
    except ImportError:
        self.log("keyboard 未安装，快捷键不可用", "warn")
    except Exception as e:
        self.log(f"快捷键注册失败: {e}", "warn")
