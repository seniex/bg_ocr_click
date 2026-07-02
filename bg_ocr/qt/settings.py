from PyQt6 import QtCore, QtWidgets

from bg_ocr.action_runtime import _play_sound
from bg_ocr.qt.theme import THEMES
from bg_ocr.system import _relaunch_as_admin


class _SettingsEditor(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsEditor")
        self._widgets = {}
        self._loading = False
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(8)
        self._widgets["tesseract_path"] = QtWidgets.QLineEdit()
        self._widgets["paddle_exe_path"] = QtWidgets.QLineEdit()
        self._widgets["capture_mode"] = QtWidgets.QComboBox()
        self._widgets["capture_mode"].addItems(["printwindow", "imagegrab", "auto"])
        self._widgets["theme"] = QtWidgets.QComboBox()
        self._widgets["theme"].addItems(list(THEMES))
        self._widgets["sound_enabled"] = QtWidgets.QCheckBox("启用音效提示")
        self._widgets["sound_file"] = QtWidgets.QLineEdit()
        self._widgets["sound_on_match"] = QtWidgets.QCheckBox("Main match")
        self._widgets["sound_on_popup_match"] = QtWidgets.QCheckBox("弹窗匹配")
        self._widgets["sound_on_no_match"] = QtWidgets.QCheckBox("Popup no match")
        self._widgets["start_on_launch"] = QtWidgets.QCheckBox("启动时自动开始")
        self._widgets["hotkey_start"] = QtWidgets.QComboBox()
        self._widgets["hotkey_stop"] = QtWidgets.QComboBox()
        for cb in [self._widgets["hotkey_start"], self._widgets["hotkey_stop"]]:
            cb.addItems(["", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"])
        self._widgets["auto_bind_enabled"] = QtWidgets.QCheckBox("按进程名自动绑定")
        self._widgets["auto_bind_process"] = QtWidgets.QLineEdit()
        self._widgets["paddle_exe_browse"] = QtWidgets.QPushButton("浏览")
        self._widgets["tess_browse"] = QtWidgets.QPushButton("浏览")
        self._widgets["sound_browse"] = QtWidgets.QPushButton("浏览")
        self._widgets["sound_test"] = QtWidgets.QPushButton("试听")
        self._widgets["relaunch_admin"] = QtWidgets.QPushButton("以管理员重启")

        for key in ["tesseract_path", "paddle_exe_path", "sound_file"]:
            self._widgets[key].setObjectName("settingsPathField")
        for key in ["paddle_exe_browse", "tess_browse", "sound_browse"]:
            self._widgets[key].setObjectName("settingsBrowseButton")
        self._widgets["sound_test"].setObjectName("settingsSoundTestButton")

        self._widgets["paddle_exe_browse"].clicked.connect(self._browse_paddle)
        self._widgets["tess_browse"].clicked.connect(self._browse_tess)
        self._widgets["sound_browse"].clicked.connect(self._browse_sound)
        self._widgets["sound_test"].clicked.connect(lambda: _play_sound(self._widgets["sound_file"].text().strip()))
        self._widgets["relaunch_admin"].clicked.connect(_relaunch_as_admin)
        self._connect_change_signals()

        form.addRow("Tesseract", self._row(self._widgets["tesseract_path"], self._widgets["tess_browse"]))
        form.addRow("PaddleOCR-json", self._row(self._widgets["paddle_exe_path"], self._widgets["paddle_exe_browse"]))
        form.addRow("截取模式", self._widgets["capture_mode"])
        form.addRow("Theme", self._widgets["theme"])
        form.addRow("Sound enabled", self._widgets["sound_enabled"])
        form.addRow("音效文件", self._row(self._widgets["sound_file"], self._widgets["sound_browse"], self._widgets["sound_test"]))
        form.addRow("音效触发", self._row(
            self._widgets["sound_on_match"],
            self._widgets["sound_on_popup_match"],
            self._widgets["sound_on_no_match"],
        ))
        form.addRow("启动行为", self._widgets["start_on_launch"])
        form.addRow("启动热键", self._widgets["hotkey_start"])
        form.addRow("停止热键", self._widgets["hotkey_stop"])
        form.addRow("自动绑定", self._row(self._widgets["auto_bind_enabled"], self._widgets["auto_bind_process"]))
        form.addRow("管理员", self._widgets["relaunch_admin"])
        layout.addLayout(form)
        layout.addStretch(1)

    def _connect_change_signals(self):
        for widget in self._widgets.values():
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.textChanged.connect(self._on_changed)
            elif isinstance(widget, QtWidgets.QComboBox):
                widget.currentTextChanged.connect(self._on_changed)
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.toggled.connect(self._on_changed)

    def _on_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    def _row(self, *widgets):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            lay.addWidget(widget)
        return w

    def load_settings(self, cfg):
        self._loading = True
        try:
            self._widgets["tesseract_path"].setText(cfg.get("tesseract_path", ""))
            self._widgets["paddle_exe_path"].setText(cfg.get("paddle_exe_path", ""))
            self._widgets["capture_mode"].setCurrentText(cfg.get("capture_mode", "printwindow"))
            self._widgets["theme"].setCurrentText(cfg.get("theme", "default"))
            self._widgets["sound_enabled"].setChecked(bool(cfg.get("sound_enabled", False)))
            self._widgets["sound_file"].setText(cfg.get("sound_file", ""))
            self._widgets["sound_on_match"].setChecked(bool(cfg.get("sound_on_match", True)))
            self._widgets["sound_on_popup_match"].setChecked(bool(cfg.get("sound_on_popup_match", False)))
            self._widgets["sound_on_no_match"].setChecked(bool(cfg.get("sound_on_no_match", True)))
            self._widgets["start_on_launch"].setChecked(bool(cfg.get("start_on_launch", True)))
            self._widgets["hotkey_start"].setCurrentText(cfg.get("hotkey_start", "").upper())
            self._widgets["hotkey_stop"].setCurrentText(cfg.get("hotkey_stop", "").upper())
            self._widgets["auto_bind_enabled"].setChecked(bool(cfg.get("auto_bind_enabled", False)))
            self._widgets["auto_bind_process"].setText(cfg.get("auto_bind_process", ""))
        finally:
            self._loading = False

    def dump_settings(self):
        return {
            "tesseract_path": self._widgets["tesseract_path"].text().strip(),
            "paddle_exe_path": self._widgets["paddle_exe_path"].text().strip(),
            "capture_mode": self._widgets["capture_mode"].currentText(),
            "theme": self._widgets["theme"].currentText(),
            "sound_enabled": self._widgets["sound_enabled"].isChecked(),
            "sound_file": self._widgets["sound_file"].text().strip(),
            "sound_on_match": self._widgets["sound_on_match"].isChecked(),
            "sound_on_popup_match": self._widgets["sound_on_popup_match"].isChecked(),
            "sound_on_no_match": self._widgets["sound_on_no_match"].isChecked(),
            "start_on_launch": self._widgets["start_on_launch"].isChecked(),
            "hotkey_start": self._widgets["hotkey_start"].currentText().strip().lower(),
            "hotkey_stop": self._widgets["hotkey_stop"].currentText().strip().lower(),
            "auto_bind_enabled": self._widgets["auto_bind_enabled"].isChecked(),
            "auto_bind_process": self._widgets["auto_bind_process"].text().strip(),
        }

    def _browse_paddle(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择PaddleOCR-json.exe", "", "EXE (*.exe);;All (*.*)")
        if path:
            self._widgets["paddle_exe_path"].setText(path)

    def _browse_tess(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择tesseract.exe", "", "EXE (*.exe);;All (*.*)")
        if path:
            self._widgets["tesseract_path"].setText(path)

    def _browse_sound(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择音效文件", "", "Audio (*.wav *.mp3);;All (*.*)")
        if path:
            self._widgets["sound_file"].setText(path)
