/**
 * Frontend TypeScript 型別，對應 backend API schemas。
 */

// -- 共用信封 --

export interface ApiResponse<T> {
  readonly success: boolean
  readonly data: T
  readonly message: string
}

export interface SessionStatus {
  readonly authenticated: boolean
}

export interface PaginationMeta {
  readonly page: number
  readonly page_size: number
  readonly total: number
  readonly total_pages: number
}

export interface PaginatedResponse<T> {
  readonly success: boolean
  readonly data: readonly T[]
  readonly message: string
  readonly pagination: PaginationMeta
}

// -- Overview --

export interface UpcomingBillItem {
  readonly id: number
  readonly bank_code: string
  readonly bank_name: string | null
  readonly billing_month: string
  readonly total_amount: number
  readonly due_date: string
  readonly is_paid: boolean
}

export interface OverviewData {
  readonly month: string
  readonly total_spending: number
  readonly total_paid: number
  readonly total_unpaid: number
  readonly upcoming_bills: readonly UpcomingBillItem[]
}

// -- Transactions --

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

export interface TrendItem {
  readonly month: string
  readonly total: number
}

export interface CategoryItem {
  readonly category: string
  readonly total: number
}

export interface BankItem {
  readonly bank_code: string
  readonly bank_name: string | null
  readonly total: number
}

// -- Bills --

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

export interface BillUpdateRequest {
  readonly is_paid: boolean
}

// -- Settings: Banks --

export interface BankConfigItem {
  readonly id: number
  readonly bank_code: string
  readonly bank_name: string
  readonly gmail_filter: string
  readonly active_parser_version: string
  readonly is_active: boolean
}

export interface BankConfigCreateRequest {
  readonly bank_code: string
  readonly bank_name: string
  readonly gmail_filter: string
  readonly active_parser_version?: string
  readonly is_active?: boolean
}

export interface BankConfigUpdateRequest {
  readonly is_active?: boolean
  readonly active_parser_version?: string
}

// -- Settings: Categories --

export interface CategoryKeywordItem {
  readonly id: number
  readonly keyword: string
  readonly category: string
}

export interface CategoryKeywordCreateRequest {
  readonly keyword: string
  readonly category: string
}

export interface CategoryKeywordUpdateRequest {
  readonly keyword?: string
  readonly category?: string
}
