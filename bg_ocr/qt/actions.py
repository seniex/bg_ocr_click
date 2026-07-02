from __future__ import annotations

import copy
import json

from PyQt6 import QtCore, QtWidgets

from bg_ocr.action_runtime import ACTION_DEFAULTS, _CLICK_LABELS, _CLICK_TYPES, _KEY_ACTIONS, _KEY_HINTS, _POS_MODES
from bg_ocr.capture import capture_full_preview


def _copy_action(kind="mouse", data=None):
    base = copy.deepcopy(ACTION_DEFAULTS.get(kind, ACTION_DEFAULTS["mouse"]))
    if data:
        base.update(data)
    return base


def _wrap(layout):
    w = QtWidgets.QWidget()
    w.setLayout(layout)
    return w


class _FocusWheelSpinBox(QtWidgets.QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class _FocusWheelDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class _FocusWheelComboBox(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta:
            step = -1 if delta > 0 else 1
            self.setCurrentIndex(max(0, min(self.count() - 1, self.currentIndex() + step)))
            event.accept()
            return
        super().wheelEvent(event)


class _MappedComboBox(_FocusWheelComboBox):
    def __init__(self, value_to_label, parent=None):
        super().__init__(parent)
        self._value_to_label = dict(value_to_label)
        self._label_to_value = {label: value for value, label in self._value_to_label.items()}
        self.addItems(self._value_to_label.values())

    def setCurrentText(self, text):
        label = self._value_to_label.get(text, text)
        super().setCurrentText(label)

    def currentValue(self):
        return self._label_to_value.get(self.currentText(), self.currentText())


class _ActionJsonDialog(QtWidgets.QDialog):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setObjectName("actionJsonDialog")
        self.setWindowTitle("编辑动作序列 JSON")
        self.actions = [_copy_action(a.get("kind", "mouse"), a) for a in (actions or []) if isinstance(a, dict)]

        layout = QtWidgets.QVBoxLayout(self)
        self._edit = QtWidgets.QPlainTextEdit()
        self._edit.setObjectName("actionJsonEditor")
        self._edit.setPlainText(json.dumps(self.actions, ensure_ascii=False, indent=2))
        layout.addWidget(self._edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        try:
            value = json.loads(self._edit.toPlainText() or "[]")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "JSON 错误", str(exc))
            return
        if not isinstance(value, list):
            QtWidgets.QMessageBox.critical(self, "JSON 错误", "动作序列必须是列表")
            return
        self.actions = [_copy_action(a.get("kind", "mouse"), a) for a in value if isinstance(a, dict)]
        self.accept()


class _LegacyActionSequenceWidget(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    _VISIBLE_FIELDS = {
        "mouse": ["pre_delay", "pos_mode", "offset_x", "offset_y", "click_type", "count", "interval"],
        "key": ["pre_delay", "key", "action", "count", "interval"],
        "text": ["pre_delay", "text", "interval"],
        "delay": ["seconds"],
        "scroll": ["abs_x", "abs_y", "direction", "clicks", "multiplier"],
    }

    def __init__(self, actions=None, parent=None, image_picker_cls=None, screen_point_picker_cls=None):
        super().__init__(parent)
        self._actions = [_copy_action(a.get("kind", "mouse"), a) for a in (actions or []) if isinstance(a, dict)]
        self._current = -1
        self._loading = False
        self._syncing_drop = False
        self._image_picker_cls_override = image_picker_cls
        self._screen_point_picker_cls_override = screen_point_picker_cls
        self._build()
        self._refresh_list()
        if self._actions:
            self._list.setCurrentRow(0)

    def _combo(self, values=None, editable=False):
        cb = _FocusWheelComboBox()
        cb.setEditable(editable)
        if values:
            cb.addItems(values)
        return cb

    def _mapped_combo(self, value_to_label):
        return _MappedComboBox(value_to_label)

    def _spin(self, minimum, maximum, value):
        sb = _FocusWheelSpinBox()
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _dspin(self, minimum, maximum, value):
        sb = _FocusWheelDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)

        toolbar = QtWidgets.QHBoxLayout()
        for kind, text in [
            ("mouse", "鼠标"),
            ("key", "按键"),
            ("delay", "延迟"),
            ("scroll", "滚轮"),
            ("text", "文本"),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(lambda _checked=False, k=kind: self._add_action(k))
            toolbar.addWidget(btn)
        self._json_btn = QtWidgets.QPushButton("JSON")
        self._json_btn.clicked.connect(self._edit_json)
        toolbar.addWidget(self._json_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._list = QtWidgets.QListWidget()
        self._list.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self._list.currentRowChanged.connect(self._change_row)
        self._list.model().rowsMoved.connect(lambda *_args: self._sync_actions_from_list_order())
        layout.addWidget(self._list)

        self._fields = {}
        self._fields["pre_delay"] = self._dspin(0, 3600, 0)
        self._fields["pos_mode"] = self._combo([key for key, _label in _POS_MODES])
        self._fields["offset_x"] = self._spin(-100000, 100000, 0)
        self._fields["offset_y"] = self._spin(-100000, 100000, 0)
        self._fields["abs_x"] = self._spin(-100000, 100000, 0)
        self._fields["abs_y"] = self._spin(-100000, 100000, 0)
        self._fields["click_type"] = self._combo(_CLICK_TYPES)
        self._fields["count"] = self._spin(1, 999, 1)
        self._fields["interval"] = self._dspin(0, 3600, 0.1)
        self._fields["key"] = self._combo(_KEY_HINTS, editable=True)
        self._fields["action"] = self._combo([key for key, _label in _KEY_ACTIONS])
        self._fields["text"] = QtWidgets.QLineEdit()
        self._fields["seconds"] = self._dspin(0, 3600, 0.5)
        self._fields["direction"] = self._combo(["down", "up"])
        self._fields["clicks"] = self._spin(1, 999, 1)
        self._fields["multiplier"] = self._dspin(0.01, 100, 1.0)
        self._pick_window_btn = QtWidgets.QPushButton("窗口取点")
        self._pick_screen_btn = QtWidgets.QPushButton("屏幕取点")
        self._pick_window_btn.clicked.connect(self._pick_window_coord)
        self._pick_screen_btn.clicked.connect(self._pick_screen_coord)

        labels = [
            ("前置等待", "pre_delay"),
            ("位置", "pos_mode"),
            ("偏移X", "offset_x"),
            ("偏移Y", "offset_y"),
            ("坐标X", "abs_x"),
            ("坐标Y", "abs_y"),
            ("方式", "click_type"),
            ("次数", "count"),
            ("间隔", "interval"),
            ("按键", "key"),
            ("按键动作", "action"),
            ("文本", "text"),
            ("等待秒数", "seconds"),
            ("方向", "direction"),
            ("格数", "clicks"),
            ("倍率", "multiplier"),
        ]
        config_scroll = QtWidgets.QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        config_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._config_row = QtWidgets.QWidget()
        self._config_row.setObjectName("actionSequenceConfigRow")
        config_layout = QtWidgets.QHBoxLayout(self._config_row)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(8)
        self._field_rows = {}
        for label, key in labels:
            row = QtWidgets.QWidget(self._config_row)
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            caption = QtWidgets.QLabel(label)
            caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(caption)
            row_layout.addWidget(self._fields[key])
            config_layout.addWidget(row)
            self._field_rows[key] = row

        pick_row = QtWidgets.QHBoxLayout()
        pick_row.addWidget(self._pick_window_btn)
        pick_row.addWidget(self._pick_screen_btn)
        self._pick_row = _wrap(pick_row)
        self._pick_row.setParent(self._config_row)
        config_layout.addWidget(self._pick_row)
        config_layout.addStretch(1)
        config_scroll.setWidget(self._config_row)

        for widget in self._fields.values():
            for signal_name in ("currentIndexChanged", "textChanged", "valueChanged"):
                try:
                    getattr(widget, signal_name).connect(self._save_current)
                except Exception:
                    pass

        buttons = QtWidgets.QHBoxLayout()
        self._delete_btn = QtWidgets.QPushButton("删除")
        self._up_btn = QtWidgets.QPushButton("上移")
        self._down_btn = QtWidgets.QPushButton("下移")
        self._delete_btn.clicked.connect(self._delete_action)
        self._up_btn.clicked.connect(lambda: self._move_action(-1))
        self._down_btn.clicked.connect(lambda: self._move_action(1))
        for btn in [self._delete_btn, self._up_btn, self._down_btn]:
            buttons.addWidget(btn)
        buttons.addStretch(1)

        layout.addLayout(buttons)
        layout.addWidget(config_scroll)

    def _owner_window(self):
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "current_hwnd") and hasattr(parent, "cfg"):
                return parent
            parent = parent.parent()
        return None

    def _refresh_list(self):
        current = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for i, action in enumerate(self._actions):
            item = QtWidgets.QListWidgetItem(f"{i + 1}. {self._action_label(action)}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, action)
            self._list.addItem(item)
        self._list.blockSignals(False)
        if 0 <= current < self._list.count():
            self._list.setCurrentRow(current)

    def _action_label(self, action):
        kind = action.get("kind", "mouse")
        if kind == "mouse":
            return f"鼠标 {action.get('pos_mode', 'match_center')} {action.get('click_type', 'single')}"
        if kind == "key":
            return f"按键 {action.get('action', 'press')} {action.get('key', '')}"
        if kind == "text":
            return f"文本 {str(action.get('text', ''))[:20]}"
        if kind == "delay":
            return f"延迟 {action.get('seconds', 0.5)}s"
        if kind == "scroll":
            return f"滚轮 {action.get('direction', 'down')} {action.get('clicks', 1)}"
        return kind

    def _change_row(self, row):
        if self._loading:
            return
        self._save_current()
        self._current = row
        if 0 <= row < len(self._actions):
            self._load_action(self._actions[row])

    def _set_combo(self, key, value):
        widget = self._fields[key]
        text = "" if value is None else str(value)
        if widget.findText(text) < 0:
            widget.addItem(text)
        widget.setCurrentText(text)

    def _load_action(self, action):
        kind = action.get("kind", "mouse")
        self._loading = True
        self._fields["pre_delay"].setValue(float(action.get("pre_delay", 0.0)))
        self._set_combo("pos_mode", action.get("pos_mode", "match_center"))
        self._fields["offset_x"].setValue(int(action.get("offset_x", 0)))
        self._fields["offset_y"].setValue(int(action.get("offset_y", 0)))
        self._fields["abs_x"].setValue(int(action.get("abs_x", 0)))
        self._fields["abs_y"].setValue(int(action.get("abs_y", 0)))
        self._set_combo("click_type", action.get("click_type", "single"))
        self._fields["count"].setValue(int(action.get("count", 1)))
        self._fields["interval"].setValue(float(action.get("interval", 0.1)))
        self._set_combo("key", action.get("key", ""))
        self._set_combo("action", action.get("action", "press"))
        self._fields["text"].setText(action.get("text", ""))
        self._fields["seconds"].setValue(float(action.get("seconds", 0.5)))
        self._set_combo("direction", action.get("direction", "down"))
        self._fields["clicks"].setValue(int(action.get("clicks", 1)))
        self._fields["multiplier"].setValue(float(action.get("multiplier", 1.0)))
        self._update_field_visibility(kind)
        self._loading = False

    def _update_field_visibility(self, kind):
        visible = set(self._VISIBLE_FIELDS.get(kind, []))
        for key, row in self._field_rows.items():
            row.setVisible(key in visible)
        can_pick_point = kind in {"mouse", "scroll"}
        self._pick_window_btn.setVisible(can_pick_point)
        self._pick_screen_btn.setVisible(can_pick_point)
        self._pick_row.setVisible(can_pick_point)

    def _save_current(self):
        if self._loading or not (0 <= self._current < len(self._actions)):
            return
        old = self._actions[self._current]
        kind = old.get("kind", "mouse")
        if kind not in ACTION_DEFAULTS:
            action = copy.deepcopy(old)
            self._actions[self._current] = action
            return

        action = _copy_action(kind, old)
        action["kind"] = kind
        if kind != "delay":
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
            item.setData(QtCore.Qt.ItemDataRole.UserRole, action)

    def _add_action(self, kind):
        self._save_current()
        self._actions.append(_copy_action(kind))
        self._refresh_list()
        self._list.setCurrentRow(len(self._actions) - 1)
        self.changed.emit()

    def _delete_action(self):
        row = self._list.currentRow()
        if row < 0:
            return
        del self._actions[row]
        self._current = -1
        self._refresh_list()
        if self._actions:
            self._list.setCurrentRow(min(row, len(self._actions) - 1))
        self.changed.emit()

    def _move_action(self, direction):
        row = self._list.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= len(self._actions):
            return
        self._save_current()
        self._actions[row], self._actions[new_row] = self._actions[new_row], self._actions[row]
        self._refresh_list()
        self._list.setCurrentRow(new_row)
        self.changed.emit()

    def _sync_actions_from_list_order(self):
        if self._syncing_drop:
            return
        ordered = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            action = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(action, dict):
                ordered.append(action)
        if len(ordered) != len(self._actions):
            return
        self._syncing_drop = True
        self._actions = ordered
        self._refresh_list()
        self._syncing_drop = False
        self.changed.emit()

    def _edit_json(self):
        self._save_current()
        dlg = _ActionJsonDialog(self._actions, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.set_actions(dlg.actions)
            self.changed.emit()

    def set_actions(self, actions):
        self._actions = [_copy_action(a.get("kind", "mouse"), a) for a in (actions or []) if isinstance(a, dict)]
        self._current = -1
        self._refresh_list()
        if self._actions:
            self._list.setCurrentRow(0)

    def _set_abs_coord(self, x, y):
        self._fields["abs_x"].setValue(int(x))
        self._fields["abs_y"].setValue(int(y))
        self._save_current()
        self.changed.emit()

    def _get_image_picker_cls(self):
        if self._image_picker_cls_override is not None:
            return self._image_picker_cls_override
        from bg_ocr.qt.pickers import _ImagePickerDialog
        return _ImagePickerDialog

    def _get_screen_point_picker_cls(self):
        if self._screen_point_picker_cls_override is not None:
            return self._screen_point_picker_cls_override
        from bg_ocr.qt.pickers import _ScreenPointPickerDialog
        return _ScreenPointPickerDialog

    def _current_kind(self):
        if 0 <= self._current < len(self._actions):
            return self._actions[self._current].get("kind", "mouse")
        return "mouse"

    def _pick_window_coord(self):
        kind = self._current_kind()
        if kind not in {"mouse", "scroll"}:
            QtWidgets.QMessageBox.information(self, "提示", "窗口相对点只用于鼠标或滚轮动作")
            return
        owner = self._owner_window()
        if owner is None or not owner.current_hwnd():
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(owner.current_hwnd(), owner.cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截取目标窗口")
            return
        dlg = self._get_image_picker_cls()(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            if kind == "mouse":
                self._fields["pos_mode"].setCurrentText("window")
            self._set_abs_coord(x, y)

    def _pick_screen_coord(self):
        dlg = self._get_screen_point_picker_cls()(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.point:
            x, y = dlg.point
            if self._current_kind() == "mouse":
                self._fields["pos_mode"].setCurrentText("screen")
            self._set_abs_coord(x, y)

    @property
    def actions(self):
        self._save_current()
        return self._actions


class _ActionRowHandle(QtWidgets.QLabel):
    def __init__(self, text, editor, row_index, parent=None):
        super().__init__(text, parent)
        self._editor = editor
        self._row_index = row_index
        self._drag_start_pos = None
        self.setObjectName("actionSequenceDragHandle")
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._editor._select_row(self._row_index)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            point = self.mapTo(self._editor._config_row, event.position().toPoint())
            target = self._editor._row_index_at_y(point.y())
            self._drag_start_pos = None
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            self._editor._move_action_to(self._row_index, target)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _ActionSequenceWidget(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()
    _MIN_EDITOR_HEIGHT = 400

    _VISIBLE_FIELDS = {
        "mouse": [
            "pre_delay",
            "pos_mode",
            "offset_x",
            "offset_y",
            "abs_x",
            "abs_y",
            "click_type",
            "count",
            "interval",
        ],
        "key": ["pre_delay", "key", "action", "count", "interval"],
        "text": ["pre_delay", "text", "interval"],
        "delay": ["seconds"],
        "scroll": ["abs_x", "abs_y", "direction", "clicks", "multiplier"],
    }
    _KIND_LABELS = {
        "mouse": "\u9f20\u6807",
        "key": "\u6309\u952e",
        "text": "\u6587\u672c",
        "delay": "\u5ef6\u8fdf",
        "scroll": "\u6eda\u8f6e",
    }
    _KIND_BADGES = {
        "mouse": "\u9f20",
        "key": "\u952e",
        "text": "\u6587",
        "delay": "\u5ef6",
        "scroll": "\u6eda",
    }
    _FIELD_LABELS = {
        "pre_delay": "\u524d\u7f6e\u7b49\u5f85",
        "pos_mode": "\u4f4d\u7f6e",
        "offset_x": "\u504f\u79fbX",
        "offset_y": "\u504f\u79fbY",
        "abs_x": "\u5750\u6807X",
        "abs_y": "\u5750\u6807Y",
        "click_type": "\u65b9\u5f0f",
        "count": "\u6b21\u6570",
        "interval": "\u95f4\u9694",
        "key": "\u6309\u952e",
        "action": "\u6309\u952e\u52a8\u4f5c",
        "text": "\u6587\u672c",
        "seconds": "\u7b49\u5f85\u79d2\u6570",
        "direction": "\u65b9\u5411",
        "clicks": "\u683c\u6570",
        "multiplier": "\u500d\u7387",
    }
    _POS_LABELS_BY_VALUE = dict(_POS_MODES)
    _POS_VALUES_BY_LABEL = {label: value for value, label in _POS_MODES}
    _CLICK_VALUES_BY_LABEL = {label: value for value, label in _CLICK_LABELS.items()}

    def __init__(self, actions=None, parent=None, image_picker_cls=None, screen_point_picker_cls=None):
        super().__init__(parent)
        self.setObjectName("actionSequenceEditor")
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self._actions = [_copy_action(a.get("kind", "mouse"), a) for a in (actions or []) if isinstance(a, dict)]
        self._current = 0
        self._loading = False
        self._image_picker_cls_override = image_picker_cls
        self._screen_point_picker_cls_override = screen_point_picker_cls
        self._max_visible_rows = 10
        self._row_height_limit = 0
        self._build()
        self.set_actions(self._actions)

    def event(self, event):
        result = super().event(event)
        if event.type() == QtCore.QEvent.Type.StyleChange and hasattr(self, "_scroll"):
            self._update_scroll_height()
        return result

    def _base_editor_height(self):
        return max(self._MIN_EDITOR_HEIGHT, self.minimumHeight())

    def _combo(self, values=None, editable=False):
        cb = _FocusWheelComboBox()
        cb.setEditable(editable)
        if values:
            cb.addItems(values)
        return cb

    def _mapped_combo(self, value_to_label):
        return _MappedComboBox(value_to_label)

    def _spin(self, minimum, maximum, value):
        sb = _FocusWheelSpinBox()
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _dspin(self, minimum, maximum, value):
        sb = _FocusWheelDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QtWidgets.QHBoxLayout()
        for kind in ["mouse", "key", "delay", "scroll", "text"]:
            btn = QtWidgets.QPushButton(self._KIND_LABELS[kind])
            btn.clicked.connect(lambda _checked=False, k=kind: self._add_action(k))
            toolbar.addWidget(btn)
        self._json_btn = QtWidgets.QPushButton("JSON")
        self._json_btn.clicked.connect(self._edit_json)
        toolbar.addWidget(self._json_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._rows = []
        self._row_fields = []
        self._fields = {}
        self._field_rows = {}
        self._pick_row = None
        self._config_row = QtWidgets.QWidget()
        self._config_row.setObjectName("actionSequenceConfigRow")
        self._config_row.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self._rows_layout = QtWidgets.QVBoxLayout(self._config_row)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch(1)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setObjectName("actionSequenceScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setWidget(self._config_row)
        layout.addWidget(self._scroll)

    def _owner_window(self):
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "current_hwnd") and hasattr(parent, "cfg"):
                return parent
            parent = parent.parent()
        return None

    def _make_field(self, key):
        if key == "pre_delay":
            return self._dspin(0, 3600, 0)
        if key == "pos_mode":
            return self._mapped_combo(self._POS_LABELS_BY_VALUE)
        if key in {"offset_x", "offset_y", "abs_x", "abs_y"}:
            return self._spin(-100000, 100000, 0)
        if key == "click_type":
            return self._mapped_combo({key: _CLICK_LABELS[key] for key in _CLICK_TYPES})
        if key == "count":
            return self._spin(1, 999, 1)
        if key == "interval":
            return self._dspin(0, 3600, 0.1)
        if key == "key":
            return self._combo(_KEY_HINTS, editable=True)
        if key == "action":
            return self._combo([key for key, _label in _KEY_ACTIONS])
        if key == "text":
            return QtWidgets.QLineEdit()
        if key == "seconds":
            return self._dspin(0, 3600, 0.5)
        if key == "direction":
            return self._combo(["down", "up"])
        if key == "clicks":
            return self._spin(1, 999, 1)
        if key == "multiplier":
            return self._dspin(0.01, 100, 1.0)
        raise KeyError(key)

    def _field_value(self, fields, key):
        widget = fields[key]
        if isinstance(widget, _MappedComboBox):
            return widget.currentValue()
        if isinstance(widget, QtWidgets.QComboBox):
            text = widget.currentText()
            return text
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return widget.value()
        return None

    def _set_combo(self, widget, value):
        text = "" if value is None else str(value)
        if widget.findText(text) < 0:
            widget.addItem(text)
        widget.setCurrentText(text)

    def _set_field_value(self, fields, key, value):
        widget = fields[key]
        if isinstance(widget, QtWidgets.QComboBox):
            if key == "pos_mode":
                value = self._POS_LABELS_BY_VALUE.get(value, value)
            elif key == "click_type":
                value = _CLICK_LABELS.get(value, value)
            self._set_combo(widget, value)
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText("" if value is None else str(value))
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value))

    def _mouse_position_mode(self, fields):
        widget = fields.get("pos_mode")
        if isinstance(widget, _MappedComboBox):
            return widget.currentValue()
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        return "match_center"

    def _update_mouse_position_fields(self, row_index):
        if not (0 <= row_index < len(self._rows)):
            return
        row = self._rows[row_index]
        if row.get("kind") != "mouse":
            return
        fields = self._row_fields[row_index]
        mode = self._mouse_position_mode(fields)
        show_offset = mode == "offset"
        show_abs = mode in {"screen", "window"}
        for key in ("offset_x", "offset_y"):
            holder = row["field_rows"].get(key)
            if holder is not None:
                holder.setVisible(show_offset)
        for key in ("abs_x", "abs_y"):
            holder = row["field_rows"].get(key)
            if holder is not None:
                holder.setVisible(show_abs)
        can_pick = mode in {"window", "screen"}
        pick_button = row.get("pick_button")
        if pick_button is not None:
            pick_button.setVisible(can_pick)
        pick_row = row.get("pick_row")
        if pick_row is not None:
            pick_row.setVisible(can_pick)

    def _row_action_from_fields(self, row_index):
        old = self._actions[row_index]
        kind = old.get("kind", "mouse")
        if kind not in ACTION_DEFAULTS:
            return copy.deepcopy(old)

        fields = self._row_fields[row_index]
        action = _copy_action(kind, old)
        action["kind"] = kind
        def value(key):
            if key in fields:
                return self._field_value(fields, key)
            if key in old:
                return old[key]
            if key == "pre_delay":
                return 0.0
            if key == "interval":
                return action.get(key, 0.1)
            return action.get(key)

        if kind != "delay":
            action["pre_delay"] = value("pre_delay")
        if kind == "mouse":
            action.update({
                "pos_mode": value("pos_mode"),
                "offset_x": value("offset_x"),
                "offset_y": value("offset_y"),
                "abs_x": value("abs_x"),
                "abs_y": value("abs_y"),
                "click_type": value("click_type"),
                "count": value("count"),
                "interval": value("interval"),
            })
        elif kind == "key":
            action.update({
                "key": value("key"),
                "action": value("action"),
                "count": value("count"),
                "interval": value("interval"),
            })
        elif kind == "text":
            action.update({
                "text": value("text"),
                "interval": value("interval"),
            })
        elif kind == "delay":
            action["seconds"] = value("seconds")
        elif kind == "scroll":
            action.update({
                "abs_x": value("abs_x"),
                "abs_y": value("abs_y"),
                "direction": value("direction"),
                "clicks": value("clicks"),
                "interval": value("interval"),
                "multiplier": value("multiplier"),
            })
        return action

    def _sync_action_from_row(self, row_index, emit=True):
        if self._loading or not (0 <= row_index < len(self._actions)):
            return
        self._actions[row_index] = self._row_action_from_fields(row_index)
        if row_index == self._current:
            self._fields = self._row_fields[row_index]
        if emit:
            self.changed.emit()

    def _build_row(self, index, action):
        kind = action.get("kind", "mouse")
        container = QtWidgets.QWidget(self._config_row)
        container.setObjectName("actionSequenceInlineRow")
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        row_layout = QtWidgets.QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        badge = self._KIND_BADGES.get(kind, self._KIND_LABELS.get(kind, kind))
        handle = _ActionRowHandle(f"{index + 1}.[{badge}]", self, index, container)
        row_layout.addWidget(handle)

        fields = {}
        field_rows = {}
        pick_row = None
        pick_button = None

        def add_pick_row():
            nonlocal pick_row, pick_button
            if pick_row is not None or kind not in {"mouse", "scroll"}:
                return
            pick_row = QtWidgets.QWidget(container)
            pick_layout = QtWidgets.QHBoxLayout(pick_row)
            pick_layout.setContentsMargins(0, 0, 0, 0)
            pick_layout.setSpacing(4)
            pick_button = QtWidgets.QPushButton("\u70b9\u9009")
            pick_button.setObjectName("actionPointPickButton")
            pick_button.clicked.connect(lambda _checked=False, i=index: self._pick_coord(i))
            pick_layout.addWidget(pick_button)
            row_layout.addWidget(pick_row)

        for key in self._VISIBLE_FIELDS.get(kind, []):
            holder = QtWidgets.QWidget(container)
            holder_layout = QtWidgets.QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setSpacing(3)
            holder_layout.addWidget(QtWidgets.QLabel(self._FIELD_LABELS[key]))
            widget = self._make_field(key)
            holder_layout.addWidget(widget)
            fields[key] = widget
            field_rows[key] = holder
            row_layout.addWidget(holder)
            if key == "abs_y" and kind in {"mouse", "scroll"}:
                add_pick_row()
        add_pick_row()

        row_layout.addStretch(1)
        delete_btn = QtWidgets.QPushButton("\u5220\u9664")
        delete_btn.clicked.connect(lambda _checked=False, i=index: self._delete_action(i))
        row_layout.addWidget(delete_btn)

        row = {
            "container": container,
            "kind": kind,
            "handle": handle,
            "field_rows": field_rows,
            "pick_row": pick_row,
            "pick_button": pick_button,
        }
        self._rows.append(row)
        self._row_fields.append(fields)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, container)

        self._loading = True
        self._load_row_fields(index, action)
        self._loading = False
        self._update_mouse_position_fields(index)
        for widget in fields.values():
            for signal_name in ("currentIndexChanged", "textChanged", "valueChanged"):
                try:
                    getattr(widget, signal_name).connect(lambda *_args, i=index: self._sync_action_from_row(i))
                except Exception:
                    pass
        if kind == "mouse":
            fields["pos_mode"].currentIndexChanged.connect(lambda *_args, i=index: self._update_mouse_position_fields(i))
        container.mousePressEvent = lambda event, i=index: self._select_row(i)
        return row

    def _load_row_fields(self, index, action):
        fields = self._row_fields[index]
        kind = action.get("kind", "mouse")
        defaults = _copy_action(kind, action)
        for key in self._VISIBLE_FIELDS.get(kind, []):
            if defaults.get(key) is not None:
                self._set_field_value(fields, key, defaults.get(key))

    def _clear_rows(self):
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []
        self._row_fields = []
        self._field_rows = {}
        self._fields = {}
        self._pick_row = None

    def _refresh_rows(self, keep_current=True):
        current = self._current if keep_current else 0
        self._clear_rows()
        for index, action in enumerate(self._actions):
            self._build_row(index, action)
        if self._actions:
            self._select_row(max(0, min(current, len(self._actions) - 1)))
        else:
            self._current = -1
        self._update_scroll_height()

    def _update_scroll_height(self):
        base_height = self._base_editor_height()
        if not self._rows:
            self._row_height_limit = 0
            self._config_row.setMinimumHeight(0)
            self._scroll.setMinimumHeight(base_height)
            self._scroll.setMaximumHeight(base_height)
            return
        spacing = max(0, self._rows_layout.spacing())
        margins = self._rows_layout.contentsMargins()

        def rows_height(count):
            visible_rows = self._rows[:count]
            rows_total = sum(max(1, row["container"].sizeHint().height()) for row in visible_rows)
            gaps_total = spacing * max(0, len(visible_rows) - 1)
            return rows_total + gaps_total + margins.top() + margins.bottom()

        visible_rows = min(len(self._rows), self._max_visible_rows)
        frame = self._scroll.frameWidth() * 2
        self._config_row.setMinimumHeight(rows_height(len(self._rows)))
        self._row_height_limit = max(
            base_height,
            rows_height(min(len(self._rows), self._max_visible_rows)) + frame,
        )
        target_height = max(base_height, rows_height(visible_rows) + frame)
        self._scroll.setMinimumHeight(target_height)
        self._scroll.setMaximumHeight(self._row_height_limit)

    def _row_index_at_y(self, y):
        if not self._rows:
            return -1
        for index, row in enumerate(self._rows):
            geometry = row["container"].geometry()
            if y < geometry.center().y():
                return index
        return len(self._rows) - 1

    def _select_row(self, row):
        if not (0 <= row < len(self._actions)):
            return
        self._current = row
        self._fields = self._row_fields[row]
        self._field_rows = self._rows[row]["field_rows"]
        self._pick_row = self._rows[row]["pick_row"]

    def _save_current(self):
        if 0 <= self._current < len(self._actions):
            self._sync_action_from_row(self._current, emit=False)

    def _add_action(self, kind):
        self._save_current()
        self._actions.append(_copy_action(kind))
        self._current = len(self._actions) - 1
        self._refresh_rows()
        self.changed.emit()

    def _delete_action(self, row=None):
        if row is None:
            row = self._current
        if not (0 <= row < len(self._actions)):
            return
        del self._actions[row]
        self._current = min(row, len(self._actions) - 1)
        self._refresh_rows()
        self.changed.emit()

    def _move_action(self, direction, row=None):
        if row is None:
            row = self._current
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= len(self._actions):
            return
        self._move_action_to(row, new_row)

    def _move_action_to(self, row, new_row):
        if row < 0 or new_row < 0 or row >= len(self._actions) or new_row >= len(self._actions):
            return
        if row == new_row:
            self._select_row(row)
            return
        for index in range(len(self._actions)):
            self._sync_action_from_row(index, emit=False)
        action = self._actions.pop(row)
        self._actions.insert(new_row, action)
        self._current = new_row
        self._refresh_rows()
        self.changed.emit()

    def _edit_json(self):
        self._save_current()
        dlg = _ActionJsonDialog(self._actions, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.set_actions(dlg.actions)
            self.changed.emit()

    def set_actions(self, actions):
        self._actions = [_copy_action(a.get("kind", "mouse"), a) for a in (actions or []) if isinstance(a, dict)]
        self._current = 0 if self._actions else -1
        self._refresh_rows(keep_current=False)

    def _set_abs_coord(self, x, y, row=None):
        if row is None:
            row = self._current
        if not (0 <= row < len(self._row_fields)):
            return
        fields = self._row_fields[row]
        if "abs_x" in fields:
            fields["abs_x"].setValue(int(x))
        if "abs_y" in fields:
            fields["abs_y"].setValue(int(y))
        if "abs_x" not in fields or "abs_y" not in fields:
            self._actions[row]["abs_x"] = int(x)
            self._actions[row]["abs_y"] = int(y)
        self._sync_action_from_row(row)

    def _get_image_picker_cls(self):
        if self._image_picker_cls_override is not None:
            return self._image_picker_cls_override
        from bg_ocr.qt.pickers import _ImagePickerDialog
        return _ImagePickerDialog

    def _get_screen_point_picker_cls(self):
        if self._screen_point_picker_cls_override is not None:
            return self._screen_point_picker_cls_override
        from bg_ocr.qt.pickers import _ScreenPointPickerDialog
        return _ScreenPointPickerDialog

    def _current_kind(self, row=None):
        if row is None:
            row = self._current
        if 0 <= row < len(self._actions):
            return self._actions[row].get("kind", "mouse")
        return "mouse"

    def _pick_window_coord(self, row=None):
        if row is None:
            row = self._current
        kind = self._current_kind(row)
        if kind not in {"mouse", "scroll"}:
            QtWidgets.QMessageBox.information(self, "\u63d0\u793a", "\u7a97\u53e3\u76f8\u5bf9\u70b9\u53ea\u7528\u4e8e\u9f20\u6807\u6216\u6eda\u8f6e\u52a8\u4f5c")
            return
        owner = self._owner_window()
        if owner is None or not owner.current_hwnd():
            QtWidgets.QMessageBox.warning(self, "\u63d0\u793a", "\u8bf7\u5148\u7ed1\u5b9a\u76ee\u6807\u7a97\u53e3")
            return
        img = capture_full_preview(owner.current_hwnd(), owner.cfg.get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "\u5931\u8d25", "\u65e0\u6cd5\u622a\u53d6\u76ee\u6807\u7a97\u53e3")
            return
        dlg = self._get_image_picker_cls()(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            if kind == "mouse":
                self._row_fields[row]["pos_mode"].setCurrentText("window")
            self._set_abs_coord(x, y, row)

    def _pick_screen_coord(self, row=None):
        if row is None:
            row = self._current
        dlg = self._get_screen_point_picker_cls()(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.point:
            x, y = dlg.point
            if self._current_kind(row) == "mouse":
                self._row_fields[row]["pos_mode"].setCurrentText("screen")
            self._set_abs_coord(x, y, row)

    def _pick_coord(self, row=None):
        if row is None:
            row = self._current
        kind = self._current_kind(row)
        if kind == "mouse":
            mode = self._mouse_position_mode(self._row_fields[row])
            if mode == "window":
                self._pick_window_coord(row)
            elif mode == "screen":
                self._pick_screen_coord(row)
            return
        if kind == "scroll":
            self._pick_screen_coord(row)

    @property
    def actions(self):
        for row in range(len(self._actions)):
            self._sync_action_from_row(row, emit=False)
        return self._actions


class _ActionSequenceDialog(QtWidgets.QDialog):
    def __init__(self, actions, parent=None, image_picker_cls=None, screen_point_picker_cls=None):
        super().__init__(parent)
        self.setObjectName("actionSequenceDialog")
        self.setWindowTitle("编辑动作序列")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        self._editor = _ActionSequenceWidget(actions, self, image_picker_cls, screen_point_picker_cls)
        layout.addWidget(self._editor)

        dialog_buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        dialog_buttons.accepted.connect(self._accept)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)

        self._fields = self._editor._fields

    def _pick_window_coord(self):
        return self._editor._pick_window_coord()

    def _pick_screen_coord(self):
        return self._editor._pick_screen_coord()

    def _accept(self):
        self._editor._save_current()
        self.accept()

    @property
    def actions(self):
        return self._editor.actions
