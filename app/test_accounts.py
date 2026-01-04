from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Account


def main():
    with Session(engine) as session:
        # Find the account by name (if it exists)
        existing = session.execute(
            select(Account).where(Account.name == "Current Account")
        ).scalar_one_or_none()

        if existing is None:
            # Create it once
            account = Account(name="Current Account", type="asset")
            session.add(account)
            session.commit()
            print(f"Created account id={account.id}")
        else:
            account = existing
            print(f"Account already exists id={account.id}")

        # List all accounts
        accounts = session.execute(select(Account)).scalars().all()
        print("Accounts in database:")
        for acc in accounts:
            print(f"- {acc.id}: {acc.name} ({acc.type})")


if __name__ == "__main__":
    main()
