/**
 * FilterBar -- 可組合的篩選列元件。
 *
 * 支援篩選維度：year / month / bank / status / category / search。
 * year 與 month 互斥：選其中一個會自動清除另一個。
 * 所有狀態透過 URL search params 管理，由呼叫端傳入 get/set。
 */
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { apiGet } from '@/lib/api-client'
import type { ApiResponse, BankConfigItem } from '@/lib/types'

/** FilterBar 所有可篩選維度的目前值。 */
export interface FilterBarParams {
  /** 年度篩選，格式為 YYYY，與 month 互斥。 */
  year: string
  /** 月份篩選，格式為 YYYY-MM，與 year 互斥。 */
  month: string
  /** 銀行代碼篩選（BankConfigItem.bank_code）。 */
  bankCode: string
  /** 付款狀態篩選：`"paid"` | `"unpaid"` | `""`（全部）。 */
  status: string
  /** 分類文字篩選。 */
  category: string
  /** 商家名稱關鍵字搜尋。 */
  q: string
}

/** FilterBarParams 的鍵值，用於 onChange callback 指定變更的維度。 */
export type FilterKey = keyof FilterBarParams

interface FilterBarProps {
  /** 要顯示的篩選維度 */
  readonly show: readonly FilterKey[]
  /** 目前的篩選值 */
  readonly values: FilterBarParams
  /** 變更某個維度時的 callback */
  readonly onChange: (key: FilterKey, value: string) => void
  /** 右側附加內容（例如按鈕） */
  readonly extra?: React.ReactNode
}

/**
 * 取得所有有交易資料的年度清單，供年度篩選下拉使用。
 * 快取 5 分鐘，避免頁面切換時重複請求。
 */
function useYears() {
  return useQuery({
    queryKey: ['analytics', 'years'],
    queryFn: () => apiGet<ApiResponse<readonly number[]>>('/api/analytics/years'),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * 取得所有啟用銀行清單，供銀行篩選下拉使用。
 * 快取 5 分鐘，避免頁面切換時重複請求。
 */
function useBanks() {
  return useQuery({
    queryKey: ['settings', 'banks'],
    queryFn: () => apiGet<ApiResponse<readonly BankConfigItem[]>>('/api/settings/banks'),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * 可組合的篩選列，透過 `show` prop 控制要顯示哪些篩選維度。
 *
 * @param show - 要顯示的篩選維度陣列
 * @param values - 目前各維度的篩選值
 * @param onChange - 某維度值變更時的 callback
 * @param extra - 右側附加內容（選填）
 */
export function FilterBar({ show, values, onChange, extra }: FilterBarProps) {
  const { data: yearsData } = useYears()
  const { data: banksData } = useBanks()

  const years = yearsData?.data ?? []
  const banks = banksData?.data ?? []

  /** 選年度時清除月份（year 與 month 互斥）。 */
  function handleYear(value: string) {
    if (value) onChange('month', '')
    onChange('year', value)
  }

  /** 選月份時清除年度（month 與 year 互斥）。 */
  function handleMonth(value: string) {
    if (value) onChange('year', '')
    onChange('month', value)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {show.includes('year') && (
        <select
          value={values.year}
          onChange={(e) => handleYear(e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="年度篩選"
        >
          <option value="">全部年度</option>
          {years.map((y) => (
            <option key={y} value={String(y)}>
              {y} 年
            </option>
          ))}
        </select>
      )}

      {show.includes('month') && (
        <input
          type="month"
          value={values.month}
          onChange={(e) => handleMonth(e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="月份篩選"
        />
      )}

      {show.includes('bank') && (
        <select
          value={values.bankCode}
          onChange={(e) => onChange('bankCode', e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="銀行篩選"
        >
          <option value="">全部銀行</option>
          {banks.map((b) => (
            <option key={b.bank_code} value={b.bank_code}>
              {b.bank_name}
            </option>
          ))}
        </select>
      )}

      {show.includes('status') && (
        <select
          value={values.status}
          onChange={(e) => onChange('status', e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="付款狀態篩選"
        >
          <option value="">全部</option>
          <option value="paid">已繳</option>
          <option value="unpaid">未繳</option>
        </select>
      )}

      {show.includes('category') && (
        <input
          type="text"
          placeholder="分類"
          value={values.category}
          onChange={(e) => onChange('category', e.target.value)}
          className="h-8 w-28 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="分類篩選"
        />
      )}

      {show.includes('q') && (
        <div className="relative">
          <Search className="absolute left-2.5 top-2 size-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜尋商家..."
            value={values.q}
            onChange={(e) => onChange('q', e.target.value)}
            className="h-8 w-44 rounded-lg border border-input bg-background pl-8 pr-3 text-sm"
            aria-label="商家搜尋"
          />
        </div>
      )}

      {extra && <div className="ml-auto flex items-center gap-2">{extra}</div>}
    </div>
  )
}
