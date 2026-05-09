/**
 * Insights 頁面（bills-management-and-insights §13）。
 *
 * 取代既有 analytics 頁面，新增銀行對比、年度對比、商家排行、月對月變化、
 * 匯出對話框。
 */
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { apiGet } from '@/lib/api-client'
import type {
  ApiResponse,
  BankCompareItem,
  CategoryWithCompareItem,
  TopMerchantItem,
  TopMerchantPeriod,
  TrendItem,
  YearCompareItem,
  YearMetric,
} from '@/lib/types'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '@/components/shared/states'
import {
  BankComparisonBarChart,
  YearComparisonLineChart,
} from '@/components/comparison-chart'
import { TopMerchantsTable } from '@/components/top-merchants-table'
import { ExportDialog } from '@/components/export-dialog'
import { Button } from '@/components/ui/button'
import {
  FilterBar,
  type FilterBarParams,
  type FilterKey,
} from '@/components/shared/filter-bar'

const TREND_MONTHS_OPTIONS = [6, 12, 24] as const

const currencyFormatter = (
  v: number | string | readonly (number | string)[] | undefined,
) => `$${Number(v).toLocaleString()}`

function CategoryListWithCompare({
  data,
}: {
  readonly data: readonly CategoryWithCompareItem[]
}) {
  if (data.length === 0) return <EmptyState message="尚無類別資料" />
  return (
    <ul className="space-y-1.5 text-sm">
      {data.map((row) => {
        const change = row.change_percent
        const arrow =
          change === null || change === 0
            ? '—'
            : change > 0
              ? `▲${change.toFixed(1)}%`
              : `▼${Math.abs(change).toFixed(1)}%`
        const color =
          change === null || change === 0
            ? 'text-muted-foreground'
            : change > 0
              ? 'text-orange-600'
              : 'text-green-600'
        return (
          <li
            key={row.category}
            className="flex items-center justify-between rounded border border-border px-3 py-2"
          >
            <span className="font-medium">{row.category}</span>
            <span className="flex items-center gap-3">
              <span>${row.total.toLocaleString()}</span>
              <span className={`text-xs ${color}`}>{arrow}</span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function InsightsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const year = searchParams.get('year') ?? ''
  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const trendMonths = Number(searchParams.get('trend_months') ?? '12')
  const yearMetric = (searchParams.get('year_metric') ?? 'total') as YearMetric
  const merchantPeriod = (searchParams.get('merchant_period') ??
    'all') as TopMerchantPeriod
  const merchantLimit = Number(searchParams.get('merchant_limit') ?? '10')

  const [exportOpen, setExportOpen] = useState(false)

  const filterValues: FilterBarParams = {
    year,
    month,
    bank: bankCode,
    status: '',
    category: '',
    q: '',
  }

  function handleFilterChange(key: FilterKey, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      const paramKey = key === 'bank' ? 'bank_code' : key
      if (value) next.set(paramKey, value)
      else next.delete(paramKey)
      return next
    })
  }

  function setSearchParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set(key, value)
      return next
    })
  }

  const trendQuery = useQuery({
    queryKey: ['insights', 'trend', trendMonths],
    queryFn: () =>
      apiGet<ApiResponse<readonly TrendItem[]>>('/api/analytics/trend', {
        months: trendMonths,
      }),
  })

  const banksCompareQuery = useQuery({
    queryKey: ['insights', 'compare-banks', year, month],
    queryFn: () =>
      apiGet<ApiResponse<readonly BankCompareItem[]>>(
        '/api/analytics/compare/banks',
        {
          month: month || undefined,
          year: year ? Number(year) : undefined,
        },
      ),
  })

  const yearsCompareQuery = useQuery({
    queryKey: ['insights', 'compare-years', yearMetric],
    queryFn: () =>
      apiGet<ApiResponse<readonly YearCompareItem[]>>(
        '/api/analytics/compare/years',
        { metric: yearMetric },
      ),
  })

  const merchantsQuery = useQuery({
    queryKey: ['insights', 'top-merchants', merchantLimit, merchantPeriod],
    queryFn: () =>
      apiGet<ApiResponse<readonly TopMerchantItem[]>>(
        '/api/analytics/top-merchants',
        { limit: merchantLimit, period: merchantPeriod },
      ),
  })

  const categoriesCompareQuery = useQuery({
    queryKey: ['insights', 'categories-compare', month],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryWithCompareItem[]>>(
        '/api/analytics/categories',
        {
          month: month || undefined,
          compare_with_previous: month ? true : undefined,
        },
      ),
    enabled: !!month, // requires explicit month for compare to work
  })

  const isLoading =
    trendQuery.isLoading ||
    banksCompareQuery.isLoading ||
    yearsCompareQuery.isLoading ||
    merchantsQuery.isLoading

  const errorMsg =
    trendQuery.error?.message ??
    banksCompareQuery.error?.message ??
    yearsCompareQuery.error?.message ??
    merchantsQuery.error?.message

  if (isLoading) return <LoadingState />
  if (errorMsg) return <ErrorState message={errorMsg} />

  const trend = trendQuery.data?.data ?? []
  const banksCompare = banksCompareQuery.data?.data ?? []
  const yearsCompare = yearsCompareQuery.data?.data ?? []
  const merchants = merchantsQuery.data?.data ?? []
  const categoriesCompare = categoriesCompareQuery.data?.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Insights</h1>
        <div className="flex items-center gap-2">
          <FilterBar
            show={['year', 'month', 'bank']}
            values={filterValues}
            onChange={handleFilterChange}
          />
          <Button onClick={() => setExportOpen(true)} variant="outline" size="sm">
            <Download className="size-4" data-icon="inline-start" />
            匯出
          </Button>
        </div>
      </div>

      <section className="rounded-lg border border-border p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">月消費趨勢</h2>
          <select
            value={trendMonths}
            onChange={(e) => setSearchParam('trend_months', e.target.value)}
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
            <LineChart data={trend as TrendItem[]}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip formatter={currencyFormatter} />
              <Line
                type="monotone"
                dataKey="total"
                stroke="var(--chart-2)"
                strokeWidth={2}
                name="本月支出"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-border p-4">
          <h2 className="mb-4 text-lg font-semibold">銀行對比</h2>
          <BankComparisonBarChart data={banksCompare} />
        </section>

        <section className="rounded-lg border border-border p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">年度對比</h2>
            <select
              value={yearMetric}
              onChange={(e) => setSearchParam('year_metric', e.target.value)}
              className="h-7 rounded border border-input bg-background px-2 text-sm"
              aria-label="年度對比指標"
            >
              <option value="total">金額</option>
              <option value="count">筆數</option>
            </select>
          </div>
          <YearComparisonLineChart
            data={yearsCompare}
            metricLabel={yearMetric === 'total' ? '金額' : '筆數'}
          />
        </section>
      </div>

      <section className="rounded-lg border border-border p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">商家排行</h2>
          <div className="flex items-center gap-2 text-sm">
            <select
              value={merchantPeriod}
              onChange={(e) => setSearchParam('merchant_period', e.target.value)}
              className="h-7 rounded border border-input bg-background px-2"
              aria-label="商家排行期間"
            >
              <option value="all">全部</option>
              <option value="month">當月</option>
              <option value="year">當年</option>
            </select>
            <select
              value={merchantLimit}
              onChange={(e) => setSearchParam('merchant_limit', e.target.value)}
              className="h-7 rounded border border-input bg-background px-2"
              aria-label="商家排行筆數"
            >
              <option value="5">前 5</option>
              <option value="10">前 10</option>
              <option value="20">前 20</option>
            </select>
          </div>
        </div>
        <TopMerchantsTable data={merchants} />
      </section>

      {month && (
        <section className="rounded-lg border border-border p-4">
          <h2 className="mb-4 text-lg font-semibold">
            類別 vs 上月
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {month}
            </span>
          </h2>
          {categoriesCompareQuery.isLoading ? (
            <LoadingState />
          ) : (
            <CategoryListWithCompare data={categoriesCompare} />
          )}
        </section>
      )}

      <ExportDialog isOpen={exportOpen} onClose={() => setExportOpen(false)} />
    </div>
  )
}

export default InsightsPage
