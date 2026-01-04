from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Transaction, Entry


def create_transaction(
    session: Session,
    *,
    timestamp: datetime,
    description: str,
    primary_account_id: int,
    amount_pennies: int,
    balancing_account_id: int,
) -> Transaction:
    """
    Create a balanced transaction with two entries.
    Assumes all inputs are already validated.
    """

    tx = Transaction(
        timestamp=timestamp,
        description=description,
    )

    tx.entries = [
        Entry(
            account_id=primary_account_id,
            amount_pennies=amount_pennies,
        ),
        Entry(
            account_id=balancing_account_id,
            amount_pennies=-amount_pennies,
        ),
    ]

    session.add(tx)
    session.commit()
    session.refresh(tx)

    return tx
