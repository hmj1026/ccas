"""API 回應與請求的 Pydantic Schema。

定義所有 API 端點的 request/response 模型，
統一使用 ``ApiResponse`` 信封格式。
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

StagedAttachmentStatusLiteral = Literal[
    "staged",
    "decrypted",
    "parsed",
    "parse_skipped",
    "parse_failed",
    "failed",
    "fetch_expired",
]
PipelineRunStatusLiteral = Literal[
    "queued", "running", "succeeded", "failed", "cancelled"
]
PipelineStageLiteral = Literal["ingest", "decrypt", "parse", "classify", "notify"]

# -- 共用信封 --


class ApiResponse[T](BaseModel):
    """統一 API 回應信封。"""

    success: bool = True
    data: T
    message: str = ""


class PaginationMeta(BaseModel):
    """分頁 metadata。"""

    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedResponse[T](BaseModel):
    """含分頁的 API 回應信封。"""

    success: bool = True
    data: list[T]
    message: str = ""
    pagination: PaginationMeta


class ErrorResponse(BaseModel):
    """錯誤回應。"""

    success: bool = False
    message: str
    data: None = None


class SessionLoginRequest(BaseModel):
    """建立瀏覽器 session 的登入請求。"""

    token: str = Field(min_length=1)


class SessionStatus(BaseModel):
    """目前 session 驗證狀態。"""

    authenticated: bool


# -- Overview --


class UpcomingBillItem(BaseModel):
    """即將到期帳單摘要。"""

    id: int
    bank_code: str
    bank_name: str | None = None
    billing_month: str
    total_amount: int
    due_date: date
    is_paid: bool


class OverviewData(BaseModel):
    """Overview 摘要資料。"""

    month: str
    total_spending: int
    total_paid: int
    total_unpaid: int
    upcoming_bills: list[UpcomingBillItem]


# -- Transactions --


class TransactionItem(BaseModel):
    """交易明細。"""

    id: int
    bill_id: int
    trans_date: date
    posting_date: date | None
    merchant: str
    amount: int
    currency: str
    original_amount: int | None
    card_last4: str | None
    category: str | None
    bank_code: str
    billing_month: str


class TransactionDetailItem(TransactionItem):
    """交易詳情（bills-management-and-insights §3 / §9）含使用者編輯欄位。"""

    note: str | None
    manual_category_override: bool
    tags: list[str]
    merchant_alias: str
    updated_at: datetime


class TransactionUpdateRequest(BaseModel):
    """``PUT /api/transactions/{id}`` request body（所有欄位皆可選）。

    若提供 ``category_id`` 則同步設 ``manual_category_override = true``。

    長度上限為 defense-in-depth，避免 token 洩漏後寫入過大內容打爆 DB／UI。
    """

    category_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=50)
    merchant_alias: str | None = Field(default=None, max_length=200)


class TransactionNoteRequest(BaseModel):
    """``POST /api/transactions/{id}/note`` request body。"""

    note: str = Field(default="", max_length=2000)


# -- Analytics --


class TrendItem(BaseModel):
    """月趨勢資料點。"""

    month: str
    total: int


class CategoryItem(BaseModel):
    """類別分布項目。"""

    category: str
    total: int


class BankItem(BaseModel):
    """銀行比較項目。"""

    bank_code: str
    bank_name: str | None = None
    total: int


# -- Bills --


class BillItem(BaseModel):
    """帳單資料。"""

    id: int
    bank_code: str
    bank_name: str | None = None
    billing_month: str
    total_amount: int
    due_date: date
    is_paid: bool
    pdf_url: str | None
    created_at: datetime


class BillUpdateRequest(BaseModel):
    """帳單更新請求。"""

    is_paid: bool


# -- Staged Attachments --


class StagedAttachmentItem(BaseModel):
    """Gmail staging 附件處理狀態。

    暴露給前端的欄位刻意排除 ``staged_path`` 與 ``gmail_attachment_id``／
    ``gmail_part_id`` 等內部識別/檔案系統資訊，只保留足以在 UI 呈現
    附件狀態與原因所需的欄位。
    """

    id: int
    bank_code: str
    bank_name: str | None = None
    status: StagedAttachmentStatusLiteral
    original_filename: str
    message_date: datetime
    error_reason: str | None
    source_type: str
    created_at: datetime


# -- Settings: Banks --


class BankConfigItem(BaseModel):
    """銀行設定（不含 pdf_password_rule）。"""

    id: int
    bank_code: str
    bank_name: str
    gmail_filter: str
    active_parser_version: str
    is_active: bool


class BankConfigCreateRequest(BaseModel):
    """新增銀行設定請求。"""

    bank_code: str
    bank_name: str
    gmail_filter: str
    active_parser_version: str = "v1"
    is_active: bool = True


class BankConfigUpdateRequest(BaseModel):
    """更新銀行設定請求。"""

    is_active: bool | None = None
    active_parser_version: str | None = None


# -- Settings: Categories --


class CategoryKeywordItem(BaseModel):
    """分類關鍵字。"""

    id: int
    keyword: str
    category: str


class CategoryKeywordCreateRequest(BaseModel):
    """新增分類關鍵字請求。"""

    keyword: str = Field(min_length=1)
    category: str = Field(min_length=1)


class CategoryKeywordUpdateRequest(BaseModel):
    """更新分類關鍵字請求。"""

    keyword: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)


class PipelineTriggerRequest(BaseModel):
    """Pipeline 觸發請求參數。"""

    force: bool = False
    bank_code: str | None = None
    year: int | None = Field(default=None, ge=2000, le=2099)
    month: int | None = Field(default=None, ge=1, le=12)
    from_stage: PipelineStageLiteral | None = None
    to_stage: PipelineStageLiteral | None = None


class PipelineTriggerData(BaseModel):
    """Pipeline 觸發回應資料。"""

    job_id: str
    run_id: str


class PipelineStageEntry(BaseModel):
    """Pipeline 階段進度摘要。"""

    stage: str
    ok: int
    fail: int
    elapsed_ms: int
    counts: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class PipelineRunSummary(BaseModel):
    """Pipeline 執行紀錄列表項目。"""

    id: str
    job_id: str
    status: PipelineRunStatusLiteral
    triggered_by: str
    params: dict
    current_stage: str | None
    current_stage_processed: int
    current_stage_total: int
    stage_summary: list[PipelineStageEntry]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PipelineRunDetail(PipelineRunSummary):
    """Pipeline 執行紀錄詳情。"""


# -- Setup: Gmail OAuth Web flow --


class GmailCredentialsUploadResult(BaseModel):
    """credentials.json 上傳結果。"""

    saved_path: str
    client_id_last8: str  # 末 8 字元，用於 UI 顯示提示，不洩漏完整 ID


class GmailAuthorizeUrl(BaseModel):
    """OAuth authorize URL 與 state（前端跳轉用）。"""

    authorize_url: str
    state: str


class GmailConnectionStatus(BaseModel):
    """Gmail 連線狀態（不含 access token 本體）。"""

    connected: bool
    email: str | None = None
    granted_scopes: list[str] = []


# -- Setup: Bank management UI --


class SetupBankItem(BaseModel):
    """設定中心列表項：合併 ``bank_configs`` metadata 與 ``bank_settings`` 偏好。"""

    code: str
    display_name: str | None = None
    enabled: bool
    has_settings_row: bool
    metadata_missing: bool
    total_pdfs: int = 0
    last_ingest_at: datetime | None = None


class BankSettingsUpdateRequest(BaseModel):
    """``PUT /api/setup/banks/{code}`` request body。"""

    enabled: bool
    display_name: str | None = Field(default=None, max_length=128)
    notes: str | None = None


# -- Setup: PDF secrets management --

PdfSecretSource = Literal["db", "env", "none"]


class BankSecretStatus(BaseModel):
    """每銀行 PDF 密碼來源狀態（不含明文）。"""

    bank_code: str
    has_db_secret: bool
    has_env_secret: bool
    effective_source: PdfSecretSource


class BankSecretWriteRequest(BaseModel):
    """``PUT /api/setup/secrets/{code}`` request body。"""

    password: str = Field(min_length=1)


class BankSecretWriteResult(BaseModel):
    """``PUT /api/setup/secrets/{code}`` response（不回明文）。"""

    bank_code: str
    effective_source: PdfSecretSource


class ImportFromEnvResult(BaseModel):
    """``POST /api/setup/secrets/import-from-env`` 結果摘要。"""

    imported: int
    skipped_already_in_db: int
    bank_codes_imported: list[str] = []


# -- Setup: Admin token rotate --


class AdminTokenInfo(BaseModel):
    """``GET /api/setup/admin/token-info`` response（不洩漏完整 token）。"""

    last4: str
    created_at: datetime | None = None
    version: int


class AdminTokenRotateResult(BaseModel):
    """``POST /api/setup/admin/token-rotate`` response（一次性回傳新 token 明文）。"""

    token: str
    version: int
    last4: str


# -- bills-management-and-insights §4: User classification rules ---------------

PatternTypeLiteral = Literal["keyword", "exact", "regex"]


class ClassificationRuleItem(BaseModel):
    """單筆使用者自訂分類規則（含對應 category 名稱）。"""

    id: int
    pattern: str
    pattern_type: PatternTypeLiteral
    category_id: int
    category_name: str
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ClassificationRuleCreateRequest(BaseModel):
    """``POST /api/rules`` request body。"""

    pattern: str = Field(min_length=1)
    pattern_type: PatternTypeLiteral
    category_id: int = Field(ge=1)
    priority: int = Field(default=0)
    enabled: bool = Field(default=True)


class ClassificationRuleUpdateRequest(BaseModel):
    """``PUT /api/rules/{id}`` request body（所有欄位皆可選）。"""

    pattern: str | None = Field(default=None, min_length=1)
    pattern_type: PatternTypeLiteral | None = None
    category_id: int | None = Field(default=None, ge=1)
    priority: int | None = None
    enabled: bool | None = None


class ClassificationRuleTestRequest(BaseModel):
    """``POST /api/rules/test`` request body（即時 UI 預覽用）。"""

    pattern: str = Field(min_length=1)
    pattern_type: PatternTypeLiteral
    sample_text: str


class ClassificationRuleTestResponse(BaseModel):
    """``POST /api/rules/test`` response。"""

    matches: bool


# -- bills-management-and-insights §5: Reminder settings ----------------------

ReminderChannelLiteral = Literal["telegram", "ui_banner", "both"]


class ReminderSettingItem(BaseModel):
    """單張帳單的提醒設定 + 帳單摘要（給設定頁列表用）。"""

    bill_id: int
    bank_code: str
    bank_name: str | None = None
    billing_month: str
    due_date: date
    is_paid: bool
    enabled: bool
    days_before: list[int]
    channel: ReminderChannelLiteral
    has_setting: bool


class ReminderSettingUpdateRequest(BaseModel):
    """``PUT /api/reminders/{bill_id}/settings`` request body（all optional）。"""

    enabled: bool | None = None
    days_before: list[int] | None = Field(default=None, max_length=10)
    channel: ReminderChannelLiteral | None = None


class ReminderTestResult(BaseModel):
    """``POST /api/reminders/{bill_id}/test`` response。"""

    sent: bool
    channel: ReminderChannelLiteral
    detail: str = ""


# -- bills-management-and-insights §6: Budgets --------------------------------

BudgetScopeLiteral = Literal["monthly_total", "monthly_category", "monthly_bank"]


class BudgetItem(BaseModel):
    """單筆預算設定。"""

    id: int
    scope: BudgetScopeLiteral
    scope_ref: str | None
    amount_minor_units: int
    alert_threshold_percent: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class BudgetCreateRequest(BaseModel):
    """``POST /api/budgets`` request body。"""

    scope: BudgetScopeLiteral
    scope_ref: str | None = Field(default=None, max_length=64)
    amount_minor_units: int = Field(ge=1)
    alert_threshold_percent: int = Field(default=80, ge=1, le=100)
    enabled: bool = Field(default=True)


class BudgetUpdateRequest(BaseModel):
    """``PUT /api/budgets/{id}`` request body（all optional）。"""

    scope: BudgetScopeLiteral | None = None
    scope_ref: str | None = Field(default=None, max_length=64)
    amount_minor_units: int | None = Field(default=None, ge=1)
    alert_threshold_percent: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None


class BudgetCurrentPeriod(BaseModel):
    """``GET /api/budgets/{id}/current-period`` response。"""

    budget_id: int
    period_year_month: str
    amount_minor_units: int
    current_amount_minor_units: int
    percent: float
    threshold_breached: bool
    alert_threshold_percent: int


class BudgetAlertItem(BaseModel):
    """active 預算超支警示（給 banner / dashboard 用）。"""

    id: int
    budget_id: int
    scope: BudgetScopeLiteral
    scope_ref: str | None
    period_year_month: str
    threshold_breached_percent: int
    current_amount_minor_units: int
    amount_minor_units: int
    triggered_at: datetime
    acknowledged_at: datetime | None


# -- bills-management-and-insights §7: Insights v2 -----------------------------


class BankCompareItem(BaseModel):
    """``/api/analytics/compare/banks`` 單筆。"""

    bank_code: str
    bank_name: str | None = None
    total: int


class YearCompareItem(BaseModel):
    """``/api/analytics/compare/years`` 單筆。"""

    year: int
    value: int  # total or count, depending on metric


class TopMerchantItem(BaseModel):
    """``/api/analytics/top-merchants`` 單筆。"""

    merchant: str
    total: int
    count: int


class CategoryWithCompareItem(BaseModel):
    """``/api/analytics/categories?compare_with_previous=true`` 單筆。"""

    category: str
    total: int
    previous_total: int | None = None
    change_percent: float | None = None


YearMetricLiteral = Literal["total", "count"]
TopMerchantPeriodLiteral = Literal["year", "month", "all"]


# -- bills-management-and-insights §8: Exports ---------------------------------

ExportFormatLiteral = Literal["csv", "xlsx"]
