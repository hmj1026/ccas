/**
 * Analytics 頁面 -- 月趨勢、類別分布與銀行比較圖表。
 * 預設：全部資料（不篩選）；年度/月份互斥。
 */
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from 'recharts'
import { apiGet } from '@/lib/api-client'
import type { ApiResponse, TrendItem, CategoryItem, BankItem } from '@/lib/types'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'
import { FilterBar, type FilterBarParams, type FilterKey } from '@/components/shared/filter-bar'

/** Recharts Cell 顏色陣列，對應 CSS 變數 `--chart-1` 至 `--chart-5`。 */
const COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
]

/** 趨勢圖回溯月數選項（近 6 / 12 / 24 個月）。 */
const TREND_MONTHS_OPTIONS = [6, 12, 24] as const

function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const year = searchParams.get('year') ?? ''
  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const trendMonths = Number(searchParams.get('trend_months') ?? '12')

  const filterValues: FilterBarParams = {
    year, month, bankCode, status: '', category: '', q: '',
  }

  /**
   * 篩選列變更 callback；將指定維度寫入 URL search params。
   *
   * @param key - 變更的篩選維度
   * @param value - 新的篩選值，空字串時刪除該參數
   */
  function handleFilterChange(key: FilterKey, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      const paramKey = key === 'bankCode' ? 'bank_code' : key
      if (value) {
        next.set(paramKey, value)
      } else {
        next.delete(paramKey)
      }
      return next
    })
  }

  /**
   * 趨勢圖回溯月數變更 callback；更新 `trend_months` URL 參數。
   *
   * @param value - 選取的月數（字串）
   */
  function handleTrendMonths(value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('trend_months', value)
      return next
    })
  }

  const trendQuery = useQuery({
    queryKey: ['analytics', 'trend', trendMonths],
    queryFn: () =>
      apiGet<ApiResponse<readonly TrendItem[]>>('/api/analytics/trend', {
        months: trendMonths,
      }),
  })

  const categoriesQuery = useQuery({
    queryKey: ['analytics', 'categories', year, month],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryItem[]>>('/api/analytics/categories', {
        month: month || undefined,
        year: year ? Number(year) : undefined,
      }),
  })

  const banksQuery = useQuery({
    queryKey: ['analytics', 'banks', year, month],
    queryFn: () =>
      apiGet<ApiResponse<readonly BankItem[]>>('/api/analytics/banks', {
        month: month || undefined,
        year: year ? Number(year) : undefined,
      }),
  })

  const isLoading =
    trendQuery.isLoading || categoriesQuery.isLoading || banksQuery.isLoading
  const errorMsg =
    trendQuery.error?.message ??
    categoriesQuery.error?.message ??
    banksQuery.error?.message

  if (isLoading) return <LoadingState />
  if (errorMsg) return <ErrorState message={errorMsg} />

  const trend = trendQuery.data?.data ?? []
  const categories = categoriesQuery.data?.data ?? []
  const banks = banksQuery.data?.data ?? []

  const periodLabel = month || (year ? `${year} 年` : '全部')

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">消費分析</h1>
        <FilterBar
          show={['year', 'month', 'bank']}
          values={filterValues}
          onChange={handleFilterChange}
        />
      </div>

      {/* Trend chart */}
      <section className="rounded-lg border border-border p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">月消費趨勢</h2>
          <select
            value={trendMonths}
            onChange={(e) => handleTrendMonths(e.target.value)}
            className="h-7 rounded border border-input bg-background px-2 text-sm"
            aria-label="趨勢回溯月數"
          >
            {TREND_MONTHS_OPTIONS.map((m) => (
              <option key={m} value={m}>
                近 {m} 個月
              </option>
            ))}
          </select>
        </div>
        {trend.length === 0 ? (
          <EmptyState message="尚無趨勢資料" />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={[...trend]}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip formatter={(value) => `$${Number(value).toLocaleString()}`} />
              <Line
                type="monotone"
                dataKey="total"
                stroke="var(--chart-2)"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Category distribution */}
        <section className="rounded-lg border border-border p-4">
          <h2 className="mb-4 text-lg font-semibold">
            類別分布
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {periodLabel}
            </span>
          </h2>
          {categories.length === 0 ? (
            <EmptyState message="尚無類別資料" />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={[...categories]}
                  dataKey="total"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name }) => name}
                >
                  {categories.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => `$${Number(value).toLocaleString()}`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </section>

        {/* Bank comparison */}
        <section className="rounded-lg border border-border p-4">
          <h2 className="mb-4 text-lg font-semibold">
            銀行比較
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {periodLabel}
            </span>
          </h2>
          {banks.length === 0 ? (
            <EmptyState message="尚無銀行資料" />
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={[...banks]}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey={(d: BankItem) => d.bank_name ?? d.bank_code} />
                <YAxis />
                <Tooltip formatter={(value) => `$${Number(value).toLocaleString()}`} />
                <Bar dataKey="total" fill="var(--chart-3)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>
      </div>
    </div>
  )
}

export default AnalyticsPage
