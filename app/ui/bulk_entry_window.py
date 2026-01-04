# app/ui/bulk_entry_window.py
from __future__ import annotations
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Account
from app.ledger import create_transaction


class BulkEntryWindow(tk.Toplevel):
    """
    Staging / bulk transaction entry window.
    This step is just the shell + table columns (no saving yet).
    """

    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.title("Bulk transaction entry")
        self.geometry("1100x600")

        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        with SessionLocal() as session:
            self.account_names = session.execute(
                select(Account.name).order_by(Account.name)
            ).scalars().all()

        ttk.Label(
            container,
            text="Staging table (manual entry + imports later)",
        ).pack(anchor="w", pady=(0, 8))

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(0, 8))

        ttk.Button(actions, text="Add row", command=self._add_row).pack(side="left")
        ttk.Button(actions, text="Commit ready rows", command=self._commit_ready_rows).pack(side="left", padx=(8, 0))
        
        columns = ("date", "merchant", "description", "amount", "primary", "balancing", "status")

        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=18)
        self.tree.pack(fill="both", expand=True)

        self.tree.heading("date", text="Date")
        self.tree.heading("merchant", text="Merchant")
        self.tree.heading("description", text="Description")
        self.tree.heading("amount", text="Amount (£)")
        self.tree.heading("primary", text="Primary account")
        self.tree.heading("balancing", text="Balancing account")
        self.tree.heading("status", text="Status")

        # Reasonable starter widths
        self.tree.column("date", width=120, anchor="w")
        self.tree.column("merchant", width=180, anchor="w")
        self.tree.column("description", width=320, anchor="w")
        self.tree.column("amount", width=110, anchor="e")
        self.tree.column("primary", width=160, anchor="w")
        self.tree.column("balancing", width=160, anchor="w")
        self.tree.column("status", width=90, anchor="w")

        # Dummy row so you can see it’s alive (we’ll remove this later)
        self.tree.insert("", "end", values=("2026-01-04", "TESCO", "Groceries", "-12.34", "Current Account", "", "Draft"))
        self.tree.bind("<Double-1>", self._begin_edit)
        self._edit_entry = None
        self._edit_item = None
        self._edit_col = None


    def _add_row(self) -> None:
        """Add an empty row to the staging table."""
        self.tree.insert("", "end", values=("", "", "", "", "", "", "Draft"))
        self._validate_item(self.tree.get_children()[-1])


    def _begin_edit(self, event) -> None:
        # Identify row + column
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)  # e.g. "#1", "#2", ...

        if not item or col == "#0":
            return

        # Get cell bounding box
        bbox = self.tree.bbox(item, col)
        if not bbox:
            return
        x, y, w, h = bbox

        # Column index (0-based)
        col_index = int(col.replace("#", "")) - 1

        # Current value
        values = list(self.tree.item(item, "values"))
        current = values[col_index] if col_index < len(values) else ""

        # Clean up any existing editor
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except Exception:
                pass

        # Create overlay editor (dropdown for account columns, Entry otherwise)
        self._edit_item = item
        self._edit_col = col_index

        is_account_col = col_index in (4, 5)  # primary, balancing

        if is_account_col:
            self._edit_entry = ttk.Combobox(
                self.tree,
                values=self.account_names,
                state="readonly",
            )
            # set current if it matches
            if current in self.account_names:
                self._edit_entry.set(current)
        else:
            self._edit_entry = tk.Entry(self.tree)
            self._edit_entry.insert(0, current)
            self._edit_entry.select_range(0, tk.END)

        self._edit_entry.focus_set()
        self._edit_entry.place(x=x, y=y, width=w, height=h)

        self._edit_entry.bind("<Return>", self._commit_edit)
        self._edit_entry.bind("<Escape>", self._cancel_edit)
        self._edit_entry.bind("<FocusOut>", self._commit_edit)

        if is_account_col:
            self._edit_entry.bind("<<ComboboxSelected>>", self._commit_edit)


    def _commit_edit(self, event=None) -> None:
        if self._edit_entry is None or self._edit_item is None or self._edit_col is None:
            return

        new_value = self._edit_entry.get()

        values = list(self.tree.item(self._edit_item, "values"))
        # Ensure list is long enough
        while len(values) <= self._edit_col:
            values.append("")

        values[self._edit_col] = new_value
        self.tree.item(self._edit_item, values=values)
        self._validate_item(self._edit_item)

        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_item = None
        self._edit_col = None

    def _cancel_edit(self, event=None) -> None:
        if self._edit_entry is not None:
            self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_item = None
        self._edit_col = None

    def _validate_item(self, item_id: str) -> None:
        """
        Validate a single row and write status into the Status column.
        Columns: 0 date, 1 merchant, 2 description, 3 amount, 4 primary, 5 balancing, 6 status
        """
        values = list(self.tree.item(item_id, "values"))
        while len(values) < 7:
            values.append("")

        date_s, merchant, desc, amount_s, primary, balancing, _status = values

        errors = []

        # Required fields
        if not date_s.strip():
            errors.append("date")
        if not merchant.strip():
            errors.append("merchant")
        if not desc.strip():
            errors.append("description")
        if not amount_s.strip():
            errors.append("amount")
        if not primary.strip():
            errors.append("primary")
        if not balancing.strip():
            errors.append("balancing")

        # Date format (simple)
        if date_s.strip():
            try:
                datetime.strptime(date_s.strip(), "%Y-%m-%d")
            except ValueError:
                errors.append("date format YYYY-MM-DD")

        # Amount format (simple numeric check)
        if amount_s.strip():
            try:
                float(amount_s.strip().replace("£", ""))
            except ValueError:
                errors.append("amount format")

        # Account logic
        if primary.strip() and balancing.strip() and primary.strip() == balancing.strip():
            errors.append("primary != balancing")

        if errors:
            values[6] = "Error: " + ", ".join(errors)
        else:
            values[6] = "Ready"

        self.tree.item(item_id, values=values)

    def _validate_all(self) -> None:
        for item in self.tree.get_children():
            self._validate_item(item)

    def _commit_ready_rows(self) -> None:
        """
        Convert 'Ready' staging rows into real ledger transactions.
        Leaves Error rows untouched.
        """
        items = list(self.tree.get_children())
        if not items:
            messagebox.showinfo("Nothing to do", "No rows in the staging table.")
            return

        committed = 0
        skipped = 0
        errors = 0

        # One DB session for the whole batch (faster + cleaner)
        with SessionLocal() as session:
            for item_id in items:
                values = list(self.tree.item(item_id, "values"))
                while len(values) < 7:
                    values.append("")

                date_s, merchant, desc, amount_s, primary, balancing, status = values

                if status != "Ready":
                    skipped += 1
                    continue

                try:
                    # Parse date (YYYY-MM-DD)
                    tx_date = datetime.strptime(date_s.strip(), "%Y-%m-%d")

                    # Amount -> pennies (simple; we can harden later)
                    amt = float(amount_s.strip().replace("£", ""))
                    amount_pennies = int(round(amt * 100))

                    # Build description (merchant + description)
                    description = f"{merchant.strip()} - {desc.strip()}".strip(" -")

                    # Resolve account ids
                    primary_id = session.execute(
                        select(Account.id).where(Account.name == primary.strip())
                    ).scalar_one()

                    balancing_id = session.execute(
                        select(Account.id).where(Account.name == balancing.strip())
                    ).scalar_one()

                    # Write to ledger (double-entry enforced)
                    create_transaction(
                        session,
                        timestamp=tx_date,
                        description=description,
                        primary_account_id=primary_id,
                        amount_pennies=amount_pennies,
                        balancing_account_id=balancing_id,
                    )

                    # Mark as committed in staging (don’t delete yet)
                    values[6] = "Committed"
                    self.tree.item(item_id, values=values)
                    committed += 1

                except Exception as e:
                    # Leave row in table, mark as error
                    values[6] = f"Error: {e}"
                    self.tree.item(item_id, values=values)
                    errors += 1

        messagebox.showinfo(
            "Commit complete",
            f"Committed: {committed}\nSkipped: {skipped}\nErrors: {errors}",
        )
