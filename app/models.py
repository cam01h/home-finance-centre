from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import ForeignKey, String, Integer, DateTime, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Keep account types sane (SQLite will enforce this)
    __table_args__ = (
        CheckConstraint(
            "type IN ('asset','liability','income','expense','equity')",
            name="ck_accounts_type",
        ),
    )

    entries: Mapped[List["Entry"]] = relationship(back_populates="account")


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
