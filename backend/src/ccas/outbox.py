"""通知投遞（Notification delivery）。

所有 Telegram 通知（新帳單通知、付款提醒、預算告警、解析失敗通知）共用同一條
投遞規則，集中在 :class:`Outbox`：

1. Telegram 未設定 → 不認領，回 ``SKIPPED_UNCONFIGURED``（設定補上後下次補送）。
2. 先認領（:class:`Claim` ``acquire``），搶不到 → ``ALREADY_DELIVERED``。
3. 發送；成功 → ``confirm`` 並回 ``SENT``，認領保留，不再重送。
4. 發送失敗 → ``release`` 認領讓下次執行重試，回 ``FAILED``。認領或釋放本身
   失敗時記錄例外（釋放失敗的事件需人工確認），不中斷呼叫端批次。

認領紀錄由 ledger adapter 決定（``Claim`` seam 的三個 adapter）：

- :class:`PaymentReminderClaim`：``payment_reminders`` (bill_id, reminder_type)
  唯一鍵；新帳單通知與付款提醒共用。
- :class:`BudgetAlertsClaim`：``budget_alerts.notified``；一則訊息涵蓋多筆告警。
- :class:`ParseFailureClaim`：``staged_attachments.failure_notified_at``；
  一則訊息涵蓋多份解析失敗的帳單附件。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import CursorResult, delete, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ccas.messaging import send_message
from ccas.storage.models import BudgetAlert, PaymentReminder, StagedAttachment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ccas.config import Settings

logger = logging.getLogger(__name__)

Transport = Callable[[str], Awaitable[object]]
"""送出一則文字訊息；失敗時拋出例外。"""


class DeliveryStatus(StrEnum):
    SENT = "sent"
    ALREADY_DELIVERED = "already_delivered"
    FAILED = "failed"
    SKIPPED_UNCONFIGURED = "skipped_unconfigured"


@dataclass(frozen=True)
class DeliveryOutcome:
    status: DeliveryStatus
    error: Exception | None = None


class Claim(Protocol):
    """通知事件的認領紀錄（ledger adapter）。"""

    async def acquire(self, session: AsyncSession) -> bool:
        """取得發送權；``False`` 代表事件已投遞過（或無待發送內容）。"""
        ...

    async def release(self, session: AsyncSession) -> None:
        """發送失敗後釋放認領，讓下次執行重試。"""
        ...

    async def confirm(self, session: AsyncSession) -> None:
        """發送成功後確認投遞。"""
        ...


class Outbox:
    """以單一投遞規則發送通知事件；見模組說明。"""

    def __init__(self, session: AsyncSession, transport: Transport | None) -> None:
        self._session = session
        self._transport = transport

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        session: AsyncSession,
        *,
        transport: Transport | None = None,
    ) -> Outbox:
        """依設定建立；Token 或 chat id 缺一即為未設定（所有投遞皆略過）。"""
        token = settings.telegram_bot_token.get_secret_value()
        chat_id = settings.telegram_chat_id
        if not token or not chat_id:
            return cls(session, None)
        if transport is None:
            transport = _TelegramTransport(token, chat_id)
        return cls(session, transport)

    @property
    def configured(self) -> bool:
        return self._transport is not None

    async def deliver(self, claim: Claim, render: Callable[[], str]) -> DeliveryOutcome:
        """依投遞規則發送 ``claim`` 代表的事件；``render`` 僅在認領成功後呼叫。

        本方法不拋例外：認領、發送、釋放或確認的失敗都轉為投遞結果或記錄，
        呼叫端的批次不會因單一事件中斷。
        """
        if self._transport is None:
            return DeliveryOutcome(DeliveryStatus.SKIPPED_UNCONFIGURED)
        try:
            acquired = await claim.acquire(self._session)
        except Exception as exc:
            # 尚未認領成功，無需釋放；清掉失敗的交易即可。
            await self._session.rollback()
            logger.exception("認領通知失敗: %r", claim)
            return DeliveryOutcome(DeliveryStatus.FAILED, exc)
        if not acquired:
            return DeliveryOutcome(DeliveryStatus.ALREADY_DELIVERED)
        try:
            await self._transport(render())
        except Exception as exc:
            await self._release(claim)
            return DeliveryOutcome(DeliveryStatus.FAILED, exc)
        await self._confirm(claim)
        return DeliveryOutcome(DeliveryStatus.SENT)

    async def _release(self, claim: Claim) -> None:
        try:
            await claim.release(self._session)
        except Exception:
            await self._session.rollback()
            logger.exception(
                "釋放通知認領失敗，該事件將不會自動重送，需人工確認: %r", claim
            )

    async def _confirm(self, claim: Claim) -> None:
        try:
            await claim.confirm(self._session)
        except Exception:
            # 訊息已送達，結果仍是 SENT；確認失敗只影響是否被判定為待補送。
            await self._session.rollback()
            logger.exception("通知已送出但確認投遞失敗: %r", claim)


@dataclass(frozen=True)
class _TelegramTransport:
    """綁定 token / chat id 的 Telegram transport（只保留必要欄位）。"""

    token: str = field(repr=False)
    chat_id: str

    async def __call__(self, text: str) -> object:
        return await send_message(self.token, self.chat_id, text)


@dataclass(frozen=True)
class PaymentReminderClaim:
    """以 ``payment_reminders`` (bill_id, reminder_type) 唯一鍵認領。"""

    bill_id: int
    reminder_type: str

    async def acquire(self, session: AsyncSession) -> bool:
        stmt = (
            sqlite_insert(PaymentReminder)
            .values(bill_id=self.bill_id, reminder_type=self.reminder_type)
            .on_conflict_do_nothing(index_elements=["bill_id", "reminder_type"])
        )
        result = cast(CursorResult[Any], await session.execute(stmt))
        await session.commit()
        return result.rowcount > 0

    async def release(self, session: AsyncSession) -> None:
        await session.execute(
            delete(PaymentReminder).where(
                PaymentReminder.bill_id == self.bill_id,
                PaymentReminder.reminder_type == self.reminder_type,
            )
        )
        await session.commit()

    async def confirm(self, session: AsyncSession) -> None:
        return None


@dataclass(frozen=True)
class BudgetAlertsClaim:
    """以 ``budget_alerts.notified`` 認領；一則訊息涵蓋多筆告警。

    告警列在投遞前已 commit（``notified=False``），故 ``acquire`` 不是原子操作：
    前提是預算評估只由單一 APScheduler 行程執行。若改為多個 worker 並行評估，
    須改為原子認領，否則可能重複發送。
    """

    alerts: Sequence[BudgetAlert]

    async def acquire(self, session: AsyncSession) -> bool:
        return any(not alert.notified for alert in self.alerts)

    async def release(self, session: AsyncSession) -> None:
        # notified 維持 False → 下次評估補送。
        return None

    async def confirm(self, session: AsyncSession) -> None:
        for alert in self.alerts:
            alert.notified = True
        await session.commit()


@dataclass
class ParseFailureClaim:
    """以 ``staged_attachments.failure_notified_at`` 認領解析失敗的帳單附件。

    ``acquire`` 以原子條件更新只認領尚未通知的附件，實際認領到的 id 存於
    ``claimed_ids``，供 render 只列出本次負責的附件。
    """

    attachment_ids: Sequence[int]
    claimed_ids: list[int] = field(default_factory=list)

    async def acquire(self, session: AsyncSession) -> bool:
        if not self.attachment_ids:
            return False
        stmt = (
            update(StagedAttachment)
            .where(
                StagedAttachment.id.in_(self.attachment_ids),
                StagedAttachment.failure_notified_at.is_(None),
            )
            .values(failure_notified_at=datetime.now(UTC))
            .returning(StagedAttachment.id)
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(stmt)
        self.claimed_ids = sorted(result.scalars().all())
        await session.commit()
        return bool(self.claimed_ids)

    async def release(self, session: AsyncSession) -> None:
        if not self.claimed_ids:
            return
        await session.execute(
            update(StagedAttachment)
            .where(StagedAttachment.id.in_(self.claimed_ids))
            .values(failure_notified_at=None)
            .execution_options(synchronize_session=False)
        )
        await session.commit()

    async def confirm(self, session: AsyncSession) -> None:
        return None
