# app/ui_qt/transaction_history.py
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import Transaction, Entry


def _pennies_to_gbp(amount_pennies: int) -> str:
    return f"{amount_pennies / 100:,.2f}"


class TransactionHistoryPage(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # Header row inside the page (ribbon can stay global later)
        header = QHBoxLayout()
        title = QLabel("Transaction History")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)

        outer.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Date", "Description", "Primary", "Balancing", "Amount (£)"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        outer.addWidget(self.table, 1)

        # First load
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
        self.table.horizontalHeader().setStretchLastSection(False)

    def _set_item(self, row: int, col: int, text: str, align: Qt.AlignmentFlag | None = None) -> None:
        item = QTableWidgetItem(text)
        if align is not None:
            item.setTextAlignment(int(align))
        self.table.setItem(row, col, item)

    def _load_recent_transactions(self, limit: int = 200) -> list[dict]:
        """
        Loads recent transactions and flattens the double-entry rows into:
        (primary_account, balancing_account, amount)
        """
        with SessionLocal() as session:
            txs = session.execute(
                select(Transaction)
                .options(
                    selectinload(Transaction.entries).selectinload(Entry.account)
                )
                .order_by(Transaction.timestamp.desc())
                .limit(limit)
            ).scalars().all()

        out: list[dict] = []

        for tx in txs:
            # Default values (in case something odd happens)
            primary_name = ""
            balancing_name = ""
            amount_pennies = 0

            # We expect 2 entries per transaction
            entries = list(tx.entries or [])
            if len(entries) >= 2:
                # Your ledger logic sets:
                # primary entry = amount_pennies as passed in
                # balancing entry = -amount_pennies
                # So: choose primary as the entry whose account is asset/liability if available,
                # otherwise fallback to "the one that isn't the other".
                primary_entry = None

                for e in entries:
                    if getattr(e.account, "type", None) in ("asset", "liability"):
                        primary_entry = e
                        break

                if primary_entry is None:
                    # Fallback: pick the first entry as primary
                    primary_entry = entries[0]

                # balancing is "the other one"
                balancing_entry = next((e for e in entries if e is not primary_entry), entries[1])

                primary_name = getattr(primary_entry.account, "name", "") or ""
                balancing_name = getattr(balancing_entry.account, "name", "") or ""
                amount_pennies = int(getattr(primary_entry, "amount_pennies", 0) or 0)

            ts: datetime = tx.timestamp
            date_s = ts.strftime("%d-%m-%Y")

            out.append(
                {
                    "id": tx.id,
                    "date": date_s,
                    "description": tx.description,
                    "primary": primary_name,
                    "balancing": balancing_name,
                    "amount": _pennies_to_gbp(amount_pennies),
                }
            )

        return out
