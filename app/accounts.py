from typing import List
from sqlalchemy.orm import Session

from .models import Account

from app.models import AccountLink
from app.db import SessionLocal



PRIMARY_TYPES = ("asset", "liability")
BALANCING_TYPES = ("income", "expense", "adjustment")


def get_primary_accounts(session: Session, active_only: bool = True) -> List[Account]:
    query = session.query(Account).filter(Account.type.in_(PRIMARY_TYPES))
    if active_only:
        query = query.filter(Account.is_active.is_(True))
    return query.order_by(Account.name).all()


def get_balancing_accounts(session: Session, active_only: bool = True) -> List[Account]:
    query = session.query(Account).filter(Account.type.in_(BALANCING_TYPES))
    if active_only:
        query = query.filter(Account.is_active.is_(True))
    return query.order_by(Account.name).all()


def add_primary_account(session: Session, name: str, account_type: str) -> Account:
    if account_type not in PRIMARY_TYPES:
        raise ValueError("Primary accounts must be asset or liability")

    account = Account(name=name, type=account_type)
    session.add(account)
    session.commit()
    return account


def add_balancing_account(session: Session, name: str, account_type: str) -> Account:
    if account_type not in BALANCING_TYPES:
        raise ValueError("Balancing accounts must be income, expense, or adjustment")

    account = Account(name=name, type=account_type)
    session.add(account)
    session.commit()
    return account


def close_account(session: Session, account_id: int) -> None:
    account = session.get(Account, account_id)
    if not account:
        raise ValueError("Account not found")

    account.is_active = False
    session.commit()

def get_account_links():
    """Return all asset ↔ liability links."""
    with SessionLocal() as session:
        return session.query(AccountLink).all()


def add_account_link(asset_account_id: int, liability_account_id: int):
    """Create a new link between an asset and a liability account."""
    with SessionLocal() as session:
        link = AccountLink(
            asset_account_id=asset_account_id,
            liability_account_id=liability_account_id,
        )
        session.add(link)
        session.commit()
        return link


def delete_account_link(link_id: int):
    """Delete an existing account link."""
    with SessionLocal() as session:
        link = session.get(AccountLink, link_id)
        if link:
            session.delete(link)
            session.commit()

