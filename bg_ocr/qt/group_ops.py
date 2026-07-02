from __future__ import annotations


def _remap_chain_targets_after_delete(groups, deleted_index):
    for group in groups:
        chain_target = group.get("chain_target", -1)
        if chain_target == deleted_index:
            group["chain_target"] = -1
            group["chain_enabled"] = False
        elif chain_target > deleted_index:
            group["chain_target"] = chain_target - 1


def _remap_chain_targets_after_move(groups, old_index, new_index):
    for group in groups:
        chain_target = group.get("chain_target", -1)
        if chain_target == old_index:
            group["chain_target"] = new_index
        elif chain_target == new_index:
            group["chain_target"] = old_index


def _remap_chain_targets_after_reorder(groups, old_to_new):
    for group in groups:
        chain_target = group.get("chain_target", -1)
        if chain_target >= 0:
            group["chain_target"] = old_to_new.get(chain_target, -1)
            if group["chain_target"] < 0:
                group["chain_enabled"] = False
