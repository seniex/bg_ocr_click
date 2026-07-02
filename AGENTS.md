# Project Agent Instructions

## Project Background

This is a Python desktop application refactor.

Current goal:

The app is Qt-only. The legacy Tk UI and fallback path have been removed. Keep moving the Qt UI
toward production readiness while preserving business behavior.

`REFACTOR_STATUS.md` is the source of truth for refactor status. `QT_REFACTOR_REMAINING.md`
owns unfinished final-work details.

Before starting any task:

1. Read `REFACTOR_STATUS.md` if it exists.
2. Read `QT_REFACTOR_REMAINING.md` if it exists.
3. Check current `git status` and `git diff`.
4. Continue from the current code state and do not repeat completed work.

## Core Principles

Do not break existing behavior.

Do not:

- Reintroduce Tk UI code or a Tk fallback path.
- Rewrite business logic at large scale.
- Modify unrelated modules.
- Change business flow for UI polish.

Prefer:

- Keeping existing interfaces.
- Reusing the existing logic layer.
- Keeping Qt code modular and test-backed.

## Qt Refactor Rules

Target structure:

Business logic -> UI adapter layer -> Qt UI

Qt code should:

- Stay modular.
- Avoid putting business logic directly inside `QWidget`.
- Keep widget creation and event binding separated where practical.

New functionality should go into the Qt version.

## Task Flow

For each task:

1. Analyze current code state.
2. List the plan.
3. Modify code.
4. Run relevant tests.
5. Update `REFACTOR_STATUS.md` for high-level status and `QT_REFACTOR_REMAINING.md` for unfinished
   final-work changes.
6. When all non-real-environment work is complete, stop and explicitly tell the user to run the real
   Windows UI smoke validation manually. Do not mark the refactor production-ready until the user has
   completed and reported that real-environment test result.

Do not modify code without recording status.

## Testing

After changes, prioritize:

```powershell
python -m compileall .
```

If tests exist, run:

```powershell
python -m unittest discover -s tests -v
```

Qt tests should prefer offscreen execution and avoid requiring a real display.

## Theme System

The project has a QSS theme system. Do not continue hard-coding colors, fonts, and styles into
widget code when touching UI styling.

Current theme files:

```text
themes/
  default.qss
  modern.qss
```

## Design Files

If `DESIGN.md` or `DESIGN-*.md` exists, use it for visual guidance only.

Do not rebuild the whole UI directly from a design file. Use this flow:

1. Create an isolated preview.
2. Confirm the design.
3. Convert to Qt QSS theme.
4. Connect theme switching.

## Edit Limits

Allowed UI polish:

- QSS
- Icons
- Spacing
- Layout adjustments

Forbidden:

- Changing business flow.
- Deleting functionality.
- Refactoring core logic without focused tests.

## Git

Before editing, check `git status`.

Do not overwrite user changes. Major milestones may be committed after tests pass.

## Current Priority

Continue Qt parity smoke validation and expand QSS themes as needed.
