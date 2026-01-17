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

def delete_transaction(session: Session, transaction_id: int) -> bool:
    """
    Delete a transaction (and its entries via ORM cascade).

    Returns:
        True if the transaction existed and was deleted, False if not found.
    """
    tx = session.get(Transaction, int(transaction_id))
    if not tx:
        return False

    session.delete(tx)
    session.commit()
    return True
