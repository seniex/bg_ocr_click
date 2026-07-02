from PyQt6 import QtCore, QtWidgets

from bg_ocr.qt.group_editor import _GroupEditor
from bg_ocr.qt.settings import _SettingsEditor


def _build_home_tab(self):
    root = QtWidgets.QWidget()
    root.setObjectName("homeTab")
    layout = QtWidgets.QVBoxLayout(root)

    bind_row = QtWidgets.QHBoxLayout()
    self._title_filter = QtWidgets.QLineEdit(self.cfg.get("target_title", ""))
    self._title_filter.setObjectName("windowTitleFilter")
    self._title_filter.setPlaceholderText("窗口标题关键字")
    self._bind_find = QtWidgets.QPushButton("查找窗口")
    self._bind_pick = QtWidgets.QPushButton("绑定选中")
    self._bind_dialog = QtWidgets.QPushButton("选择窗口")
    for btn in [self._bind_find, self._bind_pick, self._bind_dialog]:
        btn.setObjectName("windowBindButton")
    self._win_list = QtWidgets.QListWidget()
    self._win_list.setObjectName("windowDetailList")
    self._title_filter.returnPressed.connect(self._find_windows)
    self._bind_find.clicked.connect(self._find_windows)
    self._bind_pick.clicked.connect(self._bind_window)
    self._bind_dialog.clicked.connect(self._pick_window_dialog)
    self._win_list.itemDoubleClicked.connect(lambda _item: self._bind_window())
    bind_row.addWidget(self._title_filter)
    bind_row.addWidget(self._bind_find)
    bind_row.addWidget(self._bind_pick)
    bind_row.addWidget(self._bind_dialog)

    self._quick_table = QtWidgets.QTableWidget(0, 6)
    self._quick_table.setObjectName("quickConfigTable")
    self._quick_table.setHorizontalHeaderLabels(["启用", "序号", "组名", "切回", "间隔", "模板图"])
    self._quick_table.horizontalHeader().setStretchLastSection(True)
    self._quick_table.verticalHeader().setVisible(False)
    self._quick_table.itemChanged.connect(lambda _item: None)
    self._quick_table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
    self._quick_table.customContextMenuRequested.connect(self._show_quick_group_detail)
    quick_btns = QtWidgets.QHBoxLayout()
    self._quick_save = QtWidgets.QPushButton("保存快捷配置")
    self._quick_refresh = QtWidgets.QPushButton("刷新列表")
    for btn in [self._quick_save, self._quick_refresh]:
        btn.setObjectName("quickConfigActionButton")
    self._quick_save.clicked.connect(self._save_quick_config)
    self._quick_refresh.clicked.connect(self._refresh_quick_config)
    quick_btns.addWidget(self._quick_save)
    quick_btns.addWidget(self._quick_refresh)
    quick_btns.addStretch(1)

    self._log = QtWidgets.QTextEdit()
    self._log.setObjectName("homeLog")
    self._log.setReadOnly(True)
    self._log.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.WidgetWidth)
    self._log_clear = QtWidgets.QPushButton("清空日志")
    self._log_clear.setObjectName("homeLogClearButton")
    self._log_clear.clicked.connect(self._log.clear)

    layout.addLayout(bind_row)
    layout.addWidget(self._win_list)
    layout.addLayout(quick_btns)
    layout.addWidget(self._quick_table)
    layout.addWidget(self._log)
    layout.addWidget(self._log_clear)
    return root


def _build_groups_tab(self):
    root = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(root)
    self._group_editor = _GroupEditor(self)
    self._group_editor.changed.connect(self._mark_dirty)
    layout.addWidget(self._group_editor)
    return root


def _build_settings_tab(self):
    root = QtWidgets.QWidget()
    root.setObjectName("settingsTab")
    layout = QtWidgets.QVBoxLayout(root)
    self._settings_editor = _SettingsEditor(self)
    layout.addWidget(self._settings_editor)
    self._dep_box = QtWidgets.QPlainTextEdit()
    self._dep_box.setObjectName("dependencyStatus")
    self._dep_box.setReadOnly(True)
    layout.addWidget(self._dep_box)
    self._save_settings_btn = QtWidgets.QPushButton("保存设置")
    self._save_settings_btn.setObjectName("settingsSaveButton")
    self._save_settings_btn.clicked.connect(self._save_settings)
    layout.addWidget(self._save_settings_btn)
    return root
