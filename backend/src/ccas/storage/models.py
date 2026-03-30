"""ORM 資料模型定義。

定義 CCAS 系統的四張核心資料表：
- bills: 信用卡帳單
- transactions: 帳單內的消費明細
- categories: 關鍵字分類對照
- bank_configs: 銀行設定
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Bill(Base):
    """信用卡帳單。

    每張帳單以 (bank_code, billing_month) 為唯一識別。
    一張帳單包含多筆 Transaction（一對多關聯）。
    """

    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("bank_code", "billing_month", name="uq_bill_bank_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank_code: Mapped[str] = mapped_column(Text, nullable=False)
    billing_month: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )


class Transaction(Base):
    """消費交易明細。

    每筆交易隸屬於一張 Bill（多對一關聯）。
    金額以整數儲存（元為單位），外幣交易另記原始金額。
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id"), nullable=False
    )
    trans_date: Mapped[date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    merchant: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="TWD")
    original_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_last4: Mapped[str | None] = mapped_column(Text, nullable=True)
    installment_current: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installment_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    bill: Mapped["Bill"] = relationship(back_populates="transactions")


class Category(Base):
    """消費分類關鍵字對照。

    以 keyword（唯一）比對交易商家名稱，自動歸類消費類別。
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)


class BankConfig(Base):
    """銀行設定。

    每間銀行以 bank_code（唯一）識別，記錄 Gmail 篩選條件、
    PDF 密碼規則、使用的解析器版本等。
    """

    __tablename__ = "bank_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    gmail_filter: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_password_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_parser_version: Mapped[str] = mapped_column(Text, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
