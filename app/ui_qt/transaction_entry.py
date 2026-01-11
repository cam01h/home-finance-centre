# app/ui_qt/transaction_entry.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

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

from sqlalchemy import select

from app.accounts import get_balancing_accounts, get_primary_accounts
from app.db import SessionLocal
from app.ledger import create_transaction
from app.models import Account


@dataclass
class EntryData:
    txn_date: date
    merchant: str
    description: str
    amount_pennies: int
    primary_account_id: int
    balancing_account_id: int


def _decimal_to_pennies(value: Decimal) -> int:
    # Decimal pounds -> pennies (rounded)
    return int((value * 100).to_integral_value())


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

        self.primary_combo = QComboBox()
        self.primary_combo.addItem("— Select primary account —", None)

        self.balancing_combo = QComboBox()
        self.balancing_combo.addItem("— Select balancing account —", None)

        form_layout.addRow("Date", self.date_edit)
        form_layout.addRow("Merchant", self.merchant_edit)
        form_layout.addRow("Description", self.desc_edit)
        form_layout.addRow("Amount", self.amount_edit)
        form_layout.addRow("Primary account", self.primary_combo)
        form_layout.addRow("Balancing account", self.balancing_combo)

        outer.addWidget(form_wrap)

        actions = QHBoxLayout()
        actions.addStretch(1)

        self.save_btn = QPushButton("Save transaction")
        self.save_btn.setMinimumHeight(36)
        self.save_btn.clicked.connect(self.on_save_clicked)
        actions.addWidget(self.save_btn)

        outer.addLayout(actions)
        outer.addStretch(1)

        self.reload_accounts()

    def reload_accounts(self) -> None:
        """Load account dropdowns from DB (active accounts)."""
        self.primary_combo.blockSignals(True)
        self.balancing_combo.blockSignals(True)

        self.primary_combo.clear()
        self.balancing_combo.clear()
        self.primary_combo.addItem("— Select primary account —", None)
        self.balancing_combo.addItem("— Select balancing account —", None)

        with SessionLocal() as session:
            primaries = get_primary_accounts(session, active_only=True)
            bals = get_balancing_accounts(session, active_only=True)

        for acc in primaries:
            self.primary_combo.addItem(acc.name, acc.id)

        for acc in bals:
            self.balancing_combo.addItem(acc.name, acc.id)

        self.primary_combo.blockSignals(False)
        self.balancing_combo.blockSignals(False)

    def on_save_clicked(self) -> None:
        try:
            data = self._read_form()
        except ValueError as e:
            QMessageBox.warning(self, "Validation error", str(e))
            return

        try:
            with SessionLocal() as session:
                create_transaction(
                    session,
                    timestamp=datetime.combine(data.txn_date, datetime.now().time()),
                    description=self._build_description(data.merchant, data.description),
                    primary_account_id=data.primary_account_id,
                    amount_pennies=data.amount_pennies,
                    balancing_account_id=data.balancing_account_id,
                )
        except Exception as e:
            QMessageBox.critical(self, "Database error", f"Failed to save:\n{e}")
            return

        QMessageBox.information(self, "Saved", "Transaction saved.")
        self._reset_form()

    def _build_description(self, merchant: str, desc: str) -> str:
        merchant = merchant.strip()
        desc = desc.strip()
        if merchant and desc:
            return f"{merchant} - {desc}"
        return merchant or desc

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
            amount_dec = Decimal(amt_raw)
        except InvalidOperation:
            raise ValueError("Amount must be a valid number like -12.34 or 1200.00.")
        amount_pennies = _decimal_to_pennies(amount_dec)

        primary_id = self.primary_combo.currentData()
        balancing_id = self.balancing_combo.currentData()

        if not primary_id:
            raise ValueError("Primary account is required.")
        if not balancing_id:
            raise ValueError("Balancing account is required.")
        if primary_id == balancing_id:
            raise ValueError("Primary and balancing accounts must be different.")

        return EntryData(
            txn_date=txn_date,
            merchant=merchant,
            description=description,
            amount_pennies=amount_pennies,
            primary_account_id=int(primary_id),
            balancing_account_id=int(balancing_id),
        )

    def _reset_form(self) -> None:
        self.merchant_edit.clear()
        self.desc_edit.clear()
        self.amount_edit.clear()
        self.primary_combo.setCurrentIndex(0)
        self.balancing_combo.setCurrentIndex(0)
        self.merchant_edit.setFocus()
