/**
 * Frontend TypeScript 型別，對應 backend API schemas。
 */

// -- 共用信封 --

/** API 統一回應信封，所有端點均回傳此結構。 */
export interface ApiResponse<T> {
  readonly success: boolean
  readonly data: T
  readonly message: string
}

/** 瀏覽器 session 驗證狀態。 */
export interface SessionStatus {
  readonly authenticated: boolean
}

/** 分頁中繼資料，附帶於分頁列表回應中。 */
export interface PaginationMeta {
  readonly page: number
  readonly page_size: number
  readonly total: number
  readonly total_pages: number
}

/** 帶分頁資訊的 API 回應信封。 */
export interface PaginatedResponse<T> {
  readonly success: boolean
  readonly data: readonly T[]
  readonly message: string
  readonly pagination: PaginationMeta
}

// -- Overview --

/** 即將到期帳單摘要，用於總覽頁提醒區塊。 */
export interface UpcomingBillItem {
  readonly id: number
  readonly bank_code: string
  readonly bank_name: string | null
  readonly billing_month: string
  readonly total_amount: number
  readonly due_date: string
  readonly is_paid: boolean
}

/** 總覽頁資料結構，包含本月消費統計與即將到期帳單。 */
export interface OverviewData {
  readonly month: string
  readonly total_spending: number
  readonly total_paid: number
  readonly total_unpaid: number
  readonly upcoming_bills: readonly UpcomingBillItem[]
}

// -- Transactions --

/** 單筆信用卡交易明細。 */
export interface TransactionItem {
  readonly id: number
  readonly bill_id: number
  readonly trans_date: string
  readonly posting_date: string | null
  readonly merchant: string
  readonly amount: number
  readonly currency: string
  readonly original_amount: number | null
  readonly card_last4: string | null
  readonly category: string | null
  readonly bank_code: string
  readonly billing_month: string
}

/**
 * 交易詳情（bills-management-and-insights §3 / §9）。
 * 在 ``TransactionItem`` 上加上使用者編輯欄位。
 */
export interface TransactionDetailItem extends TransactionItem {
  readonly note: string | null
  readonly manual_category_override: boolean
  readonly tags: readonly string[]
  readonly merchant_alias: string
  readonly updated_at: string
}

/** ``PUT /api/transactions/{id}`` request body（所有欄位皆可選）。 */
export interface TransactionUpdateRequest {
  readonly category_id?: number
  readonly note?: string
  readonly tags?: readonly string[]
  readonly merchant_alias?: string
}

// -- Analytics --

/** 月消費趨勢資料點，用於折線圖。 */
export interface TrendItem {
  readonly month: string
  readonly total: number
}

/** 類別消費統計，用於圓餅圖分布。 */
export interface CategoryItem {
  readonly category: string
  readonly total: number
}

/** 銀行消費統計，用於長條圖比較。 */
export interface BankItem {
  readonly bank_code: string
  readonly bank_name: string | null
  readonly total: number
}

// -- Bills --

/** 帳單記錄，包含付款狀態與 PDF 連結。 */
export interface BillItem {
  readonly id: number
  readonly bank_code: string
  readonly bank_name: string | null
  readonly billing_month: string
  readonly total_amount: number
  readonly due_date: string
  readonly is_paid: boolean
  readonly pdf_url: string | null
  readonly created_at: string
}

/** 帳單付款狀態更新請求。 */
export interface BillUpdateRequest {
  readonly is_paid: boolean
}

// -- Staged Attachments --

/**
 * Staged 附件狀態值（對應後端 StagedAttachmentStatus enum）。
 * - staged / decrypted / parsed：pipeline 進行中或已完成
 * - decrypt_failed：解密失敗（密碼錯誤 / 檔案異常）
 * - parse_skipped：零結帳單，預期不解析
 * - parse_failed：解析失敗（需人工介入）
 * - manual_review_needed：pipeline 偵測到需人工介入
 * - failed：下載 / ingest 失敗（可重試）
 * - fetch_expired：下載連結已一次性使用過期（不可自動重試）
 */
export type StagedAttachmentStatus =
  | 'staged'
  | 'decrypted'
  | 'decrypt_failed'
  | 'parsed'
  | 'parse_skipped'
  | 'parse_failed'
  | 'manual_review_needed'
  | 'failed'
  | 'fetch_expired'

/** Gmail staging 附件狀態，用於呈現異常 / 過期下載。 */
export interface StagedAttachmentItem {
  readonly id: number
  readonly bank_code: string
  readonly bank_name: string | null
  readonly status: StagedAttachmentStatus
  readonly original_filename: string
  readonly message_date: string
  readonly error_reason: string | null
  readonly source_type: string
  readonly created_at: string
}

// -- Settings: Banks --

/** 銀行設定，包含 Gmail 篩選條件與 parser 版本。 */
export interface BankConfigItem {
  readonly id: number
  readonly bank_code: string
  readonly bank_name: string
  readonly gmail_filter: string
  readonly active_parser_version: string
  readonly is_active: boolean
}

/** 新增銀行設定請求。 */
export interface BankConfigCreateRequest {
  readonly bank_code: string
  readonly bank_name: string
  readonly gmail_filter: string
  readonly active_parser_version?: string
  readonly is_active?: boolean
}

/** 更新銀行設定請求（部分更新）。 */
export interface BankConfigUpdateRequest {
  readonly is_active?: boolean
  readonly active_parser_version?: string
}

// -- Settings: Categories --

/** 分類關鍵字規則，用於交易自動分類。 */
export interface CategoryKeywordItem {
  readonly id: number
  readonly keyword: string
  readonly category: string
}

/** 新增分類關鍵字請求。 */
export interface CategoryKeywordCreateRequest {
  readonly keyword: string
  readonly category: string
}

/** 更新分類關鍵字請求（部分更新）。 */
export interface CategoryKeywordUpdateRequest {
  readonly keyword?: string
  readonly category?: string
}

// -- Pipeline Operations --

/** Pipeline 階段名稱。 */
export type PipelineStage = 'ingest' | 'decrypt' | 'parse' | 'classify' | 'notify'

/** Pipeline 執行狀態。 */
export type PipelineRunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

/** Pipeline 觸發請求參數。 */
export interface PipelineTriggerRequest {
  readonly force?: boolean
  readonly bank_code?: string | null
  readonly year?: number | null
  readonly month?: number | null
  readonly from_stage?: PipelineStage | null
  readonly to_stage?: PipelineStage | null
}

/** Pipeline 觸發回應資料。 */
export interface PipelineTriggerData {
  readonly job_id: string
  readonly run_id: string
}

/** Pipeline 單一階段摘要。 */
export interface PipelineStageEntry {
  readonly stage: PipelineStage | string
  readonly ok: number
  readonly fail: number
  readonly elapsed_ms: number
  readonly counts?: Readonly<Record<string, number>>
  readonly errors?: readonly string[]
}

/** Pipeline 執行紀錄列表項目。 */
export interface PipelineRunSummary {
  readonly id: string
  readonly job_id: string
  readonly status: PipelineRunStatus
  readonly triggered_by: string
  readonly params: PipelineTriggerRequest
  readonly current_stage: PipelineStage | string | null
  readonly current_stage_processed: number
  readonly current_stage_total: number
  readonly stage_summary: readonly PipelineStageEntry[]
  readonly error_message: string | null
  readonly started_at: string | null
  readonly completed_at: string | null
  readonly created_at: string
  readonly updated_at: string
}

/** Pipeline 執行紀錄詳情。 */
export type PipelineRunDetail = PipelineRunSummary

// -- Reminders (bills-management-and-insights §5) --

/** 通知管道。 */
export type ReminderChannel = 'telegram' | 'ui_banner' | 'both'

/** 單張帳單的提醒設定 + 帳單摘要（給設定頁列表用）。 */
export interface ReminderSettingItem {
  readonly bill_id: number
  readonly bank_code: string
  readonly bank_name: string | null
  readonly billing_month: string
  readonly due_date: string
  readonly is_paid: boolean
  readonly enabled: boolean
  readonly days_before: readonly number[]
  readonly channel: ReminderChannel
  readonly has_setting: boolean
}

/** Update reminder setting request (partial)。 */
export interface ReminderSettingUpdateRequest {
  readonly enabled?: boolean
  readonly days_before?: readonly number[]
  readonly channel?: ReminderChannel
}

/** 測試推送結果。 */
export interface ReminderTestResult {
  readonly sent: boolean
  readonly channel: ReminderChannel
  readonly detail: string
}

// -- Budgets (bills-management-and-insights §6) --

/** 預算範圍。 */
export type BudgetScope = 'monthly_total' | 'monthly_category' | 'monthly_bank'

/** 單筆預算設定。 */
export interface BudgetItem {
  readonly id: number
  readonly scope: BudgetScope
  readonly scope_ref: string | null
  readonly amount_ntd: number
  readonly alert_threshold_percent: number
  readonly enabled: boolean
  readonly created_at: string
  readonly updated_at: string
}

/** Create budget request。 */
export interface BudgetCreateRequest {
  readonly scope: BudgetScope
  readonly scope_ref?: string | null
  readonly amount_ntd: number
  readonly alert_threshold_percent?: number
  readonly enabled?: boolean
}

/** Update budget request (partial)。 */
export interface BudgetUpdateRequest {
  readonly scope?: BudgetScope
  readonly scope_ref?: string | null
  readonly amount_ntd?: number
  readonly alert_threshold_percent?: number
  readonly enabled?: boolean
}

/** 當月累計花費 + threshold 狀態。 */
export interface BudgetCurrentPeriod {
  readonly budget_id: number
  readonly period_year_month: string
  readonly amount_ntd: number
  readonly current_amount_ntd: number
  readonly percent: number
  readonly threshold_breached: boolean
  readonly alert_threshold_percent: number
}

/** active 預算超支警示（給 banner 用）。 */
export interface BudgetAlertItem {
  readonly id: number
  readonly budget_id: number
  readonly scope: BudgetScope
  readonly scope_ref: string | null
  readonly period_year_month: string
  readonly threshold_breached_percent: number
  readonly current_amount_ntd: number
  readonly amount_ntd: number
  readonly triggered_at: string
  readonly acknowledged_at: string | null
}

// -- Insights v2 (bills-management-and-insights §7) --

/** 銀行對比 (`/api/analytics/compare/banks`)。 */
export interface BankCompareItem {
  readonly bank_code: string
  readonly bank_name: string | null
  readonly total: number
}

/** 年度對比 (`/api/analytics/compare/years`)。 */
export interface YearCompareItem {
  readonly year: number
  readonly value: number
}

/** Top merchant 排行 (`/api/analytics/top-merchants`)。 */
export interface TopMerchantItem {
  readonly merchant: string
  readonly total: number
  readonly count: number
}

/** Category with month-over-month compare (`compare_with_previous=true`)。 */
export interface CategoryWithCompareItem {
  readonly category: string
  readonly total: number
  readonly previous_total: number | null
  readonly change_percent: number | null
}

export type YearMetric = 'total' | 'count'
export type TopMerchantPeriod = 'year' | 'month' | 'all'
export type ExportFormat = 'csv' | 'xlsx'

// -- User classification rules (bills-management-and-insights §4 §10) --

export type PatternType = 'keyword' | 'exact' | 'regex'

export interface ClassificationRuleItem {
  readonly id: number
  readonly pattern: string
  readonly pattern_type: PatternType
  readonly category_id: number
  readonly category_name: string
  readonly priority: number
  readonly enabled: boolean
  readonly created_at: string
  readonly updated_at: string
}

export interface ClassificationRuleCreateRequest {
  readonly pattern: string
  readonly pattern_type: PatternType
  readonly category_id: number
  readonly priority?: number
  readonly enabled?: boolean
}

export interface ClassificationRuleUpdateRequest {
  readonly pattern?: string
  readonly pattern_type?: PatternType
  readonly category_id?: number
  readonly priority?: number
  readonly enabled?: boolean
}

export interface ClassificationRuleTestRequest {
  readonly pattern: string
  readonly pattern_type: PatternType
  readonly sample_text: string
}

export interface ClassificationRuleTestResponse {
  readonly matches: boolean
}
