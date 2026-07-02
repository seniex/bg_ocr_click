from __future__ import annotations

import copy

from bg_ocr.config import GROUP_DEFAULT


def _copy_group(data=None):
    group = copy.deepcopy(GROUP_DEFAULT)
    if data:
        group.update(data)
    return group
