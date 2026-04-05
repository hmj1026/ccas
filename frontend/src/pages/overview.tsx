/**
 * Overview 頁面 -- 本月總覽與即將到期帳單。
 * 預設顯示當月（API 端 fallback：當月無資料則最近有資料月份）。
 */
import { useQuery } from '@tanstack/react-query'
import { CalendarClock, CreditCard, CheckCircle, AlertCircle } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { apiGet } from '@/lib/api-client'
import type { ApiResponse, OverviewData } from '@/lib/types'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'
import { FilterBar, type FilterBarParams, type FilterKey } from '@/components/shared/filter-bar'

/**
 * 將數字金額格式化為帶千分位的新台幣字串。
 *
 * @param amount - 金額（整數，單位 TWD）
 * @returns 格式化字串，例如 `$1,234`
 */
function formatAmount(amount: number): string {
  return `$${amount.toLocaleString()}`
}

function OverviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const month = searchParams.get('month') ?? ''

  const filterValues: FilterBarParams = {
    year: '', month, bankCode: '', status: '', category: '', q: '',
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
      if (value) {
        next.set(key === 'bankCode' ? 'bank_code' : key, value)
      } else {
        next.delete(key === 'bankCode' ? 'bank_code' : key)
      }
      return next
    })
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['overview', month],
    queryFn: () =>
      apiGet<ApiResponse<OverviewData>>('/api/overview', {
        month: month || undefined,
      }),
  })

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState message={error.message} />
  if (!data?.data) return <EmptyState message="尚無本月資料" />

  const overview = data.data

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{overview.month} 總覽</h1>
        <FilterBar
          show={['month']}
          values={filterValues}
          onChange={handleFilterChange}
        />
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          icon={<CreditCard className="size-5 text-muted-foreground" />}
          label="總消費"
          value={formatAmount(overview.total_spending)}
        />
        <SummaryCard
          icon={<CheckCircle className="size-5 text-green-600" />}
          label="已繳"
          value={formatAmount(overview.total_paid)}
        />
        <SummaryCard
          icon={<AlertCircle className="size-5 text-orange-500" />}
          label="未繳"
          value={formatAmount(overview.total_unpaid)}
        />
      </div>

      {/* Upcoming bills */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">即將到期帳單</h2>
        {overview.upcoming_bills.length === 0 ? (
          <EmptyState message="沒有即將到期的帳單" />
        ) : (
          <div className="space-y-2">
            {overview.upcoming_bills.map((bill) => (
              <div
                key={bill.id}
                className="flex items-center justify-between rounded-lg border border-border p-3"
              >
                <div className="flex items-center gap-3">
                  <CalendarClock className="size-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">
                      {bill.bank_name ?? bill.bank_code}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      到期日: {bill.due_date}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold">
                    {formatAmount(bill.total_amount)}
                  </p>
                  <p
                    className={`text-xs ${
                      bill.is_paid ? 'text-green-600' : 'text-orange-500'
                    }`}
                  >
                    {bill.is_paid ? '已繳' : '未繳'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

/**
 * 總覽頁統計卡片，顯示圖示、標籤與數值。
 *
 * @param icon - 左側圖示元素
 * @param label - 統計指標名稱
 * @param value - 格式化後的數值字串
 */
function SummaryCard({
  icon,
  label,
  value,
}: {
  readonly icon: React.ReactNode
  readonly label: string
  readonly value: string
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-sm text-muted-foreground">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold">{value}</p>
    </div>
  )
}

export default OverviewPage
