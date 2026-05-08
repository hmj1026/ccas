"""ORM 資料模型定義。

定義 CCAS 系統的資料表：
- bills: 信用卡帳單
- transactions: 帳單內的消費明細
- categories: 關鍵字分類對照
- bank_configs: 銀行設定
- staged_attachments: Gmail 附件 staging 記錄
- bank_settings: 銀行 enabled toggle 與 display metadata（oauth-onboarding-ui §2.1）
- bank_secrets: PDF 解密密碼密文儲存（oauth-onboarding-ui §2.2）
- gmail_oauth_state: Gmail OAuth Web flow PKCE state（oauth-onboarding-ui §2.3）
- pipeline_runs: pipeline 執行歷史與即時進度 SSOT（pipeline-operations-center §1）
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    is_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    bill: Mapped["Bill"] = relationship(back_populates="transactions")


class Category(Base):
    """消費分類關鍵字對照。

    以 keyword（唯一）比對交易商家名稱，自動歸類消費類別。

    ``source`` 標記 row 來源：``"seed"`` 表示由 ``ccas.tools.categories``
    從 YAML 寫入；``"user"`` 表示使用者在後台手動新增或修改。reseed 時
    只會 DELETE / UPDATE ``source == "seed"`` 的 row，避免覆寫使用者
    資料，同時又能把 YAML 已移除的 seed 規則真正刪掉。
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Literal["seed", "user"]] = mapped_column(
        Text, nullable=False, server_default="user", default="user"
    )


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


class StagedAttachment(Base):
    """Gmail 附件 staging 記錄。

    每筆記錄追蹤一個從 Gmail 下載的 PDF 附件，
    包含其 Gmail 來源識別資訊、落地路徑與處理狀態。
    以 (gmail_message_id, gmail_part_id) 為穩定 dedupe 鍵，
    防止同一附件重複 staging。`gmail_attachment_id` 每次 Gmail API 呼叫
    都會重生，僅用於下載動作，不可作為 dedupe 鍵。
    """

    __tablename__ = "staged_attachments"
    __table_args__ = (
        UniqueConstraint(
            "gmail_message_id",
            "gmail_part_id",
            name="uq_staged_gmail_message_part",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank_code: Mapped[str] = mapped_column(Text, nullable=False)
    gmail_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    gmail_attachment_id: Mapped[str] = mapped_column(Text, nullable=False)
    gmail_part_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    staged_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(
        Text, server_default="attachment", nullable=False
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PaymentReminder(Base):
    """付款提醒發送記錄。

    以 (bill_id, reminder_type) 為唯一識別，
    防止同一帳單同一提醒類型重複發送。
    """

    __tablename__ = "payment_reminders"
    __table_args__ = (
        UniqueConstraint("bill_id", "reminder_type", name="uq_reminder_bill_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id"), nullable=False
    )
    reminder_type: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class BankSettings(Base):
    """銀行 UI 設定（oauth-onboarding-ui §2.1）。

    取代 ``banks.yaml`` 的 ``enabled`` 欄位作為 SSOT；保留 yaml 為 fallback。
    PK 為 ``code``（與 banks.yaml 的 bank_code 同名、皆為大寫）。

    與 ``bank_configs`` 並列：
    - ``bank_configs``：解析器設定（gmail filter / pdf 規則 / parser 版本）
    - ``bank_settings``：使用者偏好（enabled toggle / display name / notes）
    """

    __tablename__ = "bank_settings"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class BankSecret(Base):
    """PDF 解密密碼密文儲存（oauth-onboarding-ui §2.2）。

    ``encrypted_password`` 為 ``MasterKeyManager.encrypt`` 產生的 base64
    Fernet ciphertext；明文密碼絕不入庫。master.key 必須與密文同備份還原，
    否則解密將失敗（``MasterKeyMismatchError``）。
    """

    __tablename__ = "bank_secrets"

    bank_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GmailOAuthState(Base):
    """Gmail OAuth Web flow 一次性 PKCE state（oauth-onboarding-ui §2.3）。

    ``state`` 由 ``/api/setup/gmail/authorize`` 產生並寫入；callback 驗證後
    刪除。entrypoint 啟動時清理 ``created_at`` 超過 1 天的條目（避免堆積
    過期 state）。
    """

    __tablename__ = "gmail_oauth_state"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    code_verifier: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class PipelineRunStatus(StrEnum):
    """Pipeline 執行狀態（pipeline-operations-center D5）。

    queued: 已建立 row 等待 worker 取出
    running: worker 已開始執行
    succeeded: 全部階段完成（item-level failure 仍算 succeeded，
        計入 stage_summary.fail）
    failed: 階段 crash / RQ timeout / unhandled exception
    cancelled: 預留欄位，本 change 不實作 cancel API（Phase 2）
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineRun(Base):
    """Pipeline 執行歷史與即時進度 SSOT（pipeline-operations-center §1）。

    取代「trigger 後只回 job_id、跑完即遺」的舊行為；每筆 trigger 對應
    一筆 row，由 ``DbProgressReporter`` 在 worker 執行期間更新進度欄位。
    CLI 與 scheduler 路徑走 ``NoopProgressReporter`` 不寫此表（D10）。

    欄位：
    - ``id``: UUID PK，由 router 端產生（不依賴 DB autoincrement）
    - ``job_id``: RQ enqueue 後的 job id，與 ``id`` 一對一
    - ``status``: 狀態 enum，初始 queued、worker 開始 running、終態 succeeded/failed
    - ``triggered_by``: ``"api"`` / ``"cli"`` / ``"scheduler"`` 等字面值（D2.1）
    - ``params``: trigger 時的 PipelineOptions JSON（force / bank_code / year /
      month / from_stage / to_stage）
    - ``current_stage``: 當前正在執行的階段名稱（ingest/decrypt/parse/classify/notify）
    - ``current_stage_processed``: 當前階段已處理 item 數
    - ``current_stage_total``: 當前階段總 item 數
    - ``stage_summary``: 已完成階段陣列，每筆 ``{stage, ok, fail, elapsed_ms}``
    - ``error_message``: 階段 crash 或 RQ timeout 訊息
    - ``started_at`` / ``completed_at`` / ``created_at`` / ``updated_at``: 時間戳

    SQLite trigger 確保 ``updated_at`` 在 Core-style bulk UPDATE 下亦自動刷新
    （與 ``bank_settings`` 同 pattern，見 alembic ``2570bbdebf54``）。
    """

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index(
            "ix_pipeline_runs_created_at_desc",
            text("created_at DESC"),
        ),
        Index("ix_pipeline_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PipelineRunStatus] = mapped_column(
        String(16),
        nullable=False,
        default=PipelineRunStatus.QUEUED,
        server_default=PipelineRunStatus.QUEUED.value,
    )
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_stage_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    current_stage_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    stage_summary: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
