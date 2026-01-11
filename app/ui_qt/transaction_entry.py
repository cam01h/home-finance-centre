# app/ui_qt/pages/transaction_entry.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.db import SessionLocal
from app.models import Transaction  # assumes you already have a Transaction model


@dataclass
class EntryData:
    txn_date: date
    merchant: str
    description: str
    amount: Decimal
    account_id: int | None  # optional if your schema supports it


class TransactionEntryPage(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        title = QLabel("Transaction Entry")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        form_wrap = QFrame()
        form_layout = QFormLayout(form_wrap)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())

        self.merchant_edit = QLineEdit()
        self.merchant_edit.setPlaceholderText("e.g. Tesco")

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Optional")

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("e.g. -12.34 (spend) or 1200.00 (income)")

        # NOTE: wire this to real accounts later
        self.account_combo = QComboBox()
        self.account_combo.addItem("— Select account —", None)

        form_layout.addRow("Date", self.date_edit)
        form_layout.addRow("Merchant", self.merchant_edit)
        form_layout.addRow("Description", self.desc_edit)
        form_layout.addRow("Amount", self.amount_edit)
        form_layout.addRow("Account", self.account_combo)

        outer.addWidget(form_wrap)

        # Actions
        actions = QHBoxLayout()
        actions.addStretch(1)

        self.save_btn = QPushButton("Save transaction")
        self.save_btn.setMinimumHeight(36)
        self.save_btn.clicked.connect(self.on_save_clicked)

        actions.addWidget(self.save_btn)
        outer.addLayout(actions)

        outer.addStretch(1)

    def on_save_clicked(self) -> None:
        try:
            data = self._read_form()
        except ValueError as e:
            QMessageBox.warning(self, "Validation error", str(e))
            return

        try:
            self._insert_transaction(data)
        except Exception as e:
            QMessageBox.critical(self, "Database error", f"Failed to save:\n{e}")
            return

        QMessageBox.information(self, "Saved", "Transaction saved.")
        self._reset_form()

    def _read_form(self) -> EntryData:
        qd = self.date_edit.date()
        txn_date = date(qd.year(), qd.month(), qd.day())

        merchant = self.merchant_edit.text().strip()
        if not merchant:
            raise ValueError("Merchant is required.")

        description = self.desc_edit.text().strip()

        amt_raw = self.amount_edit.text().strip()
        if not amt_raw:
            raise ValueError("Amount is required.")
        try:
            amount = Decimal(amt_raw)
        except InvalidOperation:
            raise ValueError("Amount must be a valid number like -12.34 or 1200.00.")

        account_id = self.account_combo.currentData()

        return EntryData(
            txn_date=txn_date,
            merchant=merchant,
            description=description,
            amount=amount,
            account_id=account_id,
        )

    def _insert_transaction(self, data: EntryData) -> None:
        with SessionLocal() as session:
            txn = Transaction(
                date=data.txn_date,
                merchant=data.merchant,
                description=data.description,
                amount=data.amount,
                account_id=data.account_id,
            )
            session.add(txn)
            session.commit()

    def _reset_form(self) -> None:
        self.merchant_edit.clear()
        self.desc_edit.clear()
        self.amount_edit.clear()
        self.account_combo.setCurrentIndex(0)
        self.merchant_edit.setFocus()
