"""Qt bindings for the GUI: PySide6 (ReyOS) or PyQt6 (Ubuntu 24.04 has no
PySide6 package). Only what gui.py uses."""
try:
    from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal  # noqa: F401
    from PySide6.QtGui import QAction, QIcon  # noqa: F401
    from PySide6 import QtWidgets  # noqa: F401
    BINDING = "PySide6"
except ImportError:
    from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal as Signal  # noqa: F401
    from PyQt6.QtGui import QAction, QIcon  # noqa: F401
    from PyQt6 import QtWidgets  # noqa: F401
    BINDING = "PyQt6"
