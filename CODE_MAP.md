# Code Map

## Entry Points

- `bg_ocr_qt.py`
  - Root-level Qt application entry; this is the only project `.py` file kept in the repository root.
  - Re-exports the Qt app surface from `bg_ocr.qt.main_window` and `bg_ocr.qt.app` for existing
    `import bg_ocr_qt` callers.
- `bg_ocr/qt/app.py`
  - Qt application launcher.
  - `_launch_qt()` creates `QApplication`, checks startup dependencies/admin state, creates
    `BgOcrQtWindow`, restores geometry, and starts the Qt event loop.
  - `main()` launches Qt directly and does not fall back to Tk.

## Shared Backend Modules

- `bg_ocr/config.py`: config/log paths, default group/template dictionaries, `load_config()`, `save_config()`.
- `bg_ocr/action_runtime.py`: shared action defaults, action option lists, and async sound playback.
- `bg_ocr/monitor.py`: group monitor runtime for recognition, action execution, chaining, and popup flow.
- `bg_ocr/capture.py`: window/region capture helpers and capture dependency flags.
- `bg_ocr/ocr.py`: PaddleOCR-json integration, Tesseract setup, preprocessing, OCR helpers.
- `bg_ocr/matching.py`: keyword, image template, and color matching helpers.
- `bg_ocr/mouse.py`: background/foreground click helpers and action sequence execution.
- `bg_ocr/system.py`: Windows admin elevation and window enumeration helpers.
- `bg_ocr/compat.py`: package-level compatibility re-export module; there is no root
  `bg_ocr_click.py` script.

## Qt UI Modules

- `bg_ocr/qt/main_window.py`: `BgOcrQtWindow` plus thin wrappers to focused Qt modules.
- `bg_ocr/qt/actions.py`: Qt action sequence dialog.
- `bg_ocr/qt/templates.py`: Qt popup template dialog.
- `bg_ocr/qt/theme.py`: QSS theme resolution, loading, and application.
- `bg_ocr/qt/group_editor.py`: Qt group editor widget.
- `bg_ocr/qt/settings.py`: Qt settings editor.
- `bg_ocr/qt/pickers.py`: Qt region, window, and screen point pickers.
- `bg_ocr/qt/tabs.py`: Qt tab builders.
- `bg_ocr/qt/window_setup.py`: main-window frame setup.
- `bg_ocr/qt/window_lifecycle.py`: main-window initialization lifecycle.
- `bg_ocr/qt/window_binding.py`: target-window filtering and binding.
- `bg_ocr/qt/auto_bind.py`: process-window auto-bind loop.
- `bg_ocr/qt/hotkeys.py`: global hotkey registration/cleanup.
- `bg_ocr/qt/monitor_lifecycle.py`: monitor start/stop lifecycle.
- `bg_ocr/qt/shutdown.py`: close/shutdown persistence.
- `bg_ocr/qt/group_coordinator.py`: group editor load/save coordination.
- `bg_ocr/qt/group_manager.py`: group add/delete/move and quick config helpers.
- `bg_ocr/qt/group_factory.py`: group config copy helper.
- `bg_ocr/qt/group_ops.py`: chain target remapping helpers.
- `bg_ocr/qt/state.py`: Qt state/UI sync helpers.
- `bg_ocr/qt/runtime_adapter.py`: runtime-facing Qt adapter callbacks.
- `bg_ocr/qt/runtime_checks.py`: dependency checks.
- `bg_ocr/qt/value_helpers.py`: JSON, region, and color parse/format helpers.

## Tests

- `tests/test_smoke.py`
  - Entry availability and Qt-only fallback checks.
  - Qt module-boundary checks.
  - Offscreen Qt widget and lifecycle smoke tests.
  - Runtime helper and matching tests.

## Current Risk Boundaries

- Do not reintroduce Tk UI code or fallback behavior.
- Keep root-level project Python files limited to `bg_ocr_qt.py`.
- Avoid large business-logic rewrites without focused tests.
