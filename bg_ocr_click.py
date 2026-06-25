"""
BgOcrClick v5
后台窗口多组OCR/图像/颜色识别点击工具

特性：
- 三种截图方式：ImageGrab / PrintWindow / 自动
- 三种监控类型：文字OCR / 图像检测 / 颜色识别
- 两种点击方式：PostMessage后台 / QuickSwitch切前台
- 多监控组并发，截图锁防冲突
- 串联流程（方案C链式）
- 坐标点选输入
"""

import sys, os, ctypes, threading, time, json, copy, random
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog

# ── 依赖 ──────────────────────────────────────────────────
MISSING = []
try:
    import win32gui, win32ui, win32con, win32api, win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False; MISSING.append("pywin32")

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False; MISSING.append("Pillow")


# ── 主题 ──────────────────────────────────────────────────
T = {
    "bg":"#1e2130","sidebar":"#161827","card":"#252840","card2":"#2d3150",
    "accent":"#3d6bff","success":"#2ecc71","danger":"#e74c3c","warning":"#f39c12",
    "text":"#e8eaf0","text2":"#9099b8","border":"#363d60",
    "bp":"#3d6bff","bd":"#c0392b","bs":"#27ae60","bg2":"#363d60",
    "lb":"#141520","lt":"#8fc6ff","lw":"#f39c12","lo":"#2ecc71","le":"#e74c3c",
}




# ══════════════════════════════════════════════════════════
#  音效播放
# ══════════════════════════════════════════════════════════
def _play_sound(sound_file):
    """异步播放音效文件（wav/mp3），不阻塞主线程"""
    if not sound_file or not os.path.exists(sound_file):
        return
    def _do():
        try:
            import ctypes as _ct
            # 用 Windows PlaySound（只支持 wav）
            _ct.windll.winmm.PlaySoundW(sound_file, None, 0x0001 | 0x0002)  # SND_FILENAME|SND_ASYNC
        except:
            try:
                import subprocess as _sp
                # fallback: 用 Windows Media Player 命令行播放 mp3
                _sp.Popen(["wmplayer", "/play", "/close", sound_file],
                          stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                          creationflags=0x08000000)
            except: pass
    threading.Thread(target=_do, daemon=True).start()

# ══════════════════════════════════════════════════════════
#  截图层
# ══════════════════════════════════════════════════════════

def pick_screen_coord(callback):
    """
    创建全屏透明覆盖层，用户点击后返回屏幕绝对坐标
    callback(x, y)
    """
    overlay = tk.Toplevel()
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-alpha", 0.01)
    overlay.attributes("-topmost", True)
    overlay.configure(bg="white")
    overlay.title("")

    lbl = tk.Label(overlay, text="请点击目标位置...",
        bg="#222", fg="white", font=("Microsoft YaHei",14),
        padx=20, pady=10)
    lbl.place(relx=0.5, rely=0.05, anchor="center")

    def on_click(e):
        x, y = e.x_root, e.y_root
        overlay.destroy()
        callback(x, y)

    overlay.bind("<Button-1>", on_click)
    overlay.bind("<Escape>", lambda e: overlay.destroy())
    overlay.focus_force()

def pick_window_coord(hwnd, callback, cap_mode="printwindow"):
    """
    截绑定窗口后在截图上点击，返回窗口相对坐标
    callback(rel_x, rel_y)
    """
    img = capture_full_preview(hwnd, cap_mode)
    if img is None:
        messagebox.showwarning("提示","无法截取窗口")
        return

    win = tk.Toplevel()
    win.title("点击选择坐标")
    win.attributes("-topmost", True)

    max_w, max_h = 1200, 800
    scale = min(max_w/img.width, max_h/img.height, 1.0)
    dw, dh = int(img.width*scale), int(img.height*scale)
    disp = img.resize((dw,dh), Image.LANCZOS) if scale<1 else img

    tk_img = ImageTk.PhotoImage(disp)
    canvas = tk.Canvas(win, width=dw, height=dh,
        cursor="crosshair", bg="black", bd=0, highlightthickness=0)
    canvas.pack()
    canvas.create_image(0,0,anchor="nw",image=tk_img)
    canvas._ref = tk_img

    tk.Label(win, text="点击选择坐标位置（Esc取消）",
        bg="#222", fg="#aaa", font=("Microsoft YaHei",9)).pack(fill="x",pady=2)

    def on_click(e):
        rx = int(e.x/scale); ry = int(e.y/scale)
        win.destroy()
        callback(rx, ry)

    canvas.bind("<Button-1>", on_click)
    win.bind("<Escape>", lambda e: win.destroy())

class GroupMonitor:
    """单个监控组的运行引擎"""

    def __init__(self, app, index):
        self.app   = app
        self.index = index
        self._stop = threading.Event()
        self._thread = None

    @property
    def gcfg(self):
        try: return self.app.cfg["groups"][self.index]
        except: return copy.deepcopy(GROUP_DEFAULT)

    @property
    def gtag(self):
        """返回日志前缀，格式: [组N-组名]"""
        try:
            name = self.app.cfg["groups"][self.index].get("name", "")
            if name:
                return f"[组{self.index+1}-{name}]"
        except Exception:
            pass
        return f"[组{self.index+1}]"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        self.app.log(f"{self.gtag} 启动", "ok")
        while not self._stop.is_set():
            g = self.gcfg
            if not g.get("enabled", True):
                # 关闭状态仅作为子流程，不独立循环
                time.sleep(1); continue
            try:
                self._run_once(g)
            except Exception as e:
                self.app.log(f"{self.gtag} 异常: {e}", "err")
                try:
                    import traceback
                    with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
                        _lf.write(f"[{time.strftime('%H:%M:%S')}] {self.gtag} 异常完整堆栈:\n"
                                  f"{traceback.format_exc()}\n")
                except: pass
            # 可中断等待
            interval = max(1, int(g.get("interval",5)))
            for _ in range(interval*2):
                if self._stop.is_set(): break
                time.sleep(0.5)
        self.app.log(f"{self.gtag} 已停止", "warn")

    def run_as_chain(self, gcfg):
        """被串联调用时执行一次（忽略enabled状态）"""
        try: self._run_once(gcfg)
        except Exception as e:
            self.app.log(f"{self.gtag}(链) 异常: {e}", "err")

    def _run_once(self, g):
        hwnd = self.app.cfg.get("target_hwnd",0)
        if not hwnd:
            self.app.log(f"{self.gtag} 未绑定窗口","warn"); return
        try:
            if not win32gui.IsWindow(hwnd):
                self.app.log(f"{self.gtag} 窗口句柄失效，请重新绑定","err"); return
            if win32gui.IsIconic(hwnd):
                self.app.log(f"{self.gtag} 窗口最小化，跳过","warn"); return
        except Exception as e:
            self.app.log(f"{self.gtag} 窗口检查异常: {e}","err"); return

        cap_mode = g.get("capture_mode","global")
        if cap_mode == "global":
            cap_mode = self.app.cfg.get("capture_mode","printwindow")

        # ── 仅弹窗监控模式：跳过识别/点击，直接进入弹窗流程 ──
        if g.get("popup_only_mode") and g.get("popup_enabled")                 and g.get("popup_title_kw","").strip():
            self.app.log(f"{self.gtag} 仅弹窗模式：直接进入弹窗流程","info")
            self._run_popup_flow(g, hwnd, cap_mode)
            return

        region = g.get("region")
        if not region:
            self.app.log(f"{self.gtag} 未设置监控区域","warn"); return

        img, used = capture_region(hwnd, region, cap_mode)
        if img is None:
            self.app.log(f"{self.gtag} 截图失败[{cap_mode}]","err"); return
        self.app.log(f"{self.gtag} 截图成功[{used}] 尺寸{img.size}","info")

        # 调试模式：自动保存截图供诊断
        if g.get("debug_save", False):
            try:
                save_dir = os.path.join(os.path.dirname(CONFIG_FILE))
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, f"debug_g{self.index+1}.png")
                img.save(save_path)
                self.app.log(f"{self.gtag} 截图已保存: {save_path}","info")
            except Exception as e:
                self.app.log(f"{self.gtag} 截图保存失败: {e}","warn")

        matched, click_pos = self._recognize(g, img)
        if not matched:
            self.app.log(f"{self.gtag} 未匹配","info"); return

        self.app.log(f"{self.gtag} 匹配成功","ok")
        self._play_if("match")
        self._do_action(g, hwnd, region, click_pos)

        # 弹窗流程
        if g.get("popup_enabled") and g.get("popup_title_kw","").strip():
            self._run_popup_flow(g, hwnd, cap_mode)
            return

        # 串联
        if g.get("chain_enabled") and g.get("chain_target",-1) >= 0:
            wait = max(0, int(g.get("chain_wait",1)))
            self.app.log(f"{self.gtag} 串联等待 {wait}s...","info")
            for _ in range(wait*2):
                if self._stop.is_set(): return
                time.sleep(0.5)
            self._run_chain(g["chain_target"])

    def _do_action(self, g, hwnd, region, click_pos):
        cmode = g.get("click_mode", "postmessage")
        actions = g.get("actions", [])

        # ── 旧配置迁移：无 actions 时从旧字段生成一条默认动作 ──
        if not actions:
            ctype   = g.get("click_type", "single")
            ctarget = g.get("click_target", "keyword")
            if not ctarget:
                ctarget = "window" if g.get("custom_click", False) else "keyword"
            if ctarget == "keyword":
                migrated = {"kind": "mouse", "pre_delay": 0.0,
                            "pos_mode": "match_center",
                            "click_type": ctype, "count": 1, "interval": 0.1}
            elif ctarget == "window":
                migrated = {"kind": "mouse", "pre_delay": 0.0,
                            "pos_mode": "window",
                            "abs_x": g.get("custom_x", 0),
                            "abs_y": g.get("custom_y", 0),
                            "click_type": ctype, "count": 1, "interval": 0.1}
            else:  # screen
                migrated = {"kind": "mouse", "pre_delay": 0.0,
                            "pos_mode": "screen",
                            "abs_x": g.get("custom_x", 0),
                            "abs_y": g.get("custom_y", 0),
                            "click_type": ctype, "count": 1, "interval": 0.1}
            actions = [migrated]

        # match_pos：识别中心转为窗口相对坐标
        if click_pos and region:
            match_pos = (region[0] + click_pos[0], region[1] + click_pos[1])
        elif region:
            match_pos = ((region[0]+region[2])//2, (region[1]+region[3])//2)
        else:
            match_pos = click_pos

        exec_action_sequence(
            actions, match_pos, hwnd, g,
            lambda msg, tag: self.app.log(f"{self.gtag} {msg}", tag),
            self._stop.is_set,
            stop_hotkey=self.app.cfg.get("hotkey_stop", "")
        )

    def _find_windows_by_title(self, kw):
        """按标题关键词枚举所有可见窗口，返回 {hwnd: title}"""
        result = {}
        kw_lower = kw.lower()
        def cb(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if t.strip() and kw_lower in t.lower():
                    result[h] = t
        try:
            win32gui.EnumWindows(cb, None)
        except: pass
        return result

    def _wait_for_popup(self, title_kw, main_hwnds, timeout):
        """
        等待弹窗出现：新出现的、标题含关键词的窗口
        main_hwnds: 已知主窗口hwnd集合（排除）
        返回新弹窗hwnd列表，超时返回空列表
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop.is_set(): return []
            wins = self._find_windows_by_title(title_kw)
            popups = [h for h in wins if h not in main_hwnds]
            if popups:
                return popups
            time.sleep(0.3)
        return []

    def _wait_for_hwnd_close(self, hwnd, timeout):
        """等待指定hwnd窗口消失，超时返回False"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop.is_set(): return True
            try:
                if not win32gui.IsWindow(hwnd): return True
                if not win32gui.IsWindowVisible(hwnd): return True
                t = win32gui.GetWindowText(hwnd)
                if not t.strip(): return True
            except: return True
            time.sleep(0.2)
        return False

    def _wait_popup_stable(self, hwnd, min_w=50, min_h=50,
                           stable_ms=300, timeout=3.0):
        """
        等待弹窗尺寸稳定：
        - 尺寸超过 min_w x min_h（排除动画初始帧）
        - 连续 stable_ms 毫秒尺寸不再变化
        - 超过 timeout 秒强制继续
        """
        deadline = time.time() + timeout
        last_size = None
        stable_since = None

        while time.time() < deadline:
            if self._stop.is_set(): return
            try:
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2]-rect[0]; h = rect[3]-rect[1]
            except:
                return

            if w < min_w or h < min_h:
                # 尺寸太小，还在动画中，继续等
                last_size = None; stable_since = None
                time.sleep(0.05)
                continue

            curr = (w, h)
            if curr != last_size:
                last_size = curr
                stable_since = time.time()
                time.sleep(0.05)
                continue

            # 尺寸稳定了，看是否超过稳定时长
            if time.time() - stable_since >= stable_ms / 1000.0:
                self.app.log(f"[弹窗] 弹窗尺寸稳定: {w}x{h}","info")
                return

            time.sleep(0.05)

        self.app.log(f"[弹窗] 等待弹窗稳定超时，强制继续","warn")

    def _check_size_cond(self, tmpl, w, h):
        """检查弹窗尺寸是否满足条件，满足返回True，不满足返回False（调用方决定跳过）"""
        if not tmpl.get("size_cond_enabled", False):
            return False  # 未启用条件，默认全窗口
        w_op  = tmpl.get("size_cond_w_op", ">")
        w_val = int(tmpl.get("size_cond_w_val", 0))
        h_op  = tmpl.get("size_cond_h_op", ">")
        h_val = int(tmpl.get("size_cond_h_val", 0))
        logic = tmpl.get("size_cond_logic", "and")
        ops = {">": lambda a,b: a>b, "<": lambda a,b: a<b,
               ">=": lambda a,b: a>=b, "<=": lambda a,b: a<=b}
        w_match = ops.get(w_op, ops[">"])(w, w_val)
        h_match = ops.get(h_op, ops[">"])(h, h_val)
        if logic == "or":
            return w_match or h_match
        return w_match and h_match

    def _recognize_popup(self, tmpl, hwnd, cap_mode):
        """
        对弹窗截图识别，支持尺寸条件+指定区域
        返回 (matched, click_pos, img)
        """
        tname = tmpl.get("name","模板")
        try:
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2]-rect[0]; h = rect[3]-rect[1]
            if w<=0 or h<=0:
                self.app.log(f"[弹窗]「{tname}」窗口尺寸异常 {w}x{h}","err")
                return False, None, None
        except Exception as e:
            self.app.log(f"[弹窗]「{tname}」获取窗口尺寸失败: {e}","err")
            return False, None, None

        # 尺寸条件判断：
        # - 未启用条件 → 检测全窗口
        # - 启用条件且满足 → 检测指定区域
        # - 启用条件但不满足 → 跳过此条检测
        size_cond_enabled = tmpl.get("size_cond_enabled", False)
        if size_cond_enabled:
            cond_met = self._check_size_cond(tmpl, w, h)
            if not cond_met:
                self.app.log(f"[弹窗]「{tname}」弹窗{w}x{h} 不满足尺寸条件，跳过","info")
                return False, None, None
            region = tmpl.get("region")
            if region:
                crop_region = [
                    max(0, region[0]), max(0, region[1]),
                    min(w, region[2]), min(h, region[3])
                ]
                self.app.log(f"[弹窗]「{tname}」弹窗{w}x{h} 满足尺寸条件，检测区域{crop_region}","info")
            else:
                crop_region = [0, 0, w, h]
                self.app.log(f"[弹窗]「{tname}」弹窗{w}x{h} 满足尺寸条件，检测全窗口","info")
        else:
            crop_region = [0, 0, w, h]

        img, used = capture_region(hwnd, crop_region, cap_mode)
        if img is None:
            self.app.log(f"[弹窗]「{tname}」截图失败[{cap_mode}]","err")
            return False, None, None
        self.app.log(f"[弹窗]「{tname}」截图成功[{used}] 尺寸{img.size}","info")

        typ    = tmpl.get("type","ocr")
        tess   = self.app.cfg.get("tesseract_path","")
        engine = tmpl.get("ocr_engine","paddle")
        offset_x = crop_region[0]
        offset_y = crop_region[1]

        if typ == "ocr":
            psm      = int(tmpl.get("ocr_psm", 6))
            scale    = int(tmpl.get("ocr_scale", 2))
            binarize = bool(tmpl.get("ocr_binarize", True))
            thr_bin  = int(tmpl.get("ocr_threshold", 128))
            contrast = float(tmpl.get("ocr_contrast", 1.5))
            invert   = bool(tmpl.get("ocr_invert", False))
            if engine == "paddle":
                if scale > 1:
                    try:
                        w2, h2 = img.size[0]*scale, img.size[1]*scale
                        proc = img.resize((w2, h2), Image.LANCZOS)
                    except: proc = img
                else:
                    proc = img
            else:
                proc = preprocess(img, scale=scale, contrast=contrast,
                                  binarize=binarize, threshold=thr_bin, invert=invert)
                if proc is None: proc = img
            text = do_ocr_text(proc, engine=engine,
                               lang=tmpl.get("language","chi_sim"),
                               tess_path=tess, psm=psm)
            eng_info = f"engine={engine}" + (f" psm={psm}" if engine=="tesseract" else "")
            text_short = (text or "").strip().replace("\n"," ")[:80]
            kw_str = tmpl.get("keywords","")
            self.app.log(f"[弹窗]「{tname}」 OCR({eng_info}):「{text_short or '(空)'}」| 关键词:「{kw_str}」","info")

            # 匹配空结果：OCR 为空时视为匹配成功，点击位置无法定位关键词
            if not text:
                if tmpl.get("match_empty_ocr", False):
                    self.app.log(f"[弹窗]「{tname}」 OCR为空，匹配空结果","ok")
                    return True, None, img
                return False, None, img

            matched, first_kw = match_keywords(text, kw_str)
            if not matched: return False, None, img
            kws_for_pos = [first_kw] if first_kw else []
            pos = do_ocr_find_pos(proc, kws_for_pos, engine=engine,
                                  lang=tmpl.get("language","chi_sim"),
                                  tess_path=tess, psm=psm)
            # proc 是放大后的图，坐标除以 scale 还原
            if pos and scale > 1:
                pos = (pos[0] // scale, pos[1] // scale)
            if pos:
                pos = (pos[0] + offset_x, pos[1] + offset_y)
            return True, pos, img

        elif typ == "image":
            tp = tmpl.get("template_path")
            if not tp:
                self.app.log(f"[弹窗]「{tname}」未设置模板图像","warn")
                return False, None, img
            if not os.path.exists(tp):
                self.app.log(f"[弹窗]「{tname}」模板文件不存在: {tp}","err")
                return False, None, img
            try:
                tmpl_img = _imread_unicode(tp)
                if tmpl_img is None:
                    self.app.log(f"[弹窗]「{tname}」模板读取失败（路径含中文或文件损坏）","err")
                    return False, None, img
            except Exception as e:
                self.app.log(f"[弹窗]「{tname}」模板读取异常: {e}","err")
                return False, None, img
            thr = tmpl.get("threshold",80) / 100.0
            matched, pos, score = match_template(img, tmpl_img, thr)
            self.app.log(f"[弹窗]「{tname}」图像匹配得分: {score:.1%} (阈值{thr:.0%})","ok" if matched else "info")
            if pos:
                pos = (pos[0] + offset_x, pos[1] + offset_y)
            return matched, pos, img

        elif typ == "color":
            tc  = tmpl.get("target_color",[255,0,0])
            tol = tmpl.get("tolerance",10)
            matched, pos = match_color(img, tc, tol)
            self.app.log(f"[弹窗]「{tname}」颜色匹配 RGB{tuple(tc)}: {'命中' if matched else '未命中'}","ok" if matched else "info")
            if pos:
                pos = (pos[0] + offset_x, pos[1] + offset_y)
            return matched, pos, img

        return False, None, img

    def _do_popup_action(self, tmpl, hwnd, click_pos, img):
        """对弹窗执行操作序列"""
        actions = tmpl.get("actions", [])

        # 旧配置迁移
        if not actions:
            ctype   = tmpl.get("click_type", "single")
            ctarget = tmpl.get("click_target", "keyword")
            if not ctarget:
                ctarget = "window" if tmpl.get("custom_click", False) else "keyword"
            if ctarget == "keyword":
                migrated = {"kind": "mouse", "pre_delay": 0.0,
                            "pos_mode": "match_center",
                            "click_type": ctype, "count": 1, "interval": 0.1}
            elif ctarget == "window":
                migrated = {"kind": "mouse", "pre_delay": 0.0,
                            "pos_mode": "window",
                            "abs_x": tmpl.get("custom_x", 0),
                            "abs_y": tmpl.get("custom_y", 0),
                            "click_type": ctype, "count": 1, "interval": 0.1}
            else:
                migrated = {"kind": "mouse", "pre_delay": 0.0,
                            "pos_mode": "screen",
                            "abs_x": tmpl.get("custom_x", 0),
                            "abs_y": tmpl.get("custom_y", 0),
                            "click_type": ctype, "count": 1, "interval": 0.1}
            actions = [migrated]

        match_pos = click_pos  # 弹窗的 click_pos 已经是弹窗相对坐标
        exec_action_sequence(
            actions, match_pos, hwnd, tmpl,
            lambda msg, tag: self.app.log(f"[弹窗]「{tmpl.get('name','')}」{msg}", tag),
            self._stop.is_set,
            stop_hotkey=self.app.cfg.get("hotkey_stop", "")
        )
        return True

    def _only_main_remains(self, title_kw, main_hwnds):
        """检查是否只剩主窗口，没有其他同标题窗口"""
        current = self._find_windows_by_title(title_kw)
        extras  = set(current.keys()) - main_hwnds
        # 过滤掉已消失的窗口
        alive_extras = [h for h in extras
                        if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h)
                        and win32gui.GetWindowText(h).strip()]
        return len(alive_extras) == 0

    def _run_popup_flow(self, g, main_hwnd, cap_mode):
        """
        弹窗流程主循环
        退出条件：同标题窗口中只剩主窗口集合（无其他弹窗）
        """
        title_kw      = g.get("popup_title_kw","").strip()
        wait_appear   = max(1, int(g.get("popup_wait_appear",5)))
        total_timeout = max(10, int(g.get("popup_total_timeout",120)))
        no_match_act  = g.get("popup_no_match_action","continue")
        templates     = g.get("popup_templates",[])

        if not title_kw or not templates:
            self.app.log(f"{self.gtag} 弹窗流程未配置完整，跳过","warn")
            return

        self.app.log(f"{self.gtag} 进入弹窗流程，标题关键词:「{title_kw}」","info")

        # 主窗口集合 = 只有绑定的 target_hwnd
        # 不能把当前所有同标题窗口都算作主窗口，否则已弹出的弹窗会被误排除
        main_hwnds = {main_hwnd} if main_hwnd else set()
        # 如果 target_hwnd 不在同标题窗口里（标题不含关键词），则扫描一次找真正的主窗口
        current_all = self._find_windows_by_title(title_kw)
        if main_hwnd not in current_all:
            # 主窗口标题不含弹窗关键词，主窗口集合为空（所有同标题窗口都是弹窗）
            main_hwnds = set()
        self.app.log(f"[弹窗] 主窗口集合: {list(main_hwnds)}","info")

        deadline      = time.time() + total_timeout
        handled_hwnds = set()   # 本轮已处理（点击过）的弹窗，避免重复识别同一内容

        while not self._stop.is_set() and time.time() < deadline:

            # ── 枚举当前所有弹窗（主窗口以外的同标题窗口）──
            current_all = self._find_windows_by_title(title_kw)
            popup_hwnds = [h for h in current_all
                           if h not in main_hwnds
                           and win32gui.IsWindow(h)
                           and win32gui.IsWindowVisible(h)
                           and win32gui.GetWindowText(h).strip()]

            if not popup_hwnds:
                # 没有任何弹窗，等一段时间再检查（防止弹窗刚关闭下一个还没出来）
                self.app.log(f"[弹窗] 无弹窗，等待{wait_appear}s确认已全部处理...","info")
                all_clear = True
                for _ in range(wait_appear * 4):
                    if self._stop.is_set(): break
                    time.sleep(0.25)
                    if not self._only_main_remains(title_kw, main_hwnds):
                        all_clear = False
                        self.app.log(f"[弹窗] 检测到新弹窗出现，继续处理","info")
                        break
                if all_clear:
                    self.app.log(f"[弹窗] 确认无弹窗，流程结束","ok")
                    break
                continue  # 有新弹窗，继续外层循环

            self.app.log(f"[弹窗] 发现 {len(popup_hwnds)} 个弹窗: {popup_hwnds}","ok")

            any_handled = False
            for popup_hwnd in popup_hwnds:
                if self._stop.is_set(): break

                # 已经处理过且窗口还在：说明点击后内容可能变化了，重新识别
                popup_title = ""
                try: popup_title = win32gui.GetWindowText(popup_hwnd)
                except: pass
                self.app.log(f"[弹窗] 处理弹窗[{popup_hwnd}]「{popup_title}」","info")

                # 等待弹窗尺寸稳定
                self._wait_popup_stable(popup_hwnd)

                matched_any = False
                for tmpl in templates:
                    if self._stop.is_set(): break

                    tname = tmpl.get("name","模板")
                    matched, click_pos, img = self._recognize_popup(
                        tmpl, popup_hwnd, cap_mode)

                    if not matched:
                        continue

                    self.app.log(f"[弹窗] 模板「{tname}」匹配成功","ok")
                    self._play_if("popup_match")
                    self._do_popup_action(tmpl, popup_hwnd, click_pos, img)
                    matched_any = True
                    any_handled = True
                    handled_hwnds.add(popup_hwnd)

                    after_wait = max(0, int(tmpl.get("after_click_wait",1)))
                    self.app.log(f"[弹窗] 等待响应 {after_wait}s...","info")
                    for _ in range(after_wait * 4):
                        if self._stop.is_set(): break
                        time.sleep(0.25)

                    # 匹配后停止整个弹窗流程 / 停止全部监控（互斥）
                    stop_flow = tmpl.get("after_match_stop_flow", False)
                    stop_all  = tmpl.get("after_match_stop_all", False)
                    if stop_flow or stop_all:
                        sf = tmpl.get("after_match_sound_file","").strip()
                        if sf:
                            _play_sound(sf)
                        if stop_all:
                            self.app.log(f"[弹窗] 模板「{tname}」触发停止全部监控","warn")
                            self.app.after(0, self.app._stop)
                        else:
                            self.app.log(f"[弹窗] 模板「{tname}」触发停止流程","warn")
                        return

                    break  # 当前弹窗匹配到模板，跳出模板循环处理下一个弹窗

                if not matched_any:
                    # 未匹配：如果是第一次遇到这个弹窗则执行 no_match_action
                    if popup_hwnd in handled_hwnds:
                        self.app.log(f"[弹窗][{popup_hwnd}] 已处理过但内容无法识别，跳过","warn")
                        main_hwnds.add(popup_hwnd)  # 加入主窗口集合永久排除
                    else:
                        self.app.log(f"[弹窗][{popup_hwnd}] 所有模板均未匹配，执行: {no_match_act}","info")
                        self._handle_no_match_action(no_match_act)
                        if no_match_act in ("pause_group","stop_all"):
                            return  # 直接退出弹窗流程

            if not any_handled:
                # 有弹窗但全部无法匹配，等一下再试（可能内容还在加载）
                time.sleep(0.5)

        if time.time() >= deadline:
            self.app.log(f"[弹窗] 弹窗流程总超时，强制退出","warn")
        else:
            self.app.log(f"[弹窗] 弹窗流程结束，恢复主监控","ok")

    def _recognize(self, g, img):
        typ    = g.get("type","ocr")
        tess   = self.app.cfg.get("tesseract_path","")
        tag    = self.gtag
        engine = g.get("ocr_engine","paddle")

        if typ == "ocr":
            if engine == "tesseract":
                if not HAS_TESSERACT:
                    self.app.log(f"{tag} pytesseract 未安装","err"); return False, None
                if not (tess and os.path.exists(tess)):
                    self.app.log(f"{tag} Tesseract路径无效: {tess}","err"); return False, None
            elif engine == "paddle":
                if not HAS_PADDLE:
                    self.app.log(f"{tag} PaddleOCR 未安装","err"); return False, None

            psm      = int(g.get("ocr_psm", 6))
            scale    = int(g.get("ocr_scale", 1))
            binarize = bool(g.get("ocr_binarize", True))
            thr_bin  = int(g.get("ocr_threshold", 128))
            contrast = float(g.get("ocr_contrast", 1.5))
            invert   = bool(g.get("ocr_invert", False))
            # Paddle: 放大后识别更准，但不做二值化
            if engine == "paddle":
                if scale > 1:
                    try:
                        w2, h2 = img.size[0]*scale, img.size[1]*scale
                        proc = img.resize((w2, h2), Image.LANCZOS)
                    except: proc = img
                else:
                    proc = img
            else:
                proc = preprocess(img, scale=scale, contrast=contrast,
                                  binarize=binarize, threshold=thr_bin, invert=invert)
                if proc is None: proc = img

            eng_info = f"engine={engine}" + (f" psm={psm}" if engine=="tesseract" else "")
            try:
                text = do_ocr_text(proc, engine=engine,
                                   lang=g.get("language","chi_sim"),
                                   tess_path=tess, psm=psm)
            except Exception as e:
                self.app.log(f"{tag} OCR调用异常: {e}","err")
                return False, None
            if not text:
                self.app.log(f"{tag} OCR结果为空 ({eng_info})","info"); return False, None
            text_short = text.strip().replace("\n"," ")[:60]
            kw_str = g.get("keywords","")
            if not kw_str.strip():
                self.app.log(f"{tag} 未设置关键词","warn"); return False, None
            self.app.log(f"{tag} OCR({eng_info}): 「{text_short}」 | 关键词: 「{kw_str}」","info")
            matched, first_kw = match_keywords(text, kw_str)
            if not matched:
                return False, None
            kws_for_pos = [first_kw] if first_kw else []
            pos = do_ocr_find_pos(proc, kws_for_pos, engine=engine,
                                  lang=g.get("language","chi_sim"),
                                  tess_path=tess, psm=psm) if kws_for_pos else None
            # proc 是放大后的图，坐标需要除以 scale 还原到原图坐标系
            if pos and scale > 1:
                pos = (pos[0] // scale, pos[1] // scale)
            self.app.log(f"{tag} OCR匹配成功，关键词坐标(图内): {pos}","ok")
            return True, pos

        elif typ == "image":
            tp = g.get("template_path")
            if not tp:
                self.app.log(f"{tag} 未设置模板图像","warn"); return False, None
            if not os.path.exists(tp):
                self.app.log(f"{tag} 模板文件不存在: {tp}","err"); return False, None
            if not HAS_CV2:
                self.app.log(f"{tag} opencv 未安装","err"); return False, None
            try:
                tmpl = _imread_unicode(tp)
                if tmpl is None:
                    self.app.log(f"{tag} 模板图像读取失败（路径含中文或文件损坏）","err"); return False, None
            except Exception as e:
                self.app.log(f"{tag} 读取模板异常: {e}","err"); return False, None
            thr = g.get("threshold",80) / 100.0
            matched, pos, score = match_template(img, tmpl, thr)
            self.app.log(f"{tag} 图像匹配得分: {score:.1%} (阈值{thr:.0%})", "ok" if matched else "info")
            return matched, pos

        elif typ == "color":
            tc  = g.get("target_color",[255,0,0])
            tol = g.get("tolerance",10)
            if not HAS_NUMPY:
                self.app.log(f"{tag} numpy 未安装","err"); return False, None
            matched, pos = match_color(img, tc, tol)
            self.app.log(f"{tag} 颜色识别 RGB{tuple(tc)} 容差{tol}: {'匹配' if matched else '未匹配'}", "ok" if matched else "info")
            return matched, pos

        self.app.log(f"{tag} 未知识别类型: {typ}","err")
        return False, None

    def _run_chain(self, target_index):
        monitors = self.app.monitors
        if target_index < 0 or target_index >= len(monitors): return
        g = None
        try: g = self.app.cfg["groups"][target_index]
        except: return
        self.app.log(f"{self.gtag}→组{target_index+1} 串联执行","info")
        monitors[target_index].run_as_chain(g)

    def _play_if(self, event):
        """根据全局音效配置决定是否播放音效
        event: 'match' | 'popup_match' | 'no_match'
        """
        cfg = self.app.cfg
        if not cfg.get("sound_enabled", False): return
        sf = cfg.get("sound_file","").strip()
        if not sf: return
        key_map = {"match":"sound_on_match",
                   "popup_match":"sound_on_popup_match",
                   "no_match":"sound_on_no_match"}
        if cfg.get(key_map.get(event,""), False):
            _play_sound(sf)

    def _handle_no_match_action(self, action, tag="[弹窗]"):
        """处理弹窗全部不匹配时的行为"""
        if action == "pause_group":
            self.app.log(f"{tag} 全部不匹配 → 暂停当前监控组","warn")
            self._play_if("no_match")
            self._stop.set()  # 停止本组循环
        elif action == "stop_all":
            self.app.log(f"{tag} 全部不匹配 → 停止全部监控","warn")
            self._play_if("no_match")
            self.app.after(0, self.app._stop)  # 主线程停止所有组
        else:
            pass  # continue: 不做任何操作

# ══════════════════════════════════════════════════════════
#  GUI 帮助
# ══════════════════════════════════════════════════════════
def _btn(parent, text, color, cmd, **kw):
    return tk.Button(parent, text=text, bg=color, fg="white",
        relief="flat", font=("Microsoft YaHei",9),
        cursor="hand2", command=cmd,
        activebackground=T["accent"], activeforeground="white",
        padx=10, pady=3, **kw)

def _lbl(parent, text, fg=None, **kw):
    return tk.Label(parent, text=text, bg=T["card"],
        fg=fg or T["text2"], font=("Microsoft YaHei",9), **kw)

def _entry(parent, width, value):
    e = tk.Entry(parent, bg=T["card2"], fg=T["text"],
        insertbackground=T["text"], relief="flat",
        font=("Microsoft YaHei",10), width=width)
    e.insert(0, str(value))
    return e

def _sep(parent):
    tk.Frame(parent, bg=T["border"], height=1).pack(fill="x", pady=4)

# ══════════════════════════════════════════════════════════
#  监控组卡片 Widget
# ══════════════════════════════════════════════════════════
class GroupCard(tk.Frame):
    """每个监控组的可视化配置卡片"""

    def __init__(self, parent, app, index, on_delete, on_move_up, on_move_down):
        super().__init__(parent, bg=T["card"],
            highlightthickness=1, highlightbackground=T["border"])
        self.app      = app
        self.index    = index
        self.on_delete= on_delete

        self._build(on_delete, on_move_up, on_move_down)
        self.load()

    def _build(self, on_delete, on_move_up, on_move_down):
        # ── 标题栏 ──────────────────────────────────────
        hdr = tk.Frame(self, bg=T["card2"])
        hdr.pack(fill="x")

        self._enabled = tk.BooleanVar()
        tk.Checkbutton(hdr, variable=self._enabled,
            bg=T["card2"], fg=T["text"], selectcolor=T["card"],
            activebackground=T["card2"],
            font=("Microsoft YaHei",9)).pack(side="left", padx=4)

        # 序号（可编辑，与快捷配置保持一致）
        self._seq_var = tk.StringVar(value=str(self.index + 1))
        tk.Entry(hdr, textvariable=self._seq_var,
            bg=T["card2"], fg=T["accent"],
            insertbackground=T["text"], relief="flat",
            font=("Microsoft YaHei",9,"bold"), width=3,
            justify="center").pack(side="left", padx=(4,0), pady=4)
        tk.Label(hdr, text=".", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")

        self._name_var = tk.StringVar()
        tk.Entry(hdr, textvariable=self._name_var,
            bg=T["card2"], fg=T["text"],
            insertbackground=T["text"], relief="flat",
            font=("Microsoft YaHei",9,"bold"), width=14).pack(
                side="left", padx=4, pady=4)

        self._type_var = tk.StringVar()
        ttk.Combobox(hdr, textvariable=self._type_var,
            values=["ocr","image","color"],
            width=6, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=4)
        self._type_var.trace_add("write", lambda *_: self._on_type_change())

        _btn(hdr,"↑",T["bg2"],on_move_up).pack(side="right",padx=2,pady=4)
        _btn(hdr,"↓",T["bg2"],on_move_down).pack(side="right",padx=2,pady=4)
        _btn(hdr,"删除",T["bd"],on_delete).pack(side="right",padx=4,pady=4)

        body = tk.Frame(self, bg=T["card"])
        body.pack(fill="x", padx=8, pady=6)

        # ── 区域 ────────────────────────────────────────
        r_region = tk.Frame(body, bg=T["card"]); r_region.pack(fill="x", pady=2)
        _btn(r_region,"选择区域",T["bp"],self._select_region).pack(side="left")
        self._region_lbl = _lbl(r_region, "未设置", anchor="w")
        self._region_lbl.pack(side="left", padx=6)

        # ── 截图方式 ─────────────────────────────────────
        r_cap = tk.Frame(body, bg=T["card"]); r_cap.pack(fill="x", pady=2)
        _lbl(r_cap,"截图:").pack(side="left")
        self._cap_var = tk.StringVar(value="global")
        for v,t in [("global","全局"),("printwindow","PrintWindow"),
                    ("imagegrab","ImageGrab"),("auto","自动")]:
            tk.Radiobutton(r_cap, text=t, variable=self._cap_var, value=v,
                bg=T["card"], fg=T["text"], selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",8)).pack(side="left", padx=3)

        # ── OCR 设置 ──────────────────────────────────────
        # OCR frame 仅作为类型切换的占位（内容已移到点击位置下方）
        self._ocr_frame = tk.Frame(body, bg=T["card"])

        # ── 图像检测设置 ──────────────────────────────────
        self._img_frame = tk.Frame(body, bg=T["card"])
        r2 = tk.Frame(self._img_frame, bg=T["card"]); r2.pack(fill="x",pady=2)
        _btn(r2,"截图为模板",T["bp"],self._capture_template).pack(side="left")
        _btn(r2,"选择文件",T["bg2"],self._browse_template).pack(side="left",padx=4)
        self._tmpl_lbl = _lbl(r2,"未设置",anchor="w")
        self._tmpl_lbl.pack(side="left", padx=4)
        r2b = tk.Frame(self._img_frame, bg=T["card"]); r2b.pack(fill="x",pady=2)
        _lbl(r2b,"匹配阈值:").pack(side="left")
        self._thr_e = _entry(r2b, 4, "80")
        self._thr_e.pack(side="left", padx=4, ipady=3)
        _lbl(r2b,"%").pack(side="left")

        # ── 颜色识别设置 ──────────────────────────────────
        self._color_frame = tk.Frame(body, bg=T["card"])
        r3 = tk.Frame(self._color_frame, bg=T["card"]); r3.pack(fill="x",pady=2)
        _btn(r3,"拾色",T["bp"],self._pick_color).pack(side="left")
        self._color_preview = tk.Label(r3, width=4, bg="#ff0000",
            relief="solid", bd=1)
        self._color_preview.pack(side="left", padx=4)
        self._color_val = [255,0,0]
        self._color_lbl = _lbl(r3,"RGB(255,0,0)")
        self._color_lbl.pack(side="left", padx=4)
        r3b = tk.Frame(self._color_frame, bg=T["card"]); r3b.pack(fill="x",pady=2)
        _lbl(r3b,"颜色容差:").pack(side="left")
        self._tol_e = _entry(r3b, 4, "10")
        self._tol_e.pack(side="left", padx=4, ipady=3)

        _sep(body)

        # ── 动作配置 ──────────────────────────────────────
        r_act = tk.Frame(body, bg=T["card"]); r_act.pack(fill="x",pady=2)
        _lbl(r_act,"间隔:").pack(side="left")
        self._intv_e = _entry(r_act, 4, "5")
        self._intv_e.pack(side="left", padx=4, ipady=3)
        _lbl(r_act,"秒  暂停:").pack(side="left")
        self._pause_e = _entry(r_act, 4, "10")
        self._pause_e.pack(side="left", padx=4, ipady=3)
        _lbl(r_act,"秒").pack(side="left")
        self._debug_save = tk.BooleanVar(value=False)
        tk.Checkbutton(r_act, text="🔍 保存截图(调试)",
            variable=self._debug_save,
            bg=T["card"], fg=T["warning"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=(16,0))

        # ── 点击模式 + 置底 + 抖动/模拟 ──────────────────────
        r_click = tk.Frame(body, bg=T["card"]); r_click.pack(fill="x",pady=2)
        _lbl(r_click,"点击:").pack(side="left")
        self._cmode_var = tk.StringVar(value="postmessage")
        for v,t in [("postmessage","PostMessage后台"),("quickswitch","QuickSwitch前台")]:
            tk.Radiobutton(r_click, text=t, variable=self._cmode_var, value=v,
                bg=T["card"], fg=T["text"], selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",8),
                command=self._toggle_sink_ck).pack(side="left", padx=3)
        self._sink_after_click = tk.BooleanVar(value=False)
        self._sink_ck_widget = tk.Checkbutton(
            r_click, text="序列完成后切回",
            variable=self._sink_after_click,
            bg=T["card"], fg=T["warning"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8))
        self._mouse_jitter   = tk.BooleanVar(value=True)
        self._mouse_humanize = tk.BooleanVar(value=True)
        tk.Checkbutton(r_click, text="坐标抖动",
            variable=self._mouse_jitter,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=(12,2))
        tk.Checkbutton(r_click, text="模拟人工移动",
            variable=self._mouse_humanize,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=2)
        self._toggle_sink_ck()

        # ── 操作序列编辑器 ────────────────────────────────
        _sep(body)
        self._action_editor = ActionSequenceEditor(
            body, self.app,
            get_hwnd_fn  = lambda: self.app.cfg.get("target_hwnd", 0),
            get_cmode_fn = lambda: self._cmode_var.get(),
        )
        self._action_editor.pack(fill="x", pady=(2,4))
        _sep(body)

        # ── 关键词 / OCR引擎 / 参数（所有类型共用关键词，OCR类型额外有引擎设置）──
        _sep(body)
        r_kw = tk.Frame(body, bg=T["card"]); r_kw.pack(fill="x",pady=2)
        _lbl(r_kw,"关键词:").pack(side="left")
        self._kw_e = _entry(r_kw, 22, "")
        self._kw_e.pack(side="left", padx=4, ipady=3)
        _lbl(r_kw,"语言:").pack(side="left")
        self._lang_var = tk.StringVar(value="chi_sim")
        ttk.Combobox(r_kw, textvariable=self._lang_var,
            values=["chi_sim","chi_tra","eng"],
            width=8, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=4)
        tk.Label(r_kw, text="｜ 用 | 分隔OR，用 , 分隔AND  例: 开始|确认  例: 领取,奖励",
            bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=8)

        # OCR 引擎（仅 type==ocr 时可见，通过 _ocr_settings_frame 控制）
        # 立即 pack 占位，确保位置固定在关键词行下方
        self._ocr_settings_frame = tk.Frame(body, bg=T["card"])
        self._ocr_settings_frame.pack(fill="x")  # 先占位，_on_type_change 再控制内容显示

        # 引擎选择 + 放大 在同一行
        r1e = tk.Frame(self._ocr_settings_frame, bg=T["card"]); r1e.pack(fill="x",pady=2)
        _lbl(r1e,"OCR引擎:").pack(side="left")
        self._ocr_engine = tk.StringVar(value="paddle")
        for v,t in [("paddle","PaddleOCR（推荐）"),("tesseract","Tesseract")]:
            tk.Radiobutton(r1e, text=t, variable=self._ocr_engine, value=v,
                bg=T["card"], fg=T["text"], selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",9),
                command=self._toggle_ocr_engine).pack(side="left", padx=4)
        # Paddle 放大（同行显示，Tesseract时隐藏）
        self._paddle_scale_frame = tk.Frame(r1e, bg=T["card"])
        _lbl(self._paddle_scale_frame,"  放大:").pack(side="left")
        self._ocr_scale = tk.StringVar(value="2")
        ttk.Combobox(self._paddle_scale_frame, textvariable=self._ocr_scale,
            values=["1","2","3","4"],
            width=2, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=4)
        _lbl(self._paddle_scale_frame,"x（小图时提升识别率）").pack(side="left")
        self._paddle_scale_frame.pack(side="left")

        # 占位（保持旧引用不报错）
        self._paddle_params_frame = tk.Frame(self._ocr_settings_frame, bg=T["card"])

        # Tesseract 专属参数
        self._tess_params_frame = tk.Frame(self._ocr_settings_frame, bg=T["card"])
        r1b = tk.Frame(self._tess_params_frame, bg=T["card"]); r1b.pack(fill="x",pady=2)
        _lbl(r1b,"PSM:").pack(side="left")
        self._ocr_psm = tk.StringVar(value="6")
        ttk.Combobox(r1b, textvariable=self._ocr_psm,
            values=["6","7","11","3","4","13"],
            width=3, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=4)
        tk.Label(r1b, text="(6=块 7=单行 11=稀疏)",
            bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",7)).pack(side="left")
        _lbl(r1b," 放大:").pack(side="left", padx=(8,0))
        self._ocr_scale_tess = tk.StringVar(value="2")
        ttk.Combobox(r1b, textvariable=self._ocr_scale_tess,
            values=["1","2","3"],
            width=2, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=4)
        _lbl(r1b,"x  对比度:").pack(side="left")
        self._ocr_contrast_e = _entry(r1b, 4, "1.5")
        self._ocr_contrast_e.pack(side="left", padx=4, ipady=2)
        r1c = tk.Frame(self._tess_params_frame, bg=T["card"]); r1c.pack(fill="x",pady=2)
        self._ocr_binarize = tk.BooleanVar(value=True)
        tk.Checkbutton(r1c, text="二值化 阈值:",
            variable=self._ocr_binarize,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._ocr_threshold_e = _entry(r1c, 4, "128")
        self._ocr_threshold_e.pack(side="left", padx=4, ipady=2)
        tk.Label(r1c, text="(0-255)",
            bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",7)).pack(side="left")
        self._ocr_invert = tk.BooleanVar(value=False)
        tk.Checkbutton(r1c, text="反色（深色背景）",
            variable=self._ocr_invert,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9)).pack(side="left", padx=(12,0))

        # ── 串联配置 ──────────────────────────────────────
        r_chain = tk.Frame(body, bg=T["card"]); r_chain.pack(fill="x",pady=2)
        self._chain_ck = tk.BooleanVar()
        tk.Checkbutton(r_chain, text="串联执行",
            variable=self._chain_ck,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9),
            command=self._toggle_chain).pack(side="left")
        self._chain_frame = tk.Frame(r_chain, bg=T["card"])
        self._chain_frame.pack(side="left", padx=4)
        _lbl(self._chain_frame,"→组:").pack(side="left")
        self._chain_target = tk.StringVar(value="")
        self._chain_cb = ttk.Combobox(self._chain_frame,
            textvariable=self._chain_target, width=12,
            state="readonly", font=("Microsoft YaHei",9))
        self._chain_cb.pack(side="left", padx=4)
        _lbl(self._chain_frame,"等待:").pack(side="left")
        self._chain_wait = _entry(self._chain_frame, 3, "1")
        self._chain_wait.pack(side="left", padx=2, ipady=3)
        _lbl(self._chain_frame,"秒").pack(side="left")
        self._toggle_chain()

        # ── 模板存储 ──────────────────────────────────────
        self._template_path = None

        self._on_type_change()

        # ── 弹窗流程配置（监控组最底部）────────────────────
        _sep(body)
        r_popup_hdr = tk.Frame(body, bg=T["card"]); r_popup_hdr.pack(fill="x",pady=2)
        self._popup_ck = tk.BooleanVar()
        tk.Checkbutton(r_popup_hdr, text="启用弹窗流程",
            variable=self._popup_ck,
            bg=T["card"], fg=T["warning"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9,"bold"),
            command=self._toggle_popup).pack(side="left")
        self._popup_only_ck = tk.BooleanVar()
        tk.Checkbutton(r_popup_hdr, text="仅弹窗监控（跳过识别直接循环弹窗流程）",
            variable=self._popup_only_ck,
            bg=T["card"], fg=T["accent"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9)).pack(side="left", padx=12)

        self._popup_frame = tk.Frame(body, bg=T["card2"],
            highlightthickness=1, highlightbackground=T["border"])

        pf = tk.Frame(self._popup_frame, bg=T["card2"])
        pf.pack(fill="x", padx=6, pady=4)

        r_p1 = tk.Frame(pf, bg=T["card2"]); r_p1.pack(fill="x", pady=2)
        tk.Label(r_p1, text="弹窗标题关键词:", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        tf1=tk.Frame(r_p1,bg=T["border"],padx=1,pady=1); tf1.pack(side="left",padx=4)
        self._popup_title_e = tk.Entry(tf1,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",font=("Microsoft YaHei",9),width=16)
        self._popup_title_e.pack(ipady=3)

        r_p2 = tk.Frame(pf, bg=T["card2"]); r_p2.pack(fill="x", pady=2)
        tk.Label(r_p2, text="等待弹窗出现:", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        tf2=tk.Frame(r_p2,bg=T["border"],padx=1,pady=1); tf2.pack(side="left",padx=4)
        self._popup_wait_appear_e = tk.Entry(tf2,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",font=("Microsoft YaHei",9),width=4)
        self._popup_wait_appear_e.insert(0,"5"); self._popup_wait_appear_e.pack(ipady=3)
        tk.Label(r_p2, text="秒  等待弹窗关闭:", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        tf3=tk.Frame(r_p2,bg=T["border"],padx=1,pady=1); tf3.pack(side="left",padx=4)
        self._popup_wait_close_e = tk.Entry(tf3,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",font=("Microsoft YaHei",9),width=4)
        self._popup_wait_close_e.insert(0,"10"); self._popup_wait_close_e.pack(ipady=3)
        tk.Label(r_p2, text="秒  总超时:", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        tf4=tk.Frame(r_p2,bg=T["border"],padx=1,pady=1); tf4.pack(side="left",padx=4)
        self._popup_total_e = tk.Entry(tf4,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",font=("Microsoft YaHei",9),width=5)
        self._popup_total_e.insert(0,"120"); self._popup_total_e.pack(ipady=3)
        tk.Label(r_p2, text="秒", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")

        # 全部不匹配时的行为
        r_p3 = tk.Frame(pf, bg=T["card2"]); r_p3.pack(fill="x", pady=2)
        tk.Label(r_p3, text="全部不匹配时:", bg=T["card2"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._popup_no_match_var = tk.StringVar(value="continue")
        for v,t,c in [("continue","继续循环",T["text2"]),
                      ("pause_group","暂停当前组",T["warning"]),
                      ("stop_all","停止全部监控",T["danger"])]:
            tk.Radiobutton(r_p3, text=t, variable=self._popup_no_match_var, value=v,
                bg=T["card2"], fg=c, selectcolor=T["card"],
                activebackground=T["card2"],
                font=("Microsoft YaHei",9)).pack(side="left", padx=6)

        tk.Label(pf, text="弹窗处理模板：",
            bg=T["card2"], fg=T["text"],
            font=("Microsoft YaHei",9,"bold")).pack(anchor="w", pady=(6,2))

        # 模板卡片容器（新增按钮在容器下方）
        self._popup_templates_frame = tk.Frame(self._popup_frame, bg=T["card2"])
        self._popup_templates_frame.pack(fill="x", padx=6, pady=(0,2))

        # 新增模板按钮放最后
        r_add = tk.Frame(self._popup_frame, bg=T["card2"])
        r_add.pack(fill="x", padx=6, pady=(2,6))
        _btn(r_add, "+ 新增模板", T["bp"], self._add_popup_template).pack(side="left")

        self._popup_template_cards = []
        self._toggle_popup()

    # ── 类型切换显示/隐藏 ────────────────────────────────

    def _on_type_change(self):
        typ = self._type_var.get()
        self._ocr_frame.pack_forget()
        self._img_frame.pack_forget()
        self._color_frame.pack_forget()
        # 控制 _ocr_settings_frame 内部内容（引擎行）的显示，frame 本身位置固定
        for w in self._ocr_settings_frame.winfo_children():
            w.pack_forget()
        if typ == "ocr":
            # 重新 pack 引擎行（已在 _ocr_settings_frame 内）
            for w in self._ocr_settings_frame.winfo_children():
                w.pack(fill="x")
            self._toggle_ocr_engine()
        elif typ == "image":
            self._img_frame.pack(fill="x", pady=2)
        elif typ == "color":
            self._color_frame.pack(fill="x", pady=2)

    def _toggle_custom(self):
        pass  # 旧方法，坐标输入已移至操作序列编辑器

    def _toggle_sink_ck(self):
        """QuickSwitch模式时显示"点后置底"勾选框，其他模式隐藏"""
        if self._cmode_var.get() == "quickswitch":
            self._sink_ck_widget.pack(side="left", padx=(12,0))
        else:
            self._sink_ck_widget.pack_forget()

    def _toggle_ocr_engine(self):
        eng = self._ocr_engine.get()
        self._paddle_params_frame.pack_forget()
        self._tess_params_frame.pack_forget()
        if eng == "tesseract":
            self._paddle_scale_frame.pack_forget()
            self._tess_params_frame.pack(fill="x", pady=2)
        else:
            self._paddle_scale_frame.pack(side="left")

    def _toggle_chain(self):
        state = "normal" if self._chain_ck.get() else "disabled"
        for w in self._chain_frame.winfo_children():
            try: w.config(state=state)
            except: pass

    def _toggle_popup(self):
        if self._popup_ck.get():
            self._popup_frame.pack(fill="x", pady=(2,4))
        else:
            self._popup_frame.pack_forget()

    def _add_popup_template(self, tmpl_data=None):
        idx = len(self._popup_template_cards)
        card = PopupTemplateCard(
            self._popup_templates_frame, self.app, self, idx,
            tmpl_data or copy.deepcopy(POPUP_TEMPLATE_DEFAULT),
            on_delete=lambda i=idx: self._delete_popup_template(i),
            on_move_up=lambda i=idx: self._move_popup_template(i, -1),
            on_move_down=lambda i=idx: self._move_popup_template(i, 1))
        card.pack(fill="x", pady=2)
        self._popup_template_cards.append(card)

    def _move_popup_template(self, idx, direction):
        tmpls = [c.get_data() for c in self._popup_template_cards
                 if c.winfo_exists()]
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(tmpls):
            return
        tmpls[idx], tmpls[new_idx] = tmpls[new_idx], tmpls[idx]
        for w in self._popup_templates_frame.winfo_children():
            w.destroy()
        self._popup_template_cards.clear()
        for td in tmpls:
            self._add_popup_template(td)

    def _delete_popup_template(self, idx):
        tmpls = [c.get_data() for c in self._popup_template_cards
                 if c.winfo_exists()]
        if 0 <= idx < len(tmpls):
            del tmpls[idx]
        for w in self._popup_templates_frame.winfo_children():
            w.destroy()
        self._popup_template_cards.clear()
        for td in tmpls:
            self._add_popup_template(td)

    def _do_capture_template_from_image(self, img, target_card):
        """从已截好的全窗图上让用户拖选，保存模板到 target_card"""
        win = tk.Toplevel()
        win.title("截取模板区域"); win.attributes("-topmost",True)
        win.resizable(False,False)
        max_w,max_h=1200,800
        scale=min(max_w/img.width,max_h/img.height,1.0)
        dw,dh=int(img.width*scale),int(img.height*scale)
        disp=img.resize((dw,dh),Image.LANCZOS) if scale<1 else img
        tk_img=ImageTk.PhotoImage(disp)
        canvas=tk.Canvas(win,width=dw,height=dh,cursor="crosshair",
            bg="black",bd=0,highlightthickness=0)
        canvas.pack()
        canvas.create_image(0,0,anchor="nw",image=tk_img)
        canvas._ref=tk_img
        tk.Label(win,text="拖动选择模板区域",
            bg="#222",fg="#aaa",font=("Microsoft YaHei",9)).pack(fill="x",pady=2)
        state={"s":None,"r":None}
        def press(e): state["s"]=(e.x,e.y)
        def drag(e):
            if state["s"]:
                if state["r"]: canvas.delete(state["r"])
                state["r"]=canvas.create_rectangle(state["s"][0],state["s"][1],e.x,e.y,
                    outline="#f39c12",width=2,dash=(4,2))
        def release(e):
            if state["s"]:
                x1=int(min(state["s"][0],e.x)/scale); y1=int(min(state["s"][1],e.y)/scale)
                x2=int(max(state["s"][0],e.x)/scale); y2=int(max(state["s"][1],e.y)/scale)
                if x2-x1>4 and y2-y1>4:
                    hwnd=self.app.cfg.get("target_hwnd",0)
                    full=_printwindow_full(hwnd) if hwnd else img
                    crop=(full or img).crop((x1,y1,x2,y2))
                    save_dir=os.path.dirname(CONFIG_FILE)
                    path=os.path.join(save_dir,
                        f"tmpl_g{self.index}_p{target_card.index}.png")
                    crop.save(path)
                    target_card._template_path=path
                    target_card._tmpl_lbl.config(
                        text=os.path.basename(path),fg=T["success"])
                win.destroy()
        canvas.bind("<ButtonPress-1>",press)
        canvas.bind("<B1-Motion>",drag)
        canvas.bind("<ButtonRelease-1>",release)
        win.bind("<Escape>",lambda e:win.destroy())

    def _do_pick_color_from_image(self, img, target_card):
        """从已截好的图上让用户点击拾色，结果写入 target_card"""
        win=tk.Toplevel()
        win.title("点击拾取颜色"); win.attributes("-topmost",True)
        win.resizable(False,False)
        max_w,max_h=1200,800
        scale=min(max_w/img.width,max_h/img.height,1.0)
        dw,dh=int(img.width*scale),int(img.height*scale)
        disp=img.resize((dw,dh),Image.LANCZOS) if scale<1 else img
        tk_img=ImageTk.PhotoImage(disp)
        canvas=tk.Canvas(win,width=dw,height=dh,cursor="crosshair",
            bg="black",bd=0,highlightthickness=0)
        canvas.pack(); canvas.create_image(0,0,anchor="nw",image=tk_img)
        canvas._ref=tk_img
        prev=tk.Label(win,text="移动预览",bg="#000",fg="#fff",
            font=("Consolas",10),width=40); prev.pack(fill="x",pady=2)
        def motion(e):
            rx,ry=int(e.x/scale),int(e.y/scale)
            try:
                px=img.getpixel((rx,ry)); r,g,b=px[0],px[1],px[2]
                hc=f"#{r:02x}{g:02x}{b:02x}"
                prev.config(text=f"RGB({r},{g},{b})  {hc}",bg=hc,
                    fg="black" if r+g+b>384 else "white")
            except: pass
        def click(e):
            rx,ry=int(e.x/scale),int(e.y/scale)
            try:
                px=img.getpixel((rx,ry)); r,g,b=px[0],px[1],px[2]
                target_card._color_val=[r,g,b]
                hc=f"#{r:02x}{g:02x}{b:02x}"
                target_card._color_preview.config(bg=hc)
                target_card._color_lbl.config(text=f"RGB({r},{g},{b})")
            except: pass
            win.destroy()
        canvas.bind("<Motion>",motion)
        canvas.bind("<Button-1>",click)
        win.bind("<Escape>",lambda e:win.destroy())

    # ── 区域选择 ────────────────────────────────────────

    def _select_region(self):
        hwnd = self.app.cfg.get("target_hwnd",0)
        if not hwnd:
            messagebox.showwarning("提示","请先绑定目标窗口"); return
        img = capture_full_preview(hwnd, self.app.cfg.get("capture_mode","printwindow"))
        if img is None:
            messagebox.showerror("失败","无法截取窗口"); return

        win = tk.Toplevel()
        win.title(f"组{self.index+1} 选择监控区域")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        max_w, max_h = 1200, 800
        scale = min(max_w/img.width, max_h/img.height, 1.0)
        dw,dh = int(img.width*scale), int(img.height*scale)
        disp  = img.resize((dw,dh),Image.LANCZOS) if scale<1 else img

        tk_img = ImageTk.PhotoImage(disp)
        canvas = tk.Canvas(win, width=dw, height=dh,
            cursor="crosshair", bg="black", bd=0, highlightthickness=0)
        canvas.pack()
        canvas.create_image(0,0,anchor="nw",image=tk_img)
        canvas._ref = tk_img
        tk.Label(win,text="拖动选择监控区域，松开确认（Esc取消）",
            bg="#222",fg="#aaa",font=("Microsoft YaHei",9)).pack(fill="x",pady=2)

        state={"s":None,"r":None}
        def press(e):
            state["s"]=(e.x,e.y)
            if state["r"]: canvas.delete(state["r"])
        def drag(e):
            if state["s"]:
                if state["r"]: canvas.delete(state["r"])
                state["r"]=canvas.create_rectangle(
                    state["s"][0],state["s"][1],e.x,e.y,
                    outline="#3d6bff",width=2,dash=(4,2))
        def release(e):
            if state["s"]:
                x1=int(min(state["s"][0],e.x)/scale)
                y1=int(min(state["s"][1],e.y)/scale)
                x2=int(max(state["s"][0],e.x)/scale)
                y2=int(max(state["s"][1],e.y)/scale)
                if x2-x1>4 and y2-y1>4:
                    g=self.app.cfg["groups"][self.index]
                    g["region"]=[x1,y1,x2,y2]
                    self._region_lbl.config(text=f"({x1},{y1})-({x2},{y2})")
                win.destroy()
        canvas.bind("<ButtonPress-1>",press)
        canvas.bind("<B1-Motion>",drag)
        canvas.bind("<ButtonRelease-1>",release)
        win.bind("<Escape>",lambda e:win.destroy())

    # ── 图像模板 ──────────────────────────────────────────

    def _capture_template(self):
        hwnd = self.app.cfg.get("target_hwnd",0)
        if not hwnd:
            messagebox.showwarning("提示","请先绑定目标窗口"); return
        img = capture_full_preview(hwnd, self.app.cfg.get("capture_mode","printwindow"))
        if img is None:
            messagebox.showerror("失败","无法截取窗口"); return

        win = tk.Toplevel()
        win.title("截取模板图像区域")
        win.attributes("-topmost",True); win.resizable(False,False)
        max_w,max_h=1200,800
        scale=min(max_w/img.width,max_h/img.height,1.0)
        dw,dh=int(img.width*scale),int(img.height*scale)
        disp=img.resize((dw,dh),Image.LANCZOS) if scale<1 else img
        tk_img=ImageTk.PhotoImage(disp)
        canvas=tk.Canvas(win,width=dw,height=dh,cursor="crosshair",
            bg="black",bd=0,highlightthickness=0)
        canvas.pack()
        canvas.create_image(0,0,anchor="nw",image=tk_img)
        canvas._ref=tk_img
        tk.Label(win,text="拖动选择模板区域",
            bg="#222",fg="#aaa",font=("Microsoft YaHei",9)).pack(fill="x",pady=2)

        state={"s":None,"r":None}
        def press(e): state["s"]=(e.x,e.y); (canvas.delete(state["r"]) if state["r"] else None)
        def drag(e):
            if state["s"]:
                if state["r"]: canvas.delete(state["r"])
                state["r"]=canvas.create_rectangle(state["s"][0],state["s"][1],e.x,e.y,
                    outline="#f39c12",width=2,dash=(4,2))
        def release(e):
            if state["s"]:
                x1=int(min(state["s"][0],e.x)/scale); y1=int(min(state["s"][1],e.y)/scale)
                x2=int(max(state["s"][0],e.x)/scale); y2=int(max(state["s"][1],e.y)/scale)
                if x2-x1>4 and y2-y1>4:
                    # 用PrintWindow截模板确保准确
                    hwnd2=self.app.cfg.get("target_hwnd",0)
                    full=_printwindow_full(hwnd2) or img
                    crop=full.crop((x1,y1,x2,y2))
                    # 保存到配置目录
                    save_dir=os.path.dirname(CONFIG_FILE)
                    path=os.path.join(save_dir,f"template_g{self.index}.png")
                    crop.save(path)
                    g=self.app.cfg["groups"][self.index]
                    g["template_path"]=path
                    self._template_path=path
                    name=os.path.basename(path)
                    self._tmpl_lbl.config(text=name,fg=T["success"])
                win.destroy()
        canvas.bind("<ButtonPress-1>",press)
        canvas.bind("<B1-Motion>",drag)
        canvas.bind("<ButtonRelease-1>",release)
        win.bind("<Escape>",lambda e:win.destroy())

    def _browse_template(self):
        p=filedialog.askopenfilename(
            title="选择模板图像",
            filetypes=[("图像","*.png *.jpg *.bmp *.jpeg"),("All","*.*")])
        if p:
            g=self.app.cfg["groups"][self.index]
            g["template_path"]=p
            self._template_path=p
            self._tmpl_lbl.config(text=os.path.basename(p),fg=T["success"])
            save_config(self.app.cfg)  # 立即持久化，防止不点保存按钮导致路径丢失

    # ── 颜色拾色 ─────────────────────────────────────────

    def _pick_color(self):
        hwnd=self.app.cfg.get("target_hwnd",0)
        if not hwnd:
            messagebox.showwarning("提示","请先绑定目标窗口"); return
        # 将KK置前台
        try:
            win32gui.SetWindowPos(hwnd,win32con.HWND_TOPMOST,0,0,0,0,
                win32con.SWP_NOMOVE|win32con.SWP_NOSIZE)
            time.sleep(0.1)
            win32gui.SetForegroundWindow(hwnd); time.sleep(0.15)
            win32gui.SetWindowPos(hwnd,win32con.HWND_NOTOPMOST,0,0,0,0,
                win32con.SWP_NOMOVE|win32con.SWP_NOSIZE)
        except: pass

        img=capture_full_preview(hwnd, self.app.cfg.get("capture_mode","printwindow"))
        if img is None:
            messagebox.showerror("失败","截图失败"); return

        win=tk.Toplevel()
        win.title("点击拾取颜色"); win.attributes("-topmost",True)
        win.resizable(False,False)

        max_w,max_h=1200,800
        scale=min(max_w/img.width,max_h/img.height,1.0)
        dw,dh=int(img.width*scale),int(img.height*scale)
        disp=img.resize((dw,dh),Image.LANCZOS) if scale<1 else img
        tk_img=ImageTk.PhotoImage(disp)
        canvas=tk.Canvas(win,width=dw,height=dh,
            cursor="crosshair",bg="black",bd=0,highlightthickness=0)
        canvas.pack()
        canvas.create_image(0,0,anchor="nw",image=tk_img)
        canvas._ref=tk_img

        preview_lbl=tk.Label(win,text="移动鼠标预览颜色",
            bg="#000",fg="#fff",font=("Consolas",10),width=40)
        preview_lbl.pack(fill="x",pady=2)

        def motion(e):
            rx,ry=int(e.x/scale),int(e.y/scale)
            try:
                px=img.getpixel((rx,ry))
                r,g,b=px[0],px[1],px[2]
                hex_c=f"#{r:02x}{g:02x}{b:02x}"
                preview_lbl.config(
                    text=f"RGB({r},{g},{b})  {hex_c}",bg=hex_c,
                    fg="black" if (r+g+b)>384 else "white")
            except: pass

        def click(e):
            rx,ry=int(e.x/scale),int(e.y/scale)
            try:
                px=img.getpixel((rx,ry))
                r,g,b=px[0],px[1],px[2]
                self._color_val=[r,g,b]
                hex_c=f"#{r:02x}{g:02x}{b:02x}"
                self._color_preview.config(bg=hex_c)
                self._color_lbl.config(text=f"RGB({r},{g},{b})")
                g2=self.app.cfg["groups"][self.index]
                g2["target_color"]=[r,g,b]
            except: pass
            win.destroy()

        canvas.bind("<Motion>",motion)
        canvas.bind("<Button-1>",click)
        win.bind("<Escape>",lambda e:win.destroy())

    # ── 坐标点选 ─────────────────────────────────────────

    def _pick_coord(self):
        pass  # 旧方法，坐标点选已移至操作序列编辑器行内

    # ── 串联下拉更新 ─────────────────────────────────────

    def update_chain_options(self, group_names):
        """外部调用，更新串联目标下拉列表，同时刷新当前选中项显示"""
        self._chain_index_map = {}  # display string → index
        opts = []
        for i, n in enumerate(group_names):
            if i == self.index: continue
            label = f"{i+1}:{n}"
            opts.append(label)
            self._chain_index_map[label] = i
        self._chain_cb["values"] = opts
        # 刷新当前选中项（根据已保存的 chain_target 索引）
        try:
            ct = self.app.cfg["groups"][self.index].get("chain_target", -1)
            if ct >= 0:
                for label, idx in self._chain_index_map.items():
                    if idx == ct:
                        self._chain_target.set(label)
                        return
            self._chain_target.set("")
        except: pass

    # ── 数据读写 ──────────────────────────────────────────

    def load(self):
        """从 app.cfg["groups"][index] 载入"""
        try:
            g=self.app.cfg["groups"][self.index]
        except:
            g=copy.deepcopy(GROUP_DEFAULT)
        self._enabled.set(g.get("enabled",True))
        self._seq_var.set(str(g.get("seq", self.index + 1)))
        self._name_var.set(g.get("name",f"监控组{self.index+1}"))
        self._type_var.set(g.get("type","ocr"))
        self._cap_var.set(g.get("capture_mode","global"))
        # region
        r=g.get("region")
        self._region_lbl.config(
            text=f"({r[0]},{r[1]})-({r[2]},{r[3]})" if r else "未设置")
        # ocr
        self._kw_e.delete(0,"end"); self._kw_e.insert(0,g.get("keywords",""))
        self._lang_var.set(g.get("language","chi_sim"))
        self._ocr_engine.set(g.get("ocr_engine","paddle"))
        self._toggle_ocr_engine()
        self._ocr_psm.set(str(g.get("ocr_psm",6)))
        scale_val = str(g.get("ocr_scale",2))
        self._ocr_scale.set(scale_val)       # paddle scale
        self._ocr_scale_tess.set(scale_val)  # tess scale
        self._ocr_contrast_e.delete(0,"end")
        self._ocr_contrast_e.insert(0,str(g.get("ocr_contrast",1.5)))
        self._ocr_binarize.set(g.get("ocr_binarize",True))
        self._ocr_threshold_e.delete(0,"end")
        self._ocr_threshold_e.insert(0,str(g.get("ocr_threshold",128)))
        self._ocr_invert.set(g.get("ocr_invert",False))
        # image
        tp=g.get("template_path")
        self._template_path=tp
        self._tmpl_lbl.config(
            text=os.path.basename(tp) if tp else "未设置",
            fg=T["success"] if tp else T["text2"])
        self._thr_e.delete(0,"end"); self._thr_e.insert(0,str(g.get("threshold",80)))
        # color
        tc=g.get("target_color",[255,0,0])
        self._color_val=tc
        hex_c=f"#{tc[0]:02x}{tc[1]:02x}{tc[2]:02x}"
        self._color_preview.config(bg=hex_c)
        self._color_lbl.config(text=f"RGB({tc[0]},{tc[1]},{tc[2]})")
        self._tol_e.delete(0,"end"); self._tol_e.insert(0,str(g.get("tolerance",10)))
        # action
        self._intv_e.delete(0,"end"); self._intv_e.insert(0,str(g.get("interval",5)))
        self._pause_e.delete(0,"end"); self._pause_e.insert(0,str(g.get("pause",10)))
        self._debug_save.set(g.get("debug_save",False))
        self._cmode_var.set(g.get("click_mode","postmessage"))
        self._sink_after_click.set(g.get("sink_after_click", False))
        self._mouse_jitter.set(g.get("mouse_jitter", True))
        self._mouse_humanize.set(g.get("mouse_humanize", True))
        self._toggle_sink_ck()
        # 加载操作序列（直接引用列表，ActionSequenceEditor 原地修改）
        if "actions" not in g:
            g["actions"] = []
        self._action_editor.load(g["actions"])
        # chain
        self._chain_ck.set(g.get("chain_enabled",False))
        self._chain_wait.config(state="normal")  # 确保可写，disabled状态下delete/insert静默失败
        self._chain_wait.delete(0,"end"); self._chain_wait.insert(0,str(g.get("chain_wait",2)))
        self._toggle_chain()
        # popup
        self._popup_ck.set(g.get("popup_enabled",False))
        self._popup_only_ck.set(g.get("popup_only_mode",False))
        self._popup_title_e.delete(0,"end")
        self._popup_title_e.insert(0,g.get("popup_title_kw",""))
        self._popup_wait_appear_e.delete(0,"end")
        self._popup_wait_appear_e.insert(0,str(g.get("popup_wait_appear",5)))
        self._popup_wait_close_e.delete(0,"end")
        self._popup_wait_close_e.insert(0,str(g.get("popup_wait_close",10)))
        self._popup_total_e.delete(0,"end")
        self._popup_total_e.insert(0,str(g.get("popup_total_timeout",120)))
        self._popup_no_match_var.set(g.get("popup_no_match_action","continue"))
        # 重建弹窗模板卡片
        for w in self._popup_templates_frame.winfo_children():
            w.destroy()
        self._popup_template_cards.clear()
        for td in g.get("popup_templates",[]):
            self._add_popup_template(td)
        self._toggle_popup()
        self._on_type_change()

    def save(self):
        """将当前UI状态写回 app.cfg["groups"][index]"""
        while len(self.app.cfg["groups"]) <= self.index:
            self.app.cfg["groups"].append(copy.deepcopy(GROUP_DEFAULT))
        g=self.app.cfg["groups"][self.index]
        g["enabled"]=self._enabled.get()
        try: g["seq"] = int(self._seq_var.get())
        except: g["seq"] = self.index + 1
        g["name"]=self._name_var.get()
        g["type"]=self._type_var.get()
        g["capture_mode"]=self._cap_var.get()
        g["keywords"]=self._kw_e.get()
        g["language"]=self._lang_var.get()
        eng = self._ocr_engine.get()
        g["ocr_engine"]=eng
        try: g["ocr_psm"]=int(self._ocr_psm.get())
        except: pass
        try:
            # 保存当前引擎对应的放大值
            scale_w = self._ocr_scale if eng=="paddle" else self._ocr_scale_tess
            g["ocr_scale"]=int(scale_w.get())
        except: pass
        try: g["ocr_contrast"]=float(self._ocr_contrast_e.get())
        except: pass
        g["ocr_binarize"]=self._ocr_binarize.get()
        try: g["ocr_threshold"]=int(self._ocr_threshold_e.get())
        except: pass
        g["ocr_invert"]=self._ocr_invert.get()
        if self._template_path:
            g["template_path"]=self._template_path
        try: g["threshold"]=int(self._thr_e.get())
        except: pass
        g["target_color"]=self._color_val
        try: g["tolerance"]=int(self._tol_e.get())
        except: pass
        try: g["interval"]=int(self._intv_e.get())
        except: pass
        try: g["pause"]=int(self._pause_e.get())
        except: pass
        g["debug_save"]=self._debug_save.get()
        g["click_mode"]=self._cmode_var.get()
        g["sink_after_click"]=self._sink_after_click.get()
        g["mouse_jitter"]=self._mouse_jitter.get()
        g["mouse_humanize"]=self._mouse_humanize.get()
        self._action_editor.save()
        # g["actions"] 已由 editor.save() 原地更新，无需回写
        g["chain_enabled"]=self._chain_ck.get()
        try: g["chain_wait"]=int(self._chain_wait.get())
        except: pass
        ct=self._chain_target.get()
        if ct and hasattr(self, "_chain_index_map"):
            g["chain_target"] = self._chain_index_map.get(ct, -1)
        elif ct:
            # 兼容旧格式 "index:name"
            try: g["chain_target"]=int(ct.split(":")[0])-1
            except: g["chain_target"]=-1
        else:
            g["chain_target"]=-1
        # popup
        g["popup_enabled"]=self._popup_ck.get()
        g["popup_only_mode"]=self._popup_only_ck.get()
        g["popup_title_kw"]=self._popup_title_e.get().strip()
        try: g["popup_wait_appear"]=int(self._popup_wait_appear_e.get())
        except: pass
        try: g["popup_wait_close"]=int(self._popup_wait_close_e.get())
        except: pass
        try: g["popup_total_timeout"]=int(self._popup_total_e.get())
        except: pass
        g["popup_no_match_action"]=self._popup_no_match_var.get()
        g["popup_templates"]=[c.get_data() for c in self._popup_template_cards
                               if c.winfo_exists()]


# ══════════════════════════════════════════════════════════
#  混合操作序列编辑器
# ══════════════════════════════════════════════════════════

# 各类型默认值
ACTION_DEFAULTS = {
    "mouse":  {"kind":"mouse",  "pre_delay":0.0, "pos_mode":"match_center",
               "offset_x":0, "offset_y":0, "abs_x":0, "abs_y":0,
               "click_type":"single", "count":1, "interval":0.1},
    "key":    {"kind":"key",    "key":"", "action":"press",
               "count":1, "interval":0.05},
    "text":   {"kind":"text",   "text":"", "interval":0.05},
    "delay":  {"kind":"delay",  "seconds":0.5},
    "scroll": {"kind":"scroll", "abs_x":0, "abs_y":0,
               "direction":"down", "clicks":1,
               "interval":0.1, "multiplier":1.0},
}

_POS_MODES = [
    ("match_center", "识别位置(中心点)"),
    ("offset",       "识别位置+偏移"),
    ("window",       "窗口相对坐标"),
    ("screen",       "屏幕固定坐标"),
]
_POS_MODE_LABELS = [v for _, v in _POS_MODES]
_POS_MODE_VALS   = {v: k for k, v in _POS_MODES}
_POS_LABEL       = {k: v for k, v in _POS_MODES}

_CLICK_TYPES = ["single","double","right","down","up","move"]
_CLICK_LABELS = {"single":"单击","double":"双击","right":"右键",
                 "down":"按下","up":"弹起","move":"移动"}

_KEY_ACTIONS = [("press","按键"),("down","按下"),("up","弹起")]
_KEY_ACTION_LABEL = {k:v for k,v in _KEY_ACTIONS}
_KEY_ACTION_VALS  = {v:k for k,v in _KEY_ACTIONS}

_KEY_HINTS = [
    "ctrl+c","ctrl+v","ctrl+a","ctrl+z","ctrl+s",
    "enter","space","esc","tab","backspace","delete",
    "shift","ctrl","alt","win",
    "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
    "up","down","left","right",
    "numpad0","numpad1","numpad2","numpad3","numpad4",
    "numpad5","numpad6","numpad7","numpad8","numpad9",
    "ctrl+shift+f5","win+r","alt+f4",
]


class ActionSequenceEditor(tk.Frame):
    """
    混合操作序列编辑器，嵌入 GroupCard / PopupTemplateCard。
    _actions 直接引用宿主 dict 内的列表，save() 原地写回，调用方无需额外处理。
    """

    def __init__(self, parent, app, get_hwnd_fn, get_cmode_fn):
        """
        parent:       父容器
        app:          App 实例（用于 cfg 和坐标点选）
        get_hwnd_fn:  callable() → hwnd，用于点选窗口相对坐标
        get_cmode_fn: callable() → "postmessage"|"quickswitch"，当前点击模式
        """
        super().__init__(parent, bg=T["card"])
        self.app          = app
        self._get_hwnd    = get_hwnd_fn
        self._get_cmode   = get_cmode_fn
        self._actions     = []   # 直接引用宿主列表，由 load() 赋值
        self._row_widgets = []   # 每条动作的行 Frame 列表
        self._build_header()
        self._rows_frame = tk.Frame(self, bg=T["card"])
        self._rows_frame.pack(fill="x")

    # ── 标题行 ────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=T["card2"]); hdr.pack(fill="x", pady=(4,2))
        tk.Label(hdr, text="操作序列:", bg=T["card2"], fg=T["text"],
            font=("Microsoft YaHei",9,"bold")).pack(side="left", padx=6)
        for label, kind in [("+ 鼠标","mouse"),("+ 按键","key"),
                             ("+ 文本","text"),("+ 延迟","delay"),("+ 滚轮","scroll")]:
            _btn(hdr, label, T["bp"],
                 lambda k=kind: self._add(k)).pack(side="left", padx=2, pady=2)

    # ── 增删移 ────────────────────────────────────────────

    def _add(self, kind):
        self._actions.append(copy.deepcopy(ACTION_DEFAULTS[kind]))
        self._rebuild()

    def _del(self, idx):
        if 0 <= idx < len(self._actions):
            del self._actions[idx]
        self._rebuild()

    def _move(self, idx, delta):
        """先 save 当前行再移动，防止 _rebuild 前数据丢失"""
        self._save_rows()
        j = idx + delta
        if 0 <= j < len(self._actions):
            self._actions[idx], self._actions[j] = self._actions[j], self._actions[idx]
        self._rebuild()

    # ── 数据 I/O ──────────────────────────────────────────

    def load(self, actions_list):
        """传入宿主列表的引用，重建行"""
        self._actions = actions_list
        self._rebuild()

    def save(self):
        """把当前 UI 状态写回 self._actions（原地修改，不返回新列表）"""
        self._save_rows()

    def _save_rows(self):
        for i, rw in enumerate(self._row_widgets):
            if i < len(self._actions):
                self._actions[i] = rw.get_data()

    # ── 重建行列表 ────────────────────────────────────────

    def _rebuild(self):
        for w in self._rows_frame.winfo_children():
            w.destroy()
        self._row_widgets = []
        n = len(self._actions)
        for i, act in enumerate(self._actions):
            rw = _ActionRow(
                self._rows_frame, self.app, act, i, n,
                on_del   = lambda idx=i: self._del(idx),
                on_up    = lambda idx=i: self._move(idx, -1),
                on_down  = lambda idx=i: self._move(idx, +1),
                get_hwnd = self._get_hwnd,
                get_cmode= self._get_cmode,
            )
            rw.pack(fill="x", pady=1)
            self._row_widgets.append(rw)


class _ActionRow(tk.Frame):
    """单条动作行，根据 kind 动态渲染不同控件"""

    def __init__(self, parent, app, action, idx, total,
                 on_del, on_up, on_down, get_hwnd, get_cmode):
        bg = T["card"] if idx % 2 == 0 else T["card2"]
        super().__init__(parent, bg=bg)
        self.app       = app
        self._bg       = bg
        self._action   = copy.deepcopy(action)
        self._get_hwnd = get_hwnd
        self._get_cmode = get_cmode
        self._build(idx, total, on_del, on_up, on_down)

    def _lbl(self, parent, text, w=None):
        kw = dict(bg=self._bg, fg=T["text2"],
                  font=("Microsoft YaHei",8))
        if w: kw["width"] = w
        return tk.Label(parent, text=text, **kw)

    def _ent(self, parent, width, default=""):
        e = tk.Entry(parent, bg=T["card2"], fg=T["text"],
                     insertbackground=T["text"], relief="flat",
                     font=("Microsoft YaHei",8), width=width, justify="center")
        e.insert(0, str(default))
        return e

    def _build(self, idx, total, on_del, on_up, on_down):
        bg = self._bg
        row = self  # 整个 frame 就是一行

        # 行号
        self._lbl(row, f"{idx+1}.").pack(side="left", padx=(4,2))

        kind = self._action.get("kind", "mouse")

        # 类型标签 [鼠]/[键]/[文]/[延]/[滚]
        kind_map = {"mouse":"[鼠]","key":"[键]","text":"[文]","delay":"[延]","scroll":"[滚]"}
        kind_colors = {"mouse":T["accent"],"key":T["warning"],"text":T["success"],
                       "delay":T["text2"],"scroll":T["info"] if "info" in T else T["text2"]}
        tk.Label(row, text=kind_map.get(kind,"[?]"),
            bg=bg, fg=kind_colors.get(kind, T["text2"]),
            font=("Microsoft YaHei",8,"bold"), width=4).pack(side="left", padx=2)

        # ── 各类型专属控件 ────────────────────────────────
        if kind == "delay":
            self._build_delay(row)
        elif kind == "key":
            self._build_key(row)
        elif kind == "text":
            self._build_text(row)
        elif kind == "scroll":
            self._build_scroll(row)
        else:  # mouse
            self._build_mouse(row)

        # ── 操作按钮（右侧固定）────────────────────────────
        _btn(row, "×", T["bd"], on_del).pack(side="right", padx=2, pady=1)
        _btn(row, "↓", T["bg2"], on_down).pack(side="right", padx=1, pady=1)
        _btn(row, "↑", T["bg2"], on_up).pack(side="right", padx=1, pady=1)

    # ── 延迟行 ────────────────────────────────────────────
    def _build_delay(self, row):
        self._lbl(row, "等待").pack(side="left", padx=(4,2))
        self._sec_e = self._ent(row, 6, self._action.get("seconds", 0.5))
        self._sec_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "秒").pack(side="left")

    # ── 键盘行 ────────────────────────────────────────────
    def _build_key(self, row):
        self._lbl(row, "按键").pack(side="left", padx=(4,2))
        self._key_cb = ttk.Combobox(row, values=_KEY_HINTS,
            font=("Microsoft YaHei",8), width=14)
        self._key_cb.set(self._action.get("key",""))
        self._key_cb.pack(side="left", padx=2, ipady=2)

        self._lbl(row, "操作").pack(side="left", padx=(6,2))
        self._kact_var = tk.StringVar(
            value=_KEY_ACTION_LABEL.get(self._action.get("action","press"),"按键"))
        ttk.Combobox(row, textvariable=self._kact_var,
            values=[v for _,v in _KEY_ACTIONS],
            width=6, state="readonly",
            font=("Microsoft YaHei",8)).pack(side="left", padx=2)

        self._lbl(row, "次数").pack(side="left", padx=(6,2))
        self._kcount_e = self._ent(row, 3, self._action.get("count",1))
        self._kcount_e.pack(side="left", padx=2, ipady=2)

        self._lbl(row, "间隔").pack(side="left", padx=(6,2))
        self._kintv_e = self._ent(row, 4, self._action.get("interval",0.05))
        self._kintv_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "秒").pack(side="left")

    # ── 文本行 ────────────────────────────────────────────
    def _build_text(self, row):
        self._lbl(row, "文本").pack(side="left", padx=(4,2))
        self._text_e = self._ent(row, 24, self._action.get("text",""))
        self._text_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "间隔").pack(side="left", padx=(6,2))
        self._tintv_e = self._ent(row, 4, self._action.get("interval",0.05))
        self._tintv_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "秒").pack(side="left")

    # ── 滚轮行 ────────────────────────────────────────────
    def _build_scroll(self, row):
        self._lbl(row, "位置").pack(side="left", padx=(4,2))
        self._lbl(row, "X").pack(side="left")
        self._sx_e = self._ent(row, 5, self._action.get("abs_x",0))
        self._sx_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "Y").pack(side="left")
        self._sy_e = self._ent(row, 5, self._action.get("abs_y",0))
        self._sy_e.pack(side="left", padx=2, ipady=2)
        _btn(row, "点选", T["bg2"], self._pick_scroll_coord).pack(side="left", padx=2)

        self._lbl(row, "方向").pack(side="left", padx=(6,2))
        self._sdir_var = tk.StringVar(value=self._action.get("direction","down"))
        ttk.Combobox(row, textvariable=self._sdir_var,
            values=["up","down"], width=5, state="readonly",
            font=("Microsoft YaHei",8)).pack(side="left", padx=2)

        self._lbl(row, "格数").pack(side="left", padx=(6,2))
        self._sclk_e = self._ent(row, 3, self._action.get("clicks",1))
        self._sclk_e.pack(side="left", padx=2, ipady=2)

        self._lbl(row, "间隔").pack(side="left", padx=(4,2))
        self._sintv_e = self._ent(row, 4, self._action.get("interval",0.1))
        self._sintv_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "秒").pack(side="left")

        self._lbl(row, "倍数").pack(side="left", padx=(4,2))
        self._smul_e = self._ent(row, 4, self._action.get("multiplier",1.0))
        self._smul_e.pack(side="left", padx=2, ipady=2)

    def _pick_scroll_coord(self):
        def fill(x, y):
            self._sx_e.delete(0,"end"); self._sx_e.insert(0, str(x))
            self._sy_e.delete(0,"end"); self._sy_e.insert(0, str(y))
        pick_screen_coord(fill)

    # ── 鼠标行 ────────────────────────────────────────────
    def _build_mouse(self, row):
        self._lbl(row, "前置等待").pack(side="left", padx=(4,2))
        self._pre_e = self._ent(row, 4, self._action.get("pre_delay",0.0))
        self._pre_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "秒").pack(side="left")

        self._lbl(row, "位置").pack(side="left", padx=(6,2))
        cur_mode = self._action.get("pos_mode","match_center")
        cur_label = _POS_LABEL.get(cur_mode, _POS_MODE_LABELS[0])
        self._pos_var = tk.StringVar(value=cur_label)
        self._pos_cb = ttk.Combobox(row, textvariable=self._pos_var,
            values=_POS_MODE_LABELS, width=14, state="readonly",
            font=("Microsoft YaHei",8))
        self._pos_cb.pack(side="left", padx=2)
        self._pos_var.trace_add("write", lambda *_: self._toggle_pos_fields())

        # 动态坐标字段容器（紧跟位置下拉）
        self._pos_extra = tk.Frame(row, bg=self._bg)
        self._pos_extra.pack(side="left")

        self._lbl(row, "方式").pack(side="left", padx=(6,2))
        ctype_label = _CLICK_LABELS.get(self._action.get("click_type","single"),"单击")
        self._ctype_var = tk.StringVar(value=ctype_label)
        ttk.Combobox(row, textvariable=self._ctype_var,
            values=[_CLICK_LABELS[k] for k in _CLICK_TYPES],
            width=6, state="readonly",
            font=("Microsoft YaHei",8)).pack(side="left", padx=2)

        self._lbl(row, "点击").pack(side="left", padx=(6,2))
        self._mcount_e = self._ent(row, 3, self._action.get("count",1))
        self._mcount_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "次").pack(side="left")

        self._lbl(row, "间隔").pack(side="left", padx=(4,2))
        self._mintv_e = self._ent(row, 4, self._action.get("interval",0.1))
        self._mintv_e.pack(side="left", padx=2, ipady=2)
        self._lbl(row, "秒").pack(side="left")

        # 初始化动态坐标字段
        self._pos_field_widgets = {}
        self._toggle_pos_fields()

    def _toggle_pos_fields(self):
        """根据位置模式切换显示的额外坐标字段"""
        if not hasattr(self, "_pos_extra"):
            return
        for w in self._pos_extra.winfo_children():
            w.destroy()
        self._pos_field_widgets = {}

        mode_label = self._pos_var.get()
        mode = _POS_MODE_VALS.get(mode_label, "match_center")
        bg = self._bg

        def lbl(t): return tk.Label(self._pos_extra, text=t,
            bg=bg, fg=T["text2"], font=("Microsoft YaHei",8))
        def ent(w, default):
            e = tk.Entry(self._pos_extra, bg=T["card2"], fg=T["text"],
                insertbackground=T["text"], relief="flat",
                font=("Microsoft YaHei",8), width=w, justify="center")
            e.insert(0, str(default))
            return e

        if mode == "offset":
            lbl("偏移X").pack(side="left", padx=(4,2))
            ex = ent(5, self._action.get("offset_x",0)); ex.pack(side="left", padx=2, ipady=2)
            lbl("Y").pack(side="left")
            ey = ent(5, self._action.get("offset_y",0)); ey.pack(side="left", padx=2, ipady=2)
            self._pos_field_widgets = {"offset_x": ex, "offset_y": ey}
        elif mode in ("window", "screen"):
            lbl("X").pack(side="left", padx=(4,2))
            ex = ent(6, self._action.get("abs_x",0)); ex.pack(side="left", padx=2, ipady=2)
            lbl("Y").pack(side="left")
            ey = ent(6, self._action.get("abs_y",0)); ey.pack(side="left", padx=2, ipady=2)
            _btn(self._pos_extra, "点选", T["bg2"],
                 lambda m=mode: self._pick_mouse_coord(m)).pack(side="left", padx=2)
            self._pos_field_widgets = {"abs_x": ex, "abs_y": ey}

    def _pick_mouse_coord(self, mode):
        def fill(x, y):
            w = self._pos_field_widgets
            if "abs_x" in w:
                w["abs_x"].delete(0,"end"); w["abs_x"].insert(0, str(x))
                w["abs_y"].delete(0,"end"); w["abs_y"].insert(0, str(y))
        if mode == "screen":
            pick_screen_coord(fill)
        else:
            hwnd = self._get_hwnd()
            if not hwnd:
                messagebox.showwarning("提示","请先绑定目标窗口"); return
            cap = self.app.cfg.get("capture_mode","printwindow")
            pick_window_coord(hwnd, fill, cap)

    # ── get_data ──────────────────────────────────────────
    def get_data(self):
        """读取当前行 UI 状态，返回 action dict"""
        kind = self._action.get("kind","mouse")
        d = copy.deepcopy(self._action)

        try:
            if kind == "delay":
                d["seconds"] = float(self._sec_e.get())

            elif kind == "key":
                d["key"]      = self._key_cb.get().strip()
                d["action"]   = _KEY_ACTION_VALS.get(self._kact_var.get(), "press")
                d["count"]    = max(1, int(self._kcount_e.get()))
                d["interval"] = float(self._kintv_e.get())

            elif kind == "text":
                d["text"]     = self._text_e.get()
                d["interval"] = float(self._tintv_e.get())

            elif kind == "scroll":
                d["abs_x"]      = int(self._sx_e.get())
                d["abs_y"]      = int(self._sy_e.get())
                d["direction"]  = self._sdir_var.get()
                d["clicks"]     = max(1, int(self._sclk_e.get()))
                d["interval"]   = float(self._sintv_e.get())
                d["multiplier"] = float(self._smul_e.get())

            else:  # mouse
                d["pre_delay"]  = float(self._pre_e.get())
                mode_label      = self._pos_var.get()
                d["pos_mode"]   = _POS_MODE_VALS.get(mode_label, "match_center")
                ctype_label     = self._ctype_var.get()
                # 反查 click_type 值
                ctype_rev = {v:k for k,v in _CLICK_LABELS.items()}
                d["click_type"] = ctype_rev.get(ctype_label, "single")
                d["count"]      = max(1, int(self._mcount_e.get()))
                d["interval"]   = float(self._mintv_e.get())
                fw = self._pos_field_widgets
                if "offset_x" in fw:
                    d["offset_x"] = int(fw["offset_x"].get())
                    d["offset_y"] = int(fw["offset_y"].get())
                if "abs_x" in fw:
                    d["abs_x"] = int(fw["abs_x"].get())
                    d["abs_y"] = int(fw["abs_y"].get())
        except Exception:
            pass  # 转换失败保留旧值

        return d


# ══════════════════════════════════════════════════════════
#  弹窗处理模板卡片
# ══════════════════════════════════════════════════════════
class PopupTemplateCard(tk.Frame):
    """弹窗处理模板的配置卡片（嵌套在 GroupCard 内）"""

    def __init__(self, parent, app, group_card, index, data,
                 on_delete, on_move_up=None, on_move_down=None):
        super().__init__(parent, bg=T["card"],
            highlightthickness=1, highlightbackground=T["border"])
        self.app        = app
        self.group_card = group_card
        self.index      = index
        self._data      = copy.deepcopy(data)
        self._template_path = data.get("template_path")
        self._color_val = data.get("target_color",[255,0,0])
        self._build(on_delete, on_move_up, on_move_down)
        self._load(data)

    def _build(self, on_delete, on_move_up=None, on_move_down=None):
        # 标题行
        hdr = tk.Frame(self, bg=T["card2"]); hdr.pack(fill="x")
        self._name_var = tk.StringVar()
        tk.Entry(hdr, textvariable=self._name_var,
            bg=T["card2"], fg=T["text"],
            insertbackground=T["text"], relief="flat",
            font=("Microsoft YaHei",8,"bold"), width=12).pack(
                side="left", padx=4, pady=3)
        self._type_var = tk.StringVar(value="ocr")
        ttk.Combobox(hdr, textvariable=self._type_var,
            values=["ocr","image","color"], width=6,
            state="readonly", font=("Microsoft YaHei",8)).pack(
                side="left", padx=4)
        self._type_var.trace_add("write", lambda *_: self._on_type_change())
        _btn(hdr,"删除",T["bd"],on_delete).pack(side="right",padx=4,pady=3)
        if on_move_down:
            _btn(hdr,"↓",T["bg2"],on_move_down).pack(side="right",padx=2,pady=3)
        if on_move_up:
            _btn(hdr,"↑",T["bg2"],on_move_up).pack(side="right",padx=2,pady=3)

        body = tk.Frame(self, bg=T["card"]); body.pack(fill="x", padx=8, pady=4)

        # ── 配置用窗口绑定（仅用于选区，运行时用实际弹窗hwnd）──
        wb = tk.Frame(body, bg=T["card2"],
            highlightthickness=1, highlightbackground=T["border"])
        wb.pack(fill="x", pady=(0,4))
        wbi = tk.Frame(wb, bg=T["card2"]); wbi.pack(fill="x", padx=6, pady=4)
        tk.Label(wbi, text="配置用窗口（选区时用）:", bg=T["card2"],
            fg=T["warning"], font=("Microsoft YaHei",8)).pack(side="left")
        self._cfg_kw_e = _entry(wbi, 12, "")
        self._cfg_kw_e.pack(side="left", padx=4, ipady=2)
        _btn(wbi,"查找",T["bp"],self._cfg_find_windows).pack(side="left",padx=2)
        wb2 = tk.Frame(wb, bg=T["card2"]); wb2.pack(fill="x", padx=6, pady=(0,2))
        self._cfg_win_lb = tk.Listbox(wb2, bg=T["card2"], fg=T["text"],
            selectbackground=T["accent"], font=("Microsoft YaHei",8),
            height=2, relief="flat", activestyle="none")
        sb_c = ttk.Scrollbar(wb2, command=self._cfg_win_lb.yview)
        self._cfg_win_lb.configure(yscrollcommand=sb_c.set)
        sb_c.pack(side="right", fill="y"); self._cfg_win_lb.pack(fill="x")
        self._cfg_win_data = []
        wb3 = tk.Frame(wb, bg=T["card2"]); wb3.pack(fill="x", padx=6, pady=(0,4))
        _btn(wb3,"绑定选中",T["bs"],self._cfg_bind_window).pack(side="left")
        self._cfg_bound_lbl = tk.Label(wb3, text="未绑定",
            bg=T["card2"], fg=T["text2"], font=("Microsoft YaHei",8))
        self._cfg_bound_lbl.pack(side="left", padx=8)
        self._cfg_hwnd = 0

        # ── 尺寸条件 ──
        sc = tk.Frame(body, bg=T["card"]); sc.pack(fill="x", pady=2)
        self._size_cond_ck = tk.BooleanVar(value=False)
        tk.Checkbutton(sc, text="尺寸条件（满足时检测指定区域，否则全窗口）",
            variable=self._size_cond_ck,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8),
            command=self._toggle_size_cond).pack(side="left")

        self._size_frame = tk.Frame(body, bg=T["card"])
        sr1 = tk.Frame(self._size_frame, bg=T["card"]); sr1.pack(fill="x", pady=2)
        tk.Label(sr1, text="宽度", bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._w_op = tk.StringVar(value=">")
        ttk.Combobox(sr1, textvariable=self._w_op,
            values=[">","<",">=","<="], width=3,
            state="readonly", font=("Microsoft YaHei",8)).pack(side="left", padx=2)
        self._w_val_e = _entry(sr1, 5, "0"); self._w_val_e.pack(side="left", padx=2, ipady=2)
        self._size_logic = tk.StringVar(value="and")
        for v,t in [("and","且"),("or","或")]:
            tk.Radiobutton(sr1, text=t, variable=self._size_logic, value=v,
                bg=T["card"], fg=T["text"], selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",8)).pack(side="left", padx=4)
        tk.Label(sr1, text="高度", bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._h_op = tk.StringVar(value=">")
        ttk.Combobox(sr1, textvariable=self._h_op,
            values=[">","<",">=","<="], width=3,
            state="readonly", font=("Microsoft YaHei",8)).pack(side="left", padx=2)
        self._h_val_e = _entry(sr1, 5, "0"); self._h_val_e.pack(side="left", padx=2, ipady=2)

        sr2 = tk.Frame(self._size_frame, bg=T["card"]); sr2.pack(fill="x", pady=2)
        _btn(sr2,"选择检测区域",T["bp"],self._select_region).pack(side="left")
        self._region_lbl = tk.Label(sr2, text="未设置", bg=T["card"],
            fg=T["text2"], font=("Microsoft YaHei",8))
        self._region_lbl.pack(side="left", padx=6)
        self._popup_region = None

        self._toggle_size_cond()

        # OCR 设置
        self._ocr_f = tk.Frame(body, bg=T["card"])
        r1 = tk.Frame(self._ocr_f, bg=T["card"]); r1.pack(fill="x",pady=1)
        tk.Label(r1,text="关键词:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._kw_e = _entry(r1, 18, ""); self._kw_e.pack(side="left",padx=4,ipady=2)
        tk.Label(r1,text="语言:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._lang_var = tk.StringVar(value="chi_sim")
        ttk.Combobox(r1,textvariable=self._lang_var,
            values=["chi_sim","chi_tra","eng"],width=7,
            state="readonly",font=("Microsoft YaHei",8)).pack(side="left",padx=4)
        self._match_empty_ocr = tk.BooleanVar(value=False)
        tk.Checkbutton(r1,text="匹配空结果",
            variable=self._match_empty_ocr,
            bg=T["card"],fg=T["accent"],selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left",padx=6)

        # OCR 引擎
        r1e = tk.Frame(self._ocr_f, bg=T["card"]); r1e.pack(fill="x",pady=1)
        tk.Label(r1e,text="引擎:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._ocr_engine = tk.StringVar(value="paddle")
        for v,t in [("paddle","PaddleOCR"),("tesseract","Tesseract")]:
            tk.Radiobutton(r1e,text=t,variable=self._ocr_engine,value=v,
                bg=T["card"],fg=T["text"],selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",8),
                command=self._toggle_ocr_engine).pack(side="left",padx=3)

        # Tesseract 专属参数
        self._tess_params_frame = tk.Frame(self._ocr_f, bg=T["card"])
        r1b = tk.Frame(self._tess_params_frame, bg=T["card"]); r1b.pack(fill="x",pady=1)
        tk.Label(r1b,text="PSM:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._ocr_psm = tk.StringVar(value="6")
        ttk.Combobox(r1b,textvariable=self._ocr_psm,
            values=["6","7","11","3","4","13"],width=3,
            state="readonly",font=("Microsoft YaHei",8)).pack(side="left",padx=2)
        tk.Label(r1b,text="放大:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left",padx=(6,0))
        self._ocr_scale = tk.StringVar(value="2")
        ttk.Combobox(r1b,textvariable=self._ocr_scale,
            values=["1","2","3"],width=2,
            state="readonly",font=("Microsoft YaHei",8)).pack(side="left",padx=2)
        tk.Label(r1b,text="x  对比度:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._ocr_contrast_e = _entry(r1b,4,"1.5")
        self._ocr_contrast_e.pack(side="left",padx=2,ipady=2)
        self._ocr_binarize = tk.BooleanVar(value=True)
        tk.Checkbutton(r1b,text="二值化 阈值:",
            variable=self._ocr_binarize,
            bg=T["card"],fg=T["text"],selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left",padx=(6,0))
        self._ocr_threshold_e = _entry(r1b,4,"128")
        self._ocr_threshold_e.pack(side="left",padx=2,ipady=2)
        self._ocr_invert = tk.BooleanVar(value=False)
        tk.Checkbutton(r1b,text="反色",
            variable=self._ocr_invert,
            bg=T["card"],fg=T["text"],selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left",padx=(6,0))

        # 图像设置
        self._img_f = tk.Frame(body, bg=T["card"])
        r2 = tk.Frame(self._img_f, bg=T["card"]); r2.pack(fill="x",pady=1)
        _btn(r2,"截图为模板",T["bp"],self._capture_template).pack(side="left")
        _btn(r2,"选择文件",T["bg2"],self._browse_template).pack(side="left",padx=4)
        self._tmpl_lbl = tk.Label(r2,text="未设置",bg=T["card"],
            fg=T["text2"],font=("Microsoft YaHei",8)); self._tmpl_lbl.pack(side="left")
        r2b= tk.Frame(self._img_f,bg=T["card"]); r2b.pack(fill="x",pady=1)
        tk.Label(r2b,text="阈值:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._thr_e = _entry(r2b,4,"80"); self._thr_e.pack(side="left",padx=4,ipady=2)
        tk.Label(r2b,text="%",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")

        # 颜色设置
        self._color_f = tk.Frame(body, bg=T["card"])
        r3 = tk.Frame(self._color_f, bg=T["card"]); r3.pack(fill="x",pady=1)
        _btn(r3,"拾色",T["bp"],self._pick_color).pack(side="left")
        self._color_preview = tk.Label(r3,width=3,bg="#ff0000",
            relief="solid",bd=1); self._color_preview.pack(side="left",padx=4)
        self._color_lbl = tk.Label(r3,text="RGB(255,0,0)",bg=T["card"],
            fg=T["text2"],font=("Microsoft YaHei",8)); self._color_lbl.pack(side="left")
        r3b= tk.Frame(self._color_f,bg=T["card"]); r3b.pack(fill="x",pady=1)
        tk.Label(r3b,text="容差:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._tol_e = _entry(r3b,4,"10"); self._tol_e.pack(side="left",padx=4,ipady=2)

        # ── 点击模式 + 后等待 + 抖动/模拟 ─────────────────
        r_act = tk.Frame(body,bg=T["card"]); r_act.pack(fill="x",pady=2)
        tk.Label(r_act,text="点击:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._cmode_var=tk.StringVar(value="postmessage")
        for v,t in [("postmessage","后台"),("quickswitch","前台")]:
            tk.Radiobutton(r_act,text=t,variable=self._cmode_var,value=v,
                bg=T["card"],fg=T["text"],selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",8)).pack(side="left",padx=2)
        tk.Label(r_act,text="点击后等待:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left",padx=(8,0))
        self._after_wait_e=_entry(r_act,3,"1")
        self._after_wait_e.pack(side="left",padx=2,ipady=2)
        tk.Label(r_act,text="秒",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._mouse_jitter   = tk.BooleanVar(value=True)
        self._mouse_humanize = tk.BooleanVar(value=True)
        tk.Checkbutton(r_act, text="坐标抖动",
            variable=self._mouse_jitter,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=(10,2))
        tk.Checkbutton(r_act, text="模拟人工",
            variable=self._mouse_humanize,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=2)

        # ── 操作序列编辑器 ────────────────────────────────
        self._action_editor = ActionSequenceEditor(
            body, self.app,
            get_hwnd_fn  = lambda: self._cfg_hwnd,
            get_cmode_fn = lambda: self._cmode_var.get(),
        )
        self._action_editor.pack(fill="x", pady=(2,4))

        # ── 匹配后停止流程 + 独立音效 ──
        r_stop = tk.Frame(body, bg=T["card"]); r_stop.pack(fill="x", pady=(4,0))
        self._after_match_stop = tk.BooleanVar(value=False)
        self._after_match_stop_all = tk.BooleanVar(value=False)

        def _on_stop_flow():
            if self._after_match_stop.get():
                self._after_match_stop_all.set(False)
        def _on_stop_all():
            if self._after_match_stop_all.get():
                self._after_match_stop.set(False)

        tk.Checkbutton(r_stop, text="匹配后停止弹窗流程",
            variable=self._after_match_stop,
            command=_on_stop_flow,
            bg=T["card"], fg=T["warning"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left")
        tk.Checkbutton(r_stop, text="匹配后停止全部监控",
            variable=self._after_match_stop_all,
            command=_on_stop_all,
            bg=T["card"], fg=T["danger"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=(12,0))

        r_snd = tk.Frame(body, bg=T["card"]); r_snd.pack(fill="x", pady=1)
        tk.Label(r_snd, text="匹配后音效:", bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        self._stop_sound_e = _entry(r_snd, 22, "")
        self._stop_sound_e.pack(side="left", padx=4, ipady=2)
        def _browse_stop_sound():
            p = filedialog.askopenfilename(title="选择音效文件",
                filetypes=[("音频","*.wav *.mp3"),("All","*.*")])
            if p:
                self._stop_sound_e.delete(0,"end")
                self._stop_sound_e.insert(0, p)
        def _preview_stop_sound():
            _play_sound(self._stop_sound_e.get().strip())
        _btn(r_snd, "浏览", T["bp"], _browse_stop_sound).pack(side="left")
        _btn(r_snd, "试听", T["bg2"], _preview_stop_sound).pack(side="left", padx=4)

        self._on_type_change()

    def _on_type_change(self):
        t=self._type_var.get()
        self._ocr_f.pack_forget()
        self._img_f.pack_forget()
        self._color_f.pack_forget()
        if t=="ocr": self._ocr_f.pack(fill="x",pady=2)
        elif t=="image": self._img_f.pack(fill="x",pady=2)
        elif t=="color": self._color_f.pack(fill="x",pady=2)

    def _toggle_ocr_engine(self):
        if self._ocr_engine.get() == "tesseract":
            self._tess_params_frame.pack(fill="x", pady=1)
        else:
            self._tess_params_frame.pack_forget()

    def _toggle_custom(self):
        show = self._click_target.get() in ("window","screen")
        if show:
            self._xy_frame.pack(fill="x", pady=(0,2))
        else:
            self._xy_frame.pack_forget()

    def _toggle_size_cond(self):
        if self._size_cond_ck.get():
            self._size_frame.pack(fill="x", pady=2)
        else:
            self._size_frame.pack_forget()

    def _cfg_find_windows(self):
        kw = self._cfg_kw_e.get().strip()
        wins = list_windows()
        if kw: wins = [(h,t) for h,t in wins if kw.lower() in t.lower()]
        self._cfg_win_data = wins
        self._cfg_win_lb.delete(0,"end")
        for h,t in wins:
            self._cfg_win_lb.insert("end", f"[{h}] {t}")

    def _cfg_bind_window(self):
        sel = self._cfg_win_lb.curselection()
        if not sel: messagebox.showwarning("提示","请先选择窗口"); return
        hwnd, title = self._cfg_win_data[sel[0]]
        self._cfg_hwnd = hwnd
        self._cfg_bound_lbl.config(
            text=f"[{hwnd}] {title[:28]}", fg=T["success"])

    def _select_region(self):
        hwnd = self._cfg_hwnd
        if not hwnd:
            messagebox.showwarning("提示","请先在上方绑定配置用窗口"); return
        cap_mode = self.app.cfg.get("capture_mode","printwindow")
        img = capture_full_preview(hwnd, cap_mode)
        if img is None:
            messagebox.showerror("失败","无法截取窗口，请确认窗口未最小化"); return

        win = tk.Toplevel(); win.title("选择检测区域（弹窗相对坐标）")
        win.attributes("-topmost",True); win.resizable(False,False)
        max_w,max_h = 1200,800
        scale = min(max_w/img.width, max_h/img.height, 1.0)
        dw,dh = int(img.width*scale), int(img.height*scale)
        disp = img.resize((dw,dh),Image.LANCZOS) if scale<1 else img
        tk_img = ImageTk.PhotoImage(disp)
        canvas = tk.Canvas(win,width=dw,height=dh,cursor="crosshair",
            bg="black",bd=0,highlightthickness=0)
        canvas.pack()
        canvas.create_image(0,0,anchor="nw",image=tk_img)
        canvas._ref = tk_img
        tk.Label(win,text="拖动选择检测区域（相对弹窗左上角）",
            bg="#222",fg="#aaa",font=("Microsoft YaHei",9)).pack(fill="x",pady=2)
        state = {"s":None,"r":None}
        def press(e): state["s"]=(e.x,e.y)
        def drag(e):
            if state["s"]:
                if state["r"]: canvas.delete(state["r"])
                state["r"]=canvas.create_rectangle(state["s"][0],state["s"][1],
                    e.x,e.y,outline="#f39c12",width=2,dash=(4,2))
        def release(e):
            if state["s"]:
                x1=int(min(state["s"][0],e.x)/scale)
                y1=int(min(state["s"][1],e.y)/scale)
                x2=int(max(state["s"][0],e.x)/scale)
                y2=int(max(state["s"][1],e.y)/scale)
                if x2-x1>4 and y2-y1>4:
                    self._popup_region = [x1,y1,x2,y2]
                    self._region_lbl.config(
                        text=f"({x1},{y1})-({x2},{y2})", fg=T["success"])
                win.destroy()
        canvas.bind("<ButtonPress-1>",press)
        canvas.bind("<B1-Motion>",drag)
        canvas.bind("<ButtonRelease-1>",release)
        win.bind("<Escape>",lambda e:win.destroy())

    def _capture_template(self):
        hwnd=self.app.cfg.get("target_hwnd",0)
        if not hwnd: messagebox.showwarning("提示","请先绑定目标窗口"); return
        img=capture_full_preview(hwnd,self.app.cfg.get("capture_mode","printwindow"))
        if img is None: messagebox.showerror("失败","截图失败"); return
        # 复用 GroupCard 的截取逻辑
        self.group_card._do_capture_template_from_image(img, self)

    def _browse_template(self):
        p=filedialog.askopenfilename(title="选择模板图像",
            filetypes=[("图像","*.png *.jpg *.bmp"),("All","*.*")])
        if p:
            self._template_path=p
            self._tmpl_lbl.config(text=os.path.basename(p),fg=T["success"])
            # 弹窗卡数据需通过父卡 save() 写入 cfg，再落盘
            try:
                self.group_card.save()
                save_config(self.group_card.app.cfg)
            except Exception:
                pass

    def _pick_color(self):
        hwnd=self.app.cfg.get("target_hwnd",0)
        if not hwnd: messagebox.showwarning("提示","请先绑定目标窗口"); return
        try:
            win32gui.SetWindowPos(hwnd,win32con.HWND_TOPMOST,0,0,0,0,
                win32con.SWP_NOMOVE|win32con.SWP_NOSIZE)
            time.sleep(0.1)
            win32gui.SetForegroundWindow(hwnd); time.sleep(0.15)
            win32gui.SetWindowPos(hwnd,win32con.HWND_NOTOPMOST,0,0,0,0,
                win32con.SWP_NOMOVE|win32con.SWP_NOSIZE)
        except: pass
        img=capture_full_preview(hwnd,self.app.cfg.get("capture_mode","printwindow"))
        if img is None: messagebox.showerror("失败","截图失败"); return
        self.group_card._do_pick_color_from_image(img, self)

    def _pick_coord(self):
        ct=self._click_target.get()
        def fill(x,y):
            self._cx_e.delete(0,"end"); self._cx_e.insert(0,str(x))
            self._cy_e.delete(0,"end"); self._cy_e.insert(0,str(y))
        if ct=="screen":
            pick_screen_coord(fill)
        elif ct=="window":
            # 窗口相对坐标使用该模板绑定的 config_hwnd
            hwnd = self._cfg_hwnd or self.app.cfg.get("target_hwnd",0)
            if not hwnd: messagebox.showwarning("提示","请先在上方绑定配置用窗口"); return
            pick_window_coord(hwnd,fill,
                self.app.cfg.get("capture_mode","printwindow"))
        else:
            messagebox.showinfo("提示","识别位置无需手动选坐标")

    def _load(self, d):
        self._name_var.set(d.get("name","弹窗模板"))
        self._type_var.set(d.get("type","ocr"))
        self._kw_e.delete(0,"end"); self._kw_e.insert(0,d.get("keywords",""))
        self._match_empty_ocr.set(d.get("match_empty_ocr",False))
        self._lang_var.set(d.get("language","chi_sim"))
        self._ocr_engine.set(d.get("ocr_engine","paddle"))
        self._toggle_ocr_engine()
        self._ocr_psm.set(str(d.get("ocr_psm",6)))
        self._ocr_scale.set(str(d.get("ocr_scale",2)))
        self._ocr_contrast_e.delete(0,"end")
        self._ocr_contrast_e.insert(0,str(d.get("ocr_contrast",1.5)))
        self._ocr_binarize.set(d.get("ocr_binarize",True))
        self._ocr_threshold_e.delete(0,"end")
        self._ocr_threshold_e.insert(0,str(d.get("ocr_threshold",128)))
        self._ocr_invert.set(d.get("ocr_invert",False))
        tp=d.get("template_path")
        self._template_path=tp
        self._tmpl_lbl.config(
            text=os.path.basename(tp) if tp else "未设置",
            fg=T["success"] if tp else T["text2"])
        self._thr_e.delete(0,"end"); self._thr_e.insert(0,str(d.get("threshold",80)))
        tc=d.get("target_color",[255,0,0])
        self._color_val=tc
        hex_c=f"#{tc[0]:02x}{tc[1]:02x}{tc[2]:02x}"
        self._color_preview.config(bg=hex_c)
        self._color_lbl.config(text=f"RGB({tc[0]},{tc[1]},{tc[2]})")
        self._tol_e.delete(0,"end"); self._tol_e.insert(0,str(d.get("tolerance",10)))
        self._cmode_var.set(d.get("click_mode","postmessage"))
        self._after_wait_e.delete(0,"end")
        self._after_wait_e.insert(0,str(d.get("after_click_wait",1)))
        self._mouse_jitter.set(d.get("mouse_jitter", True))
        self._mouse_humanize.set(d.get("mouse_humanize", True))
        if "actions" not in d:
            d["actions"] = []
        self._action_editor.load(d["actions"])
        # 尺寸条件
        self._size_cond_ck.set(d.get("size_cond_enabled",False))
        self._w_op.set(d.get("size_cond_w_op",">"))
        self._w_val_e.delete(0,"end"); self._w_val_e.insert(0,str(d.get("size_cond_w_val",0)))
        self._h_op.set(d.get("size_cond_h_op",">"))
        self._h_val_e.delete(0,"end"); self._h_val_e.insert(0,str(d.get("size_cond_h_val",0)))
        self._size_logic.set(d.get("size_cond_logic","and"))
        self._popup_region = d.get("region")
        if self._popup_region:
            r = self._popup_region
            self._region_lbl.config(text=f"({r[0]},{r[1]})-({r[2]},{r[3]})",fg=T["success"])
        self._toggle_size_cond()
        # 配置用窗口
        self._cfg_hwnd = d.get("config_hwnd",0)
        cfg_title = d.get("config_title","")
        if self._cfg_hwnd and cfg_title:
            self._cfg_bound_lbl.config(
                text=f"[{self._cfg_hwnd}] {cfg_title[:28]}", fg=T["success"])
        # 匹配后停止流程 + 独立音效
        self._after_match_stop.set(d.get("after_match_stop_flow", False))
        self._after_match_stop_all.set(d.get("after_match_stop_all", False))
        self._stop_sound_e.delete(0,"end")
        self._stop_sound_e.insert(0, d.get("after_match_sound_file",""))
        self._on_type_change()

    def get_data(self):
        d=copy.deepcopy(POPUP_TEMPLATE_DEFAULT)
        d["name"]=self._name_var.get()
        d["type"]=self._type_var.get()
        d["keywords"]=self._kw_e.get()
        d["match_empty_ocr"]=self._match_empty_ocr.get()
        d["language"]=self._lang_var.get()
        d["ocr_engine"]=self._ocr_engine.get()
        try: d["ocr_psm"]=int(self._ocr_psm.get())
        except: pass
        try: d["ocr_scale"]=int(self._ocr_scale.get())
        except: pass
        try: d["ocr_contrast"]=float(self._ocr_contrast_e.get())
        except: pass
        d["ocr_binarize"]=self._ocr_binarize.get()
        try: d["ocr_threshold"]=int(self._ocr_threshold_e.get())
        except: pass
        d["ocr_invert"]=self._ocr_invert.get()
        if self._template_path: d["template_path"]=self._template_path
        try: d["threshold"]=int(self._thr_e.get())
        except: pass
        d["target_color"]=self._color_val
        try: d["tolerance"]=int(self._tol_e.get())
        except: pass
        d["click_mode"]=self._cmode_var.get()
        try: d["after_click_wait"]=int(self._after_wait_e.get())
        except: pass
        d["mouse_jitter"]=self._mouse_jitter.get()
        d["mouse_humanize"]=self._mouse_humanize.get()
        self._action_editor.save()
        # d["actions"] 由 editor.save() 原地更新
        d["size_cond_enabled"]=self._size_cond_ck.get()
        d["size_cond_w_op"]=self._w_op.get()
        try: d["size_cond_w_val"]=int(self._w_val_e.get())
        except: pass
        d["size_cond_h_op"]=self._h_op.get()
        try: d["size_cond_h_val"]=int(self._h_val_e.get())
        except: pass
        d["size_cond_logic"]=self._size_logic.get()
        d["region"]=self._popup_region
        d["config_hwnd"]=self._cfg_hwnd
        d["config_title"]=self._cfg_bound_lbl.cget("text") if self._cfg_hwnd else ""
        d["after_match_stop_flow"]=self._after_match_stop.get()
        d["after_match_stop_all"]=self._after_match_stop_all.get()
        d["after_match_sound_file"]=self._stop_sound_e.get().strip()
        return d
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("懒人修仙传2自动化 v5")
        self.minsize(900,600)
        self.configure(bg=T["bg"])
        self.resizable(True,True)

        self.cfg      = load_config()
        # 恢复上次窗口大小/位置
        geo = self.cfg.get("window_geometry","1020x750")
        try: self.geometry(geo)
        except: self.geometry("1020x750")
        self.monitors = []   # GroupMonitor 列表
        self.cards    = []   # GroupCard 列表
        self._running = False
        self._win_data= []

        self._build_ui()
        self._refresh_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # 启动进程名自动绑定后台线程
        self._auto_bind_stop = threading.Event()
        threading.Thread(target=self._auto_bind_loop, daemon=True).start()

    # ── UI 骨架 ───────────────────────────────────────────

    def _build_ui(self):
        top=tk.Frame(self,bg=T["sidebar"],height=48)
        top.pack(fill="x"); top.pack_propagate(False)
        tk.Label(top,text="BgOcrClick v5",bg=T["sidebar"],
            fg=T["accent"],font=("Microsoft YaHei",13,"bold"),
            padx=18).pack(side="left",pady=8)
        is_admin=_is_admin()
        tk.Label(top,
            text="● 管理员" if is_admin else "● 非管理员",
            bg=T["sidebar"],
            fg=T["success"] if is_admin else T["warning"],
            font=("Microsoft YaHei",9)).pack(side="right",padx=6)
        self._status_lbl=tk.Label(top,text="●  未运行",
            bg=T["sidebar"],fg=T["text2"],font=("Microsoft YaHei",9))
        self._status_lbl.pack(side="right",padx=18)

        body=tk.Frame(self,bg=T["bg"]); body.pack(fill="both",expand=True)
        sidebar=tk.Frame(body,bg=T["sidebar"],width=280)
        sidebar.pack(fill="y",side="left"); sidebar.pack_propagate(False)
        self._content=tk.Frame(body,bg=T["bg"])
        self._content.pack(fill="both",expand=True)

        self._frames={}; self._nav_btns={}
        for key,label in [("home","🏠  首页"),
                           ("groups","⚙  监控组"),
                           ("setting","🔧  设置")]:
            b=tk.Button(sidebar,text=label,
                bg=T["sidebar"],fg=T["text2"],
                activebackground=T["card"],activeforeground=T["text"],
                relief="flat",anchor="w",padx=18,
                font=("Microsoft YaHei",9),cursor="hand2",
                command=lambda k=key:self._show_page(k))
            b.pack(fill="x",pady=1,ipady=10)
            self._nav_btns[key]=b

        # ── 快捷跳转区 ──────────────────────────────────────
        tk.Frame(sidebar, bg=T["card2"], height=1).pack(fill="x", pady=4)
        tk.Label(sidebar, text="快捷跳转", bg=T["sidebar"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(anchor="w", padx=12, pady=(2,2))

        jump_outer = tk.Frame(sidebar, bg=T["sidebar"],
            highlightthickness=1, highlightbackground=T["card2"])
        jump_outer.pack(fill="x", padx=8, pady=(0,4))

        jump_canvas = tk.Canvas(jump_outer, bg=T["sidebar"],
            bd=0, highlightthickness=0, height=1500)
        jump_sb = ttk.Scrollbar(jump_outer, orient="vertical",
            command=jump_canvas.yview)
        jump_canvas.configure(yscrollcommand=jump_sb.set)
        jump_sb.pack(side="right", fill="y")
        jump_canvas.pack(side="left", fill="x", expand=True)

        self._jump_frame = tk.Frame(jump_canvas, bg=T["sidebar"])
        jump_canvas_win = jump_canvas.create_window(
            (0,0), window=self._jump_frame, anchor="nw")

        def _jump_configure(e):
            jump_canvas.configure(scrollregion=jump_canvas.bbox("all"))
        def _jump_resize(e):
            jump_canvas.itemconfig(jump_canvas_win, width=e.width)
        self._jump_frame.bind("<Configure>", _jump_configure)
        jump_canvas.bind("<Configure>", _jump_resize)

        def _jump_scroll(e):
            jump_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        jump_canvas.bind("<MouseWheel>", _jump_scroll)
        self._jump_frame.bind("<MouseWheel>", _jump_scroll)
        self._jump_canvas = jump_canvas
        self._jump_scroll_fn = _jump_scroll

        self._frames["groups"] = self._build_groups()
        self._frames["home"]   = self._build_home()
        self._frames["setting"]= self._build_setting()
        self._show_page("home")
        self.after(100, self._start)   # 启动后自动开始监控
        # 初始化快捷键和按钮文字
        self._update_btn_labels()
        self.after(200, self._apply_hotkeys)
        self.after(50, self._refresh_jump_list)

    def _show_page(self,key):
        for f in self._frames.values(): f.pack_forget()
        self._frames[key].pack(fill="both",expand=True)
        for k,b in self._nav_btns.items():
            b.config(bg=T["card"] if k==key else T["sidebar"],
                     fg=T["text"] if k==key else T["text2"])

    def _scroll_to_card(self, card_index):
        """跳转到监控组页后，滚动使第 card_index 张卡片可见"""
        try:
            if not hasattr(self, "cards") or card_index >= len(self.cards):
                return
            card = self.cards[card_index]
            canvas = self._groups_canvas  # 监控组页的滚动 canvas
            # 强制更新布局
            canvas.update_idletasks()
            # 获取卡片在 canvas 内容 frame 中的 y 位置
            card.update_idletasks()
            y = card.winfo_y()
            total_h = self._groups_inner.winfo_height()
            canvas_h = canvas.winfo_height()
            if total_h <= canvas_h:
                return
            frac = y / total_h
            canvas.yview_moveto(frac)
        except Exception as e:
            try:
                with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
                    _lf.write(f"[{time.strftime('%H:%M:%S')}] _scroll_to_card 异常: {e}\n")
            except: pass

    # ── 首页 ─────────────────────────────────────────────

    def _build_home(self):
        f=tk.Frame(self._content,bg=T["bg"])

        # 状态卡
        sc=self._card(f,"功能状态")
        sr=tk.Frame(sc,bg=T["card"]); sr.pack(fill="x",pady=4)
        self._stat_dot=tk.Label(sr,text="●",bg=T["card"],
            fg=T["text2"],font=("Microsoft YaHei",9))
        self._stat_dot.pack(side="left",padx=(0,4))
        self._stat_txt=tk.Label(sr,text="未运行",bg=T["card"],
            fg=T["text2"],font=("Microsoft YaHei",9))
        self._stat_txt.pack(side="left")

        # 当前绑定摘要
        self._home_bound_lbl=tk.Label(sr,text="",bg=T["card"],
            fg=T["text2"],font=("Microsoft YaHei",9))
        self._home_bound_lbl.pack(side="left",padx=(20,0))

        br=tk.Frame(sc,bg=T["card"]); br.pack(fill="x",pady=(10,4))
        self._btn_start=_btn(br,"▶  开始运行",T["bs"],self._start)
        self._btn_start.pack(side="left",padx=(0,8))
        self._btn_stop=_btn(br,"■  停止运行",T["bd"],self._stop)
        self._btn_stop.pack(side="left")
        self._btn_stop.config(state="disabled")
        tk.Label(br,text="窗口绑定和截图方式在「监控组」页配置",
            bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left",padx=16)

        # ── 监控组快捷配置区 ──────────────────────────────
        qc_outer = tk.Frame(f, bg=T["bg"])
        qc_outer.pack(fill="x", padx=14, pady=6)
        tk.Label(qc_outer, text="监控组快捷配置",
            bg=T["bg"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(anchor="w", pady=(0,2))
        qc_card = tk.Frame(qc_outer, bg=T["card"],
            highlightthickness=1, highlightbackground=T["border"])
        qc_card.pack(fill="x")
        qc_inner = tk.Frame(qc_card, bg=T["card"])
        qc_inner.pack(fill="x", padx=10, pady=6)

        # 表头
        hdr_row = tk.Frame(qc_inner, bg=T["card2"])
        hdr_row.pack(fill="x", pady=(0,2))
        for txt, w in [("启用",4),("序号",4),("监控组名",16),("序列完成后切回",10),("间隔(秒)",7)]:
            tk.Label(hdr_row, text=txt, bg=T["card2"], fg=T["text2"],
                font=("Microsoft YaHei",8), width=w, anchor="w").pack(
                    side="left", padx=4, pady=2)

        # 可滚动列表容器
        qc_list_outer = tk.Frame(qc_inner, bg=T["card"],
            highlightthickness=1, highlightbackground=T["border"])
        qc_list_outer.pack(fill="x", pady=(0,4))
        qc_canvas = tk.Canvas(qc_list_outer, bg=T["card"],
            bd=0, highlightthickness=0, height=550)
        qc_sb = ttk.Scrollbar(qc_list_outer, orient="vertical",
            command=qc_canvas.yview)
        qc_canvas.configure(yscrollcommand=qc_sb.set)
        qc_sb.pack(side="right", fill="y")
        qc_canvas.pack(side="left", fill="x", expand=True)
        self._qc_list_frame = tk.Frame(qc_canvas, bg=T["card"])
        qc_canvas_win = qc_canvas.create_window(
            (0,0), window=self._qc_list_frame, anchor="nw")

        def _qc_configure(e):
            qc_canvas.configure(scrollregion=qc_canvas.bbox("all"))
        def _qc_resize(e):
            qc_canvas.itemconfig(qc_canvas_win, width=e.width)
        self._qc_list_frame.bind("<Configure>", _qc_configure)
        qc_canvas.bind("<Configure>", _qc_resize)

        def _qc_scroll(e):
            qc_canvas.yview_scroll(int(-1*(e.delta/120)), "units")

        def _bind_scroll_recursive(widget):
            widget.bind("<MouseWheel>", _qc_scroll)
            for child in widget.winfo_children():
                _bind_scroll_recursive(child)

        qc_canvas.bind("<MouseWheel>", _qc_scroll)
        self._qc_list_frame.bind("<MouseWheel>", _qc_scroll)
        # 保存引用，供 _refresh_quick_config 在新增行时重新绑定
        self._qc_scroll_fn = _qc_scroll
        self._qc_canvas = qc_canvas

        # 底部保存按钮
        qc_btn_row = tk.Frame(qc_inner, bg=T["card"])
        qc_btn_row.pack(fill="x", pady=(2,0))
        _btn(qc_btn_row, "保存快捷配置", T["bs"],
             self._save_quick_config).pack(side="left")
        tk.Label(qc_btn_row,
            text="（修改序号后保存将自动重排，重复序号会提示错误）",
            bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=8)

        # 存快捷配置行的控件引用列表
        self._qc_rows = []   # list of dict per group
        self._refresh_quick_config()

        # ── 运行日志（固定高度，不再 expand）──────────────
        lc_outer = tk.Frame(f, bg=T["bg"])
        lc_outer.pack(fill="x", padx=14, pady=6)
        tk.Label(lc_outer, text="运行日志",
            bg=T["bg"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(anchor="w", pady=(0,2))
        lc_card = tk.Frame(lc_outer, bg=T["card"],
            highlightthickness=1, highlightbackground=T["border"])
        lc_card.pack(fill="x")
        lc_inner = tk.Frame(lc_card, bg=T["card"])
        lc_inner.pack(fill="x", padx=10, pady=8)

        lf2=tk.Frame(lc_inner,bg=T["lb"]); lf2.pack(fill="x")
        self._log=tk.Text(lf2,bg=T["lb"],fg=T["lt"],
            font=("Consolas",9),relief="flat",state="disabled",
            wrap="word",bd=0,padx=6,pady=4,height=18)
        sb2=ttk.Scrollbar(lf2,command=self._log.yview)
        self._log.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right",fill="y"); self._log.pack(fill="x")
        for tag,color in [("ok",T["lo"]),("warn",T["lw"]),
                          ("err",T["le"]),("info",T["lt"])]:
            self._log.tag_config(tag,foreground=color)
        brow=tk.Frame(f,bg=T["bg"]); brow.pack(fill="x",pady=(4,0))
        _btn(brow,"清除日志",T["bg2"],self._clear_log).pack(side="right",padx=4)
        self._log_autoscroll = tk.BooleanVar(value=True)
        tk.Checkbutton(brow, text="滚动到底",
            variable=self._log_autoscroll,
            bg=T["bg"], fg=T["text2"], selectcolor=T["card"],
            activebackground=T["bg"],
            font=("Microsoft YaHei",8)).pack(side="right", padx=4)
        return f

    # ── 监控组页 ──────────────────────────────────────────

    def _build_groups(self):
        f=tk.Frame(self._content,bg=T["bg"])

        # ── 绑定窗口区 ────────────────────────────────────
        wc=self._card(f,"目标窗口")
        wr=tk.Frame(wc,bg=T["card"]); wr.pack(fill="x",pady=4)
        tk.Label(wr,text="标题关键字:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._kw_e2=tk.Entry(wr,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",
            font=("Microsoft YaHei",10),width=22)
        self._kw_e2.insert(0,self.cfg.get("target_title",""))
        self._kw_e2.pack(side="left",padx=6,ipady=4)
        _btn(wr,"查找",T["bp"],self._find_windows).pack(side="left",padx=4)

        lf_win=tk.Frame(wc,bg=T["card2"]); lf_win.pack(fill="x",pady=(4,0))
        self._win_lb=tk.Listbox(lf_win,bg=T["card2"],fg=T["text"],
            selectbackground=T["accent"],font=("Microsoft YaHei",9),
            height=3,relief="flat",activestyle="none")
        sb_win=ttk.Scrollbar(lf_win,command=self._win_lb.yview)
        self._win_lb.configure(yscrollcommand=sb_win.set)
        sb_win.pack(side="right",fill="y"); self._win_lb.pack(fill="x")

        wr2=tk.Frame(wc,bg=T["card"]); wr2.pack(fill="x",pady=(6,0))
        _btn(wr2,"绑定选中窗口",T["bs"],self._bind_window).pack(side="left")
        self._bound_lbl=tk.Label(wr2,text="未绑定",bg=T["card"],
            fg=T["text2"],font=("Microsoft YaHei",9))
        self._bound_lbl.pack(side="left",padx=10)

        # 已绑定时显示
        hwnd=self.cfg.get("target_hwnd",0)
        title=self.cfg.get("target_title","")
        if hwnd and title:
            self._bound_lbl.config(
                text=f"已绑定: [{hwnd}] {title[:36]}",fg=T["success"])

        # ── 进程名自动绑定 ────────────────────────────────
        abr = tk.Frame(wc, bg=T["card"]); abr.pack(fill="x", pady=(8,2))
        self._auto_bind_enabled = tk.BooleanVar(
            value=self.cfg.get("auto_bind_enabled", False))
        tk.Checkbutton(abr, text="按进程名自动绑定:",
            variable=self._auto_bind_enabled,
            bg=T["card"], fg=T["text"], selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9),
            command=self._save_auto_bind).pack(side="left")
        self._auto_bind_proc_e = tk.Entry(abr, bg=T["card2"], fg=T["text"],
            insertbackground=T["text"], relief="flat",
            font=("Microsoft YaHei",9), width=20)
        self._auto_bind_proc_e.insert(0, self.cfg.get("auto_bind_process",""))
        self._auto_bind_proc_e.pack(side="left", padx=6, ipady=3)
        tk.Label(abr, text="（如 game.exe，仅1个窗口时自动绑定，多窗口不自动）",
            bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left")
        _btn(abr, "保存", T["bp"], self._save_auto_bind).pack(side="left", padx=6)

        # ── 全局截图方式 ──────────────────────────────────
        gc=self._card(f,"全局截图方式")
        self._global_cap=tk.StringVar(
            value=self.cfg.get("capture_mode","printwindow"))
        cap_row=tk.Frame(gc,bg=T["card"]); cap_row.pack(fill="x",pady=2)
        for v,t,desc in [
            ("printwindow","PrintWindow","被遮挡有效，需管理员"),
            ("imagegrab",  "ImageGrab",  "颜色准，不需管理员"),
            ("auto",       "自动",        "先ImageGrab，黑图切PrintWindow"),
        ]:
            col=tk.Frame(cap_row,bg=T["card"]); col.pack(side="left",padx=6)
            tk.Radiobutton(col,text=t,variable=self._global_cap,value=v,
                bg=T["card"],fg=T["text"],selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",9)).pack(anchor="w")
            tk.Label(col,text=desc,bg=T["card"],fg=T["text2"],
                font=("Microsoft YaHei",7)).pack(anchor="w")

        # ── 操作栏 ───────────────────────────────────────
        top_bar=tk.Frame(f,bg=T["bg"]); top_bar.pack(fill="x",padx=14,pady=(4,6))
        _btn(top_bar,"+ 新增监控组",T["bp"],self._add_group).pack(side="left")
        _btn(top_bar,"保存所有配置",T["bs"],self._save_all).pack(side="left",padx=8)

        # ── 可滚动卡片区 ──────────────────────────────────
        outer=tk.Frame(f,bg=T["bg"]); outer.pack(fill="both",expand=True,padx=14)
        canvas=tk.Canvas(outer,bg=T["bg"],bd=0,highlightthickness=0)
        sb=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y")
        canvas.pack(side="left",fill="both",expand=True)
        self._groups_inner=tk.Frame(canvas,bg=T["bg"])
        canvas_win=canvas.create_window((0,0),window=self._groups_inner,anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_resize(e):
            canvas.itemconfig(canvas_win,width=e.width)
        self._groups_inner.bind("<Configure>",on_configure)
        canvas.bind("<Configure>",on_canvas_resize)

        def _scroll(e):
            canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        canvas.bind_all("<MouseWheel>",_scroll)

        self._groups_canvas=canvas
        self._rebuild_cards()
        return f

    def _rebuild_cards(self):
        """重建所有监控组卡片"""
        for w in self._groups_inner.winfo_children():
            w.destroy()
        self.cards.clear()

        for i in range(len(self.cfg["groups"])):
            self._add_card(i)

        self._update_chain_options()

    def _add_card(self, index):
        card=GroupCard(
            self._groups_inner, self, index,
            on_delete=lambda i=index: self._delete_group(i),
            on_move_up=lambda i=index: self._move_group(i,-1),
            on_move_down=lambda i=index: self._move_group(i,1),
        )
        card.pack(fill="x",pady=4)
        self.cards.append(card)

    def _add_group(self):
        self._save_all_cards()
        new=copy.deepcopy(GROUP_DEFAULT)
        new["name"]=f"监控组{len(self.cfg['groups'])+1}"
        self.cfg["groups"].append(new)
        save_config(self.cfg)
        self._rebuild_cards()

    def _delete_group(self, index):
        if not messagebox.askyesno("确认",f"删除监控组{index+1}？"): return
        self._save_all_cards()
        if 0<=index<len(self.cfg["groups"]):
            del self.cfg["groups"][index]
        # 修正所有组的 chain_target
        for g in self.cfg["groups"]:
            ct = g.get("chain_target",-1)
            if ct == index:
                g["chain_target"] = -1  # 被删的目标 → 清除
                g["chain_enabled"] = False
            elif ct > index:
                g["chain_target"] = ct - 1  # 后面的索引前移
        save_config(self.cfg)
        self._rebuild_cards()

    def _move_group(self, index, delta):
        self._save_all_cards()
        new_i=index+delta
        if new_i<0 or new_i>=len(self.cfg["groups"]): return
        gs=self.cfg["groups"]
        gs[index],gs[new_i]=gs[new_i],gs[index]
        # 修正所有组的 chain_target（两个互换的索引对调）
        for g in gs:
            ct = g.get("chain_target",-1)
            if ct == index: g["chain_target"] = new_i
            elif ct == new_i: g["chain_target"] = index
        save_config(self.cfg)
        self._rebuild_cards()

    def _update_chain_options(self):
        names=[g.get("name",f"组{i+1}") for i,g in enumerate(self.cfg["groups"])]
        for card in self.cards:
            card.update_chain_options(names)

    def _save_all_cards(self):
        for card in self.cards:
            try: card.save()
            except: pass
        self._update_chain_options()

    def _save_all(self):
        self._save_all_cards()
        if hasattr(self, "_global_cap"):
            self.cfg["capture_mode"]=self._global_cap.get()
        save_config(self.cfg)
        self.log("配置已保存","ok")
        self._refresh_quick_config()   # ← 同步首页快捷配置
        self._refresh_jump_list()       # ← 同步侧边栏跳转列表

    def _detect_chain_loops(self):
        """
        检测串联配置中的循环组，返回处于循环中的 index 集合。
        用 Floyd 判环思路：从每个启用串联的组出发，沿 chain_target 追踪，
        若路径中出现已访问节点则构成循环，路径上所有节点都标记为循环。
        """
        groups = self.cfg.get("groups", [])
        n = len(groups)
        in_loop = set()

        for start in range(n):
            if not groups[start].get("chain_enabled"): continue
            path = []
            visited = {}
            cur = start
            while True:
                g = groups[cur] if cur < n else None
                if g is None or not g.get("chain_enabled"): break
                nxt = g.get("chain_target", -1)
                if nxt < 0 or nxt >= n: break
                if nxt in visited:
                    # 找到循环，从循环入口到当前都标记
                    loop_start_pos = visited[nxt]
                    for idx in path[loop_start_pos:]:
                        in_loop.add(idx)
                    in_loop.add(nxt)
                    break
                visited[cur] = len(path)
                path.append(cur)
                cur = nxt

        return in_loop

    def _refresh_jump_list(self):
        """根据 cfg['groups'] 重建侧边栏快捷跳转列表"""
        if not hasattr(self, "_jump_frame"):
            return
        for w in self._jump_frame.winfo_children():
            w.destroy()

        in_loop = self._detect_chain_loops()

        for i, g in enumerate(self.cfg["groups"]):
            seq     = g.get("seq", i + 1)
            name    = g.get("name", f"监控组{i+1}")
            enabled = g.get("enabled", True)
            ct      = g.get("chain_target", -1)
            chain_str = ""
            if g.get("chain_enabled") and 0 <= ct < len(self.cfg["groups"]):
                cg    = self.cfg["groups"][ct]
                cseq  = cg.get("seq", ct + 1)
                cname = cg.get("name", f"监控组{ct+1}")
                chain_str = f" →{cseq}.{cname}"

            row_bg   = T["sidebar"]
            fg_color = T["success"] if enabled else T["text2"]

            row = tk.Frame(self._jump_frame, bg=row_bg, cursor="hand2")
            row.pack(fill="x", pady=1)

            loop_mark = "↺ " if i in in_loop else ""
            lbl_text = f"{loop_mark}{seq}. {name}{chain_str}"
            lbl = tk.Label(row, text=lbl_text,
                bg=row_bg, fg=fg_color,
                font=("Microsoft YaHei",8),
                anchor="w", padx=8, pady=3)
            lbl.pack(fill="x")

            def _jump(e, idx=i):
                self._show_page("groups")
                self.after(50, lambda: self._scroll_to_card(idx))
            row.bind("<Button-1>", _jump)
            lbl.bind("<Button-1>", _jump)

            def _enter(e, r=row, l=lbl):
                r.config(bg=T["card2"]); l.config(bg=T["card2"])
            def _leave(e, r=row, l=lbl, fg=fg_color):
                r.config(bg=T["sidebar"]); l.config(bg=T["sidebar"], fg=fg)
            row.bind("<Enter>", _enter); row.bind("<Leave>", _leave)
            lbl.bind("<Enter>", _enter); lbl.bind("<Leave>", _leave)

        self._jump_frame.update_idletasks()
        if hasattr(self, "_jump_canvas"):
            self._jump_canvas.configure(
                scrollregion=self._jump_canvas.bbox("all"))
        if hasattr(self, "_jump_scroll_fn"):
            def _rebind(w, fn):
                w.bind("<MouseWheel>", fn)
                for c in w.winfo_children(): _rebind(c, fn)
            _rebind(self._jump_frame, self._jump_scroll_fn)

    # ── 监控组快捷配置（首页） ────────────────────────────

    def _refresh_quick_config(self):
        """根据 cfg['groups'] 重建首页快捷配置列表行"""
        if not hasattr(self, "_qc_list_frame"):
            return
        # 清除旧行
        for w in self._qc_list_frame.winfo_children():
            w.destroy()
        self._qc_rows = []
        in_loop = self._detect_chain_loops()

        for i, g in enumerate(self.cfg["groups"]):
            row_bg = T["card"] if i % 2 == 0 else T["card2"]
            row = tk.Frame(self._qc_list_frame, bg=row_bg)
            row.pack(fill="x", pady=1)

            # 启用勾选
            en_var = tk.BooleanVar(value=g.get("enabled", True))
            tk.Checkbutton(row, variable=en_var,
                bg=row_bg, fg=T["text"], selectcolor=T["card"],
                activebackground=row_bg,
                font=("Microsoft YaHei",9), width=3).pack(side="left", padx=4)

            # 序号输入（用于重排）
            seq_var = tk.StringVar(value=str(i + 1))
            seq_e = tk.Entry(row, textvariable=seq_var,
                bg=T["card2"], fg=T["text"],
                insertbackground=T["text"], relief="flat",
                font=("Microsoft YaHei",9), width=4, justify="center")
            seq_e.pack(side="left", padx=4, ipady=2)

            # 组名输入（循环串联组加 ↺ 前缀提示）
            loop_prefix = "↺ " if i in in_loop else ""
            name_var = tk.StringVar(value=loop_prefix + g.get("name", f"组{i+1}"))
            name_e = tk.Entry(row, textvariable=name_var,
                bg=T["card2"], fg=T["text"],
                insertbackground=T["text"], relief="flat",
                font=("Microsoft YaHei",9), width=16)
            name_e.pack(side="left", padx=4, ipady=2)

            # 序列完成后切回
            sink_var = tk.BooleanVar(value=g.get("sink_after_click", False))
            tk.Checkbutton(row, variable=sink_var,
                bg=row_bg, fg=T["text"], selectcolor=T["card"],
                activebackground=row_bg,
                font=("Microsoft YaHei",9), width=8).pack(side="left", padx=4)

            # 间隔
            intv_var = tk.StringVar(value=str(g.get("interval", 5)))
            intv_e = tk.Entry(row, textvariable=intv_var,
                bg=T["card2"], fg=T["text"],
                insertbackground=T["text"], relief="flat",
                font=("Microsoft YaHei",9), width=5, justify="center")
            intv_e.pack(side="left", padx=4, ipady=2)

            # 右键跳转到对应监控组
            def _jump(event, idx=i):
                self._show_page("groups")
                self.after(50, lambda: self._scroll_to_card(idx))
            row.bind("<Button-3>", _jump)
            for child in row.winfo_children():
                child.bind("<Button-3>", _jump)

            self._qc_rows.append({
                "en": en_var, "seq": seq_var, "name": name_var,
                "sink": sink_var, "intv": intv_var
            })

        # 更新 canvas scrollregion，并对所有子控件递归绑定滚轮
        self._qc_list_frame.update_idletasks()
        if hasattr(self, "_qc_canvas"):
            self._qc_canvas.configure(
                scrollregion=self._qc_canvas.bbox("all"))
        if hasattr(self, "_qc_scroll_fn"):
            def _rebind(widget, fn):
                widget.bind("<MouseWheel>", fn)
                for child in widget.winfo_children():
                    _rebind(child, fn)
            _rebind(self._qc_list_frame, self._qc_scroll_fn)

    def _save_quick_config(self):
        """读取快捷配置列表，校验序号无重复后排序写入 cfg 并保存"""
        rows = self._qc_rows
        n = len(rows)
        if n == 0:
            return
        if n != len(self.cfg["groups"]):
            messagebox.showerror("错误", "快捷配置行数与监控组数不一致，请刷新后重试")
            return

        # 收集序号并校验
        seqs = []
        for i, r in enumerate(rows):
            try:
                s = int(r["seq"].get())
            except ValueError:
                messagebox.showerror("序号错误", f"第{i+1}行序号不是有效整数")
                return
            seqs.append(s)

        if len(seqs) != len(set(seqs)):
            dup = [s for s in seqs if seqs.count(s) > 1]
            messagebox.showerror("序号重复", f"存在重复序号: {sorted(set(dup))}，请修改后保存")
            return

        # 将 enabled / name / sink_after_click 写入 cfg（不排序时先原位更新）
        for i, r in enumerate(rows):
            g = self.cfg["groups"][i]
            g["enabled"] = r["en"].get()
            raw_name = r["name"].get().strip().lstrip("↺").strip()
            g["name"] = raw_name or g["name"]
            g["sink_after_click"] = r["sink"].get()
            try: g["interval"] = int(r["intv"].get())
            except: pass

        # 按序号重排 groups
        order = sorted(range(n), key=lambda i: seqs[i])
        self.cfg["groups"] = [self.cfg["groups"][i] for i in order]

        # 回写 seq 字段（按排序后的实际位置，用排序后的 seq 值）
        sorted_seqs = sorted(seqs)
        for i, g in enumerate(self.cfg["groups"]):
            g["seq"] = sorted_seqs[i]

        # chain_target 索引修正（old_pos → new_pos 映射）
        old_to_new = {old: new for new, old in enumerate(order)}
        for g in self.cfg["groups"]:
            ct = g.get("chain_target", -1)
            if ct >= 0:
                g["chain_target"] = old_to_new.get(ct, -1)

        save_config(self.cfg)
        self.log("快捷配置已保存，已按序号重排", "ok")

        # 同步刷新首页列表 + 监控组卡片
        self._refresh_quick_config()
        if hasattr(self, "_groups_inner"):
            self._rebuild_cards()
        self._refresh_jump_list()

    # ── 进程名自动绑定 ────────────────────────────────────

    def _save_auto_bind(self):
        """保存自动绑定设置到 cfg"""
        if not hasattr(self, "_auto_bind_enabled"):
            return
        self.cfg["auto_bind_enabled"] = self._auto_bind_enabled.get()
        self.cfg["auto_bind_process"] = self._auto_bind_proc_e.get().strip()
        save_config(self.cfg)
        state = "启用" if self.cfg["auto_bind_enabled"] else "禁用"
        self.log(f"自动绑定已{state}，进程名: {self.cfg['auto_bind_process']}", "info")

    def _auto_bind_loop(self):
        """
        后台线程：每3秒检测一次目标进程窗口。
        仅在启用状态 + 进程名非空时运行检测。
        只有恰好1个窗口时自动绑定；多窗口时只打日志提示，不自动绑定。
        进程重启后（hwnd失效或不同）自动更新绑定。
        """
        while not self._auto_bind_stop.is_set():
            try:
                enabled = self.cfg.get("auto_bind_enabled", False)
                proc    = self.cfg.get("auto_bind_process", "").strip()
                if enabled and proc:
                    wins = list_windows_by_process(proc)
                    if len(wins) == 1:
                        hwnd, title = wins[0]
                        cur_hwnd = self.cfg.get("target_hwnd", 0)
                        # 检查当前绑定是否仍然有效且一致
                        try:
                            cur_valid = HAS_WIN32 and win32gui.IsWindow(cur_hwnd)
                        except Exception:
                            cur_valid = False
                        if not cur_valid or hwnd != cur_hwnd:
                            self.cfg["target_hwnd"] = hwnd
                            self.cfg["target_title"] = title
                            save_config(self.cfg)
                            def _ui_update(h=hwnd, t=title):
                                try:
                                    self._bound_lbl.config(
                                        text=f"已绑定: [{h}] {t[:36]}",
                                        fg=T["success"])
                                except Exception:
                                    pass
                                try:
                                    self._home_bound_lbl.config(
                                        text=f"| 自动绑定: {t[:24]}",
                                        fg=T["success"])
                                except Exception:
                                    pass
                            self.after(0, _ui_update)
                            self.after(0, lambda t=title: self.log(
                                f"[自动绑定] 已绑定进程 {proc} 的窗口: 「{t}」", "ok"))
                    elif len(wins) > 1:
                        # 多窗口：只在绑定失效时提示一次
                        cur_hwnd = self.cfg.get("target_hwnd", 0)
                        try:
                            cur_valid = HAS_WIN32 and win32gui.IsWindow(cur_hwnd)
                        except Exception:
                            cur_valid = False
                        if not cur_valid:
                            self.after(0, lambda n=len(wins), p=proc: self.log(
                                f"[自动绑定] 进程 {p} 有 {n} 个窗口，请手动绑定", "warn"))
            except Exception as e:
                try:
                    with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
                        _lf.write(f"[{time.strftime('%H:%M:%S')}] [自动绑定] 异常: {e}\n")
                except Exception:
                    pass
            self._auto_bind_stop.wait(3.0)

    def _build_setting(self):
        f=tk.Frame(self._content,bg=T["bg"])

        pc=self._card(f,"PaddleOCR-json（推荐OCR引擎）")
        pl=tk.Label(pc,
            text="下载地址: https://github.com/hiroi-sora/PaddleOCR-json/releases/latest\n"
                 "下载 PaddleOCR-json_v1.4.1_windows_x64.7z，解压后选择其中的 .exe 文件",
            bg=T["card"],fg=T["text2"],font=("Microsoft YaHei",8),
            justify="left",anchor="w")
        pl.pack(fill="x",pady=(0,4))
        pr=tk.Frame(pc,bg=T["card"]); pr.pack(fill="x",pady=4)
        tk.Label(pr,text="exe路径:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._paddle_e=tk.Entry(pr,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",
            font=("Microsoft YaHei",9),width=46)
        self._paddle_e.insert(0,self.cfg.get("paddle_exe_path",""))
        self._paddle_e.pack(side="left",padx=6,ipady=4)
        def browse_paddle():
            p=filedialog.askopenfilename(title="选择PaddleOCR-json.exe",
                filetypes=[("EXE","*.exe"),("All","*.*")])
            if p: self._paddle_e.delete(0,"end"); self._paddle_e.insert(0,p)
        _btn(pr,"浏览",T["bp"],browse_paddle).pack(side="left")

        tc=self._card(f,"Tesseract OCR")
        r=tk.Frame(tc,bg=T["card"]); r.pack(fill="x",pady=4)
        tk.Label(r,text="路径:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._tess_e=tk.Entry(r,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",
            font=("Microsoft YaHei",9),width=50)
        self._tess_e.insert(0,self.cfg.get("tesseract_path",""))
        self._tess_e.pack(side="left",padx=6,ipady=4)
        def browse():
            p=filedialog.askopenfilename(title="选择tesseract.exe",
                filetypes=[("EXE","*.exe"),("All","*.*")])
            if p: self._tess_e.delete(0,"end"); self._tess_e.insert(0,p)
        _btn(r,"浏览",T["bp"],browse).pack(side="left")

        ac=self._card(f,"管理员权限")
        is_admin=_is_admin()
        tk.Label(ac,
            text=("✓ 已管理员权限运行" if is_admin
                  else "✗ 非管理员：PrintWindow截图会黑屏\n点击下方按钮提权"),
            bg=T["card"],fg=T["success"] if is_admin else T["warning"],
            font=("Microsoft YaHei",9),justify="left",anchor="w"
        ).pack(fill="x",padx=4,pady=4)
        if not is_admin:
            _btn(ac,"🔒 以管理员权限重启",T["bp"],_relaunch_as_admin).pack(
                anchor="w",pady=(4,0))

        dc=self._card(f,"依赖状态")
        for name,ok in [("pywin32",HAS_WIN32),("Pillow",HAS_PIL),
                         ("PaddleOCR",HAS_PADDLE),("pytesseract",HAS_TESSERACT),("opencv-python",HAS_CV2),
                         ("numpy",HAS_NUMPY),("pyautogui",HAS_PYAUTOGUI),
                         ("screeninfo",HAS_SCREENINFO)]:
            dr=tk.Frame(dc,bg=T["card"]); dr.pack(fill="x",pady=2)
            tk.Label(dr,text=name,bg=T["card"],fg=T["text"],
                font=("Microsoft YaHei",9),width=16,anchor="w").pack(side="left",padx=4)
            tk.Label(dr,text="● 已安装" if ok else "● 未安装",
                bg=T["card"],fg=T["success"] if ok else T["danger"],
                font=("Microsoft YaHei",9)).pack(side="left")

        hkc = self._card(f, "快捷键")
        hk_row = tk.Frame(hkc, bg=T["card"]); hk_row.pack(fill="x", pady=4)
        _FKEYS = ["（无）","F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12"]
        tk.Label(hk_row, text="开始监控:", bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._hk_start_var = tk.StringVar(
            value=self.cfg.get("hotkey_start","").upper() or "（无）")
        ttk.Combobox(hk_row, textvariable=self._hk_start_var,
            values=_FKEYS, width=6, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=6)
        tk.Label(hk_row, text="停止监控:", bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left", padx=(16,0))
        self._hk_stop_var = tk.StringVar(
            value=self.cfg.get("hotkey_stop","").upper() or "（无）")
        ttk.Combobox(hk_row, textvariable=self._hk_stop_var,
            values=_FKEYS, width=6, state="readonly",
            font=("Microsoft YaHei",9)).pack(side="left", padx=6)
        tk.Label(hk_row, text="（需管理员权限）", bg=T["card"], fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(side="left", padx=8)

        sc=self._card(f,"音效提示")
        sr1=tk.Frame(sc,bg=T["card"]); sr1.pack(fill="x",pady=4)
        self._sound_enabled=tk.BooleanVar(value=self.cfg.get("sound_enabled",False))
        tk.Checkbutton(sr1,text="启用音效提示",variable=self._sound_enabled,
            bg=T["card"],fg=T["text"],selectcolor=T["card2"],
            activebackground=T["card"],
            font=("Microsoft YaHei",9)).pack(side="left")
        sr2=tk.Frame(sc,bg=T["card"]); sr2.pack(fill="x",pady=2)
        tk.Label(sr2,text="音效文件:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._sound_e=tk.Entry(sr2,bg=T["card2"],fg=T["text"],
            insertbackground=T["text"],relief="flat",
            font=("Microsoft YaHei",9),width=42)
        self._sound_e.insert(0,self.cfg.get("sound_file",""))
        self._sound_e.pack(side="left",padx=6,ipady=4)
        def browse_sound():
            p=filedialog.askopenfilename(title="选择音效文件",
                filetypes=[("音频","*.wav *.mp3"),("WAV","*.wav"),("MP3","*.mp3"),("All","*.*")])
            if p: self._sound_e.delete(0,"end"); self._sound_e.insert(0,p)
        _btn(sr2,"浏览",T["bp"],browse_sound).pack(side="left")
        _btn(sr2,"试听",T["bg2"],lambda:_play_sound(self._sound_e.get())).pack(side="left",padx=4)
        sr3=tk.Frame(sc,bg=T["card"]); sr3.pack(fill="x",pady=2)
        tk.Label(sr3,text="播放时机:",bg=T["card"],fg=T["text2"],
            font=("Microsoft YaHei",9)).pack(side="left")
        self._sound_on_match=tk.BooleanVar(value=self.cfg.get("sound_on_match",True))
        self._sound_on_popup=tk.BooleanVar(value=self.cfg.get("sound_on_popup_match",False))
        self._sound_on_nomatch=tk.BooleanVar(value=self.cfg.get("sound_on_no_match",True))
        for var,text in [(self._sound_on_match,"主监控匹配"),
                         (self._sound_on_popup,"弹窗匹配"),
                         (self._sound_on_nomatch,"弹窗不匹配")]:
            tk.Checkbutton(sr3,text=text,variable=var,
                bg=T["card"],fg=T["text"],selectcolor=T["card2"],
                activebackground=T["card"],
                font=("Microsoft YaHei",9)).pack(side="left",padx=6)

        _btn(f,"保存设置",T["bs"],self._save_settings).pack(
            anchor="w",padx=16,pady=8)
        return f

    # ── UI 帮助 ───────────────────────────────────────────

    def _card(self,parent,title,expand=False):
        outer=tk.Frame(parent,bg=T["bg"])
        if expand: outer.pack(fill="both",expand=True,padx=14,pady=6)
        else:      outer.pack(fill="x",padx=14,pady=6)
        tk.Label(outer,text=title,bg=T["bg"],fg=T["text2"],
            font=("Microsoft YaHei",8)).pack(anchor="w",pady=(0,2))
        card=tk.Frame(outer,bg=T["card"],
            highlightthickness=1,highlightbackground=T["border"])
        if expand: card.pack(fill="both",expand=True)
        else:      card.pack(fill="x")
        inner=tk.Frame(card,bg=T["card"])
        if expand: inner.pack(fill="both",expand=True,padx=10,pady=8)
        else:      inner.pack(fill="x",padx=10,pady=8)
        return inner

    # ── 窗口查找/绑定 ────────────────────────────────────

    def _find_windows(self):
        kw=self._kw_e2.get().strip()
        wins=list_windows()
        if kw: wins=[(h,t) for h,t in wins if kw.lower() in t.lower()]
        self._win_data=wins
        self._win_lb.delete(0,"end")
        for h,t in wins: self._win_lb.insert("end",f"[{h}] {t}")
        self.log(f"找到 {len(wins)} 个窗口","info")

    def _bind_window(self):
        sel=self._win_lb.curselection()
        if not sel: messagebox.showwarning("提示","请先选择窗口"); return
        hwnd,title=self._win_data[sel[0]]
        self.cfg["target_hwnd"]=hwnd
        self.cfg["target_title"]=title
        self._bound_lbl.config(
            text=f"已绑定: [{hwnd}] {title[:36]}",fg=T["success"])
        # 同步首页摘要
        if hasattr(self,"_home_bound_lbl"):
            self._home_bound_lbl.config(
                text=f"| 已绑定: {title[:24]}",fg=T["success"])
        self.log(f"已绑定：[{hwnd}] {title}","ok")
        save_config(self.cfg)

    # ── 监控启停 ─────────────────────────────────────────

    def _start(self):
        if self._running: return
        self._save_all_cards()
        if hasattr(self, "_global_cap"):
            self.cfg["capture_mode"]=self._global_cap.get()
        if not self.cfg.get("target_hwnd"):
            messagebox.showwarning("提示","请先绑定目标窗口"); return
        enabled=[g for g in self.cfg["groups"] if g.get("enabled",True)]
        if not enabled:
            messagebox.showwarning("提示","没有已启用的监控组"); return
        for g in enabled:
            if g.get("type")=="ocr":
                eng = g.get("ocr_engine","paddle")
                if eng=="paddle" and not HAS_PADDLE:
                    messagebox.showwarning("缺少依赖","有监控组使用PaddleOCR，请先安装: pip install paddlepaddle paddleocr"); return
                if eng=="tesseract" and not HAS_TESSERACT:
                    messagebox.showwarning("缺少依赖","有监控组使用Tesseract，请先安装 pytesseract"); return

        # 启动 PaddleOCR-json 引擎（必须在监控线程启动之前完成）
        # 检查顶层 ocr 组 + 所有 popup_templates，两处都可能调用 paddle
        uses_paddle = any(
            g.get("ocr_engine","paddle")=="paddle" and g.get("type")=="ocr"
            for g in self.cfg["groups"] if g.get("enabled",True)
        )
        if not uses_paddle:
            uses_paddle = any(
                pt.get("ocr_engine","paddle")=="paddle"
                for g in self.cfg["groups"] if g.get("enabled",True)
                for pt in g.get("popup_templates",[])
            )
        if uses_paddle:
            exe = self.cfg.get("paddle_exe_path","").strip()
            if not exe or not os.path.exists(exe):
                messagebox.showwarning("提示",
                    "有监控组使用 PaddleOCR-json，请在设置页配置 PaddleOCR-json.exe 路径\n"
                    "下载：https://github.com/hiroi-sora/PaddleOCR-json/releases/latest")
                return
            try:
                self.log("正在启动 PaddleOCR-json 引擎...","info")
                _paddle_engine.start(exe)
                self.log("PaddleOCR-json 引擎就绪","ok")
            except Exception as e:
                messagebox.showerror("引擎启动失败", str(e))
                return

        self._running=True
        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")

        # 为每个组创建监控器（引擎已就绪后再启动线程）
        self.monitors=[GroupMonitor(self,i)
                       for i in range(len(self.cfg["groups"]))]
        # 只启动enabled的组
        for i,g in enumerate(self.cfg["groups"]):
            if g.get("enabled",True):
                self.monitors[i].start()

        self._set_status(True)
        self.log(f"▶ 启动 {len([g for g in self.cfg['groups'] if g.get('enabled',True)])} 个监控组","ok")

    def _stop(self):
        self._running=False
        for m in self.monitors: m.stop()
        self.monitors.clear()
        _paddle_engine.stop()
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._set_status(False)
        self.log("■ 已停止","warn")

    # ── 设置保存 ─────────────────────────────────────────

    def _save_settings(self):
        self.cfg["tesseract_path"]=self._tess_e.get().strip()
        self.cfg["paddle_exe_path"]=self._paddle_e.get().strip()
        self.cfg["sound_enabled"]=self._sound_enabled.get()
        self.cfg["sound_file"]=self._sound_e.get().strip()
        self.cfg["sound_on_match"]=self._sound_on_match.get()
        self.cfg["sound_on_popup_match"]=self._sound_on_popup.get()
        self.cfg["sound_on_no_match"]=self._sound_on_nomatch.get()
        # 快捷键
        hk_s = self._hk_start_var.get()
        hk_t = self._hk_stop_var.get()
        self.cfg["hotkey_start"] = "" if hk_s == "（无）" else hk_s.lower()
        self.cfg["hotkey_stop"]  = "" if hk_t == "（无）" else hk_t.lower()
        save_config(self.cfg)
        self._apply_hotkeys()
        self._update_btn_labels()
        self.log("设置已保存","ok")
        messagebox.showinfo("保存成功","设置已保存")

    def _apply_hotkeys(self):
        """注册/更新全局快捷键，需要 keyboard 库（管理员权限）"""
        try:
            import keyboard as _kb
            try: _kb.unhook_all_hotkeys()
            except: pass
            hk_s = self.cfg.get("hotkey_start", "")
            hk_t = self.cfg.get("hotkey_stop",  "")
            if hk_s:
                _kb.add_hotkey(hk_s, lambda: self.after(0, self._start))
            if hk_t:
                _kb.add_hotkey(hk_t, lambda: self.after(0, self._stop))
            if hk_s or hk_t:
                self.log(f"快捷键已注册: 开始={hk_s.upper() or '无'} 停止={hk_t.upper() or '无'}", "ok")
        except ImportError:
            self.log("keyboard 库未安装，快捷键不可用（pip install keyboard）", "warn")
        except Exception as e:
            self.log(f"快捷键注册失败: {e}", "warn")
            try:
                with open(_LOG_FILE, "a", encoding="utf-8") as _lf:
                    _lf.write(f"[{time.strftime('%H:%M:%S')}] _apply_hotkeys 异常: {e}\n")
            except: pass

    def _poll_hotkeys(self):
        pass  # keyboard 库版本无需轮询

    def _update_btn_labels(self):
        """把快捷键显示到首页开始/停止按钮文字上"""
        hk_s = self.cfg.get("hotkey_start", "").upper()
        hk_t = self.cfg.get("hotkey_stop",  "").upper()
        start_txt = f"▶  开始运行  [{hk_s}]" if hk_s else "▶  开始运行"
        stop_txt  = f"■  停止运行  [{hk_t}]" if hk_t else "■  停止运行"
        try:
            self._btn_start.config(text=start_txt)
            self._btn_stop.config(text=stop_txt)
        except: pass

    # ── 状态/日志 ────────────────────────────────────────

    def _set_status(self, running):
        color=T["success"] if running else T["text2"]
        text="运行中" if running else "未运行"
        self.after(0,lambda:self._status_lbl.config(text=f"●  {text}",fg=color))
        self.after(0,lambda:self._stat_dot.config(fg=color))
        self.after(0,lambda:self._stat_txt.config(text=text,fg=color))

    def log(self, msg, tag="info"):
        def _do():
            ts=time.strftime("%H:%M:%S")
            line=f"[{ts}] {msg}\n"
            self._log.config(state="normal")
            self._log.insert("end",line,tag)
            if getattr(self, "_log_autoscroll", None) and self._log_autoscroll.get():
                self._log.see("end")
            self._log.config(state="disabled")
            # 实时写入日志文件
            try:
                with open(_LOG_FILE,"a",encoding="utf-8") as _lf:
                    _lf.write(line)
            except: pass
        self.after(0,_do)

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0","end")
        self._log.config(state="disabled")

    def _refresh_status(self):
        self.after(3000,self._refresh_status)

    def _on_close(self):
        self._stop()
        self._save_all_cards()
        if hasattr(self, "_auto_bind_stop"):
            self._auto_bind_stop.set()
        try:
            import keyboard as _kb; _kb.unhook_all_hotkeys()
        except: pass
        if hasattr(self, "_global_cap"):
            self.cfg["capture_mode"]=self._global_cap.get()
        # 保存窗口位置大小
        try: self.cfg["window_geometry"] = self.geometry()
        except: pass
        save_config(self.cfg)
        # 将 log 控件内容写入文件
        try:
            content = self._log.get("1.0","end").strip()
            if content:
                with open(_LOG_FILE,"a",encoding="utf-8") as _lf:
                    _lf.write(content + "\n")
        except: pass
        self.destroy()

# ══════════════════════════════════════════════════════════
from bg_ocr_config import (
    CONFIG_FILE,
    LOG_FILE as _LOG_FILE,
    GROUP_DEFAULT,
    POPUP_TEMPLATE_DEFAULT,
    load_config,
    save_config,
)
from bg_ocr_capture import HAS_SCREENINFO, capture_region, capture_full_preview
from bg_ocr_ocr import HAS_PADDLE, HAS_TESSERACT, do_ocr_find_pos, do_ocr_text, get_paddle_engine, preprocess
from bg_ocr_matching import HAS_CV2, HAS_NUMPY, _imread_unicode, match_color, match_keywords, match_template
from bg_ocr_mouse import HAS_PYAUTOGUI, click_postmessage, click_quickswitch, exec_action_sequence
from bg_ocr_system import _is_admin, _relaunch_as_admin, list_windows, list_windows_by_process

_paddle_engine = get_paddle_engine()

def main():
    if not HAS_WIN32 or not HAS_PIL:
        root=tk.Tk(); root.withdraw()
        messagebox.showerror("缺少依赖",
            f"缺少：{', '.join(MISSING)}\n\n"
            "pip install pywin32 Pillow pytesseract pyautogui screeninfo opencv-python numpy")
        root.destroy(); sys.exit(1)

    if not _is_admin():
        root=tk.Tk(); root.withdraw()
        ans=messagebox.askyesno("权限提示",
            "当前非管理员权限。\n\n"
            "PrintWindow截图（被遮挡时有效）需要管理员权限，\n"
            "非管理员运行截图可能黑屏。\n\n"
            "是否以管理员权限重启？")
        root.destroy()
        if ans: _relaunch_as_admin()

    App().mainloop()


if __name__=="__main__":
    main()
