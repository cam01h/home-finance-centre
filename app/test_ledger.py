from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Account, Transaction, Entry


def get_or_create_account(session: Session, name: str, type_: str) -> Account:
    acc = session.execute(select(Account).where(Account.name == name)).scalar_one_or_none()
    if acc is None:
        acc = Account(name=name, type=type_)
        session.add(acc)
        session.commit()
    return acc


def main():
    with Session(engine) as session:
        # 1) Ensure accounts exist
        current = get_or_create_account(session, "Current Account", "asset")
        groceries = get_or_create_account(session, "Groceries", "expense")

        # 2) Create a Tesco transaction with two entries (double-entry)
        txn = Transaction(description="Tesco shop")
        txn.entries = [
            Entry(account_id=groceries.id, amount_pennies=+10000),  # expense increases
            Entry(account_id=current.id, amount_pennies=-10000),    # asset decreases
        ]

        # 3) Enforce the core invariant BEFORE saving
        total = sum(e.amount_pennies for e in txn.entries)
        if total != 0:
            raise ValueError(f"Transaction not balanced (sum={total})")

        session.add(txn)
        session.commit()

        print(f"Created transaction id={txn.id}")

        # 4) Show balances: sum of entries per account
        rows = session.execute(
            select(Account.name, Account.type, func.coalesce(func.sum(Entry.amount_pennies), 0))
            .join(Entry, Entry.account_id == Account.id, isouter=True)
            .group_by(Account.id)
            .order_by(Account.id)
        ).all()

        print("Account balances (pennies):")
        for name, type_, bal in rows:
            print(f"- {name} [{type_}]: {bal}")


if __name__ == "__main__":
    main()
