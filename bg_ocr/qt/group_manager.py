from __future__ import annotations

import os

from PyQt6 import QtCore, QtWidgets

from bg_ocr.capture import capture_full_preview
from bg_ocr.config import CONFIG_FILE
from bg_ocr.qt.group_ops import (
    _remap_chain_targets_after_delete,
    _remap_chain_targets_after_move,
    _remap_chain_targets_after_reorder,
)


def _add_group(win, save_config_fn, copy_group):
    win._save_current_group()
    win.cfg["groups"].append(copy_group({"name": f"Group {len(win.cfg['groups']) + 1}"}))
    win._current_index = len(win.cfg["groups"]) - 1
    win._refresh_group_list()
    win._group_list.setCurrentRow(win._current_index)
    save_config_fn(win.cfg)


def _delete_group(win, save_config_fn):
    idx = win._group_list.currentRow()
    if idx < 0:
        return
    if QtWidgets.QMessageBox.question(win, "Confirm", f"Delete group {idx + 1}?") != QtWidgets.QMessageBox.StandardButton.Yes:
        return
    win._save_current_group()
    del win.cfg["groups"][idx]
    _remap_chain_targets_after_delete(win.cfg["groups"], idx)
    win._current_index = max(0, idx - 1)
    win._refresh_group_list()
    win._refresh_quick_config()
    if win.cfg["groups"]:
        win._group_list.setCurrentRow(win._current_index)
    save_config_fn(win.cfg)


def _move_group(win, direction, save_config_fn):
    idx = win._group_list.currentRow()
    if idx < 0:
        return
    new_idx = idx + direction
    if new_idx < 0 or new_idx >= len(win.cfg["groups"]):
        return
    win._save_current_group()
    groups = win.cfg["groups"]
    groups[idx], groups[new_idx] = groups[new_idx], groups[idx]
    _remap_chain_targets_after_move(groups, idx, new_idx)
    win._current_index = new_idx
    win._refresh_group_list()
    win._refresh_quick_config()
    win._group_list.setCurrentRow(new_idx)
    save_config_fn(win.cfg)


def _quick_template_edit(win, row):
    cell = win._quick_table.cellWidget(row, 5)
    if cell is None:
        return None
    return cell.findChild(QtWidgets.QLineEdit, "quickTemplatePath")


def _show_quick_group_detail(win, pos):
    row = win._quick_table.rowAt(pos.y())
    if row < 0:
        return
    win._show_group_detail(row)


def _browse_quick_template(win, row):
    edit = _quick_template_edit(win, row)
    if edit is None:
        return
    path, _ = QtWidgets.QFileDialog.getOpenFileName(
        win, "选择模板图像", "", "Images (*.png *.jpg *.jpeg *.bmp);;All (*.*)"
    )
    if path:
        edit.setText(path)


def _capture_quick_template(win, row):
    edit = _quick_template_edit(win, row)
    if edit is None:
        return
    hwnd = win.current_hwnd()
    if not hwnd:
        QtWidgets.QMessageBox.warning(win, "提示", "请先绑定目标窗口")
        return
    img = capture_full_preview(hwnd, win.cfg.get("capture_mode", "printwindow"))
    if img is None:
        QtWidgets.QMessageBox.critical(win, "失败", "无法截图")
        return
    from bg_ocr.qt.pickers import _ImagePickerDialog

    dlg = _ImagePickerDialog(img, "rect", win)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dlg.selection:
        return
    x1, y1, x2, y2 = dlg.selection
    crop = img.crop((x1, y1, x2, y2))
    save_dir = os.path.dirname(CONFIG_FILE)
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f"template_g{row + 1}.png")
    crop.save(path)
    edit.setText(path)


def _build_quick_template_cell(win, row, group):
    if group.get("type") != "image":
        item = QtWidgets.QTableWidgetItem("")
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        win._quick_table.setItem(row, 5, item)
        win._quick_table.setCellWidget(row, 5, None)
        return
    cell = QtWidgets.QWidget()
    cell.setObjectName("quickTemplateCell")
    layout = QtWidgets.QHBoxLayout(cell)
    layout.setContentsMargins(0, 0, 0, 0)
    edit = QtWidgets.QLineEdit(group.get("template_path") or "")
    edit.setObjectName("quickTemplatePath")
    browse = QtWidgets.QPushButton("浏览")
    capture = QtWidgets.QPushButton("截取")
    browse.setObjectName("quickTemplateButton")
    capture.setObjectName("quickTemplateButton")
    browse.clicked.connect(lambda _checked=False, r=row: _browse_quick_template(win, r))
    capture.clicked.connect(lambda _checked=False, r=row: _capture_quick_template(win, r))
    layout.addWidget(edit, 1)
    layout.addWidget(browse)
    layout.addWidget(capture)
    win._quick_table.setCellWidget(row, 5, cell)


def _save_quick_config(win, save_config_fn):
    win._save_current_group()
    selected_group_id = None
    if 0 <= win._current_index < len(win.cfg["groups"]):
        selected_group_id = id(win.cfg["groups"][win._current_index])
    seqs = []
    for row in range(win._quick_table.rowCount()):
        try:
            seqs.append(int(win._quick_table.item(row, 1).text()))
        except Exception:
            QtWidgets.QMessageBox.critical(win, "Error", f"Row {row + 1} sequence is not a valid integer")
            return
    if len(seqs) != len(set(seqs)):
        QtWidgets.QMessageBox.critical(win, "Duplicate sequence", "Duplicate sequence values exist; edit them before saving")
        return
    for row, group in enumerate(win.cfg["groups"]):
        group["enabled"] = win._quick_table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked
        group["name"] = win._quick_table.item(row, 2).text().strip() or group.get("name", "")
        group["sink_after_click"] = win._quick_table.item(row, 3).checkState() == QtCore.Qt.CheckState.Checked
        try:
            group["interval"] = int(win._quick_table.item(row, 4).text())
        except Exception:
            pass
        if group.get("type") == "image":
            edit = _quick_template_edit(win, row)
            if edit is not None:
                group["template_path"] = edit.text().strip() or None
    order = sorted(range(len(seqs)), key=lambda i: seqs[i])
    win.cfg["groups"] = [win.cfg["groups"][i] for i in order]
    old_to_new = {old: new for new, old in enumerate(order)}
    for i, group in enumerate(win.cfg["groups"]):
        group["seq"] = i + 1
    _remap_chain_targets_after_reorder(win.cfg["groups"], old_to_new)
    if win.cfg["groups"]:
        win._current_index = min(win._current_index, len(win.cfg["groups"]) - 1)
    else:
        win._current_index = 0
    if selected_group_id is not None:
        for i, group in enumerate(win.cfg["groups"]):
            if id(group) == selected_group_id:
                win._current_index = i
                break
    save_config_fn(win.cfg)
    win._refresh_group_list()
    win._refresh_quick_config()
    if win.cfg["groups"]:
        win._group_list.setCurrentRow(min(win._current_index, len(win.cfg["groups"]) - 1))
    win.log("Quick config saved", "ok")
