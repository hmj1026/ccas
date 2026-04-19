/**
 * Bills 頁面 -- 帳單列表、付款狀態切換與 PDF 連結。
 * 預設：全部帳單，依 billing_month 降序。
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Check, Clock, ChevronLeft, ChevronRight } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { apiGet, apiPatch } from '@/lib/api-client'
import type { ApiResponse, BillItem, PaginatedResponse } from '@/lib/types'
import { formatAmount } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'
import { FilterBar, type FilterBarParams, type FilterKey } from '@/components/shared/filter-bar'
import { StagedAttachmentsWarning } from '@/components/staged-attachments-warning'

function BillsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const year = searchParams.get('year') ?? ''
  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const status = searchParams.get('status') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  const filterValues: FilterBarParams = {
    year, month, bank: bankCode, status, category: '', q: '',
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
    queryKey: ['bills', year, month, bankCode, status, page],
    queryFn: () =>
      apiGet<PaginatedResponse<BillItem>>('/api/bills', {
        year: year ? Number(year) : undefined,
        month: month || undefined,
        bank_code: bankCode || undefined,
        status: status || undefined,
        page,
        page_size: 20,
      }),
  })

  const togglePaid = useMutation({
    mutationFn: ({ id, is_paid }: { id: number; is_paid: boolean }) =>
      apiPatch<ApiResponse<BillItem>>(`/api/bills/${id}`, { is_paid }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bills'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  /**
   * 更新 URL 中的分頁參數；第 1 頁時刪除 `page` 參數保持 URL 乾淨。
   *
   * @param p - 目標頁碼
   */
  function setPage(p: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (p === 1) next.delete('page')
      else next.set('page', String(p))
      return next
    })
  }

  const pagination = data?.pagination

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">帳單管理</h1>

      <StagedAttachmentsWarning />

      <FilterBar
        show={['year', 'month', 'bank', 'status']}
        values={filterValues}
        onChange={handleFilterChange}
        extra={
          pagination && (
            <span className="text-sm text-muted-foreground">共 {pagination.total} 筆</span>
          )
        }
      />

      {/* Bill list */}
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} />
      ) : !data?.data.length ? (
        <EmptyState message="沒有符合條件的帳單" />
      ) : (
        <div className="space-y-3">
          {data.data.map((bill) => (
            <div
              key={bill.id}
              className="flex items-center justify-between rounded-lg border border-border p-4"
            >
              <div className="space-y-1">
                <p className="font-medium">{bill.bank_name ?? bill.bank_code}</p>
                <p className="text-sm text-muted-foreground">
                  {bill.billing_month} / 到期日: {bill.due_date}
                </p>
                <p className="text-lg font-bold">{formatAmount(bill.total_amount)}</p>
              </div>

              <div className="flex items-center gap-2">
                {bill.pdf_url && (
                  <a
                    href={bill.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                    aria-label={`開啟 ${bill.bank_name ?? bill.bank_code} PDF`}
                  >
                    <ExternalLink className="size-4" />
                    PDF
                  </a>
                )}
                <Button
                  variant={bill.is_paid ? 'secondary' : 'outline'}
                  size="sm"
                  disabled={togglePaid.isPending}
                  onClick={() =>
                    togglePaid.mutate({ id: bill.id, is_paid: !bill.is_paid })
                  }
                  aria-label={bill.is_paid ? '標記為未繳' : '標記為已繳'}
                >
                  {bill.is_paid ? (
                    <>
                      <Check className="size-4" data-icon="inline-start" />
                      已繳
                    </>
                  ) : (
                    <>
                      <Clock className="size-4" data-icon="inline-start" />
                      未繳
                    </>
                  )}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            aria-label="上一頁"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-sm">
            {page} / {pagination.total_pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pagination.total_pages}
            onClick={() => setPage(page + 1)}
            aria-label="下一頁"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

export default BillsPage
