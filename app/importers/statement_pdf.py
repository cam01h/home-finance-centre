from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, List, Optional

import pdfplumber

# ================================================================
# the below is optimised for my banks stantes that only arrive in PDF form. Feel free to fork and
# adapt for your own bank statements.
# ================================================================
DATE_LINE_RE = re.compile(r"^(?P<day>\d{2})\s(?P<mon>[A-Za-z]{3})\s(?P<yy>\d{2})\s+(?P<rest>.+)$")

MONEY_RE = re.compile(r"(?P<num>\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})")

@dataclass
class _TxBlock:
    date_display: str            # e.g. "02/12/2025" (DD/MM/YYYY)
    raw_lines: List[str]         # all lines belonging to this transaction block


def _month_to_number(mon: str) -> int:
    #Convert 'Dec' -> 12 etc.
    months = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    m = months.get(mon.capitalize())
    if not m:
        raise ValueError(f"Unknown month token: {mon!r}")
    return m


def _yy_to_yyyy(yy: str) -> int:
    # Convert '25' -> 2025 etc.
    return 2000 + int(yy)


def _format_date_ddmmyyyy(day: str, mon: str, yy: str) -> str:
    # Convert 'DD', 'Mon', 'YY' -> 'DD/MM/YYYY'
    d = int(day)
    m = _month_to_number(mon)
    y = _yy_to_yyyy(yy)
    return f"{d:02d}/{m:02d}/{y:04d}"


def _iter_pdf_lines(pdf_path: Path) -> Iterable[str]:
    # Extract all text lines from the PDF, yielding one line at a time.
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if line:
                    yield line


# Allow leading whitespace + the common starters.
# This catches cases where pdf text extraction inserts odd spacing.
NO_DATE_START_RE = re.compile(r"^\s*(CR|DD|VIS|TFR|BP)\b")


def _split_into_blocks(lines: Iterable[str]) -> List[_TxBlock]:
    """
    remember that the intentional furtherance of PDFs in the world is
    a heinous crime against humanity and your children will judge you
    """
    blocks: List[_TxBlock] = []
    current: Optional[_TxBlock] = None
    last_date_display: Optional[str] = None

    for line in lines:
        normline = re.sub(r"[^A-Z]", "", line.upper())
        if normline.startswith("BALANCECARRIEDFORWARD") or normline.startswith("BALANCEBROUGHTFORWARD"):
            if current is not None:
                blocks.append(current)
                current = None
            continue

        m_date = DATE_LINE_RE.match(line)
        if m_date:
            # close current block
            if current is not None:
                blocks.append(current)

            last_date_display = _format_date_ddmmyyyy(
                m_date.group("day"), m_date.group("mon"), m_date.group("yy")
            )
            current = _TxBlock(date_display=last_date_display, raw_lines=[line])
            continue

        # If we have a date already, and the line looks like a new transaction starter
        # start a new block with inherited date.
        if last_date_display and NO_DATE_START_RE.match(line):
            if current is not None:
                blocks.append(current)
            current = _TxBlock(date_display=last_date_display, raw_lines=[line])
            continue

        # Otherwise, it's a continuation line (or header noise before first tx)
        if current is not None:
            current.raw_lines.append(line)

    if current is not None:
        blocks.append(current)

    return blocks

def _strip_trailing_money(text: str, n: int = 2) -> str:
    # Remove the last `n` money tokens from the END of the string.
    # Works whether the token has commas or not.
    out = text.strip()
    for _ in range(n):
        out = re.sub(rf"\s{MONEY_RE.pattern}\s*$", "", out).strip()
    return out


def _clean_amount_token(token: str) -> str:
    # Remove commas from a money token, e.g. "5,224.34" -> "5224.34"
    return token.replace(",", "")


def _extract_amount_and_balance(block_text: str) -> tuple[Optional[str], Optional[str]]:
    # Extract money tokens from the block text.
    nums = [m.group("num") for m in MONEY_RE.finditer(block_text)]
    if not nums:
        return None, None

    if len(nums) == 1:
        # Some HSBC lines extract only the amount (balance column missing in text layer)
        amount = _clean_amount_token(nums[-1])
        return amount, None

    # Usual case: ... amount balance
    amount = _clean_amount_token(nums[-2])
    balance = _clean_amount_token(nums[-1])
    return amount, balance



def _is_credit(block_text: str) -> bool:
    first_line = block_text.splitlines()[0] if block_text else ""

    # If statement omitted the date on same-day lines, credits still start with "CR "
    if first_line.startswith("CR "):
        return True

    # Otherwise, try the dated format: "DD Mon YY CR ..."
    m = DATE_LINE_RE.match(first_line)
    if not m:
        return False

    rest = m.group("rest").strip()
    return rest.startswith("CR ")



def _build_staging_row(block: _TxBlock) -> dict:
    # Build a staging row dict from the transaction block that matches your staging schema.
    block_text_multiline = "\n".join(block.raw_lines)
    block_text_flat = " ".join(block.raw_lines)

    amount, balance = _extract_amount_and_balance(block_text_flat)

    if amount is None:
        amount_out = ""
    else:
        if _is_credit(block_text_multiline):
            amount_out = amount  # credit
        else:
            amount_out = f"-{amount}"  # debit

    desc = block_text_flat

    # Remove trailing amount/balance safely (handles commas properly)
    desc = _strip_trailing_money(desc, n=2)

    # Optionally, you can also strip the date prefix from description.
    m = DATE_LINE_RE.match(block.raw_lines[0])
    if m:
        first_rest = m.group("rest").strip()
        continuation = block.raw_lines[1:]
        desc = " ".join([first_rest] + continuation).strip()

        desc = _strip_trailing_money(desc, n=2)

    # Drop statement boilerplate that sometimes looks like a transaction.
    # PDF text extraction sometimes removes spaces (e.g. BALANCECARRIEDFORWARD),
    # so we normalise to letters-only before checking.
    norm = re.sub(r"[^A-Z]", "", desc.upper())
    if norm.startswith("BALANCEBROUGHTFORWARD") or norm.startswith("BALANCECARRIEDFORWARD"):
        return {}

    merchant = ""

    return {
        "date": block.date_display,
        "merchant": merchant,
        "description": desc,
        "amount": amount_out,
        "primary": "",      # Not part of your staging schema, but useful for debugging
        "balancing": "",    # Not part of your staging schema, but useful for debugging
    }


def extract_transactions_from_pdf(pdf_path: str | Path) -> List[dict]:
    # Main entry point: extract transactions from the given PDF file path. Returns a list of staging row dicts.
    path = Path(pdf_path)

    # Basic safety checks
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {path}")

    # 1) Read all lines from the PDF
    lines = list(_iter_pdf_lines(path))

    # 2) Split into date-anchored transaction blocks
    blocks = _split_into_blocks(lines)

    # 3) Convert blocks to staging rows
    rows: List[dict] = []
    for b in blocks:
        row = _build_staging_row(b)

        # If we couldn't find an amount, it's probably not a transaction
        # (or it's a weird header line that accidentally looked like a date).
        # We keep only rows with a date AND a non-empty amount.
        if row and row.get("date") and row.get("amount"):
            rows.append(row)

    return rows
