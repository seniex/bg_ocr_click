from PyQt6 import QtCore, QtGui, QtWidgets

from bg_ocr.system import list_windows


class _ImagePickerDialog(QtWidgets.QDialog):
    def __init__(self, pil_image, mode="rect", parent=None):
        super().__init__(parent)
        self.setObjectName("imagePickerDialog")
        self.setWindowTitle("选择区域")
        self.setModal(True)
        self._mode = mode
        self._image = pil_image
        self._selection = None

        img = pil_image.convert("RGBA")
        self._qimage = QtGui.QImage(
            img.tobytes("raw", "RGBA"),
            img.width,
            img.height,
            img.width * 4,
            QtGui.QImage.Format.Format_RGBA8888,
        ).copy()
        pix = QtGui.QPixmap.fromImage(self._qimage)

        self._label = _PickLabel(pix, mode, self)
        self._label.selected.connect(self._on_selected)
        self._label.clicked.connect(self._on_clicked)

        self._info = QtWidgets.QLabel("拖拽选择区域，释放后自动确认" if mode == "rect" else "点击取样")
        self._info.setObjectName("pickerInfo")
        self._info.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._info)
        layout.addWidget(btns)
        self.resize(min(pix.width() + 40, 1280), min(pix.height() + 100, 900))

    def _on_selected(self, data):
        self._selection = data
        self.accept()

    def _on_clicked(self, data):
        self._selection = data
        self.accept()

    @property
    def selection(self):
        return self._selection


class _PickLabel(QtWidgets.QLabel):
    selected = QtCore.pyqtSignal(object)
    clicked = QtCore.pyqtSignal(object)

    def __init__(self, pixmap, mode, parent=None):
        super().__init__(parent)
        self.setObjectName("pickerImage")
        self.setPixmap(pixmap)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setMouseTracking(True)
        self._mode = mode
        self._drag_start = None
        self._drag_end = None
        self._scale = 1.0
        self._base = pixmap
        self._selection_color = QtGui.QColor("#3d6bff")
        self._selection_pen_width = 2
        self.setMinimumSize(pixmap.size())

    @QtCore.pyqtProperty(QtGui.QColor)
    def selectionColor(self):
        return QtGui.QColor(self._selection_color)

    @selectionColor.setter
    def selectionColor(self, color):
        next_color = QtGui.QColor(color)
        if next_color.isValid():
            self._selection_color = next_color
            self.update()

    @QtCore.pyqtProperty(int)
    def selectionPenWidth(self):
        return self._selection_pen_width

    @selectionPenWidth.setter
    def selectionPenWidth(self, width):
        try:
            self._selection_pen_width = max(1, int(width))
            self.update()
        except (TypeError, ValueError):
            pass

    def _map_pos(self, pos):
        return int(pos.x() / self._scale), int(pos.y() / self._scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._base.isNull():
            return
        scale = min(self.width() / self._base.width(), self.height() / self._base.height(), 1.0)
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        size = QtCore.QSize(
            max(1, int(self._base.width() * scale)),
            max(1, int(self._base.height() * scale)),
        )
        self.setPixmap(self._base.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        ))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_end = event.position()
            self.update()

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            self._drag_end = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._mode == "point":
            x, y = self._map_pos(event.position())
            self.clicked.emit((x, y))
            return
        if self._drag_start is None:
            return
        self._drag_end = event.position()
        x1 = int(min(self._drag_start.x(), self._drag_end.x()) / self._scale)
        y1 = int(min(self._drag_start.y(), self._drag_end.y()) / self._scale)
        x2 = int(max(self._drag_start.x(), self._drag_end.x()) / self._scale)
        y2 = int(max(self._drag_start.y(), self._drag_end.y()) / self._scale)
        self._drag_start = None
        self._drag_end = None
        if x2 - x1 > 4 and y2 - y1 > 4:
            self.selected.emit([x1, y1, x2, y2])

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._mode != "rect" or self._drag_start is None or self._drag_end is None:
            return
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(self.selectionColor, self.selectionPenWidth, QtCore.Qt.PenStyle.DashLine))
        rect = QtCore.QRectF(self._drag_start, self._drag_end).normalized()
        painter.drawRect(rect)


class _ScreenPointPickerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick screen point")
        self.setModal(True)
        self._point = None
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setObjectName("screenPointOverlay")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._hit_test_fill = QtGui.QColor(0, 0, 0, 1)

        geom = QtCore.QRect()
        for screen in QtGui.QGuiApplication.screens():
            geom = geom.united(screen.geometry()) if geom.isValid() else screen.geometry()
        if geom.isValid():
            self.setGeometry(geom)

        self._hint_label = QtWidgets.QLabel("Click target point, Esc to cancel", self)
        self._hint_label.setObjectName("screenPointHint")
        self._hint_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hint_label.adjustSize()
        self._hint_label.move(max(20, self.width() // 2 - self._hint_label.width() // 2), 30)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self._hit_test_fill)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = event.globalPosition().toPoint()
            self._point = (pos.x(), pos.y())
            self.accept()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @property
    def point(self):
        return self._point


class _WindowPickerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("windowPickerDialog")
        self.setWindowTitle("选择目标窗口")
        self.setModal(True)
        self._windows = []
        self._selected = None

        self._filter = QtWidgets.QLineEdit()
        self._filter.setObjectName("windowPickerFilter")
        self._filter.setPlaceholderText("标题关键字")
        self._list = QtWidgets.QListWidget()
        self._list.setObjectName("windowPickerList")
        self._refresh_btn = QtWidgets.QPushButton("刷新")
        self._bind_btn = QtWidgets.QPushButton("绑定")
        self._cancel_btn = QtWidgets.QPushButton("取消")

        for btn in [self._refresh_btn, self._bind_btn, self._cancel_btn]:
            btn.setObjectName("windowPickerActionButton")

        self._refresh_btn.clicked.connect(self._refresh)
        self._bind_btn.clicked.connect(self._accept_selected)
        self._cancel_btn.clicked.connect(self.reject)
        self._filter.textChanged.connect(self._refresh)
        self._list.itemDoubleClicked.connect(lambda _item: self._accept_selected())

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self._filter)
        top.addWidget(self._refresh_btn)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._bind_btn)
        buttons.addWidget(self._cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._list)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self):
        key = self._filter.text().strip().lower()
        self._list.clear()
        self._windows = list_windows()
        for hwnd, title in self._windows:
            if key and key not in title.lower():
                continue
            self._list.addItem(f"[{hwnd}] {title}")

    def _accept_selected(self):
        row = self._list.currentRow()
        if row < 0:
            return
        visible = []
        key = self._filter.text().strip().lower()
        for hwnd, title in self._windows:
            if key and key not in title.lower():
                continue
            visible.append((hwnd, title))
        if 0 <= row < len(visible):
            self._selected = visible[row]
            self.accept()

    @property
    def selected(self):
        return self._selected


def _wrap(layout):
    w = QtWidgets.QWidget()
    w.setLayout(layout)
    return w
