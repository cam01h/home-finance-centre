from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class ParsedTransaction:
    date: str                 # keep as string for now; we’ll parse properly later
    description: str
    amount: Decimal
    balance: Optional[Decimal] = None


def extract_transactions_from_pdf(pdf_path: str | Path) -> List[ParsedTransaction]:
    """
    HSBC PDF import spike.
    For now: just validates the path and returns an empty list.
    Next iteration: actually parse with pdfplumber.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {path}")

    return []
