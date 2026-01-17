from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import ForeignKey, String, Integer, DateTime, CheckConstraint, Column, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    # Existing concept: the “kind” of account
    type = Column(String, nullable=False)

    # New: lets you “close” an account without deleting it (history stays intact)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "type IN ('asset','liability','income','expense','adjustment')",
            name="ck_accounts_type"
        ),
    )

    # Existing relationship (assuming you already have Entry.account back_populates="account")
    entries = relationship("Entry", back_populates="account")

    # Optional convenience (no DB column)
    @property
    def is_primary(self) -> bool:
        return self.type in ("asset", "liability")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    description: Mapped[str] = mapped_column(String(200), nullable=False)

    entries: Mapped[List["Entry"]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
    )


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    # Store money as integer pennies to avoid float errors
    amount_pennies: Mapped[int] = mapped_column(Integer, nullable=False)

    transaction: Mapped["Transaction"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship(back_populates="entries")

class AccountLink(Base):
    __tablename__ = "account_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The "thing" (asset) e.g. House, Car
    asset_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
    )

    # The "encumbrance" (liability) e.g. Mortgage, Car loan
    liability_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
    )

    # Prevent duplicate links like (House, Mortgage) being inserted twice
    __table_args__ = (
        UniqueConstraint(
            "asset_account_id",
            "liability_account_id",
            name="uq_account_links_asset_liability",
        ),
    )

    # These make it easy to work with in Python/Qt (optional but useful)
    asset_account: Mapped["Account"] = relationship(
        "Account",
        foreign_keys=[asset_account_id],
    )
    liability_account: Mapped["Account"] = relationship(
        "Account",
        foreign_keys=[liability_account_id],
    )