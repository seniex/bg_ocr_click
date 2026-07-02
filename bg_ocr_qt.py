from __future__ import annotations

from bg_ocr.qt import main_window as _main_window
from bg_ocr.qt.app import _launch_qt, main

for _name in dir(_main_window):
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = getattr(_main_window, _name)

del _main_window, _name


if __name__ == "__main__":
    main()
