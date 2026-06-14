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
        Index("ix_bills_billing_month", "billing_month"),
        Index(
            "ix_bills_is_notified_false",
            "is_notified",
            sqlite_where=text("is_notified = 0"),
        ),
        Index(
            "ix_bills_is_paid_false",
            "is_paid",
            sqlite_where=text("is_paid = 0"),
        ),
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
    __table_args__ = (
        Index("ix_transactions_bill_id", "bill_id"),
        # 類別篩選 + 依交易日排序（交易列表 / 匯出）與類別彙總（analytics）熱路徑。
        Index("ix_transactions_category_trans_date", "category", "trans_date"),
        # 商家彙總（top-merchants GROUP BY merchant）與商家篩選熱路徑。
        Index("ix_transactions_merchant", "merchant"),
    )

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

    # bills-management-and-insights §1.1 — 使用者編輯欄位
    manual_category_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    merchant_alias: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

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


class StagedAttachmentStatus(StrEnum):
    """Staged attachment 處理狀態 SSOT（全部九個合法值）。

    staged: ingest 落地完成，等待 decrypt
    decrypted: 解密完成（或未加密透通），等待 parse
    decrypt_failed: 解密失敗（密碼解析失敗 / staged_path 異常 / 解密例外）
    parsed: 解析完成
    parse_skipped: 解析略過（無對應 parser 等）
    parse_failed: 解析失敗
    manual_review_needed: pipeline 偵測到需人工介入（worker bulk update）
    failed: ingest 階段失敗
    fetch_expired: 來源下載連結過期（如 FUBON record_not_found）

    DB 欄位維持 ``Mapped[str]``（Text），不做 enum migration；
    API Literal（``schemas.StagedAttachmentStatusLiteral``）須與本 enum
    同步，由 unit test 保證。
    """

    STAGED = "staged"
    DECRYPTED = "decrypted"
    DECRYPT_FAILED = "decrypt_failed"
    PARSED = "parsed"
    PARSE_SKIPPED = "parse_skipped"
    PARSE_FAILED = "parse_failed"
    MANUAL_REVIEW_NEEDED = "manual_review_needed"
    FAILED = "failed"
    FETCH_EXPIRED = "fetch_expired"


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
        Index("ix_staged_attachments_status", "status"),
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
        Index("ix_payment_reminders_bill_id", "bill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id"), nullable=False
    )
    reminder_type: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ReminderChannel(StrEnum):
    """付款提醒通知管道（bills-management-and-insights §5）。

    telegram: 僅推 Telegram（沿用既有 ``send_payment_reminders`` 行為）
    ui_banner: 僅顯示 UI banner（不推 Telegram，預留 future enhancement）
    both: Telegram + UI banner 兩者都推
    """

    TELEGRAM = "telegram"
    UI_BANNER = "ui_banner"
    BOTH = "both"


class ReminderSetting(Base):
    """付款提醒設定（bills-management-and-insights §5）。

    keyed by ``bill_id`` (PK FK)；每張帳單最多一筆 row。沒有 row 視同預設
    （enabled=true、days_before=[3,1]、channel=telegram），與 change 前行為等價。

    **Spec deviation**：design §D9 假設既有 ``PaymentReminder`` 模型已有
    ``(days_before, channel, enabled)`` 欄位，但實際上 ``payment_reminders``
    為 sent log（``bill_id`` + ``reminder_type`` + ``sent_at``）。為避免混淆
    sent log 與設定兩種語意，獨立新表 ``reminder_settings`` 儲存 settings；
    sent log 表保持原樣不動。
    """

    __tablename__ = "reminder_settings"

    bill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    # JSON list of int days, e.g. [3, 1]; evaluator iterates each value
    days_before: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[3, 1]'")
    )
    channel: Mapped[ReminderChannel] = mapped_column(
        String(16),
        nullable=False,
        default=ReminderChannel.TELEGRAM,
        server_default=ReminderChannel.TELEGRAM.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


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


class PatternType(StrEnum):
    """使用者分類規則的比對策略（bills-management-and-insights §1.2）。

    keyword: 子字串比對（case-insensitive，正規化後）
    exact: 完全相等（normalize 後）
    regex: 正規表示式（含 100ms timeout 保護，避免 catastrophic backtracking）
    """

    KEYWORD = "keyword"
    EXACT = "exact"
    REGEX = "regex"


class UserClassificationRule(Base):
    """使用者自訂進階分類規則（bills-management-and-insights §1.2）。

    與既有 ``categories`` 表（keyword + 字串 category）並列：
    - ``categories``：seed yaml 與簡單 keyword 規則（內建分類引擎）
    - ``classification_rules``：使用者自訂進階規則，支援 keyword / exact /
      regex 三種 pattern_type、priority 排序、enabled toggle

    classify 流程依序：``manual_category_override`` → user rules
    （priority DESC）→ 內建 engine → ``DEFAULT_CATEGORY``。

    **Spec deviation**：spec §1.2 命名為 ``ClassificationRule``；為避免與
    既有 ``classifier/rules.py:ClassificationRule`` (in-memory dataclass for
    keyword Category snapshot) 命名衝突，Python class 改名為
    ``UserClassificationRule``。table 名仍為 ``classification_rules`` 與 spec
    一致；對 API / migration / FK reference 完全等價。
    """

    __tablename__ = "classification_rules"
    __table_args__ = (
        Index(
            "ix_classification_rules_priority_enabled",
            text("priority DESC"),
            "enabled",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_type: Mapped[PatternType] = mapped_column(
        String(16), nullable=False, default=PatternType.KEYWORD
    )
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=False
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class BudgetScope(StrEnum):
    """預算範圍（bills-management-and-insights §1.3）。

    monthly_total: 整月總支出 cap（``scope_ref`` 必為 NULL）
    monthly_category: 單一分類月支出 cap（``scope_ref`` 為 category 名稱）
    monthly_bank: 單一銀行月支出 cap（``scope_ref`` 為 bank_code）
    """

    MONTHLY_TOTAL = "monthly_total"
    MONTHLY_CATEGORY = "monthly_category"
    MONTHLY_BANK = "monthly_bank"


class Budget(Base):
    """預算上限與警示閾值（bills-management-and-insights §1.3）。

    每筆 row 為一個 active 預算規則。``scope_ref`` 依 ``scope`` 不同有不同
    解讀（見 BudgetScope docstring）；evaluator 每日跑一次（scheduler），
    超過 ``alert_threshold_percent`` 即建立 BudgetAlert + 推 Telegram。
    """

    __tablename__ = "budgets"
    __table_args__ = (Index("ix_budgets_scope_ref", "scope", "scope_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[BudgetScope] = mapped_column(String(32), nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whole NTD dollars (元); the whole system stores integer NTD, never cents
    amount_ntd: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_threshold_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=80, server_default="80"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class BudgetAlert(Base):
    """預算超支警示記錄（bills-management-and-insights §1.4）。

    evaluator 偵測到超過閾值即建立一筆。同月同 budget 同 threshold 不重
    複觸發（evaluator 端去重）。``acknowledged_at`` 由 dashboard banner 的
    確認按鈕填入。
    """

    __tablename__ = "budget_alerts"
    __table_args__ = (
        Index(
            "ix_budget_alerts_triggered_at_desc",
            text("triggered_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("budgets.id"), nullable=False
    )
    period_year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    threshold_breached_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    # Whole NTD dollars (元) accumulated at trigger time
    current_amount_ntd: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
