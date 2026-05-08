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
