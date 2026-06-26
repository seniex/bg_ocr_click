from __future__ import annotations

import copy
import json
import os
import threading
import time
from typing import Any

from PyQt6 import QtCore, QtGui, QtWidgets

from bg_ocr_capture import HAS_PIL, HAS_SCREENINFO, HAS_WIN32, capture_full_preview, capture_region
from bg_ocr_click import ACTION_DEFAULTS, GroupMonitor, _CLICK_TYPES, _KEY_ACTIONS, _KEY_HINTS, _POS_MODES, _play_sound
from bg_ocr_config import CONFIG_FILE, GROUP_DEFAULT, LOG_FILE, POPUP_TEMPLATE_DEFAULT, load_config, save_config
from bg_ocr_matching import HAS_CV2, HAS_NUMPY
from bg_ocr_mouse import HAS_PYAUTOGUI
from bg_ocr_ocr import HAS_PADDLE, HAS_TESSERACT, get_paddle_engine
from bg_ocr_system import _is_admin, _relaunch_as_admin, list_windows, list_windows_by_process

_paddle_engine = get_paddle_engine()


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


def _copy_group(data=None):
    g = copy.deepcopy(GROUP_DEFAULT)
    if data:
        g.update(data)
    return g


def _copy_template(data=None):
    t = copy.deepcopy(POPUP_TEMPLATE_DEFAULT)
    if data:
        t.update(data)
    return t


def _copy_action(kind="mouse", data=None):
    base = copy.deepcopy(ACTION_DEFAULTS.get(kind, ACTION_DEFAULTS["mouse"]))
    if data:
        base.update(data)
    return base


class _UiBridge(QtCore.QObject):
    log_requested = QtCore.pyqtSignal(str, str)
    invoke_requested = QtCore.pyqtSignal(object)
    status_requested = QtCore.pyqtSignal(bool)


class _ImagePickerDialog(QtWidgets.QDialog):
    def __init__(self, pil_image, mode="rect", parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择区域")
        self.setModal(True)
        self._mode = mode
        self._image = pil_image
        self._selection = None

        img = pil_image.convert("RGBA")
        self._qimage = QtGui.QImage(
            img.tobytes("raw", "RGBA"),
            img.width,
            img.height,
            img.width * 4,
            QtGui.QImage.Format.Format_RGBA8888,
        ).copy()
        pix = QtGui.QPixmap.fromImage(self._qimage)

        self._label = _PickLabel(pix, mode, self)
        self._label.selected.connect(self._on_selected)
        self._label.clicked.connect(self._on_clicked)

        self._info = QtWidgets.QLabel("拖拽选择区域，释放后自动确认" if mode == "rect" else "点击取样")
        self._info.setStyleSheet("color: #aaa;")
        self._info.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._info)
        layout.addWidget(btns)
        self.resize(min(pix.width() + 40, 1280), min(pix.height() + 100, 900))

    def _on_selected(self, data):
        self._selection = data
        self.accept()

    def _on_clicked(self, data):
        self._selection = data
        self.accept()

    @property
    def selection(self):
        return self._selection


class _PickLabel(QtWidgets.QLabel):
    selected = QtCore.pyqtSignal(object)
    clicked = QtCore.pyqtSignal(object)

    def __init__(self, pixmap, mode, parent=None):
        super().__init__(parent)
        self.setPixmap(pixmap)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setMouseTracking(True)
        self._mode = mode
        self._drag_start = None
        self._drag_end = None
        self._scale = 1.0
        self._base = pixmap
        self.setMinimumSize(pixmap.size())

    def _map_pos(self, pos):
        return int(pos.x() / self._scale), int(pos.y() / self._scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._base.isNull():
            return
        scale = min(self.width() / self._base.width(), self.height() / self._base.height(), 1.0)
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        size = QtCore.QSize(
            max(1, int(self._base.width() * scale)),
            max(1, int(self._base.height() * scale)),
        )
        self.setPixmap(self._base.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        ))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_end = event.position()
            self.update()

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            self._drag_end = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._mode == "point":
            x, y = self._map_pos(event.position())
            self.clicked.emit((x, y))
            return
        if self._drag_start is None:
            return
        self._drag_end = event.position()
        x1 = int(min(self._drag_start.x(), self._drag_end.x()) / self._scale)
        y1 = int(min(self._drag_start.y(), self._drag_end.y()) / self._scale)
        x2 = int(max(self._drag_start.x(), self._drag_end.x()) / self._scale)
        y2 = int(max(self._drag_start.y(), self._drag_end.y()) / self._scale)
        self._drag_start = None
        self._drag_end = None
        if x2 - x1 > 4 and y2 - y1 > 4:
            self.selected.emit([x1, y1, x2, y2])

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._mode != "rect" or self._drag_start is None or self._drag_end is None:
            return
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor("#3d6bff"), 2, QtCore.Qt.PenStyle.DashLine))
        rect = QtCore.QRectF(self._drag_start, self._drag_end).normalized()
        painter.drawRect(rect)


class _ScreenPointPickerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick screen point")
        self.setModal(True)
        self._point = None
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 45);")

        geom = QtCore.QRect()
        for screen in QtGui.QGuiApplication.screens():
            geom = geom.united(screen.geometry()) if geom.isValid() else screen.geometry()
        if geom.isValid():
            self.setGeometry(geom)

        label = QtWidgets.QLabel("Click target point, Esc to cancel", self)
        label.setStyleSheet("color: white; background: rgba(0, 0, 0, 180); padding: 10px 14px;")
        label.adjustSize()
        label.move(max(20, self.width() // 2 - label.width() // 2), 30)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint()
            self._point = (pos.x(), pos.y())
            self.accept()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @property
    def point(self):
        return self._point


class _WindowPickerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择目标窗口")
        self.setModal(True)
        self._windows = []
        self._selected = None

        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText("标题关键字")
        self._list = QtWidgets.QListWidget()
        self._refresh_btn = QtWidgets.QPushButton("刷新")
        self._bind_btn = QtWidgets.QPushButton("绑定")
        self._cancel_btn = QtWidgets.QPushButton("取消")

        self._refresh_btn.clicked.connect(self._refresh)
        self._bind_btn.clicked.connect(self._accept_selected)
        self._cancel_btn.clicked.connect(self.reject)
        self._filter.textChanged.connect(self._refresh)
        self._list.itemDoubleClicked.connect(lambda _item: self._accept_selected())

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self._filter)
        top.addWidget(self._refresh_btn)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._bind_btn)
        buttons.addWidget(self._cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._list)
        layout.addLayout(buttons)
        self.resize(780, 560)
        self._refresh()

    def _refresh(self):
        key = self._filter.text().strip().lower()
        self._list.clear()
        self._windows = list_windows()
        for hwnd, title in self._windows:
            if key and key not in title.lower():
                continue
            self._list.addItem(f"[{hwnd}] {title}")

    def _accept_selected(self):
        row = self._list.currentRow()
        if row < 0:
            return
        visible = []
        key = self._filter.text().strip().lower()
        for hwnd, title in self._windows:
            if key and key not in title.lower():
                continue
            visible.append((hwnd, title))
        if 0 <= row < len(visible):
            self._selected = visible[row]
            self.accept()

    @property
    def selected(self):
        return self._selected


class _ActionSequenceDialog(QtWidgets.QDialog):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑动作序列")
        self.setModal(True)
        self._actions = [_copy_action(a.get("kind", "mouse"), a) for a in (actions or []) if isinstance(a, dict)]
        self._current = -1
        self._loading = False
        self._build()
        self._refresh_list()
        if self._actions:
            self._list.setCurrentRow(0)

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        split = QtWidgets.QSplitter()
        self._list = QtWidgets.QListWidget()
        self._list.currentRowChanged.connect(self._change_row)
        split.addWidget(self._list)

        right = QtWidgets.QWidget()
        self._form = QtWidgets.QFormLayout(right)
        self._form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._fields = {}
        self._fields["kind"] = QtWidgets.QComboBox()
        self._fields["kind"].addItems(list(ACTION_DEFAULTS.keys()))
        self._fields["pre_delay"] = self._dspin(0, 3600, 0)
        self._fields["pos_mode"] = QtWidgets.QComboBox()
        self._fields["pos_mode"].addItems([key for key, _label in _POS_MODES])
        self._fields["offset_x"] = self._spin(-100000, 100000, 0)
        self._fields["offset_y"] = self._spin(-100000, 100000, 0)
        self._fields["abs_x"] = self._spin(-100000, 100000, 0)
        self._fields["abs_y"] = self._spin(-100000, 100000, 0)
        self._fields["click_type"] = QtWidgets.QComboBox()
        self._fields["click_type"].addItems(_CLICK_TYPES)
        self._fields["count"] = self._spin(1, 999, 1)
        self._fields["interval"] = self._dspin(0, 3600, 0.1)
        self._fields["key"] = QtWidgets.QComboBox()
        self._fields["key"].setEditable(True)
        self._fields["key"].addItems(_KEY_HINTS)
        self._fields["action"] = QtWidgets.QComboBox()
        self._fields["action"].addItems([key for key, _label in _KEY_ACTIONS])
        self._fields["text"] = QtWidgets.QLineEdit()
        self._fields["seconds"] = self._dspin(0, 3600, 0.5)
        self._fields["direction"] = QtWidgets.QComboBox()
        self._fields["direction"].addItems(["down", "up"])
        self._fields["clicks"] = self._spin(1, 999, 1)
        self._fields["multiplier"] = self._dspin(0.01, 100, 1.0)
        self._pick_window_btn = QtWidgets.QPushButton("Pick window point")
        self._pick_screen_btn = QtWidgets.QPushButton("Pick screen point")
        self._pick_window_btn.clicked.connect(self._pick_window_coord)
        self._pick_screen_btn.clicked.connect(self._pick_screen_coord)

        labels = [
            ("类型", "kind"),
            ("前置延迟", "pre_delay"),
            ("位置模式", "pos_mode"),
            ("偏移X", "offset_x"),
            ("偏移Y", "offset_y"),
            ("坐标X", "abs_x"),
            ("坐标Y", "abs_y"),
            ("点击类型", "click_type"),
            ("次数", "count"),
            ("间隔", "interval"),
            ("按键", "key"),
            ("按键动作", "action"),
            ("文本", "text"),
            ("延迟秒数", "seconds"),
            ("滚轮方向", "direction"),
            ("滚轮格数", "clicks"),
            ("滚轮倍率", "multiplier"),
        ]
        for label, key in labels:
            self._form.addRow(label, self._fields[key])

        pick_row = QtWidgets.QHBoxLayout()
        pick_row.addWidget(self._pick_window_btn)
        pick_row.addWidget(self._pick_screen_btn)
        self._form.addRow("Coordinate picker", _wrap(pick_row))

        for widget in self._fields.values():
            for signal_name in ("currentIndexChanged", "textChanged", "valueChanged"):
                try:
                    getattr(widget, signal_name).connect(self._save_current)
                except Exception:
                    pass

        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)

        buttons = QtWidgets.QHBoxLayout()
        self._add_btn = QtWidgets.QPushButton("新增")
        self._delete_btn = QtWidgets.QPushButton("删除")
        self._up_btn = QtWidgets.QPushButton("上移")
        self._down_btn = QtWidgets.QPushButton("下移")
        self._add_btn.clicked.connect(self._add_action)
        self._delete_btn.clicked.connect(self._delete_action)
        self._up_btn.clicked.connect(lambda: self._move_action(-1))
        self._down_btn.clicked.connect(lambda: self._move_action(1))
        for btn in [self._add_btn, self._delete_btn, self._up_btn, self._down_btn]:
            buttons.addWidget(btn)
        buttons.addStretch(1)

        dialog_buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        dialog_buttons.accepted.connect(self._accept)
        dialog_buttons.rejected.connect(self.reject)

        layout.addLayout(buttons)
        layout.addWidget(split)
        layout.addWidget(dialog_buttons)
        self.resize(900, 560)

    def _spin(self, minimum, maximum, value):
        sb = QtWidgets.QSpinBox()
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _dspin(self, minimum, maximum, value):
        sb = QtWidgets.QDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _owner_window(self):
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "current_hwnd") and hasattr(parent, "cfg"):
                return parent
            parent = parent.parent()
        return None

    def _refresh_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for i, action in enumerate(self._actions):
            self._list.addItem(f"{i + 1}. {self._action_label(action)}")
        self._list.blockSignals(False)

    def _action_label(self, action):
        kind = action.get("kind", "mouse")
        if kind == "mouse":
            return f"mouse {action.get('pos_mode', 'match_center')} {action.get('click_type', 'single')}"
        if kind == "key":
            return f"key {action.get('action', 'press')} {action.get('key', '')}"
        if kind == "text":
            return f"text {str(action.get('text', ''))[:20]}"
        if kind == "delay":
            return f"delay {action.get('seconds', 0.5)}s"
        if kind == "scroll":
            return f"scroll {action.get('direction', 'down')} {action.get('clicks', 1)}"
        return kind

    def _change_row(self, row):
        if self._loading:
            return
        self._save_current()
        self._current = row
        if 0 <= row < len(self._actions):
            self._load_action(self._actions[row])

    def _load_action(self, action):
        self._loading = True
        self._fields["kind"].setCurrentText(action.get("kind", "mouse"))
        self._fields["pre_delay"].setValue(float(action.get("pre_delay", 0.0)))
        self._fields["pos_mode"].setCurrentText(action.get("pos_mode", "match_center"))
        self._fields["offset_x"].setValue(int(action.get("offset_x", 0)))
        self._fields["offset_y"].setValue(int(action.get("offset_y", 0)))
        self._fields["abs_x"].setValue(int(action.get("abs_x", 0)))
        self._fields["abs_y"].setValue(int(action.get("abs_y", 0)))
        self._fields["click_type"].setCurrentText(action.get("click_type", "single"))
        self._fields["count"].setValue(int(action.get("count", 1)))
        self._fields["interval"].setValue(float(action.get("interval", 0.1)))
        self._fields["key"].setCurrentText(action.get("key", ""))
        self._fields["action"].setCurrentText(action.get("action", "press"))
        self._fields["text"].setText(action.get("text", ""))
        self._fields["seconds"].setValue(float(action.get("seconds", 0.5)))
        self._fields["direction"].setCurrentText(action.get("direction", "down"))
        self._fields["clicks"].setValue(int(action.get("clicks", 1)))
        self._fields["multiplier"].setValue(float(action.get("multiplier", 1.0)))
        self._loading = False

    def _save_current(self):
        if self._loading or not (0 <= self._current < len(self._actions)):
            return
        kind = self._fields["kind"].currentText()
        old = self._actions[self._current]
        action = _copy_action(kind, old)
        action["kind"] = kind
        action["pre_delay"] = self._fields["pre_delay"].value()
        if kind == "mouse":
            action.update({
                "pos_mode": self._fields["pos_mode"].currentText(),
                "offset_x": self._fields["offset_x"].value(),
                "offset_y": self._fields["offset_y"].value(),
                "abs_x": self._fields["abs_x"].value(),
                "abs_y": self._fields["abs_y"].value(),
                "click_type": self._fields["click_type"].currentText(),
                "count": self._fields["count"].value(),
                "interval": self._fields["interval"].value(),
            })
        elif kind == "key":
            action.update({
                "key": self._fields["key"].currentText(),
                "action": self._fields["action"].currentText(),
                "count": self._fields["count"].value(),
                "interval": self._fields["interval"].value(),
            })
        elif kind == "text":
            action.update({
                "text": self._fields["text"].text(),
                "interval": self._fields["interval"].value(),
            })
        elif kind == "delay":
            action["seconds"] = self._fields["seconds"].value()
        elif kind == "scroll":
            action.update({
                "abs_x": self._fields["abs_x"].value(),
                "abs_y": self._fields["abs_y"].value(),
                "direction": self._fields["direction"].currentText(),
                "clicks": self._fields["clicks"].value(),
                "interval": self._fields["interval"].value(),
                "multiplier": self._fields["multiplier"].value(),
            })
        self._actions[self._current] = action
        item = self._list.item(self._current)
        if item:
            item.setText(f"{self._current + 1}. {self._action_label(action)}")

    def _add_action(self):
        kind, ok = QtWidgets.QInputDialog.getItem(
            self, "新增动作", "类型", list(ACTION_DEFAULTS.keys()), 0, False
        )
        if not ok:
            return
        self._save_current()
        self._actions.append(_copy_action(kind))
        self._refresh_list()
        self._list.setCurrentRow(len(self._actions) - 1)

    def _delete_action(self):
        row = self._list.currentRow()
        if row < 0:
            return
        del self._actions[row]
        self._current = -1
        self._refresh_list()
        if self._actions:
            self._list.setCurrentRow(min(row, len(self._actions) - 1))

    def _move_action(self, direction):
        row = self._list.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= len(self._actions):
            return
        self._save_current()
        self._actions[row], self._actions[new_row] = self._actions[new_row], self._actions[row]
        self._refresh_list()
        self._list.setCurrentRow(new_row)

    def _set_abs_coord(self, x, y):
        self._fields["abs_x"].setValue(int(x))
        self._fields["abs_y"].setValue(int(y))
        self._save_current()

    def _pick_window_coord(self):
        if self._fields["kind"].currentText() != "mouse":
            QtWidgets.QMessageBox.information(self, "Tip", "Window-relative points are only used by mouse actions")
            return
        owner = self._owner_window()
        if owner is None or not owner.current_hwnd():
            QtWidgets.QMessageBox.warning(self, "Tip", "Bind a target window first")
            return
        img = capture_full_preview(owner.current_hwnd(), owner.cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "Failed", "Unable to capture target window")
            return
        dlg = _ImagePickerDialog(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            self._fields["pos_mode"].setCurrentText("window")
            self._set_abs_coord(x, y)

    def _pick_screen_coord(self):
        dlg = _ScreenPointPickerDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.point:
            x, y = dlg.point
            if self._fields["kind"].currentText() == "mouse":
                self._fields["pos_mode"].setCurrentText("screen")
            self._set_abs_coord(x, y)

    def _accept(self):
        self._save_current()
        self.accept()

    @property
    def actions(self):
        return self._actions


class _PopupTemplateDialog(QtWidgets.QDialog):
    def __init__(self, templates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit popup templates")
        self.setModal(True)
        self._templates = [_copy_template(t) for t in (templates or []) if isinstance(t, dict)]
        self._current = -1
        self._loading = False
        self._build()
        self._refresh_list()
        if self._templates:
            self._list.setCurrentRow(0)

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)

        buttons = QtWidgets.QHBoxLayout()
        self._add_btn = QtWidgets.QPushButton("Add")
        self._delete_btn = QtWidgets.QPushButton("Delete")
        self._up_btn = QtWidgets.QPushButton("Up")
        self._down_btn = QtWidgets.QPushButton("Down")
        self._add_btn.clicked.connect(self._add_template)
        self._delete_btn.clicked.connect(self._delete_template)
        self._up_btn.clicked.connect(lambda: self._move_template(-1))
        self._down_btn.clicked.connect(lambda: self._move_template(1))
        for btn in [self._add_btn, self._delete_btn, self._up_btn, self._down_btn]:
            buttons.addWidget(btn)
        buttons.addStretch(1)

        split = QtWidgets.QSplitter()
        self._list = QtWidgets.QListWidget()
        self._list.currentRowChanged.connect(self._change_row)
        split.addWidget(self._list)

        right = QtWidgets.QScrollArea()
        right.setWidgetResizable(True)
        form_widget = QtWidgets.QWidget()
        self._form = QtWidgets.QFormLayout(form_widget)
        self._form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._form.setHorizontalSpacing(10)
        self._form.setVerticalSpacing(8)
        self._fields = {}

        self._fields["name"] = QtWidgets.QLineEdit()
        self._fields["type"] = self._combo(["ocr", "image", "color"])
        self._fields["keywords"] = QtWidgets.QLineEdit()
        self._fields["language"] = self._combo(["chi_sim", "chi_sim_vert", "eng"], editable=True)
        self._fields["ocr_engine"] = self._combo(["paddle", "tesseract"])
        self._fields["ocr_psm"] = self._spin(0, 13, 6)
        self._fields["ocr_scale"] = self._spin(1, 8, 2)
        self._fields["ocr_binarize"] = QtWidgets.QCheckBox()
        self._fields["ocr_threshold"] = self._spin(0, 255, 128)
        self._fields["ocr_contrast"] = self._dspin(0.1, 5.0, 1.5)
        self._fields["ocr_invert"] = QtWidgets.QCheckBox()
        self._fields["template_path"] = QtWidgets.QLineEdit()
        self._fields["threshold"] = self._spin(0, 100, 80)
        self._fields["target_color"] = QtWidgets.QLineEdit()
        self._fields["tolerance"] = self._spin(0, 255, 10)
        self._fields["click_mode"] = self._combo(["postmessage", "quickswitch"])
        self._fields["mouse_jitter"] = QtWidgets.QCheckBox()
        self._fields["mouse_humanize"] = QtWidgets.QCheckBox()
        self._fields["after_click_wait"] = self._spin(0, 3600, 1)
        self._fields["click_type"] = self._combo(["single", "double", "right"])
        self._fields["click_target"] = self._combo(["keyword", "window", "screen"])
        self._fields["custom_x"] = self._spin(-100000, 100000, 0)
        self._fields["custom_y"] = self._spin(-100000, 100000, 0)
        self._fields["match_empty_ocr"] = QtWidgets.QCheckBox()
        self._fields["size_cond_enabled"] = QtWidgets.QCheckBox()
        self._fields["size_cond_w_op"] = self._combo([">", ">=", "=", "<=", "<"])
        self._fields["size_cond_w_val"] = self._spin(0, 100000, 0)
        self._fields["size_cond_h_op"] = self._combo([">", ">=", "=", "<=", "<"])
        self._fields["size_cond_h_val"] = self._spin(0, 100000, 0)
        self._fields["size_cond_logic"] = self._combo(["and", "or"])
        self._fields["region"] = QtWidgets.QLineEdit()
        self._fields["after_match_stop_flow"] = QtWidgets.QCheckBox()
        self._fields["after_match_stop_all"] = QtWidgets.QCheckBox()
        self._fields["after_match_sound_file"] = QtWidgets.QLineEdit()

        self._template_browse = QtWidgets.QPushButton("Browse")
        self._template_capture = QtWidgets.QPushButton("Capture")
        self._region_pick = QtWidgets.QPushButton("Pick")
        self._color_pick = QtWidgets.QPushButton("Pick")
        self._actions_edit = QtWidgets.QPushButton("Edit actions")
        self._sound_browse = QtWidgets.QPushButton("Browse")

        self._template_browse.clicked.connect(self._browse_template)
        self._template_capture.clicked.connect(self._capture_template)
        self._region_pick.clicked.connect(self._pick_region)
        self._color_pick.clicked.connect(self._pick_color)
        self._actions_edit.clicked.connect(self._edit_actions)
        self._sound_browse.clicked.connect(self._browse_sound)

        rows = [
            ("Name", "name"),
            ("Type", "type"),
            ("Keywords", "keywords"),
            ("Language", "language"),
            ("OCR engine", "ocr_engine"),
            ("OCR PSM", "ocr_psm"),
            ("OCR scale", "ocr_scale"),
            ("OCR binarize", "ocr_binarize"),
            ("OCR threshold", "ocr_threshold"),
            ("OCR contrast", "ocr_contrast"),
            ("OCR invert", "ocr_invert"),
            ("Similarity", "threshold"),
            ("Tolerance", "tolerance"),
            ("Click mode", "click_mode"),
            ("Mouse jitter", "mouse_jitter"),
            ("Humanize mouse", "mouse_humanize"),
            ("After click wait", "after_click_wait"),
            ("Click type", "click_type"),
            ("Click target", "click_target"),
            ("Custom X", "custom_x"),
            ("Custom Y", "custom_y"),
            ("Match empty OCR", "match_empty_ocr"),
            ("Size condition", "size_cond_enabled"),
            ("Width op", "size_cond_w_op"),
            ("Width value", "size_cond_w_val"),
            ("Height op", "size_cond_h_op"),
            ("Height value", "size_cond_h_val"),
            ("Size logic", "size_cond_logic"),
            ("Stop popup flow", "after_match_stop_flow"),
            ("Stop all", "after_match_stop_all"),
        ]
        for label, key in rows:
            self._form.addRow(label, self._fields[key])

        template_row = QtWidgets.QHBoxLayout()
        template_row.addWidget(self._fields["template_path"])
        template_row.addWidget(self._template_browse)
        template_row.addWidget(self._template_capture)
        self._form.addRow("Template image", _wrap(template_row))

        color_row = QtWidgets.QHBoxLayout()
        color_row.addWidget(self._fields["target_color"])
        color_row.addWidget(self._color_pick)
        self._form.addRow("Target color", _wrap(color_row))

        region_row = QtWidgets.QHBoxLayout()
        region_row.addWidget(self._fields["region"])
        region_row.addWidget(self._region_pick)
        self._form.addRow("Region", _wrap(region_row))

        sound_row = QtWidgets.QHBoxLayout()
        sound_row.addWidget(self._fields["after_match_sound_file"])
        sound_row.addWidget(self._sound_browse)
        self._form.addRow("Stop sound", _wrap(sound_row))
        self._form.addRow("Actions", self._actions_edit)

        for widget in self._fields.values():
            for signal_name in ("stateChanged", "currentIndexChanged", "textChanged", "valueChanged"):
                try:
                    getattr(widget, signal_name).connect(self._save_current)
                except Exception:
                    pass

        right.setWidget(form_widget)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        dialog_buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        dialog_buttons.accepted.connect(self._accept)
        dialog_buttons.rejected.connect(self.reject)

        layout.addLayout(buttons)
        layout.addWidget(split)
        layout.addWidget(dialog_buttons)
        self.resize(980, 680)

    def _combo(self, values, editable=False):
        cb = QtWidgets.QComboBox()
        cb.setEditable(editable)
        cb.addItems(values)
        return cb

    def _spin(self, minimum, maximum, value=0):
        sb = QtWidgets.QSpinBox()
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _dspin(self, minimum, maximum, value=0.0):
        sb = QtWidgets.QDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _owner_window(self):
        parent = self.parent()
        return parent.parent() if parent is not None else None

    def _refresh_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for i, tmpl in enumerate(self._templates):
            self._list.addItem(f"{i + 1}. {self._template_label(tmpl)}")
        self._list.blockSignals(False)

    def _template_label(self, tmpl):
        name = str(tmpl.get("name") or "Popup template")
        kind = tmpl.get("type", "ocr")
        if kind == "ocr":
            suffix = str(tmpl.get("keywords") or "")[:24]
        elif kind == "image":
            suffix = os.path.basename(str(tmpl.get("template_path") or ""))
        else:
            suffix = _format_color(tmpl.get("target_color", [255, 0, 0]))
        return f"{name} [{kind}] {suffix}".strip()

    def _change_row(self, row):
        if self._loading:
            return
        self._save_current()
        self._current = row
        if 0 <= row < len(self._templates):
            self._load_template(self._templates[row])

    def _set_combo(self, key, value):
        widget = self._fields[key]
        text = "" if value is None else str(value)
        if widget.findText(text) < 0 and widget.isEditable():
            widget.addItem(text)
        widget.setCurrentText(text)

    def _safe_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default

    def _load_template(self, tmpl):
        self._loading = True
        self._fields["name"].setText(str(tmpl.get("name", "")))
        self._set_combo("type", tmpl.get("type", "ocr"))
        self._fields["keywords"].setText(str(tmpl.get("keywords", "")))
        self._set_combo("language", tmpl.get("language", "chi_sim"))
        self._set_combo("ocr_engine", tmpl.get("ocr_engine", "paddle"))
        self._fields["ocr_psm"].setValue(self._safe_int(tmpl.get("ocr_psm", 6), 6))
        self._fields["ocr_scale"].setValue(self._safe_int(tmpl.get("ocr_scale", 2), 2))
        self._fields["ocr_binarize"].setChecked(bool(tmpl.get("ocr_binarize", True)))
        self._fields["ocr_threshold"].setValue(self._safe_int(tmpl.get("ocr_threshold", 128), 128))
        self._fields["ocr_contrast"].setValue(self._safe_float(tmpl.get("ocr_contrast", 1.5), 1.5))
        self._fields["ocr_invert"].setChecked(bool(tmpl.get("ocr_invert", False)))
        self._fields["template_path"].setText(str(tmpl.get("template_path") or ""))
        self._fields["threshold"].setValue(self._safe_int(tmpl.get("threshold", 80), 80))
        self._fields["target_color"].setText(_format_color(tmpl.get("target_color", [255, 0, 0])))
        self._fields["tolerance"].setValue(self._safe_int(tmpl.get("tolerance", 10), 10))
        self._set_combo("click_mode", tmpl.get("click_mode", "postmessage"))
        self._fields["mouse_jitter"].setChecked(bool(tmpl.get("mouse_jitter", True)))
        self._fields["mouse_humanize"].setChecked(bool(tmpl.get("mouse_humanize", True)))
        self._fields["after_click_wait"].setValue(self._safe_int(tmpl.get("after_click_wait", 1), 1))
        self._set_combo("click_type", tmpl.get("click_type", "single"))
        self._set_combo("click_target", tmpl.get("click_target", "keyword"))
        self._fields["custom_x"].setValue(self._safe_int(tmpl.get("custom_x", 0), 0))
        self._fields["custom_y"].setValue(self._safe_int(tmpl.get("custom_y", 0), 0))
        self._fields["match_empty_ocr"].setChecked(bool(tmpl.get("match_empty_ocr", False)))
        self._fields["size_cond_enabled"].setChecked(bool(tmpl.get("size_cond_enabled", False)))
        self._set_combo("size_cond_w_op", tmpl.get("size_cond_w_op", ">"))
        self._fields["size_cond_w_val"].setValue(self._safe_int(tmpl.get("size_cond_w_val", 0), 0))
        self._set_combo("size_cond_h_op", tmpl.get("size_cond_h_op", ">"))
        self._fields["size_cond_h_val"].setValue(self._safe_int(tmpl.get("size_cond_h_val", 0), 0))
        self._set_combo("size_cond_logic", tmpl.get("size_cond_logic", "and"))
        self._fields["region"].setText(_format_region(tmpl.get("region")))
        self._fields["after_match_stop_flow"].setChecked(bool(tmpl.get("after_match_stop_flow", False)))
        self._fields["after_match_stop_all"].setChecked(bool(tmpl.get("after_match_stop_all", False)))
        self._fields["after_match_sound_file"].setText(str(tmpl.get("after_match_sound_file", "")))
        self._loading = False

    def _save_current(self, *_args):
        if self._loading or not (0 <= self._current < len(self._templates)):
            return
        tmpl = _copy_template(self._templates[self._current])
        tmpl["name"] = self._fields["name"].text().strip() or tmpl["name"]
        tmpl["type"] = self._fields["type"].currentText()
        tmpl["keywords"] = self._fields["keywords"].text()
        tmpl["language"] = self._fields["language"].currentText()
        tmpl["ocr_engine"] = self._fields["ocr_engine"].currentText()
        tmpl["ocr_psm"] = self._fields["ocr_psm"].value()
        tmpl["ocr_scale"] = self._fields["ocr_scale"].value()
        tmpl["ocr_binarize"] = self._fields["ocr_binarize"].isChecked()
        tmpl["ocr_threshold"] = self._fields["ocr_threshold"].value()
        tmpl["ocr_contrast"] = self._fields["ocr_contrast"].value()
        tmpl["ocr_invert"] = self._fields["ocr_invert"].isChecked()
        tmpl["template_path"] = self._fields["template_path"].text().strip() or None
        tmpl["threshold"] = self._fields["threshold"].value()
        tmpl["target_color"] = _parse_color(self._fields["target_color"].text())
        tmpl["tolerance"] = self._fields["tolerance"].value()
        tmpl["click_mode"] = self._fields["click_mode"].currentText()
        tmpl["mouse_jitter"] = self._fields["mouse_jitter"].isChecked()
        tmpl["mouse_humanize"] = self._fields["mouse_humanize"].isChecked()
        tmpl["after_click_wait"] = self._fields["after_click_wait"].value()
        tmpl["click_type"] = self._fields["click_type"].currentText()
        tmpl["click_target"] = self._fields["click_target"].currentText()
        tmpl["custom_x"] = self._fields["custom_x"].value()
        tmpl["custom_y"] = self._fields["custom_y"].value()
        tmpl["match_empty_ocr"] = self._fields["match_empty_ocr"].isChecked()
        tmpl["size_cond_enabled"] = self._fields["size_cond_enabled"].isChecked()
        tmpl["size_cond_w_op"] = self._fields["size_cond_w_op"].currentText()
        tmpl["size_cond_w_val"] = self._fields["size_cond_w_val"].value()
        tmpl["size_cond_h_op"] = self._fields["size_cond_h_op"].currentText()
        tmpl["size_cond_h_val"] = self._fields["size_cond_h_val"].value()
        tmpl["size_cond_logic"] = self._fields["size_cond_logic"].currentText()
        tmpl["region"] = _parse_region(self._fields["region"].text())
        tmpl["after_match_stop_flow"] = self._fields["after_match_stop_flow"].isChecked()
        tmpl["after_match_stop_all"] = self._fields["after_match_stop_all"].isChecked()
        tmpl["after_match_sound_file"] = self._fields["after_match_sound_file"].text().strip()
        self._templates[self._current] = tmpl
        item = self._list.item(self._current)
        if item:
            item.setText(f"{self._current + 1}. {self._template_label(tmpl)}")

    def _add_template(self):
        self._save_current()
        tmpl = _copy_template()
        tmpl["name"] = f"{tmpl.get('name', 'Popup template')} {len(self._templates) + 1}"
        self._templates.append(tmpl)
        self._refresh_list()
        self._list.setCurrentRow(len(self._templates) - 1)

    def _delete_template(self):
        row = self._list.currentRow()
        if row < 0:
            return
        del self._templates[row]
        self._current = -1
        self._refresh_list()
        if self._templates:
            self._list.setCurrentRow(min(row, len(self._templates) - 1))

    def _move_template(self, direction):
        row = self._list.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= len(self._templates):
            return
        self._save_current()
        self._templates[row], self._templates[new_row] = self._templates[new_row], self._templates[row]
        self._refresh_list()
        self._list.setCurrentRow(new_row)

    def _edit_actions(self):
        if not (0 <= self._current < len(self._templates)):
            return
        self._save_current()
        dlg = _ActionSequenceDialog(self._templates[self._current].get("actions", []), self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._templates[self._current]["actions"] = dlg.actions
            self._refresh_list()
            self._list.setCurrentRow(self._current)

    def _browse_template(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select template image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All (*.*)"
        )
        if path:
            self._fields["template_path"].setText(path)
            self._save_current()

    def _browse_sound(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select sound file", "", "Audio (*.wav *.mp3);;All (*.*)")
        if path:
            self._fields["after_match_sound_file"].setText(path)
            self._save_current()

    def _capture_preview(self):
        owner = self._owner_window()
        if owner is None or not owner.current_hwnd():
            QtWidgets.QMessageBox.warning(self, "Tip", "Bind a target window first")
            return None
        img = capture_full_preview(owner.current_hwnd(), owner.cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "Failed", "Unable to capture target window")
        return img

    def _pick_region(self):
        img = self._capture_preview()
        if img is None:
            return
        dlg = _ImagePickerDialog(img, "rect", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            self._fields["region"].setText(_json_dump(dlg.selection))
            self._save_current()

    def _pick_color(self):
        img = self._capture_preview()
        if img is None:
            return
        dlg = _ImagePickerDialog(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            try:
                px = img.getpixel((x, y))
                color = [int(px[0]), int(px[1]), int(px[2])]
            except Exception:
                return
            self._fields["target_color"].setText(_format_color(color))
            self._save_current()

    def _capture_template(self):
        img = self._capture_preview()
        if img is None:
            return
        dlg = _ImagePickerDialog(img, "rect", self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dlg.selection:
            return
        x1, y1, x2, y2 = dlg.selection
        crop = img.crop((x1, y1, x2, y2))
        save_dir = os.path.dirname(CONFIG_FILE)
        os.makedirs(save_dir, exist_ok=True)
        owner = self._owner_window()
        group_index = owner.current_group_index() + 1 if owner is not None else 0
        path = os.path.join(save_dir, f"template_popup_g{group_index}_{int(time.time())}.png")
        crop.save(path)
        self._fields["template_path"].setText(path)
        self._save_current()

    def _accept(self):
        self._save_current()
        self.accept()

    @property
    def templates(self):
        return self._templates


class _GroupEditor(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets = {}
        self._build()

    def _add_labeled(self, form, label, widget):
        form.addRow(label, widget)
        return widget

    def _combo(self, values, editable=False):
        cb = QtWidgets.QComboBox()
        cb.setEditable(editable)
        cb.addItems(values)
        return cb

    def _spin(self, minimum, maximum, value=0):
        sb = QtWidgets.QSpinBox()
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _dspin(self, minimum, maximum, value=0.0):
        sb = QtWidgets.QDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self._form = QtWidgets.QFormLayout(inner)
        self._form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._form.setHorizontalSpacing(10)
        self._form.setVerticalSpacing(8)

        self._widgets["enabled"] = QtWidgets.QCheckBox("启用")
        self._widgets["name"] = QtWidgets.QLineEdit()
        self._widgets["type"] = self._combo(["ocr", "image", "color"])
        self._widgets["capture_mode"] = self._combo(["global", "printwindow", "imagegrab", "auto"])
        self._widgets["keywords"] = QtWidgets.QLineEdit()
        self._widgets["language"] = self._combo(["chi_sim", "chi_sim_vert", "eng"], editable=True)
        self._widgets["ocr_engine"] = self._combo(["paddle", "tesseract"])
        self._widgets["ocr_psm"] = self._spin(0, 13, 6)
        self._widgets["ocr_scale"] = self._spin(1, 8, 1)
        self._widgets["ocr_binarize"] = QtWidgets.QCheckBox("二值化")
        self._widgets["ocr_threshold"] = self._spin(0, 255, 128)
        self._widgets["ocr_contrast"] = self._dspin(0.1, 5.0, 1.5)
        self._widgets["ocr_invert"] = QtWidgets.QCheckBox("反色")
        self._widgets["region"] = QtWidgets.QLineEdit()
        self._widgets["template_path"] = QtWidgets.QLineEdit()
        self._widgets["threshold"] = self._spin(0, 100, 80)
        self._widgets["target_color"] = QtWidgets.QLineEdit()
        self._widgets["tolerance"] = self._spin(0, 255, 10)
        self._widgets["click_mode"] = self._combo(["postmessage", "quickswitch"])
        self._widgets["sink_after_click"] = QtWidgets.QCheckBox("点击后切回")
        self._widgets["mouse_jitter"] = QtWidgets.QCheckBox("鼠标抖动")
        self._widgets["mouse_humanize"] = QtWidgets.QCheckBox("人性化移动")
        self._widgets["actions"] = QtWidgets.QPlainTextEdit()
        self._widgets["click_type"] = self._combo(["single", "double", "right"])
        self._widgets["click_target"] = self._combo(["keyword", "window", "screen"])
        self._widgets["custom_x"] = self._spin(-100000, 100000, 0)
        self._widgets["custom_y"] = self._spin(-100000, 100000, 0)
        self._widgets["interval"] = self._spin(1, 3600, 5)
        self._widgets["pause"] = self._spin(0, 3600, 10)
        self._widgets["debug_save"] = QtWidgets.QCheckBox("调试保存截图")
        self._widgets["chain_enabled"] = QtWidgets.QCheckBox("启用串联")
        self._widgets["chain_target"] = self._combo([""], editable=False)
        self._widgets["chain_wait"] = self._spin(0, 3600, 2)
        self._widgets["popup_only_mode"] = QtWidgets.QCheckBox("仅弹窗模式")
        self._widgets["popup_enabled"] = QtWidgets.QCheckBox("启用弹窗流程")
        self._widgets["popup_title_kw"] = QtWidgets.QLineEdit()
        self._widgets["popup_wait_appear"] = self._spin(1, 3600, 5)
        self._widgets["popup_wait_close"] = self._spin(1, 3600, 10)
        self._widgets["popup_total_timeout"] = self._spin(10, 3600, 120)
        self._widgets["popup_no_match_action"] = self._combo(["continue", "pause_group", "stop_all"])
        self._widgets["popup_templates"] = QtWidgets.QPlainTextEdit()

        self._template_browse = QtWidgets.QPushButton("浏览")
        self._template_capture = QtWidgets.QPushButton("截取")
        self._region_pick = QtWidgets.QPushButton("选择")
        self._color_pick = QtWidgets.QPushButton("取色")
        self._actions_edit = QtWidgets.QPushButton("打开动作编辑器")
        self._popup_templates_edit = QtWidgets.QPushButton("Open popup template editor")
        self._region_preview = QtWidgets.QLabel("")
        self._template_preview = QtWidgets.QLabel("")

        self._template_browse.clicked.connect(self._browse_template)
        self._template_capture.clicked.connect(self._capture_template)
        self._region_pick.clicked.connect(self._pick_region)
        self._color_pick.clicked.connect(self._pick_color)
        self._actions_edit.clicked.connect(self._edit_actions)
        self._popup_templates_edit.clicked.connect(self._edit_popup_templates)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._widgets["region"])
        row.addWidget(self._region_pick)
        self._add_labeled(self._form, "区域", _wrap(row))

        trow = QtWidgets.QHBoxLayout()
        trow.addWidget(self._widgets["template_path"])
        trow.addWidget(self._template_browse)
        trow.addWidget(self._template_capture)
        self._add_labeled(self._form, "模板图", _wrap(trow))

        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(self._widgets["target_color"])
        crow.addWidget(self._color_pick)
        self._add_labeled(self._form, "颜色", _wrap(crow))

        for label, key in [
            ("启用", "enabled"),
            ("名称", "name"),
            ("类型", "type"),
            ("截取模式", "capture_mode"),
            ("关键字", "keywords"),
            ("语言", "language"),
            ("OCR引擎", "ocr_engine"),
            ("OCR PSM", "ocr_psm"),
            ("OCR 放大", "ocr_scale"),
            ("OCR 二值化", "ocr_binarize"),
            ("OCR 阈值", "ocr_threshold"),
            ("OCR 对比度", "ocr_contrast"),
            ("OCR 反色", "ocr_invert"),
            ("相似度阈值", "threshold"),
            ("容差", "tolerance"),
            ("点击模式", "click_mode"),
            ("点击后切回", "sink_after_click"),
            ("鼠标抖动", "mouse_jitter"),
            ("人性化移动", "mouse_humanize"),
            ("动作序列(JSON)", "actions"),
            ("点击类型", "click_type"),
            ("点击目标", "click_target"),
            ("自定义X", "custom_x"),
            ("自定义Y", "custom_y"),
            ("间隔", "interval"),
            ("暂停", "pause"),
            ("调试保存", "debug_save"),
            ("串联启用", "chain_enabled"),
            ("串联目标", "chain_target"),
            ("串联等待", "chain_wait"),
            ("仅弹窗", "popup_only_mode"),
            ("弹窗启用", "popup_enabled"),
            ("弹窗标题关键字", "popup_title_kw"),
            ("弹窗等待出现", "popup_wait_appear"),
            ("弹窗等待关闭", "popup_wait_close"),
            ("弹窗总超时", "popup_total_timeout"),
            ("弹窗无匹配动作", "popup_no_match_action"),
            ("弹窗模板(JSON)", "popup_templates"),
        ]:
            w = self._widgets[key]
            if isinstance(w, QtWidgets.QPlainTextEdit):
                w.setMinimumHeight(120)
            elif isinstance(w, QtWidgets.QLineEdit):
                w.setMinimumWidth(300)
            if key == "actions":
                action_layout = QtWidgets.QVBoxLayout()
                action_layout.addWidget(self._actions_edit)
                action_layout.addWidget(w)
                self._add_labeled(self._form, label, _wrap(action_layout))
            elif key == "popup_templates":
                template_layout = QtWidgets.QVBoxLayout()
                template_layout.addWidget(self._popup_templates_edit)
                template_layout.addWidget(w)
                self._add_labeled(self._form, label, _wrap(template_layout))
            else:
                self._add_labeled(self._form, label, w)

        self._widgets["ocr_binarize"].stateChanged.connect(self.changed.emit)
        self._widgets["ocr_invert"].stateChanged.connect(self.changed.emit)
        self._widgets["sink_after_click"].stateChanged.connect(self.changed.emit)
        self._widgets["mouse_jitter"].stateChanged.connect(self.changed.emit)
        self._widgets["mouse_humanize"].stateChanged.connect(self.changed.emit)
        self._widgets["debug_save"].stateChanged.connect(self.changed.emit)
        self._widgets["chain_enabled"].stateChanged.connect(self.changed.emit)
        self._widgets["popup_only_mode"].stateChanged.connect(self.changed.emit)
        self._widgets["popup_enabled"].stateChanged.connect(self.changed.emit)
        self._widgets["enabled"].stateChanged.connect(self.changed.emit)
        for key, widget in self._widgets.items():
            if isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox, QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                try:
                    widget.textChanged.connect(self.changed.emit)  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    widget.currentIndexChanged.connect(self.changed.emit)  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    widget.valueChanged.connect(self.changed.emit)  # type: ignore[attr-defined]
                except Exception:
                    pass

        scroll.setWidget(inner)
        layout.addWidget(scroll)
        self._inner = inner

    def set_chain_options(self, group_names, current_index):
        cb = self._widgets["chain_target"]
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("")
        self._chain_map = {}
        for i, name in enumerate(group_names):
            if i == current_index:
                continue
            label = f"{i + 1}:{name}"
            self._chain_map[label] = i
            cb.addItem(label)
        cb.blockSignals(False)

    def load_group(self, g, current_index=0):
        self._current_region = g.get("region")
        self._current_template = g.get("template_path")
        self._widgets["enabled"].setChecked(bool(g.get("enabled", True)))
        self._widgets["name"].setText(g.get("name", ""))
        self._widgets["type"].setCurrentText(g.get("type", "ocr"))
        self._widgets["capture_mode"].setCurrentText(g.get("capture_mode", "global"))
        self._widgets["keywords"].setText(g.get("keywords", ""))
        self._widgets["language"].setCurrentText(g.get("language", "chi_sim"))
        self._widgets["ocr_engine"].setCurrentText(g.get("ocr_engine", "paddle"))
        self._widgets["ocr_psm"].setValue(int(g.get("ocr_psm", 6)))
        self._widgets["ocr_scale"].setValue(int(g.get("ocr_scale", 1)))
        self._widgets["ocr_binarize"].setChecked(bool(g.get("ocr_binarize", True)))
        self._widgets["ocr_threshold"].setValue(int(g.get("ocr_threshold", 128)))
        self._widgets["ocr_contrast"].setValue(float(g.get("ocr_contrast", 1.5)))
        self._widgets["ocr_invert"].setChecked(bool(g.get("ocr_invert", False)))
        self._widgets["region"].setText(_format_region(g.get("region")))
        self._widgets["template_path"].setText(g.get("template_path") or "")
        self._widgets["threshold"].setValue(int(g.get("threshold", 80)))
        self._widgets["target_color"].setText(_format_color(g.get("target_color", [255, 0, 0])))
        self._widgets["tolerance"].setValue(int(g.get("tolerance", 10)))
        self._widgets["click_mode"].setCurrentText(g.get("click_mode", "postmessage"))
        self._widgets["sink_after_click"].setChecked(bool(g.get("sink_after_click", False)))
        self._widgets["mouse_jitter"].setChecked(bool(g.get("mouse_jitter", True)))
        self._widgets["mouse_humanize"].setChecked(bool(g.get("mouse_humanize", True)))
        self._widgets["actions"].setPlainText(_json_dump(g.get("actions", [])))
        self._widgets["click_type"].setCurrentText(g.get("click_type", "single"))
        self._widgets["click_target"].setCurrentText(g.get("click_target", "keyword"))
        self._widgets["custom_x"].setValue(int(g.get("custom_x", 0)))
        self._widgets["custom_y"].setValue(int(g.get("custom_y", 0)))
        self._widgets["interval"].setValue(int(g.get("interval", 5)))
        self._widgets["pause"].setValue(int(g.get("pause", 10)))
        self._widgets["debug_save"].setChecked(bool(g.get("debug_save", False)))
        self._widgets["chain_enabled"].setChecked(bool(g.get("chain_enabled", False)))
        self._widgets["chain_wait"].setValue(int(g.get("chain_wait", 2)))
        self._widgets["popup_only_mode"].setChecked(bool(g.get("popup_only_mode", False)))
        self._widgets["popup_enabled"].setChecked(bool(g.get("popup_enabled", False)))
        self._widgets["popup_title_kw"].setText(g.get("popup_title_kw", ""))
        self._widgets["popup_wait_appear"].setValue(int(g.get("popup_wait_appear", 5)))
        self._widgets["popup_wait_close"].setValue(int(g.get("popup_wait_close", 10)))
        self._widgets["popup_total_timeout"].setValue(int(g.get("popup_total_timeout", 120)))
        self._widgets["popup_no_match_action"].setCurrentText(g.get("popup_no_match_action", "continue"))
        self._widgets["popup_templates"].setPlainText(_json_dump(g.get("popup_templates", [])))
        self.set_chain_options([], current_index)
        ct = g.get("chain_target", -1)
        self._chain_target_index = ct

    def dump_group(self, current_index=0):
        g = _copy_group()
        g["enabled"] = self._widgets["enabled"].isChecked()
        g["name"] = self._widgets["name"].text().strip() or g["name"]
        g["type"] = self._widgets["type"].currentText()
        g["capture_mode"] = self._widgets["capture_mode"].currentText()
        g["keywords"] = self._widgets["keywords"].text()
        g["language"] = self._widgets["language"].currentText()
        g["ocr_engine"] = self._widgets["ocr_engine"].currentText()
        g["ocr_psm"] = self._widgets["ocr_psm"].value()
        g["ocr_scale"] = self._widgets["ocr_scale"].value()
        g["ocr_binarize"] = self._widgets["ocr_binarize"].isChecked()
        g["ocr_threshold"] = self._widgets["ocr_threshold"].value()
        g["ocr_contrast"] = self._widgets["ocr_contrast"].value()
        g["ocr_invert"] = self._widgets["ocr_invert"].isChecked()
        g["region"] = _parse_region(self._widgets["region"].text())
        g["template_path"] = self._widgets["template_path"].text().strip() or None
        g["threshold"] = self._widgets["threshold"].value()
        g["target_color"] = _parse_color(self._widgets["target_color"].text())
        g["tolerance"] = self._widgets["tolerance"].value()
        g["click_mode"] = self._widgets["click_mode"].currentText()
        g["sink_after_click"] = self._widgets["sink_after_click"].isChecked()
        g["mouse_jitter"] = self._widgets["mouse_jitter"].isChecked()
        g["mouse_humanize"] = self._widgets["mouse_humanize"].isChecked()
        g["actions"] = _json_load(self._widgets["actions"].toPlainText(), [])
        g["click_type"] = self._widgets["click_type"].currentText()
        g["click_target"] = self._widgets["click_target"].currentText()
        g["custom_x"] = self._widgets["custom_x"].value()
        g["custom_y"] = self._widgets["custom_y"].value()
        g["interval"] = self._widgets["interval"].value()
        g["pause"] = self._widgets["pause"].value()
        g["debug_save"] = self._widgets["debug_save"].isChecked()
        g["chain_enabled"] = self._widgets["chain_enabled"].isChecked()
        g["chain_wait"] = self._widgets["chain_wait"].value()
        if hasattr(self, "_chain_map"):
            g["chain_target"] = self._chain_map.get(self._widgets["chain_target"].currentText(), -1)
        else:
            g["chain_target"] = getattr(self, "_chain_target_index", -1)
        g["popup_only_mode"] = self._widgets["popup_only_mode"].isChecked()
        g["popup_enabled"] = self._widgets["popup_enabled"].isChecked()
        g["popup_title_kw"] = self._widgets["popup_title_kw"].text().strip()
        g["popup_wait_appear"] = self._widgets["popup_wait_appear"].value()
        g["popup_wait_close"] = self._widgets["popup_wait_close"].value()
        g["popup_total_timeout"] = self._widgets["popup_total_timeout"].value()
        g["popup_no_match_action"] = self._widgets["popup_no_match_action"].currentText()
        g["popup_templates"] = _json_load(self._widgets["popup_templates"].toPlainText(), [])
        return g

    def _edit_actions(self):
        actions = _json_load(self._widgets["actions"].toPlainText(), [])
        dlg = _ActionSequenceDialog(actions, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._widgets["actions"].setPlainText(_json_dump(dlg.actions))
            self.changed.emit()

    def _edit_popup_templates(self):
        templates = _json_load(self._widgets["popup_templates"].toPlainText(), [])
        if not isinstance(templates, list):
            templates = []
        dlg = _PopupTemplateDialog(templates, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._widgets["popup_templates"].setPlainText(_json_dump(dlg.templates))
            self.changed.emit()

    def _current_image(self):
        from bg_ocr_click import _is_admin  # lazy import to avoid early cycles
        return None

    def _pick_region(self):
        hwnd = self.parent().current_hwnd()
        if not hwnd:
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(hwnd, self.parent().cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截取窗口")
            return
        dlg = _ImagePickerDialog(img, "rect", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            region = dlg.selection
            self._widgets["region"].setText(_json_dump(region))
            self.changed.emit()

    def _pick_color(self):
        hwnd = self.parent().current_hwnd()
        if not hwnd:
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(hwnd, self.parent().cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截图")
            return
        dlg = _ImagePickerDialog(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            try:
                px = img.getpixel((x, y))
                color = [int(px[0]), int(px[1]), int(px[2])]
            except Exception:
                return
            self._widgets["target_color"].setText(_format_color(color))
            self.changed.emit()

    def _browse_template(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择模板图像", "", "Images (*.png *.jpg *.jpeg *.bmp);;All (*.*)"
        )
        if path:
            self._widgets["template_path"].setText(path)
            self.changed.emit()

    def _capture_template(self):
        hwnd = self.parent().current_hwnd()
        if not hwnd:
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(hwnd, self.parent().cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截图")
            return
        dlg = _ImagePickerDialog(img, "rect", self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dlg.selection:
            return
        x1, y1, x2, y2 = dlg.selection
        crop = img.crop((x1, y1, x2, y2))
        save_dir = os.path.dirname(CONFIG_FILE)
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, f"template_g{self.parent().current_group_index() + 1}.png")
        crop.save(path)
        self._widgets["template_path"].setText(path)
        self.changed.emit()


def _wrap(layout):
    w = QtWidgets.QWidget()
    w.setLayout(layout)
    return w


class _SettingsEditor(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets = {}
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(8)
        self._widgets["tesseract_path"] = QtWidgets.QLineEdit()
        self._widgets["paddle_exe_path"] = QtWidgets.QLineEdit()
        self._widgets["capture_mode"] = QtWidgets.QComboBox()
        self._widgets["capture_mode"].addItems(["printwindow", "imagegrab", "auto"])
        self._widgets["sound_enabled"] = QtWidgets.QCheckBox("启用音效提示")
        self._widgets["sound_file"] = QtWidgets.QLineEdit()
        self._widgets["sound_on_match"] = QtWidgets.QCheckBox("主流程匹配")
        self._widgets["sound_on_popup_match"] = QtWidgets.QCheckBox("弹窗匹配")
        self._widgets["sound_on_no_match"] = QtWidgets.QCheckBox("弹窗不匹配")
        self._widgets["hotkey_start"] = QtWidgets.QComboBox()
        self._widgets["hotkey_stop"] = QtWidgets.QComboBox()
        for cb in [self._widgets["hotkey_start"], self._widgets["hotkey_stop"]]:
            cb.addItems(["", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"])
        self._widgets["auto_bind_enabled"] = QtWidgets.QCheckBox("按进程名自动绑定")
        self._widgets["auto_bind_process"] = QtWidgets.QLineEdit()
        self._widgets["paddle_exe_browse"] = QtWidgets.QPushButton("浏览")
        self._widgets["tess_browse"] = QtWidgets.QPushButton("浏览")
        self._widgets["sound_browse"] = QtWidgets.QPushButton("浏览")
        self._widgets["sound_test"] = QtWidgets.QPushButton("试听")
        self._widgets["relaunch_admin"] = QtWidgets.QPushButton("以管理员重启")

        self._widgets["paddle_exe_browse"].clicked.connect(self._browse_paddle)
        self._widgets["tess_browse"].clicked.connect(self._browse_tess)
        self._widgets["sound_browse"].clicked.connect(self._browse_sound)
        self._widgets["sound_test"].clicked.connect(lambda: _play_sound(self._widgets["sound_file"].text().strip()))
        self._widgets["relaunch_admin"].clicked.connect(_relaunch_as_admin)

        form.addRow("Tesseract", self._row(self._widgets["tesseract_path"], self._widgets["tess_browse"]))
        form.addRow("PaddleOCR-json", self._row(self._widgets["paddle_exe_path"], self._widgets["paddle_exe_browse"]))
        form.addRow("全局截图方式", self._widgets["capture_mode"])
        form.addRow("音效开关", self._widgets["sound_enabled"])
        form.addRow("音效文件", self._row(self._widgets["sound_file"], self._widgets["sound_browse"], self._widgets["sound_test"]))
        form.addRow("音效触发", self._row(
            self._widgets["sound_on_match"],
            self._widgets["sound_on_popup_match"],
            self._widgets["sound_on_no_match"],
        ))
        form.addRow("启动热键", self._widgets["hotkey_start"])
        form.addRow("停止热键", self._widgets["hotkey_stop"])
        form.addRow("自动绑定", self._row(self._widgets["auto_bind_enabled"], self._widgets["auto_bind_process"]))
        form.addRow("管理员", self._widgets["relaunch_admin"])
        layout.addLayout(form)
        layout.addStretch(1)

    def _row(self, *widgets):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            lay.addWidget(widget)
        return w

    def load_settings(self, cfg):
        self._widgets["tesseract_path"].setText(cfg.get("tesseract_path", ""))
        self._widgets["paddle_exe_path"].setText(cfg.get("paddle_exe_path", ""))
        self._widgets["capture_mode"].setCurrentText(cfg.get("capture_mode", "printwindow"))
        self._widgets["sound_enabled"].setChecked(bool(cfg.get("sound_enabled", False)))
        self._widgets["sound_file"].setText(cfg.get("sound_file", ""))
        self._widgets["sound_on_match"].setChecked(bool(cfg.get("sound_on_match", True)))
        self._widgets["sound_on_popup_match"].setChecked(bool(cfg.get("sound_on_popup_match", False)))
        self._widgets["sound_on_no_match"].setChecked(bool(cfg.get("sound_on_no_match", True)))
        self._widgets["hotkey_start"].setCurrentText(cfg.get("hotkey_start", "").upper())
        self._widgets["hotkey_stop"].setCurrentText(cfg.get("hotkey_stop", "").upper())
        self._widgets["auto_bind_enabled"].setChecked(bool(cfg.get("auto_bind_enabled", False)))
        self._widgets["auto_bind_process"].setText(cfg.get("auto_bind_process", ""))

    def dump_settings(self):
        return {
            "tesseract_path": self._widgets["tesseract_path"].text().strip(),
            "paddle_exe_path": self._widgets["paddle_exe_path"].text().strip(),
            "capture_mode": self._widgets["capture_mode"].currentText(),
            "sound_enabled": self._widgets["sound_enabled"].isChecked(),
            "sound_file": self._widgets["sound_file"].text().strip(),
            "sound_on_match": self._widgets["sound_on_match"].isChecked(),
            "sound_on_popup_match": self._widgets["sound_on_popup_match"].isChecked(),
            "sound_on_no_match": self._widgets["sound_on_no_match"].isChecked(),
            "hotkey_start": self._widgets["hotkey_start"].currentText().strip().lower(),
            "hotkey_stop": self._widgets["hotkey_stop"].currentText().strip().lower(),
            "auto_bind_enabled": self._widgets["auto_bind_enabled"].isChecked(),
            "auto_bind_process": self._widgets["auto_bind_process"].text().strip(),
        }

    def _browse_paddle(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择PaddleOCR-json.exe", "", "EXE (*.exe);;All (*.*)")
        if path:
            self._widgets["paddle_exe_path"].setText(path)

    def _browse_tess(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择tesseract.exe", "", "EXE (*.exe);;All (*.*)")
        if path:
            self._widgets["tesseract_path"].setText(path)

    def _browse_sound(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择音效文件", "", "Audio (*.wav *.mp3);;All (*.*)")
        if path:
            self._widgets["sound_file"].setText(path)


class BgOcrQtWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.monitors = []
        self._running = False
        self._bridge = _UiBridge()
        self._bridge.log_requested.connect(self._append_log)
        self._bridge.invoke_requested.connect(self._run_in_ui)
        self._bridge.status_requested.connect(self._set_status)
        self._auto_bind_stop = threading.Event()
        self._auto_bind_thread = None
        self._group_order_dirty = False
        self._loading_group_editor = False
        self._current_index = 0
        self._build_ui()
        self._load_from_cfg()
        self._start_auto_bind_loop()
        QtCore.QTimer.singleShot(150, self._start)
        QtCore.QTimer.singleShot(250, self._apply_hotkeys)
        self._refresh_window_title()

    def _build_ui(self):
        self.setWindowTitle("BgOcrClick Qt")
        self.resize(1180, 860)
        self._tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self._tabs)

        self._home = self._build_home_tab()
        self._groups = self._build_groups_tab()
        self._settings = self._build_settings_tab()

        self._tabs.addTab(self._home, "首页")
        self._tabs.addTab(self._groups, "监控组")
        self._tabs.addTab(self._settings, "设置")

    def _build_home_tab(self):
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)

        status_row = QtWidgets.QHBoxLayout()
        self._status = QtWidgets.QLabel("未运行")
        self._status_dot = QtWidgets.QLabel("●")
        self._status_dot.setStyleSheet("color: #9099b8;")
        self._bound = QtWidgets.QLabel("未绑定窗口")
        self._start_btn = QtWidgets.QPushButton("开始运行")
        self._stop_btn = QtWidgets.QPushButton("停止运行")
        self._stop_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start)
        self._stop_btn.clicked.connect(self._stop)
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status)
        status_row.addStretch(1)
        status_row.addWidget(self._bound)
        status_row.addWidget(self._start_btn)
        status_row.addWidget(self._stop_btn)

        bind_row = QtWidgets.QHBoxLayout()
        self._title_filter = QtWidgets.QLineEdit(self.cfg.get("target_title", ""))
        self._title_filter.setPlaceholderText("窗口标题关键字")
        self._bind_find = QtWidgets.QPushButton("查找窗口")
        self._bind_pick = QtWidgets.QPushButton("绑定选中")
        self._bind_dialog = QtWidgets.QPushButton("选择窗口")
        self._win_list = QtWidgets.QListWidget()
        self._title_filter.returnPressed.connect(self._find_windows)
        self._bind_find.clicked.connect(self._find_windows)
        self._bind_pick.clicked.connect(self._bind_window)
        self._bind_dialog.clicked.connect(self._pick_window_dialog)
        self._win_list.itemDoubleClicked.connect(lambda _item: self._bind_window())
        bind_row.addWidget(self._title_filter)
        bind_row.addWidget(self._bind_find)
        bind_row.addWidget(self._bind_pick)
        bind_row.addWidget(self._bind_dialog)

        self._quick_table = QtWidgets.QTableWidget(0, 5)
        self._quick_table.setHorizontalHeaderLabels(["启用", "序号", "组名", "切回", "间隔"])
        self._quick_table.horizontalHeader().setStretchLastSection(True)
        self._quick_table.verticalHeader().setVisible(False)
        self._quick_table.itemChanged.connect(lambda _item: None)
        quick_btns = QtWidgets.QHBoxLayout()
        self._quick_save = QtWidgets.QPushButton("保存快捷配置")
        self._quick_refresh = QtWidgets.QPushButton("刷新列表")
        self._quick_save.clicked.connect(self._save_quick_config)
        self._quick_refresh.clicked.connect(self._refresh_quick_config)
        quick_btns.addWidget(self._quick_save)
        quick_btns.addWidget(self._quick_refresh)
        quick_btns.addStretch(1)

        self._log = QtWidgets.QTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.WidgetWidth)
        self._log.setMinimumHeight(260)
        self._log_clear = QtWidgets.QPushButton("清空日志")
        self._log_clear.clicked.connect(self._log.clear)

        layout.addLayout(status_row)
        layout.addLayout(bind_row)
        layout.addWidget(self._win_list)
        layout.addLayout(quick_btns)
        layout.addWidget(self._quick_table)
        layout.addWidget(self._log)
        layout.addWidget(self._log_clear)
        return root

    def _build_groups_tab(self):
        root = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(root)

        left = QtWidgets.QVBoxLayout()
        self._group_list = QtWidgets.QListWidget()
        self._group_list.currentRowChanged.connect(self._on_group_changed)
        self._group_add = QtWidgets.QPushButton("新增")
        self._group_del = QtWidgets.QPushButton("删除")
        self._group_up = QtWidgets.QPushButton("上移")
        self._group_down = QtWidgets.QPushButton("下移")
        self._group_save = QtWidgets.QPushButton("保存当前组")
        self._group_add.clicked.connect(self._add_group)
        self._group_del.clicked.connect(self._delete_group)
        self._group_up.clicked.connect(lambda: self._move_group(-1))
        self._group_down.clicked.connect(lambda: self._move_group(1))
        self._group_save.clicked.connect(self._save_group_config)
        left.addWidget(self._group_list)
        row = QtWidgets.QHBoxLayout()
        for btn in [self._group_add, self._group_del, self._group_up, self._group_down]:
            row.addWidget(btn)
        left.addLayout(row)
        left.addWidget(self._group_save)

        self._group_editor = _GroupEditor(self)
        self._group_editor.changed.connect(self._mark_dirty)

        layout.addLayout(left, 1)
        layout.addWidget(self._group_editor, 3)
        return root

    def _build_settings_tab(self):
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        self._settings_editor = _SettingsEditor(self)
        layout.addWidget(self._settings_editor)
        self._dep_box = QtWidgets.QPlainTextEdit()
        self._dep_box.setReadOnly(True)
        layout.addWidget(self._dep_box)
        self._save_settings_btn = QtWidgets.QPushButton("保存设置")
        self._save_settings_btn.clicked.connect(self._save_settings)
        layout.addWidget(self._save_settings_btn)
        return root

    def _load_from_cfg(self):
        self._settings_editor.load_settings(self.cfg)
        self._refresh_group_list()
        self._refresh_quick_config()
        self._refresh_dependencies()
        self._refresh_bound_label()
        if self.cfg["groups"]:
            self._group_list.setCurrentRow(0)

    def _refresh_dependencies(self):
        lines = [
            f"pywin32: {'OK' if HAS_WIN32 else 'missing'}",
            f"Pillow: {'OK' if HAS_PIL else 'missing'}",
            f"PaddleOCR: {'OK' if HAS_PADDLE else 'missing'}",
            f"pytesseract: {'OK' if HAS_TESSERACT else 'missing'}",
            f"opencv-python: {'OK' if HAS_CV2 else 'missing'}",
            f"numpy: {'OK' if HAS_NUMPY else 'missing'}",
            f"pyautogui: {'OK' if HAS_PYAUTOGUI else 'missing'}",
            f"screeninfo: {'OK' if HAS_SCREENINFO else 'missing'}",
            f"admin: {'yes' if _is_admin() else 'no'}",
        ]
        self._dep_box.setPlainText("\n".join(lines))

    def _refresh_window_title(self):
        name = self.cfg.get("target_title", "")
        self.setWindowTitle(f"BgOcrClick Qt - {name[:20] if name else '未绑定'}")

    def _refresh_bound_label(self):
        hwnd = self.cfg.get("target_hwnd", 0)
        title = self.cfg.get("target_title", "")
        self._bound.setText(f"窗口: [{hwnd}] {title}" if hwnd and title else "未绑定窗口")

    def _refresh_group_list(self):
        self._group_list.blockSignals(True)
        self._group_list.clear()
        for i, g in enumerate(self.cfg["groups"]):
            self._group_list.addItem(f"{i + 1}. {g.get('name', f'监控组{i + 1}')}")
        self._group_list.blockSignals(False)
        self._group_editor.set_chain_options([g.get("name", f"监控组{i + 1}") for i, g in enumerate(self.cfg["groups"])], self._current_index)

    def _refresh_quick_config(self):
        groups = self.cfg["groups"]
        self._quick_table.blockSignals(True)
        self._quick_table.setRowCount(len(groups))
        for i, g in enumerate(groups):
            chk = QtWidgets.QTableWidgetItem()
            chk.setCheckState(QtCore.Qt.CheckState.Checked if g.get("enabled", True) else QtCore.Qt.CheckState.Unchecked)
            self._quick_table.setItem(i, 0, chk)
            seq = QtWidgets.QTableWidgetItem(str(g.get("seq", i + 1)))
            self._quick_table.setItem(i, 1, seq)
            name = QtWidgets.QTableWidgetItem(g.get("name", f"监控组{i + 1}"))
            self._quick_table.setItem(i, 2, name)
            sink = QtWidgets.QTableWidgetItem()
            sink.setCheckState(QtCore.Qt.CheckState.Checked if g.get("sink_after_click", False) else QtCore.Qt.CheckState.Unchecked)
            self._quick_table.setItem(i, 3, sink)
            interval = QtWidgets.QTableWidgetItem(str(g.get("interval", 5)))
            self._quick_table.setItem(i, 4, interval)
        self._quick_table.blockSignals(False)

    def current_group_index(self):
        return max(0, self._current_index)

    def current_hwnd(self):
        return self.cfg.get("target_hwnd", 0)

    def _mark_dirty(self):
        if self._loading_group_editor:
            return
        self._group_order_dirty = True

    def _run_in_ui(self, fn):
        try:
            fn()
        except Exception as e:
            self.log(f"回调异常: {e}", "err")

    def after(self, ms, fn):
        threading.Timer(max(0, ms) / 1000.0, lambda: self._bridge.invoke_requested.emit(fn)).start()

    def log(self, msg, tag="info"):
        self._bridge.log_requested.emit(msg, tag)

    def _append_log(self, msg, tag="info"):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        color = {
            "ok": "#2ecc71",
            "warn": "#f39c12",
            "err": "#e74c3c",
            "info": "#8fc6ff",
        }.get(tag, "#e8eaf0")
        self._log.append(f'<span style="color:{color}">{line}</span>')
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _set_status(self, running):
        self._status.setText("运行中" if running else "未运行")
        self._status_dot.setStyleSheet("color: #2ecc71;" if running else "color: #9099b8;")
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

    def _play_if(self, event):
        cfg = self.cfg
        if not cfg.get("sound_enabled", False):
            return
        sf = cfg.get("sound_file", "").strip()
        if not sf:
            return
        mapping = {
            "match": "sound_on_match",
            "popup_match": "sound_on_popup_match",
            "no_match": "sound_on_no_match",
        }
        if cfg.get(mapping.get(event, ""), False):
            _play_sound(sf)

    def _refresh_monitor_state(self):
        self._refresh_bound_label()
        self._refresh_window_title()
        self._refresh_group_list()
        self._refresh_quick_config()
        self._refresh_dependencies()

    def _find_windows(self):
        self._win_list.clear()
        key = self._title_filter.text().strip().lower()
        for hwnd, title in list_windows():
            if key and key not in title.lower():
                continue
            self._win_list.addItem(f"[{hwnd}] {title}")
        self.log(f"找到 {self._win_list.count()} 个窗口", "info")

    def _bind_selected_window(self, hwnd, title):
        self.cfg["target_hwnd"] = hwnd
        self.cfg["target_title"] = title
        self._title_filter.setText(title)
        self._refresh_monitor_state()
        save_config(self.cfg)
        self.log(f"宸茬粦瀹氱獥鍙? [{hwnd}] {title}", "ok")

    def _pick_window_dialog(self):
        dlg = _WindowPickerDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selected:
            hwnd, title = dlg.selected
            self._bind_selected_window(hwnd, title)

    def _bind_window(self):
        row = self._win_list.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择窗口")
            return
        key = self._title_filter.text().strip().lower()
        windows = []
        for hwnd, title in list_windows():
            if key and key not in title.lower():
                continue
            windows.append((hwnd, title))
        if row >= len(windows):
            return
        hwnd, title = windows[row]
        self._bind_selected_window(hwnd, title)

    def _load_group_editor(self, index):
        self._loading_group_editor = True
        try:
            self._group_editor.load_group(self.cfg["groups"][index], index)
            self._group_editor.set_chain_options(
                [g.get("name", f"监控组{i + 1}") for i, g in enumerate(self.cfg["groups"])],
                index,
            )
        finally:
            self._loading_group_editor = False
            self._group_order_dirty = False

    def _on_group_changed(self, index):
        if index < 0 or index >= len(self.cfg["groups"]):
            return
        if self._current_index == index and not self._group_order_dirty:
            self._load_group_editor(index)
            return
        self._save_current_group()
        self._current_index = index
        self._load_group_editor(index)

    def _save_current_group(self):
        if not self.cfg["groups"]:
            return
        idx = min(max(self._current_index, 0), len(self.cfg["groups"]) - 1)
        self.cfg["groups"][idx] = self._group_editor.dump_group(idx)
        self._group_order_dirty = False

    def _save_group_config(self):
        self._save_current_group()
        save_config(self.cfg)
        self._refresh_group_list()
        self._refresh_quick_config()
        self._group_list.setCurrentRow(min(self._current_index, len(self.cfg["groups"]) - 1))
        self.log("监控组配置已保存", "ok")

    def _add_group(self):
        self._save_current_group()
        self.cfg["groups"].append(_copy_group({"name": f"监控组{len(self.cfg['groups']) + 1}"}))
        self._current_index = len(self.cfg["groups"]) - 1
        self._refresh_group_list()
        self._group_list.setCurrentRow(self._current_index)
        save_config(self.cfg)

    def _delete_group(self):
        idx = self._group_list.currentRow()
        if idx < 0:
            return
        if QtWidgets.QMessageBox.question(self, "确认", f"删除监控组{idx + 1}？") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._save_current_group()
        del self.cfg["groups"][idx]
        for g in self.cfg["groups"]:
            ct = g.get("chain_target", -1)
            if ct == idx:
                g["chain_target"] = -1
                g["chain_enabled"] = False
            elif ct > idx:
                g["chain_target"] = ct - 1
        self._current_index = max(0, idx - 1)
        self._refresh_group_list()
        self._refresh_quick_config()
        if self.cfg["groups"]:
            self._group_list.setCurrentRow(self._current_index)
        save_config(self.cfg)

    def _move_group(self, direction):
        idx = self._group_list.currentRow()
        if idx < 0:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.cfg["groups"]):
            return
        self._save_current_group()
        groups = self.cfg["groups"]
        groups[idx], groups[new_idx] = groups[new_idx], groups[idx]
        self._current_index = new_idx
        self._refresh_group_list()
        self._refresh_quick_config()
        self._group_list.setCurrentRow(new_idx)
        save_config(self.cfg)

    def _save_quick_config(self):
        self._save_current_group()
        seqs = []
        for row in range(self._quick_table.rowCount()):
            try:
                seqs.append(int(self._quick_table.item(row, 1).text()))
            except Exception:
                QtWidgets.QMessageBox.critical(self, "错误", f"第{row + 1}行序号不是有效整数")
                return
        if len(seqs) != len(set(seqs)):
            QtWidgets.QMessageBox.critical(self, "序号重复", "存在重复序号，请修改后保存")
            return
        for row, g in enumerate(self.cfg["groups"]):
            g["enabled"] = self._quick_table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked
            g["name"] = self._quick_table.item(row, 2).text().strip() or g.get("name", "")
            g["sink_after_click"] = self._quick_table.item(row, 3).checkState() == QtCore.Qt.CheckState.Checked
            try:
                g["interval"] = int(self._quick_table.item(row, 4).text())
            except Exception:
                pass
        order = sorted(range(len(seqs)), key=lambda i: seqs[i])
        self.cfg["groups"] = [self.cfg["groups"][i] for i in order]
        save_config(self.cfg)
        self._refresh_group_list()
        self._refresh_quick_config()
        self._group_list.setCurrentRow(min(self._current_index, len(self.cfg["groups"]) - 1))
        self.log("快捷配置已保存", "ok")

    def _save_settings(self):
        self._save_current_group()
        self.cfg.update(self._settings_editor.dump_settings())
        save_config(self.cfg)
        self._apply_hotkeys()
        self._refresh_monitor_state()
        self.log("设置已保存", "ok")
        QtWidgets.QMessageBox.information(self, "保存成功", "设置已保存")

    def _apply_hotkeys(self):
        try:
            import keyboard as _kb
            try:
                _kb.unhook_all_hotkeys()
            except Exception:
                pass
            hk_s = self.cfg.get("hotkey_start", "")
            hk_t = self.cfg.get("hotkey_stop", "")
            if hk_s:
                _kb.add_hotkey(hk_s, lambda: self.after(0, self._start))
            if hk_t:
                _kb.add_hotkey(hk_t, lambda: self.after(0, self._stop))
            if hk_s or hk_t:
                self.log(f"热键已注册: start={hk_s.upper() or '无'} stop={hk_t.upper() or '无'}", "ok")
        except ImportError:
            self.log("keyboard 未安装，快捷键不可用", "warn")
        except Exception as e:
            self.log(f"快捷键注册失败: {e}", "warn")

    def _uses_paddle(self):
        for g in self.cfg["groups"]:
            if not g.get("enabled", True):
                continue
            if g.get("type", "ocr") == "ocr" and g.get("ocr_engine", "paddle") == "paddle":
                return True
            for tmpl in g.get("popup_templates", []):
                if tmpl.get("type", "ocr") == "ocr" and tmpl.get("ocr_engine", "paddle") == "paddle":
                    return True
        return False

    def _missing_runtime_dependency(self):
        for g_index, g in enumerate(self.cfg["groups"], start=1):
            if not g.get("enabled", True):
                continue
            missing = self._missing_match_dependency(g, f"group {g_index}")
            if missing:
                return missing
            for t_index, tmpl in enumerate(g.get("popup_templates", []), start=1):
                missing = self._missing_match_dependency(tmpl, f"group {g_index} popup {t_index}")
                if missing:
                    return missing
        return None

    def _missing_match_dependency(self, item, label):
        kind = item.get("type", "ocr")
        if kind == "ocr":
            engine = item.get("ocr_engine", "paddle")
            if engine == "paddle" and not HAS_PADDLE:
                return f"{label} uses PaddleOCR, please install paddlepaddle/paddleocr"
            if engine == "tesseract" and not HAS_TESSERACT:
                return f"{label} uses Tesseract, please install pytesseract"
        elif kind == "image" and (not HAS_CV2 or not HAS_NUMPY):
            return f"{label} uses image template matching, please install opencv-python and numpy"
        elif kind == "color" and not HAS_NUMPY:
            return f"{label} uses color matching, please install numpy"
        return None

    def _start(self):
        if self._running:
            return
        self._save_current_group()
        self.cfg.update(self._settings_editor.dump_settings())
        save_config(self.cfg)
        if not self.cfg.get("target_hwnd"):
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        enabled = [g for g in self.cfg["groups"] if g.get("enabled", True)]
        if not enabled:
            QtWidgets.QMessageBox.warning(self, "提示", "没有已启用的监控组")
            return
        missing = self._missing_runtime_dependency()
        if missing:
            QtWidgets.QMessageBox.warning(self, "缺少依赖", missing)
            return
        if self._uses_paddle():
            exe = self.cfg.get("paddle_exe_path", "").strip()
            if not exe or not os.path.exists(exe):
                QtWidgets.QMessageBox.warning(self, "提示", "请先配置 PaddleOCR-json.exe 路径")
                return
            try:
                self.log("正在启动 PaddleOCR-json 引擎...", "info")
                _paddle_engine.start(exe)
                self.log("PaddleOCR-json 引擎就绪", "ok")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "引擎启动失败", str(e))
                return
        self._running = True
        self.monitors = [GroupMonitor(self, i) for i in range(len(self.cfg["groups"]))]
        for i, g in enumerate(self.cfg["groups"]):
            if g.get("enabled", True):
                self.monitors[i].start()
        self._set_status(True)
        self.log(f"启动 {len(enabled)} 个监控组", "ok")

    def _stop(self):
        if not self._running and not self.monitors:
            return
        self._running = False
        for m in self.monitors:
            m.stop()
        self.monitors.clear()
        try:
            _paddle_engine.stop()
        except Exception:
            pass
        self._set_status(False)
        self.log("已停止", "warn")

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
                            self.after(0, lambda h=hwnd, t=title: self.log(f"[自动绑定] 已绑定进程 {proc} 的窗口 [{h}] {t}", "ok"))
                    elif len(wins) > 1:
                        cur_hwnd = self.cfg.get("target_hwnd", 0)
                        if not cur_hwnd:
                            self.after(0, lambda n=len(wins), p=proc: self.log(f"[自动绑定] 进程 {p} 有 {n} 个窗口，请手动绑定", "warn"))
            except Exception as e:
                try:
                    with open(LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"[{time.strftime('%H:%M:%S')}] [自动绑定] 异常: {e}\n")
                except Exception:
                    pass
            self._auto_bind_stop.wait(3.0)

    def closeEvent(self, event):
        self._on_close()
        event.accept()

    def _on_close(self):
        self._stop()
        self._save_current_group()
        try:
            self.cfg.update(self._settings_editor.dump_settings())
        except Exception:
            pass
        if hasattr(self, "_auto_bind_stop"):
            self._auto_bind_stop.set()
        try:
            import keyboard as _kb
            _kb.unhook_all_hotkeys()
        except Exception:
            pass
        self.cfg["window_geometry"] = f"{self.width()}x{self.height()}"
        save_config(self.cfg)


def _launch_qt():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if not HAS_WIN32 or not HAS_PIL:
        QtWidgets.QMessageBox.critical(
            None,
            "缺少依赖",
            "缺少 pywin32 或 Pillow，无法启动 Qt 版界面",
        )
        return None
    if not _is_admin():
        ans = QtWidgets.QMessageBox.question(
            None,
            "权限提示",
            "当前非管理员权限。\nPrintWindow 截图在被遮挡时需要管理员权限。\n是否以管理员权限重启？",
        )
        if ans == QtWidgets.QMessageBox.StandardButton.Yes:
            _relaunch_as_admin()
    win = BgOcrQtWindow()
    geom = win.cfg.get("window_geometry", "1180x860")
    try:
        w, h = [int(x) for x in geom.lower().split("x", 1)]
        win.resize(w, h)
    except Exception:
        pass
    win.show()
    return app.exec()


def main(fallback_to_tk: bool = True):
    try:
        return _launch_qt()
    except Exception as e:
        if not fallback_to_tk:
            raise
        try:
            from bg_ocr_click import _launch_tk

            return _launch_tk(str(e))
        except Exception:
            raise


if __name__ == "__main__":
    main()
