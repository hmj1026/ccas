/**
 * Analytics 頁面 -- 月趨勢、類別分布與銀行比較圖表。
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

const COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
]

function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const month = searchParams.get('month') ?? ''

  const trendQuery = useQuery({
    queryKey: ['analytics', 'trend'],
    queryFn: () =>
      apiGet<ApiResponse<readonly TrendItem[]>>('/api/analytics/trend', {
        months: 6,
      }),
  })

  const categoriesQuery = useQuery({
    queryKey: ['analytics', 'categories', month],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryItem[]>>('/api/analytics/categories', {
        month: month || undefined,
      }),
  })

  const banksQuery = useQuery({
    queryKey: ['analytics', 'banks', month],
    queryFn: () =>
      apiGet<ApiResponse<readonly BankItem[]>>('/api/analytics/banks', {
        month: month || undefined,
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">消費分析</h1>
        <input
          type="month"
          value={month}
          onChange={(e) =>
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev)
              if (e.target.value) {
                next.set('month', e.target.value)
              } else {
                next.delete('month')
              }
              return next
            })
          }
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="月份篩選"
        />
      </div>

      {/* Trend chart */}
      <section className="rounded-lg border border-border p-4">
        <h2 className="mb-4 text-lg font-semibold">月消費趨勢</h2>
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
          <h2 className="mb-4 text-lg font-semibold">類別分布</h2>
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
          <h2 className="mb-4 text-lg font-semibold">銀行比較</h2>
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
