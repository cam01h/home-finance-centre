# app/ui_qt/transaction_history.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
from sqlalchemy.orm import selectinload

from app.accounts import get_balancing_accounts, get_primary_accounts
from app.db import SessionLocal
from app.models import Transaction, Entry
from app.ledger import delete_transaction

def _pennies_to_gbp(amount_pennies: int) -> str:
    return f"{amount_pennies / 100:,.2f}"


def _decimal_to_pennies(value: Decimal) -> int:
    return int((value * 100).to_integral_value())


@dataclass
class TxFlat:
    tx_id: int
    timestamp: datetime
    description: str
    primary_account_id: int
    primary_account_name: str
    balancing_account_id: int
    balancing_account_name: str
    amount_pennies: int  # primary side amount


def _pick_primary_and_balancing(entries: list[Entry]) -> tuple[Entry, Entry]:
    """
    Your ledger writes:
      - primary entry = amount_pennies passed in
      - balancing entry = -amount_pennies
    Prefer primary based on account.type in ('asset','liability') if available.
    """
    if len(entries) < 2:
        raise ValueError("Transaction does not have two entries.")

    primary_entry = None
    for e in entries:
        if getattr(e.account, "type", None) in ("asset", "liability"):
            primary_entry = e
            break

    if primary_entry is None:
        primary_entry = entries[0]

    balancing_entry = next((e for e in entries if e is not primary_entry), entries[1])
    return primary_entry, balancing_entry


class EditTransactionDialog(QDialog):
    def __init__(self, parent: QWidget, tx: TxFlat) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit transaction #{tx.tx_id}")
        self.tx = tx

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        form_wrap = QFrame()
        form = QFormLayout(form_wrap)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate(tx.timestamp.year, tx.timestamp.month, tx.timestamp.day))

        # Description
        self.desc_edit = QLineEdit()
        self.desc_edit.setText(tx.description)

        # Amount (£)
        self.amount_edit = QLineEdit()
        self.amount_edit.setText(str(Decimal(tx.amount_pennies) / Decimal(100)))

        # Accounts
        self.primary_combo = QComboBox()
        self.balancing_combo = QComboBox()

        self.primary_combo.addItem("— Select primary account —", None)
        self.balancing_combo.addItem("— Select balancing account —", None)

        with SessionLocal() as session:
            primaries = get_primary_accounts(session, active_only=True)
            bals = get_balancing_accounts(session, active_only=True)

        for acc in primaries:
            self.primary_combo.addItem(acc.name, acc.id)
        for acc in bals:
            self.balancing_combo.addItem(acc.name, acc.id)

        # Preselect current values
        self._select_combo_value(self.primary_combo, tx.primary_account_id)
        self._select_combo_value(self.balancing_combo, tx.balancing_account_id)

        form.addRow("Date", self.date_edit)
        form.addRow("Description", self.desc_edit)
        form.addRow("Amount", self.amount_edit)
        form.addRow("Primary account", self.primary_combo)
        form.addRow("Balancing account", self.balancing_combo)

        outer.addWidget(form_wrap)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.save_btn = QPushButton("Save changes")
        self.save_btn.setMinimumHeight(34)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._on_save)

        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)

        outer.addLayout(btns)

        self._result: dict | None = None

    def _select_combo_value(self, combo: QComboBox, value: int) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _on_save(self) -> None:
        try:
            payload = self._read()
        except ValueError as e:
            QMessageBox.warning(self, "Validation error", str(e))
            return

        self._result = payload
        self.accept()

    def _read(self) -> dict:
        qd = self.date_edit.date()
        new_date = date(qd.year(), qd.month(), qd.day())

        desc = self.desc_edit.text().strip()
        if not desc:
            raise ValueError("Description is required.")

        amt_raw = self.amount_edit.text().strip()
        if not amt_raw:
            raise ValueError("Amount is required.")
        try:
            amt_dec = Decimal(amt_raw)
        except InvalidOperation:
            raise ValueError("Amount must be a valid number like -12.34 or 1200.00.")
        amount_pennies = _decimal_to_pennies(amt_dec)

        primary_id = self.primary_combo.currentData()
        balancing_id = self.balancing_combo.currentData()
        if not primary_id:
            raise ValueError("Primary account is required.")
        if not balancing_id:
            raise ValueError("Balancing account is required.")
        if int(primary_id) == int(balancing_id):
            raise ValueError("Primary and balancing accounts must be different.")

        return {
            "date": new_date,
            "description": desc,
            "amount_pennies": int(amount_pennies),
            "primary_account_id": int(primary_id),
            "balancing_account_id": int(balancing_id),
        }

    @property
    def result_payload(self) -> dict | None:
        return self._result


class TransactionHistoryPage(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Transaction History")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.edit_btn = QPushButton("Edit selected")
        self.edit_btn.setMinimumHeight(32)
        self.edit_btn.clicked.connect(self.edit_selected)

        self.delete_btn = QPushButton("Delete selected")
        self.delete_btn.setMinimumHeight(32)
        self.delete_btn.clicked.connect(self.delete_selected)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.clicked.connect(self.refresh)

        header.addWidget(self.edit_btn)
        header.addWidget(self.delete_btn)
        header.addWidget(self.refresh_btn)
        outer.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Date", "Description", "Primary", "Balancing", "Amount (£)"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)

        outer.addWidget(self.table, 1)

        self.refresh()

    def refresh(self) -> None:
        tx_rows = self._load_recent_transactions(limit=200)

        self.table.setRowCount(len(tx_rows))
        for r, row in enumerate(tx_rows):
            self._set_item(r, 0, str(row["id"]), align=Qt.AlignRight | Qt.AlignVCenter)
            self._set_item(r, 1, row["date"])
            self._set_item(r, 2, row["description"])
            self._set_item(r, 3, row["primary"])
            self._set_item(r, 4, row["balancing"])
            self._set_item(r, 5, row["amount"], align=Qt.AlignRight | Qt.AlignVCenter)

        self.table.resizeColumnsToContents()

    def edit_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Nothing selected", "Select a transaction row first.")
            return

        tx_id_item = self.table.item(row, 0)
        if not tx_id_item:
            return

        try:
            tx_id = int(tx_id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Could not read selected transaction ID.")
            return

        try:
            tx_flat = self._load_tx_flat(tx_id)
        except Exception as e:
            QMessageBox.critical(self, "Load error", f"Failed to load transaction:\n{e}")
            return

        dlg = EditTransactionDialog(self, tx_flat)
        if dlg.exec() != QDialog.Accepted:
            return

        payload = dlg.result_payload
        if not payload:
            return

        try:
            self._apply_edit(tx_id, payload)
        except Exception as e:
            QMessageBox.critical(self, "Save error", f"Failed to save changes:\n{e}")
            return

        self.refresh()

    def delete_selected(self) -> None:
        # Collect unique transaction IDs from selected rows
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.information(self, "Nothing selected", "Select one or more transaction rows first.")
            return

        tx_ids: list[int] = []
        for r in rows:
            item = self.table.item(r, 0)  # ID column
            if not item:
                continue
            try:
                tx_ids.append(int(item.text()))
            except ValueError:
                continue

        # De-duplicate while preserving order
        seen: set[int] = set()
        tx_ids = [x for x in tx_ids if not (x in seen or seen.add(x))]

        if not tx_ids:
            QMessageBox.warning(self, "Error", "Could not read any transaction IDs from the selection.")
            return

        plural = "s" if len(tx_ids) != 1 else ""
        resp = QMessageBox.question(
            self,
            "Confirm delete",
            f"Delete {len(tx_ids)} transaction{plural}?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        deleted_count = 0
        not_found_count = 0
        first_error: str | None = None

        try:
            with SessionLocal() as session:
                for tx_id in tx_ids:
                    try:
                        ok = delete_transaction(session, tx_id)
                        if ok:
                            deleted_count += 1
                        else:
                            not_found_count += 1
                    except Exception as e:
                        # keep going, but remember the first error
                        if first_error is None:
                            first_error = str(e)
        except Exception as e:
            QMessageBox.critical(self, "Delete error", f"Failed to delete transactions:\n{e}")
            return

        self.refresh()
        self.table.clearSelection()

        msg = f"Deleted: {deleted_count}"
        if not_found_count:
            msg += f"\nNot found: {not_found_count}"
        if first_error:
            msg += f"\n\nFirst error:\n{first_error}"

        QMessageBox.information(self, "Delete complete", msg)

    def _set_item(self, row: int, col: int, text: str, align: Qt.AlignmentFlag | None = None) -> None:
        item = QTableWidgetItem(text)
        if align is not None:
            item.setTextAlignment(int(align))
        self.table.setItem(row, col, item)

    def _load_recent_transactions(self, limit: int = 200) -> list[dict]:
        with SessionLocal() as session:
            txs = session.execute(
                select(Transaction)
                .options(selectinload(Transaction.entries).selectinload(Entry.account))
                .order_by(Transaction.timestamp.desc())
                .limit(limit)
            ).scalars().all()

        out: list[dict] = []
        for tx in txs:
            entries = list(tx.entries or [])
            if len(entries) >= 2:
                p, b = _pick_primary_and_balancing(entries)
                primary_name = getattr(p.account, "name", "") or ""
                balancing_name = getattr(b.account, "name", "") or ""
                amount_pennies = int(getattr(p, "amount_pennies", 0) or 0)
            else:
                primary_name = ""
                balancing_name = ""
                amount_pennies = 0

            out.append(
                {
                    "id": tx.id,
                    "date": tx.timestamp.strftime("%d-%m-%Y"),
                    "description": tx.description,
                    "primary": primary_name,
                    "balancing": balancing_name,
                    "amount": _pennies_to_gbp(amount_pennies),
                }
            )

        return out

    def _load_tx_flat(self, tx_id: int) -> TxFlat:
        with SessionLocal() as session:
            tx = session.execute(
                select(Transaction)
                .where(Transaction.id == tx_id)
                .options(selectinload(Transaction.entries).selectinload(Entry.account))
            ).scalar_one()

        entries = list(tx.entries or [])
        p, b = _pick_primary_and_balancing(entries)

        return TxFlat(
            tx_id=tx.id,
            timestamp=tx.timestamp,
            description=tx.description,
            primary_account_id=int(p.account_id),
            primary_account_name=getattr(p.account, "name", "") or "",
            balancing_account_id=int(b.account_id),
            balancing_account_name=getattr(b.account, "name", "") or "",
            amount_pennies=int(p.amount_pennies),
        )

    def _apply_edit(self, tx_id: int, payload: dict) -> None:
        """
        Updates:
          - Transaction.timestamp (keeps existing time-of-day)
          - Transaction.description
          - Entry(account_id/amount_pennies) for both entries
        """
        with SessionLocal() as session:
            tx = session.execute(
                select(Transaction)
                .where(Transaction.id == tx_id)
                .options(selectinload(Transaction.entries))
            ).scalar_one()

            # timestamp: keep existing time, replace date
            old_ts = tx.timestamp
            new_date: date = payload["date"]
            tx.timestamp = datetime.combine(new_date, old_ts.time())

            tx.description = payload["description"]

            entries = list(tx.entries or [])
            if len(entries) < 2:
                raise ValueError("Transaction does not have two entries to edit.")

            # choose primary/balancing by current account types if possible
            # (same selection logic but without account joined here)
            # simplest safe rule: assume entry[0] is primary and entry[1] is balancing,
            # THEN overwrite both account_ids and amounts to match user selections.
            # This preserves the 2-entry structure regardless of prior ordering.
            amount_pennies = int(payload["amount_pennies"])
            primary_id = int(payload["primary_account_id"])
            balancing_id = int(payload["balancing_account_id"])

            e1, e2 = entries[0], entries[1]
            e1.account_id = primary_id
            e1.amount_pennies = amount_pennies
            e2.account_id = balancing_id
            e2.amount_pennies = -amount_pennies

            session.commit()
