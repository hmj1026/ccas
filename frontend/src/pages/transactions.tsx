/**
 * Transactions 頁面 -- 交易查詢、篩選、分頁與 CSV 匯出。
 * 預設：全部交易，依 trans_date 降序。
 */
import { useQuery } from '@tanstack/react-query'
import { Download, ChevronLeft, ChevronRight, Pencil } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { apiGet, apiFetchBlob } from '@/lib/api-client'
import type { PaginatedResponse, TransactionItem } from '@/lib/types'
import { formatAmount, formatDate } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'
import { FilterBar, type FilterBarParams } from '@/components/shared/filter-bar'
import { useFilterParams } from '@/lib/use-filter-params'

const FILTER_SHOW = ['year', 'month', 'bank', 'category', 'q'] as const

function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const year = searchParams.get('year') ?? ''
  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const category = searchParams.get('category') ?? ''
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')
  const pageSize = 20

  const filterValues = useMemo<FilterBarParams>(
    () => ({ year, month, bank: bankCode, status: '', category, q }),
    [year, month, bankCode, category, q],
  )

  const handleFilterChange = useFilterParams(true)

  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const { data, isLoading, error, refetch, isFetching } = useQuery({
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
    setExportError(null)
    setIsExporting(true)
    try {
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
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'CSV 匯出失敗，請稍後再試')
    } finally {
      setIsExporting(false)
    }
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
        <Button
          variant="outline"
          size="sm"
          onClick={handleExportCsv}
          disabled={isExporting}
        >
          <Download className="size-4" data-icon="inline-start" />
          {isExporting ? '匯出中...' : '匯出 CSV'}
        </Button>
      </div>

      {exportError ? (
        <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {exportError}
        </div>
      ) : null}

      <FilterBar
        show={FILTER_SHOW}
        values={filterValues}
        onChange={handleFilterChange}
      />

      {/* Table */}
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          message={error.message}
          onRetry={() => refetch()}
          isRetrying={isFetching}
        />
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
                  <th className="px-3 py-2 w-12" aria-label="操作"></th>
                </tr>
              </thead>
              <tbody>
                {data.data.map((tx) => (
                  <tr key={tx.id} className="tr-list border-t border-border">
                    <td className="px-3 py-2 whitespace-nowrap">{formatDate(tx.trans_date)}</td>
                    <td className="px-3 py-2">
                      <Link
                        to={`/transactions/${tx.id}`}
                        className="rounded-sm hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                      >
                        {tx.merchant}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{tx.category ?? '-'}</td>
                    <td className="px-3 py-2">{tx.bank_code}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {formatAmount(tx.amount, tx.currency)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {/* Visual-only duplicate of the keyboard-reachable merchant
                          link above; hidden from AT/tab order to avoid two
                          consecutive links to the same target per row. */}
                      <Link
                        to={`/transactions/${tx.id}`}
                        aria-hidden="true"
                        tabIndex={-1}
                        className="inline-flex items-center text-muted-foreground hover:text-foreground"
                      >
                        <Pencil className="size-4" />
                      </Link>
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
