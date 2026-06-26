import unittest
import os

from PIL import Image

import bg_ocr_click
import bg_ocr_matching
import bg_ocr_ocr
import bg_ocr_qt


class ProjectSmokeTests(unittest.TestCase):
    def test_main_is_console_entry(self):
        self.assertTrue(callable(bg_ocr_click.main))

    def test_qt_main_is_available(self):
        self.assertTrue(callable(bg_ocr_qt.main))
        self.assertTrue(hasattr(bg_ocr_qt, "BgOcrQtWindow"))

    def test_qt_settings_capture_mode_roundtrip(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._SettingsEditor()
        try:
            editor.load_settings({"capture_mode": "auto"})
            self.assertEqual(editor.dump_settings()["capture_mode"], "auto")
        finally:
            editor.close()

    def test_qt_uses_paddle_only_for_ocr_items(self):
        win = bg_ocr_qt.BgOcrQtWindow.__new__(bg_ocr_qt.BgOcrQtWindow)
        win.cfg = {
            "groups": [
                {
                    "enabled": True,
                    "type": "image",
                    "ocr_engine": "paddle",
                    "popup_templates": [{"type": "image", "ocr_engine": "paddle"}],
                }
            ]
        }
        self.assertFalse(win._uses_paddle())
        win.cfg["groups"][0]["popup_templates"].append({"type": "ocr", "ocr_engine": "paddle"})
        self.assertTrue(win._uses_paddle())

    def test_qt_popup_template_dependency_check(self):
        win = bg_ocr_qt.BgOcrQtWindow.__new__(bg_ocr_qt.BgOcrQtWindow)
        win.cfg = {
            "groups": [
                {
                    "enabled": True,
                    "type": "noop",
                    "popup_templates": [{"type": "ocr", "ocr_engine": "tesseract"}],
                }
            ]
        }
        old = bg_ocr_qt.HAS_TESSERACT
        bg_ocr_qt.HAS_TESSERACT = False
        try:
            missing = win._missing_runtime_dependency()
            self.assertIn("group 1 popup 1", missing)
            self.assertIn("Tesseract", missing)
        finally:
            bg_ocr_qt.HAS_TESSERACT = old

    def test_paddle_engine_is_shared(self):
        self.assertIs(bg_ocr_click._paddle_engine, bg_ocr_ocr.get_paddle_engine())

    def test_keyword_matching(self):
        matched, keyword = bg_ocr_matching.match_keywords("Hello World", "missing|world")
        self.assertTrue(matched)
        self.assertEqual(keyword, "world")

    def test_color_matching(self):
        if not bg_ocr_matching.HAS_NUMPY:
            self.skipTest("numpy is not available")
        img = Image.new("RGB", (8, 8), (255, 0, 0))
        matched, pos = bg_ocr_matching.match_color(img, [255, 0, 0], 0)
        self.assertTrue(matched)
        self.assertEqual(pos, (3, 3))

    def test_template_matching_when_cv2_available(self):
        if not bg_ocr_matching.HAS_CV2:
            self.skipTest("opencv-python is not available")
        img = Image.new("RGB", (8, 8), (255, 0, 0))
        template = bg_ocr_matching._pil_to_bgr(img)
        matched, pos, score = bg_ocr_matching.match_template(img, template, 0.9)
        self.assertTrue(matched)
        self.assertEqual(pos, (4, 4))
        self.assertGreaterEqual(score, 0.9)


if __name__ == "__main__":
    unittest.main()
