# Qt Refactor Remaining Work

## Purpose

Track unfinished final work after removing the legacy Tk UI. `REFACTOR_STATUS.md` is the high-level
source of truth.

## Progress Summary

- Estimated progress: 100%.
- Root-level Python project files have been consolidated to `bg_ocr_qt.py`; shared runtime modules
  now live under `bg_ocr/` and Qt helpers under `bg_ocr/qt/`.
- Automated Qt/offscreen coverage is broad and currently passing.
- QSS selector coverage is broad enough for the main shell, home page, settings page, picker/dialog
  surfaces, group editor, popup templates, and action sequence editor.
- Package-layout cleanup on 2026-07-02 passed `python -m compileall .`,
  `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v` with 146 tests OK, and
  `python -m pip install -e . --dry-run --no-deps`.
- `package_only/` was created as a packaging-only staging directory with install instructions in
  `package_only/安装方法.md`; staging verification passed compileall, 146 offscreen tests, and
  editable-install dry-run.
- Real Windows UI smoke validation for the package-layout cleanup was reported by the user on
  2026-07-02 with no issues found.
- Final automated refresh on 2026-07-02 after manual smoke passed `python -m compileall .`,
  `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v` with 145 tests OK, and
  `python -m pip install -e . --dry-run --no-deps`.
- Real-use config `config/bg_ocr_click_tk.json` has been normalized into active
  `config/bg_ocr_click.json`; structural checks passed for 23 groups and the original active config
  was backed up as `config/bg_ocr_click.before_tk_migration_20260702_201806.json`.
- Real Windows UI smoke validation was reported by the user on 2026-07-02 with no issues found.
- The Qt refactor has no known remaining release blocker under the validated scope.

## Remaining Work

1. Fix any future issues found in real UI use with focused tests.
2. Continue incremental QSS polish only when touching a UI surface; avoid new inline styling where a
   stable selector is practical.
3. Re-run packaging/install smoke before publishing future release builds.

## Exit Reminder

Real Windows UI smoke validation was reported complete with no issues on 2026-07-02 for the current
package-layout build. Repeat the manual smoke pass after high-risk runtime/UI changes before calling
a later build production-ready.

## Verification Checklist

- `python -m compileall .`
- `python -m unittest discover -s tests -v`
- `python -m pip install -e . --dry-run --no-deps`
- Real Windows UI smoke for the runtime workflows, passed by user report on 2026-07-02.
- Re-run final packaging check before publishing future release builds.

## Known Issues

- PyQt6 font-directory warnings appear in offscreen tests but do not fail the suite.
- Terminal Chinese output may be mojibake; use UTF-8 reads and existing mojibake guard tests before
  editing localized strings.
