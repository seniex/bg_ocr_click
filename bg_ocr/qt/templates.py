from __future__ import annotations

import copy
import os
import time

from PyQt6 import QtCore, QtWidgets

from bg_ocr.capture import capture_full_preview
from bg_ocr.config import CONFIG_FILE, POPUP_TEMPLATE_DEFAULT
from bg_ocr.qt.actions import _ActionSequenceDialog
from bg_ocr.qt.value_helpers import _format_color, _format_region, _json_dump, _json_load, _parse_color, _parse_region


def _copy_template(data=None):
    t = copy.deepcopy(POPUP_TEMPLATE_DEFAULT)
    if data:
        t.update(data)
    return t


def _wrap(layout):
    w = QtWidgets.QWidget()
    w.setLayout(layout)
    return w


class _PopupTemplateDialog(QtWidgets.QDialog):
    def __init__(self, templates, parent=None, image_picker_cls=None, screen_point_picker_cls=None):
        super().__init__(parent)
        self.setObjectName("popupTemplateDialog")
        self.setWindowTitle("Edit popup templates")
        self.setModal(True)
        self._templates = [_copy_template(t) for t in (templates or []) if isinstance(t, dict)]
        self._current = -1
        self._loading = False
        self._image_picker_cls_override = image_picker_cls
        self._screen_point_picker_cls_override = screen_point_picker_cls
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
        for btn in [self._add_btn, self._delete_btn, self._up_btn, self._down_btn]:
            btn.setObjectName("popupTemplateToolbarButton")
        self._add_btn.clicked.connect(self._add_template)
        self._delete_btn.clicked.connect(self._delete_template)
        self._up_btn.clicked.connect(lambda: self._move_template(-1))
        self._down_btn.clicked.connect(lambda: self._move_template(1))
        for btn in [self._add_btn, self._delete_btn, self._up_btn, self._down_btn]:
            buttons.addWidget(btn)
        buttons.addStretch(1)

        split = QtWidgets.QSplitter()
        split.setObjectName("popupTemplateSplit")
        self._list = QtWidgets.QListWidget()
        self._list.setObjectName("popupTemplateList")
        self._list.currentRowChanged.connect(self._change_row)
        split.addWidget(self._list)

        right = QtWidgets.QScrollArea()
        right.setObjectName("popupTemplateFormScroll")
        right.setWidgetResizable(True)
        form_widget = QtWidgets.QWidget()
        form_widget.setObjectName("popupTemplateForm")
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
        for key in ["name", "keywords", "template_path", "target_color", "region", "after_match_sound_file"]:
            self._fields[key].setObjectName("popupTemplateTextField")

        self._template_browse = QtWidgets.QPushButton("Browse")
        self._template_capture = QtWidgets.QPushButton("Capture")
        self._region_pick = QtWidgets.QPushButton("Pick")
        self._color_pick = QtWidgets.QPushButton("Pick")
        self._actions_edit = QtWidgets.QPushButton("Edit actions")
        self._sound_browse = QtWidgets.QPushButton("Browse")
        self._pick_window_btn = QtWidgets.QPushButton("Pick window point")
        self._pick_screen_btn = QtWidgets.QPushButton("Pick screen point")
        for btn in [
            self._template_browse,
            self._template_capture,
            self._region_pick,
            self._color_pick,
            self._sound_browse,
            self._pick_window_btn,
            self._pick_screen_btn,
        ]:
            btn.setObjectName("popupTemplateCompactButton")
        self._actions_edit.setObjectName("popupTemplateActionsButton")

        self._template_browse.clicked.connect(self._browse_template)
        self._template_capture.clicked.connect(self._capture_template)
        self._region_pick.clicked.connect(self._pick_region)
        self._color_pick.clicked.connect(self._pick_color)
        self._actions_edit.clicked.connect(self._edit_actions)
        self._sound_browse.clicked.connect(self._browse_sound)
        self._pick_window_btn.clicked.connect(self._pick_window_coord)
        self._pick_screen_btn.clicked.connect(self._pick_screen_coord)

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

        point_row = QtWidgets.QHBoxLayout()
        point_row.addWidget(self._pick_window_btn)
        point_row.addWidget(self._pick_screen_btn)
        self._form.addRow("Click point", _wrap(point_row))

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
        self._fields["after_match_stop_flow"].stateChanged.connect(self._sync_stop_flow_option)
        self._fields["after_match_stop_all"].stateChanged.connect(self._sync_stop_all_option)

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
        while parent is not None:
            if hasattr(parent, "current_hwnd") and hasattr(parent, "cfg"):
                return parent
            parent = parent.parent()
        return None

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
        if widget.findText(text) < 0:
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

    def _sync_stop_flow_option(self, *_args):
        if self._fields["after_match_stop_flow"].isChecked():
            self._fields["after_match_stop_all"].setChecked(False)

    def _sync_stop_all_option(self, *_args):
        if self._fields["after_match_stop_all"].isChecked():
            self._fields["after_match_stop_flow"].setChecked(False)

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
        self._current = new_row
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
        dlg = self._get_image_picker_cls()(img, "rect", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            self._fields["region"].setText(_json_dump(dlg.selection))
            self._save_current()

    def _pick_color(self):
        img = self._capture_preview()
        if img is None:
            return
        dlg = self._get_image_picker_cls()(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            try:
                px = img.getpixel((x, y))
                color = [int(px[0]), int(px[1]), int(px[2])]
            except Exception:
                return
            self._fields["target_color"].setText(_format_color(color))
            self._save_current()

    def _set_click_coord(self, target, x, y):
        self._fields["click_target"].setCurrentText(target)
        self._fields["custom_x"].setValue(int(x))
        self._fields["custom_y"].setValue(int(y))
        self._save_current()

    def _pick_window_coord(self):
        img = self._capture_preview()
        if img is None:
            return
        dlg = self._get_image_picker_cls()(img, "point", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selection:
            x, y = dlg.selection
            self._set_click_coord("window", x, y)

    def _pick_screen_coord(self):
        dlg = self._get_screen_point_picker_cls()(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.point:
            x, y = dlg.point
            self._set_click_coord("screen", x, y)

    def _capture_template(self):
        img = self._capture_preview()
        if img is None:
            return
        dlg = self._get_image_picker_cls()(img, "rect", self)
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
