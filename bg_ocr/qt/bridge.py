from PyQt6 import QtCore


class _UiBridge(QtCore.QObject):
    log_requested = QtCore.pyqtSignal(str, str)
    invoke_requested = QtCore.pyqtSignal(object)
    status_requested = QtCore.pyqtSignal(bool)
