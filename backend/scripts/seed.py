"""開發用種子資料腳本。

可重複執行（冪等）：每次先清除既有資料再重新寫入。
包含 BankConfig、Category、Bill、Transaction 範例資料。
"""

import asyncio
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.config import get_settings
from ccas.storage.models import BankConfig, Base, Bill, Category, Transaction


async def clear_seed_data(session: AsyncSession) -> None:
    """清除所有種子資料，依照外鍵順序刪除。"""
    await session.execute(delete(Transaction))
    await session.execute(delete(Bill))
    await session.execute(delete(Category))
    await session.execute(delete(BankConfig))
    await session.commit()


async def seed_bank_configs(session: AsyncSession) -> None:
    """寫入銀行設定範例資料（中國信託、國泰世華）。"""
    configs = [
        BankConfig(
            bank_code="CTBC",
            bank_name="中國信託",
            gmail_filter="from:service@ctbcbank.com subject:信用卡",
            pdf_password_rule="ID_LAST_4 + BIRTHDAY_MMDD",
            active_parser_version="v1",
            is_active=True,
        ),
        BankConfig(
            bank_code="CATHAY",
            bank_name="國泰世華",
            gmail_filter="from:cathaybk@email.cathaybk.com.tw subject:帳單",
            pdf_password_rule="ID_FULL",
            active_parser_version="v1",
            is_active=True,
        ),
    ]
    session.add_all(configs)
    await session.commit()


async def seed_categories(session: AsyncSession) -> None:
    """寫入消費分類關鍵字對照範例資料。"""
    categories = [
        Category(keyword="全聯", category="日用品"),
        Category(keyword="家樂福", category="日用品"),
        Category(keyword="麥當勞", category="美食"),
        Category(keyword="星巴克", category="飲料"),
        Category(keyword="台灣大哥大", category="通訊"),
        Category(keyword="中油", category="交通"),
        Category(keyword="NETFLIX", category="娛樂"),
        Category(keyword="SPOTIFY", category="娛樂"),
        Category(keyword="UBER", category="交通"),
    ]
    session.add_all(categories)
    await session.commit()


async def seed_bills_and_transactions(session: AsyncSession) -> None:
    """寫入帳單與交易明細範例資料。"""
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=28500,
        due_date=date(2026, 4, 15),
        is_paid=False,
        file_path="/data/pdfs/ctbc_2026_03.pdf",
        created_at=datetime(2026, 3, 28, 10, 0, 0),
    )
    session.add(bill)
    await session.flush()

    transactions = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="全聯福利中心",
            amount=1250,
            currency="TWD",
            card_last4="1234",
            category="日用品",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 5),
            merchant="星巴克 信義門市",
            amount=380,
            currency="TWD",
            card_last4="1234",
            category="飲料",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 10),
            merchant="NETFLIX.COM",
            amount=390,
            currency="TWD",
            card_last4="1234",
            category="娛樂",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 15),
            merchant="AMAZON.CO.JP",
            amount=8500,
            currency="TWD",
            original_amount=3980,
            card_last4="5678",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 20),
            merchant="APPLE STORE",
            amount=17980,
            currency="TWD",
            card_last4="1234",
            installment_current=1,
            installment_total=6,
        ),
    ]
    session.add_all(transactions)
    await session.commit()


async def main() -> None:
    """執行種子資料寫入流程並輸出統計。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        print("Clearing existing seed data...")
        await clear_seed_data(session)

        print("Seeding bank configs...")
        await seed_bank_configs(session)

        print("Seeding categories...")
        await seed_categories(session)

        print("Seeding bills and transactions...")
        await seed_bills_and_transactions(session)

        # Verify
        result = await session.execute(select(Bill))
        bills = result.scalars().all()
        print(f"Seeded {len(bills)} bill(s)")

        result = await session.execute(select(Transaction))
        txns = result.scalars().all()
        print(f"Seeded {len(txns)} transaction(s)")

        result = await session.execute(select(Category))
        cats = result.scalars().all()
        print(f"Seeded {len(cats)} category(s)")

        result = await session.execute(select(BankConfig))
        banks = result.scalars().all()
        print(f"Seeded {len(banks)} bank config(s)")

    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
