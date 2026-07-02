from __future__ import annotations

import copy
import os

from PyQt6 import QtCore, QtWidgets

from bg_ocr.capture import capture_full_preview, capture_region
from bg_ocr.config import CONFIG_FILE
from bg_ocr.qt.actions import _ActionSequenceDialog, _ActionSequenceWidget
from bg_ocr.qt.group_factory import _copy_group
from bg_ocr.qt.templates import _PopupTemplateDialog
from bg_ocr.qt.value_helpers import _format_color, _format_region, _json_dump, _json_load, _parse_color, _parse_region


def _wrap(layout):
    w = QtWidgets.QWidget()
    w.setLayout(layout)
    return w


class _FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.setObjectName("groupFieldFlow")

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QtCore.QSize(left + right, top + bottom)
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        line_height = 0
        full_width = max(0, effective.width())

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisibleTo(self.parentWidget()):
                continue
            hint = item.sizeHint()
            full_row = widget is not None and widget.property("fieldSpan") == "full"
            item_width = full_width if full_row else min(hint.width(), full_width)
            next_x = x + item_width + self.spacing()
            if x > effective.x() and (full_row or next_x - self.spacing() > effective.right()):
                x = effective.x()
                y += line_height + self.spacing()
                next_x = x + item_width + self.spacing()
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), QtCore.QSize(item_width, hint.height())))
            if full_row:
                x = effective.x()
                y += hint.height() + self.spacing()
                line_height = 0
            else:
                x = next_x
                line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


def _normalize_monitor_type(value):
    aliases = {"orc": "ocr", "coor": "color"}
    return aliases.get(str(value or "ocr").lower(), str(value or "ocr").lower())


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
        step = -1 if event.angleDelta().y() > 0 else 1
        self.setCurrentIndex(max(0, min(self.count() - 1, self.currentIndex() + step)))
        event.accept()


class _GroupEditor(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("groupEditor")
        self._widgets = {}
        self._build()

    def _add_labeled(self, form, label, widget):
        form.addRow(label, widget)
        return widget

    def _combo(self, values, editable=False):
        cb = _FocusWheelComboBox()
        cb.setEditable(editable)
        cb.addItems(values)
        return cb

    def _spin(self, minimum, maximum, value=0):
        sb = _FocusWheelSpinBox()
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _dspin(self, minimum, maximum, value=0.0):
        sb = _FocusWheelDoubleSpinBox()
        sb.setDecimals(3)
        sb.setRange(minimum, maximum)
        sb.setValue(value)
        return sb

    def _section(self, title, object_name, columns=2, spacing=6):
        box = QtWidgets.QGroupBox(title)
        box.setObjectName(object_name)
        flow = _FlowLayout(box, spacing=spacing)
        self._section_layouts[object_name] = flow
        return box, flow, columns

    def _add_grid_field(self, grid, row, column, label, key, widget=None, colspan=1, full_span=False):
        if widget is None:
            widget = self._widgets[key]
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        caption = QtWidgets.QLabel(label)
        caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(caption)
        expands = full_span or colspan > 1
        layout.addWidget(widget, 1 if expands else 0)
        if expands:
            container.setProperty("fieldSpan", "full")
            container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        else:
            container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        grid.addWidget(container)
        self._field_containers[key] = container
        return container

    def _add_keyword_field(self, grid, row, column, colspan=1):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        caption = QtWidgets.QLabel("关键字")
        caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(caption)

        value_col = QtWidgets.QVBoxLayout()
        value_col.setContentsMargins(0, 0, 0, 0)
        value_col.setSpacing(3)
        value_col.addWidget(self._widgets["keywords"])
        self._keyword_help = QtWidgets.QLabel(
            "规则：多个关键词用 |、逗号、分号、顿号或换行分隔，任一命中即匹配；忽略空格差异。"
        )
        self._keyword_help.setObjectName("keywordHelp")
        self._keyword_help.setWordWrap(False)
        value_col.addWidget(self._keyword_help)
        layout.addLayout(value_col)

        language_pair = QtWidgets.QWidget(container)
        language_layout = QtWidgets.QHBoxLayout(language_pair)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(6)
        language_caption = QtWidgets.QLabel("\u8bed\u8a00")
        language_caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        language_layout.addWidget(language_caption)
        language_layout.addWidget(self._widgets["language"])
        language_pair.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(language_pair, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)

        container.setProperty("fieldSpan", "full")
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        grid.addWidget(container)
        self._field_containers["keywords"] = container
        self._field_containers["language"] = language_pair
        return container

    def _add_section_fields(self, grid, fields, columns=2, start_row=0):
        for index, (label, key) in enumerate(fields):
            if key in self._field_containers:
                continue
            self._add_grid_field(grid, start_row + index // columns, index % columns, label, key)

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self._field_containers = {}
        self._section_layouts = {}
        sections = QtWidgets.QVBoxLayout(inner)
        sections.setContentsMargins(8, 8, 8, 8)
        sections.setSpacing(8)

        self._widgets["enabled"] = QtWidgets.QCheckBox("启用")
        self._widgets["name"] = QtWidgets.QLineEdit()
        self._widgets["type"] = self._combo(["ocr", "image", "color"])
        self._widgets["capture_mode"] = self._combo(["global", "printwindow", "imagegrab", "auto"])
        self._widgets["keywords"] = QtWidgets.QLineEdit()
        self._widgets["language"] = self._combo(["chi_sim", "chi_sim_vert", "eng"], editable=True)
        self._widgets["ocr_engine"] = self._combo(["paddle", "tesseract"])
        self._widgets["language"].setProperty("fieldSize", "short")
        self._widgets["ocr_engine"].setProperty("fieldSize", "short")
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
        self._widgets["sink_after_click"] = QtWidgets.QCheckBox("")
        self._widgets["mouse_jitter"] = QtWidgets.QCheckBox("")
        self._widgets["mouse_humanize"] = QtWidgets.QCheckBox("")
        self._widgets["actions"] = _ActionSequenceWidget(parent=self)
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
        self._widgets["popup_templates"].setObjectName("popupTemplatesJson")

        self._template_browse = QtWidgets.QPushButton("浏览")
        self._template_capture = QtWidgets.QPushButton("截取")
        self._region_pick = QtWidgets.QPushButton("选择")
        self._color_pick = QtWidgets.QPushButton("取色")
        self._popup_templates_edit = QtWidgets.QPushButton("打开弹窗模板编辑器")
        self._popup_templates_edit.setObjectName("popupTemplatesEditButton")
        self._region_preview = QtWidgets.QLabel("")
        self._template_preview = QtWidgets.QLabel("")

        self._template_browse.clicked.connect(self._browse_template)
        self._template_capture.clicked.connect(self._capture_template)
        self._region_pick.clicked.connect(self._pick_region)
        self._color_pick.clicked.connect(self._pick_color)
        self._popup_templates_edit.clicked.connect(self._edit_popup_templates)

        basic_box, basic_grid, basic_columns = self._section("基础", "groupSectionBasic")
        self._add_section_fields(
            basic_grid,
            [
                ("启用", "enabled"),
                ("名称", "name"),
                ("类型", "type"),
                ("截取模式", "capture_mode"),
                ("间隔", "interval"),
                ("暂停", "pause"),
                ("调试保存", "debug_save"),
            ],
            basic_columns,
        )
        sections.addWidget(basic_box)

        recognition_box, recognition_grid, recognition_columns = self._section("识别", "groupSectionRecognition")
        self._recognition_box = recognition_box
        self._add_keyword_field(recognition_grid, 0, 0, colspan=recognition_columns)
        self._add_section_fields(
            recognition_grid,
            [
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
            ],
            recognition_columns,
            start_row=1,
        )
        sections.addWidget(recognition_box)

        target_box, target_grid, target_columns = self._section("目标", "groupSectionTarget")
        self._target_box = target_box
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._widgets["region"])
        row.addWidget(self._region_pick)
        self._add_grid_field(target_grid, 0, 0, "区域", "region", _wrap(row), colspan=target_columns)

        trow = QtWidgets.QHBoxLayout()
        trow.addWidget(self._widgets["template_path"])
        trow.addWidget(self._template_browse)
        trow.addWidget(self._template_capture)
        self._add_grid_field(target_grid, 1, 0, "模板图", "template_path", _wrap(trow), colspan=target_columns)

        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(self._widgets["target_color"])
        crow.addWidget(self._color_pick)
        self._add_grid_field(target_grid, 2, 0, "颜色", "target_color", _wrap(crow), colspan=target_columns)
        sections.addWidget(target_box)

        actions_box, actions_grid, actions_columns = self._section("动作", "groupSectionActions", columns=1)
        self._add_grid_field(actions_grid, 0, 0, "动作序列", "actions", colspan=actions_columns, full_span=True)
        sections.addWidget(actions_box)

        click_box, click_grid, click_columns = self._section("点击", "groupSectionClick", spacing=16)
        self._click_box = click_box
        self._add_section_fields(
            click_grid,
            [
                ("点击模式", "click_mode"),
                ("序列完成后切回", "sink_after_click"),
                ("鼠标抖动", "mouse_jitter"),
                ("人性化移动", "mouse_humanize"),
            ],
            click_columns,
        )
        sections.addWidget(click_box)

        chain_box, chain_grid, chain_columns = self._section("串联", "groupSectionChain")
        self._add_section_fields(
            chain_grid,
            [
                ("串联启用", "chain_enabled"),
                ("串联目标", "chain_target"),
                ("串联等待", "chain_wait"),
            ],
            chain_columns,
        )
        sections.addWidget(chain_box)

        popup_box, popup_grid, popup_columns = self._section("弹窗", "groupSectionPopup")
        self._add_section_fields(
            popup_grid,
            [
                ("弹窗启用", "popup_enabled"),
                ("仅弹窗", "popup_only_mode"),
                ("标题关键字", "popup_title_kw"),
                ("等待出现", "popup_wait_appear"),
                ("等待关闭", "popup_wait_close"),
                ("总超时", "popup_total_timeout"),
                ("无匹配动作", "popup_no_match_action"),
            ],
            popup_columns,
        )
        template_layout = QtWidgets.QVBoxLayout()
        template_layout.addWidget(self._popup_templates_edit)
        template_layout.addWidget(self._widgets["popup_templates"])
        self._add_grid_field(
            popup_grid,
            4,
            0,
            "弹窗模板",
            "popup_templates",
            _wrap(template_layout),
            colspan=popup_columns,
        )
        sections.addWidget(popup_box)
        sections.addStretch(1)

        self._widgets["ocr_binarize"].stateChanged.connect(self.changed.emit)
        self._widgets["ocr_invert"].stateChanged.connect(self.changed.emit)
        self._widgets["sink_after_click"].stateChanged.connect(self.changed.emit)
        self._widgets["mouse_jitter"].stateChanged.connect(self.changed.emit)
        self._widgets["mouse_humanize"].stateChanged.connect(self.changed.emit)
        self._widgets["actions"].changed.connect(self.changed.emit)
        self._widgets["debug_save"].stateChanged.connect(self.changed.emit)
        self._widgets["chain_enabled"].stateChanged.connect(self.changed.emit)
        self._widgets["popup_only_mode"].stateChanged.connect(self.changed.emit)
        self._widgets["popup_enabled"].stateChanged.connect(self.changed.emit)
        self._widgets["popup_enabled"].stateChanged.connect(lambda _state: self._update_popup_visibility())
        self._widgets["type"].currentIndexChanged.connect(lambda _index: self._update_recognition_visibility())
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
        self._update_popup_visibility()
        self._update_recognition_visibility()

    def _update_popup_visibility(self):
        visible = self._widgets["popup_enabled"].isChecked()
        for key in [
            "popup_only_mode",
            "popup_title_kw",
            "popup_wait_appear",
            "popup_wait_close",
            "popup_total_timeout",
            "popup_no_match_action",
            "popup_templates",
        ]:
            container = self._field_containers.get(key)
            if container is not None:
                container.setVisible(visible)

    def _update_recognition_visibility(self):
        monitor_type = _normalize_monitor_type(self._widgets["type"].currentText())
        type_fields = {
            "ocr": {
                "keywords",
                "language",
                "ocr_engine",
                "ocr_psm",
                "ocr_scale",
                "ocr_binarize",
                "ocr_threshold",
                "ocr_contrast",
                "ocr_invert",
            },
            "image": {"template_path", "threshold"},
            "color": {"target_color", "tolerance"},
        }
        detail_fields = set().union(*type_fields.values())
        visible_fields = type_fields.get(monitor_type, set())
        for key in detail_fields:
            container = self._field_containers.get(key)
            if container is not None:
                container.setVisible(key in visible_fields)

    def set_chain_options(self, group_names, current_index, selected_index=None):
        if selected_index is None:
            selected_index = getattr(self, "_chain_target_index", -1)
        try:
            selected_index = int(selected_index)
        except Exception:
            selected_index = -1
        if selected_index == current_index or selected_index < 0 or selected_index >= len(group_names):
            selected_index = -1

        cb = self._widgets["chain_target"]
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("")
        self._chain_map = {}
        selected_label = ""
        for i, name in enumerate(group_names):
            if i == current_index:
                continue
            label = f"{i + 1}:{name}"
            self._chain_map[label] = i
            cb.addItem(label)
            if i == selected_index:
                selected_label = label
        if selected_label:
            cb.setCurrentText(selected_label)
        else:
            cb.setCurrentIndex(0)
        cb.blockSignals(False)
        self._chain_target_index = selected_index

    def load_group(self, g, current_index=0):
        self._loaded_group = copy.deepcopy(g)
        self._current_region = g.get("region")
        self._current_template = g.get("template_path")
        self._widgets["enabled"].setChecked(bool(g.get("enabled", True)))
        self._widgets["name"].setText(g.get("name", ""))
        self._widgets["type"].setCurrentText(_normalize_monitor_type(g.get("type", "ocr")))
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
        self._widgets["actions"].set_actions(g.get("actions", []))
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
        ct = g.get("chain_target", -1)
        self._chain_target_index = ct
        self._widgets["popup_templates"].setPlainText(_json_dump(g.get("popup_templates", [])))
        self._update_popup_visibility()
        self._update_recognition_visibility()

    def dump_group(self, current_index=0):
        g = _copy_group(getattr(self, "_loaded_group", None))
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
        g["actions"] = self._widgets["actions"].actions
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
        self._widgets["actions"]._edit_json()
        self.changed.emit()

    def _edit_popup_templates(self):
        templates = _json_load(self._widgets["popup_templates"].toPlainText(), [])
        if not isinstance(templates, list):
            templates = []
        dlg = _PopupTemplateDialog(templates, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._widgets["popup_templates"].setPlainText(_json_dump(dlg.templates))
            self.changed.emit()

    def _get_image_picker_cls(self):
        from bg_ocr.qt.pickers import _ImagePickerDialog
        return _ImagePickerDialog

    def _current_image(self):
        return None

    def _owner_window(self):
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "current_hwnd") and hasattr(parent, "cfg"):
                return parent
            parent = parent.parent()
        return None

    def _pick_region(self):
        owner = self._owner_window()
        hwnd = owner.current_hwnd() if owner is not None else None
        if not hwnd:
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(hwnd, getattr(owner, "cfg", {}).get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截取窗口")
            return
        dlg = self._get_image_picker_cls()(img, "rect", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            region = dlg.selection
            self._widgets["region"].setText(_json_dump(region))
            self.changed.emit()

    def _pick_color(self):
        owner = self._owner_window()
        hwnd = owner.current_hwnd() if owner is not None else None
        if not hwnd:
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(hwnd, getattr(owner, "cfg", {}).get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截图")
            return
        dlg = self._get_image_picker_cls()(img, "point", self)
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
        owner = self._owner_window()
        hwnd = owner.current_hwnd() if owner is not None else None
        if not hwnd:
            QtWidgets.QMessageBox.warning(self, "提示", "请先绑定目标窗口")
            return
        img = capture_full_preview(hwnd, getattr(owner, "cfg", {}).get("capture_mode", "printwindow"))
        if img is None:
            QtWidgets.QMessageBox.critical(self, "失败", "无法截图")
            return
        dlg = self._get_image_picker_cls()(img, "rect", self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dlg.selection:
            return
        x1, y1, x2, y2 = dlg.selection
        crop = img.crop((x1, y1, x2, y2))
        save_dir = os.path.dirname(CONFIG_FILE)
        os.makedirs(save_dir, exist_ok=True)
        group_index = owner.current_group_index() if owner is not None and hasattr(owner, "current_group_index") else 0
        path = os.path.join(save_dir, f"template_g{group_index + 1}.png")
        crop.save(path)
        self._widgets["template_path"].setText(path)
        self.changed.emit()
