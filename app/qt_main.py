# app/qt_main.py
from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from app.ui_qt.main_window import MainWindow
from app.ui_qt.theme import Theme, build_qss

def main() -> int:
    app = QApplication(sys.argv)

    qss = build_qss(Theme())
    if qss.strip():
        app.setStyleSheet(qss)

    win = MainWindow()
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
