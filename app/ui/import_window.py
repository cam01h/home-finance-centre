import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
from app.importers.statement_pdf import extract_transactions_from_pdf


IGNORE = "(ignore)"


class ImportWindow(tk.Toplevel):
    """
    Import file window (CSV now; PDF later).
    For MVP: CSV -> mapping -> rows -> callback into BulkEntryWindow.
    """

    def __init__(self, master, *, on_import_rows):
        super().__init__(master)
        self.title("Import file")
        self.geometry("720x520")

        self.on_import_rows = on_import_rows
        self.selected_path = None
        self.headers = []

        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Import file (CSV now, PDF later)",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        top = ttk.Frame(container)
        top.pack(fill="x")

        ttk.Button(top, text="Add file…", command=self._add_file).pack(side="left")
        self.path_label = ttk.Label(top, text="", wraplength=520)
        self.path_label.pack(side="left", padx=(10, 0))

        # Mapping area (created after headers load)
        self.mapping_frame = ttk.LabelFrame(container, text="Map CSV columns to staging fields")
        self.mapping_frame.pack(fill="x", pady=(12, 0))

        self.mapping_vars = {}   # field -> tk.StringVar
        self.mapping_boxes = {}  # field -> Combobox

        # Native CSV preview (first 5 rows)
        self.preview_frame = ttk.LabelFrame(container, text="CSV preview (first 5 rows)")
        self.preview_frame.pack(fill="both", expand=False, pady=(12, 0))

        self.preview_tree = ttk.Treeview(self.preview_frame, show="headings", height=6)
        self.preview_tree.pack(fill="both", expand=True)

        self._preview_scroll_x = ttk.Scrollbar(self.preview_frame, orient="horizontal", command=self.preview_tree.xview)
        self._preview_scroll_x.pack(fill="x")
        self.preview_tree.configure(xscrollcommand=self._preview_scroll_x.set)

        # Preview / messages
        self.output = tk.Text(container, height=8)
        self.output.pack(fill="both", expand=True, pady=(12, 0))

        # Buttons
        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(12, 0))
        self.import_btn = ttk.Button(bottom, text="Import into staging", command=self._import_csv)
        self.import_btn.pack(side="left")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")

        # Start disabled until a CSV is selected
        self.import_btn.configure(state="disabled")

        # Define the canonical staging fields we support
        self.fields = [
            ("date", "Date (required)"),
            ("amount", "Amount (required)"),
            ("merchant", "Merchant"),
            ("description", "Description"),
            ("primary", "Primary account"),
            ("balancing", "Balancing account"),
        ]

        self._build_mapping_ui([])

    def _log(self, text: str) -> None:
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def _clear_log(self) -> None:
        self.output.delete("1.0", "end")

    def _build_mapping_ui(self, headers):
        # Clear any existing widgets in mapping_frame
        for child in self.mapping_frame.winfo_children():
            child.destroy()

        options = [IGNORE] + list(headers)

        for r, (field_key, label) in enumerate(self.fields):
            ttk.Label(self.mapping_frame, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=6)

            var = tk.StringVar(value=IGNORE)
            box = ttk.Combobox(self.mapping_frame, values=options, textvariable=var, state="readonly")
            box.grid(row=r, column=1, sticky="ew", padx=8, pady=6)

            self.mapping_vars[field_key] = var
            self.mapping_boxes[field_key] = box

        self.mapping_frame.columnconfigure(1, weight=1)

    def _show_preview(self, df_preview: pd.DataFrame) -> None:
        # Clear existing columns + rows
        for col in self.preview_tree["columns"]:
            self.preview_tree.heading(col, text="")
        self.preview_tree.delete(*self.preview_tree.get_children())

        cols = list(df_preview.columns)
        self.preview_tree["columns"] = cols

        # Headings + widths (simple + readable)
        for c in cols:
            self.preview_tree.heading(c, text=str(c))
            self.preview_tree.column(c, width=140, stretch=False, anchor="w")

        # Insert rows (native values)
        for _, row in df_preview.iterrows():
            values = ["" if pd.isna(row[c]) else str(row[c]) for c in cols]
            self.preview_tree.insert("", "end", values=values)

    def _add_file(self):
        path = filedialog.askopenfilename(
            title="Select file",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self.selected_path = path
        self.path_label.configure(text=path)

        self._clear_log()
        self._log(f"Selected file: {path}")

        if not path.lower().endswith(".csv"):
            self.import_btn.configure(state="disabled")
            messagebox.showinfo("Not supported yet", "Only CSV files are supported right now.")
            return

        try:
            # Headers-only read
            df0 = pd.read_csv(path, nrows=0)
            self.headers = list(df0.columns)
            
            df_preview = pd.read_csv(path, nrows=5)
            self._show_preview(df_preview)
            
            self._log("\nDetected CSV columns:")
            for h in self.headers:
                self._log(f" - {h}")

            self._build_mapping_ui(self.headers)
            self.import_btn.configure(state="normal")

        except Exception as e:
            self.import_btn.configure(state="disabled")
            messagebox.showerror("Import error", f"Failed to read CSV headers:\n{e}")

    def _import_csv(self):
        if not self.selected_path or not self.selected_path.lower().endswith(".csv"):
            return

        # Build mapping
        mapping = {k: self.mapping_vars[k].get() for k, _ in self.fields}

        # Enforce required fields
        if mapping["date"] == IGNORE or mapping["amount"] == IGNORE:
            messagebox.showerror("Mapping error", "Date and Amount must be mapped (required).")
            return

        # Read full CSV (MVP)
        try:
            df = pd.read_csv(self.selected_path)

            rows_out = []
            for _, row in df.iterrows():
                out = {}

                # Date: parse day-first; format DD/MM/YYYY
                raw_date = row.get(mapping["date"], "")
                dt = pd.to_datetime(raw_date, dayfirst=True, errors="coerce")
                if pd.isna(dt):
                    out["date"] = ""
                else:
                    out["date"] = dt.strftime("%d/%m/%Y")

                # Amount: keep as string; strip currency and commas
                raw_amt = row.get(mapping["amount"], "")
                amt_s = "" if pd.isna(raw_amt) else str(raw_amt)
                amt_s = amt_s.replace("£", "").replace(",", "").strip()
                out["amount"] = amt_s

                # Optional text fields
                for key in ("merchant", "description"):
                    col = mapping[key]
                    if col == IGNORE:
                        out[key] = ""
                    else:
                        v = row.get(col, "")
                        out[key] = "" if pd.isna(v) else str(v).strip()

                # Optional account fields (we’ll mostly leave blank in MVP)
                for key in ("primary", "balancing"):
                    col = mapping[key]
                    if col == IGNORE:
                        out[key] = ""
                    else:
                        v = row.get(col, "")
                        out[key] = "" if pd.isna(v) else str(v).strip()

                rows_out.append(out)

            if not rows_out:
                messagebox.showinfo("Nothing imported", "No rows found in the CSV.")
                return

            # Send rows to BulkEntryWindow
            self.on_import_rows(rows_out)

            messagebox.showinfo("Imported", f"Imported {len(rows_out)} rows into staging.")
            self.destroy()

        except Exception as e:
            messagebox.showerror("Import error", f"Failed to import CSV:\n{e}")
