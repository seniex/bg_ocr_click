from __future__ import annotations

import copy
import os
import threading
import time

from bg_ocr.action_runtime import _play_sound
from bg_ocr.capture import Image, capture_region, win32gui
from bg_ocr.config import CONFIG_FILE, GROUP_DEFAULT, LOG_FILE as _LOG_FILE
from bg_ocr.matching import HAS_CV2, HAS_NUMPY, _imread_unicode, match_color, match_keywords, match_template
from bg_ocr.mouse import exec_action_sequence
from bg_ocr.ocr import HAS_PADDLE, HAS_TESSERACT, do_ocr_find_pos, do_ocr_text, preprocess


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

