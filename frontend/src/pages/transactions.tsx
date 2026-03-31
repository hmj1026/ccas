/**
 * Transactions 頁面 -- 交易查詢、篩選、分頁與 CSV 匯出。
 */
import { useQuery } from '@tanstack/react-query'
import { Download, Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { apiGet, apiFetchBlob } from '@/lib/api-client'
import type { PaginatedResponse, TransactionItem } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'

function formatAmount(amount: number, currency: string): string {
  return `${currency === 'TWD' ? '$' : currency + ' '}${amount.toLocaleString()}`
}

function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const category = searchParams.get('category') ?? ''
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')
  const pageSize = 20

  const { data, isLoading, error } = useQuery({
    queryKey: ['transactions', month, bankCode, category, q, page],
    queryFn: () =>
      apiGet<PaginatedResponse<TransactionItem>>('/api/transactions', {
        month: month || undefined,
        bank_code: bankCode || undefined,
        category: category || undefined,
        q: q || undefined,
        page,
        page_size: pageSize,
      }),
  })

  function updateParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
      if (key !== 'page') next.delete('page')
      return next
    })
  }

  async function handleExportCsv() {
    const blob = await apiFetchBlob('/api/transactions/export', {
      month: month || undefined,
      bank_code: bankCode || undefined,
      category: category || undefined,
      q: q || undefined,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions${month ? `-${month}` : ''}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">交易明細</h1>
        <Button variant="outline" size="sm" onClick={handleExportCsv}>
          <Download className="size-4" data-icon="inline-start" />
          匯出 CSV
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          type="month"
          value={month}
          onChange={(e) => updateParam('month', e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="月份篩選"
        />
        <input
          type="text"
          placeholder="銀行代碼"
          value={bankCode}
          onChange={(e) => updateParam('bank_code', e.target.value)}
          className="h-8 w-28 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="銀行篩選"
        />
        <input
          type="text"
          placeholder="分類"
          value={category}
          onChange={(e) => updateParam('category', e.target.value)}
          className="h-8 w-28 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="分類篩選"
        />
        <div className="relative">
          <Search className="absolute left-2.5 top-2 size-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜尋商家..."
            value={q}
            onChange={(e) => updateParam('q', e.target.value)}
            className="h-8 w-44 rounded-lg border border-input bg-background pl-8 pr-3 text-sm"
            aria-label="商家搜尋"
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} />
      ) : !data?.data.length ? (
        <EmptyState message="找不到符合條件的交易" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  <th className="px-3 py-2">日期</th>
                  <th className="px-3 py-2">商家</th>
                  <th className="px-3 py-2">分類</th>
                  <th className="px-3 py-2">銀行</th>
                  <th className="px-3 py-2 text-right">金額</th>
                </tr>
              </thead>
              <tbody>
                {data.data.map((tx) => (
                  <tr key={tx.id} className="border-t border-border">
                    <td className="px-3 py-2 whitespace-nowrap">{tx.trans_date}</td>
                    <td className="px-3 py-2">{tx.merchant}</td>
                    <td className="px-3 py-2">{tx.category ?? '-'}</td>
                    <td className="px-3 py-2">{tx.bank_code}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {formatAmount(tx.amount, tx.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.pagination && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                共 {data.pagination.total} 筆
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon-xs"
                  disabled={page <= 1}
                  onClick={() => updateParam('page', String(page - 1))}
                  aria-label="上一頁"
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <span>
                  {page} / {data.pagination.total_pages}
                </span>
                <Button
                  variant="outline"
                  size="icon-xs"
                  disabled={page >= data.pagination.total_pages}
                  onClick={() => updateParam('page', String(page + 1))}
                  aria-label="下一頁"
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default TransactionsPage
