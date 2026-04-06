/**
 * Transactions 頁面 -- 交易查詢、篩選、分頁與 CSV 匯出。
 * 預設：全部交易，依 trans_date 降序。
 */
import { useQuery } from '@tanstack/react-query'
import { Download, ChevronLeft, ChevronRight } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { apiGet, apiFetchBlob } from '@/lib/api-client'
import type { PaginatedResponse, TransactionItem } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'
import { FilterBar, type FilterBarParams, type FilterKey } from '@/components/shared/filter-bar'

/**
 * 將金額格式化為帶幣別前綴的字串。
 * TWD 顯示 `$`，其他幣別顯示幣別代碼。
 *
 * @param amount - 金額數值
 * @param currency - 幣別代碼，例如 `"TWD"`、`"USD"`
 * @returns 格式化字串，例如 `$1,234` 或 `USD 50`
 */
function formatAmount(amount: number, currency: string): string {
  return `${currency === 'TWD' ? '$' : currency + ' '}${amount.toLocaleString()}`
}

function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const year = searchParams.get('year') ?? ''
  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const category = searchParams.get('category') ?? ''
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')
  const pageSize = 20

  const filterValues: FilterBarParams = {
    year, month, bank: bankCode, status: '', category, q,
  }

  /**
   * 篩選列變更 callback；將指定維度寫入 URL search params 並重置分頁至第 1 頁。
   *
   * @param key - 變更的篩選維度
   * @param value - 新的篩選值，空字串時刪除該參數
   */
  function handleFilterChange(key: FilterKey, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      const paramKey = key === 'bank' ? 'bank_code' : key
      if (value) {
        next.set(paramKey, value)
      } else {
        next.delete(paramKey)
      }
      next.delete('page')
      return next
    })
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['transactions', year, month, bankCode, category, q, page],
    queryFn: () =>
      apiGet<PaginatedResponse<TransactionItem>>('/api/transactions', {
        year: year ? Number(year) : undefined,
        month: month || undefined,
        bank_code: bankCode || undefined,
        category: category || undefined,
        q: q || undefined,
        page,
        page_size: pageSize,
      }),
  })

  /**
   * 下載目前篩選條件的交易記錄為 CSV 檔案。
   * 動態產生帶篩選條件的檔名（含月份或年度）。
   */
  async function handleExportCsv() {
    const blob = await apiFetchBlob('/api/transactions/export', {
      year: year ? Number(year) : undefined,
      month: month || undefined,
      bank_code: bankCode || undefined,
      category: category || undefined,
      q: q || undefined,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions${month ? `-${month}` : year ? `-${year}` : ''}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  /**
   * 更新 URL 中的分頁參數；第 1 頁時刪除 `page` 參數保持 URL 乾淨。
   *
   * @param p - 目標頁碼
   */
  function updatePage(p: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (p === 1) next.delete('page')
      else next.set('page', String(p))
      return next
    })
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

      <FilterBar
        show={['year', 'month', 'bank', 'category', 'q']}
        values={filterValues}
        onChange={handleFilterChange}
      />

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
                  onClick={() => updatePage(page - 1)}
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
                  onClick={() => updatePage(page + 1)}
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
