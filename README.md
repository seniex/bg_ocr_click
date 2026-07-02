# Bg OCR Click

Windows background OCR click automation tool.

## Project Layout

- `bg_ocr_qt.py`: root Qt entry point; re-exports the Qt app surface for existing `bg_ocr_qt` imports.
- `bg_ocr/`: application package for shared runtime logic.
- `bg_ocr/compat.py`: compatibility re-export module for historical runtime imports.
- `bg_ocr/qt/`: focused Qt UI modules, including app launch, main window, dialogs, settings, state, and lifecycle helpers.
- `themes/`: QSS theme files.
- `tests/`: offscreen Qt smoke tests and runtime helper tests.

## Install

```bash
python -m pip install -e .
```

## Run

```bash
python bg_ocr_qt.py
```

Or after editable install:

```bash
bg-ocr-click
```

## Check

```bash
python -m compileall .
python -m unittest discover -s tests -v
```
