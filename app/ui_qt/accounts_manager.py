# app/ui_qt/accounts_manager.py
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import select

from app.accounts import add_balancing_account, add_primary_account
from app.db import SessionLocal
from app.models import Account


ACCOUNT_TYPES = ("asset", "liability", "income", "expense", "adjustment")


@dataclass
class NewAccountPayload:
    name: str
    acc_type: str


class AddAccountDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add account")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        form_wrap = QFrame()
        form = QFormLayout(form_wrap)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Current Account, Groceries, Salary")

        self.type_combo = QComboBox()
        for t in ACCOUNT_TYPES:
            self.type_combo.addItem(t, t)

        form.addRow("Name", self.name_edit)
        form.addRow("Type", self.type_combo)

        outer.addWidget(form_wrap)

        btns = QHBoxLayout()
        btns.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.add_btn = QPushButton("Add")
        self.add_btn.setMinimumHeight(34)

        self.cancel_btn.clicked.connect(self.reject)
        self.add_btn.clicked.connect(self._on_add)

        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.add_btn)
        outer.addLayout(btns)

        self._payload: NewAccountPayload | None = None
        self.name_edit.setFocus()

    def _on_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation error", "Name is required.")
            return

        acc_type = str(self.type_combo.currentData())
        if acc_type not in ACCOUNT_TYPES:
            QMessageBox.warning(self, "Validation error", "Invalid account type.")
            return

        self._payload = NewAccountPayload(name=name, acc_type=acc_type)
        self.accept()

    @property
    def payload(self) -> NewAccountPayload | None:
        return self._payload


class AccountsManagerPage(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Accounts Manager")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.add_btn = QPushButton("Add account")
        self.add_btn.setMinimumHeight(32)
        self.add_btn.clicked.connect(self.add_account)

        self.toggle_btn = QPushButton("Toggle active")
        self.toggle_btn.setMinimumHeight(32)
        self.toggle_btn.clicked.connect(self.toggle_active_selected)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.clicked.connect(self.refresh)

        header.addWidget(self.add_btn)
        header.addWidget(self.toggle_btn)
        header.addWidget(self.refresh_btn)
        outer.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Type", "Active"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        outer.addWidget(self.table, 1)

        self.refresh()

    def refresh(self) -> None:
        accounts = self._load_accounts()

        self.table.setRowCount(len(accounts))
        for r, acc in enumerate(accounts):
            self._set_item(r, 0, str(acc.id), align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_item(r, 1, acc.name)
            self._set_item(r, 2, acc.type)
            self._set_item(r, 3, "Yes" if acc.is_active else "No")

        self.table.resizeColumnsToContents()

    def add_account(self) -> None:
        dlg = AddAccountDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        payload = dlg.payload
        if not payload:
            return

        try:
            with SessionLocal() as session:
                if payload.acc_type in ("asset", "liability"):
                    add_primary_account(session, payload.name, payload.acc_type)
                else:
                    add_balancing_account(session, payload.name, payload.acc_type)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add account:\n{e}")
            return

        self.refresh()

    def toggle_active_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Nothing selected", "Select an account row first.")
            return

        id_item = self.table.item(row, 0)
        if not id_item:
            return

        try:
            account_id = int(id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Could not read selected account ID.")
            return

        try:
            with SessionLocal() as session:
                acc = session.get(Account, account_id)
                if not acc:
                    raise ValueError("Account not found.")
                acc.is_active = not bool(acc.is_active)
                session.commit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update account:\n{e}")
            return

        self.refresh()

    def _load_accounts(self) -> list[Account]:
        with SessionLocal() as session:
            return session.execute(select(Account).order_by(Account.name)).scalars().all()

    def _set_item(self, row: int, col: int, text: str, align: Qt.AlignmentFlag | None = None) -> None:
        item = QTableWidgetItem(text)
        if align is not None:
            item.setTextAlignment(int(align))
        self.table.setItem(row, col, item)
