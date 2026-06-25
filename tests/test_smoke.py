import unittest

from PIL import Image

import bg_ocr_click
import bg_ocr_matching
import bg_ocr_ocr


class ProjectSmokeTests(unittest.TestCase):
    def test_main_is_console_entry(self):
        self.assertTrue(callable(bg_ocr_click.main))

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
