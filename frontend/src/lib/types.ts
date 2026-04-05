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
