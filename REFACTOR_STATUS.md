# Qt Refactor Status

## Current Goal

The app is Qt-only. The legacy Tk UI and fallback path have been removed. Keep improving Qt
production readiness while preserving existing business behavior.

## Overall Progress

- Estimated progress: 100%.
- The core Qt refactor is structurally complete: startup, main window composition, settings,
  dialogs, pickers, group editing, hotkeys, monitor lifecycle, shutdown, theme loading, and runtime
  checks are split across focused Qt modules.
- Real Windows UI smoke validation has been user-tested with no issues reported.
- Final automated and packaging smoke checks are passing; the Qt refactor is production-ready under
  the validated scope.

## Current Architecture

- `bg_ocr_qt.py` is the only root-level project Python file. It is a thin Qt entry/re-export
  module for the existing `bg_ocr_qt` import surface.
- Shared business/runtime behavior lives under the `bg_ocr` package, including `config.py`,
  `capture.py`, `ocr.py`, `matching.py`, `mouse.py`, `action_runtime.py`, and `monitor.py`.
- The historical root `bg_ocr_click.py` compatibility script has been removed. Package-level
  compatibility re-exports live in `bg_ocr/compat.py` only.
- Qt-specific behavior lives in focused `bg_ocr/qt` modules for app launch, window setup, state,
  settings, pickers, templates, actions, group management, monitor lifecycle, hotkeys, runtime
  checks, and shutdown. `bg_ocr/qt/main_window.py` owns `BgOcrQtWindow`.
- QSS themes live in `themes/default.qss` and `themes/modern.qss` and are applied through
  `bg_ocr/qt/theme.py`.
- Qt default window geometry is centralized in `bg_ocr.config.DEFAULT_WINDOW_GEOMETRY`.

## Implemented UI Parity

- Main shell: fixed top runtime/admin status row, left page navigation, persistent monitor-group
  sidebar, and right-side page stack.
- Home page: window binding, quick-config editing, group-detail navigation from quick config, image
  template path editing, and log controls.
- Groups page: modular group editor with recognition, target, action sequence, popup, chain, and
  quick-switch behavior preserved.
- Settings page: theme selection from the shared theme list, startup auto-start toggle, path
  controls, dependency status, sound-test behavior, hotkeys, auto-bind, and admin relaunch.
- Runtime flow: monitor start/stop preflight, dependency checks, window binding, auto-bind, hotkeys,
  shutdown persistence, and UI callback forwarding are covered through Qt paths.

## QSS Coverage

Stable selectors and theme-owned sizing now cover the main status row, left navigation/sidebar,
home window binding, home quick actions, quick-config template cells, settings dependency/path/save
controls, picker dialogs, window-picker internals, editor dialogs, group editor sections and fields,
popup-template dialogs, action JSON dialogs, and action-sequence rows/editor surfaces.

Avoid adding new inline widget sizing or styling when a QSS selector is practical.

## Automated Coverage

- Smoke tests guard Qt-only boundaries, compatibility re-exports, no Tk fallback, package data,
  theme loading, settings roundtrip, startup prompts, geometry restore, mojibake regressions, and
  key Chinese labels.
- Offscreen Qt smoke tests cover group editor state, quick config, chain targets, popup flows,
  action dialogs/editor rows, popup template dialogs, pickers, window binding, auto-bind, hotkeys,
  monitor lifecycle, shutdown, runtime adapter behavior, and dependency checks.
- Matching/runtime tests cover OCR/image/color dispatch, keyword/color/template helpers when
  dependencies are present, runtime dependency preflight, group deletion, quick-config edge cases,
  and focus-gated wheel behavior.
- QSS smoke tests verify both selector presence and representative polished widget sizing.

## Last Automated Verification

2026-07-02 package-layout cleanup:

- Root-level project Python files are limited to `bg_ocr_qt.py`; business and Qt helper modules
  were moved into `bg_ocr/` and `bg_ocr/qt/`.
- `python -m compileall .`: passed.
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`: passed, 146 tests OK.
- `python -m pip install -e . --dry-run --no-deps`: passed, `Would install bg-ocr-click-0.1.0`.
- Real Windows UI smoke validation for the package-layout build was reported by the user with no
  issues found.
- `package_only/` was created as a packaging-only staging copy. It includes the installable source,
  QSS themes, tests, active `config/bg_ocr_click.json`, package metadata, status docs,
  `README_仅用于打包.md`, and `安装方法.md`.
- Package staging verification from `package_only/`: `python -m compileall .` passed,
  `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v` passed with 146 tests OK,
  and `python -m pip install -e . --dry-run --no-deps` passed.

2026-07-02 final refresh after manual smoke:

- `python -m compileall .`: passed.
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`: passed, 145 tests OK.
- `python -m pip install -e . --dry-run --no-deps`: passed, `Would install bg-ocr-click-0.1.0`.
- Real Windows UI smoke validation was reported by the user with no issues found.
- Real-use config `config/bg_ocr_click_tk.json` was schema-checked, normalized through the current
  config loader, and written to active `config/bg_ocr_click.json`; 23 groups loaded with no missing
  current fields or unsupported action kinds.

## Last Real UI Verification

2026-07-02 manual Windows UI smoke after package-layout cleanup:

- User reported manual testing found no issues.
- The package-layout build is no longer blocked on real-environment smoke validation.
- Keep production changes focused and re-run the relevant smoke workflows after any runtime/UI
  fixes.

Earlier full verification in this refactor pass:

- `python -m compileall .`: passed.
- `python -m unittest discover -s tests -v`: passed, 145 tests OK.
- `cmd.exe /c .\install_codex_context_menu.bat -h`: passed.
- `cmd.exe /c .\install_codex_context_menu.bat --dry-run`: passed without registry writes.
- `python -m pip install -e . --dry-run --no-deps`: passed, `Would install bg-ocr-click-0.1.0`.

## Guardrails

- Do not reintroduce Tk UI code or Tk fallback behavior.
- Keep business logic in shared runtime modules instead of Qt widgets.
- Add focused offscreen tests before touching Qt state sync, lifecycle, dialogs, or action editing.
- Real Windows UI smoke validation passed by user report on 2026-07-02; repeat it after any
  high-risk runtime or UI workflow changes before calling a later build production-ready.
- Re-run packaging/install smoke before publishing future release builds.
- Use UTF-8 and avoid shell rewrites that can corrupt Chinese text through console mojibake.
