/**
 * FilterBar -- 可組合的篩選列元件。
 *
 * 支援篩選維度：year / month / bank / status / category / search。
 * year 與 month 互斥：選其中一個會自動清除另一個。
 * 所有狀態透過 URL search params 管理，由呼叫端傳入 get/set。
 */
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { apiGet } from '@/lib/api-client'
import type {
  ApiResponse,
  BankConfigItem,
  CategoryKeywordItem,
} from '@/lib/types'

/** FilterBar 所有可篩選維度的目前值。 */
export interface FilterBarParams {
  /** 年度篩選，格式為 YYYY，與 month 互斥。 */
  year: string
  /** 月份篩選，格式為 YYYY-MM，與 year 互斥。 */
  month: string
  /** 銀行代碼篩選（BankConfigItem.bank_code）。 */
  bank: string
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
 * 取得分類關鍵字清單，供分類篩選下拉使用。
 * 與其他頁面共用同一 cache key（`['settings', 'categories']`），避免重複請求。
 * 快取 5 分鐘，cache-key 風格對齊 useBanks()。
 */
function useCategories() {
  return useQuery({
    queryKey: ['settings', 'categories'],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryKeywordItem[]>>(
        '/api/settings/categories',
      ),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * 延遲提交的文字輸入。
 * 本地即時更新，blur 或 Enter 時才觸發 onCommit，避免每次 keystroke 觸發 API 查詢。
 * 外部 value 變更（例如 URL params 重置）時自動同步。
 *
 * `minCommitLength`：非空值需達此長度才提交，避免送出後端會以 422 拒絕的過短查詢
 * （例如交易搜尋 q 的 min_length=2）。空字串永遠允許提交（用於清除篩選）。
 */
function DebouncedInput({
  value: externalValue,
  onCommit,
  minCommitLength = 0,
  ...rest
}: Omit<React.ComponentProps<'input'>, 'onChange' | 'onBlur' | 'onKeyDown' | 'value'> & {
  readonly value: string
  readonly onCommit: (value: string) => void
  readonly minCommitLength?: number
}) {
  const [localValue, setLocalValue] = useState(externalValue)
  const [prevExternalValue, setPrevExternalValue] = useState(externalValue)
  const committedRef = useRef(externalValue)

  if (externalValue !== prevExternalValue) {
    setPrevExternalValue(externalValue)
    setLocalValue(externalValue)
  }

  useEffect(() => {
    committedRef.current = externalValue
  }, [externalValue])

  function commit() {
    const trimmed = localValue.trim()
    // 非空但未達門檻時不提交，避免觸發後端 422（空值放行以清除篩選）。
    if (trimmed && trimmed.length < minCommitLength) return
    if (trimmed !== committedRef.current) {
      committedRef.current = trimmed
      onCommit(trimmed)
    }
  }

  return (
    <input
      {...rest}
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
      }}
    />
  )
}

/**
 * 可組合的篩選列，透過 `show` prop 控制要顯示哪些篩選維度。
 *
 * 已用 React.memo 包裹：只要呼叫端把 `show` (module-level const)、
 * `values` (useMemo)、`onChange` (useFilterParams) 維持 referential stability，
 * 父頁面 state 變動時即可跳過整個子樹重渲染。
 *
 * @param show - 要顯示的篩選維度陣列
 * @param values - 目前各維度的篩選值
 * @param onChange - 某維度值變更時的 callback
 * @param extra - 右側附加內容（選填）
 */
export const FilterBar = memo(function FilterBar({ show, values, onChange, extra }: FilterBarProps) {
  const { data: yearsData } = useYears()
  const { data: banksData } = useBanks()
  const showCategory = show.includes('category')
  const { data: categoriesData } = useCategories()

  const years = yearsData?.data ?? []
  const banks = banksData?.data ?? []
  // 後端回傳 keyword→category 映射（多 keyword 可對同一 category），
  // 去重成不重複的 category 名稱清單供下拉使用。
  const categories = useMemo(
    () => Array.from(new Set((categoriesData?.data ?? []).map((c) => c.category))),
    [categoriesData],
  )

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
          value={values.bank}
          onChange={(e) => onChange('bank', e.target.value)}
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

      {showCategory && (
        <select
          value={values.category}
          onChange={(e) => onChange('category', e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="分類篩選"
        >
          <option value="">全部分類</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      )}

      {show.includes('q') && (
        <div className="relative">
          <Search className="absolute left-2.5 top-2 size-4 text-muted-foreground" />
          <DebouncedInput
            type="text"
            placeholder="搜尋商家..."
            value={values.q}
            onCommit={(v) => onChange('q', v)}
            minCommitLength={2}
            className="h-8 w-44 rounded-lg border border-input bg-background pl-8 pr-3 text-sm"
            aria-label="商家搜尋"
          />
        </div>
      )}

      {extra && <div className="ml-auto flex items-center gap-2">{extra}</div>}
    </div>
  )
})
