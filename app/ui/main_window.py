# app/ui/main_window.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Account, Transaction
from app.ledger import create_transaction
from app.ui.bulk_entry_window import BulkEntryWindow


class MainWindow(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master

        self.account_names: list[str] = []

        self._build()
        self.refresh_all()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Top: accounts area
        top = ttk.LabelFrame(self, text="Accounts", padding=10)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Primary").grid(row=0, column=0, sticky="w")
        self.primary_var = tk.StringVar()
        self.primary_combo = ttk.Combobox(top, textvariable=self.primary_var, state="readonly")
        self.primary_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(top, text="Balancing").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.balance_var = tk.StringVar()
        self.balance_combo = ttk.Combobox(top, textvariable=self.balance_var, state="readonly")
        self.balance_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))

                # --- Add transaction inputs (minimal)
        form = ttk.LabelFrame(self, text="Add transaction", padding=10)
        form.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Description").grid(row=0, column=0, sticky="w")
        self.desc_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.desc_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Label(form, text="Amount (£)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.amount_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.amount_var).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0)
        )

        ttk.Button(form, text="Save", command=self._save_transaction).grid(
            row=0, column=2, rowspan=2, padx=(10, 0)
        )

        ttk.Button(top, text="Refresh", command=self.refresh_all).grid(row=0, column=2, rowspan=2, padx=(10, 0))
        ttk.Button(
            top,
            text="Bulk entry",
            command=lambda: BulkEntryWindow(self.master),
        ).grid(row=0, column=3, rowspan=2, padx=(10, 0))

        # Bottom: transactions list
        bottom = ttk.LabelFrame(self, text="Recent transactions", padding=10)
        bottom.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(bottom, columns=("id", "timestamp", "description"), show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("description", text="Description")
        self.tree.column("id", width=60, anchor="e")
        self.tree.column("timestamp", width=160, anchor="w")
        self.tree.column("description", width=520, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(bottom, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")

    def refresh_all(self) -> None:
        self._load_accounts()
        self._load_transactions()

    def _load_accounts(self) -> None:
        with SessionLocal() as session:
            accounts = session.execute(select(Account).order_by(Account.name)).scalars().all()

        self.account_names = [a.name for a in accounts]
        self.primary_combo["values"] = self.account_names
        self.balance_combo["values"] = self.account_names

        if self.account_names:
            if not self.primary_var.get():
                self.primary_var.set(self.account_names[0])
            if not self.balance_var.get():
                self.balance_var.set(self.account_names[0] if len(self.account_names) == 1 else self.account_names[1])

    def _load_transactions(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        with SessionLocal() as session:
            txs = session.execute(
                select(Transaction).order_by(Transaction.timestamp.desc()).limit(50)
            ).scalars().all()

        for tx in txs:
            ts = tx.timestamp.strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", values=(tx.id, ts, tx.description))
    
    def _save_transaction(self) -> None:
        from sqlalchemy import select
        from tkinter import messagebox

        try:
            # pull raw values from UI
            description = self.desc_var.get().strip()
            amount = self.amount_var.get().strip()
            primary_name = self.primary_var.get()
            balancing_name = self.balance_var.get()

            if not description or not amount:
                raise ValueError("Description and amount are required")

            amount_pennies = int(float(amount) * 100)

            with SessionLocal() as session:
                primary_id = session.execute(
                    select(Account.id).where(Account.name == primary_name)
                ).scalar_one()

                balancing_id = session.execute(
                    select(Account.id).where(Account.name == balancing_name)
                ).scalar_one()

                create_transaction(
                    session,
                    timestamp=datetime.now(),
                    description=description,
                    primary_account_id=primary_id,
                    amount_pennies=amount_pennies,
                    balancing_account_id=balancing_id,
                )

            # clear + refresh
            self.desc_var.set("")
            self.amount_var.set("")
            self._load_transactions()

        except Exception as e:
            messagebox.showerror("Save failed", str(e))

