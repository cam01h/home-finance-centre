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
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui_qt.accounts_manager import AddAccountDialog
from app.importers.statement_csv import extract_transactions_from_csv, IGNORE
from app.accounts import get_primary_accounts, get_balancing_accounts
from app.db import SessionLocal
from app.ledger import create_transaction


REQUIRED_KEYS = ("date", "amount")
OPTIONAL_KEYS = ("merchant", "description")
ADD_NEW_ACCOUNT = "Add new account…"
ADD_NEW_ACCOUNT_DATA = "__add_new__"

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

        # Primary account (applies to all imported rows)
        self.primary_combo = QComboBox()
        self.primary_combo.addItem("— Select primary account —", None)

        with SessionLocal() as session:
            primaries = get_primary_accounts(session, active_only=True)

        for acc in primaries:
            self.primary_combo.addItem(acc.name, int(acc.id))

        form.addRow("Primary account", self.primary_combo)

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

        primary_id = self.primary_combo.currentData()
        if not primary_id:
            QMessageBox.warning(self, "Missing", "Primary account is required.")
            return

        self._mapping = mapping
        self._primary_id = int(primary_id)
        self.accept()

    @property
    def mapping(self) -> dict[str, str] | None:
        return self._mapping
    
    @property
    def primary_id(self) -> int | None:
        return getattr(self, "_primary_id", None)


class ImportAccountsDialog(QDialog):
    def __init__(self, parent: QWidget, default_primary_id: int | None = None) -> None:
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

        if default_primary_id is not None:
            idx = self.primary_combo.findData(int(default_primary_id))
            if idx >= 0:
                self.primary_combo.setCurrentIndex(idx)


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
        self.primary_account_id: int | None = None
        self._balancing_combos: list[QComboBox] = []

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

        self.pick_btn = QPushButton("Choose CSV…")
        self.pick_btn.setMinimumHeight(32)
        self.pick_btn.clicked.connect(self.choose_csv)

        self.pick_pdf_btn = QPushButton("Choose PDF…")
        self.pick_pdf_btn.setMinimumHeight(32)
        self.pick_pdf_btn.clicked.connect(self.choose_pdf)

        self.commit_btn = QPushButton("Commit to DB")
        self.commit_btn.setMinimumHeight(32)
        self.commit_btn.setEnabled(False)
        self.commit_btn.clicked.connect(self.commit_to_db)

        header.addWidget(self.pick_btn)
        header.addWidget(self.pick_pdf_btn)
        header.addWidget(self.commit_btn)
        outer.addLayout(header)

        self.file_label = QLabel("No file selected.")
        self.file_label.setObjectName("MutedText")
        outer.addWidget(self.file_label)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Merchant", "Description", "Amount", "Balancing"]
        )
        self.table.setAlternatingRowColors(True)

        # Enable editing – this is now a staging grid
        self.table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked
        )

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        outer.addWidget(self.table, 1)

    def _load_balancing_accounts(self) -> list[tuple[int, str]]:
        """Return [(id, name), ...] for active balancing accounts."""
        with SessionLocal() as session:
            bals = get_balancing_accounts(session, active_only=True)
        return [(int(a.id), str(a.name)) for a in bals]

    def _make_balancing_combo(self, current_name: str = "") -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)  # lets you type to search
        combo.lineEdit().setPlaceholderText("Select…")  # needs QLineEdit import

        accounts = self._load_balancing_accounts()

        # Add accounts
        current_index = -1
        for i, (acc_id, name) in enumerate(accounts):
            combo.addItem(name, acc_id)
            if current_name and name.strip().lower() == current_name.strip().lower():
                current_index = i

        # Divider-ish: just add the special option at the bottom
        combo.addItem(ADD_NEW_ACCOUNT, ADD_NEW_ACCOUNT_DATA)

        if current_index >= 0:
            combo.setCurrentIndex(current_index)
        else:
            combo.setCurrentIndex(-1)

        combo.currentIndexChanged.connect(lambda _=None, c=combo: self._on_balancing_changed(c))
        return combo

    def _on_balancing_changed(self, combo: QComboBox) -> None:
        if combo.currentData() != ADD_NEW_ACCOUNT_DATA:
            return

        dlg = AddAccountDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.payload:
            # user cancelled: revert selection to blank
            combo.setCurrentIndex(-1)
            return

        payload = dlg.payload

        # Only allow balancing types here
        if payload.acc_type in ("asset", "liability"):
            QMessageBox.warning(self, "Invalid", "Balancing accounts must be income, expense, or adjustment.")
            combo.setCurrentIndex(-1)
            return

        try:
            with SessionLocal() as session:
                # AccountsManager uses add_balancing_account under the hood.
                # We can call the same helper directly here for consistency.
                from app.accounts import add_balancing_account
                new_acc = add_balancing_account(session, payload.name, payload.acc_type)
                new_id = int(new_acc.id)
                new_name = str(new_acc.name)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add account:\n{e}")
            combo.setCurrentIndex(-1)
            return

        # Refresh every balancing combo so the new account is available everywhere
        accounts = self._load_balancing_accounts()

        for c in self._balancing_combos:
            current = c.currentData()

            c.blockSignals(True)
            c.clear()

            for acc_id, name in accounts:
                c.addItem(name, acc_id)

            c.addItem(ADD_NEW_ACCOUNT, ADD_NEW_ACCOUNT_DATA)

            # Preserve previous selection where possible
            if current == ADD_NEW_ACCOUNT_DATA or current is None:
                c.setCurrentIndex(-1)
            else:
                idx = c.findData(current)
                c.setCurrentIndex(idx if idx >= 0 else -1)

            c.blockSignals(False)

        # Finally, select the newly created account in the combo that triggered the add
        idx_new = combo.findData(new_id)
        if idx_new >= 0:
            combo.setCurrentIndex(idx_new)

    def _reset_import_state(self) -> None:
        """Clear current loaded rows + preview and disable commit."""
        self.rows = []
        self.primary_account_id = None
        self.commit_btn.setEnabled(False)
        self.table.setRowCount(0)
        self._balancing_combos = []

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
        if dlg.exec() != QDialog.Accepted or not dlg.mapping or not dlg.primary_id:
            # user cancelled mapping or missing required selections
            return

        self.primary_account_id = dlg.primary_id

        try:
            rows = extract_transactions_from_csv(path, dlg.mapping)
        except Exception as e:
            QMessageBox.critical(self, "Import error", f"Failed to parse CSV:\n{e}")
            # keep state reset
            return

        self._load_preview(rows)

        self.rows = rows
        self.commit_btn.setEnabled(len(self.rows) > 0)

    def choose_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose statement PDF",
            "",
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            return

        # New file selection => clear any previous loaded rows/preview immediately
        self._reset_import_state()
        self.file_label.setText(str(Path(path)))

        # (Step 1 only) We'll wire parsing + staging load next.


    def _load_preview(self, rows: list[dict]) -> None:
        self.table.setRowCount(min(len(rows), 500))  # cap preview
        self._balancing_combos = []

        for r, row in enumerate(rows[:500]):
            self._set_item(r, 0, str(row.get("date", "")))
            self._set_item(r, 1, str(row.get("merchant", "")))
            self._set_item(r, 2, str(row.get("description", "")))
            self._set_item(
                r, 3, str(row.get("amount", "")),
                align=Qt.AlignRight | Qt.AlignVCenter
            )
            combo = self._make_balancing_combo(str(row.get("balancing", "")))
            self._balancing_combos.append(combo)
            self.table.setCellWidget(r, 4, combo)



        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(4, 220)

    def _set_item(self, row: int, col: int, text: str, align: Qt.AlignmentFlag | None = None) -> None:
        item = QTableWidgetItem(text)
        if align is not None:
            item.setTextAlignment(int(align))
        self.table.setItem(row, col, item)

    def commit_to_db(self) -> None:
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "Nothing to commit", "Load a CSV first.")
            return

        if not self.primary_account_id:
            QMessageBox.warning(
                self,
                "Missing primary",
                "Primary account is not set. Re-import the CSV and choose a primary account in the mapping dialog.",
            )
            return

        resp = QMessageBox.question(
            self,
            "Confirm commit",
            "Are you sure you want to commit these staged transactions to the database?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        primary_id = int(self.primary_account_id)

        ok, skipped = 0, 0
        first_error = None

        def cell_text(r: int, c: int) -> str:
            item = self.table.item(r, c)
            return "" if item is None else str(item.text()).strip()

        try:
            with SessionLocal() as session:
                for r in range(self.table.rowCount()):
                    try:
                        date_s = cell_text(r, 0)
                        merchant = cell_text(r, 1)
                        desc_s = cell_text(r, 2)
                        amount_s = cell_text(r, 3)

                        # Balancing is a dropdown widget in column 4
                        w = self.table.cellWidget(r, 4)
                        if not isinstance(w, QComboBox):
                            skipped += 1
                            continue

                        balancing_id = w.currentData()
                        if not balancing_id or balancing_id == ADD_NEW_ACCOUNT_DATA:
                            skipped += 1
                            continue

                        ts = self._parse_date_to_timestamp(date_s)
                        desc = self._build_description(merchant, desc_s)
                        amount_pennies = self._parse_amount_to_pennies(amount_s)

                        if not desc or amount_pennies is None or ts is None:
                            skipped += 1
                            continue

                        create_transaction(
                            session,
                            timestamp=ts,
                            description=desc,
                            primary_account_id=primary_id,
                            amount_pennies=amount_pennies,
                            balancing_account_id=int(balancing_id),
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


