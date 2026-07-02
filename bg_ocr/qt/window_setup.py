from __future__ import annotations

from PyQt6 import QtWidgets

from bg_ocr.config import DEFAULT_WINDOW_GEOMETRY, parse_window_geometry
from bg_ocr.system import _is_admin


def _build_status_row(win):
    row = QtWidgets.QHBoxLayout()
    win._status = QtWidgets.QLabel("Stopped")
    win._status.setObjectName("runtimeStatusLabel")
    win._status_dot = QtWidgets.QLabel("*")
    win._status_dot.setObjectName("statusDot")
    win._status_dot.setProperty("running", False)
    win._admin_status = QtWidgets.QLabel(f"管理员: {'是' if _is_admin() else '否'}")
    win._admin_status.setObjectName("adminStatusLabel")
    win._bound = QtWidgets.QLabel("未绑定窗口")
    win._bound.setObjectName("boundWindowLabel")
    win._start_btn = QtWidgets.QPushButton("开始运行")
    win._stop_btn = QtWidgets.QPushButton("停止运行")
    for btn in [win._start_btn, win._stop_btn]:
        btn.setObjectName("runtimeControlButton")
    win._stop_btn.setEnabled(False)
    win._start_btn.clicked.connect(win._start)
    win._stop_btn.clicked.connect(win._stop)

    row.addWidget(win._status_dot)
    row.addWidget(win._status)
    row.addSpacing(12)
    row.addWidget(win._admin_status)
    row.addStretch(1)
    row.addWidget(win._bound)
    row.addWidget(win._start_btn)
    row.addWidget(win._stop_btn)
    return row


def _build_page_nav(win):
    win._page_nav = QtWidgets.QListWidget()
    win._page_nav.setObjectName("pageNav")
    win._page_nav.addItems(["首页", "监控组", "设置"])
    win._page_nav.currentRowChanged.connect(win._tabs.setCurrentIndex)
    return win._page_nav


def _build_group_sidebar(win):
    panel = QtWidgets.QWidget()
    panel.setObjectName("groupSidebar")
    layout = QtWidgets.QVBoxLayout(panel)

    win._group_list = QtWidgets.QListWidget()
    win._group_list.setObjectName("groupList")
    win._group_list.currentRowChanged.connect(win._on_group_changed)
    win._group_list.itemClicked.connect(lambda item: win._show_group_detail(win._group_list.row(item)))
    win._group_add = QtWidgets.QPushButton("新增")
    win._group_del = QtWidgets.QPushButton("删除")
    win._group_up = QtWidgets.QPushButton("上移")
    win._group_down = QtWidgets.QPushButton("下移")
    win._group_save = QtWidgets.QPushButton("保存当前组")
    for btn in [win._group_add, win._group_del, win._group_up, win._group_down]:
        btn.setObjectName("groupSidebarButton")
    win._group_save.setObjectName("groupSidebarSaveButton")
    win._group_add.clicked.connect(win._add_group)
    win._group_del.clicked.connect(win._delete_group)
    win._group_up.clicked.connect(lambda: win._move_group(-1))
    win._group_down.clicked.connect(lambda: win._move_group(1))
    win._group_save.clicked.connect(win._save_group_config)

    layout.addWidget(win._group_list)
    row = QtWidgets.QHBoxLayout()
    for btn in [win._group_add, win._group_del, win._group_up, win._group_down]:
        row.addWidget(btn)
    layout.addLayout(row)
    layout.addWidget(win._group_save)
    return panel


def _build_ui(win):
    win.setWindowTitle("BgOcrClick Qt")
    win.resize(*parse_window_geometry(DEFAULT_WINDOW_GEOMETRY))

    central = QtWidgets.QWidget()
    root = QtWidgets.QVBoxLayout(central)
    win.setCentralWidget(central)

    win._tabs = QtWidgets.QStackedWidget()
    root.addLayout(_build_status_row(win))

    win._home = win._build_home_tab()
    win._groups = win._build_groups_tab()
    win._settings = win._build_settings_tab()
    win._tabs.addWidget(win._home)
    win._tabs.addWidget(win._groups)
    win._tabs.addWidget(win._settings)

    body = QtWidgets.QHBoxLayout()
    sidebar = QtWidgets.QVBoxLayout()
    sidebar.addWidget(_build_page_nav(win))
    sidebar.addWidget(_build_group_sidebar(win), 1)
    body.addLayout(sidebar, 1)
    body.addWidget(win._tabs, 4)
    root.addLayout(body, 1)

    win._page_nav.setCurrentRow(0)
