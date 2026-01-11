# app/ui_qt/bulk_import.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.importers.statement_csv import extract_transactions_from_csv, IGNORE
from app.accounts import get_primary_accounts, get_balancing_accounts
from app.db import SessionLocal
from app.ledger import create_transaction


REQUIRED_KEYS = ("date", "amount")
OPTIONAL_KEYS = ("merchant", "description")  # keep it simple for now


class CsvMappingDialog(QDialog):
    def __init__(self, parent: QWidget, columns: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Map CSV columns")
        self._mapping: dict[str, str] | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self._boxes: dict[str, QComboBox] = {}

        def make_box(allow_ignore: bool) -> QComboBox:
            box = QComboBox()
            if allow_ignore:
                box.addItem(IGNORE, IGNORE)
            for c in columns:
                box.addItem(c, c)
            return box

        # Required
        for key in REQUIRED_KEYS:
            box = make_box(False)
            self._boxes[key] = box
            form.addRow(key.capitalize(), box)

        # Optional
        for key in OPTIONAL_KEYS:
            box = make_box(True)
            self._boxes[key] = box
            form.addRow(key.capitalize(), box)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)


    def _on_ok(self) -> None:
        mapping: dict[str, str] = {}
        for key in REQUIRED_KEYS:
            val = self._boxes[key].currentData()
            if not val or val == IGNORE:
                QMessageBox.warning(self, "Mapping error", f"{key} is required.")
                return
            mapping[key] = str(val)

        for key in OPTIONAL_KEYS:
            mapping[key] = str(self._boxes[key].currentData())

        self._mapping = mapping
        self.accept()

    @property
    def mapping(self) -> dict[str, str] | None:
        return self._mapping

class ImportAccountsDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import settings")
        self._result: dict | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        outer.addLayout(form)

        self.primary_combo = QComboBox()
        self.primary_combo.addItem("— Select primary account —", None)

        self.balancing_combo = QComboBox()
        self.balancing_combo.addItem("— Select default balancing account —", None)

        with SessionLocal() as session:
            primaries = get_primary_accounts(session, active_only=True)
            bals = get_balancing_accounts(session, active_only=True)

        for acc in primaries:
            self.primary_combo.addItem(acc.name, acc.id)

        for acc in bals:
            self.balancing_combo.addItem(acc.name, acc.id)

        form.addRow("Primary account", self.primary_combo)
        form.addRow("Default balancing", self.balancing_combo)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        ok = QPushButton("Commit")
        ok.setDefault(True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)

    def _on_ok(self) -> None:
        p = self.primary_combo.currentData()
        b = self.balancing_combo.currentData()
        if not p:
            QMessageBox.warning(self, "Missing", "Primary account is required.")
            return
        if not b:
            QMessageBox.warning(self, "Missing", "Default balancing account is required.")
            return
        if int(p) == int(b):
            QMessageBox.warning(self, "Invalid", "Primary and balancing must be different.")
            return

        self._result = {"primary_id": int(p), "balancing_id": int(b)}
        self.accept()

    @property
    def result(self) -> dict | None:
        return self._result


class BulkImportPage(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        
        self.rows: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Bulk Import")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.pick_btn = QPushButton("Choose CSV…")
        self.pick_btn.setMinimumHeight(32)
        self.pick_btn.clicked.connect(self.choose_csv)

        self.commit_btn = QPushButton("Commit to DB")
        self.commit_btn.setMinimumHeight(32)
        self.commit_btn.setEnabled(False)
        self.commit_btn.clicked.connect(self.commit_to_db)

        header.addWidget(self.pick_btn)
        header.addWidget(self.commit_btn)
        outer.addLayout(header)

        self.file_label = QLabel("No file selected.")
        self.file_label.setObjectName("MutedText")
        outer.addWidget(self.file_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date", "Merchant", "Description", "Amount"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        outer.addWidget(self.table, 1)

    def _reset_import_state(self) -> None:
        """Clear current loaded rows + preview and disable commit."""
        self.rows = []
        self.commit_btn.setEnabled(False)
        self.table.setRowCount(0)


    def choose_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose statement CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return

        # New file selection => clear any previous loaded rows/preview immediately
        self._reset_import_state()
        self.file_label.setText(str(Path(path)))

        try:
            # Read only headers to build the mapping UI
            df_head = pd.read_csv(path, nrows=0)
            columns = [str(c) for c in df_head.columns.tolist()]
        except Exception as e:
            QMessageBox.critical(self, "Import error", f"Failed to read CSV headers:\n{e}")
            # keep state reset
            return

        dlg = CsvMappingDialog(self, columns)
        if dlg.exec() != QDialog.Accepted or not dlg.mapping:
            # user cancelled mapping => keep state reset (prevents stale commit)
            return

        try:
            rows = extract_transactions_from_csv(path, dlg.mapping)
        except Exception as e:
            QMessageBox.critical(self, "Import error", f"Failed to parse CSV:\n{e}")
            # keep state reset
            return

        self._load_preview(rows)

        self.rows = rows
        self.commit_btn.setEnabled(len(self.rows) > 0)

    def _load_preview(self, rows: list[dict]) -> None:
        self.table.setRowCount(min(len(rows), 500))  # cap preview

        for r, row in enumerate(rows[:500]):
            self._set_item(r, 0, str(row.get("date", "")))
            self._set_item(r, 1, str(row.get("merchant", "")))
            self._set_item(r, 2, str(row.get("description", "")))
            self._set_item(r, 3, str(row.get("amount", "")), align=Qt.AlignRight | Qt.AlignVCenter)

        self.table.resizeColumnsToContents()

    def _set_item(self, row: int, col: int, text: str, align: Qt.AlignmentFlag | None = None) -> None:
        item = QTableWidgetItem(text)
        if align is not None:
            item.setTextAlignment(int(align))
        self.table.setItem(row, col, item)

    def commit_to_db(self) -> None:
        if not self.rows:
            QMessageBox.information(self, "Nothing to commit", "Load a CSV first.")
            return
        

        dlg = ImportAccountsDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.result:
            return

        primary_id = dlg.result["primary_id"]
        balancing_id = dlg.result["balancing_id"]

        ok, skipped = 0, 0
        first_error = None

        try:
            with SessionLocal() as session:
                for row in self.rows:
                    try:
                        ts = self._parse_date_to_timestamp(row.get("date", ""))
                        desc = self._build_description(row.get("merchant", ""), row.get("description", ""))
                        amount_pennies = self._parse_amount_to_pennies(row.get("amount", ""))

                        if not desc or amount_pennies is None or ts is None:
                            skipped += 1
                            continue

                        create_transaction(
                            session,
                            timestamp=ts,
                            description=desc,
                            primary_account_id=primary_id,
                            amount_pennies=amount_pennies,
                            balancing_account_id=balancing_id,
                        )
                        ok += 1

                    except Exception as e:
                        skipped += 1
                        if first_error is None:
                            first_error = str(e)

        except Exception as e:
            QMessageBox.critical(self, "DB error", f"Commit failed:\n{e}")
            return

        msg = f"Committed: {ok}\nSkipped: {skipped}"
        if first_error:
            msg += f"\n\nFirst skipped error:\n{first_error}"
        QMessageBox.information(self, "Import complete", msg)

        # Prevent accidental double-commit duplicates
        if ok > 0:
            self._reset_import_state()
            self.file_label.setText("Committed.")



    def _build_description(self, merchant: str, description: str) -> str:
        merchant = (merchant or "").strip()
        description = (description or "").strip()
        if merchant and description:
            return f"{merchant} - {description}"
        return merchant or description


    def _parse_amount_to_pennies(self, amount_raw: str) -> int | None:
        s = (amount_raw or "").strip()
        if not s:
            return None

        # Handle negatives like "(12.34)"
        negative = False
        if s.startswith("(") and s.endswith(")"):
            negative = True
            s = s[1:-1].strip()

        # Remove currency symbols/letters and whitespace, keep digits and separators
        # Example inputs handled:
        # "£1,234.56"  -> "1,234.56"
        # "USD 12.34"  -> "12.34"
        # "  -12.34 "  -> "-12.34"
        s = s.replace(" ", "")
        s = re.sub(r"[^\d,.\-+]", "", s)

        if not s:
            return None

        # If it includes both '.' and ',', guess which is decimal separator.
        # - UK/US: "1,234.56" => ',' thousands, '.' decimal
        # - EU:    "1.234,56" => '.' thousands, ',' decimal
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # assume EU format: remove thousands '.', swap decimal ',' -> '.'
                s = s.replace(".", "")
                s = s.replace(",", ".")
            else:
                # assume UK/US format: remove thousands ','
                s = s.replace(",", "")
        else:
            # Only commas => could be thousands or decimal, but common for statements is thousands separators
            # so we remove commas.
            s = s.replace(",", "")

        # Apply parentheses negative last (so "( -12.34 )" still works sensibly)
        if negative and not s.startswith("-"):
            s = "-" + s

        try:
            dec = Decimal(s)
        except (InvalidOperation, ValueError):
            return None

        return int((dec * 100).to_integral_value())

    def _parse_date_to_timestamp(self, date_raw: str) -> datetime | None:
        s = (date_raw or "").strip()
        if not s:
            return None

        # Common formats (date-only + date-time)
        fmts = (
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        )

        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                # If it was a date-only format, normalise to midday
                if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and len(s) <= 10:
                    return dt.replace(hour=12)
                return dt
            except ValueError:
                continue

        # Last resort: try ISO parsing (handles "YYYY-MM-DDTHH:MM:SS.sss" etc)
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            # If timezone-aware, drop tzinfo to keep DB consistent (naive)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            return None


