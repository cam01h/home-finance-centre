from __future__ import annotations

from pathlib import Path

import pandas as pd


IGNORE = "(ignore)"


def extract_transactions_from_csv(csv_path: str | Path, mapping: dict[str, str]) -> list[dict]:
    """
    Read a CSV and return rows in the staging format used by BulkEntryWindow.

    Required mapping keys:
      - "date"
      - "amount"

    Optional mapping keys:
      - "merchant"
      - "description"
      - "primary"
      - "balancing"
    """
    csv_path = str(csv_path)

    # Read full CSV (MVP)
    df = pd.read_csv(csv_path)

    rows_out: list[dict] = []
    for _, row in df.iterrows():
        out: dict[str, str] = {}

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
            col = mapping.get(key, IGNORE)
            if col == IGNORE:
                out[key] = ""
            else:
                v = row.get(col, "")
                out[key] = "" if pd.isna(v) else str(v).strip()

        # Optional account fields (we’ll mostly leave blank in MVP)
        for key in ("primary", "balancing"):
            col = mapping.get(key, IGNORE)
            if col == IGNORE:
                out[key] = ""
            else:
                v = row.get(col, "")
                out[key] = "" if pd.isna(v) else str(v).strip()

        # Skip balance rows (not real transactions)
        text_blob = f"{out.get('merchant', '')} {out.get('description', '')}".upper()
        if "BALANCE BROUGHT FORWARD" in text_blob or "BALANCE CARRIED FORWARD" in text_blob:
            continue

        rows_out.append(out)

    return rows_out
