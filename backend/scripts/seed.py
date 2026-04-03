"""開發用種子資料腳本。

Usage:
    uv run python backend/scripts/seed.py           # 新增 seed 資料（不清除既有）
    uv run python backend/scripts/seed.py --reset    # 清除所有資料後重新寫入

包含 BankConfig、Category、Bill、Transaction 範例資料。
"""

import argparse
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
    """寫入銀行設定範例資料（僅含已實作 parser 的銀行）。"""
    configs = [
        BankConfig(
            bank_code="CTBC",
            bank_name="中國信託",
            gmail_filter="from:service@ctbcbank.com subject:信用卡",
            pdf_password_rule="ID_LAST_4 + BIRTHDAY_MMDD",
            active_parser_version="v1",
            is_active=True,
        ),
    ]
    session.add_all(configs)
    await session.commit()


async def seed_categories(session: AsyncSession) -> None:
    """寫入消費分類關鍵字對照範例資料。

    涵蓋 CTBC 帳單常見的消費類別。
    """
    categories = [
        # 日用品 / 超市
        Category(keyword="全聯", category="日用品"),
        Category(keyword="家樂福", category="日用品"),
        Category(keyword="大潤發", category="日用品"),
        Category(keyword="好市多", category="日用品"),
        Category(keyword="COSTCO", category="日用品"),
        Category(keyword="寶雅", category="日用品"),
        Category(keyword="屈臣氏", category="日用品"),
        Category(keyword="康是美", category="日用品"),
        # 超商
        Category(keyword="統一超商", category="超商"),
        Category(keyword="7-ELEVEN", category="超商"),
        Category(keyword="全家", category="超商"),
        Category(keyword="萊爾富", category="超商"),
        Category(keyword="OK超商", category="超商"),
        Category(keyword="ICP", category="超商"),
        # 餐飲
        Category(keyword="麥當勞", category="餐飲"),
        Category(keyword="星巴克", category="餐飲"),
        Category(keyword="摩斯", category="餐飲"),
        Category(keyword="肯德基", category="餐飲"),
        Category(keyword="UBER EATS", category="餐飲"),
        Category(keyword="FOODPANDA", category="餐飲"),
        # 交通
        Category(keyword="中油", category="交通"),
        Category(keyword="台灣中油", category="交通"),
        Category(keyword="UBER", category="交通"),
        Category(keyword="台灣大車隊", category="交通"),
        Category(keyword="高鐵", category="交通"),
        Category(keyword="台鐵", category="交通"),
        Category(keyword="悠遊卡", category="交通"),
        # 通訊
        Category(keyword="台灣大哥大", category="通訊"),
        Category(keyword="中華電信", category="通訊"),
        Category(keyword="遠傳", category="通訊"),
        # 娛樂 / 訂閱
        Category(keyword="NETFLIX", category="娛樂"),
        Category(keyword="SPOTIFY", category="娛樂"),
        Category(keyword="YOUTUBE", category="娛樂"),
        Category(keyword="DISNEY", category="娛樂"),
        Category(keyword="APPLE", category="娛樂"),
        Category(keyword="GOOGLE", category="娛樂"),
        # 購物
        Category(keyword="蝦皮", category="購物"),
        Category(keyword="SHOPEE", category="購物"),
        Category(keyword="MOMO", category="購物"),
        Category(keyword="PCHOME", category="購物"),
        Category(keyword="AMAZON", category="購物"),
        Category(keyword="博客來", category="購物"),
        # 百貨
        Category(keyword="SOGO", category="百貨"),
        Category(keyword="新光三越", category="百貨"),
        Category(keyword="統一時代", category="百貨"),
        Category(keyword="MITSUI", category="百貨"),
        Category(keyword="LaLaport", category="百貨"),
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CCAS seed data management.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Clear all existing data before seeding.",
    )
    return parser.parse_args()


async def main(*, reset: bool = False) -> None:
    """執行種子資料寫入流程並輸出統計。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        if reset:
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
    args = _parse_args()
    asyncio.run(main(reset=args.reset))
