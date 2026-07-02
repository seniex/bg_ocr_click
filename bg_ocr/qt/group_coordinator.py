from __future__ import annotations

from bg_ocr.config import save_config


def _load_group_editor(win, index):
    win._loading_group_editor = True
    try:
        win._group_editor.load_group(win.cfg["groups"][index], index)
        win._group_editor.set_chain_options(
            [group.get("name", f"Group {i + 1}") for i, group in enumerate(win.cfg["groups"])],
            index,
            win.cfg["groups"][index].get("chain_target", -1),
        )
    finally:
        win._loading_group_editor = False
        win._group_order_dirty = False


def _on_group_changed(win, index):
    if index < 0 or index >= len(win.cfg["groups"]):
        return
    if win._current_index == index and not win._group_order_dirty:
        win._load_group_editor(index)
        return
    win._save_current_group()
    win._current_index = index
    win._load_group_editor(index)


def _show_group_detail(win, index):
    if index < 0 or index >= len(win.cfg["groups"]):
        return
    if hasattr(win, "_page_nav") and win._page_nav.currentRow() != 1:
        win._page_nav.setCurrentRow(1)
    if win._group_list.currentRow() != index:
        win._group_list.setCurrentRow(index)
    else:
        win._on_group_changed(index)


def _save_current_group(win):
    if not win.cfg["groups"]:
        return
    index = min(max(win._current_index, 0), len(win.cfg["groups"]) - 1)
    win.cfg["groups"][index] = win._group_editor.dump_group(index)
    win._group_order_dirty = False


def _save_group_config(win):
    win._save_current_group()
    save_config(win.cfg)
    win._refresh_group_list()
    win._refresh_quick_config()
    if win.cfg["groups"]:
        win._group_list.setCurrentRow(min(win._current_index, len(win.cfg["groups"]) - 1))
    win.log("Group config saved", "ok")
