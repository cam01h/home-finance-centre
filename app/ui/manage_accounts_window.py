import tkinter as tk
from tkinter import ttk
from app.db import SessionLocal
from app.models import Account
import uuid
from tkinter import messagebox
from sqlalchemy.exc import IntegrityError

class ManageAccountsWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Manage accounts")
        self.geometry("900x500")

        # --- Ribbon ---
        ribbon = ttk.Frame(self)
        ribbon.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(ribbon, text="Show:").pack(side="left")

        self.filter_var = tk.StringVar(value="Active")
        self.filter_cb = ttk.Combobox(
            ribbon,
            textvariable=self.filter_var,
            values=["Active", "All", "Closed"],
            state="readonly",
            width=10,
        )
        self.filter_cb.pack(side="left", padx=(6, 12))
        self.filter_cb.bind("<<ComboboxSelected>>", lambda e: self._reload())

        # Placeholder buttons (we’ll wire these next)
        ttk.Button(ribbon, text="Add", command=self._add_row).pack(side="left", padx=(0, 6))
        ttk.Button(ribbon, text="Remove", command=self._close_selected).pack(side="left", padx=(0, 6))
        ttk.Button(ribbon, text="Save", command=self._save).pack(side="left")

        # --- Table ---
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        cols = ("name", "type", "active")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        self.tree.bind("<Double-1>", self._begin_edit)
        self.tree.heading("name", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("active", text="Active")

        self.tree.column("name", width=420, anchor="w")
        self.tree.column("type", width=180, anchor="w")
        self.tree.column("active", width=80, anchor="center")

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self._reload()

    def _reload(self) -> None:
        # Clear existing rows
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        show = self.filter_var.get()

        with SessionLocal() as session:
            q = session.query(Account)

            if show == "Active":
                q = q.filter(Account.is_active.is_(True))
            elif show == "Closed":
                q = q.filter(Account.is_active.is_(False))
            # "All" => no filter

            q = q.order_by(Account.is_active.desc(), Account.type.asc(), Account.name.asc())

            for acc in q.all():
                self.tree.insert(
                    "",
                    "end",
                    iid=str(acc.id),
                    values=(acc.name, acc.type, "Yes" if acc.is_active else "No"),
                )


    def _add_row(self) -> None:
        self.tree.insert(
            "",
            "end",
            iid=f"new:{uuid.uuid4()}",
            values=("NEW_ACCOUNT", "expense", "Yes"),
        )


    def _begin_edit(self, event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)

        if not row_id or not col_id:
            return

        col_index = int(col_id[1:]) - 1
        values = list(self.tree.item(row_id, "values"))

        x, y, w, h = self.tree.bbox(row_id, col_id)

        # Name (text)
        if col_index == 0:
            entry = ttk.Entry(self.tree)
            entry.insert(0, values[col_index])
            entry.place(x=x, y=y, width=w, height=h)
            entry.focus()

            entry.bind(
                "<FocusOut>",
                lambda e: self._commit_edit(row_id, col_index, entry.get(), entry),
            )
            entry.bind(
                "<Return>",
                lambda e: self._commit_edit(row_id, col_index, entry.get(), entry),
            )

        # Type / Active (dropdowns)
        else:
            if col_index == 1:
                opts = ["asset", "liability", "income", "expense", "adjustment"]
            else:
                opts = ["Yes", "No"]

            var = tk.StringVar(value=values[col_index])
            cb = ttk.Combobox(
                self.tree,
                textvariable=var,
                values=opts,
                state="readonly",
            )
            cb.place(x=x, y=y, width=w, height=h)
            cb.focus()

            cb.bind(
                "<<ComboboxSelected>>",
                lambda e: self._commit_edit(row_id, col_index, var.get(), cb),
            )
            cb.bind(
                "<FocusOut>",
                lambda e: self._commit_edit(row_id, col_index, var.get(), cb),
            )


    def _commit_edit(self, row_id, col_index, new_value, widget) -> None:
        values = list(self.tree.item(row_id, "values"))
        values[col_index] = new_value
        self.tree.item(row_id, values=values)
        widget.destroy()

    def _close_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return

        row_id = selected[0]
        values = list(self.tree.item(row_id, "values"))
        # values: (name, type, active)
        if len(values) >= 3:
            values[2] = "No"
            self.tree.item(row_id, values=values)
    def _save(self) -> None:
        # Read all rows from the UI
        rows = []
        for iid in self.tree.get_children():
            name, acc_type, active_s = self.tree.item(iid, "values")
            rows.append((iid, str(name).strip(), str(acc_type).strip(), str(active_s).strip()))

        # Minimal sanity: skip totally blank names
        rows = [r for r in rows if r[1]]

        with SessionLocal() as session:
            try:
                for iid, name, acc_type, active_s in rows:
                    is_active = (active_s.lower() in ("yes", "true", "1", "active"))

                    if str(iid).startswith("new:"):
                        # Create
                        session.add(Account(name=name, type=acc_type, is_active=is_active))
                    else:
                        # Update existing by id
                        acc = session.get(Account, int(iid))
                        if not acc:
                            continue
                        acc.name = name
                        acc.type = acc_type
                        acc.is_active = is_active

                session.commit()

            except IntegrityError as e:
                session.rollback()
                messagebox.showerror(
                    "Save failed",
                    "Database rejected the changes (likely duplicate account name or invalid type).",
                )
                return
            except Exception as e:
                session.rollback()
                messagebox.showerror("Save failed", f"Unexpected error:\n{e}")
                return

        # Refresh view after successful save
        self._reload()

