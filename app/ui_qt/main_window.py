# app/ui_qt/main_window.py
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Home Finance Centre (Qt)")
        self.resize(1100, 700)

        # --- Root layout container (central widget) ---
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar (left) ---
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(8)

        title = QLabel("Home Finance")
        title.setObjectName("SidebarTitle")
        sidebar_layout.addWidget(title)

        # Nav buttons (text only for now)
        self.btn_home = QPushButton("Home")
        self.btn_entry = QPushButton("Transaction Entry")
        self.btn_history = QPushButton("Transaction History")
        self.btn_import = QPushButton("Bulk Import")
        self.btn_accounts = QPushButton("Accounts Manager")
        self.nav_buttons = [
            self.btn_home,
            self.btn_entry,
            self.btn_history,
            self.btn_import,
            self.btn_accounts,
        ]


        for btn in self.nav_buttons:
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(36)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch(1)

        # --- Main area (right): ribbon + pages ---
        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Ribbon/header placeholder
        ribbon = QFrame()
        ribbon.setObjectName("Ribbon")
        ribbon.setFixedHeight(56)

        ribbon_layout = QHBoxLayout(ribbon)
        ribbon_layout.setContentsMargins(12, 10, 12, 10)
        ribbon_layout.setSpacing(8)

        self.ribbon_title = QLabel("Home")
        self.ribbon_title.setObjectName("RibbonTitle")
        ribbon_layout.addWidget(self.ribbon_title)
        ribbon_layout.addStretch(1)

        # Pages (stack)
        self.pages = QStackedWidget()
        self.pages.setObjectName("Pages")

        self.page_home = self._make_placeholder_page("Home (dashboard placeholder)")
        self.page_entry = self._make_placeholder_page("Transaction Entry (new rows only)")
        self.page_history = self._make_placeholder_page("Transaction History (DB rows)")
        self.page_import = self._make_placeholder_page("Bulk Import (CSV/PDF)")
        self.page_accounts = self._make_placeholder_page("Accounts Manager")

        self.pages.addWidget(self.page_home)     # index 0
        self.pages.addWidget(self.page_entry)    # index 1
        self.pages.addWidget(self.page_history)  # index 2
        self.pages.addWidget(self.page_import)   # index 3
        self.pages.addWidget(self.page_accounts) # index 4

        # Wire nav -> page switching
        self.btn_home.clicked.connect(lambda: self._go(0, "Home"))
        self.btn_entry.clicked.connect(lambda: self._go(1, "Transaction Entry"))
        self.btn_history.clicked.connect(lambda: self._go(2, "Transaction History"))
        self.btn_import.clicked.connect(lambda: self._go(3, "Bulk Import"))
        self.btn_accounts.clicked.connect(lambda: self._go(4, "Accounts Manager"))

        # Assemble main area
        main_layout.addWidget(ribbon)
        main_layout.addWidget(self.pages, 1)

        # Assemble root
        root_layout.addWidget(sidebar)
        root_layout.addWidget(main_area, 1)

        # Default page
        self._go(0, "Home")

    def _make_placeholder_page(self, text: str) -> QWidget:
        page = QFrame()
        page.setObjectName("Page")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        label = QLabel(text)
        label.setObjectName("PageTitle")
        layout.addWidget(label)
        layout.addStretch(1)

        return page

    def _go(self, index: int, title: str) -> None:
        self.pages.setCurrentIndex(index)
        self.ribbon_title.setText(title)

        # Active nav styling
        for i, btn in enumerate(self.nav_buttons):
            is_active = (i == index)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
