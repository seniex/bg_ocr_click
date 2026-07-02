import unittest
import os
import inspect
import importlib.util
import tempfile

from PIL import Image

import bg_ocr.compat
import bg_ocr.matching
import bg_ocr.ocr
import bg_ocr.qt.main_window
import bg_ocr_qt


class ProjectSmokeTests(unittest.TestCase):
    def test_qt_uses_shared_action_runtime_module(self):
        import bg_ocr.action_runtime

        self.assertIs(bg_ocr_qt.ACTION_DEFAULTS, bg_ocr.action_runtime.ACTION_DEFAULTS)
        self.assertIs(bg_ocr.compat.ACTION_DEFAULTS, bg_ocr.action_runtime.ACTION_DEFAULTS)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("from bg_ocr.compat import ACTION_DEFAULTS", source)
        self.assertNotIn("from bg_ocr.compat import _is_admin", source)
        self.assertNotIn("_play_sound", source.split("from bg_ocr.compat import", 1)[-1].splitlines()[0])

    def test_qt_uses_shared_monitor_runtime_module(self):
        import bg_ocr.monitor

        self.assertIs(bg_ocr_qt.GroupMonitor, bg_ocr.monitor.GroupMonitor)
        self.assertIs(bg_ocr.compat.GroupMonitor, bg_ocr.monitor.GroupMonitor)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        with open(bg_ocr.compat.__file__, "r", encoding="utf-8") as f:
            tk_source = f.read()
        self.assertNotIn("from bg_ocr.compat import GroupMonitor", qt_source)
        self.assertNotIn("class GroupMonitor", tk_source)

    def test_qt_uses_ui_bridge_module(self):
        import bg_ocr.qt.bridge

        self.assertIs(bg_ocr_qt._UiBridge, bg_ocr.qt.bridge._UiBridge)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.bridge import _UiBridge", qt_source)
        self.assertNotIn("class _UiBridge", qt_source)

    def test_qt_uses_action_sequence_dialog_module(self):
        import bg_ocr.qt.actions

        self.assertIs(bg_ocr_qt._ActionSequenceDialog, bg_ocr.qt.actions._ActionSequenceDialog)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.actions import _ActionSequenceDialog", qt_source)
        self.assertNotIn("class _ActionSequenceDialog", qt_source)

    def test_qt_uses_popup_template_dialog_module(self):
        import bg_ocr.qt.templates

        self.assertIs(bg_ocr_qt._PopupTemplateDialog, bg_ocr.qt.templates._PopupTemplateDialog)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.templates import _PopupTemplateDialog", qt_source)
        self.assertNotIn("class _PopupTemplateDialog", qt_source)

    def test_qt_uses_group_editor_module(self):
        import bg_ocr.qt.group_editor

        self.assertIs(bg_ocr_qt._GroupEditor, bg_ocr.qt.group_editor._GroupEditor)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.group_editor import _GroupEditor", qt_source)
        self.assertNotIn("class _GroupEditor", qt_source)

    def test_qt_uses_group_factory_module(self):
        import bg_ocr.qt.group_editor
        import bg_ocr.qt.group_factory

        self.assertIs(bg_ocr_qt._copy_group, bg_ocr.qt.group_factory._copy_group)
        self.assertIs(bg_ocr.qt.group_editor._copy_group, bg_ocr.qt.group_factory._copy_group)
        for module in [bg_ocr.qt.main_window, bg_ocr.qt.group_editor]:
            with open(module.__file__, "r", encoding="utf-8") as f:
                source = f.read()
            self.assertIn("from bg_ocr.qt.group_factory import _copy_group", source)
            self.assertNotIn("def _copy_group", source)

    def test_qt_group_factory_deep_copies_defaults_and_overrides(self):
        import bg_ocr.qt.group_factory

        first = bg_ocr.qt.group_factory._copy_group({"name": "First", "future_field": {"keep": True}})
        second = bg_ocr.qt.group_factory._copy_group()

        first["popup_templates"].append({"name": "template"})
        first["future_field"]["keep"] = False

        self.assertEqual(first["name"], "First")
        self.assertEqual(first["future_field"], {"keep": False})
        self.assertEqual(second.get("popup_templates"), [])
        self.assertNotIn("future_field", second)

    def test_config_load_defaults_start_on_launch_for_new_and_legacy_configs(self):
        import json

        import bg_ocr.config

        old_config_dir = bg_ocr.config.CONFIG_DIR
        old_config_file = bg_ocr.config.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            try:
                bg_ocr.config.CONFIG_DIR = tmp
                bg_ocr.config.CONFIG_FILE = os.path.join(tmp, "bg_ocr.compat.json")

                fresh = bg_ocr.config.load_config()
                self.assertTrue(fresh["start_on_launch"])
                self.assertEqual(fresh["window_geometry"], bg_ocr.config.DEFAULT_WINDOW_GEOMETRY)
                self.assertEqual(
                    bg_ocr.config.parse_window_geometry(bg_ocr.config.DEFAULT_WINDOW_GEOMETRY),
                    (1180, 860),
                )

                with open(bg_ocr.config.CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"groups": []}, f)
                legacy = bg_ocr.config.load_config()
                self.assertTrue(legacy["start_on_launch"])
                self.assertEqual(legacy["window_geometry"], bg_ocr.config.DEFAULT_WINDOW_GEOMETRY)

                with open(bg_ocr.config.CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"groups": [], "start_on_launch": False}, f)
                self.assertFalse(bg_ocr.config.load_config()["start_on_launch"])
            finally:
                bg_ocr.config.CONFIG_DIR = old_config_dir
                bg_ocr.config.CONFIG_FILE = old_config_file

    def test_qt_uses_settings_editor_module(self):
        import bg_ocr.qt.settings

        self.assertIs(bg_ocr_qt._SettingsEditor, bg_ocr.qt.settings._SettingsEditor)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.settings import _SettingsEditor", qt_source)
        self.assertNotIn("class _SettingsEditor", qt_source)

    def test_qt_uses_theme_module(self):
        import bg_ocr.qt.theme

        self.assertTrue(callable(bg_ocr.qt.theme.apply_theme))
        self.assertTrue(callable(bg_ocr.qt.theme.load_theme))
        self.assertIn("QMainWindow", bg_ocr.qt.theme.load_theme("default"))
        self.assertEqual(bg_ocr.qt.theme.resolve_theme_name("missing"), "default")
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.theme import apply_theme", qt_source)

    def test_qt_sources_do_not_contain_common_chinese_mojibake(self):
        from pathlib import Path

        suspicious = [
            "閸",
            "闁",
            "缂",
            "娴",
            "濞",
            "鐠",
            "榧",
            "顫",
            "閺",
            "绋",
            "顒",
            "鎻愮ず",
            "璇峰厛",
            "閫夋嫨",
            "绐楀彛",
            "宸茬粦",
            "瀹氱獥",
            "瀹歌尙",
        ]
        checked = list(Path(".").glob("bg_ocr_qt*.py")) + [
            Path("REFACTOR_STATUS.md"),
            Path("QT_REFACTOR_REMAINING.md"),
        ]
        offenders = []
        for path in checked:
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), 1):
                if any(ch in line for ch in suspicious) or any("\ue000" <= ch <= "\uf8ff" for ch in line):
                    offenders.append(f"{path}:{line_no}:{line.strip()}")

        self.assertEqual([], offenders)

    def test_qt_key_chinese_ui_strings_are_preserved(self):
        import bg_ocr.qt.tabs
        import bg_ocr.qt.window_setup

        modules = [
            bg_ocr_qt._ImagePickerDialog,
            bg_ocr_qt._WindowPickerDialog,
            bg_ocr_qt._SettingsEditor,
            bg_ocr.qt.tabs._build_home_tab,
            bg_ocr.qt.tabs._build_settings_tab,
            bg_ocr.qt.window_setup._build_status_row,
            bg_ocr.qt.window_setup._build_page_nav,
            bg_ocr.qt.window_setup._build_group_sidebar,
        ]
        source = "\n".join(inspect.getsource(obj) for obj in modules)
        expected = [
            "选择区域",
            "拖拽选择区域，释放后自动确认",
            "点击取样",
            "选择目标窗口",
            "标题关键字",
            "启用音效提示",
            "按进程名自动绑定",
            "以管理员重启",
            "未绑定窗口",
            "开始运行",
            "停止运行",
            "保存快捷配置",
            "清空日志",
            "保存设置",
            "监控组",
            "保存当前组",
        ]
        for text in expected:
            with self.subTest(text=text):
                self.assertIn(text, source)

    def test_qt_theme_files_are_packaged_with_distribution(self):
        import tomllib

        theme_spec = importlib.util.find_spec("themes")
        self.assertIsNotNone(theme_spec, "themes package should be importable")
        self.assertIsNotNone(theme_spec.origin, "themes should be an explicit package")
        self.assertTrue(theme_spec.origin.endswith("__init__.py"), "themes should be an explicit package")

        with open("pyproject.toml", "rb") as f:
            pyproject = tomllib.load(f)
        setuptools_cfg = pyproject["tool"]["setuptools"]
        self.assertIn("themes", setuptools_cfg.get("packages", []))
        self.assertIn("*.qss", setuptools_cfg.get("package-data", {}).get("themes", []))

    def test_root_project_python_files_are_limited_to_qt_entry(self):
        from pathlib import Path

        root_python_files = sorted(path.name for path in Path(".").glob("*.py"))
        self.assertEqual(["bg_ocr_qt.py"], root_python_files)

    def test_qt_theme_loader_falls_back_to_packaged_resources(self):
        import bg_ocr.qt.theme

        old_theme_dir = bg_ocr.qt.theme.THEME_DIR
        bg_ocr.qt.theme.THEME_DIR = os.path.join(old_theme_dir, "missing")
        try:
            default_qss = bg_ocr.qt.theme.load_theme("default")
            self.assertIn("QMainWindow", default_qss)
            self.assertEqual(bg_ocr.qt.theme.load_theme("missing"), default_qss)
        finally:
            bg_ocr.qt.theme.THEME_DIR = old_theme_dir

    def test_qt_apply_theme_returns_resolved_name_and_styles_widget(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        widget = QtWidgets.QWidget()
        try:
            resolved = bg_ocr.qt.theme.apply_theme(widget, "missing")
            self.assertEqual(resolved, "default")
            self.assertIn("QMainWindow", widget.styleSheet())
        finally:
            widget.deleteLater()

    def test_qt_uses_picker_dialogs_module(self):
        import bg_ocr.qt.pickers

        self.assertIs(bg_ocr_qt._ImagePickerDialog, bg_ocr.qt.pickers._ImagePickerDialog)
        self.assertIs(bg_ocr_qt._ScreenPointPickerDialog, bg_ocr.qt.pickers._ScreenPointPickerDialog)
        self.assertIs(bg_ocr_qt._WindowPickerDialog, bg_ocr.qt.pickers._WindowPickerDialog)
        self.assertIs(bg_ocr_qt._wrap, bg_ocr.qt.pickers._wrap)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.pickers import _ImagePickerDialog, _ScreenPointPickerDialog, _WindowPickerDialog, _wrap", qt_source)
        self.assertNotIn("class _ImagePickerDialog", qt_source)
        self.assertNotIn("class _ScreenPointPickerDialog", qt_source)
        self.assertNotIn("class _WindowPickerDialog", qt_source)

    def test_qt_image_picker_info_label_uses_theme_style(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtWidgets

        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._ImagePickerDialog(Image.new("RGB", (8, 8), (0, 0, 0)))
        try:
            self.assertEqual(dialog.objectName(), "imagePickerDialog")
            self.assertEqual(dialog._info.objectName(), "pickerInfo")
            self.assertEqual(dialog._info.styleSheet(), "")
        finally:
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            self.assertIn("QDialog#imagePickerDialog", qss)
            self.assertIn("min-width: 640px", qss)
            self.assertIn("min-height: 420px", qss)
            self.assertIn("QLabel#pickerInfo", qss)

    def test_qt_image_picker_selection_uses_theme_properties(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._ImagePickerDialog(Image.new("RGB", (8, 8), (0, 0, 0)))
        try:
            self.assertEqual(dialog._label.objectName(), "pickerImage")
            self.assertEqual(dialog._label.styleSheet(), "")

            bg_ocr.qt.theme.apply_theme(dialog, "default")
            dialog._label.ensurePolished()
            self.assertEqual(dialog._label.selectionColor.name(), "#255f85")
            self.assertEqual(dialog._label.selectionPenWidth, 2)
        finally:
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            self.assertIn("QLabel#pickerImage", qss)
            self.assertIn("qproperty-selectionColor", qss)
            self.assertIn("qproperty-selectionPenWidth", qss)

    def test_qt_screen_point_picker_overlay_uses_theme_style(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtWidgets

        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._ScreenPointPickerDialog()
        try:
            self.assertEqual(dialog.objectName(), "screenPointOverlay")
            self.assertEqual(dialog.styleSheet(), "")
            self.assertTrue(dialog.testAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground))
            self.assertEqual(dialog._hint_label.objectName(), "screenPointHint")
            self.assertEqual(dialog._hint_label.styleSheet(), "")
            self.assertTrue(dialog._hint_label.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertEqual(dialog._hit_test_fill.alpha(), 1)
        finally:
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            self.assertIn("QDialog#screenPointOverlay", qss)
            self.assertIn("background-color: transparent", qss)
            self.assertNotIn("QDialog#screenPointOverlay {\n  background-color: rgba(0, 0, 0, 45);", qss)
            self.assertIn("QLabel#screenPointHint", qss)

    def test_qt_editor_core_controls_are_covered_by_qss_theme(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme

        required_selectors = [
            "QScrollArea",
            "QSplitter::handle",
            "QListWidget::item",
            "QListWidget::item:selected",
            "QTableWidget::item:selected",
            "QHeaderView::section",
            "QCheckBox",
            "QDialogButtonBox QPushButton",
        ]
        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            for selector in required_selectors:
                with self.subTest(theme=theme, selector=selector):
                    self.assertIn(selector, qss)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        widgets = [
            bg_ocr_qt._ActionSequenceDialog([{"kind": "mouse"}]),
            bg_ocr_qt._PopupTemplateDialog([{"name": "Popup"}]),
            bg_ocr_qt._GroupEditor(),
            bg_ocr_qt._SettingsEditor(),
        ]
        try:
            for widget in widgets:
                with self.subTest(widget=type(widget).__name__):
                    self.assertEqual(widget.styleSheet(), "")
        finally:
            for widget in widgets:
                widget.deleteLater()

    def test_qt_group_editor_field_dimensions_use_theme_rules(self):
        import bg_ocr.qt.group_editor
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.group_editor._GroupEditor)
        self.assertIn('setObjectName("groupEditor")', source)
        self.assertNotIn("setMinimumHeight(120)", source)
        self.assertNotIn("setMinimumWidth(300)", source)

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#groupEditor QPlainTextEdit", qss)
                self.assertIn("QWidget#groupEditor QLineEdit", qss)
                self.assertIn("min-height: 120px", qss)
                self.assertIn("min-width: 72px", qss)
                self.assertIn("max-width: 180px", qss)

    def test_qt_group_editor_uses_named_compact_sections(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            expected = [
                "groupSectionBasic",
                "groupSectionRecognition",
                "groupSectionTarget",
                "groupSectionActions",
                "groupSectionClick",
                "groupSectionChain",
                "groupSectionPopup",
            ]
            found = {w.objectName() for w in editor.findChildren(QtWidgets.QWidget)}
            for name in expected:
                self.assertIn(name, found)
        finally:
            editor.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#groupEditor QGroupBox#groupSectionActions", qss)
                self.assertIn("QWidget#groupEditor QGroupBox#groupSectionClick", qss)
                self.assertIn("QWidget#groupEditor QGroupBox#groupSectionPopup", qss)
                self.assertIn("padding: 12px", qss)

    def test_qt_group_editor_popup_template_controls_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_editor
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.group_editor._GroupEditor)
        self.assertIn('setObjectName("popupTemplatesJson")', source)
        self.assertIn('setObjectName("popupTemplatesEditButton")', source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            self.assertEqual(editor._widgets["popup_templates"].objectName(), "popupTemplatesJson")
            self.assertEqual(editor._popup_templates_edit.objectName(), "popupTemplatesEditButton")
            self.assertEqual(editor._widgets["popup_templates"].styleSheet(), "")
            self.assertEqual(editor._popup_templates_edit.styleSheet(), "")
        finally:
            editor.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#groupEditor QPlainTextEdit#popupTemplatesJson", qss)
                self.assertIn("QWidget#groupEditor QPushButton#popupTemplatesEditButton", qss)
                self.assertIn("min-height: 160px", qss)
                self.assertIn("min-width: 160px", qss)

    def test_qt_group_editor_fields_flow_by_content_width(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.show()
            editor.resize(1180, 700)
            editor.load_group(bg_ocr_qt._copy_group({"type": "ocr"}), 0)
            QtWidgets.QApplication.processEvents()

            basic_layout = editor._section_layouts["groupSectionBasic"]
            self.assertEqual(basic_layout.objectName(), "groupFieldFlow")
            self.assertLessEqual(basic_layout.spacing(), 8)

            first = editor._field_containers["enabled"]
            second = editor._field_containers["name"]
            self.assertGreater(second.geometry().x(), first.geometry().x())
            self.assertLess(second.geometry().x(), first.geometry().right() + 80)

            for key in ["enabled", "name", "type", "interval"]:
                self.assertEqual(editor._field_containers[key].sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Policy.Fixed)
        finally:
            editor.deleteLater()

    def test_qt_group_editor_recognition_keyword_and_language_share_first_row(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.show()
            editor.resize(1180, 700)
            editor.load_group(bg_ocr_qt._copy_group({"type": "ocr"}), 0)
            QtWidgets.QApplication.processEvents()

            keyword_pos = editor._field_containers["keywords"].mapTo(editor, editor._field_containers["keywords"].rect().topLeft())
            language_pos = editor._field_containers["language"].mapTo(editor, editor._field_containers["language"].rect().topLeft())
            engine_pos = editor._field_containers["ocr_engine"].mapTo(editor, editor._field_containers["ocr_engine"].rect().topLeft())

            self.assertEqual(language_pos.y(), keyword_pos.y())
            self.assertGreater(language_pos.x(), keyword_pos.x())
            self.assertGreater(engine_pos.y(), keyword_pos.y())
        finally:
            editor.deleteLater()

    def test_qt_group_editor_hides_popup_options_until_enabled(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        hidden_keys = [
            "popup_only_mode",
            "popup_title_kw",
            "popup_wait_appear",
            "popup_wait_close",
            "popup_total_timeout",
            "popup_no_match_action",
            "popup_templates",
        ]
        try:
            editor.show()
            editor.load_group(bg_ocr_qt._copy_group({"name": "Popup Off", "popup_enabled": False}), 0)
            QtWidgets.QApplication.processEvents()
            for key in hidden_keys:
                self.assertFalse(editor._field_containers[key].isVisible(), key)

            editor._widgets["popup_enabled"].setChecked(True)
            QtWidgets.QApplication.processEvents()
            for key in hidden_keys:
                self.assertTrue(editor._field_containers[key].isVisible(), key)
        finally:
            editor.deleteLater()

    def test_qt_group_editor_spin_boxes_only_wheel_when_focused(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtGui, QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()

        def send_wheel(widget):
            event = QtGui.QWheelEvent(
                QtCore.QPointF(1, 1),
                QtCore.QPointF(1, 1),
                QtCore.QPoint(0, 0),
                QtCore.QPoint(0, 120),
                QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier,
                QtCore.Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            QtWidgets.QApplication.sendEvent(widget, event)

        spin = editor._widgets["interval"]
        try:
            editor.show()
            spin.setValue(2)
            editor.setFocus()
            spin.clearFocus()
            QtWidgets.QApplication.processEvents()
            self.assertFalse(spin.hasFocus())

            send_wheel(spin)
            self.assertEqual(spin.value(), 2)

            spin.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            QtWidgets.QApplication.processEvents()
            self.assertTrue(spin.hasFocus())

            send_wheel(spin)
            self.assertNotEqual(spin.value(), 2)
        finally:
            editor.deleteLater()

    def test_qt_group_editor_combo_boxes_only_wheel_when_focused(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtGui, QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()

        def send_wheel(widget):
            event = QtGui.QWheelEvent(
                QtCore.QPointF(1, 1),
                QtCore.QPointF(1, 1),
                QtCore.QPoint(0, 0),
                QtCore.QPoint(0, 120),
                QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier,
                QtCore.Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            QtWidgets.QApplication.sendEvent(widget, event)

        combo = editor._widgets["type"]
        try:
            editor.show()
            combo.setCurrentText("image")
            editor.setFocus()
            combo.clearFocus()
            QtWidgets.QApplication.processEvents()
            self.assertFalse(combo.hasFocus())

            send_wheel(combo)
            self.assertEqual(combo.currentText(), "image")

            combo.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            QtWidgets.QApplication.processEvents()
            self.assertTrue(combo.hasFocus())

            send_wheel(combo)
            self.assertNotEqual(combo.currentText(), "image")
        finally:
            editor.deleteLater()

    def test_qt_editor_dialog_dimensions_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions
        import bg_ocr.qt.templates
        import bg_ocr.qt.theme

        action_source = inspect.getsource(bg_ocr.qt.actions._ActionSequenceDialog)
        template_source = inspect.getsource(bg_ocr.qt.templates._PopupTemplateDialog)
        self.assertIn('setObjectName("actionSequenceDialog")', action_source)
        self.assertIn('setObjectName("popupTemplateDialog")', template_source)
        self.assertNotIn("resize(1000, 560)", action_source)
        self.assertNotIn("resize(980, 680)", template_source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialogs = [
            bg_ocr_qt._ActionSequenceDialog([{"kind": "mouse"}]),
            bg_ocr_qt._PopupTemplateDialog([{"name": "Popup"}]),
        ]
        try:
            self.assertEqual(dialogs[0].objectName(), "actionSequenceDialog")
            self.assertEqual(dialogs[1].objectName(), "popupTemplateDialog")
            for dialog in dialogs:
                self.assertEqual(dialog.styleSheet(), "")
        finally:
            for dialog in dialogs:
                dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QDialog#actionSequenceDialog", qss)
                self.assertIn("QDialog#popupTemplateDialog", qss)
                self.assertIn("min-width: 1000px", qss)
                self.assertIn("min-height: 560px", qss)
                self.assertIn("min-width: 980px", qss)
                self.assertIn("min-height: 680px", qss)

    def test_qt_popup_template_internal_controls_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.templates
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.templates._PopupTemplateDialog)
        self.assertIn('setObjectName("popupTemplateSplit")', source)
        self.assertIn('setObjectName("popupTemplateList")', source)
        self.assertIn('setObjectName("popupTemplateFormScroll")', source)
        self.assertIn('setObjectName("popupTemplateForm")', source)
        self.assertIn('setObjectName("popupTemplateTextField")', source)
        self.assertIn('setObjectName("popupTemplateToolbarButton")', source)
        self.assertIn('setObjectName("popupTemplateCompactButton")', source)
        self.assertIn('setObjectName("popupTemplateActionsButton")', source)
        self.assertNotIn("setMinimumWidth(220)", source)
        self.assertNotIn("setMinimumWidth(520)", source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr.qt.templates._PopupTemplateDialog([{"name": "Popup", "keywords": "alpha"}])
        try:
            self.assertEqual(dialog._list.objectName(), "popupTemplateList")
            form_scroll = dialog.findChild(QtWidgets.QScrollArea, "popupTemplateFormScroll")
            self.assertIsNotNone(form_scroll)
            self.assertEqual(dialog._fields["name"].objectName(), "popupTemplateTextField")
            self.assertEqual(dialog._fields["template_path"].objectName(), "popupTemplateTextField")
            self.assertEqual(dialog._template_browse.objectName(), "popupTemplateCompactButton")
            self.assertEqual(dialog._add_btn.objectName(), "popupTemplateToolbarButton")
            self.assertEqual(dialog._actions_edit.objectName(), "popupTemplateActionsButton")

            bg_ocr.qt.theme.apply_theme(dialog, "default")
            for widget in [
                dialog._list,
                form_scroll,
                dialog._fields["name"],
                dialog._template_browse,
                dialog._actions_edit,
            ]:
                widget.ensurePolished()
            self.assertGreaterEqual(dialog._list.minimumWidth(), 220)
            self.assertGreaterEqual(form_scroll.minimumWidth(), 520)
            self.assertGreaterEqual(dialog._fields["name"].minimumWidth(), 220)
            self.assertGreaterEqual(dialog._template_browse.minimumWidth(), 64)
            self.assertGreaterEqual(dialog._actions_edit.minimumWidth(), 120)
        finally:
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QDialog#popupTemplateDialog QListWidget#popupTemplateList", qss)
                self.assertIn("QDialog#popupTemplateDialog QScrollArea#popupTemplateFormScroll", qss)
                self.assertIn("QDialog#popupTemplateDialog QLineEdit#popupTemplateTextField", qss)
                self.assertIn("QDialog#popupTemplateDialog QPushButton#popupTemplateToolbarButton", qss)
                self.assertIn("QDialog#popupTemplateDialog QPushButton#popupTemplateCompactButton", qss)
                self.assertIn("QDialog#popupTemplateDialog QPushButton#popupTemplateActionsButton", qss)
                self.assertIn("min-width: 220px", qss)
                self.assertIn("min-width: 520px", qss)
                self.assertIn("min-width: 64px", qss)
                self.assertIn("min-width: 120px", qss)

    def test_qt_action_json_dialog_uses_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.actions._ActionJsonDialog)
        self.assertIn('setObjectName("actionJsonDialog")', source)
        self.assertIn('setObjectName("actionJsonEditor")', source)
        self.assertNotIn("resize(720, 480)", source)
        self.assertNotIn("setMinimumHeight(360)", source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr.qt.actions._ActionJsonDialog([{"kind": "mouse"}])
        try:
            self.assertEqual(dialog.objectName(), "actionJsonDialog")
            self.assertEqual(dialog._edit.objectName(), "actionJsonEditor")
            self.assertEqual(dialog.styleSheet(), "")
            self.assertEqual(dialog._edit.styleSheet(), "")
        finally:
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QDialog#actionJsonDialog", qss)
                self.assertIn("QPlainTextEdit#actionJsonEditor", qss)
                self.assertIn("min-width: 720px", qss)
                self.assertIn("min-height: 480px", qss)
                self.assertIn("min-height: 360px", qss)

    def test_qt_window_picker_dimensions_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.pickers
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.pickers._WindowPickerDialog)
        self.assertIn('setObjectName("windowPickerDialog")', source)
        self.assertNotIn("resize(780, 560)", source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_list_windows = bg_ocr.qt.pickers.list_windows
        bg_ocr.qt.pickers.list_windows = lambda: []
        dialog = bg_ocr_qt._WindowPickerDialog()
        try:
            self.assertEqual(dialog.objectName(), "windowPickerDialog")
            self.assertEqual(dialog.styleSheet(), "")
        finally:
            bg_ocr.qt.pickers.list_windows = old_list_windows
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QDialog#windowPickerDialog", qss)
                self.assertIn("min-width: 780px", qss)
                self.assertIn("min-height: 560px", qss)

    def test_qt_window_picker_internal_controls_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.pickers
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.pickers._WindowPickerDialog)
        self.assertIn('setObjectName("windowPickerFilter")', source)
        self.assertIn('setObjectName("windowPickerList")', source)
        self.assertIn('setObjectName("windowPickerActionButton")', source)
        self.assertNotIn("setMinimumWidth(280)", source)
        self.assertNotIn("setMinimumHeight(320)", source)
        self.assertNotIn("setMinimumWidth(72)", source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_list_windows = bg_ocr.qt.pickers.list_windows
        bg_ocr.qt.pickers.list_windows = lambda: [(101, "Game Client")]
        dialog = bg_ocr.qt.pickers._WindowPickerDialog()
        try:
            self.assertEqual(dialog._filter.objectName(), "windowPickerFilter")
            self.assertEqual(dialog._list.objectName(), "windowPickerList")
            self.assertEqual(dialog._refresh_btn.objectName(), "windowPickerActionButton")
            self.assertEqual(dialog._bind_btn.objectName(), "windowPickerActionButton")
            self.assertEqual(dialog._cancel_btn.objectName(), "windowPickerActionButton")

            bg_ocr.qt.theme.apply_theme(dialog, "default")
            dialog.ensurePolished()
            for widget in [dialog._filter, dialog._list, dialog._refresh_btn, dialog._bind_btn, dialog._cancel_btn]:
                widget.ensurePolished()
            self.assertGreaterEqual(dialog._filter.minimumWidth(), 280)
            self.assertGreaterEqual(dialog._list.minimumHeight(), 320)
            self.assertGreaterEqual(dialog._refresh_btn.minimumWidth(), 72)
            self.assertGreaterEqual(dialog._bind_btn.minimumWidth(), 72)
            self.assertGreaterEqual(dialog._cancel_btn.minimumWidth(), 72)
        finally:
            bg_ocr.qt.pickers.list_windows = old_list_windows
            dialog.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QDialog#windowPickerDialog QLineEdit#windowPickerFilter", qss)
                self.assertIn("QDialog#windowPickerDialog QListWidget#windowPickerList", qss)
                self.assertIn("QDialog#windowPickerDialog QPushButton#windowPickerActionButton", qss)
                self.assertIn("min-width: 280px", qss)
                self.assertIn("min-height: 320px", qss)
                self.assertIn("min-width: 72px", qss)

    def test_qt_uses_tab_builder_module(self):
        import bg_ocr.qt.tabs

        self.assertTrue(callable(bg_ocr.qt.tabs._build_home_tab))
        self.assertTrue(callable(bg_ocr.qt.tabs._build_groups_tab))
        self.assertTrue(callable(bg_ocr.qt.tabs._build_settings_tab))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.tabs import _build_groups_tab, _build_home_tab, _build_settings_tab", qt_source)
        self.assertIn("return _build_home_tab(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._build_home_tab))
        self.assertIn("return _build_groups_tab(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._build_groups_tab))
        self.assertIn("return _build_settings_tab(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._build_settings_tab))

    def test_qt_main_navigation_uses_left_side_labels(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme
        import bg_ocr.qt.window_setup

        self.assertNotIn("setFixedHeight(96)", inspect.getsource(bg_ocr.qt.window_setup._build_page_nav))
        sidebar_source = inspect.getsource(bg_ocr.qt.window_setup._build_group_sidebar)
        self.assertIn('setObjectName("groupList")', sidebar_source)
        self.assertIn('setObjectName("groupSidebarButton")', sidebar_source)
        self.assertIn('setObjectName("groupSidebarSaveButton")', sidebar_source)
        self.assertNotIn("setMinimumHeight(180)", sidebar_source)
        self.assertNotIn("setMinimumWidth(150)", sidebar_source)
        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QListWidget#pageNav", qss)
                self.assertIn("min-height: 96px", qss)
                self.assertIn("max-height: 96px", qss)
                self.assertIn("QWidget#groupSidebar QListWidget#groupList", qss)
                self.assertIn("QWidget#groupSidebar QPushButton#groupSidebarButton", qss)
                self.assertIn("QWidget#groupSidebar QPushButton#groupSidebarSaveButton", qss)
                self.assertIn("min-height: 180px", qss)
                self.assertIn("min-width: 36px", qss)
                self.assertIn("min-width: 150px", qss)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            self.assertIsInstance(win._tabs, QtWidgets.QStackedWidget)
            self.assertEqual([win._page_nav.item(i).text() for i in range(win._page_nav.count())], ["首页", "监控组", "设置"])
            self.assertEqual(win._page_nav.objectName(), "pageNav")
            self.assertEqual(win._group_list.parentWidget().objectName(), "groupSidebar")
            self.assertEqual(win._group_list.objectName(), "groupList")
            self.assertEqual(win._group_add.objectName(), "groupSidebarButton")
            self.assertEqual(win._group_save.objectName(), "groupSidebarSaveButton")
            for widget in [win._group_list, win._group_add, win._group_save]:
                widget.ensurePolished()
            self.assertGreaterEqual(win._group_list.minimumHeight(), 180)
            self.assertGreaterEqual(win._group_add.minimumWidth(), 36)
            self.assertGreaterEqual(win._group_save.minimumWidth(), 150)
            win._page_nav.setCurrentRow(2)
            self.assertEqual(win._tabs.currentIndex(), 2)
            self.assertTrue(win._group_list.isVisible() or not win.isVisible())
        finally:
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_group_sidebar_click_opens_group_detail_page(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First"}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                ]
            }
            win._refresh_group_list()
            win._page_nav.setCurrentRow(2)
            win._show_group_detail(1)
            self.assertEqual(win._page_nav.currentRow(), 1)
            self.assertEqual(win._tabs.currentIndex(), 1)
            self.assertEqual(win._group_list.currentRow(), 1)
            self.assertEqual(win._current_index, 1)
            self.assertEqual(win._group_editor.dump_group(1)["name"], "Second")
        finally:
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_uses_window_setup_module(self):
        import bg_ocr.qt.window_setup

        self.assertTrue(callable(bg_ocr.qt.window_setup._build_ui))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.window_setup import _build_ui", qt_source)
        self.assertIn("return _build_ui(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._build_ui))
        self.assertNotIn("QtWidgets.QTabWidget()", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._build_ui))

    def test_qt_uses_window_lifecycle_module(self):
        import bg_ocr.qt.window_lifecycle

        self.assertTrue(callable(bg_ocr.qt.window_lifecycle._initialize_window))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.window_lifecycle import _initialize_window", qt_source)
        source = inspect.getsource(bg_ocr_qt.BgOcrQtWindow.__init__)
        self.assertIn("_initialize_window(self)", source)
        self.assertNotIn("self.monitors = []", source)
        self.assertNotIn("QTimer.singleShot", source)

    def test_qt_window_lifecycle_initializes_runtime_state(self):
        import bg_ocr.qt.window_lifecycle

        calls = []
        timers = []

        class Signal:
            def __init__(self):
                self.connected = []

            def connect(self, slot):
                self.connected.append(slot.__name__)

        class Bridge:
            def __init__(self):
                self.log_requested = Signal()
                self.invoke_requested = Signal()
                self.status_requested = Signal()

        class Event:
            pass

        class Window:
            def _append_log(self):
                pass

            def _run_in_ui(self):
                pass

            def _set_status(self):
                pass

            def _build_ui(self):
                calls.append("build_ui")

            def _apply_theme(self, name):
                calls.append(("apply_theme", name))

            def _load_from_cfg(self):
                calls.append("load_from_cfg")

            def _start_auto_bind_loop(self):
                calls.append("start_auto_bind_loop")

            def _start(self):
                pass

            def _apply_hotkeys(self):
                pass

            def _refresh_window_title(self):
                calls.append("refresh_window_title")

        def timer_single_shot(ms, fn):
            timers.append((ms, fn.__name__))

        win = Window()
        bg_ocr.qt.window_lifecycle._initialize_window(
            win,
            load_config_func=lambda: {"groups": []},
            bridge_factory=Bridge,
            event_factory=Event,
            timer_single_shot=timer_single_shot,
        )

        self.assertEqual(win.cfg, {"groups": []})
        self.assertEqual(win.monitors, [])
        self.assertFalse(win._running)
        self.assertIsInstance(win._auto_bind_stop, Event)
        self.assertIsNone(win._auto_bind_thread)
        self.assertFalse(win._group_order_dirty)
        self.assertFalse(win._loading_group_editor)
        self.assertEqual(win._current_index, 0)
        self.assertEqual(win._bridge.log_requested.connected, ["_append_log"])
        self.assertEqual(win._bridge.invoke_requested.connected, ["_run_in_ui"])
        self.assertEqual(win._bridge.status_requested.connected, ["_set_status"])
        self.assertEqual(
            calls,
            ["build_ui", ("apply_theme", "default"), "load_from_cfg", "start_auto_bind_loop", "refresh_window_title"],
        )
        self.assertEqual(timers, [(150, "_start"), (250, "_apply_hotkeys")])

    def test_qt_window_lifecycle_respects_start_on_launch_setting(self):
        import bg_ocr.qt.window_lifecycle

        timers = []

        class Signal:
            def connect(self, _slot):
                pass

        class Bridge:
            def __init__(self):
                self.log_requested = Signal()
                self.invoke_requested = Signal()
                self.status_requested = Signal()

        class Event:
            pass

        class Window:
            def _append_log(self):
                pass

            def _run_in_ui(self):
                pass

            def _set_status(self):
                pass

            def _build_ui(self):
                pass

            def _apply_theme(self, _name):
                pass

            def _load_from_cfg(self):
                pass

            def _start_auto_bind_loop(self):
                pass

            def _start(self):
                pass

            def _apply_hotkeys(self):
                pass

            def _refresh_window_title(self):
                pass

        def timer_single_shot(ms, fn):
            timers.append((ms, fn.__name__))

        win = Window()
        bg_ocr.qt.window_lifecycle._initialize_window(
            win,
            load_config_func=lambda: {"groups": [], "start_on_launch": False},
            bridge_factory=Bridge,
            event_factory=Event,
            timer_single_shot=timer_single_shot,
        )

        self.assertEqual(timers, [(250, "_apply_hotkeys")])

    def test_qt_uses_runtime_checks_module(self):
        import bg_ocr.qt.runtime_checks

        self.assertTrue(callable(bg_ocr.qt.runtime_checks._refresh_dependencies))
        self.assertTrue(callable(bg_ocr.qt.runtime_checks._uses_paddle))
        self.assertTrue(callable(bg_ocr.qt.runtime_checks._missing_runtime_dependency))
        self.assertTrue(callable(bg_ocr.qt.runtime_checks._missing_match_dependency))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.runtime_checks import", qt_source)
        self.assertIn("return _refresh_dependencies(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._refresh_dependencies))
        self.assertIn("return _uses_paddle(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._uses_paddle))
        self.assertIn("return _missing_runtime_dependency(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._missing_runtime_dependency))
        self.assertIn("return _missing_match_dependency(self, item, label)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._missing_match_dependency))

    def test_qt_uses_window_binding_module(self):
        import bg_ocr.qt.window_binding

        for name in [
            "_refresh_window_title",
            "_refresh_bound_label",
            "_find_windows",
            "_bind_selected_window",
            "_pick_window_dialog",
            "_bind_window",
        ]:
            self.assertTrue(callable(getattr(bg_ocr.qt.window_binding, name)))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.window_binding import", qt_source)
        self.assertIn("return _refresh_window_title(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._refresh_window_title))
        self.assertIn("return _refresh_bound_label(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._refresh_bound_label))
        self.assertIn("return _find_windows(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._find_windows))
        self.assertIn("return _bind_selected_window(self, hwnd, title)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._bind_selected_window))
        self.assertIn("return _pick_window_dialog(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._pick_window_dialog))
        self.assertIn("return _bind_window(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._bind_window))

    def test_qt_window_binding_filters_and_binds_selected_window(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.window_binding

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        calls = []
        saved = []

        class Window:
            def __init__(self):
                self.cfg = {"target_hwnd": 0, "target_title": ""}
                self._win_list = QtWidgets.QListWidget()
                self._title_filter = QtWidgets.QLineEdit()
                self._bound = QtWidgets.QLabel()

            def _bind_selected_window(self, hwnd, title):
                return bg_ocr.qt.window_binding._bind_selected_window(self, hwnd, title)

            def _refresh_monitor_state(self):
                calls.append("refresh_monitor_state")
                bg_ocr.qt.window_binding._refresh_bound_label(self)

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        old_list = bg_ocr.qt.window_binding.list_windows
        old_save = bg_ocr.qt.window_binding.save_config
        bg_ocr.qt.window_binding.list_windows = lambda: [(100, "Calculator"), (200, "Game Client")]
        bg_ocr.qt.window_binding.save_config = lambda cfg: saved.append(dict(cfg))
        win = Window()
        try:
            win._title_filter.setText("game")
            bg_ocr.qt.window_binding._find_windows(win)
            self.assertEqual(win._win_list.count(), 1)
            self.assertEqual(win._win_list.item(0).text(), "[200] Game Client")

            win._win_list.setCurrentRow(0)
            bg_ocr.qt.window_binding._bind_window(win)
        finally:
            bg_ocr.qt.window_binding.list_windows = old_list
            bg_ocr.qt.window_binding.save_config = old_save
            win._win_list.deleteLater()
            win._title_filter.deleteLater()
            win._bound.deleteLater()

        self.assertEqual(win.cfg["target_hwnd"], 200)
        self.assertEqual(win.cfg["target_title"], "Game Client")
        self.assertEqual(win._title_filter.text(), "Game Client")
        self.assertEqual(win._bound.text(), "Window: [200] Game Client")
        self.assertEqual(saved, [win.cfg])
        self.assertIn("refresh_monitor_state", calls)
        self.assertIn(("log", "Found 1 windows", "info"), calls)
        self.assertIn(("log", "已绑定：[200] Game Client", "ok"), calls)

    def test_qt_window_binding_warns_when_no_window_selected(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.window_binding

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        warnings = []

        class Window:
            def __init__(self):
                self.cfg = {"target_hwnd": 0, "target_title": ""}
                self._win_list = QtWidgets.QListWidget()
                self._title_filter = QtWidgets.QLineEdit()

        old_warning = bg_ocr.qt.window_binding.QtWidgets.QMessageBox.warning
        bg_ocr.qt.window_binding.QtWidgets.QMessageBox.warning = (
            lambda _parent, title, text: warnings.append((title, text))
        )
        win = Window()
        try:
            bg_ocr.qt.window_binding._bind_window(win)
        finally:
            bg_ocr.qt.window_binding.QtWidgets.QMessageBox.warning = old_warning
            win._win_list.deleteLater()
            win._title_filter.deleteLater()

        self.assertEqual(warnings, [("提示", "请先选择窗口")])
        self.assertEqual(win.cfg, {"target_hwnd": 0, "target_title": ""})

    def test_qt_uses_auto_bind_module(self):
        import bg_ocr.qt.auto_bind

        self.assertTrue(callable(bg_ocr.qt.auto_bind._start_auto_bind_loop))
        self.assertTrue(callable(bg_ocr.qt.auto_bind._auto_bind_loop))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.auto_bind import", qt_source)
        self.assertIn(
            "return _start_auto_bind_loop(self)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._start_auto_bind_loop),
        )
        self.assertIn("return _auto_bind_loop(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._auto_bind_loop))

    def test_qt_auto_bind_single_process_window_updates_binding(self):
        import bg_ocr.qt.auto_bind

        calls = []
        saved = []

        class StopEvent:
            def __init__(self):
                self.stopped = False

            def is_set(self):
                return self.stopped

            def wait(self, _seconds):
                self.stopped = True

        class Window:
            def __init__(self):
                self.cfg = {
                    "auto_bind_enabled": True,
                    "auto_bind_process": "game.exe",
                    "target_hwnd": 0,
                    "target_title": "",
                }
                self._auto_bind_stop = StopEvent()

            def after(self, ms, fn):
                calls.append(("after", ms))
                fn()

            def _refresh_monitor_state(self):
                calls.append("refresh_monitor_state")

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        old_list = bg_ocr.qt.auto_bind.list_windows_by_process
        old_save = bg_ocr.qt.auto_bind.save_config
        bg_ocr.qt.auto_bind.list_windows_by_process = lambda proc: [(12345, "Game Window")]
        bg_ocr.qt.auto_bind.save_config = lambda cfg: saved.append(dict(cfg))
        win = Window()
        try:
            bg_ocr.qt.auto_bind._auto_bind_loop(win)
        finally:
            bg_ocr.qt.auto_bind.list_windows_by_process = old_list
            bg_ocr.qt.auto_bind.save_config = old_save

        self.assertEqual(win.cfg["target_hwnd"], 12345)
        self.assertEqual(win.cfg["target_title"], "Game Window")
        self.assertEqual(saved, [win.cfg])
        self.assertIn("refresh_monitor_state", calls)
        self.assertTrue(any(call[0] == "log" and call[2] == "ok" for call in calls if isinstance(call, tuple)))

    def test_qt_auto_bind_multiple_process_windows_warns_without_binding(self):
        import bg_ocr.qt.auto_bind

        calls = []
        saved = []

        class StopEvent:
            def __init__(self):
                self.stopped = False

            def is_set(self):
                return self.stopped

            def wait(self, _seconds):
                self.stopped = True

        class Window:
            def __init__(self):
                self.cfg = {
                    "auto_bind_enabled": True,
                    "auto_bind_process": "game.exe",
                    "target_hwnd": 0,
                    "target_title": "",
                }
                self._auto_bind_stop = StopEvent()

            def after(self, ms, fn):
                calls.append(("after", ms))
                fn()

            def _refresh_monitor_state(self):
                calls.append("refresh_monitor_state")

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        old_list = bg_ocr.qt.auto_bind.list_windows_by_process
        old_save = bg_ocr.qt.auto_bind.save_config
        bg_ocr.qt.auto_bind.list_windows_by_process = lambda proc: [
            (100, "Game Window A"),
            (200, "Game Window B"),
        ]
        bg_ocr.qt.auto_bind.save_config = lambda cfg: saved.append(dict(cfg))
        win = Window()
        try:
            bg_ocr.qt.auto_bind._auto_bind_loop(win)
        finally:
            bg_ocr.qt.auto_bind.list_windows_by_process = old_list
            bg_ocr.qt.auto_bind.save_config = old_save

        self.assertEqual(win.cfg["target_hwnd"], 0)
        self.assertEqual(win.cfg["target_title"], "")
        self.assertEqual(saved, [])
        self.assertNotIn("refresh_monitor_state", calls)
        self.assertIn(("log", "[auto-bind] process game.exe has 2 windows; bind manually", "warn"), calls)

    def test_qt_uses_hotkey_module(self):
        import bg_ocr.qt.hotkeys
        import bg_ocr.qt.shutdown

        self.assertTrue(callable(bg_ocr.qt.hotkeys._apply_hotkeys))
        self.assertTrue(callable(bg_ocr.qt.hotkeys._clear_hotkeys))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.hotkeys import", qt_source)
        self.assertIn("return _apply_hotkeys(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._apply_hotkeys))
        self.assertIn("return _clear_hotkeys()", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._clear_hotkeys))
        self.assertIn("win._clear_hotkeys()", inspect.getsource(bg_ocr.qt.shutdown._on_close))

    def test_qt_hotkeys_register_start_stop_callbacks(self):
        import sys
        import types

        import bg_ocr.qt.hotkeys

        calls = []
        registered = {}

        fake_keyboard = types.SimpleNamespace(
            unhook_all_hotkeys=lambda: calls.append("clear_hotkeys"),
            add_hotkey=lambda key, callback: registered.setdefault(key, callback),
        )

        sentinel = object()
        old_keyboard = sys.modules.get("keyboard", sentinel)
        sys.modules["keyboard"] = fake_keyboard

        class Window:
            def __init__(self):
                self.cfg = {"hotkey_start": "f8", "hotkey_stop": "f9"}

            def after(self, ms, fn):
                calls.append(("after", ms, fn.__name__))
                fn()

            def _start(self):
                calls.append("start")

            def _stop(self):
                calls.append("stop")

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        try:
            win = Window()
            bg_ocr.qt.hotkeys._apply_hotkeys(win)
            registered["f8"]()
            registered["f9"]()
        finally:
            if old_keyboard is sentinel:
                sys.modules.pop("keyboard", None)
            else:
                sys.modules["keyboard"] = old_keyboard

        self.assertEqual(set(registered), {"f8", "f9"})
        self.assertIn("clear_hotkeys", calls)
        self.assertIn(("after", 0, "_start"), calls)
        self.assertIn(("after", 0, "_stop"), calls)
        self.assertIn("start", calls)
        self.assertIn("stop", calls)
        self.assertTrue(any(call[0] == "log" and call[2] == "ok" for call in calls if isinstance(call, tuple)))

    def test_qt_hotkeys_clear_without_registration_when_unconfigured(self):
        import sys
        import types

        import bg_ocr.qt.hotkeys

        calls = []
        fake_keyboard = types.SimpleNamespace(
            unhook_all_hotkeys=lambda: calls.append("clear_hotkeys"),
            add_hotkey=lambda key, callback: calls.append(("add_hotkey", key, callback)),
        )

        sentinel = object()
        old_keyboard = sys.modules.get("keyboard", sentinel)
        sys.modules["keyboard"] = fake_keyboard

        class Window:
            cfg = {"hotkey_start": "", "hotkey_stop": ""}

            def after(self, ms, fn):
                calls.append(("after", ms, fn.__name__))

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        try:
            bg_ocr.qt.hotkeys._apply_hotkeys(Window())
        finally:
            if old_keyboard is sentinel:
                sys.modules.pop("keyboard", None)
            else:
                sys.modules["keyboard"] = old_keyboard

        self.assertEqual(calls, ["clear_hotkeys"])

    def test_qt_uses_shutdown_module(self):
        import bg_ocr.qt.shutdown

        self.assertTrue(callable(bg_ocr.qt.shutdown._close_event))
        self.assertTrue(callable(bg_ocr.qt.shutdown._on_close))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.shutdown import", qt_source)
        self.assertIn("return _close_event(self, event)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow.closeEvent))
        self.assertIn("return _on_close(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._on_close))

    def test_qt_uses_group_coordinator_module(self):
        import bg_ocr.qt.group_coordinator

        for name in [
            "_load_group_editor",
            "_on_group_changed",
            "_save_current_group",
            "_save_group_config",
        ]:
            self.assertTrue(callable(getattr(bg_ocr.qt.group_coordinator, name)))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.group_coordinator import", qt_source)
        self.assertIn(
            "return _load_group_editor(self, index)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._load_group_editor),
        )
        self.assertIn(
            "return _on_group_changed(self, index)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._on_group_changed),
        )
        self.assertIn(
            "return _save_current_group(self)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._save_current_group),
        )
        self.assertIn(
            "return _save_group_config(self)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._save_group_config),
        )

    def test_qt_save_group_config_with_no_groups_keeps_selection_empty(self):
        import bg_ocr.qt.group_coordinator

        calls = []
        saved = []

        class GroupList:
            def setCurrentRow(self, row):
                if row < 0:
                    raise AssertionError("empty group save should not select a negative row")
                calls.append(("setCurrentRow", row))

        class Window:
            def __init__(self):
                self.cfg = {"groups": []}
                self._current_index = 0
                self._group_list = GroupList()

            def _save_current_group(self):
                calls.append("save_current_group")

            def _refresh_group_list(self):
                calls.append("refresh_group_list")

            def _refresh_quick_config(self):
                calls.append("refresh_quick_config")

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        old_save = bg_ocr.qt.group_coordinator.save_config
        bg_ocr.qt.group_coordinator.save_config = lambda cfg: saved.append(dict(cfg))
        try:
            bg_ocr.qt.group_coordinator._save_group_config(Window())
        finally:
            bg_ocr.qt.group_coordinator.save_config = old_save

        self.assertEqual(saved, [{"groups": []}])
        self.assertEqual(
            calls,
            [
                "save_current_group",
                "refresh_group_list",
                "refresh_quick_config",
                ("log", "Group config saved", "ok"),
            ],
        )

    def test_qt_uses_group_manager_module(self):
        import bg_ocr.qt.group_manager

        for name in [
            "_add_group",
            "_delete_group",
            "_move_group",
            "_save_quick_config",
            "_show_quick_group_detail",
            "_build_quick_template_cell",
        ]:
            self.assertTrue(callable(getattr(bg_ocr.qt.group_manager, name)))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.group_manager import", qt_source)
        self.assertIn("return _add_group(self, save_config, _copy_group)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._add_group))
        self.assertIn("return _delete_group(self, save_config)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._delete_group))
        self.assertIn(
            "return _move_group(self, direction, save_config)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._move_group),
        )
        self.assertIn(
            "return _save_quick_config(self, save_config)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._save_quick_config),
        )
        self.assertIn(
            "return _show_quick_group_detail(self, pos)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._show_quick_group_detail),
        )

    def test_qt_uses_state_module(self):
        self.assertIsNotNone(importlib.util.find_spec("bg_ocr.qt.state"), "bg_ocr.qt.state module should exist")
        import bg_ocr.qt.state

        for name in [
            "_load_from_cfg",
            "_refresh_group_list",
            "_refresh_quick_config",
            "_mark_dirty",
            "_run_in_ui",
            "_append_log",
            "_set_status",
            "_play_if",
            "_save_settings",
        ]:
            self.assertTrue(callable(getattr(bg_ocr.qt.state, name)))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.state import", qt_source)
        self.assertIn("return _load_from_cfg(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._load_from_cfg))
        self.assertIn("return _refresh_group_list(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._refresh_group_list))
        self.assertIn("return _refresh_quick_config(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._refresh_quick_config))
        self.assertIn("return _mark_dirty(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._mark_dirty))
        self.assertIn("return _run_in_ui(self, fn)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._run_in_ui))
        self.assertIn("return _append_log(self, msg, tag)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._append_log))
        self.assertIn("return _set_status(self, running)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._set_status))
        self.assertIn("return _play_if(self, event)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._play_if))
        self.assertIn("return _save_settings(self, save_config)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._save_settings))

    def test_qt_status_dot_uses_theme_property_not_inline_style(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.state
        import bg_ocr.qt.theme
        import bg_ocr.qt.window_setup

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        class Window:
            def __init__(self):
                self._status = QtWidgets.QLabel()
                self._status_dot = QtWidgets.QLabel("*")
                self._start_btn = QtWidgets.QPushButton()
                self._stop_btn = QtWidgets.QPushButton()

        win = Window()
        try:
            bg_ocr.qt.state._set_status(win, True)
            self.assertEqual(win._status.text(), "Running")
            self.assertTrue(win._status_dot.property("running"))
            self.assertEqual(win._status_dot.styleSheet(), "")
            self.assertFalse(win._start_btn.isEnabled())
            self.assertTrue(win._stop_btn.isEnabled())

            bg_ocr.qt.state._set_status(win, False)
            self.assertEqual(win._status.text(), "Stopped")
            self.assertFalse(win._status_dot.property("running"))
            self.assertEqual(win._status_dot.styleSheet(), "")
        finally:
            win._status.deleteLater()
            win._status_dot.deleteLater()
            win._start_btn.deleteLater()
            win._stop_btn.deleteLater()

        self.assertIn('setObjectName("statusDot")', inspect.getsource(bg_ocr.qt.window_setup._build_status_row))
        self.assertIn('QLabel#statusDot[running="true"]', bg_ocr.qt.theme.load_theme("default"))
        self.assertIn('QLabel#statusDot[running="false"]', bg_ocr.qt.theme.load_theme("default"))
        self.assertIn('QLabel#statusDot[running="true"]', bg_ocr.qt.theme.load_theme("modern"))
        self.assertIn('QLabel#statusDot[running="false"]', bg_ocr.qt.theme.load_theme("modern"))

    def test_qt_status_row_controls_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme
        import bg_ocr.qt.window_setup

        source = inspect.getsource(bg_ocr.qt.window_setup._build_status_row)
        self.assertIn('setObjectName("runtimeStatusLabel")', source)
        self.assertIn('setObjectName("adminStatusLabel")', source)
        self.assertIn('setObjectName("boundWindowLabel")', source)
        self.assertIn('setObjectName("runtimeControlButton")', source)
        self.assertNotIn("setMinimumWidth(220)", source)
        self.assertNotIn("setMinimumWidth(88)", source)

        class Window:
            def _start(self):
                pass

            def _stop(self):
                pass

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = Window()
        container = QtWidgets.QWidget()
        try:
            container.setLayout(bg_ocr.qt.window_setup._build_status_row(win))
            self.assertEqual(win._status.objectName(), "runtimeStatusLabel")
            self.assertEqual(win._admin_status.objectName(), "adminStatusLabel")
            self.assertEqual(win._bound.objectName(), "boundWindowLabel")
            self.assertEqual(win._start_btn.objectName(), "runtimeControlButton")
            self.assertEqual(win._stop_btn.objectName(), "runtimeControlButton")

            bg_ocr.qt.theme.apply_theme(container, "default")
            container.ensurePolished()
            for widget in [win._bound, win._start_btn, win._stop_btn]:
                widget.ensurePolished()
            self.assertGreaterEqual(win._bound.minimumWidth(), 220)
            self.assertGreaterEqual(win._start_btn.minimumWidth(), 88)
            self.assertGreaterEqual(win._stop_btn.minimumWidth(), 88)
        finally:
            container.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QLabel#boundWindowLabel", qss)
                self.assertIn("QPushButton#runtimeControlButton", qss)
                self.assertIn("min-width: 220px", qss)
                self.assertIn("min-width: 88px", qss)

    def test_qt_home_log_panel_uses_theme_sizing(self):
        import bg_ocr.qt.tabs
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.tabs._build_home_tab)
        self.assertIn('setObjectName("homeLog")', source)
        self.assertIn('setObjectName("windowDetailList")', source)
        self.assertNotIn("setMinimumHeight(260)", source)

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QTextEdit#homeLog", qss)
                self.assertIn("min-height: 260px", qss)
                self.assertIn("QListWidget#windowDetailList", qss)
                self.assertIn("max-height: 130px", qss)

    def test_qt_home_window_binding_controls_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.tabs
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.tabs._build_home_tab)
        self.assertIn('setObjectName("homeTab")', source)
        self.assertIn('setObjectName("windowTitleFilter")', source)
        self.assertIn('setObjectName("windowBindButton")', source)
        self.assertIn('setObjectName("quickConfigActionButton")', source)
        self.assertIn('setObjectName("homeLogClearButton")', source)
        self.assertNotIn("setMinimumWidth(220)", source)
        self.assertNotIn("setMinimumWidth(88)", source)
        self.assertNotIn("setMinimumWidth(112)", source)
        self.assertNotIn("setMinimumWidth(96)", source)

        class Window:
            cfg = {"target_title": "Game"}

            def _find_windows(self):
                pass

            def _bind_window(self):
                pass

            def _pick_window_dialog(self):
                pass

            def _show_quick_group_detail(self, _pos):
                pass

            def _save_quick_config(self):
                pass

            def _refresh_quick_config(self):
                pass

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = Window()
        root = bg_ocr.qt.tabs._build_home_tab(win)
        try:
            self.assertEqual(root.objectName(), "homeTab")
            self.assertEqual(win._title_filter.objectName(), "windowTitleFilter")
            self.assertEqual(win._bind_find.objectName(), "windowBindButton")
            self.assertEqual(win._bind_pick.objectName(), "windowBindButton")
            self.assertEqual(win._bind_dialog.objectName(), "windowBindButton")
            self.assertEqual(win._quick_save.objectName(), "quickConfigActionButton")
            self.assertEqual(win._quick_refresh.objectName(), "quickConfigActionButton")
            self.assertEqual(win._log_clear.objectName(), "homeLogClearButton")

            bg_ocr.qt.theme.apply_theme(root, "default")
            for widget in [
                win._title_filter,
                win._bind_find,
                win._bind_pick,
                win._bind_dialog,
                win._quick_save,
                win._quick_refresh,
                win._log_clear,
            ]:
                widget.ensurePolished()
            self.assertGreaterEqual(win._title_filter.minimumWidth(), 220)
            self.assertGreaterEqual(win._bind_find.minimumWidth(), 88)
            self.assertGreaterEqual(win._quick_save.minimumWidth(), 112)
            self.assertGreaterEqual(win._log_clear.minimumWidth(), 96)
        finally:
            root.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#homeTab QLineEdit#windowTitleFilter", qss)
                self.assertIn("QWidget#homeTab QPushButton#windowBindButton", qss)
                self.assertIn("QWidget#homeTab QPushButton#quickConfigActionButton", qss)
                self.assertIn("QWidget#homeTab QPushButton#homeLogClearButton", qss)
                self.assertIn("min-width: 220px", qss)
                self.assertIn("min-width: 88px", qss)
                self.assertIn("min-width: 112px", qss)
                self.assertIn("min-width: 96px", qss)

    def test_qt_settings_dependency_panel_uses_theme_sizing(self):
        import bg_ocr.qt.tabs
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.tabs._build_settings_tab)
        self.assertIn('setObjectName("dependencyStatus")', source)
        self.assertNotIn("setMinimumHeight(140)", source)

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QPlainTextEdit#dependencyStatus", qss)
                self.assertIn("min-height: 140px", qss)

    def test_qt_settings_save_button_uses_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.tabs
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.tabs._build_settings_tab)
        self.assertIn('setObjectName("settingsTab")', source)
        self.assertIn('setObjectName("settingsSaveButton")', source)
        self.assertNotIn("setMinimumWidth(112)", source)

        class Window(QtWidgets.QWidget):
            def _save_settings(self):
                pass

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = Window()
        root = bg_ocr.qt.tabs._build_settings_tab(win)
        try:
            self.assertEqual(root.objectName(), "settingsTab")
            self.assertEqual(win._save_settings_btn.objectName(), "settingsSaveButton")

            bg_ocr.qt.theme.apply_theme(root, "default")
            root.ensurePolished()
            win._save_settings_btn.ensurePolished()
            self.assertGreaterEqual(win._save_settings_btn.minimumWidth(), 112)
        finally:
            root.deleteLater()
            win.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#settingsTab QPushButton#settingsSaveButton", qss)
                self.assertIn("min-width: 112px", qss)

    def test_qt_settings_path_controls_use_theme_rules(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.settings
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.settings._SettingsEditor)
        self.assertIn('setObjectName("settingsEditor")', source)
        self.assertIn('setObjectName("settingsPathField")', source)
        self.assertIn('setObjectName("settingsBrowseButton")', source)
        self.assertIn('setObjectName("settingsSoundTestButton")', source)
        self.assertNotIn("setMinimumWidth(280)", source)
        self.assertNotIn("setMinimumWidth(64)", source)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.settings._SettingsEditor()
        try:
            self.assertEqual(editor.objectName(), "settingsEditor")
            path_fields = [
                editor._widgets["tesseract_path"],
                editor._widgets["paddle_exe_path"],
                editor._widgets["sound_file"],
            ]
            browse_buttons = [
                editor._widgets["paddle_exe_browse"],
                editor._widgets["tess_browse"],
                editor._widgets["sound_browse"],
            ]
            self.assertTrue(all(widget.objectName() == "settingsPathField" for widget in path_fields))
            self.assertTrue(all(widget.objectName() == "settingsBrowseButton" for widget in browse_buttons))
            self.assertEqual(editor._widgets["sound_test"].objectName(), "settingsSoundTestButton")

            bg_ocr.qt.theme.apply_theme(editor, "default")
            editor.ensurePolished()
            for widget in path_fields + browse_buttons + [editor._widgets["sound_test"]]:
                widget.ensurePolished()
            self.assertGreaterEqual(editor._widgets["tesseract_path"].minimumWidth(), 280)
            self.assertGreaterEqual(editor._widgets["paddle_exe_browse"].minimumWidth(), 64)
            self.assertGreaterEqual(editor._widgets["sound_test"].minimumWidth(), 64)
        finally:
            editor.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#settingsEditor QLineEdit#settingsPathField", qss)
                self.assertIn("QWidget#settingsEditor QPushButton#settingsBrowseButton", qss)
                self.assertIn("QWidget#settingsEditor QPushButton#settingsSoundTestButton", qss)
                self.assertIn("min-width: 280px", qss)
                self.assertIn("min-width: 64px", qss)

    def test_qt_uses_runtime_adapter_module(self):
        import bg_ocr.qt.runtime_adapter

        for name in [
            "_current_group_index",
            "_current_hwnd",
            "_after",
            "_log",
        ]:
            self.assertTrue(callable(getattr(bg_ocr.qt.runtime_adapter, name)))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.runtime_adapter import", qt_source)
        self.assertIn(
            "return _current_group_index(self)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow.current_group_index),
        )
        self.assertIn("return _current_hwnd(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow.current_hwnd))
        self.assertIn("return _after(self, ms, fn)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow.after))
        self.assertIn("return _log(self, msg, tag)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow.log))

    def test_qt_runtime_adapter_forwards_runtime_callbacks(self):
        import bg_ocr.qt.runtime_adapter

        class Signal:
            def __init__(self):
                self.emitted = []

            def emit(self, *args):
                self.emitted.append(args)

        class Bridge:
            def __init__(self):
                self.log_requested = Signal()
                self.invoke_requested = Signal()

        class Window:
            def __init__(self):
                self._current_index = -3
                self.cfg = {"target_hwnd": 12345}
                self._bridge = Bridge()

        class Timer:
            def __init__(self, seconds, callback):
                self.seconds = seconds
                self.callback = callback
                self.started = False

            def start(self):
                self.started = True
                self.callback()

        timers = []

        def timer_factory(seconds, callback):
            timer = Timer(seconds, callback)
            timers.append(timer)
            return timer

        win = Window()
        callback = object()

        self.assertEqual(bg_ocr.qt.runtime_adapter._current_group_index(win), 0)
        self.assertEqual(bg_ocr.qt.runtime_adapter._current_hwnd(win), 12345)
        bg_ocr.qt.runtime_adapter._log(win, "hello", "ok")
        bg_ocr.qt.runtime_adapter._after(win, 250, callback, timer_factory=timer_factory)

        self.assertEqual(win._bridge.log_requested.emitted, [("hello", "ok")])
        self.assertEqual(win._bridge.invoke_requested.emitted, [(callback,)])
        self.assertEqual(len(timers), 1)
        self.assertEqual(timers[0].seconds, 0.25)
        self.assertTrue(timers[0].started)

    def test_qt_runtime_adapter_ignores_deleted_bridge_timer_callbacks(self):
        import bg_ocr.qt.runtime_adapter

        class Signal:
            def emit(self, *_args):
                raise RuntimeError("wrapped C/C++ object of type _UiBridge has been deleted")

        class Bridge:
            def __init__(self):
                self.invoke_requested = Signal()

        class Window:
            def __init__(self):
                self._bridge = Bridge()

        class Timer:
            def __init__(self, _seconds, callback):
                self.callback = callback

            def start(self):
                self.callback()

        bg_ocr.qt.runtime_adapter._after(Window(), 1, object(), timer_factory=Timer)

    def test_qt_runtime_adapter_clamps_negative_after_delay(self):
        import bg_ocr.qt.runtime_adapter

        seconds_seen = []

        class Signal:
            def emit(self, *_args):
                pass

        class Bridge:
            def __init__(self):
                self.invoke_requested = Signal()

        class Window:
            def __init__(self):
                self._bridge = Bridge()

        class Timer:
            def __init__(self, seconds, callback):
                seconds_seen.append(seconds)
                self.callback = callback

            def start(self):
                self.callback()

        bg_ocr.qt.runtime_adapter._after(Window(), -250, object(), timer_factory=Timer)

        self.assertEqual(seconds_seen, [0])

    def test_qt_save_settings_updates_config_and_refreshes_runtime(self):
        self.assertIsNotNone(importlib.util.find_spec("bg_ocr.qt.state"), "bg_ocr.qt.state module should exist")
        import bg_ocr.qt.state

        calls = []
        saved = []

        class SettingsEditor:
            def dump_settings(self):
                calls.append("dump_settings")
                return {"sound_enabled": True, "theme": "modern"}

        class Window:
            def __init__(self):
                self.cfg = {"groups": []}
                self._settings_editor = SettingsEditor()

            def _save_current_group(self):
                calls.append("save_current_group")

            def _apply_hotkeys(self):
                calls.append("apply_hotkeys")

            def _refresh_monitor_state(self):
                calls.append("refresh_monitor_state")

            def _apply_theme(self, name=None):
                calls.append(("apply_theme", name))

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        old_info = bg_ocr.qt.state.QtWidgets.QMessageBox.information
        bg_ocr.qt.state.QtWidgets.QMessageBox.information = lambda *_args: calls.append("message_box")
        try:
            bg_ocr.qt.state._save_settings(Window(), lambda cfg: saved.append(dict(cfg)))
        finally:
            bg_ocr.qt.state.QtWidgets.QMessageBox.information = old_info

        self.assertEqual(
            calls,
            [
                "save_current_group",
                "dump_settings",
                ("apply_theme", "modern"),
                "apply_hotkeys",
                "refresh_monitor_state",
                ("log", "Settings saved", "ok"),
                "message_box",
            ],
        )
        self.assertEqual(saved, [{"groups": [], "sound_enabled": True, "theme": "modern"}])

    def test_qt_shutdown_saves_state_and_stops_helpers(self):
        import bg_ocr.qt.shutdown

        calls = []
        saved = []

        class StopEvent:
            def __init__(self):
                self.was_set = False

            def set(self):
                self.was_set = True

        class SettingsEditor:
            def dump_settings(self):
                calls.append("dump_settings")
                return {"capture_mode": "auto"}

        class Window:
            def __init__(self):
                self.cfg = {"groups": []}
                self._settings_editor = SettingsEditor()
                self._auto_bind_stop = StopEvent()

            def _stop(self):
                calls.append("stop")

            def _save_current_group(self):
                calls.append("save_current_group")

            def _clear_hotkeys(self):
                calls.append("clear_hotkeys")

            def width(self):
                return 640

            def height(self):
                return 480

        old_save = bg_ocr.qt.shutdown.save_config
        bg_ocr.qt.shutdown.save_config = lambda cfg: saved.append(dict(cfg))
        win = Window()
        try:
            bg_ocr.qt.shutdown._on_close(win)
        finally:
            bg_ocr.qt.shutdown.save_config = old_save

        self.assertEqual(calls, ["stop", "save_current_group", "dump_settings", "clear_hotkeys"])
        self.assertTrue(win._auto_bind_stop.was_set)
        self.assertEqual(win.cfg["capture_mode"], "auto")
        self.assertEqual(win.cfg["window_geometry"], "640x480")
        self.assertEqual(saved, [win.cfg])

    def test_qt_shutdown_tolerates_settings_dump_failure(self):
        import bg_ocr.qt.shutdown

        calls = []
        saved = []

        class SettingsEditor:
            def dump_settings(self):
                calls.append("dump_settings")
                raise RuntimeError("settings unavailable")

        class Window:
            def __init__(self):
                self.cfg = {"groups": [], "capture_mode": "printwindow"}
                self._settings_editor = SettingsEditor()

            def _stop(self):
                calls.append("stop")

            def _save_current_group(self):
                calls.append("save_current_group")

            def _clear_hotkeys(self):
                calls.append("clear_hotkeys")

            def width(self):
                return 800

            def height(self):
                return 600

        old_save = bg_ocr.qt.shutdown.save_config
        bg_ocr.qt.shutdown.save_config = lambda cfg: saved.append(dict(cfg))
        win = Window()
        try:
            bg_ocr.qt.shutdown._on_close(win)
        finally:
            bg_ocr.qt.shutdown.save_config = old_save

        self.assertEqual(calls, ["stop", "save_current_group", "dump_settings", "clear_hotkeys"])
        self.assertEqual(win.cfg["capture_mode"], "printwindow")
        self.assertEqual(win.cfg["window_geometry"], "800x600")
        self.assertEqual(saved, [win.cfg])

    def test_qt_uses_monitor_lifecycle_module(self):
        import bg_ocr.qt.monitor_lifecycle

        self.assertTrue(callable(bg_ocr.qt.monitor_lifecycle._refresh_monitor_state))
        self.assertTrue(callable(bg_ocr.qt.monitor_lifecycle._start))
        self.assertTrue(callable(bg_ocr.qt.monitor_lifecycle._stop))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.monitor_lifecycle import", qt_source)
        self.assertIn(
            "return _refresh_monitor_state(self)",
            inspect.getsource(bg_ocr_qt.BgOcrQtWindow._refresh_monitor_state),
        )
        self.assertIn("return _start(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._start))
        self.assertIn("return _stop(self)", inspect.getsource(bg_ocr_qt.BgOcrQtWindow._stop))

    def test_qt_monitor_start_stop_updates_runtime_state(self):
        import bg_ocr.qt.monitor_lifecycle

        calls = []
        saved = []
        created = []

        class SettingsEditor:
            def dump_settings(self):
                calls.append("dump_settings")
                return {"capture_mode": "printwindow"}

        class Monitor:
            def __init__(self, _win, index):
                self.index = index
                self.started = False
                self.stopped = False
                created.append(self)

            def start(self):
                self.started = True
                calls.append(("monitor_start", self.index))

            def stop(self):
                self.stopped = True
                calls.append(("monitor_stop", self.index))

        class PaddleEngine:
            def stop(self):
                calls.append("paddle_stop")

        class Window:
            def __init__(self):
                self.cfg = {
                    "target_hwnd": 12345,
                    "groups": [
                        {"enabled": True},
                        {"enabled": False},
                    ],
                }
                self.monitors = []
                self._running = False
                self._settings_editor = SettingsEditor()

            def _save_current_group(self):
                calls.append("save_current_group")

            def _missing_runtime_dependency(self):
                return ""

            def _uses_paddle(self):
                return False

            def _set_status(self, running):
                calls.append(("set_status", running))

            def log(self, msg, tag="info"):
                calls.append(("log", msg, tag))

        old_monitor = bg_ocr.qt.monitor_lifecycle.GroupMonitor
        old_save = bg_ocr.qt.monitor_lifecycle.save_config
        old_paddle = bg_ocr.qt.monitor_lifecycle._paddle_engine
        bg_ocr.qt.monitor_lifecycle.GroupMonitor = Monitor
        bg_ocr.qt.monitor_lifecycle.save_config = lambda cfg: saved.append(dict(cfg))
        bg_ocr.qt.monitor_lifecycle._paddle_engine = PaddleEngine()
        win = Window()
        try:
            bg_ocr.qt.monitor_lifecycle._start(win)
            bg_ocr.qt.monitor_lifecycle._stop(win)
        finally:
            bg_ocr.qt.monitor_lifecycle.GroupMonitor = old_monitor
            bg_ocr.qt.monitor_lifecycle.save_config = old_save
            bg_ocr.qt.monitor_lifecycle._paddle_engine = old_paddle

        self.assertFalse(win._running)
        self.assertEqual(win.monitors, [])
        self.assertEqual(len(created), 2)
        self.assertTrue(created[0].started)
        self.assertFalse(created[1].started)
        self.assertTrue(all(m.stopped for m in created))
        self.assertIn("save_current_group", calls)
        self.assertIn("dump_settings", calls)
        self.assertEqual(saved[0]["capture_mode"], "printwindow")
        self.assertIn(("set_status", True), calls)
        self.assertIn(("set_status", False), calls)
        self.assertIn(("log", "Started 1 enabled groups", "ok"), calls)
        self.assertIn(("log", "Stopped", "warn"), calls)
        self.assertIn("paddle_stop", calls)

    def test_qt_monitor_start_preflight_warnings_do_not_start_runtime(self):
        import bg_ocr.qt.monitor_lifecycle

        saved = []
        warnings = []

        class SettingsEditor:
            def dump_settings(self):
                return {"capture_mode": "printwindow"}

        class Window:
            def __init__(self, cfg, missing="", uses_paddle=False):
                self.cfg = cfg
                self.monitors = []
                self._running = False
                self._settings_editor = SettingsEditor()
                self._missing = missing
                self._uses_paddle_value = uses_paddle
                self.calls = []

            def _save_current_group(self):
                self.calls.append("save_current_group")

            def _missing_runtime_dependency(self):
                return self._missing

            def _uses_paddle(self):
                return self._uses_paddle_value

            def _set_status(self, running):
                self.calls.append(("set_status", running))

            def log(self, msg, tag="info"):
                self.calls.append(("log", msg, tag))

        cases = [
            (
                "no target",
                Window({"target_hwnd": 0, "groups": [{"enabled": True}]}),
                ("Warning", "Select a target window before starting"),
            ),
            (
                "no enabled groups",
                Window({"target_hwnd": 1, "groups": [{"enabled": False}]}),
                ("Tip", "No enabled groups"),
            ),
            (
                "missing dependency",
                Window({"target_hwnd": 1, "groups": [{"enabled": True}]}, missing="missing tesseract"),
                ("Missing dependency", "missing tesseract"),
            ),
            (
                "missing paddle exe",
                Window(
                    {"target_hwnd": 1, "groups": [{"enabled": True}], "paddle_exe_path": r"C:\missing\PaddleOCR-json.exe"},
                    uses_paddle=True,
                ),
                ("Warning", "Select PaddleOCR-json.exe first"),
            ),
        ]

        old_save = bg_ocr.qt.monitor_lifecycle.save_config
        old_warning = bg_ocr.qt.monitor_lifecycle.QtWidgets.QMessageBox.warning
        bg_ocr.qt.monitor_lifecycle.save_config = lambda cfg: saved.append(dict(cfg))
        bg_ocr.qt.monitor_lifecycle.QtWidgets.QMessageBox.warning = (
            lambda _parent, title, text: warnings.append((title, text))
        )
        try:
            for label, win, expected_warning in cases:
                with self.subTest(label=label):
                    before_saved = len(saved)
                    before_warnings = len(warnings)
                    bg_ocr.qt.monitor_lifecycle._start(win)
                    self.assertFalse(win._running)
                    self.assertEqual(win.monitors, [])
                    self.assertEqual(warnings[before_warnings], expected_warning)
                    self.assertEqual(len(saved), before_saved + 1)
                    self.assertNotIn(("set_status", True), win.calls)
        finally:
            bg_ocr.qt.monitor_lifecycle.save_config = old_save
            bg_ocr.qt.monitor_lifecycle.QtWidgets.QMessageBox.warning = old_warning

    def test_group_monitor_recognize_ocr_scales_keyword_position(self):
        import bg_ocr.monitor

        calls = []

        class App:
            cfg = {"groups": [{"name": "OCR"}], "tesseract_path": ""}

            def log(self, msg, tag="info"):
                calls.append(("log", tag, msg))

        old_has_paddle = bg_ocr.monitor.HAS_PADDLE
        old_do_text = bg_ocr.monitor.do_ocr_text
        old_find_pos = bg_ocr.monitor.do_ocr_find_pos
        old_match_keywords = bg_ocr.monitor.match_keywords
        bg_ocr.monitor.HAS_PADDLE = True
        bg_ocr.monitor.do_ocr_text = lambda img, **kwargs: "hello target"
        bg_ocr.monitor.do_ocr_find_pos = lambda img, kws, **kwargs: (20, 10)
        bg_ocr.monitor.match_keywords = lambda text, keywords: (True, "target")
        monitor = bg_ocr.monitor.GroupMonitor(App(), 0)
        try:
            matched, pos = monitor._recognize(
                {
                    "type": "ocr",
                    "ocr_engine": "paddle",
                    "ocr_scale": 2,
                    "keywords": "target",
                },
                Image.new("RGB", (10, 10), (255, 255, 255)),
            )
        finally:
            bg_ocr.monitor.HAS_PADDLE = old_has_paddle
            bg_ocr.monitor.do_ocr_text = old_do_text
            bg_ocr.monitor.do_ocr_find_pos = old_find_pos
            bg_ocr.monitor.match_keywords = old_match_keywords

        self.assertTrue(matched)
        self.assertEqual(pos, (10, 5))
        self.assertTrue(any(tag == "ok" for _kind, tag, _msg in calls))

    def test_group_monitor_recognize_image_uses_template_matching(self):
        import bg_ocr.monitor

        calls = []

        class App:
            cfg = {"groups": [{"name": "Image"}]}

            def log(self, msg, tag="info"):
                calls.append(("log", tag, msg))

        old_has_cv2 = bg_ocr.monitor.HAS_CV2
        old_read = bg_ocr.monitor._imread_unicode
        old_match = bg_ocr.monitor.match_template
        bg_ocr.monitor.HAS_CV2 = True
        bg_ocr.monitor._imread_unicode = lambda path: "template-image"
        bg_ocr.monitor.match_template = lambda img, tmpl, threshold: (True, (3, 4), threshold)
        monitor = bg_ocr.monitor.GroupMonitor(App(), 0)
        try:
            matched, pos = monitor._recognize(
                {
                    "type": "image",
                    "template_path": bg_ocr.monitor.__file__,
                    "threshold": 75,
                },
                Image.new("RGB", (10, 10), (0, 0, 0)),
            )
        finally:
            bg_ocr.monitor.HAS_CV2 = old_has_cv2
            bg_ocr.monitor._imread_unicode = old_read
            bg_ocr.monitor.match_template = old_match

        self.assertTrue(matched)
        self.assertEqual(pos, (3, 4))
        self.assertTrue(any("75%" in msg for _kind, _tag, msg in calls))

    def test_group_monitor_recognize_color_uses_color_matching(self):
        import bg_ocr.monitor

        seen = []

        class App:
            cfg = {"groups": [{"name": "Color"}]}

            def log(self, msg, tag="info"):
                seen.append(("log", tag, msg))

        def match_color(img, target_color, tolerance):
            seen.append(("match_color", target_color, tolerance))
            return True, (5, 6)

        old_has_numpy = bg_ocr.monitor.HAS_NUMPY
        old_match_color = bg_ocr.monitor.match_color
        bg_ocr.monitor.HAS_NUMPY = True
        bg_ocr.monitor.match_color = match_color
        monitor = bg_ocr.monitor.GroupMonitor(App(), 0)
        try:
            matched, pos = monitor._recognize(
                {
                    "type": "color",
                    "target_color": [12, 34, 56],
                    "tolerance": 7,
                },
                Image.new("RGB", (10, 10), (12, 34, 56)),
            )
        finally:
            bg_ocr.monitor.HAS_NUMPY = old_has_numpy
            bg_ocr.monitor.match_color = old_match_color

        self.assertTrue(matched)
        self.assertEqual(pos, (5, 6))
        self.assertIn(("match_color", [12, 34, 56], 7), seen)

    def test_action_sequence_returns_foreground_after_full_quickswitch_sequence(self):
        import types

        import bg_ocr.mouse

        events = []

        class FakeWin32Gui:
            def GetForegroundWindow(self):
                events.append("get_foreground")
                return 900

            def IsWindow(self, hwnd):
                events.append(("is_window", hwnd))
                return True

            def IsIconic(self, hwnd):
                return False

            def GetWindowRect(self, hwnd):
                return (100, 200, 500, 600)

        class FakeUser32:
            def BlockInput(self, value):
                events.append(("block", bool(value)))

            def SwitchToThisWindow(self, hwnd, value):
                events.append(("switch", hwnd, bool(value)))

            def GetAsyncKeyState(self, _vk):
                return 0

        class FakePyAutoGui:
            def position(self):
                return types.SimpleNamespace(x=7, y=8)

            def moveTo(self, x, y, duration=0):
                events.append(("move", x, y, duration))

            def click(self, x, y):
                events.append(("click", x, y))

        old_win32gui = bg_ocr.mouse.win32gui
        old_pyautogui = bg_ocr.mouse.pyautogui
        old_ctypes = bg_ocr.mouse.ctypes
        old_sleep = bg_ocr.mouse.time.sleep
        bg_ocr.mouse.win32gui = FakeWin32Gui()
        bg_ocr.mouse.pyautogui = FakePyAutoGui()
        bg_ocr.mouse.ctypes = types.SimpleNamespace(windll=types.SimpleNamespace(user32=FakeUser32()))
        bg_ocr.mouse.time.sleep = lambda _seconds: None
        try:
            bg_ocr.mouse.exec_action_sequence(
                [
                    {"kind": "mouse", "pos_mode": "window", "abs_x": 1, "abs_y": 2, "click_type": "single"},
                    {"kind": "mouse", "pos_mode": "window", "abs_x": 3, "abs_y": 4, "click_type": "single"},
                ],
                None,
                123,
                {"click_mode": "quickswitch", "sink_after_click": True, "mouse_jitter": False, "mouse_humanize": False},
                lambda _msg, _tag: None,
                lambda: False,
            )
        finally:
            bg_ocr.mouse.win32gui = old_win32gui
            bg_ocr.mouse.pyautogui = old_pyautogui
            bg_ocr.mouse.ctypes = old_ctypes
            bg_ocr.mouse.time.sleep = old_sleep

        first_click = events.index(("click", 101, 202))
        second_click = events.index(("click", 103, 204))
        restore_switch = [i for i, event in enumerate(events) if event == ("switch", 900, True)][0]
        self.assertLess(first_click, second_click)
        self.assertLess(second_click, restore_switch)

    def test_qt_uses_group_ops_module(self):
        import bg_ocr.qt.group_manager
        import bg_ocr.qt.group_ops

        self.assertTrue(callable(bg_ocr.qt.group_ops._remap_chain_targets_after_delete))
        self.assertTrue(callable(bg_ocr.qt.group_ops._remap_chain_targets_after_move))
        self.assertTrue(callable(bg_ocr.qt.group_ops._remap_chain_targets_after_reorder))
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.group_ops import", qt_source)
        self.assertIn(
            "_remap_chain_targets_after_delete(win.cfg[\"groups\"], idx)",
            inspect.getsource(bg_ocr.qt.group_manager._delete_group),
        )
        self.assertIn(
            "_remap_chain_targets_after_move(groups, idx, new_idx)",
            inspect.getsource(bg_ocr.qt.group_manager._move_group),
        )
        self.assertIn(
            "_remap_chain_targets_after_reorder(win.cfg[\"groups\"], old_to_new)",
            inspect.getsource(bg_ocr.qt.group_manager._save_quick_config),
        )

    def test_qt_group_ops_remap_chain_targets(self):
        import bg_ocr.qt.group_ops

        deleted = [
            {"chain_target": 1, "chain_enabled": True},
            {"chain_target": 2, "chain_enabled": True},
        ]
        bg_ocr.qt.group_ops._remap_chain_targets_after_delete(deleted, 1)
        self.assertEqual(deleted[0]["chain_target"], -1)
        self.assertFalse(deleted[0]["chain_enabled"])
        self.assertEqual(deleted[1]["chain_target"], 1)

        moved = [
            {"chain_target": 0},
            {"chain_target": 2},
            {"chain_target": 1},
        ]
        bg_ocr.qt.group_ops._remap_chain_targets_after_move(moved, 0, 2)
        self.assertEqual([g["chain_target"] for g in moved], [2, 0, 1])

        reordered = [
            {"chain_target": 2, "chain_enabled": True},
            {"chain_target": 0, "chain_enabled": True},
            {"chain_target": 9, "chain_enabled": True},
        ]
        bg_ocr.qt.group_ops._remap_chain_targets_after_reorder(reordered, {1: 0, 2: 1, 0: 2})
        self.assertEqual(reordered[0]["chain_target"], 1)
        self.assertEqual(reordered[1]["chain_target"], 2)
        self.assertEqual(reordered[2]["chain_target"], -1)
        self.assertFalse(reordered[2]["chain_enabled"])

    def test_qt_uses_value_helpers_module(self):
        import bg_ocr.qt.group_editor
        import bg_ocr.qt.templates
        import bg_ocr.qt.value_helpers

        for name in [
            "_json_dump",
            "_json_load",
            "_parse_region",
            "_format_region",
            "_parse_color",
            "_format_color",
        ]:
            self.assertIs(getattr(bg_ocr_qt, name), getattr(bg_ocr.qt.value_helpers, name))
            self.assertIs(getattr(bg_ocr.qt.templates, name), getattr(bg_ocr.qt.value_helpers, name))
            self.assertIs(getattr(bg_ocr.qt.group_editor, name), getattr(bg_ocr.qt.value_helpers, name))

        for module in [bg_ocr.qt.main_window, bg_ocr.qt.templates, bg_ocr.qt.group_editor]:
            with open(module.__file__, "r", encoding="utf-8") as f:
                source = f.read()
            self.assertIn("from bg_ocr.qt.value_helpers import", source)
            self.assertNotIn("def _json_dump", source)
            self.assertNotIn("def _parse_color", source)

    def test_qt_value_helpers_parse_and_format(self):
        import bg_ocr.qt.value_helpers

        self.assertEqual(bg_ocr.qt.value_helpers._parse_region("[1, 2, 3, 4]"), [1, 2, 3, 4])
        self.assertIsNone(bg_ocr.qt.value_helpers._parse_region("[1, 2, 3]"))
        self.assertEqual(bg_ocr.qt.value_helpers._format_region([1.2, 2.8, 3, 4]), "[\n  1,\n  2,\n  3,\n  4\n]")
        self.assertEqual(bg_ocr.qt.value_helpers._parse_color("RGB(300, -1, 8)"), [255, 0, 8])
        self.assertEqual(bg_ocr.qt.value_helpers._parse_color("bad"), [255, 0, 0])
        self.assertEqual(bg_ocr.qt.value_helpers._format_color([1.2, 2.8, 3]), "1,2,3")

    def test_main_is_console_entry(self):
        self.assertTrue(callable(bg_ocr.compat.main))
        with open(bg_ocr.compat.__file__, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)
        self.assertNotIn("def _launch_tk", source)
        with open("pyproject.toml", "r", encoding="utf-8") as f:
            pyproject = f.read()
        self.assertIn('bg-ocr-click = "bg_ocr_qt:main"', pyproject)

    def test_qt_main_is_available(self):
        self.assertTrue(callable(bg_ocr_qt.main))
        self.assertTrue(hasattr(bg_ocr_qt, "BgOcrQtWindow"))

    def test_qt_uses_app_launch_module(self):
        import bg_ocr.qt.app

        self.assertIs(bg_ocr_qt._launch_qt, bg_ocr.qt.app._launch_qt)
        self.assertIs(bg_ocr_qt.main, bg_ocr.qt.app.main)
        with open(bg_ocr.qt.main_window.__file__, "r", encoding="utf-8") as f:
            qt_source = f.read()
        self.assertIn("from bg_ocr.qt.app import _launch_qt, main", qt_source)
        self.assertNotIn("def _launch_qt", qt_source)

    def test_qt_main_does_not_fall_back_to_tk_when_launch_fails(self):
        import bg_ocr.qt.app

        old_launch = bg_ocr.qt.app._launch_qt
        bg_ocr.qt.app._launch_qt = lambda: (_ for _ in ()).throw(RuntimeError("qt failed"))
        try:
            with self.assertRaisesRegex(RuntimeError, "qt failed"):
                bg_ocr.qt.app.main()
        finally:
            bg_ocr.qt.app._launch_qt = old_launch
        self.assertFalse(hasattr(bg_ocr.qt.app, "_import_tk_launcher"))

    def test_qt_launch_shows_qt_error_when_startup_dependencies_missing(self):
        import bg_ocr.qt.app

        class FakeApplication:
            created = []
            exec_called = False

            @staticmethod
            def instance():
                return None

            def __init__(self, args):
                self.args = args
                FakeApplication.created.append(self)

            def exec(self):
                FakeApplication.exec_called = True
                return 1

        criticals = []
        old_app = bg_ocr.qt.app.QtWidgets.QApplication
        old_critical = bg_ocr.qt.app.QtWidgets.QMessageBox.critical
        old_has_win32 = bg_ocr.qt.app.HAS_WIN32
        old_has_pil = bg_ocr.qt.app.HAS_PIL
        bg_ocr.qt.app.QtWidgets.QApplication = FakeApplication
        bg_ocr.qt.app.QtWidgets.QMessageBox.critical = lambda *args: criticals.append(args)
        bg_ocr.qt.app.HAS_WIN32 = False
        bg_ocr.qt.app.HAS_PIL = True
        try:
            self.assertIsNone(bg_ocr.qt.app._launch_qt())
        finally:
            bg_ocr.qt.app.QtWidgets.QApplication = old_app
            bg_ocr.qt.app.QtWidgets.QMessageBox.critical = old_critical
            bg_ocr.qt.app.HAS_WIN32 = old_has_win32
            bg_ocr.qt.app.HAS_PIL = old_has_pil

        self.assertEqual(len(FakeApplication.created), 1)
        self.assertEqual(len(criticals), 1)
        self.assertFalse(FakeApplication.exec_called)

    def test_qt_launch_restores_configured_geometry_and_runs_qt_loop(self):
        import bg_ocr.qt.app

        class FakeApplication:
            created = []

            @staticmethod
            def instance():
                return None

            def __init__(self, args):
                self.args = args
                FakeApplication.created.append(self)

            def exec(self):
                return 37

        class FakeWindow:
            instances = []

            def __init__(self):
                self.cfg = {"window_geometry": "640x480"}
                self.resized = []
                self.shown = False
                FakeWindow.instances.append(self)

            def resize(self, width, height):
                self.resized.append((width, height))

            def show(self):
                self.shown = True

        old_app = bg_ocr.qt.app.QtWidgets.QApplication
        old_has_win32 = bg_ocr.qt.app.HAS_WIN32
        old_has_pil = bg_ocr.qt.app.HAS_PIL
        old_is_admin = bg_ocr.qt.app._is_admin
        old_window_cls = bg_ocr_qt.BgOcrQtWindow
        bg_ocr.qt.app.QtWidgets.QApplication = FakeApplication
        bg_ocr.qt.app.HAS_WIN32 = True
        bg_ocr.qt.app.HAS_PIL = True
        bg_ocr.qt.app._is_admin = lambda: True
        bg_ocr_qt.BgOcrQtWindow = FakeWindow
        try:
            self.assertEqual(bg_ocr.qt.app._launch_qt(), 37)
        finally:
            bg_ocr.qt.app.QtWidgets.QApplication = old_app
            bg_ocr.qt.app.HAS_WIN32 = old_has_win32
            bg_ocr.qt.app.HAS_PIL = old_has_pil
            bg_ocr.qt.app._is_admin = old_is_admin
            bg_ocr_qt.BgOcrQtWindow = old_window_cls

        self.assertEqual(len(FakeApplication.created), 1)
        self.assertEqual(len(FakeWindow.instances), 1)
        self.assertEqual(FakeWindow.instances[0].resized, [(640, 480)])
        self.assertTrue(FakeWindow.instances[0].shown)

    def test_qt_launch_uses_shared_default_geometry_when_config_missing(self):
        import bg_ocr.config
        import bg_ocr.qt.app
        import bg_ocr.qt.window_setup

        app_source = inspect.getsource(bg_ocr.qt.app._launch_qt)
        setup_source = inspect.getsource(bg_ocr.qt.window_setup._build_ui)
        self.assertIn("DEFAULT_WINDOW_GEOMETRY", app_source)
        self.assertIn("parse_window_geometry", app_source)
        self.assertIn("DEFAULT_WINDOW_GEOMETRY", setup_source)
        self.assertIn("parse_window_geometry", setup_source)
        self.assertNotIn('"1180x860"', app_source)
        self.assertNotIn("1180, 860", setup_source)
        self.assertNotIn('"1020x750"', inspect.getsource(bg_ocr.config.load_config))

        class FakeApplication:
            created = []

            @staticmethod
            def instance():
                return None

            def __init__(self, args):
                self.args = args
                FakeApplication.created.append(self)

            def exec(self):
                return 43

        class FakeWindow:
            instances = []

            def __init__(self):
                self.cfg = {}
                self.resized = []
                self.shown = False
                FakeWindow.instances.append(self)

            def resize(self, width, height):
                self.resized.append((width, height))

            def show(self):
                self.shown = True

        old_app = bg_ocr.qt.app.QtWidgets.QApplication
        old_has_win32 = bg_ocr.qt.app.HAS_WIN32
        old_has_pil = bg_ocr.qt.app.HAS_PIL
        old_is_admin = bg_ocr.qt.app._is_admin
        old_window_cls = bg_ocr_qt.BgOcrQtWindow
        bg_ocr.qt.app.QtWidgets.QApplication = FakeApplication
        bg_ocr.qt.app.HAS_WIN32 = True
        bg_ocr.qt.app.HAS_PIL = True
        bg_ocr.qt.app._is_admin = lambda: True
        bg_ocr_qt.BgOcrQtWindow = FakeWindow
        try:
            self.assertEqual(bg_ocr.qt.app._launch_qt(), 43)
        finally:
            bg_ocr.qt.app.QtWidgets.QApplication = old_app
            bg_ocr.qt.app.HAS_WIN32 = old_has_win32
            bg_ocr.qt.app.HAS_PIL = old_has_pil
            bg_ocr.qt.app._is_admin = old_is_admin
            bg_ocr_qt.BgOcrQtWindow = old_window_cls

        self.assertEqual(len(FakeApplication.created), 1)
        self.assertEqual(len(FakeWindow.instances), 1)
        self.assertEqual(
            FakeWindow.instances[0].resized,
            [bg_ocr.config.parse_window_geometry(bg_ocr.config.DEFAULT_WINDOW_GEOMETRY)],
        )
        self.assertTrue(FakeWindow.instances[0].shown)

    def test_qt_launch_ignores_invalid_saved_geometry_and_runs_qt_loop(self):
        import bg_ocr.qt.app

        class FakeApplication:
            created = []

            @staticmethod
            def instance():
                return None

            def __init__(self, args):
                self.args = args
                FakeApplication.created.append(self)

            def exec(self):
                return 41

        class FakeWindow:
            instances = []

            def __init__(self):
                self.cfg = {"window_geometry": "bad geometry"}
                self.resized = []
                self.shown = False
                FakeWindow.instances.append(self)

            def resize(self, width, height):
                self.resized.append((width, height))

            def show(self):
                self.shown = True

        old_app = bg_ocr.qt.app.QtWidgets.QApplication
        old_has_win32 = bg_ocr.qt.app.HAS_WIN32
        old_has_pil = bg_ocr.qt.app.HAS_PIL
        old_is_admin = bg_ocr.qt.app._is_admin
        old_window_cls = bg_ocr_qt.BgOcrQtWindow
        bg_ocr.qt.app.QtWidgets.QApplication = FakeApplication
        bg_ocr.qt.app.HAS_WIN32 = True
        bg_ocr.qt.app.HAS_PIL = True
        bg_ocr.qt.app._is_admin = lambda: True
        bg_ocr_qt.BgOcrQtWindow = FakeWindow
        try:
            self.assertEqual(bg_ocr.qt.app._launch_qt(), 41)
        finally:
            bg_ocr.qt.app.QtWidgets.QApplication = old_app
            bg_ocr.qt.app.HAS_WIN32 = old_has_win32
            bg_ocr.qt.app.HAS_PIL = old_has_pil
            bg_ocr.qt.app._is_admin = old_is_admin
            bg_ocr_qt.BgOcrQtWindow = old_window_cls

        self.assertEqual(len(FakeApplication.created), 1)
        self.assertEqual(len(FakeWindow.instances), 1)
        self.assertEqual(FakeWindow.instances[0].resized, [])
        self.assertTrue(FakeWindow.instances[0].shown)

    def test_qt_launch_non_admin_can_continue_without_relaunch(self):
        import bg_ocr.qt.app

        class FakeApplication:
            @staticmethod
            def instance():
                return None

            def __init__(self, args):
                self.args = args

            def exec(self):
                return 19

        class FakeWindow:
            instances = []

            def __init__(self):
                self.cfg = {"window_geometry": "1180x860"}
                self.shown = False
                FakeWindow.instances.append(self)

            def resize(self, _width, _height):
                pass

            def show(self):
                self.shown = True

        questions = []
        relaunches = []
        old_app = bg_ocr.qt.app.QtWidgets.QApplication
        old_question = bg_ocr.qt.app.QtWidgets.QMessageBox.question
        old_has_win32 = bg_ocr.qt.app.HAS_WIN32
        old_has_pil = bg_ocr.qt.app.HAS_PIL
        old_is_admin = bg_ocr.qt.app._is_admin
        old_relaunch = bg_ocr.qt.app._relaunch_as_admin
        old_window_cls = bg_ocr_qt.BgOcrQtWindow
        bg_ocr.qt.app.QtWidgets.QApplication = FakeApplication
        bg_ocr.qt.app.QtWidgets.QMessageBox.question = (
            lambda *args: questions.append(args) or bg_ocr.qt.app.QtWidgets.QMessageBox.StandardButton.No
        )
        bg_ocr.qt.app.HAS_WIN32 = True
        bg_ocr.qt.app.HAS_PIL = True
        bg_ocr.qt.app._is_admin = lambda: False
        bg_ocr.qt.app._relaunch_as_admin = lambda: relaunches.append(True)
        bg_ocr_qt.BgOcrQtWindow = FakeWindow
        try:
            self.assertEqual(bg_ocr.qt.app._launch_qt(), 19)
        finally:
            bg_ocr.qt.app.QtWidgets.QApplication = old_app
            bg_ocr.qt.app.QtWidgets.QMessageBox.question = old_question
            bg_ocr.qt.app.HAS_WIN32 = old_has_win32
            bg_ocr.qt.app.HAS_PIL = old_has_pil
            bg_ocr.qt.app._is_admin = old_is_admin
            bg_ocr.qt.app._relaunch_as_admin = old_relaunch
            bg_ocr_qt.BgOcrQtWindow = old_window_cls

        self.assertEqual(len(questions), 1)
        self.assertEqual(relaunches, [])
        self.assertEqual(len(FakeWindow.instances), 1)
        self.assertTrue(FakeWindow.instances[0].shown)

    def test_qt_launch_non_admin_relaunch_request_stops_current_startup(self):
        import bg_ocr.qt.app

        class FakeApplication:
            @staticmethod
            def instance():
                return None

            def __init__(self, args):
                self.args = args

            def exec(self):
                return 19

        class FakeWindow:
            instances = []

            def __init__(self):
                FakeWindow.instances.append(self)

        questions = []
        relaunches = []
        old_app = bg_ocr.qt.app.QtWidgets.QApplication
        old_question = bg_ocr.qt.app.QtWidgets.QMessageBox.question
        old_has_win32 = bg_ocr.qt.app.HAS_WIN32
        old_has_pil = bg_ocr.qt.app.HAS_PIL
        old_is_admin = bg_ocr.qt.app._is_admin
        old_relaunch = bg_ocr.qt.app._relaunch_as_admin
        old_window_cls = bg_ocr_qt.BgOcrQtWindow
        bg_ocr.qt.app.QtWidgets.QApplication = FakeApplication
        bg_ocr.qt.app.QtWidgets.QMessageBox.question = (
            lambda *args: questions.append(args) or bg_ocr.qt.app.QtWidgets.QMessageBox.StandardButton.Yes
        )
        bg_ocr.qt.app.HAS_WIN32 = True
        bg_ocr.qt.app.HAS_PIL = True
        bg_ocr.qt.app._is_admin = lambda: False

        def relaunch():
            relaunches.append(True)
            raise SystemExit(0)

        bg_ocr.qt.app._relaunch_as_admin = relaunch
        bg_ocr_qt.BgOcrQtWindow = FakeWindow
        try:
            with self.assertRaises(SystemExit):
                bg_ocr.qt.app._launch_qt()
        finally:
            bg_ocr.qt.app.QtWidgets.QApplication = old_app
            bg_ocr.qt.app.QtWidgets.QMessageBox.question = old_question
            bg_ocr.qt.app.HAS_WIN32 = old_has_win32
            bg_ocr.qt.app.HAS_PIL = old_has_pil
            bg_ocr.qt.app._is_admin = old_is_admin
            bg_ocr.qt.app._relaunch_as_admin = old_relaunch
            bg_ocr_qt.BgOcrQtWindow = old_window_cls

        self.assertEqual(len(questions), 1)
        self.assertEqual(relaunches, [True])
        self.assertEqual(FakeWindow.instances, [])

    def test_qt_settings_capture_mode_roundtrip(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._SettingsEditor()
        try:
            theme_widget = editor._widgets["theme"]
            self.assertEqual(
                [theme_widget.itemText(i) for i in range(theme_widget.count())],
                list(bg_ocr.qt.theme.THEMES),
            )
            editor.load_settings({"capture_mode": "auto", "theme": "modern", "start_on_launch": False})
            dumped = editor.dump_settings()
            self.assertEqual(dumped["capture_mode"], "auto")
            self.assertEqual(dumped["theme"], "modern")
            self.assertFalse(dumped["start_on_launch"])
        finally:
            editor.close()

    def test_qt_settings_editor_emits_changed_only_for_user_edits(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._SettingsEditor()
        changed = []
        editor.changed.connect(lambda: changed.append("changed"))
        try:
            editor.load_settings({
                "tesseract_path": "old.exe",
                "capture_mode": "printwindow",
                "theme": "default",
                "sound_enabled": False,
                "start_on_launch": True,
            })
            self.assertEqual(changed, [])

            editor._widgets["tesseract_path"].setText("new.exe")
            editor._widgets["capture_mode"].setCurrentText("auto")
            editor._widgets["sound_enabled"].setChecked(True)
            self.assertGreaterEqual(len(changed), 3)
        finally:
            editor.close()

    def test_qt_settings_browse_and_sound_test_signal_behavior(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.settings

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._SettingsEditor()
        changed = []
        played = []
        paths = iter([
            ("", ""),
            (r"C:\tools\tesseract.exe", ""),
            (r"C:\sound\ok.wav", ""),
        ])
        old_dialog = bg_ocr.qt.settings.QtWidgets.QFileDialog.getOpenFileName
        old_play = bg_ocr.qt.settings._play_sound
        bg_ocr.qt.settings.QtWidgets.QFileDialog.getOpenFileName = lambda *_args: next(paths)
        bg_ocr.qt.settings._play_sound = lambda path: played.append(path)
        editor.changed.connect(lambda: changed.append("changed"))
        try:
            editor.load_settings({"tesseract_path": "old.exe", "sound_file": "old.wav"})
            editor._browse_paddle()
            self.assertEqual(editor._widgets["paddle_exe_path"].text(), "")
            self.assertEqual(changed, [])

            editor._browse_tess()
            self.assertEqual(editor._widgets["tesseract_path"].text(), r"C:\tools\tesseract.exe")
            self.assertEqual(len(changed), 1)

            editor._browse_sound()
            self.assertEqual(editor._widgets["sound_file"].text(), r"C:\sound\ok.wav")
            self.assertEqual(len(changed), 2)

            editor._widgets["sound_test"].click()
            self.assertEqual(played, [r"C:\sound\ok.wav"])
            self.assertEqual(len(changed), 2)
        finally:
            bg_ocr.qt.settings.QtWidgets.QFileDialog.getOpenFileName = old_dialog
            bg_ocr.qt.settings._play_sound = old_play
            editor.close()

    def test_qt_group_load_does_not_mark_dirty(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {"groups": [bg_ocr_qt._copy_group({"name": "Dirty Test"})]}
            win._current_index = 0
            win._group_order_dirty = True
            win._load_group_editor(0)
            self.assertFalse(win._group_order_dirty)
        finally:
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_group_load_preserves_chain_target(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First", "chain_enabled": True, "chain_target": 1}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                ]
            }
            win._current_index = 0
            win._load_group_editor(0)
            win._save_current_group()
            self.assertEqual(win.cfg["groups"][0]["chain_target"], 1)
        finally:
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_group_editor_preserves_unknown_fields(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.load_group(bg_ocr_qt._copy_group({"name": "Extra", "future_field": {"keep": True}}), 0)
            dumped = editor.dump_group(0)
            self.assertEqual(dumped["future_field"], {"keep": True})
        finally:
            editor.deleteLater()

    def test_qt_group_editor_embeds_action_sequence_editor_and_hides_json_text(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions
        import bg_ocr.qt.theme

        self.assertNotIn("setMinimumWidth(72)", inspect.getsource(bg_ocr.qt.actions._ActionRowHandle))
        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QLabel#actionSequenceDragHandle", qss)
                self.assertIn("min-width: 72px", qss)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            self.assertIsInstance(editor._widgets["actions"], bg_ocr.qt.actions._ActionSequenceWidget)
            self.assertTrue(hasattr(editor._widgets["actions"], "_json_btn"))
            self.assertNotIsInstance(editor._widgets["actions"], QtWidgets.QPlainTextEdit)
            self.assertEqual(editor._field_containers["actions"].property("fieldSpan"), "full")
            self.assertEqual(
                editor._field_containers["actions"].sizePolicy().horizontalPolicy(),
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        finally:
            editor.deleteLater()

    def test_qt_group_editor_action_widget_saves_typed_actions(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        group = bg_ocr_qt._copy_group({"name": "Actions", "actions": []})
        try:
            editor.load_group(group, 0)
            actions = editor._widgets["actions"]
            actions._add_action("delay")
            actions._row_fields[0]["seconds"].setValue(1.25)
            dumped = editor.dump_group(0)
            self.assertEqual(dumped["actions"], [{"kind": "delay", "seconds": 1.25}])
        finally:
            editor.deleteLater()

    def test_qt_action_editor_adds_inline_rows_with_visible_controls(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget()
        try:
            editor._add_action("delay")
            editor._add_action("text")

            self.assertFalse(hasattr(editor, "_list"))
            self.assertEqual(len(editor._rows), 2)
            self.assertEqual(editor._rows[0]["kind"], "delay")
            self.assertEqual(editor._rows[1]["kind"], "text")
            self.assertTrue(editor._rows[0]["container"].isAncestorOf(editor._row_fields[0]["seconds"]))
            self.assertTrue(editor._rows[1]["container"].isAncestorOf(editor._row_fields[1]["text"]))

            editor._row_fields[0]["seconds"].setValue(1.75)
            editor._row_fields[1]["text"].setText("inline edit")
            self.assertEqual(editor.actions[0], {"kind": "delay", "seconds": 1.75})
            self.assertEqual(editor.actions[1]["text"], "inline edit")
        finally:
            editor.deleteLater()

    def test_qt_action_editor_scroll_area_fills_available_width_and_keeps_single_row_tall(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions
        import bg_ocr.qt.theme

        source = inspect.getsource(bg_ocr.qt.actions._ActionSequenceWidget)
        self.assertIn('setObjectName("actionSequenceEditor")', source)
        self.assertIn('setObjectName("actionSequenceScroll")', source)
        self.assertNotIn("self.setMinimumHeight(self._MIN_EDITOR_HEIGHT)", source)

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#actionSequenceEditor", qss)
                self.assertIn("QScrollArea#actionSequenceScroll", qss)
                self.assertIn("min-height: 400px", qss)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget([{"kind": "mouse"}])
        try:
            editor.setStyleSheet(bg_ocr.qt.theme.load_theme("default"))
            editor.show()
            editor.resize(700, 400)
            QtWidgets.QApplication.processEvents()

            self.assertEqual(editor.objectName(), "actionSequenceEditor")
            self.assertEqual(editor._scroll.objectName(), "actionSequenceScroll")
            self.assertLess(editor.minimumWidth(), 1000)
            self.assertGreaterEqual(editor.minimumHeight(), 400)
            self.assertEqual(editor.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Policy.Expanding)
            self.assertLess(editor._scroll.minimumWidth(), 1000)
            self.assertGreaterEqual(editor._scroll.minimumHeight(), 400)
            self.assertEqual(editor._scroll.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Policy.Expanding)
            self.assertEqual(editor._scroll.verticalScrollBar().maximum(), 0)
            self.assertGreaterEqual(editor._scroll.viewport().height(), editor._rows[0]["container"].sizeHint().height())
        finally:
            editor.deleteLater()

    def test_qt_action_editor_drag_handle_reorders_rows_without_move_buttons(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget(
            [{"kind": "delay", "seconds": 1}, {"kind": "text", "text": "two"}, {"kind": "key", "key": "enter"}]
        )
        try:
            self.assertTrue(all("handle" in row for row in editor._rows))
            self.assertEqual(editor._rows[0]["handle"].objectName(), "actionSequenceDragHandle")
            row_buttons = [button.text() for button in editor.findChildren(QtWidgets.QPushButton)]
            self.assertNotIn("上移", row_buttons)
            self.assertNotIn("下移", row_buttons)
            self.assertIn("删除", row_buttons)

            editor._move_action_to(0, 2)
            self.assertEqual([action["kind"] for action in editor.actions], ["text", "key", "delay"])
            self.assertEqual(editor._rows[2]["handle"].text(), "3.[\u5ef6]")
        finally:
            editor.deleteLater()

    def test_qt_group_editor_filters_recognition_fields_by_monitor_type(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.load_group(bg_ocr_qt._copy_group({"type": "ocr"}), 0)
            self.assertFalse(editor._field_containers["keywords"].isHidden())
            self.assertFalse(editor._field_containers["language"].isHidden())
            self.assertTrue(editor._field_containers["template_path"].isHidden())
            self.assertTrue(editor._field_containers["target_color"].isHidden())

            editor._widgets["type"].setCurrentText("image")
            self.assertFalse(editor._field_containers["template_path"].isHidden())
            self.assertFalse(editor._field_containers["threshold"].isHidden())
            self.assertTrue(editor._field_containers["keywords"].isHidden())
            self.assertTrue(editor._field_containers["target_color"].isHidden())

            editor._widgets["type"].setCurrentText("color")
            self.assertFalse(editor._field_containers["target_color"].isHidden())
            self.assertFalse(editor._field_containers["tolerance"].isHidden())
            self.assertTrue(editor._field_containers["keywords"].isHidden())
            self.assertTrue(editor._field_containers["template_path"].isHidden())

            editor.load_group(bg_ocr_qt._copy_group({"type": "orc"}), 0)
            self.assertEqual(editor._widgets["type"].currentText(), "ocr")
            self.assertFalse(editor._field_containers["keywords"].isHidden())

            editor.load_group(bg_ocr_qt._copy_group({"type": "coor"}), 0)
            self.assertEqual(editor._widgets["type"].currentText(), "color")
            self.assertFalse(editor._field_containers["target_color"].isHidden())
        finally:
            editor.deleteLater()

    def test_qt_group_editor_click_section_keeps_only_sequence_level_options(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.load_group(bg_ocr_qt._copy_group({"sink_after_click": True}), 0)
            self.assertEqual(editor._widgets["sink_after_click"].text(), "")
            self.assertEqual(editor._widgets["mouse_jitter"].text(), "")
            self.assertEqual(editor._widgets["mouse_humanize"].text(), "")
            self.assertGreaterEqual(editor._section_layouts["groupSectionClick"].spacing(), 16)
            visible_keys = [
                key for key, container in editor._field_containers.items()
                if container.parent() is editor._click_box and not container.isHidden()
            ]
            self.assertEqual(visible_keys, ["click_mode", "sink_after_click", "mouse_jitter", "mouse_humanize"])
            dumped = editor.dump_group(0)
            self.assertEqual(dumped["click_type"], "single")
            self.assertEqual(dumped["click_target"], "keyword")
            self.assertEqual(dumped["custom_x"], 0)
            self.assertEqual(dumped["custom_y"], 0)
            self.assertTrue(dumped["sink_after_click"])
        finally:
            editor.deleteLater()

    def test_qt_group_editor_has_ocr_keyword_rule_help(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            help_text = editor._keyword_help.text()
            self.assertEqual(
                help_text,
                "规则：多个关键词用 |、逗号、分号、顿号或换行分隔，任一命中即匹配；忽略空格差异。",
            )
            self.assertFalse(editor._keyword_help.wordWrap())
            self.assertNotIn("例", help_text)
            self.assertIn("|", help_text)
            self.assertIn("，", help_text)
            self.assertIs(editor._keyword_help.parent(), editor._field_containers["keywords"])
        finally:
            editor.deleteLater()

    def test_qt_group_editor_compact_field_widths_come_from_qss(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "themes", "default.qss"), "r", encoding="utf-8") as f:
            default_qss = f.read()
        with open(os.path.join(os.path.dirname(__file__), "..", "themes", "modern.qss"), "r", encoding="utf-8") as f:
            modern_qss = f.read()

        for qss in [default_qss, modern_qss]:
            self.assertIn("QWidget#groupEditor QLineEdit", qss)
            self.assertIn("min-width: 72px", qss)
            self.assertIn("max-width: 180px", qss)
            self.assertIn("QLabel#keywordHelp", qss)

    def test_qt_group_editor_ocr_keyword_row_and_short_controls_are_compact(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.show()
            editor.load_group(bg_ocr_qt._copy_group({"type": "ocr"}), 0)
            QtWidgets.QApplication.processEvents()

            keyword_pos = editor._field_containers["keywords"].mapTo(
                editor, editor._field_containers["keywords"].rect().topLeft()
            )
            language_pos = editor._field_containers["language"].mapTo(
                editor, editor._field_containers["language"].rect().topLeft()
            )
            self.assertEqual(language_pos.y(), keyword_pos.y())
            self.assertGreater(language_pos.x(), keyword_pos.x())
            self.assertEqual(editor._widgets["language"].property("fieldSize"), "short")
            self.assertEqual(editor._widgets["ocr_engine"].property("fieldSize"), "short")
        finally:
            editor.deleteLater()

    def test_qt_group_editor_roundtrips_monitoring_config_fields(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        group = bg_ocr_qt._copy_group(
            {
                "enabled": False,
                "name": "Monitor Config",
                "type": "color",
                "capture_mode": "imagegrab",
                "keywords": "alpha|beta",
                "language": "eng",
                "ocr_engine": "tesseract",
                "ocr_psm": 11,
                "ocr_scale": 3,
                "ocr_binarize": False,
                "ocr_threshold": 191,
                "ocr_contrast": 2.25,
                "ocr_invert": True,
                "region": [10, 20, 30, 40],
                "template_path": r"C:\tmp\needle.png",
                "threshold": 87,
                "target_color": [12, 34, 56],
                "tolerance": 17,
                "interval": 9,
                "pause": 4,
                "debug_save": True,
            }
        )
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.load_group(group, 0)
            dumped = editor.dump_group(0)
            for key in [
                "enabled",
                "name",
                "type",
                "capture_mode",
                "keywords",
                "language",
                "ocr_engine",
                "ocr_psm",
                "ocr_scale",
                "ocr_binarize",
                "ocr_threshold",
                "ocr_invert",
                "region",
                "template_path",
                "threshold",
                "target_color",
                "tolerance",
                "interval",
                "pause",
                "debug_save",
            ]:
                self.assertEqual(dumped[key], group[key])
            self.assertAlmostEqual(dumped["ocr_contrast"], group["ocr_contrast"])
        finally:
            editor.deleteLater()

    def test_qt_group_editor_roundtrips_chain_and_popup_flow_fields(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        popup_templates = [
            {
                "name": "OCR popup",
                "type": "ocr",
                "keywords": "ready|go",
                "language": "eng",
                "ocr_engine": "tesseract",
                "ocr_psm": 7,
                "ocr_scale": 2,
                "ocr_binarize": False,
                "ocr_threshold": 177,
                "ocr_contrast": 2.0,
                "ocr_invert": True,
                "click_mode": "quickswitch",
                "click_type": "double",
                "click_target": "window",
                "custom_x": 44,
                "custom_y": 55,
                "match_empty_ocr": True,
                "size_cond_enabled": True,
                "size_cond_w_op": ">=",
                "size_cond_w_val": 320,
                "size_cond_h_op": "<=",
                "size_cond_h_val": 240,
                "size_cond_logic": "or",
                "region": [1, 2, 30, 40],
                "after_match_stop_flow": True,
                "after_match_sound_file": r"C:\tmp\done.wav",
                "actions": [{"kind": "delay", "seconds": 0.5}],
            },
            {
                "name": "Image popup",
                "type": "image",
                "template_path": r"C:\tmp\popup.png",
                "threshold": 91,
            },
        ]
        group = bg_ocr_qt._copy_group(
            {
                "name": "Popup Flow",
                "chain_enabled": True,
                "chain_target": 2,
                "chain_wait": 12,
                "popup_only_mode": True,
                "popup_enabled": True,
                "popup_title_kw": "Result",
                "popup_wait_appear": 8,
                "popup_wait_close": 9,
                "popup_total_timeout": 180,
                "popup_no_match_action": "pause_group",
                "popup_templates": popup_templates,
            }
        )
        editor = bg_ocr_qt._GroupEditor()
        try:
            editor.load_group(group, 0)
            editor.set_chain_options(["First", "Second", "Third"], 0, selected_index=2)
            dumped = editor.dump_group(0)
            for key in [
                "chain_enabled",
                "chain_target",
                "chain_wait",
                "popup_only_mode",
                "popup_enabled",
                "popup_title_kw",
                "popup_wait_appear",
                "popup_wait_close",
                "popup_total_timeout",
                "popup_no_match_action",
                "popup_templates",
            ]:
                self.assertEqual(dumped[key], group[key])

            editor._widgets["chain_target"].setCurrentText("2:Second")
            self.assertEqual(editor.dump_group(0)["chain_target"], 1)
        finally:
            editor.deleteLater()

    def test_qt_group_editor_pick_region_and_color_updates_fields(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_editor

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        img = Image.new("RGB", (8, 8), (0, 0, 0))
        img.putpixel((2, 3), (10, 20, 30))
        picker_calls = []
        changed = []

        class Parent(QtWidgets.QWidget):
            cfg = {"capture_mode": "printwindow"}

            def current_hwnd(self):
                return 12345

        class Picker:
            def __init__(self, picked_img, mode, _parent):
                self.selection = [1, 2, 4, 5] if mode == "rect" else (2, 3)
                picker_calls.append((picked_img, mode))

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        old_capture = bg_ocr.qt.group_editor.capture_full_preview
        bg_ocr.qt.group_editor.capture_full_preview = lambda hwnd, mode: img
        parent = Parent()
        editor = bg_ocr_qt._GroupEditor(parent)
        editor._get_image_picker_cls = lambda: Picker
        editor.changed.connect(lambda: changed.append("changed"))
        try:
            editor._pick_region()
            editor._pick_color()
        finally:
            bg_ocr.qt.group_editor.capture_full_preview = old_capture
            editor.deleteLater()
            parent.deleteLater()

        self.assertEqual(bg_ocr_qt._parse_region(editor._widgets["region"].text()), [1, 2, 4, 5])
        self.assertEqual(editor._widgets["target_color"].text(), "10,20,30")
        self.assertEqual([mode for _img, mode in picker_calls], ["rect", "point"])
        self.assertGreaterEqual(len(changed), 2)

    def test_qt_group_editor_pickers_find_owner_window_through_ancestors(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_editor

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        img = Image.new("RGB", (10, 10), (0, 0, 0))
        img.putpixel((2, 3), (40, 50, 60))
        picker_calls = []

        class Owner(QtWidgets.QWidget):
            cfg = {"capture_mode": "printwindow"}

            def current_hwnd(self):
                return 12345

            def current_group_index(self):
                return 4

        class Picker:
            def __init__(self, picked_img, mode, _parent):
                self.selection = [1, 2, 5, 6] if mode == "rect" else (2, 3)
                picker_calls.append((picked_img, mode))

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        old_capture = bg_ocr.qt.group_editor.capture_full_preview
        old_config_file = bg_ocr.qt.group_editor.CONFIG_FILE
        bg_ocr.qt.group_editor.capture_full_preview = lambda hwnd, mode: img
        owner = Owner()
        middle = QtWidgets.QWidget(owner)
        editor = bg_ocr_qt._GroupEditor(middle)
        editor._get_image_picker_cls = lambda: Picker
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bg_ocr.qt.group_editor.CONFIG_FILE = os.path.join(tmp, "config.json")
                editor._pick_region()
                editor._pick_color()
                editor._capture_template()
                captured_path = editor._widgets["template_path"].text()

                self.assertEqual(bg_ocr_qt._parse_region(editor._widgets["region"].text()), [1, 2, 5, 6])
                self.assertEqual(editor._widgets["target_color"].text(), "40,50,60")
                self.assertEqual(os.path.basename(captured_path), "template_g5.png")
                self.assertTrue(os.path.exists(captured_path))
        finally:
            bg_ocr.qt.group_editor.capture_full_preview = old_capture
            bg_ocr.qt.group_editor.CONFIG_FILE = old_config_file
            editor.deleteLater()
            middle.deleteLater()
            owner.deleteLater()

        self.assertEqual([mode for _img, mode in picker_calls], ["rect", "point", "rect"])

    def test_qt_action_dialog_preserves_unknown_fields_and_kind(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._ActionSequenceDialog(
            [{"kind": "future_action", "pre_delay": 0.25, "future_field": {"keep": True}}]
        )
        try:
            dialog._accept()
            self.assertEqual(dialog.actions[0]["kind"], "future_action")
            self.assertEqual(dialog.actions[0]["future_field"], {"keep": True})
        finally:
            dialog.deleteLater()

    def test_qt_action_dialog_picks_window_and_screen_points(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        img = Image.new("RGB", (12, 12), (0, 0, 0))
        picker_calls = []

        class Owner(QtWidgets.QWidget):
            cfg = {"capture_mode": "printwindow"}

            def current_hwnd(self):
                return 12345

        class ImagePicker:
            def __init__(self, picked_img, mode, _parent):
                self.selection = (7, 8)
                picker_calls.append((picked_img, mode))

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        class ScreenPicker:
            def __init__(self, _parent):
                self.point = (300, 400)

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        old_capture = bg_ocr.qt.actions.capture_full_preview
        bg_ocr.qt.actions.capture_full_preview = lambda hwnd, mode: img
        owner = Owner()
        dialog = bg_ocr_qt._ActionSequenceDialog(
            [{"kind": "mouse"}],
            owner,
            image_picker_cls=ImagePicker,
            screen_point_picker_cls=ScreenPicker,
        )
        try:
            dialog._pick_window_coord()
            self.assertEqual(dialog.actions[0]["pos_mode"], "window")
            self.assertEqual(dialog.actions[0]["abs_x"], 7)
            self.assertEqual(dialog.actions[0]["abs_y"], 8)

            dialog._pick_screen_coord()
            self.assertEqual(dialog.actions[0]["pos_mode"], "screen")
            self.assertEqual(dialog.actions[0]["abs_x"], 300)
            self.assertEqual(dialog.actions[0]["abs_y"], 400)
        finally:
            bg_ocr.qt.actions.capture_full_preview = old_capture
            dialog.deleteLater()
            owner.deleteLater()

        self.assertEqual(picker_calls, [(img, "point")])

    def test_qt_action_dialog_roundtrips_all_action_kinds(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._ActionSequenceDialog(
            [
                {"kind": "mouse"},
                {"kind": "key"},
                {"kind": "text"},
                {"kind": "delay"},
                {"kind": "scroll"},
            ]
        )
        try:
            dialog._editor._row_fields[0]["pre_delay"].setValue(0.25)
            dialog._editor._row_fields[0]["pos_mode"].setCurrentText("offset")
            dialog._editor._row_fields[0]["offset_x"].setValue(3)
            dialog._editor._row_fields[0]["offset_y"].setValue(-4)
            dialog._editor._row_fields[0]["click_type"].setCurrentText("double")
            dialog._editor._row_fields[0]["count"].setValue(2)
            dialog._editor._row_fields[0]["interval"].setValue(0.2)

            dialog._editor._row_fields[1]["key"].setCurrentText("ctrl+s")
            dialog._editor._row_fields[1]["action"].setCurrentText("press")
            dialog._editor._row_fields[1]["count"].setValue(3)
            dialog._editor._row_fields[1]["interval"].setValue(0.05)

            dialog._editor._row_fields[2]["text"].setText("hello")
            dialog._editor._row_fields[2]["interval"].setValue(0.03)

            dialog._editor._row_fields[3]["seconds"].setValue(1.25)

            dialog._editor._row_fields[4]["abs_x"].setValue(31)
            dialog._editor._row_fields[4]["abs_y"].setValue(32)
            dialog._editor._row_fields[4]["direction"].setCurrentText("up")
            dialog._editor._row_fields[4]["clicks"].setValue(4)
            dialog._editor._row_fields[4]["multiplier"].setValue(2.5)

            dialog._accept()
            self.assertEqual(
                dialog.actions,
                [
                    {
                        "kind": "mouse",
                        "pre_delay": 0.25,
                        "pos_mode": "offset",
                        "offset_x": 3,
                        "offset_y": -4,
                        "abs_x": 0,
                        "abs_y": 0,
                        "click_type": "double",
                        "count": 2,
                        "interval": 0.2,
                    },
                    {
                        "kind": "key",
                        "pre_delay": 0.0,
                        "key": "ctrl+s",
                        "action": "press",
                        "count": 3,
                        "interval": 0.05,
                    },
                    {
                        "kind": "text",
                        "pre_delay": 0.0,
                        "text": "hello",
                        "interval": 0.03,
                    },
                    {
                        "kind": "delay",
                        "seconds": 1.25,
                    },
                    {
                        "kind": "scroll",
                        "pre_delay": 0.0,
                        "abs_x": 31,
                        "abs_y": 32,
                        "direction": "up",
                        "clicks": 4,
                        "interval": 0.1,
                        "multiplier": 2.5,
                    },
                ],
            )
        finally:
            dialog.deleteLater()

    def test_qt_action_editor_fields_are_filtered_by_action_type(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget(
            [
                {"kind": "mouse"},
                {"kind": "delay"},
            ]
        )
        try:
            editor.show()
            QtWidgets.QApplication.processEvents()

            editor._select_row(0)
            QtWidgets.QApplication.processEvents()
            self.assertEqual(
                set(editor._field_rows),
                {
                    "pre_delay",
                    "pos_mode",
                    "offset_x",
                    "offset_y",
                    "abs_x",
                    "abs_y",
                    "click_type",
                    "count",
                    "interval",
                },
            )

            editor._select_row(1)
            QtWidgets.QApplication.processEvents()
            self.assertEqual(set(editor._field_rows), {"seconds"})
        finally:
            editor.deleteLater()

    def test_qt_action_editor_uses_inline_rows_without_splitter_or_list(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions
        import bg_ocr.qt.theme

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget([{"kind": "mouse"}])
        try:
            self.assertEqual(editor.findChildren(QtWidgets.QSplitter), [])
            self.assertEqual(editor._config_row.objectName(), "actionSequenceConfigRow")
            self.assertEqual(editor.findChildren(QtWidgets.QListWidget), [])
            self.assertEqual(editor._rows[0]["container"].objectName(), "actionSequenceInlineRow")
            self.assertEqual(editor._rows[0]["pick_button"].objectName(), "actionPointPickButton")
            self.assertIs(editor._field_rows["pre_delay"].parent(), editor._rows[0]["container"])
            self.assertIs(editor._pick_row.parent(), editor._rows[0]["container"])
        finally:
            editor.deleteLater()

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QWidget#actionSequenceInlineRow", qss)
                self.assertIn("QPushButton#actionPointPickButton", qss)
                self.assertIn("min-width: 52px", qss)

    def test_qt_action_editor_mouse_row_shows_coordinates_for_selected_position_only(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget([{"kind": "mouse"}])
        try:
            editor.show()
            QtWidgets.QApplication.processEvents()
            row = editor._rows[0]
            fields = editor._row_fields[0]

            self.assertEqual(row["handle"].text(), "1.[鼠]")
            self.assertIs(row["pick_row"].parent(), row["container"])
            self.assertEqual(row["pick_button"].text(), "点选")
            self.assertEqual(len(row["container"].findChildren(QtWidgets.QPushButton, "actionPointPickButton")), 1)

            fields["pos_mode"].setCurrentText("match_center")
            QtWidgets.QApplication.processEvents()
            self.assertFalse(row["field_rows"]["offset_x"].isVisible())
            self.assertFalse(row["field_rows"]["offset_y"].isVisible())
            self.assertFalse(row["field_rows"]["abs_x"].isVisible())
            self.assertFalse(row["field_rows"]["abs_y"].isVisible())
            self.assertFalse(row["pick_button"].isVisible())
            self.assertFalse(row["pick_row"].isVisible())

            fields["pos_mode"].setCurrentText("offset")
            QtWidgets.QApplication.processEvents()
            self.assertTrue(row["field_rows"]["offset_x"].isVisible())
            self.assertTrue(row["field_rows"]["offset_y"].isVisible())
            self.assertFalse(row["field_rows"]["abs_x"].isVisible())
            self.assertFalse(row["field_rows"]["abs_y"].isVisible())
            self.assertFalse(row["pick_button"].isVisible())
            self.assertFalse(row["pick_row"].isVisible())

            fields["pos_mode"].setCurrentText("screen")
            QtWidgets.QApplication.processEvents()
            self.assertFalse(row["field_rows"]["offset_x"].isVisible())
            self.assertFalse(row["field_rows"]["offset_y"].isVisible())
            self.assertTrue(row["field_rows"]["abs_x"].isVisible())
            self.assertTrue(row["field_rows"]["abs_y"].isVisible())
            self.assertTrue(row["pick_button"].isVisible())
            self.assertTrue(row["pick_row"].isVisible())

            fields["pos_mode"].setCurrentText("window")
            QtWidgets.QApplication.processEvents()
            self.assertFalse(row["field_rows"]["offset_x"].isVisible())
            self.assertFalse(row["field_rows"]["offset_y"].isVisible())
            self.assertTrue(row["field_rows"]["abs_x"].isVisible())
            self.assertTrue(row["field_rows"]["abs_y"].isVisible())
            self.assertTrue(row["pick_button"].isVisible())
            self.assertTrue(row["pick_row"].isVisible())
        finally:
            editor.deleteLater()

    def test_qt_action_editor_pick_button_follows_coordinate_fields_and_scroll_is_compact(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget([{"kind": "mouse"}, {"kind": "scroll"}])
        try:
            editor.show()
            QtWidgets.QApplication.processEvents()

            mouse_widgets = [
                item.widget()
                for item in (
                    editor._rows[0]["container"].layout().itemAt(i)
                    for i in range(editor._rows[0]["container"].layout().count())
                )
                if item.widget() is not None
            ]
            self.assertLess(
                mouse_widgets.index(editor._rows[0]["pick_row"]),
                mouse_widgets.index(editor._rows[0]["field_rows"]["click_type"]),
            )
            self.assertGreater(
                mouse_widgets.index(editor._rows[0]["pick_row"]),
                mouse_widgets.index(editor._rows[0]["field_rows"]["abs_y"]),
            )

            scroll_row = editor._rows[1]
            self.assertEqual(set(scroll_row["field_rows"]), {"abs_x", "abs_y", "direction", "clicks", "multiplier"})
            scroll_widgets = [
                item.widget()
                for item in (
                    scroll_row["container"].layout().itemAt(i)
                    for i in range(scroll_row["container"].layout().count())
                )
                if item.widget() is not None
            ]
            self.assertGreater(
                scroll_widgets.index(scroll_row["pick_row"]),
                scroll_widgets.index(scroll_row["field_rows"]["abs_y"]),
            )
            self.assertLess(
                scroll_widgets.index(scroll_row["pick_row"]),
                scroll_widgets.index(scroll_row["field_rows"]["direction"]),
            )
            self.assertNotIn("pre_delay", scroll_row["field_rows"])
            self.assertNotIn("interval", scroll_row["field_rows"])
        finally:
            editor.deleteLater()

    def test_qt_action_editor_mouse_combos_show_labels_but_save_internal_values(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget([{"kind": "mouse"}])
        try:
            fields = editor._row_fields[0]
            self.assertEqual(fields["pos_mode"].currentText(), "识别位置(中心点)")
            self.assertEqual(fields["click_type"].currentText(), "单击")

            fields["pos_mode"].setCurrentText("识别位置+偏移")
            fields["offset_x"].setValue(11)
            fields["offset_y"].setValue(-12)
            fields["click_type"].setCurrentText("双击")
            self.assertEqual(editor.actions[0]["pos_mode"], "offset")
            self.assertEqual(editor.actions[0]["offset_x"], 11)
            self.assertEqual(editor.actions[0]["offset_y"], -12)
            self.assertEqual(editor.actions[0]["click_type"], "double")
        finally:
            editor.deleteLater()

    def test_qt_action_editor_scroll_action_supports_point_picking(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        img = Image.new("RGB", (12, 12), (0, 0, 0))
        picker_calls = []

        class Owner(QtWidgets.QWidget):
            cfg = {"capture_mode": "printwindow"}

            def current_hwnd(self):
                return 12345

        class ImagePicker:
            def __init__(self, picked_img, mode, _parent):
                self.selection = (7, 8)
                picker_calls.append((picked_img, mode))

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        class ScreenPicker:
            def __init__(self, _parent):
                self.point = (300, 400)

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        old_capture = bg_ocr.qt.actions.capture_full_preview
        old_information = QtWidgets.QMessageBox.information
        bg_ocr.qt.actions.capture_full_preview = lambda hwnd, mode: img
        QtWidgets.QMessageBox.information = lambda *_args: None
        owner = Owner()
        editor = bg_ocr.qt.actions._ActionSequenceWidget(
            [{"kind": "scroll"}],
            owner,
            image_picker_cls=ImagePicker,
            screen_point_picker_cls=ScreenPicker,
        )
        try:
            owner.show()
            editor.show()
            QtWidgets.QApplication.processEvents()
            self.assertTrue(editor._rows[0]["pick_row"].isVisible())
            editor._row_fields[0]["abs_x"].setValue(11)
            editor._row_fields[0]["abs_y"].setValue(22)
            self.assertEqual(editor.actions[0]["abs_x"], 11)
            self.assertEqual(editor.actions[0]["abs_y"], 22)

            editor._pick_window_coord()
            self.assertEqual(editor.actions[0]["abs_x"], 7)
            self.assertEqual(editor.actions[0]["abs_y"], 8)
            self.assertNotIn("pos_mode", editor.actions[0])

            editor._pick_coord(0)
            self.assertEqual(editor.actions[0]["abs_x"], 300)
            self.assertEqual(editor.actions[0]["abs_y"], 400)
            self.assertNotIn("pos_mode", editor.actions[0])
        finally:
            bg_ocr.qt.actions.capture_full_preview = old_capture
            QtWidgets.QMessageBox.information = old_information
            editor.deleteLater()
            owner.deleteLater()

        self.assertEqual(picker_calls, [(img, "point")])

    def test_qt_action_editor_combo_boxes_only_wheel_when_focused(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtGui, QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget([{"kind": "mouse"}])

        def send_wheel(widget):
            event = QtGui.QWheelEvent(
                QtCore.QPointF(1, 1),
                QtCore.QPointF(1, 1),
                QtCore.QPoint(0, 0),
                QtCore.QPoint(0, 120),
                QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier,
                QtCore.Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            QtWidgets.QApplication.sendEvent(widget, event)

        combo = editor._fields["pos_mode"]
        try:
            editor.show()
            combo.setCurrentText("offset")
            editor.setFocus()
            combo.clearFocus()
            QtWidgets.QApplication.processEvents()

            send_wheel(combo)
            self.assertEqual(combo.currentText(), "识别位置+偏移")

            combo.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            QtWidgets.QApplication.processEvents()
            send_wheel(combo)
            self.assertNotEqual(combo.currentText(), "识别位置+偏移")
        finally:
            editor.deleteLater()

    def test_qt_action_editor_reorders_saved_actions(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = bg_ocr.qt.actions._ActionSequenceWidget(
            [
                {"kind": "delay", "seconds": 1.0},
                {"kind": "text", "text": "hello"},
            ]
        )
        try:
            editor._move_action(-1, 1)
            self.assertEqual([a["kind"] for a in editor.actions], ["text", "delay"])
        finally:
            editor.deleteLater()

    def test_qt_action_json_dialog_replaces_actions_with_valid_json(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.actions

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr.qt.actions._ActionJsonDialog([{"kind": "delay", "seconds": 0.5}])
        try:
            dialog._edit.setPlainText('[{"kind": "text", "text": "ok"}]')
            dialog._accept()
            self.assertEqual(dialog.actions, [{"kind": "text", "text": "ok", "interval": 0.05}])
        finally:
            dialog.deleteLater()

    def test_qt_popup_template_dialog_preserves_unknown_fields_and_type(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._PopupTemplateDialog(
            [{"name": "Future", "type": "future_template", "future_field": {"keep": True}}]
        )
        try:
            dialog._accept()
            self.assertEqual(dialog.templates[0]["type"], "future_template")
            self.assertEqual(dialog.templates[0]["future_field"], {"keep": True})
        finally:
            dialog.deleteLater()

    def test_qt_popup_template_stop_options_are_mutually_exclusive(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._PopupTemplateDialog([{"name": "Popup"}])
        try:
            stop_flow = dialog._fields["after_match_stop_flow"]
            stop_all = dialog._fields["after_match_stop_all"]

            stop_flow.setChecked(True)
            stop_all.setChecked(True)
            self.assertFalse(stop_flow.isChecked())
            self.assertTrue(stop_all.isChecked())

            stop_flow.setChecked(True)
            self.assertTrue(stop_flow.isChecked())
            self.assertFalse(stop_all.isChecked())
        finally:
            dialog.deleteLater()

    def test_qt_popup_template_move_keeps_edited_template_with_row(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dialog = bg_ocr_qt._PopupTemplateDialog([
            {"name": "First", "type": "ocr", "keywords": "one"},
            {"name": "Second", "type": "image", "template_path": r"C:\templates\second.png"},
        ])
        try:
            dialog._fields["name"].setText("First edited")
            dialog._fields["keywords"].setText("edited")
            dialog._move_template(1)

            self.assertEqual(dialog._current, 1)
            self.assertEqual(dialog._list.currentRow(), 1)
            self.assertEqual(dialog.templates[0]["name"], "Second")
            self.assertEqual(dialog.templates[0]["type"], "image")
            self.assertEqual(dialog.templates[0]["template_path"], r"C:\templates\second.png")
            self.assertEqual(dialog.templates[1]["name"], "First edited")
            self.assertEqual(dialog.templates[1]["type"], "ocr")
            self.assertEqual(dialog.templates[1]["keywords"], "edited")
        finally:
            dialog.deleteLater()

    def test_qt_popup_template_picks_window_and_screen_click_points(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.templates

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.assertTrue(hasattr(bg_ocr_qt._PopupTemplateDialog, "_pick_window_coord"))
        self.assertTrue(hasattr(bg_ocr_qt._PopupTemplateDialog, "_pick_screen_coord"))
        self.assertIn("screen_point_picker_cls", inspect.signature(bg_ocr_qt._PopupTemplateDialog).parameters)

        img = Image.new("RGB", (16, 16), (0, 0, 0))
        picker_calls = []

        class Owner(QtWidgets.QWidget):
            cfg = {"capture_mode": "printwindow"}

            def current_hwnd(self):
                return 12345

        class ImagePicker:
            def __init__(self, picked_img, mode, _parent):
                self.selection = (9, 10)
                picker_calls.append((picked_img, mode))

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        class ScreenPicker:
            def __init__(self, _parent):
                self.point = (300, 400)

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

        old_capture = bg_ocr.qt.templates.capture_full_preview
        bg_ocr.qt.templates.capture_full_preview = lambda hwnd, mode: img
        owner = Owner()
        dialog = bg_ocr_qt._PopupTemplateDialog(
            [{"name": "Popup", "click_target": "keyword"}],
            owner,
            image_picker_cls=ImagePicker,
            screen_point_picker_cls=ScreenPicker,
        )
        try:
            dialog._pick_window_coord()
            self.assertEqual(dialog.templates[0]["click_target"], "window")
            self.assertEqual(dialog.templates[0]["custom_x"], 9)
            self.assertEqual(dialog.templates[0]["custom_y"], 10)

            dialog._pick_screen_coord()
            self.assertEqual(dialog.templates[0]["click_target"], "screen")
            self.assertEqual(dialog.templates[0]["custom_x"], 300)
            self.assertEqual(dialog.templates[0]["custom_y"], 400)
        finally:
            bg_ocr.qt.templates.capture_full_preview = old_capture
            dialog.deleteLater()
            owner.deleteLater()

        self.assertEqual(picker_calls, [(img, "point")])

    def test_qt_move_group_remaps_chain_targets(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        bg_ocr.qt.main_window.save_config = lambda _cfg: None
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First", "chain_enabled": True, "chain_target": 1}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                ]
            }
            win._current_index = 0
            win._refresh_group_list()
            win._group_list.setCurrentRow(0)
            win._load_group_editor(0)
            win._move_group(1)
            self.assertEqual([g["name"] for g in win.cfg["groups"]], ["Second", "First"])
            self.assertEqual(win.cfg["groups"][1]["chain_target"], 0)
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_delete_group_cancel_keeps_config_unchanged(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_manager

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        old_question = bg_ocr.qt.group_manager.QtWidgets.QMessageBox.question
        saved = []
        bg_ocr.qt.main_window.save_config = lambda cfg: saved.append(dict(cfg))
        bg_ocr.qt.group_manager.QtWidgets.QMessageBox.question = (
            lambda *_args: QtWidgets.QMessageBox.StandardButton.No
        )
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First"}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                ]
            }
            win._current_index = 1
            win._refresh_group_list()
            win._group_list.setCurrentRow(1)
            win._delete_group()
            self.assertEqual([g["name"] for g in win.cfg["groups"]], ["First", "Second"])
            self.assertEqual(win._current_index, 1)
            self.assertEqual(win._group_list.currentRow(), 1)
            self.assertEqual(saved, [])
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            bg_ocr.qt.group_manager.QtWidgets.QMessageBox.question = old_question
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_delete_group_remaps_chain_targets_and_saves(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_manager

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        old_question = bg_ocr.qt.group_manager.QtWidgets.QMessageBox.question
        saved = []
        bg_ocr.qt.main_window.save_config = lambda cfg: saved.append(dict(cfg))
        bg_ocr.qt.group_manager.QtWidgets.QMessageBox.question = (
            lambda *_args: QtWidgets.QMessageBox.StandardButton.Yes
        )
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First", "chain_enabled": True, "chain_target": 1}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                    bg_ocr_qt._copy_group({"name": "Third", "chain_enabled": True, "chain_target": 2}),
                ]
            }
            win._current_index = 1
            win._refresh_group_list()
            win._group_list.setCurrentRow(1)
            win._load_group_editor(1)
            win._delete_group()
            self.assertEqual([g["name"] for g in win.cfg["groups"]], ["First", "Third"])
            self.assertFalse(win.cfg["groups"][0]["chain_enabled"])
            self.assertEqual(win.cfg["groups"][0]["chain_target"], -1)
            self.assertEqual(win.cfg["groups"][1]["chain_target"], 1)
            self.assertEqual(win._current_index, 0)
            self.assertEqual(win._group_list.currentRow(), 0)
            self.assertEqual(saved[-1], win.cfg)
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            bg_ocr.qt.group_manager.QtWidgets.QMessageBox.question = old_question
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_quick_table_context_menu_opens_group_detail_page(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First"}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                ]
            }
            win._refresh_group_list()
            win._refresh_quick_config()
            win._page_nav.setCurrentRow(0)
            pos = QtCore.QPoint(4, win._quick_table.rowViewportPosition(1) + 4)
            win._show_quick_group_detail(pos)
            self.assertEqual(win._page_nav.currentRow(), 1)
            self.assertEqual(win._group_list.currentRow(), 1)
            self.assertEqual(win._group_editor.dump_group(1)["name"], "Second")
        finally:
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_quick_table_template_column_edits_image_groups_only(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtCore, QtWidgets

        import bg_ocr.qt.theme

        for theme in ["default", "modern"]:
            qss = bg_ocr.qt.theme.load_theme(theme)
            with self.subTest(theme=theme):
                self.assertIn("QTableWidget#quickConfigTable QLineEdit#quickTemplatePath", qss)
                self.assertIn("QTableWidget#quickConfigTable QPushButton#quickTemplateButton", qss)
                self.assertIn("min-width: 160px", qss)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        saved = []
        bg_ocr.qt.main_window.save_config = lambda cfg: saved.append({"groups": [dict(group) for group in cfg["groups"]]})
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "Image", "type": "image", "template_path": r"C:\old.png"}),
                    bg_ocr_qt._copy_group({"name": "Ocr", "type": "ocr"}),
                ]
            }
            win._current_index = 0
            win._refresh_group_list()
            win._load_group_editor(0)
            win._refresh_quick_config()

            self.assertEqual(win._quick_table.columnCount(), 6)
            self.assertEqual(win._quick_table.objectName(), "quickConfigTable")
            self.assertEqual(win._quick_table.horizontalHeaderItem(5).text(), "模板图")
            image_cell = win._quick_table.cellWidget(0, 5)
            self.assertIsNotNone(image_cell)
            self.assertEqual(image_cell.objectName(), "quickTemplateCell")
            edit = image_cell.findChild(QtWidgets.QLineEdit, "quickTemplatePath")
            self.assertIsNotNone(edit)
            self.assertEqual(edit.text(), r"C:\old.png")
            buttons = image_cell.findChildren(QtWidgets.QPushButton, "quickTemplateButton")
            self.assertEqual([button.text() for button in buttons], ["浏览", "截取"])
            self.assertIsNone(win._quick_table.cellWidget(1, 5))
            self.assertFalse(win._quick_table.item(1, 5).flags() & QtCore.Qt.ItemFlag.ItemIsEditable)

            edit.setText(r"C:\new.png")
            win._save_quick_config()
            self.assertEqual(saved[-1]["groups"][0]["template_path"], r"C:\new.png")
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_quick_reorder_remaps_chain_and_keeps_selection(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        bg_ocr.qt.main_window.save_config = lambda _cfg: None
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First", "chain_enabled": True, "chain_target": 2}),
                    bg_ocr_qt._copy_group({"name": "Second"}),
                    bg_ocr_qt._copy_group({"name": "Third"}),
                ]
            }
            win._current_index = 1
            win._refresh_group_list()
            win._load_group_editor(1)
            win._refresh_quick_config()
            for row, seq in enumerate(["3", "1", "2"]):
                win._quick_table.item(row, 1).setText(seq)
            win._save_quick_config()
            self.assertEqual([g["name"] for g in win.cfg["groups"]], ["Second", "Third", "First"])
            self.assertEqual(win._current_index, 0)
            self.assertEqual(win.cfg["groups"][2]["chain_target"], 1)
            self.assertEqual([g["seq"] for g in win.cfg["groups"]], [1, 2, 3])
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_quick_save_rejects_invalid_sequence_without_saving(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_manager

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        old_critical = bg_ocr.qt.group_manager.QtWidgets.QMessageBox.critical
        saved = []
        criticals = []
        bg_ocr.qt.main_window.save_config = lambda cfg: saved.append(dict(cfg))
        bg_ocr.qt.group_manager.QtWidgets.QMessageBox.critical = (
            lambda _parent, title, text: criticals.append((title, text))
        )
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First", "seq": 1}),
                    bg_ocr_qt._copy_group({"name": "Second", "seq": 2}),
                ]
            }
            win._current_index = 1
            win._refresh_group_list()
            win._load_group_editor(1)
            win._refresh_quick_config()
            win._quick_table.item(0, 1).setText("bad")
            win._save_quick_config()
            self.assertEqual([g["name"] for g in win.cfg["groups"]], ["First", "Second"])
            self.assertEqual(win._current_index, 1)
            self.assertEqual(saved, [])
            self.assertEqual(criticals[0][0], "Error")
            self.assertIn("not a valid integer", criticals[0][1])
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            bg_ocr.qt.group_manager.QtWidgets.QMessageBox.critical = old_critical
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_quick_save_rejects_duplicate_sequence_without_saving(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        import bg_ocr.qt.group_manager

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        old_critical = bg_ocr.qt.group_manager.QtWidgets.QMessageBox.critical
        saved = []
        criticals = []
        bg_ocr.qt.main_window.save_config = lambda cfg: saved.append(dict(cfg))
        bg_ocr.qt.group_manager.QtWidgets.QMessageBox.critical = (
            lambda _parent, title, text: criticals.append((title, text))
        )
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {
                "groups": [
                    bg_ocr_qt._copy_group({"name": "First", "seq": 1}),
                    bg_ocr_qt._copy_group({"name": "Second", "seq": 2}),
                ]
            }
            win._current_index = 0
            win._refresh_group_list()
            win._load_group_editor(0)
            win._refresh_quick_config()
            win._quick_table.item(0, 1).setText("1")
            win._quick_table.item(1, 1).setText("1")
            win._save_quick_config()
            self.assertEqual([g["name"] for g in win.cfg["groups"]], ["First", "Second"])
            self.assertEqual(win._current_index, 0)
            self.assertEqual(saved, [])
            self.assertEqual(criticals[0][0], "Duplicate sequence")
            self.assertIn("Duplicate sequence values", criticals[0][1])
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            bg_ocr.qt.group_manager.QtWidgets.QMessageBox.critical = old_critical
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

    def test_qt_quick_save_with_no_groups_keeps_empty_selection_stable(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        old_save = bg_ocr.qt.main_window.save_config
        saved = []
        bg_ocr.qt.main_window.save_config = lambda cfg: saved.append(dict(cfg))
        win = bg_ocr_qt.BgOcrQtWindow()
        try:
            win.cfg = {"groups": []}
            win._current_index = 0
            win._refresh_group_list()
            win._refresh_quick_config()
            win._save_quick_config()
            self.assertEqual(win._current_index, 0)
            self.assertEqual(win._group_list.currentRow(), -1)
            self.assertEqual(saved[-1], {"groups": []})
        finally:
            bg_ocr.qt.main_window.save_config = old_save
            win._auto_bind_stop.set()
            win._stop()
            win.deleteLater()

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
        import bg_ocr.qt.runtime_checks

        win = bg_ocr_qt.BgOcrQtWindow.__new__(bg_ocr_qt.BgOcrQtWindow)
        win.cfg = {
            "groups": [
                {
                    "enabled": True,
                    "type": "noop",
                    "popup_enabled": True,
                    "popup_title_kw": "Popup",
                    "popup_templates": [{"type": "ocr", "ocr_engine": "tesseract"}],
                }
            ]
        }
        old = bg_ocr.qt.runtime_checks.HAS_TESSERACT
        bg_ocr.qt.runtime_checks.HAS_TESSERACT = False
        try:
            missing = win._missing_runtime_dependency()
            self.assertIn("group 1 popup 1", missing)
            self.assertIn("Tesseract", missing)
        finally:
            bg_ocr.qt.runtime_checks.HAS_TESSERACT = old

    def test_qt_runtime_dependency_checks_pyautogui_for_group_actions(self):
        import bg_ocr.qt.runtime_checks

        win = bg_ocr_qt.BgOcrQtWindow.__new__(bg_ocr_qt.BgOcrQtWindow)
        old = bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI
        bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI = False
        try:
            cases = [
                ("key", {"actions": [{"kind": "key", "key": "enter"}]}),
                ("text", {"actions": [{"kind": "text", "text": "hello"}]}),
                ("scroll", {"actions": [{"kind": "scroll", "abs_x": 1, "abs_y": 2}]}),
                ("screen mouse", {"actions": [{"kind": "mouse", "pos_mode": "screen"}]}),
                (
                    "quickswitch mouse",
                    {"click_mode": "quickswitch", "actions": [{"kind": "mouse", "pos_mode": "window"}]},
                ),
            ]
            for label, overrides in cases:
                with self.subTest(label=label):
                    group = {"enabled": True, "type": "noop"}
                    group.update(overrides)
                    win.cfg = {"groups": [group]}
                    missing = win._missing_runtime_dependency()
                    self.assertIsNotNone(missing)
                    self.assertIn("group 1 action 1", missing)
                    self.assertIn("pyautogui", missing)
        finally:
            bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI = old

    def test_qt_runtime_dependency_checks_pyautogui_for_popup_actions(self):
        import bg_ocr.qt.runtime_checks

        win = bg_ocr_qt.BgOcrQtWindow.__new__(bg_ocr_qt.BgOcrQtWindow)
        win.cfg = {
            "groups": [
                {
                    "enabled": True,
                    "type": "noop",
                    "popup_enabled": True,
                    "popup_title_kw": "Popup",
                    "popup_templates": [
                        {"type": "noop", "actions": [{"kind": "text", "text": "popup"}]},
                    ],
                }
            ]
        }
        old = bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI
        bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI = False
        try:
            missing = win._missing_runtime_dependency()
            self.assertIsNotNone(missing)
            self.assertIn("group 1 popup 1 action 1", missing)
            self.assertIn("pyautogui", missing)
        finally:
            bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI = old

    def test_qt_runtime_dependency_skips_disabled_popup_flow_actions(self):
        import bg_ocr.qt.runtime_checks

        win = bg_ocr_qt.BgOcrQtWindow.__new__(bg_ocr_qt.BgOcrQtWindow)
        win.cfg = {
            "groups": [
                {
                    "enabled": True,
                    "type": "noop",
                    "popup_enabled": False,
                    "popup_templates": [
                        {"type": "noop", "actions": [{"kind": "text", "text": "disabled popup"}]},
                    ],
                }
            ]
        }
        old = bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI
        bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI = False
        try:
            self.assertIsNone(win._missing_runtime_dependency())
        finally:
            bg_ocr.qt.runtime_checks.HAS_PYAUTOGUI = old

    def test_paddle_engine_is_shared(self):
        self.assertIs(bg_ocr.compat._paddle_engine, bg_ocr.ocr.get_paddle_engine())

    def test_keyword_matching(self):
        matched, keyword = bg_ocr.matching.match_keywords("Hello World", "missing|world")
        self.assertTrue(matched)
        self.assertEqual(keyword, "world")

    def test_color_matching(self):
        if not bg_ocr.matching.HAS_NUMPY:
            self.skipTest("numpy is not available")
        img = Image.new("RGB", (8, 8), (255, 0, 0))
        matched, pos = bg_ocr.matching.match_color(img, [255, 0, 0], 0)
        self.assertTrue(matched)
        self.assertEqual(pos, (3, 3))

    def test_template_matching_when_cv2_available(self):
        if not bg_ocr.matching.HAS_CV2:
            self.skipTest("opencv-python is not available")
        img = Image.new("RGB", (8, 8), (255, 0, 0))
        template = bg_ocr.matching._pil_to_bgr(img)
        matched, pos, score = bg_ocr.matching.match_template(img, template, 0.9)
        self.assertTrue(matched)
        self.assertEqual(pos, (4, 4))
        self.assertGreaterEqual(score, 0.9)


if __name__ == "__main__":
    unittest.main()
