# Bg OCR Click

Windows background OCR click automation tool.

## Project Layout

- `bg_ocr_click.py`: Tkinter UI and workflow orchestration.
- `bg_ocr_config.py`: config defaults, config file IO, and log path setup.
- `bg_ocr_capture.py`: window capture helpers.
- `bg_ocr_ocr.py`: image preprocessing and OCR engines.
- `bg_ocr_matching.py`: keyword, template image, and color matching helpers.
- `bg_ocr_mouse.py`: background/foreground mouse and action sequence helpers.
- `bg_ocr_system.py`: admin elevation and window enumeration helpers.

## Install

```bash
python -m pip install -e .
```

## Run

```bash
python bg_ocr_click.py
```

Or after editable install:

```bash
bg-ocr-click
```

## Check

```bash
python -m py_compile bg_ocr_click.py bg_ocr_config.py bg_ocr_capture.py bg_ocr_ocr.py bg_ocr_matching.py bg_ocr_mouse.py bg_ocr_system.py
python -m unittest discover -s tests
```
